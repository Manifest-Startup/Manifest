"""Risk tiers and approvals, enforced where a step runs rather than in a prompt.

Tier 0 reads and tier 1 reversible work inside Manifest run without asking. Tier 2 (anything
another person sees or that changes shared state, such as sending a message) and tier 3
(money, legal, access, destructive) run only with an approval whose ``scope`` is exactly
what will happen. The scope is hashed; the person approves that hash, and the step checks it
again right before it runs, so nothing (a later edit, a model, text in a reply) can change
the message, the recipient or the channel after the person said yes.

There are no standing authorizations yet: every tier 2+ step asks once.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from app.services.goals import store

APPROVAL_TTL = timedelta(days=7)
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
