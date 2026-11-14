"""DSAR + breach deadline checker.

Designed to run on a 1h schedule. Walks ``dsar_requests`` and
``incident_breach_timers`` and emits an audit event for every row whose
statutory deadline is approaching (``--warn-hours``, default 48) or
already breached. The audit chain (T14) makes the alerts tamper-evident
and the security pipeline can wire SIEM alerting on the
``dsar_deadline_warning`` / ``dsar_deadline_breached`` /
``breach_timer_deadline_warning`` event types.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, os.pardir))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.breach_timer_service import find_due as find_due_breach  # noqa: E402
from app.services.dsar_workflow_service import find_overdue  # noqa: E402
from app.services.security_audit_service import record_security_event  # noqa: E402
from app.utils.logger import logger  # noqa: E402


def _emit(event_type: str, target_id: str, metadata: dict) -> None:
    try:
        record_security_event(
            event_type,
            actor_id="system",
            actor_type="system",
            action=event_type,
            target_type=event_type.split("_")[0],
            target_id=target_id,
            outcome="warning" if "warning" in event_type else "failure",
            metadata=metadata,
        )
    except Exception:  # pragma: no cover
        logger.warning("[deadline_checker] audit emit failed", exc_info=True)


def check_dsar(warn_hours: int = 48) -> dict:
    breached = find_overdue(window_hours=0)
    warning = [
        r for r in find_overdue(window_hours=warn_hours)
        if r not in breached
    ]
    for row in breached:
        _emit("dsar_deadline_breached", str(row["id"]), {"due_at": row.get("due_at"), "type": row.get("type")})
    for row in warning:
        _emit("dsar_deadline_warning", str(row["id"]), {"due_at": row.get("due_at"), "type": row.get("type")})
    return {"breached": len(breached), "warning": len(warning)}


def check_breach_timers(warn_hours: int = 24) -> dict:
    rows = find_due_breach(within_hours=warn_hours)
    now = datetime.now(timezone.utc)
    breached = []
    warning = []
    for r in rows:
        deadline = r.get("deadline_at")
        if isinstance(deadline, str):
            try:
                deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
            except Exception:
                deadline = None
        if deadline and deadline <= now:
            breached.append(r)
            _emit(
                "breach_timer_deadline_breached",
                str(r["id"]),
                {"deadline_at": r.get("deadline_at"), "kind": r.get("kind")},
            )
        else:
            warning.append(r)
            _emit(
                "breach_timer_deadline_warning",
                str(r["id"]),
                {"deadline_at": r.get("deadline_at"), "kind": r.get("kind")},
            )
    return {"breached": len(breached), "warning": len(warning)}


def main() -> int:
    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "dsar": check_dsar(),
        "breach": check_breach_timers(),
    }
    print(json.dumps(summary, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
