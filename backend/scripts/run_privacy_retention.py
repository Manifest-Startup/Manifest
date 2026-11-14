"""
Privacy retention orchestrator.

A single nightly entry point that walks every data class with a defined
retention window and prunes / anonymises rows that exceeded their TTL.
Designed to be invoked from a scheduler (cron, k8s CronJob, Replit
scheduled deployment) so SOC 2 / GDPR / HIPAA reviewers can point at
*one* job that enforces every retention policy.

Each step is best-effort: a failure in one class does not prevent the
others from running. The summary is written to stdout as JSON for log
ingestion and to the security audit log so completion is provable.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

# Bootstrap sys.path so the script works whether invoked from repo root
# or from inside backend/.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, os.pardir))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
_REPO = os.path.abspath(os.path.join(_BACKEND, os.pardir))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from app.db.database import get_database_url, get_db_connection  # noqa: E402
from app.services.security_audit_service import record_security_event  # noqa: E402
from app.utils.logger import logger  # noqa: E402


# ---------------------------------------------------------------------------
# Retention policy table
# ---------------------------------------------------------------------------
# (name, sql, default_days). The SQL must accept exactly one positional
# parameter — the cutoff timestamp — and should be idempotent.
RETENTION_POLICIES: List[Dict[str, Any]] = [
    {
        "name": "expired_password_reset_tokens",
        "scope": "password_reset_tokens",
        "default_days": 1,
        "env": "MANIFEST_RETENTION_PWRESET_DAYS",
        "sql": "DELETE FROM password_reset_tokens WHERE expires_at < %s",
    },
    {
        "name": "stale_user_sessions",
        "scope": "user_sessions",
        "default_days": 90,
        "env": "MANIFEST_RETENTION_SESSIONS_DAYS",
        "sql": "DELETE FROM user_sessions WHERE COALESCE(last_seen_at, created_at) < %s",
    },
    {
        "name": "guest_accounts",
        "scope": "users",
        "default_days": 30,
        "env": "MANIFEST_RETENTION_GUEST_DAYS",
        "sql": (
            "DELETE FROM users WHERE COALESCE(role, '') = 'guest' "
            "AND created_at < %s AND deletion_requested_at IS NULL"
        ),
    },
    {
        "name": "consent_ledger_history",
        "scope": "privacy_consents",
        "default_days": 1825,  # 5 years for audit defensibility
        "env": "MANIFEST_RETENTION_CONSENT_DAYS",
        "sql": (
            "DELETE FROM privacy_consents WHERE consent_updated_at < %s "
            "AND user_id IS NULL AND visitor_id IS NULL"
        ),
    },
]


def _cutoff_for(days: int) -> datetime:
    from datetime import timedelta
    return datetime.now(timezone.utc) - timedelta(days=days)


def _apply_exception_predicates(sql: str, exceptions: List[Any], scope: str) -> tuple:
    """Inject ``AND NOT (<match>)`` clauses for every exception whose
    scope matches this policy. Returns ``(sql, applied_ids)``.

    The ``match`` predicate is sourced from the on-disk register that
    only the DPO can write to. We *intentionally* do not parameterise
    the predicate — the register is operator-only configuration, not
    user input — but we audit every applied predicate by id so any
    deviation from the default deletion plan is provable.
    """
    applied: List[str] = []
    for ex in exceptions:
        if getattr(ex, "scope", None) != scope:
            continue
        match = getattr(ex, "match", None)
        if not match:
            continue
        sql = f"{sql} AND NOT ({match})"
        applied.append(getattr(ex, "id", "?"))
    return sql, applied


def _run_policy(
    policy: Dict[str, Any],
    exceptions: List[Any] | None = None,
) -> Dict[str, Any]:
    days = int(os.getenv(policy["env"], policy["default_days"]) or policy["default_days"])
    cutoff = _cutoff_for(days)
    summary: Dict[str, Any] = {
        "name": policy["name"],
        "scope": policy.get("scope", policy["name"]),
        "days": days,
        "cutoff": cutoff.isoformat(),
        "deleted": 0,
        "outcome": "success",
        "exceptions_applied": [],
    }
    if not get_database_url():
        summary["outcome"] = "skipped_no_db"
        return summary

    sql = policy["sql"]
    if exceptions:
        sql, applied = _apply_exception_predicates(
            sql, exceptions, policy.get("scope", policy["name"])
        )
        summary["exceptions_applied"] = applied
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (cutoff,))
                summary["deleted"] = cur.rowcount or 0
            conn.commit()
    except Exception as exc:
        logger.exception("[retention] policy %s failed: %s", policy["name"], exc)
        summary["outcome"] = "failure"
        summary["error"] = str(exc)[:200]
    return summary


def run_all() -> Dict[str, Any]:
    started = datetime.now(timezone.utc)
    # Honour the retention exception register. **Fail-safe semantics**:
    # if the register file exists but is unreadable / malformed we
    # *abort* destructive deletion entirely and mark the run partial,
    # because silently dropping holds could destroy data that is under
    # legal hold or active investigation. Missing file (no exceptions
    # configured at all) is the only allowed empty state.
    from app.services.retention_exception_register import (  # local import keeps script light
        RegisterLoadError,
        _resolve_path,
        load_register_strict,
    )

    register_path = _resolve_path(None)
    # Single-read, fail-loud loader. ``load_register_strict`` performs
    # exactly one file read and raises ``RegisterLoadError`` for any
    # problem (parse error, wrong root shape, missing key, malformed
    # entry, rejected SQL match predicate). Eliminates the TOCTOU
    # window of a separate validate-then-load pair: a transient I/O
    # fault between the two cannot cause a fail-open destructive run.
    register_load_error: Optional[str] = None
    exception_objs: List[Any] = []
    try:
        exception_objs = load_register_strict(register_path)
    except RegisterLoadError as exc:
        register_load_error = exc.code
    except Exception as exc:  # defence in depth: anything unexpected aborts
        register_load_error = f"register_read_error:{type(exc).__name__}"

    active_exceptions = [
        {
            "id": e.id,
            "scope": e.scope,
            "approved_by": e.approved_by,
            "opened_at": e.opened_at,
            "expected_close": e.expected_close,
        }
        for e in exception_objs
    ]

    if register_load_error:
        logger.error(
            "[retention] aborting destructive run; register unreadable: %s (path=%s)",
            register_load_error,
            register_path,
        )
        results = [
            {
                "name": p["name"],
                "scope": p.get("scope", p["name"]),
                "days": int(os.getenv(p["env"], p["default_days"]) or p["default_days"]),
                "cutoff": _cutoff_for(
                    int(os.getenv(p["env"], p["default_days"]) or p["default_days"])
                ).isoformat(),
                "deleted": 0,
                "outcome": "skipped_register_error",
                "exceptions_applied": [],
            }
            for p in RETENTION_POLICIES
        ]
    else:
        results = [_run_policy(p, exception_objs) for p in RETENTION_POLICIES]

    finished = datetime.now(timezone.utc)
    summary = {
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_ms": int((finished - started).total_seconds() * 1000),
        "policies": results,
        "active_exceptions": active_exceptions,
        "register_path": register_path,
        "register_status": (
            "ok"
            if not register_load_error
            else f"error:{register_load_error}"
        ),
    }
    try:
        record_security_event(
            "retention_run_completed",
            actor_id="system",
            actor_type="system",
            action="retention_run",
            target_type="dataset",
            outcome=(
                "success"
                if all(r["outcome"] in {"success", "skipped_no_db"} for r in results)
                and not register_load_error
                else "partial"
            ),
            metadata={
                "policies": [
                    {"name": r["name"], "deleted": r["deleted"], "outcome": r["outcome"]}
                    for r in results
                ],
                "active_exceptions": active_exceptions,
            },
        )
    except Exception:  # pragma: no cover - never block on audit
        logger.warning("[retention] audit emit failed", exc_info=True)
    return summary


def main() -> int:
    summary = run_all()
    print(json.dumps(summary, default=str, indent=2))
    if any(p["outcome"] == "failure" for p in summary["policies"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
