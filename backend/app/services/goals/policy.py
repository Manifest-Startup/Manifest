"""Risk tiers and approvals, enforced where a step runs rather than in a prompt.

Tier 0 reads and tier 1 reversible work inside Manifest run without asking. Tier 2 (anything
another person sees or that changes shared state, such as sending a message) and tier 3
(money, legal, access, destructive) run only with an approval whose ``scope`` is exactly
what will happen. The scope is hashed; the person approves that hash, and the step checks it
again right before it runs, so nothing (a later edit, a model, text in a reply) can change
the message, the recipient or the channel after the person said yes.

Standing authorizations (ADR 0022) let the person pre-approve one narrow kind of tier 2
action: today, sending messages to named Open Media handles, at most N a week, until an
expiry or until they revoke it. Tier 3 is never covered. Each use is written as an approved
approval row (``decided_via = "standing:<id>"``) with the exact scope, so the audit trail is
the same as for a one-off yes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from app.services.goals import store
from app.utils.logger import logger

APPROVAL_TTL = timedelta(days=7)
GRANT_MAX_DAYS = 90
STANDING_ACTIONS = {"message.send"}
REQUIRES_APPROVAL_FROM_TIER = 2


class ApprovalError(ValueError):
    pass


def scope_sha256(scope: dict[str, Any]) -> str:
    canonical = json.dumps(scope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def needs_approval(tier: int) -> bool:
    return int(tier) >= REQUIRES_APPROVAL_FROM_TIER


def _expired(approval: dict[str, Any]) -> bool:
    expires = store.parse_time(approval.get("expires_at"))
    return expires is not None and expires <= store.now()


def current_for_task(db: Any, user_id: str, task_id: str) -> dict[str, Any] | None:
    """The latest approval for a task (pending or decided), newest first."""
    rows = store.select(db, store.APPROVALS, user_id=user_id, task_id=task_id)
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows[0] if rows else None


def is_authorized(db: Any, user_id: str, task_id: str, scope: dict[str, Any]) -> bool:
    """True only for an approved, unexpired approval of exactly this scope."""
    approval = current_for_task(db, user_id, task_id)
    return bool(
        approval
        and approval.get("status") == "approved"
        and approval.get("scope_sha256") == scope_sha256(scope)
        and not _expired(approval)
    )


def request(
    db: Any,
    *,
    user_id: str,
    goal_id: str,
    task: dict[str, Any],
    scope: dict[str, Any],
    summary: str,
    reason: str,
    consequences: str,
) -> dict[str, Any]:
    """Ask once per task and scope. A changed scope supersedes the old pending request."""
    digest = scope_sha256(scope)
    existing = current_for_task(db, user_id, task["id"])
    if existing and existing.get("status") == "pending":
        if not _expired(existing) and existing.get("scope_sha256") == digest:
            return existing
        store.cas_update(
            db,
            store.APPROVALS,
            existing["id"],
            {"status": "pending"},
            {"status": "expired" if _expired(existing) else "superseded"},
        )
    approval = store.insert(
        db,
        store.APPROVALS,
        {
            "user_id": user_id,
            "goal_id": goal_id,
            "task_id": task["id"],
            "action": task["capability"],
            "summary": summary[:500],
            "reason": reason[:500],
            "consequences": consequences[:500],
            "risk_tier": int(task["risk_tier"]),
            "scope": scope,
            "scope_sha256": digest,
            "status": "pending",
            "expires_at": (store.now() + APPROVAL_TTL).isoformat(),
        },
    )
    store.record_event(
        db,
        user_id,
        goal_id,
        "approval.requested",
        summary,
        {"approval_id": approval["id"], "task_id": task["id"], "risk_tier": task["risk_tier"]},
        dedupe_key=f"approval.requested:{approval['id']}",
    )
    return approval


def decide(
    db: Any,
    user_id: str,
    approval_id: str,
    *,
    approve: bool,
    scope_sha256_seen: str,
    via: str,
) -> dict[str, Any]:
    """Record the person's decision. ``scope_sha256_seen`` proves they saw this exact scope."""
    approval = store.one(db, store.APPROVALS, id=approval_id, user_id=user_id)
    if approval is None:
        raise ApprovalError("No such approval.")
    if approval.get("status") != "pending":
        raise ApprovalError(f"This approval is already {approval.get('status')}.")
    if _expired(approval):
        store.cas_update(
            db, store.APPROVALS, approval_id, {"status": "pending"}, {"status": "expired"}
        )
        raise ApprovalError("This approval expired. Ask Manifest to prepare it again.")
    if (scope_sha256_seen or "").strip().lower() != approval["scope_sha256"]:
        raise ApprovalError(
            "That isn't the version waiting for approval. Read the current request and decide on it."
        )
    status = "approved" if approve else "denied"
    decided = store.cas_update(
        db,
        store.APPROVALS,
        approval_id,
        {"status": "pending"},
        {"status": status, "decided_at": store.now().isoformat(), "decided_via": via[:40]},
    )
    if decided is None:
        raise ApprovalError("Someone decided this approval a moment ago.")
    store.record_event(
        db,
        user_id,
        approval["goal_id"],
        f"approval.{'granted' if approve else 'denied'}",
        f"{'Approved' if approve else 'Declined'}: {approval['summary']}",
        {"approval_id": approval_id, "task_id": approval["task_id"], "via": via},
        dedupe_key=f"approval.decided:{approval_id}",
    )
    return decided


