"""GraphQL types and mappers for the multi-turn idea qualification agent."""

import json
from typing import Any

import strawberry


@strawberry.type
class QualificationMessage:
    role: str
    content: str
    ts: str | None = None


@strawberry.type
class IdeaQualificationSession:
    id: str
    user_id: str
    idea_id: str | None = None
    initial_idea_text: str
    status: str
    transcript: list[QualificationMessage]
    next_question: str | None = None
    turn_count: int = 0
    qualification_score: int | None = None
    qualification_explanation: str | None = None
    user_seriousness: int | None = None
    user_domain_knowledge: int | None = None
    user_goals: str | None = None
    user_budget: str | None = None
    user_timeline: str | None = None
    user_execution_ability: int | None = None
    idea_market_need: int | None = None
    idea_target_customer: str | None = None
    idea_feasibility: int | None = None
    idea_defensibility: int | None = None
    idea_revenue_potential: int | None = None
    idea_competition: str | None = None
    idea_risks: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def _map_qualification_session(row: dict[str, Any]) -> IdeaQualificationSession:
    """Convert a DB row into the GraphQL type. Tolerates missing fields."""
    transcript_raw = row.get("transcript") or []
    if isinstance(transcript_raw, str):
        try:
            transcript_raw = json.loads(transcript_raw)
        except (TypeError, ValueError):
            transcript_raw = []
    transcript = [
        QualificationMessage(
            role=str(item.get("role", "")),
            content=str(item.get("content", "")),
            ts=item.get("ts"),
        )
        for item in transcript_raw
        if isinstance(item, dict)
    ]
    created_at = row.get("created_at")
    updated_at = row.get("updated_at")
    return IdeaQualificationSession(
        id=str(row.get("id", "")),
        user_id=str(row.get("user_id", "")),
        idea_id=row.get("idea_id"),
        initial_idea_text=str(row.get("initial_idea_text", "")),
        status=str(row.get("status", "in_progress")),
        transcript=transcript,
        next_question=row.get("next_question"),
        turn_count=int(row.get("turn_count") or 0),
        qualification_score=row.get("qualification_score"),
        qualification_explanation=row.get("qualification_explanation"),
        user_seriousness=row.get("user_seriousness"),
        user_domain_knowledge=row.get("user_domain_knowledge"),
        user_goals=row.get("user_goals"),
        user_budget=row.get("user_budget"),
        user_timeline=row.get("user_timeline"),
        user_execution_ability=row.get("user_execution_ability"),
        idea_market_need=row.get("idea_market_need"),
        idea_target_customer=row.get("idea_target_customer"),
        idea_feasibility=row.get("idea_feasibility"),
        idea_defensibility=row.get("idea_defensibility"),
        idea_revenue_potential=row.get("idea_revenue_potential"),
        idea_competition=row.get("idea_competition"),
        idea_risks=row.get("idea_risks"),
        created_at=(
            created_at.isoformat()
            if hasattr(created_at, "isoformat")
            else (str(created_at) if created_at else None)
        ),
        updated_at=(
            updated_at.isoformat()
            if hasattr(updated_at, "isoformat")
            else (str(updated_at) if updated_at else None)
        ),
    )
