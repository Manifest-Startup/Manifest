"""GraphQL resolvers for goals that run: plans, approvals, progress and what was learned.

Thin on purpose: the rules (risk tiers, approvals, verification) live in
``app.services.goals`` and are enforced there, whoever calls.
"""

from __future__ import annotations

import asyncio
from typing import Any

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.resolvers.discovery import _idea_for
from app.graphql.types.goals import (
    ApprovalRequest,
    Goal,
    GoalCapability,
    KnowledgeFact,
    StandingAuthorization,
    map_approval,
    map_fact,
    map_goal,
)
from app.services.goals import engine, knowledge, policy
from app.services.goals.capabilities import REGISTRY
from strawberry.scalars import JSON

_ERRORS = (engine.GoalError, policy.ApprovalError, knowledge.KnowledgeError)


def _uid(info: strawberry.Info) -> str:
    return str(get_current_user_id(info.context["request"]))


async def _call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except _ERRORS as exc:
        raise ValueError(str(exc)) from None


def _goal(view: dict[str, Any]) -> Goal:
    return map_goal(view["goal"], view)


def _grant(row: dict[str, Any], used: int) -> StandingAuthorization:
    return StandingAuthorization(
        id=row["id"],
        action=row["action"],
        recipients=list(row.get("recipients") or []),
        max_per_week=int(row["max_per_week"]),
        used_this_week=used,
        note=row.get("note") or "",
        status=row["status"],
        expires_at=row.get("expires_at"),
        created_at=row.get("created_at"),
    )


def _signed_in_browser(info: strawberry.Info) -> bool:
    """The person in the web app (session cookie), not a token an agent or script holds."""
    request = info.context["request"]
    cookies = getattr(request, "cookies", {}) or {}
    return not request.headers.get("authorization") and bool(
        cookies.get("session_token") or cookies.get("access_token")
    )


def _via(info: strawberry.Info) -> str:
    agent = info.context["request"].headers.get("user-agent", "") or "api"
    return agent.split("/")[0][:40] or "api"


@strawberry.type
class GoalsQuery:
    @strawberry.field
    async def goals(self, info: strawberry.Info, include_closed: bool = False) -> list[Goal]:
        """Your goals, most recently active first (closed ones with includeClosed), each with
        its steps, approvals waiting for you and a progress report (``report.spoken``)."""
        db, uid = info.context["db"], _uid(info)
        rows = await _call(engine.list_goals, db, uid, include_closed=include_closed)
        views = [await _call(engine.view, db, uid, g["id"]) for g in rows[:20]]
        return [_goal(v) for v in views]

    @strawberry.field
    async def goal(self, info: strawberry.Info, goal_id: str) -> Goal:
        """One goal with its steps, approvals, timeline, facts and a progress report to say
        aloud (``report.spoken``). Reading it doesn't run anything; use advanceGoal for that."""
        view = await _call(engine.view, info.context["db"], _uid(info), goal_id)
        return _goal(view)

    @strawberry.field
    async def pending_approvals(self, info: strawberry.Info) -> list[ApprovalRequest]:
        """Everything waiting for your yes or no, across goals."""
        rows = await _call(engine.pending_approvals, info.context["db"], _uid(info))
        return [map_approval(a) for a in rows]

    @strawberry.field
    async def goal_capabilities(self) -> list[GoalCapability]:
        """The steps a goal's plan can use, with their risk tier. Tier 2 and up always wait
        for the person's approval of exactly what will happen."""
        return [
            GoalCapability(
                name=c.name,
                title=c.title,
                risk_tier=c.tier,
                needs_approval=policy.needs_approval(c.tier),
                description=c.description,
                required_inputs=list(c.required),
            )
            for c in REGISTRY.values()
        ]

    @strawberry.field
    async def knowledge_facts(
        self,
        info: strawberry.Info,
        subject: str,
        subject_type: str = "person",
        include_history: bool = False,
    ) -> list[KnowledgeFact]:
        """What Manifest knows about a person (an Open Media handle) or other subject, with
        each fact's source, kind and confidence. Corrected facts appear only with includeHistory."""
        rows = await _call(
            knowledge.facts_about,
            info.context["db"],
            _uid(info),
            subject_type,
            subject,
            include_history=include_history,
        )
        return [map_fact(f) for f in rows]

    @strawberry.field
    async def standing_authorizations(
        self, info: strawberry.Info, include_inactive: bool = False
    ) -> list[StandingAuthorization]:
        """What Manifest may do without asking each time (ADR 0022), with this week's uses."""
        db, uid = info.context["db"], _uid(info)
        rows = await _call(policy.grants, db, uid, include_inactive=include_inactive)
        return [_grant(r, policy._uses_this_week(db, uid, r["id"])) for r in rows]