# --- standing authorizations ----------------------------------------------------------------


def _handles(recipients: list[str]) -> list[str]:
    clean = []
    for raw in recipients or []:
        handle = str(raw or "").strip().lstrip("@").lower()
        if not handle or len(handle) > 64 or any(c.isspace() for c in handle):
            raise ApprovalError(f"'{raw}' isn't an Open Media handle.")
        if handle not in clean:
            clean.append(handle)
    if not 1 <= len(clean) <= 20:
        raise ApprovalError("Name between 1 and 20 people.")
    return clean


def grant(
    db: Any,
    user_id: str,
    *,
    action: str,
    recipients: list[str],
    max_per_week: int,
    days: int,
    note: str = "",
) -> dict[str, Any]:
    if action not in STANDING_ACTIONS:
        raise ApprovalError(f"Only {', '.join(sorted(STANDING_ACTIONS))} can be pre-approved.")
    if not 1 <= int(max_per_week) <= 20:
        raise ApprovalError("Allow between 1 and 20 a week.")
    if not 1 <= int(days) <= GRANT_MAX_DAYS:
        raise ApprovalError(f"A standing approval lasts 1 to {GRANT_MAX_DAYS} days.")
    row = store.insert(
        db,
        store.GRANTS,
        {
            "user_id": user_id,
            "action": action,
            "recipients": _handles(recipients),
            "max_per_week": int(max_per_week),
            "note": (note or "")[:300],
            "status": "active",
            "expires_at": (store.now() + timedelta(days=int(days))).isoformat(),
        },
    )
    store.record_event(
        db,
        user_id,
        None,
        "authorization.granted",
        f"Standing approval: {action} to {', '.join('@' + h for h in row['recipients'])}, "
        f"up to {row['max_per_week']} a week, for {int(days)} days",
        {"grant_id": row["id"]},
    )
    return row


def revoke(db: Any, user_id: str, grant_id: str) -> dict[str, Any]:
    row = store.one(db, store.GRANTS, id=grant_id, user_id=user_id)
    if row is None:
        raise ApprovalError("No such standing approval.")
    if row["status"] == "revoked":
        return row
    revoked = store.cas_update(
        db,
        store.GRANTS,
        grant_id,
        {"status": "active"},
        {"status": "revoked", "revoked_at": store.now().isoformat()},
    )
    store.record_event(
        db,
        user_id,
        None,
        "authorization.revoked",
        "Standing approval revoked",
        {"grant_id": grant_id},
    )
    return revoked or row


def grants(db: Any, user_id: str, *, include_inactive: bool = False) -> list[dict[str, Any]]:
    rows = store.select(db, store.GRANTS, user_id=user_id)
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    live = [r for r in rows if r["status"] == "active" and not _expired(r)]
    return rows if include_inactive else live


def _uses_this_week(db: Any, user_id: str, grant_id: str) -> int:
    since = store.now() - timedelta(days=7)
    rows = store.select(db, store.APPROVALS, user_id=user_id, decided_via=f"standing:{grant_id}")
    return sum(1 for r in rows if (store.parse_time(r.get("decided_at")) or since) > since)


def use_standing(
    db: Any,
    *,
    user_id: str,
    goal_id: str,
    task: dict[str, Any],
    scope: dict[str, Any],
    summary: str,
    reason: str,
    consequences: str,
) -> dict[str, Any] | None:
    """Approve this exact scope under a matching standing authorization, if one has room."""
    if int(task["risk_tier"]) != 2 or scope.get("action") not in STANDING_ACTIONS:
        return None
    recipient = str(scope.get("to") or "").lower()
    try:
        active = grants(db, user_id)
    except Exception as exc:  # noqa: BLE001 — no grants table yet: fall back to asking
        logger.warning(
            "[goals] standing approvals unavailable", extra={"exception.type": type(exc).__name__}
        )
        return None
    for row in active:
        if row["action"] != scope["action"] or recipient not in (row.get("recipients") or []):
            continue
        if _uses_this_week(db, user_id, row["id"]) >= int(row["max_per_week"]):
            continue
        existing = current_for_task(db, user_id, task["id"])
        if existing and existing.get("status") == "pending":
            store.cas_update(
                db, store.APPROVALS, existing["id"], {"status": "pending"}, {"status": "superseded"}
            )
        stamp = store.now().isoformat()
        approval = store.insert(
            db,
            store.APPROVALS,
            {
                "user_id": user_id,
                "goal_id": goal_id,
                "task_id": task["id"],
                "action": task["capability"],
                "summary": summary[:500],
                "reason": reason[:500],
                "consequences": consequences[:500],
                "risk_tier": int(task["risk_tier"]),
                "scope": scope,
                "scope_sha256": scope_sha256(scope),
                "status": "approved",
                "decided_via": f"standing:{row['id']}",
                "decided_at": stamp,
                "expires_at": (store.now() + APPROVAL_TTL).isoformat(),
            },
        )
        store.record_event(
            db,
            user_id,
            goal_id,
            "approval.granted",
            f"Approved by your standing approval: {summary}",
            {"approval_id": approval["id"], "task_id": task["id"], "grant_id": row["id"]},
            dedupe_key=f"approval.decided:{approval['id']}",
        )
        return approval
    return None
