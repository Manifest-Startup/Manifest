"""GraphQL types and mappers for Business Model Canvas sections and partner discovery."""

from typing import Any

import strawberry


@strawberry.type
class BmcSection:
    section_name: str
    content: str | None = None
    content_format: str = "markdown"
    needs_user_review: bool = False
    generated_by_run_id: str | None = None
    last_generated_at: str | None = None
    last_user_edit_at: str | None = None


def _map_bmc_section(row: dict[str, Any]) -> BmcSection:
    def _iso(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    return BmcSection(
        section_name=str(row.get("section_name", "")),
        content=row.get("content"),
        content_format=str(row.get("content_format") or "markdown"),
        needs_user_review=bool(row.get("needs_user_review") or False),
        generated_by_run_id=row.get("generated_by_run_id"),
        last_generated_at=_iso(row.get("last_generated_at")),
        last_user_edit_at=_iso(row.get("last_user_edit_at")),
    )


@strawberry.type
class PartnerCandidate:
    id: str
    idea_id: str
    name: str
    website: str | None = None
    category: str
    why_relevant: str | None = None
    suggested_use: str | None = None
    integration_type: str
    data_required: str | None = None
    actions_possible: str | None = None
    pricing_notes: str | None = None
    risk_notes: str | None = None
    implementation_difficulty: str | None = None
    recommended_next_step: str | None = None
    rank: int = 999
    relevance_score: int | None = None
    confidence: str | None = None
    approved: bool = False
    approved_at: str | None = None
    generated_by_run_id: str | None = None
    last_generated_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def _map_partner_candidate(row: dict[str, Any]) -> PartnerCandidate:
    def _iso(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    return PartnerCandidate(
        id=str(row.get("id", "")),
        idea_id=str(row.get("idea_id", "")),
        name=str(row.get("name", "")),
        website=row.get("website"),
        category=str(row.get("category", "")),
        why_relevant=row.get("why_relevant"),
        suggested_use=row.get("suggested_use"),
        integration_type=str(row.get("integration_type") or "unknown"),
        data_required=row.get("data_required"),
        actions_possible=row.get("actions_possible"),
        pricing_notes=row.get("pricing_notes"),
        risk_notes=row.get("risk_notes"),
        implementation_difficulty=row.get("implementation_difficulty"),
        recommended_next_step=row.get("recommended_next_step"),
        rank=int(row.get("rank") or 999),
        relevance_score=row.get("relevance_score"),
        confidence=row.get("confidence"),
        approved=bool(row.get("approved") or False),
        approved_at=_iso(row.get("approved_at")),
        generated_by_run_id=row.get("generated_by_run_id"),
        last_generated_at=_iso(row.get("last_generated_at")),
        created_at=_iso(row.get("created_at")),
        updated_at=_iso(row.get("updated_at")),
    )