@strawberry.type
class GoalsMutation:
    @strawberry.mutation
    async def create_goal(
        self,
        info: strawberry.Info,
        title: str,
        steps: JSON,
        desired_outcome: str = "",
        success_criteria: list[str] | None = None,
        idea_id: str | None = None,
    ) -> Goal:
        """Save a goal the person committed to, with a plan: steps = [{key, capability, input,
        depends_on}] (see goalCapabilities; reference an earlier step's result as
        "$steps.<key>" or "$steps.<key>.<field>"). Runs what it can at once; tier 2+ steps wait
        for approval. Only for real commitments, not ideas being explored. An active goal with
        the same title is returned instead of a duplicate (existing: true)."""
        db, uid = info.context["db"], _uid(info)
        if idea_id:
            await _idea_for(info, idea_id, write=True)
        if not isinstance(steps, list):
            raise ValueError("steps is a list of {key, capability, input, depends_on}.")
        view = await _call(
            engine.create_goal,
            db,
            uid,
            title=title,
            steps=steps,
            desired_outcome=desired_outcome,
            success_criteria=success_criteria,
            idea_id=idea_id,
            source={"via": _via(info)},
        )
        return _goal(view)

    @strawberry.mutation
    async def start_outreach_goal(
        self,
        info: strawberry.Info,
        handle: str,
        message: str,
        purpose: str = "",
        title: str | None = None,
        idea_id: str | None = None,
        wait_days: int = 7,
    ) -> Goal:
        """Reach out to someone on Open Media and hear back: checks the handle, prepares the
        message, asks the person to approve exactly that message (pendingApprovals), sends it,
        waits for the reply and records it as knowledge. Nothing is sent before approval."""
        if idea_id:
            await _idea_for(info, idea_id, write=True)
        wait = max(1, min(int(wait_days), 30))
        who = handle.strip().lstrip("@")
        view = await _call(
            engine.create_goal,
            info.context["db"],
            _uid(info),
            title=title or f"Hear back from @{who}",
            steps=engine.outreach_plan(who, message, purpose=purpose, wait_days=wait),
            desired_outcome=purpose or f"A reply from @{who}",
            success_criteria=[f"@{who} replies on Open Media"],
            idea_id=idea_id,
            source={"via": _via(info), "template": "outreach"},
        )
        return _goal(view)

    @strawberry.mutation
    async def advance_goal(self, info: strawberry.Info, goal_id: str) -> Goal:
        """Run every step that can run now (and check for replies), then report progress."""
        view = await _call(
            engine.advance, info.context["db"], _uid(info), goal_id, force_check=True
        )
        return _goal(view)

    @strawberry.mutation
    async def decide_approval(
        self, info: strawberry.Info, approval_id: str, approve: bool, scope_sha256: str
    ) -> Goal:
        """Approve or decline one request. Only after the person clearly said yes or no to this
        exact request (its summary and consequences); pass its scopeSha256 unchanged. Approving
        runs the step at once."""
        view = await _call(
            engine.decide_approval,
            info.context["db"],
            _uid(info),
            approval_id,
            approve=approve,
            scope_sha256=scope_sha256,
            via=_via(info),
        )
        return _goal(view)

    @strawberry.mutation
    async def grant_standing_authorization(
        self,
        info: strawberry.Info,
        recipients: list[str],
        max_per_week: int = 3,
        days: int = 30,
        note: str = "",
        action: str = "message.send",
    ) -> StandingAuthorization:
        """Let Manifest send messages to these Open Media handles without asking each time,
        up to maxPerWeek a week for `days` days (max 90). Only from the Manifest web app,
        signed in: agents and API tokens can't grant themselves permission."""
        if not _signed_in_browser(info):
            raise ValueError(
                "Standing approvals can only be given in the Manifest app (Messages), not by an agent."
            )
        row = await _call(
            policy.grant,
            info.context["db"],
            _uid(info),
            action=action,
            recipients=recipients,
            max_per_week=max_per_week,
            days=days,
            note=note,
        )
        return _grant(row, 0)

    @strawberry.mutation
    async def revoke_standing_authorization(
        self, info: strawberry.Info, authorization_id: str
    ) -> StandingAuthorization:
        """Stop a standing approval now; Manifest asks again for each action."""
        db, uid = info.context["db"], _uid(info)
        row = await _call(policy.revoke, db, uid, authorization_id)
        return _grant(row, policy._uses_this_week(db, uid, row["id"]))

    @strawberry.mutation
    async def cancel_goal(self, info: strawberry.Info, goal_id: str) -> Goal:
        """Stop a goal: open steps and pending approvals are cancelled; history stays."""
        view = await _call(engine.cancel_goal, info.context["db"], _uid(info), goal_id)
        return _goal(view)

    @strawberry.mutation
    async def retry_goal_step(self, info: strawberry.Info, goal_id: str, step_key: str) -> Goal:
        """Try a blocked or failed step again after the person fixed what blocked it."""
        view = await _call(engine.retry_step, info.context["db"], _uid(info), goal_id, step_key)
        return _goal(view)

    @strawberry.mutation
    async def correct_knowledge(
        self,
        info: strawberry.Info,
        subject: str,
        predicate: str,
        value: str,
        subject_type: str = "person",
        goal_id: str | None = None,
    ) -> KnowledgeFact:
        """The person corrects what Manifest knows ("@ana is our technology partner, not a
        customer": subject @ana, predicate relationship, value technology partner). Earlier
        facts are kept as superseded, never repeated as current."""
        result = await _call(
            knowledge.correct,
            info.context["db"],
            _uid(info),
            subject_type=subject_type,
            subject_key=subject,
            predicate=predicate,
            value=value,
            goal_id=goal_id,
        )
        return map_fact(result["fact"])
