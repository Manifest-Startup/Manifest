"""GraphQL types for goals that run (``app.services.goals``)."""

from typing import Any

import strawberry
from strawberry.scalars import JSON


@strawberry.type
class GoalStep:
    key: str
    title: str
    capability: str
    risk_tier: int
    status: str
    depends_on: list[str]
    result: JSON
    verification: JSON
    attempts: int
    last_error: str | None
    next_check_at: str | None


@strawberry.type
class ApprovalRequest:
    """Something Manifest will do only if you say yes. Read ``summary`` and ``consequences``
    to the person; to decide, pass ``scopeSha256`` back to ``decideApproval``."""

    id: str
    goal_id: str
    action: str
    summary: str
    reason: str
    consequences: str
    risk_tier: int
    scope: JSON
    scope_sha256: str
    status: str
    expires_at: str | None
    decided_at: str | None


@strawberry.type
class KnowledgeFact:
    id: str
    subject_type: str
    subject: str
    predicate: str
    value: str
    kind: str
    confidence: float
    source_type: str
    source_ref: str
    status: str
    superseded_by: str | None
    created_at: str | None


@strawberry.type
class GoalEvent:
    type: str
    summary: str
    created_at: str | None
    payload: JSON


@strawberry.type
class GoalReport:
    """Say this aloud: only the parts with something in them."""

    completed: list[str]
    in_progress: list[str]
    waiting: list[str]
    needs_you: list[str]
    next: list[str]
    spoken: str


@strawberry.type
class Goal:
    id: str
    title: str
    desired_outcome: str
    success_criteria: list[str]
    status: str
    idea_id: str | None
    created_at: str | None
    updated_at: str | None
    existing: bool
    steps: list[GoalStep]
    approvals: list[ApprovalRequest]
    timeline: list[GoalEvent]
    facts: list[KnowledgeFact]
    report: GoalReport | None


@strawberry.type
class StandingAuthorization:
    """A standing yes: Manifest may do ``action`` for these recipients without asking, up to
    ``maxPerWeek`` times a week, until ``expiresAt`` or until it is revoked."""

    id: str
    action: str
    recipients: list[str]
    max_per_week: int
    used_this_week: int
    note: str
    status: str
    expires_at: str | None
    created_at: str | None


@strawberry.type
class GoalCapability:
    name: str
    title: str
    risk_tier: int
    needs_approval: bool
    description: str
    required_inputs: list[str]


def map_approval(row: dict[str, Any]) -> ApprovalRequest:
    return ApprovalRequest(
        id=row["id"],
        goal_id=row["goal_id"],
        action=row["action"],
        summary=row["summary"],
        reason=row["reason"],
        consequences=row["consequences"],
        risk_tier=int(row["risk_tier"]),
        scope=row.get("scope") or {},
        scope_sha256=row["scope_sha256"],
        status=row["status"],
        expires_at=row.get("expires_at"),
        decided_at=row.get("decided_at"),
    )


def map_fact(row: dict[str, Any]) -> KnowledgeFact:
    return KnowledgeFact(
        id=row["id"],
        subject_type=row["subject_type"],
        subject=row["subject_key"],
        predicate=row["predicate"],
        value=row["object_value"],
        kind=row["kind"],
        confidence=float(row["confidence"]),
        source_type=row["source_type"],
        source_ref=row["source_ref"],
        status=row["status"],
        superseded_by=row.get("superseded_by"),
        created_at=row.get("created_at"),
    )


def _spoken(report: dict[str, list[str]]) -> str:
    labels = (
        ("completed", "Done"),
        ("in_progress", "In progress"),
        ("waiting", "Waiting"),
        ("needs_you", "Needs you"),
        ("next", "Next"),
    )
    parts = [f"{label}: {'; '.join(report[key])}." for key, label in labels if report.get(key)]
    return " ".join(parts) or "Nothing has happened yet."


def map_goal(goal: dict[str, Any], view: dict[str, Any] | None = None) -> Goal:
    view = view or {}
    report = view.get("report")
    return Goal(
        id=goal["id"],
        title=goal["title"],
        desired_outcome=goal.get("desired_outcome") or "",
        success_criteria=list((goal.get("success_criteria") or {}).get("items") or []),
        status=goal["status"],
        idea_id=goal.get("idea_id"),
        created_at=goal.get("created_at"),
        updated_at=goal.get("updated_at"),
        existing=bool(view.get("existing")),
        steps=[
            GoalStep(
                key=t["step_key"],
                title=t["title"],
                capability=t["capability"],
                risk_tier=int(t["risk_tier"]),
                status=t["status"],
                depends_on=list(t.get("depends_on") or []),
                result=t.get("result") or {},
                verification=t.get("verification") or {},
                attempts=int(t.get("attempts") or 0),
                last_error=t.get("last_error"),
                next_check_at=t.get("next_check_at"),
            )
            for t in view.get("tasks") or []
        ],
        approvals=[map_approval(a) for a in view.get("approvals") or []],
        timeline=[
            GoalEvent(
                type=e["type"],
                summary=e["summary"],
                created_at=e.get("created_at"),
                payload=e.get("payload") or {},
            )
            for e in view.get("events") or []
        ],
        facts=[map_fact(f) for f in view.get("facts") or []],
        report=GoalReport(**report, spoken=_spoken(report)) if report else None,
    )
