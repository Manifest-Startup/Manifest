import asyncio
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import unquote, urlparse

import strawberry
from app.auth.current_user import (
    DEMO_MODE,
    get_current_session_id_optional,
    get_current_user_id,
    get_current_user_id_optional,
)
from app.graphql.error_masking import infrastructure_error_masker
from app.graphql.open_media_types import (
    Conversation,
    Message,
    OpenMediaLink,
    OpenMediaRealtimeToken,
    UnreadCount,
    call_open_media,
    map_conversation,
    map_link,
    map_message,
)
from app.graphql.pitch_reel_types import (
    PitchReel,
    PitchReelComment,
    PitchReelCommentCreateResult,
    PitchReelLikeResult,
    PitchReelShareResult,
    map_pitch_reel,
    map_pitch_reel_comment,
)
from app.security.cookies import clear_auth_cookies, set_auth_cookies
from app.services.ai.credentials import start_thread_with_current_key
from app.services.compliance.security_audit import record_security_event
from app.services.documents.demo_documents import build_demo_documents
from app.services.ideas import generation_jobs as job_service
from app.services.ideas.versioning_policy import VERSION_KIND_MANUAL
from app.services.identity.sessions import (
    list_user_sessions,
    revoke_all_other_sessions,
    revoke_all_sessions,
    revoke_session,
)
from app.services.operations.survey_ops import survey_ops_service
from app.services.shared import cache as cache_service
from app.utils.logger import logger
from fastapi import HTTPException

_AI_CACHE_TTL_SECONDS = int(os.getenv("AI_INTERACTIVE_CACHE_TTL_SECONDS", "300"))
_ai_request_lock = threading.Lock()


def _cache_key(namespace: str, value: str) -> str:
    return f"{namespace}:{value.strip().lower()}"


def _get_ai_cache(namespace: str, value: str) -> Any:
    # Backed by Redis when REDIS_URL is set (shared across workers), else an
    # in-process TTL map — identical behaviour to before. See cache_service.
    return cache_service.cache_get(_cache_key(namespace, value))


def _set_ai_cache(namespace: str, value: str, result: Any) -> None:
    cache_service.cache_set(_cache_key(namespace, value), result, _AI_CACHE_TTL_SECONDS)


def _generate_documents_for_idea(idea_id: str, description: str):
    """Generate all documents (BMC, pitch deck, PRD, patent) for an idea using AI and save to DB."""
    from app.services.ideas.document_generation import generate_background_tasks

    generate_background_tasks(description, idea_id)


def _start_background_generation(idea_id: str, description: str | None) -> bool:
    """Start fire-and-forget document generation when a description is present."""
    if not description or not description.strip():
        return False

    start_thread_with_current_key(_generate_documents_for_idea, idea_id, description)
    return True


def _get_pitch_deck(description: str) -> str:
    from app.managers.manifest_manager import manifest_manager

    manifest_manager.set_idea(description)
    if manifest_manager.ai_layer.is_available():
        try:
            return manifest_manager.generate_pitch_deck()
        except Exception as exc:
            logger.error(f"[GraphQL] Falling back to demo pitch deck generation: {exc}")

    return build_demo_documents(description).pitch_deck


def _get_product_requirements_document(description: str) -> str:
    from app.managers.manifest_manager import manifest_manager

    manifest_manager.set_idea(description)
    if manifest_manager.ai_layer.is_available():
        try:
            return manifest_manager.generate_product_requirements_document()
        except Exception as exc:
            logger.error(f"[GraphQL] Falling back to demo PRD generation: {exc}")

    return build_demo_documents(description).product_requirements_document


def _get_provisional_patent(description: str) -> str:
    from app.managers.manifest_manager import manifest_manager

    manifest_manager.set_idea(description)
    if manifest_manager.ai_layer.is_available():
        try:
            from app.services.documents.provisional_patent import ProvisionalPatent

            patent_service = ProvisionalPatent(manifest_manager)
            return patent_service.generate()
        except Exception as exc:
            logger.error(f"[GraphQL] Falling back to demo provisional patent generation: {exc}")

    return build_demo_documents(description).provisional_patent


def _update_idea_generated_field(
    db, idea_id: str, user_id: str | None, field_name: str, value: str
) -> None:
    if not user_id:
        return

    (
        db.table("ideas")
        .update({field_name: value})
        .eq("idea_id", idea_id)
        .eq("user_id", user_id)
        .execute()
    )
    from app.services.ideas.list_metadata import refresh_idea_list_metadata

    refresh_idea_list_metadata(db, idea_id, user_id)


def _ensure_idea_identifier(db, idea_data: dict[str, object]) -> str:
    """Backfill a stable idea_id for older imported rows that were saved without one."""
    existing_idea_id = str(idea_data.get("idea_id") or "").strip()
    if existing_idea_id:
        return existing_idea_id

    generated_idea_id = str(uuid.uuid4())
    idea_data["idea_id"] = generated_idea_id

    try:
        query = db.table("ideas").update({"idea_id": generated_idea_id}).is_("idea_id", None)

        if idea_data.get("user_id") is not None:
            query = query.eq("user_id", idea_data.get("user_id"))
        if idea_data.get("created_at") is not None:
            query = query.eq("created_at", idea_data.get("created_at"))
        if idea_data.get("title") is not None:
            query = query.eq("title", idea_data.get("title"))
        if idea_data.get("description") is not None:
            query = query.eq("description", idea_data.get("description"))

        query.execute()
    except Exception as exc:  # pragma: no cover
        logger.warning(f"[ideas] Failed to backfill missing idea_id: {exc}")

    return generated_idea_id


def _display_name(record: dict | None, default: str = "User") -> str:
    if not record:
        return default

    first_name = (record.get("first_name") or "").strip()
    last_name = (record.get("last_name") or "").strip()
    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        return full_name

    username = (record.get("username") or "").strip()
    if username:
        return username

    email = (record.get("email") or "").strip()
    if email:
        return email.split("@", 1)[0]

    return default


SEARCHABLE_IDEA_FIELDS = [
    ("Description", "description", 6),
    ("Business model", "business_model_canvas", 5),
    ("Pitch deck", "pitch_deck", 4),
    ("Product requirements", "product_requirements_document", 4),
    ("Patent", "provisional_patent", 3),
    ("Research", "similar_ideas", 3),
]


def _coerce_datetime(value: object | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return datetime.utcnow()
    return datetime.utcnow()


def _normalize_search_text(value: str | None) -> str:
    if not value:
        return ""

    text = value
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"[`*_>#|]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _search_tokens(query: str) -> list[str]:
    normalized = _normalize_search_text(query).lower()
    if not normalized:
        return []

    tokens = [token for token in re.split(r"[^a-z0-9]+", normalized) if len(token) > 1]
    return list(dict.fromkeys(tokens))


def _score_search_text(text: str, exact_query: str, tokens: list[str], weight: int) -> int:
    if not text:
        return 0

    lower_text = text.lower()
    score = 0

    if exact_query and exact_query in lower_text:
        score += weight * 8

    matched_tokens = 0
    for token in tokens:
        occurrences = lower_text.count(token)
        if occurrences:
            matched_tokens += 1
            score += min(occurrences, 4) * weight * 2
            if lower_text.startswith(token):
                score += weight

    if tokens and matched_tokens == len(tokens):
        score += weight * max(len(tokens), 1)

    return score


def _build_search_snippet(text: str, tokens: list[str], max_length: int = 190) -> str:
    clean = _normalize_search_text(text)
    if not clean:
        return ""

    lower_text = clean.lower()
    first_index = len(clean)

    for token in tokens:
        token_index = lower_text.find(token)
        if token_index != -1:
            first_index = min(first_index, token_index)

    if first_index == len(clean):
        first_index = 0

    start = max(first_index - 48, 0)
    end = min(start + max_length, len(clean))
    snippet = clean[start:end].strip()

    if start > 0:
        snippet = f"...{snippet}"
    if end < len(clean):
        snippet = f"{snippet}..."

    return snippet


def _rank_idea_record(idea_data: dict[str, object], query: str) -> dict[str, object] | None:
    normalized_query = _normalize_search_text(query).lower()
    tokens = _search_tokens(query)

    if not normalized_query and not tokens:
        return None

    title = _normalize_search_text(idea_data.get("title"))
    fields = [("Title", title, 10)]
    fields.extend(
        (label, _normalize_search_text(idea_data.get(field_name)), weight)
        for label, field_name, weight in SEARCHABLE_IDEA_FIELDS
    )

    total_score = 0
    best_match_label = None
    best_match_text = title
    best_match_score = 0

    for label, text, weight in fields:
        current_score = _score_search_text(text, normalized_query, tokens, weight)
        if current_score <= 0:
            continue

        total_score += current_score
        if current_score > best_match_score:
            best_match_score = current_score
            best_match_label = label
            best_match_text = text

    if total_score <= 0:
        return None

    snippet_source = (
        best_match_text or title or _normalize_search_text(idea_data.get("description"))
    )
    snippet = (
        _build_search_snippet(snippet_source, tokens) or title or "Open this idea in the workspace."
    )

    return {
        "score": total_score,
        "snippet": snippet,
        "matched_in": best_match_label or "Workspace",
    }


def _search_idea_records(
    idea_records: list[dict[str, object]], query: str, limit: int
) -> list[dict[str, object]]:
    ranked_results: list[dict[str, object]] = []

    for idea_data in idea_records:
        ranked_match = _rank_idea_record(idea_data, query)
        if not ranked_match:
            continue

        ranked_results.append(
            {
                **idea_data,
                **ranked_match,
            }
        )

    ranked_results.sort(
        key=lambda item: (
            int(item.get("score", 0)),
            _coerce_datetime(item.get("created_at")),
        ),
        reverse=True,
    )

    return ranked_results[: max(limit, 1)]


def _fetch_user_search_profiles(db, user_ids: list[str | None]) -> dict[str, dict[str, object]]:
    unique_ids = sorted({str(user_id) for user_id in user_ids if user_id})
    if not unique_ids:
        return {}

    try:
        response = (
            db.table("users")
            .select("user_id, email, first_name, last_name, username, profile_picture_url")
            .in_("user_id", unique_ids)
            .execute()
        )
        return {
            str(profile.get("user_id")): profile
            for profile in (response.data or [])
            if profile.get("user_id")
        }
    except Exception as exc:
        logger.warning(f"[universal_search] Failed to batch load creator profiles: {exc}")
        return {}


def _build_web_source(url: str) -> dict[str, str] | None:
    if not url:
        return None

    parsed = urlparse(url)
    hostname = parsed.netloc.replace("www.", "") or url
    path_tail = unquote(parsed.path.strip("/").split("/")[-1]) if parsed.path else ""
    path_tail = re.sub(r"\.[a-z0-9]+$", "", path_tail, flags=re.IGNORECASE)
    pretty_tail = re.sub(r"[-_]+", " ", path_tail).strip()

    title = hostname
    if pretty_tail:
        title = pretty_tail[:80]

    return {
        "title": title[:100] or hostname,
        "url": url,
        "hostname": hostname,
    }


def _format_search_context_items(items: list["UniversalSearchIdeaResult"], label: str) -> str:
    if not items:
        return f"{label}: none"

    context_lines = [f"{label}:"]
    for item in items[:3]:
        context_lines.append(f"- {item.title} ({item.matched_in or 'Workspace'}): {item.snippet}")
    return "\n".join(context_lines)


def _generate_universal_search_summary(
    query: str,
    my_ideas: list["UniversalSearchIdeaResult"],
    published_ideas: list["UniversalSearchIdeaResult"],
    web_summary: str | None,
) -> str | None:
    from app.managers.manifest_manager import manifest_manager

    if not manifest_manager.ai_layer.is_available():
        return None

    prompt = [
        {
            "role": "system",
            "content": (
                "You are Manifest Search, a concise founder-workspace assistant. "
                "Synthesize the search results into 3 short sentences. "
                "Mention internal notes, public ideas, and web research only if they are present. "
                "No bullet points, no preamble."
            ),
        },
        {
            "role": "user",
            "content": (
                f'Search query: "{query}"\n\n'
                f"{_format_search_context_items(my_ideas, 'Internal notes')}\n\n"
                f"{_format_search_context_items(published_ideas, 'Published ideas')}\n\n"
                f"Web research:\n{web_summary or 'none'}"
            ),
        },
    ]

    try:
        return _normalize_search_text(manifest_manager.ai_layer.generate_text(prompt)) or None
    except Exception as exc:
        logger.warning(f"[universal_search] Failed to generate AI summary: {exc}")
        return None


# Session configuration - uses PostgreSQL for user storage
SESSION_SECRET = os.getenv("SESSION_SECRET", "")

# Canonical skills taxonomy for the Manifest platform.
AVAILABLE_SKILLS: list[str] = [
    # Engineering
    "Full Stack Development",
    "Frontend Development",
    "Backend Development",
    "Mobile Development",
    "iOS Development",
    "Android Development",
    "DevOps / Cloud",
    "Data Engineering",
    "Machine Learning / AI",
    "Cybersecurity",
    "Blockchain / Web3",
    "Embedded Systems",
    # Product & Design
    "Product Management",
    "UX / UI Design",
    "Product Strategy",
    "Quality Assurance",
    "Technical Writing",
    # Business
    "Business Development",
    "Sales",
    "Marketing",
    "Growth Hacking",
    "Operations",
    "Finance / Accounting",
    "Fundraising",
    "Legal",
    "Human Resources",
    # Creative
    "Graphic Design",
    "Brand Design",
    "Video Production",
    "Copywriting",
    "Content Marketing",
    "SEO / SEM",
    "Social Media",
    # Data & Research
    "Data Analysis",
    "Data Science",
    "Market Research",
    "User Research",
]


@strawberry.type
class User:
    user_id: str
    email: str
    created_at: datetime
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    country: str | None = None
    bio: str | None = None
    address: str | None = None
    state: str | None = None
    gravatar_hash: str | None = None
    profile_picture_url: str | None = None
    skills: list[str] = strawberry.field(default_factory=list)


@strawberry.type
class Idea:
    idea_id: str
    user_id: str
    title: str
    description: str | None
    created_at: datetime
    pitch_deck: str | None = None
    product_requirements_document: str | None = None
    provisional_patent: str | None = None
    business_model_canvas: str | None = None
    similar_ideas: str | None = None
    is_published: bool = False
    required_skills: list[str] = strawberry.field(default_factory=list)


@strawberry.type
class IdeaSummary:
    """Lightweight row for workspace idea lists — avoids serializing large generated documents."""

    idea_id: str
    user_id: str
    title: str
    description: str | None
    has_description: bool = False
    created_at: datetime
    is_published: bool = False
    generated_asset_count: int = 0


IDEA_SUMMARY_DB_COLUMNS = (
    "idea_id, user_id, title, created_at, is_published, " "generated_asset_count, has_description"
)

IDEA_DETAIL_DB_COLUMNS = (
    "idea_id, user_id, title, description, created_at, pitch_deck, "
    "product_requirements_document, provisional_patent, business_model_canvas, "
    "similar_ideas, is_published"
)


def _idea_detail_columns(info: strawberry.Info) -> str:
    """Read large text columns only when the operation selects them.

    Strawberry expands named and inline fragments in selected_fields. SQL
    identifiers come exclusively from this allowlist, never from query text.
    """
    columns = ["idea_id", "user_id", "title", "created_at", "is_published"]
    optional = {
        "description": "description",
        "pitchDeck": "pitch_deck",
        "productRequirementsDocument": "product_requirements_document",
        "provisionalPatent": "provisional_patent",
        "businessModelCanvas": "business_model_canvas",
        "similarIdeas": "similar_ideas",
    }

    def collect(selections):
        for selection in selections:
            column = optional.get(getattr(selection, "name", ""))
            if column and column not in columns:
                columns.append(column)
            collect(getattr(selection, "selections", []))

    collect(info.selected_fields)
    return ", ".join(columns)


@strawberry.type
class PitchDeckOutput:
    pitch_deck: str


@strawberry.type
class ProductRequirementsDocumentOutput:
    product_requirements_document: str


@strawberry.type
class ProvisionalPatentOutput:
    provisional_patent: str
    coversheet_pdf: str | None = None
    specification_pdf: str | None = None


@strawberry.type
class GenerationJob:
    """Status of an async document-generation job (Phase 3 queue)."""

    id: str
    status: str
    document_types: list[str]
    idea_id: str | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@strawberry.type
class EnqueueJobResult:
    job_id: str
    status: str


def _to_generation_job(job: dict[str, Any]) -> GenerationJob:
    return GenerationJob(
        id=str(job.get("id") or ""),
        status=str(job.get("status") or ""),
        document_types=list(job.get("document_types") or []),
        idea_id=job.get("idea_id"),
        error_message=job.get("error_message"),
        created_at=job.get("created_at"),
        updated_at=job.get("updated_at"),
    )


@strawberry.type
class ContactForm:
    first_name: str
    last_name: str
    email: str
    message: str


@strawberry.type
class Investment:
    investment_id: str
    idea_id: str
    investor_id: str
    cash_amount: float
    sweat_equity_hours: float
    sweat_equity_value: float
    equity_percentage: float
    investment_type: str
    role: str | None = None
    status: str = "pending"
    notes: str | None = None
    created_at: datetime
    investor_name: str | None = None
    investor_avatar: str | None = None


@strawberry.type
class CapTableEntry:
    entry_id: str
    idea_id: str
    stakeholder_id: str
    stakeholder_type: str
    equity_percentage: float
    shares_owned: float
    share_class: str
    vesting_status: str
    vested_percentage: float
    stakeholder_name: str | None = None
    stakeholder_avatar: str | None = None


@strawberry.type
class PortfolioItem:
    investment_id: str
    idea_id: str
    idea_title: str
    idea_description: str | None = None
    cash_amount: float
    sweat_equity_value: float
    equity_percentage: float
    status: str
    created_at: datetime


@strawberry.type
class UserFollow:
    follow_id: str
    follower_id: str
    followed_id: str
    created_at: datetime
    user_name: str | None = None
    user_avatar: str | None = None


@strawberry.type
class FollowResult:
    following: bool
    followed_id: str


@strawberry.type
class VoteResult:
    voted: bool
    idea_id: str
    vote_count: int


@strawberry.type
class PublishResult:
    idea_id: str
    is_published: bool


@strawberry.type
class UniversalSearchIdeaResult:
    idea_id: str
    title: str
    snippet: str
    matched_in: str | None = None
    created_at: datetime
    user_id: str
    is_published: bool = False
    creator_name: str | None = None
    creator_avatar: str | None = None


@strawberry.type
class UniversalSearchWebSource:
    title: str
    url: str
    hostname: str | None = None


@strawberry.type
class UniversalSearchResults:
    query: str
    my_ideas: list[UniversalSearchIdeaResult]
    published_ideas: list[UniversalSearchIdeaResult]
    assistant_summary: str | None = None
    web_summary: str | None = None
    web_sources: list[UniversalSearchWebSource]


@strawberry.type
class SweatEquityCalculation:
    sweat_value: float
    equity_percentage: float
    hours: float
    hourly_rate: float


@strawberry.type
class SocialStats:
    follower_count: int
    following_count: int
    is_following: bool = False


@strawberry.type
class SurveyDistributionItem:
    label: str
    count: int
    percentage: float | None = None


@strawberry.type
class SurveyThemeSummary:
    theme: str
    count: int


@strawberry.type
class SurveyInsights:
    generated_at: str
    window_days: int
    total_responses: int
    research_responses: int
    product_feedback_responses: int
    research_signup_intent_avg: float | None = None
    research_follow_up_rate: float | None = None
    product_pmf_very_disappointed_pct: float | None = None
    product_nps_score: int | None = None
    product_progress_avg: float | None = None
    product_deliverable_avg: float | None = None
    product_satisfaction_avg: float | None = None
    product_ease_avg: float | None = None
    product_satisfaction_topbox_pct: float | None = None
    product_ai_quality_avg: float | None = None
    top_research_roles: list[SurveyDistributionItem]
    top_research_value_props: list[SurveyDistributionItem]
    top_research_barriers: list[SurveyDistributionItem]
    top_research_first_outputs: list[SurveyDistributionItem]
    top_research_trust_signals: list[SurveyDistributionItem]
    top_product_benefits: list[SurveyDistributionItem]
    top_product_tasks: list[SurveyDistributionItem]
    top_action_themes: list[SurveyThemeSummary]


@strawberry.input
class CreateInvestmentInput:
    idea_id: str
    cash_amount: float = 0
    sweat_equity_hours: float = 0
    hourly_rate: float = 50
    equity_percentage: float = 0
    investment_type: str = "cash"
    role: str | None = None
    notes: str | None = None


@strawberry.input
class AddContributionInput:
    investment_id: str
    contribution_type: str
    amount: float = 0
    hours_worked: float = 0
    hourly_rate: float = 50
    description: str | None = None


@strawberry.input
class ContactFormInput:
    first_name: str
    last_name: str
    email: str
    message: str


@strawberry.input
class SubmitSurveyInput:
    """In-app survey payload; answers_json is a JSON object of question keys to values."""

    survey_type: str
    answers_json: str
    contact_email: str | None = None


@strawberry.input
class AccountUpdateInput:
    email: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    country: str | None = None
    bio: str | None = None
    address: str | None = None
    state: str | None = None
    gravatar_hash: str | None = None
    profile_picture_url: str | None = None
    skills: list[str] | None = None


@strawberry.type
class SimilarIdeas:
    similar_ideas: str


@strawberry.type
class AuthUser:
    user_id: str
    email: str
    token: str
    is_guest: bool = False


@strawberry.type
class SessionInfo:
    session_id: str
    current: bool
    created_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_seen_at: datetime | None = None
    request_ip: str | None = None
    user_agent: str | None = None


@strawberry.type
class PrivacyStatus:
    export_available: bool
    deletion_requested_at: datetime | None = None
    guest_retention_days: int = 30


@strawberry.type
class GuestSessionResult:
    """Returned only from start_guest_session; includes one-time merge secret."""

    user_id: str
    email: str
    token: str
    merge_secret: str


@strawberry.type
class Patent:
    patent_id: str
    title: str
    description: str | None
    created_at: datetime


@strawberry.type
class ExportResult:
    content: str
    format: str
    filename: str


@strawberry.type
class Integration:
    integration_id: str
    user_id: str
    service_name: str
    service_id: str
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: datetime | None = None
    connected_at: datetime
    metadata: str | None = None  # JSON string for additional service-specific data


@strawberry.type
class AiKeyStatus:
    """Bring-your-own-key status. ``source``: "user", "platform" or "none"."""

    configured: bool
    source: str
    last4: str | None = None


def _visible_integrations(rows: list[dict]) -> list[dict]:
    """Integrations shown in the UI; the BYOK OpenAI key is exposed only via aiKeyStatus."""
    return [row for row in rows if row.get("service_id") != "openai"]


def _ai_key_status(user_id: str) -> AiKeyStatus:
    from app.services.ai.credentials import platform_key
    from app.services.ai.user_keys import key_last4

    last4 = key_last4(user_id)
    if last4:
        return AiKeyStatus(configured=True, source="user", last4=last4)
    if platform_key():
        return AiKeyStatus(configured=True, source="platform")
    return AiKeyStatus(configured=False, source="none")


@strawberry.input
class ConnectIntegrationInput:
    service_id: str
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: datetime | None = None
    metadata: str | None = None


@strawberry.type
class ImportResult:
    imported_count: int
    skipped_count: int
    errors: list[str]


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    logger.warning("DATABASE_URL is not set. Database operations may fail.")


def _require_full_account(db, request) -> str:
    """Raise if the current user is a try-before-signup guest (blocked for social/invest/publish)."""
    from app.services.identity.guest_workspace import fetch_user_is_guest

    user_id = get_current_user_id(request)
    if fetch_user_is_guest(db, user_id):
        raise Exception("Create an account to use this feature.")
    return user_id


def _request_ip(info: strawberry.Info) -> str | None:
    request = info.context.get("request")
    client = getattr(request, "client", None) if request else None
    return getattr(client, "host", None) if client else None


def _user_agent(info: strawberry.Info) -> str | None:
    """Best-effort User-Agent extraction for the canonical audit row."""
    request = info.context.get("request")
    if not request:
        return None
    headers = getattr(request, "headers", None)
    if not headers:
        return None
    try:
        ua = headers.get("user-agent")
    except Exception:
        return None
    return (ua or "")[:500] or None


def _set_browser_auth_session(info: strawberry.Info, token: str) -> None:
    response = info.context.get("response")
    request = info.context.get("request")
    if not response:
        return
    try:
        set_auth_cookies(response, token, request)
    except Exception as cookie_error:
        logger.warning("[auth_session] Failed to set auth cookies: %s", cookie_error)


def _load_user_auth_record(user_id: str) -> dict[str, object] | None:
    if not user_id:
        return None
    from app.db.database import get_db_connection

    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
                SELECT user_id, email, auth_provider,
                       COALESCE(is_guest, FALSE) AS is_guest,
                       deletion_requested_at
                FROM users
                WHERE user_id = %s
                """,
            (user_id,),
        )
        return cur.fetchone()


def _build_survey_distribution_items(items: list[dict[str, Any]]) -> list[SurveyDistributionItem]:
    distribution_items: list[SurveyDistributionItem] = []
    for item in items or []:
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        distribution_items.append(
            SurveyDistributionItem(
                label=label,
                count=int(item.get("count") or 0),
                percentage=(
                    float(item["percentage"]) if item.get("percentage") is not None else None
                ),
            )
        )
    return distribution_items


def _build_survey_theme_summaries(items: list[dict[str, Any]]) -> list[SurveyThemeSummary]:
    theme_items: list[SurveyThemeSummary] = []
    for item in items or []:
        theme = str(item.get("theme") or "").strip()
        if not theme:
            continue
        theme_items.append(
            SurveyThemeSummary(
                theme=theme,
                count=int(item.get("count") or 0),
            )
        )
    return theme_items


def _build_survey_insights(summary: dict[str, Any]) -> SurveyInsights:
    return SurveyInsights(
        generated_at=str(summary.get("generated_at") or datetime.utcnow().isoformat()),
        window_days=int(summary.get("window_days") or 90),
        total_responses=int(summary.get("total_responses") or 0),
        research_responses=int(summary.get("research_responses") or 0),
        product_feedback_responses=int(summary.get("product_feedback_responses") or 0),
        research_signup_intent_avg=(
            float(summary["research_signup_intent_avg"])
            if summary.get("research_signup_intent_avg") is not None
            else None
        ),
        research_follow_up_rate=(
            float(summary["research_follow_up_rate"])
            if summary.get("research_follow_up_rate") is not None
            else None
        ),
        product_pmf_very_disappointed_pct=(
            float(summary["product_pmf_very_disappointed_pct"])
            if summary.get("product_pmf_very_disappointed_pct") is not None
            else None
        ),
        product_nps_score=(
            int(summary["product_nps_score"])
            if summary.get("product_nps_score") is not None
            else None
        ),
        product_progress_avg=(
            float(summary["product_progress_avg"])
            if summary.get("product_progress_avg") is not None
            else None
        ),
        product_deliverable_avg=(
            float(summary["product_deliverable_avg"])
            if summary.get("product_deliverable_avg") is not None
            else None
        ),
        product_satisfaction_avg=(
            float(summary["product_satisfaction_avg"])
            if summary.get("product_satisfaction_avg") is not None
            else None
        ),
        product_ease_avg=(
            float(summary["product_ease_avg"])
            if summary.get("product_ease_avg") is not None
            else None
        ),
        product_satisfaction_topbox_pct=(
            float(summary["product_satisfaction_topbox_pct"])
            if summary.get("product_satisfaction_topbox_pct") is not None
            else None
        ),
        product_ai_quality_avg=(
            float(summary["product_ai_quality_avg"])
            if summary.get("product_ai_quality_avg") is not None
            else None
        ),
        top_research_roles=_build_survey_distribution_items(
            summary.get("top_research_roles") or []
        ),
        top_research_value_props=_build_survey_distribution_items(
            summary.get("top_research_value_props") or []
        ),
        top_research_barriers=_build_survey_distribution_items(
            summary.get("top_research_barriers") or []
        ),
        top_research_first_outputs=_build_survey_distribution_items(
            summary.get("top_research_first_outputs") or []
        ),
        top_research_trust_signals=_build_survey_distribution_items(
            summary.get("top_research_trust_signals") or []
        ),
        top_product_benefits=_build_survey_distribution_items(
            summary.get("top_product_benefits") or []
        ),
        top_product_tasks=_build_survey_distribution_items(summary.get("top_product_tasks") or []),
        top_action_themes=_build_survey_theme_summaries(summary.get("top_action_themes") or []),
    )


@strawberry.type
class AdminDailyCostPoint:
    date: str
    billable_usd: float
    model_cost_usd: float
    event_count: int


@strawberry.type
class AdminUserSpend:
    user_id: str
    email: str | None = None
    billable_usd: float = 0.0
    event_count: int = 0


@strawberry.type
class AdminExpensiveRun:
    id: str
    user_id: str
    user_email: str | None = None
    agent_kind: str
    status: str
    billable_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    started_at: str
    completed_at: str | None = None


@strawberry.type
class AdminCostTotals:
    total_billable_usd: float = 0.0
    total_model_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_runs: int = 0
    failed_runs: int = 0
    active_users: int = 0


@strawberry.type
class AdminLabelSpend:
    """Same shape as CostByLabel but distinct type so admin types
    don't depend on a forward reference to per-user dashboard types."""

    label: str
    billable_usd: float


@strawberry.type
class AdminCostOverview:
    window_days: int
    window_start: str
    generated_at: str
    totals: AdminCostTotals
    burn_rate_per_day_usd: float = 0.0
    month_to_date_billable_usd: float = 0.0
    projected_month_billable_usd: float = 0.0
    daily_series: list[AdminDailyCostPoint]
    top_users: list[AdminUserSpend]
    by_agent_kind: list[AdminLabelSpend]
    by_model: list[AdminLabelSpend]
    expensive_runs: list[AdminExpensiveRun]


@strawberry.type
class AdminAgentRunRow:
    id: str
    user_id: str
    user_email: str | None = None
    agent_kind: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    total_billable_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    error_message: str | None = None
    idea_id: str | None = None
    qualification_session_id: str | None = None


@strawberry.type
class AdminTopFailingTest:
    test_name: str
    failures: int


@strawberry.type
class AdminProductionTestStats:
    window_hours: int
    total_runs: int = 0
    pass_count: int = 0
    fail_count: int = 0
    flaky_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    failure_rate: float = 0.0
    issues_opened: int = 0
    issues_deduped: int = 0
    top_failing_tests: list[AdminTopFailingTest]


def _map_admin_overview(payload: dict[str, Any]) -> AdminCostOverview:
    totals = payload.get("totals") or {}
    return AdminCostOverview(
        window_days=int(payload.get("window_days") or 0),
        window_start=str(payload.get("window_start") or ""),
        generated_at=str(payload.get("generated_at") or ""),
        totals=AdminCostTotals(
            total_billable_usd=float(totals.get("total_billable_usd") or 0),
            total_model_cost_usd=float(totals.get("total_model_cost_usd") or 0),
            total_input_tokens=int(totals.get("total_input_tokens") or 0),
            total_output_tokens=int(totals.get("total_output_tokens") or 0),
            total_runs=int(totals.get("total_runs") or 0),
            failed_runs=int(totals.get("failed_runs") or 0),
            active_users=int(totals.get("active_users") or 0),
        ),
        burn_rate_per_day_usd=float(payload.get("burn_rate_per_day_usd") or 0),
        month_to_date_billable_usd=float(payload.get("month_to_date_billable_usd") or 0),
        projected_month_billable_usd=float(payload.get("projected_month_billable_usd") or 0),
        daily_series=[
            AdminDailyCostPoint(
                date=str(p.get("date") or ""),
                billable_usd=float(p.get("billable_usd") or 0),
                model_cost_usd=float(p.get("model_cost_usd") or 0),
                event_count=int(p.get("event_count") or 0),
            )
            for p in (payload.get("daily_series") or [])
        ],
        top_users=[
            AdminUserSpend(
                user_id=str(u.get("user_id") or ""),
                email=u.get("email"),
                billable_usd=float(u.get("billable_usd") or 0),
                event_count=int(u.get("event_count") or 0),
            )
            for u in (payload.get("top_users") or [])
        ],
        by_agent_kind=[
            AdminLabelSpend(
                label=str(i.get("label") or ""), billable_usd=float(i.get("billable_usd") or 0)
            )
            for i in (payload.get("by_agent_kind") or [])
        ],
        by_model=[
            AdminLabelSpend(
                label=str(i.get("label") or ""), billable_usd=float(i.get("billable_usd") or 0)
            )
            for i in (payload.get("by_model") or [])
        ],
        expensive_runs=[
            AdminExpensiveRun(
                id=str(r.get("id") or ""),
                user_id=str(r.get("user_id") or ""),
                user_email=r.get("user_email"),
                agent_kind=str(r.get("agent_kind") or ""),
                status=str(r.get("status") or ""),
                billable_usd=float(r.get("billable_usd") or 0),
                input_tokens=int(r.get("input_tokens") or 0),
                output_tokens=int(r.get("output_tokens") or 0),
                started_at=str(r.get("started_at") or ""),
                completed_at=r.get("completed_at"),
            )
            for r in (payload.get("expensive_runs") or [])
        ],
    )


def _map_admin_agent_run(row: dict[str, Any]) -> AdminAgentRunRow:
    def _iso(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    return AdminAgentRunRow(
        id=str(row.get("id") or ""),
        user_id=str(row.get("user_id") or ""),
        user_email=row.get("user_email"),
        agent_kind=str(row.get("agent_kind") or ""),
        status=str(row.get("status") or ""),
        started_at=_iso(row.get("started_at")),
        completed_at=_iso(row.get("completed_at")),
        total_billable_cost_usd=float(row.get("total_billable_cost_usd") or 0),
        total_input_tokens=int(row.get("total_input_tokens") or 0),
        total_output_tokens=int(row.get("total_output_tokens") or 0),
        error_message=row.get("error_message"),
        idea_id=row.get("idea_id"),
        qualification_session_id=row.get("qualification_session_id"),
    )


def _map_admin_test_stats(payload: dict[str, Any]) -> AdminProductionTestStats:
    counts = payload.get("counts_by_status") or {}
    return AdminProductionTestStats(
        window_hours=int(payload.get("window_hours") or 0),
        total_runs=int(payload.get("total_runs") or 0),
        pass_count=int(counts.get("pass") or 0),
        fail_count=int(counts.get("fail") or 0),
        flaky_count=int(counts.get("flaky") or 0),
        error_count=int(counts.get("error") or 0),
        skipped_count=int(counts.get("skipped") or 0),
        failure_rate=float(payload.get("failure_rate") or 0),
        issues_opened=int(payload.get("issues_opened") or 0),
        issues_deduped=int(payload.get("issues_deduped") or 0),
        top_failing_tests=[
            AdminTopFailingTest(
                test_name=str(t.get("test_name") or ""),
                failures=int(t.get("failures") or 0),
            )
            for t in (payload.get("top_failing_tests") or [])
        ],
    )


# ==================== VOICE TESTING ====================


@strawberry.type
class VoiceTestRun:
    id: str
    scenario: str
    user_persona: str
    user_emotion: str
    user_goal: str | None = None
    user_input: str
    expected_behavior: str | None = None
    assistant_response: str | None = None
    executor_kind: str = "stub"
    score_intent_understanding: int | None = None
    score_emotional_awareness: int | None = None
    score_helpfulness: int | None = None
    overall_score: float | None = None
    pass_status: bool | None = None
    detected_failures: list[str]
    root_cause_analysis: str | None = None
    improved_response_example: str | None = None
    simulator_run_id: str | None = None
    executor_run_id: str | None = None
    evaluator_run_id: str | None = None
    created_at: str | None = None


@strawberry.type
class VoiceTestSlice:
    """Per-scenario or per-emotion slice of the rolling stats."""

    label: str
    total: int
    pass_count: int
    fail_count: int


@strawberry.type
class VoiceTestFailureCount:
    failure: str
    count: int


@strawberry.type
class VoiceTestAverageScores:
    intent_understanding: float
    emotional_awareness: float
    helpfulness: float


@strawberry.type
class VoiceTestStats:
    window_hours: int
    total_runs: int
    passed: int
    failed: int
    not_evaluated: int
    pass_rate: float
    average_scores: VoiceTestAverageScores
    by_scenario: list[VoiceTestSlice]
    by_emotion: list[VoiceTestSlice]
    top_failures: list[VoiceTestFailureCount]


def _map_voice_test_run(row: dict[str, Any]) -> VoiceTestRun:
    def _iso(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    failures_raw = row.get("detected_failures") or []
    if isinstance(failures_raw, str):
        try:
            failures_raw = json.loads(failures_raw)
        except (TypeError, ValueError):
            failures_raw = []
    overall = row.get("overall_score")
    return VoiceTestRun(
        id=str(row.get("id", "")),
        scenario=str(row.get("scenario", "")),
        user_persona=str(row.get("user_persona", "")),
        user_emotion=str(row.get("user_emotion", "")),
        user_goal=row.get("user_goal"),
        user_input=str(row.get("user_input", "")),
        expected_behavior=row.get("expected_behavior"),
        assistant_response=row.get("assistant_response"),
        executor_kind=str(row.get("executor_kind") or "stub"),
        score_intent_understanding=row.get("score_intent_understanding"),
        score_emotional_awareness=row.get("score_emotional_awareness"),
        score_helpfulness=row.get("score_helpfulness"),
        overall_score=float(overall) if overall is not None else None,
        pass_status=row.get("pass_status"),
        detected_failures=[str(f) for f in (failures_raw or [])],
        root_cause_analysis=row.get("root_cause_analysis"),
        improved_response_example=row.get("improved_response_example"),
        simulator_run_id=row.get("simulator_run_id"),
        executor_run_id=row.get("executor_run_id"),
        evaluator_run_id=row.get("evaluator_run_id"),
        created_at=_iso(row.get("created_at")),
    )


def _map_voice_test_stats(payload: dict[str, Any]) -> VoiceTestStats:
    avg = payload.get("average_scores") or {}
    return VoiceTestStats(
        window_hours=int(payload.get("window_hours") or 0),
        total_runs=int(payload.get("total_runs") or 0),
        passed=int(payload.get("passed") or 0),
        failed=int(payload.get("failed") or 0),
        not_evaluated=int(payload.get("not_evaluated") or 0),
        pass_rate=float(payload.get("pass_rate") or 0),
        average_scores=VoiceTestAverageScores(
            intent_understanding=float(avg.get("intent_understanding") or 0),
            emotional_awareness=float(avg.get("emotional_awareness") or 0),
            helpfulness=float(avg.get("helpfulness") or 0),
        ),
        by_scenario=[
            VoiceTestSlice(
                label=str(s.get("scenario") or ""),
                total=int(s.get("total") or 0),
                pass_count=int(s.get("pass") or 0),
                fail_count=int(s.get("fail") or 0),
            )
            for s in (payload.get("by_scenario") or [])
        ],
        by_emotion=[
            VoiceTestSlice(
                label=str(s.get("emotion") or ""),
                total=int(s.get("total") or 0),
                pass_count=int(s.get("pass") or 0),
                fail_count=int(s.get("fail") or 0),
            )
            for s in (payload.get("by_emotion") or [])
        ],
        top_failures=[
            VoiceTestFailureCount(
                failure=str(f.get("failure") or ""),
                count=int(f.get("count") or 0),
            )
            for f in (payload.get("top_failures") or [])
        ],
    )


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


@strawberry.type
class AgentRunSummary:
    id: str
    agent_kind: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    total_model_cost_usd: float = 0.0
    total_billable_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    error_message: str | None = None
    qualification_session_id: str | None = None
    idea_id: str | None = None


@strawberry.type
class CostByLabel:
    label: str
    billable_usd: float


@strawberry.type
class MonthlySpend:
    month_start: str
    total_billable_usd: float
    total_model_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    event_count: int
    by_agent_kind: list[CostByLabel]
    by_model: list[CostByLabel]


@strawberry.type
class UserCostLimits:
    monthly_variable_cap_usd: float
    paused: bool
    base_subscription_usd: float
    currency: str = "USD"


@strawberry.type
class CostPreflight:
    """Read-only preflight: would a new agent run be allowed right now?

    The frontend calls this to know whether to disable an agent
    button before the user clicks it; the resolver layer ALSO enforces
    on every agent mutation, so this is purely a UX preview.
    """

    allowed: bool
    reason: str | None = None  # 'paused' | 'over_cap' | 'would_exceed_cap' | null
    monthly_usage_usd: float
    cap_usd: float
    remaining_usd: float
    estimated_cost_usd: float
    paused: bool
    agent_kind: str | None = None


@strawberry.type
class UserCostDashboard:
    limits: UserCostLimits
    spend: MonthlySpend
    remaining_usd: float
    pct_of_cap: float
    warn_level: str  # ok | elevated | critical | over
    recent_runs: list[AgentRunSummary]
    estimated_total_with_subscription_usd: float


def _map_agent_run(row: dict[str, Any]) -> AgentRunSummary:
    def _iso(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    return AgentRunSummary(
        id=str(row.get("id", "")),
        agent_kind=str(row.get("agent_kind", "")),
        status=str(row.get("status", "")),
        started_at=_iso(row.get("started_at")),
        completed_at=_iso(row.get("completed_at")),
        total_model_cost_usd=float(row.get("total_model_cost_usd") or 0),
        total_billable_cost_usd=float(row.get("total_billable_cost_usd") or 0),
        total_input_tokens=int(row.get("total_input_tokens") or 0),
        total_output_tokens=int(row.get("total_output_tokens") or 0),
        error_message=row.get("error_message"),
        qualification_session_id=row.get("qualification_session_id"),
        idea_id=row.get("idea_id"),
    )


def _map_cost_dashboard(payload: dict[str, Any]) -> UserCostDashboard:
    limits = payload.get("limits") or {}
    spend = payload.get("spend") or {}
    return UserCostDashboard(
        limits=UserCostLimits(
            monthly_variable_cap_usd=float(limits.get("monthly_variable_cap_usd") or 0),
            paused=bool(limits.get("paused") or False),
            base_subscription_usd=float(limits.get("base_subscription_usd") or 0),
            currency=str(limits.get("currency") or "USD"),
        ),
        spend=MonthlySpend(
            month_start=str(spend.get("month_start") or ""),
            total_billable_usd=float(spend.get("total_billable_usd") or 0),
            total_model_cost_usd=float(spend.get("total_model_cost_usd") or 0),
            total_input_tokens=int(spend.get("total_input_tokens") or 0),
            total_output_tokens=int(spend.get("total_output_tokens") or 0),
            event_count=int(spend.get("event_count") or 0),
            by_agent_kind=[
                CostByLabel(label=k, billable_usd=float(v))
                for k, v in (spend.get("by_agent_kind") or {}).items()
            ],
            by_model=[
                CostByLabel(label=k, billable_usd=float(v))
                for k, v in (spend.get("by_model") or {}).items()
            ],
        ),
        remaining_usd=float(payload.get("remaining_usd") or 0),
        pct_of_cap=float(payload.get("pct_of_cap") or 0),
        warn_level=str(payload.get("warn_level") or "ok"),
        recent_runs=[_map_agent_run(r) for r in (payload.get("recent_runs") or [])],
        estimated_total_with_subscription_usd=float(
            payload.get("estimated_total_with_subscription_usd") or 0
        ),
    )


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


@strawberry.type
class Query:
    @strawberry.field
    async def me(self, info: strawberry.Info) -> User:
        user_id = get_current_user_id(info.context["request"])

        # Sync DB call moved off the event loop (Phase 2): this resolver runs
        # on every page load, and a blocking .execute() here stalls every
        # in-flight request on the worker for the query's duration.
        def _load() -> User:
            response = (
                info.context["db"]
                .table("users")
                .select("*")
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            if not response.data:
                raise Exception("User not found")
            user_data = response.data
            user_fields = {field.name for field in User.__dataclass_fields__.values()}
            filtered_user_data = {k: v for k, v in user_data.items() if k in user_fields}
            return User(**filtered_user_data)

        return await asyncio.to_thread(_load)

    @strawberry.field
    async def generation_job(self, info: strawberry.Info, job_id: str) -> GenerationJob | None:
        """Poll the status of an async document-generation job (Phase 3).

        Only the job's owner can read it; returns null for a missing or
        not-owned job.
        """
        user_id = get_current_user_id(info.context["request"])
        job = job_service.get_job(info.context["db"], job_id)
        if not job:
            return None
        owner = job.get("user_id")
        if owner and owner != user_id:
            return None
        return _to_generation_job(job)

    @strawberry.field
    async def ideas(
        self,
        info: strawberry.Info,
        first: int = 100,
        after: str | None = None,
    ) -> list[IdeaSummary]:
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.list_metadata import (
            IDEA_SUMMARY_DB_COLUMNS as summary_columns,
        )
        from app.services.ideas.list_metadata import (
            decode_ideas_cursor,
            normalize_ideas_page_size,
            read_list_metadata,
        )

        page_size = normalize_ideas_page_size(first)
        db = info.context["db"]

        # Sync DB work (list query + per-row legacy id backfill) runs in a
        # worker thread so the sidebar list never blocks the event loop.
        def _load() -> list[IdeaSummary]:
            query = (
                db.table("ideas")
                .select(summary_columns)
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(page_size)
            )
            if after:
                try:
                    cursor_at, _cursor_id = decode_ideas_cursor(after)
                except ValueError as exc:
                    raise Exception("Invalid pagination cursor") from exc
                query = (
                    db.table("ideas")
                    .select(summary_columns)
                    .eq("user_id", user_id)
                    .lt("created_at", cursor_at.isoformat())
                    .order("created_at", desc=True)
                    .limit(page_size)
                )

            response = query.execute()
            if not response.data:
                return []

            mapped_ideas: list[IdeaSummary] = []
            for idea_data in response.data:
                idea_id = _ensure_idea_identifier(db, idea_data)
                gac, has_desc = read_list_metadata(idea_data)
                raw_ca = idea_data.get("created_at")
                created_at = (
                    _coerce_datetime(raw_ca) if raw_ca is not None else datetime.now(timezone.utc)
                )
                mapped_ideas.append(
                    IdeaSummary(
                        idea_id=idea_id,
                        user_id=str(idea_data.get("user_id") or ""),
                        title=idea_data.get("title", "") or "",
                        description=None,
                        has_description=has_desc,
                        created_at=created_at,
                        is_published=bool(idea_data.get("is_published", False)),
                        generated_asset_count=gac,
                    )
                )
            return mapped_ideas

        return await asyncio.to_thread(_load)

    @strawberry.field
    async def idea(self, info: strawberry.Info, idea_id: str) -> Idea:
        user_id = get_current_user_id(info.context["request"])

        # A note-only request must not fetch every generated document blob.
        columns = _idea_detail_columns(info)

        def _load() -> Any:
            return (
                info.context["db"]
                .table("ideas")
                .select(columns)
                .eq("idea_id", idea_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

        response = await asyncio.to_thread(_load)
        if not response.data:
            raise Exception("Idea not found")
        idea_data = response.data
        mapped_data = {
            "idea_id": idea_data.get("idea_id"),
            "user_id": idea_data.get("user_id"),
            "title": idea_data.get("title", ""),
            "description": idea_data.get("description"),
            "created_at": idea_data.get("created_at"),
            "pitch_deck": idea_data.get("pitch_deck"),
            "product_requirements_document": idea_data.get("product_requirements_document"),
            "provisional_patent": idea_data.get("provisional_patent"),
            "business_model_canvas": idea_data.get("business_model_canvas"),
            "is_published": idea_data.get("is_published", False),
            "similar_ideas": idea_data.get("similar_ideas"),
        }
        return Idea(**mapped_data)

    @strawberry.field
    async def account(self, info: strawberry.Info) -> User:
        user_id = get_current_user_id(info.context["request"])

        # Off-loop for the same reason as `me` (fetched eagerly at app boot).
        def _load() -> User:
            response = (
                info.context["db"]
                .table("users")
                .select("*")
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            if not response.data:
                raise Exception("User not found")
            user_data = response.data
            user_fields = {field.name for field in User.__dataclass_fields__.values()}
            filtered_user_data = {k: v for k, v in user_data.items() if k in user_fields}
            return User(**filtered_user_data)

        return await asyncio.to_thread(_load)

    @strawberry.field
    async def my_sessions(self, info: strawberry.Info) -> list[SessionInfo]:
        user_id = get_current_user_id(info.context["request"])
        current_session_id = get_current_session_id_optional(info.context["request"])
        sessions = list_user_sessions(user_id, current_session_id)
        return [
            SessionInfo(
                session_id=str(item.get("session_id") or ""),
                current=bool(item.get("current")),
                created_at=item.get("created_at"),
                expires_at=item.get("expires_at"),
                revoked_at=item.get("revoked_at"),
                last_seen_at=item.get("last_seen_at"),
                request_ip=item.get("request_ip"),
                user_agent=item.get("user_agent"),
            )
            for item in sessions
        ]

    @strawberry.field
    async def privacy_status(self, info: strawberry.Info) -> PrivacyStatus:
        user_id = get_current_user_id(info.context["request"])
        user_row = _load_user_auth_record(user_id) or {}
        return PrivacyStatus(
            export_available=True,
            deletion_requested_at=user_row.get("deletion_requested_at"),
            guest_retention_days=30,
        )

    @strawberry.field
    async def survey_insights(self, info: strawberry.Info, window_days: int = 90) -> SurveyInsights:
        get_current_user_id(info.context["request"])
        summary = survey_ops_service.get_summary(info.context["db"], window_days=window_days)
        return _build_survey_insights(summary)

    @strawberry.field
    async def ai_key_status(self, info: strawberry.Info) -> AiKeyStatus:
        user_id = get_current_user_id(info.context["request"])
        return await asyncio.to_thread(_ai_key_status, str(user_id))

    @strawberry.field
    async def integrations(self, info: strawberry.Info) -> list[Integration]:
        user_id = get_current_user_id(info.context["request"])
        response = (
            info.context["db"].table("integrations").select("*").eq("user_id", user_id).execute()
        )
        if not response.data:
            return []
        integrations = []
        for integration_data in _visible_integrations(response.data):
            integration_fields = {field.name for field in Integration.__dataclass_fields__.values()}
            filtered_data = {k: v for k, v in integration_data.items() if k in integration_fields}
            # Don't expose sensitive tokens in the response
            if "access_token" in filtered_data:
                filtered_data["access_token"] = "***" if filtered_data["access_token"] else None
            if "refresh_token" in filtered_data:
                filtered_data["refresh_token"] = "***" if filtered_data["refresh_token"] else None
            # Convert connected_at from string to datetime if needed
            if "connected_at" in filtered_data:
                val = filtered_data["connected_at"]
                if isinstance(val, str):
                    try:
                        filtered_data["connected_at"] = datetime.fromisoformat(
                            val.replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[integrations] Failed to parse connected_at '{val}': {e}")
                        filtered_data["connected_at"] = datetime.utcnow()
                elif val is None:
                    filtered_data["connected_at"] = datetime.utcnow()
            else:
                filtered_data["connected_at"] = datetime.utcnow()
            # Also handle expires_at if it's a string
            if "expires_at" in filtered_data and filtered_data["expires_at"] is not None:
                val = filtered_data["expires_at"]
                if isinstance(val, str):
                    try:
                        filtered_data["expires_at"] = datetime.fromisoformat(
                            val.replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        filtered_data["expires_at"] = None
            integrations.append(Integration(**filtered_data))
        return integrations

    @strawberry.field
    async def integration(self, info: strawberry.Info, service_id: str) -> Integration | None:
        user_id = get_current_user_id(info.context["request"])
        response = (
            info.context["db"]
            .table("integrations")
            .select("*")
            .eq("user_id", user_id)
            .eq("service_id", service_id)
            .single()
            .execute()
        )
        if not response.data:
            return None
        integration_fields = {field.name for field in Integration.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in response.data.items() if k in integration_fields}
        # Don't expose sensitive tokens in the response
        if "access_token" in filtered_data:
            filtered_data["access_token"] = "***" if filtered_data["access_token"] else None
        if "refresh_token" in filtered_data:
            filtered_data["refresh_token"] = "***" if filtered_data["refresh_token"] else None
        # Convert connected_at from string to datetime if needed
        if "connected_at" in filtered_data:
            val = filtered_data["connected_at"]
            if isinstance(val, str):
                try:
                    filtered_data["connected_at"] = datetime.fromisoformat(
                        val.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(f"[integration] Failed to parse connected_at '{val}': {e}")
                    filtered_data["connected_at"] = datetime.utcnow()
            elif val is None:
                filtered_data["connected_at"] = datetime.utcnow()
        else:
            filtered_data["connected_at"] = datetime.utcnow()
        # Also handle expires_at if it's a string
        if "expires_at" in filtered_data and filtered_data["expires_at"] is not None:
            val = filtered_data["expires_at"]
            if isinstance(val, str):
                try:
                    filtered_data["expires_at"] = datetime.fromisoformat(val.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    filtered_data["expires_at"] = None
        return Integration(**filtered_data)

    @strawberry.field
    async def profile(self, info: strawberry.Info) -> AuthUser | None:
        # Attempt to resolve the current user.  If no access_token is
        # present (first page load, logged-out visitor), `get_current_user_id`
        # raises HTTP 401.  We intercept that specific case so the resolver
        # simply returns `null` instead of bubbling an error up the GraphQL
        # stack – this keeps the backend logs clean on startup.
        try:
            user_id = get_current_user_id(info.context["request"])
        except HTTPException as exc:
            if exc.status_code == 401:  # Missing/invalid token – treat as anonymous user
                logger.info("[schema.profile] No valid session detected – returning null profile")
                return None
            raise  # Re-raise other auth errors
        if not user_id:
            return None

        # Profile gates the entire workspace on a reload. Keep its database
        # read off the event loop and avoid loading unrelated account fields.
        def _load_profile():
            return (
                info.context["db"]
                .table("users")
                .select("user_id, email, is_guest")
                .eq("user_id", user_id)
                .single()
                .execute()
            )

        response = await asyncio.to_thread(_load_profile)
        if not response.data:
            return None

        token = (
            info.context["request"].cookies.get("session_token")
            or info.context["request"].cookies.get("access_token")
            or ""
        )

        user_data = response.data
        if not user_data.get("user_id") or not user_data.get("email"):
            return None

        is_guest = bool(user_data.get("is_guest", False))
        return AuthUser(
            user_id=user_data["user_id"],
            email=user_data["email"],
            token=token,
            is_guest=is_guest,
        )

    @strawberry.field
    async def find_similar_ideas(
        self, info: strawberry.Info, idea_description: str
    ) -> SimilarIdeas:
        from app.managers.manifest_manager import manifest_manager

        normalized_description = (idea_description or "").strip()
        cached_result = _get_ai_cache("find_similar_ideas", normalized_description)
        if cached_result is not None:
            return SimilarIdeas(similar_ideas=cached_result or "")

        def generate_similar_ideas() -> str:
            with _ai_request_lock:
                manifest_manager.set_idea(normalized_description)
                manifest_manager.similar_ideas.update()
                return manifest_manager.get_similar_ideas() or ""

        try:
            if manifest_manager.ai_layer.is_available():
                result = await asyncio.to_thread(generate_similar_ideas)
            else:
                result = build_demo_documents(normalized_description).similar_ideas
            _set_ai_cache("find_similar_ideas", normalized_description, result or "")
            return SimilarIdeas(similar_ideas=result or "")
        except Exception as e:
            logger.error(f"Error generating similar ideas: {e}")
            return SimilarIdeas(
                similar_ideas=build_demo_documents(normalized_description).similar_ideas
            )

    @strawberry.field
    async def idea_investments(self, info: strawberry.Info, idea_id: str) -> list[Investment]:
        """Get all investments for an idea"""
        from app.services.social.investments import create_investment_service

        service = create_investment_service(info.context["db"])
        investments_data = await service.get_idea_investments(idea_id)

        investments = []
        for inv in investments_data:
            investor = inv.get("investors", {}) or {}
            investments.append(
                Investment(
                    investment_id=inv["investment_id"],
                    idea_id=inv["idea_id"],
                    investor_id=inv["investor_id"],
                    cash_amount=float(inv.get("cash_amount") or 0),
                    sweat_equity_hours=float(inv.get("sweat_equity_hours") or 0),
                    sweat_equity_value=float(inv.get("sweat_equity_value") or 0),
                    equity_percentage=float(inv.get("equity_percentage") or 0),
                    investment_type=inv.get("investment_type") or "cash",
                    role=inv.get("role"),
                    status=inv.get("status") or "pending",
                    notes=inv.get("notes"),
                    created_at=(
                        datetime.fromisoformat(inv["created_at"].replace("Z", "+00:00"))
                        if isinstance(inv["created_at"], str)
                        else inv["created_at"]
                    ),
                    investor_name=_display_name(investor),
                    investor_avatar=investor.get("profile_picture_url"),
                )
            )
        return investments

    @strawberry.field
    async def idea_cap_table(self, info: strawberry.Info, idea_id: str) -> list[CapTableEntry]:
        """Get the cap table for an idea"""
        from app.services.social.investments import create_investment_service

        service = create_investment_service(info.context["db"])
        cap_data = await service.get_cap_table(idea_id)

        entries = []
        for entry in cap_data:
            stakeholder = entry.get("stakeholder", {}) or {}
            entries.append(
                CapTableEntry(
                    entry_id=entry["entry_id"],
                    idea_id=entry["idea_id"],
                    stakeholder_id=entry["stakeholder_id"],
                    stakeholder_type=entry.get("stakeholder_type") or "user",
                    equity_percentage=float(entry.get("equity_percentage") or 0),
                    shares_owned=float(entry.get("shares_owned") or 0),
                    share_class=entry.get("share_class") or "common",
                    vesting_status=entry.get("vesting_status") or "none",
                    vested_percentage=float(entry.get("vested_percentage") or 100),
                    stakeholder_name=_display_name(stakeholder),
                    stakeholder_avatar=stakeholder.get("profile_picture_url"),
                )
            )
        return entries

    @strawberry.field
    async def my_portfolio(self, info: strawberry.Info) -> list[PortfolioItem]:
        """Get current user's investment portfolio"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.social.investments import create_investment_service

        service = create_investment_service(info.context["db"])
        portfolio_data = await service.get_user_investments(user_id)

        items = []
        for inv in portfolio_data:
            idea = inv.get("ideas", {}) or {}
            items.append(
                PortfolioItem(
                    investment_id=inv["investment_id"],
                    idea_id=inv["idea_id"],
                    idea_title=idea.get("title") or "Untitled Idea",
                    idea_description=idea.get("description"),
                    cash_amount=float(inv.get("cash_amount") or 0),
                    sweat_equity_value=float(inv.get("sweat_equity_value") or 0),
                    equity_percentage=float(inv.get("equity_percentage") or 0),
                    status=inv.get("status") or "pending",
                    created_at=(
                        datetime.fromisoformat(inv["created_at"].replace("Z", "+00:00"))
                        if isinstance(inv["created_at"], str)
                        else inv["created_at"]
                    ),
                )
            )
        return items

    @strawberry.field
    async def user_followers(self, info: strawberry.Info, user_id: str) -> list[UserFollow]:
        """Get followers for a user"""
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])
        followers_data = await service.get_followers(user_id)

        followers = []
        for f in followers_data:
            user = f.get("follower", {}) or {}
            followers.append(
                UserFollow(
                    follow_id=f["follow_id"],
                    follower_id=f["follower_id"],
                    followed_id=f["followed_id"],
                    created_at=(
                        datetime.fromisoformat(f["created_at"].replace("Z", "+00:00"))
                        if isinstance(f["created_at"], str)
                        else f["created_at"]
                    ),
                    user_name=_display_name(user),
                    user_avatar=user.get("profile_picture_url"),
                )
            )
        return followers

    @strawberry.field
    async def user_following(self, info: strawberry.Info, user_id: str) -> list[UserFollow]:
        """Get users that a user is following"""
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])
        following_data = await service.get_following(user_id)

        following = []
        for f in following_data:
            user = f.get("followed", {}) or {}
            following.append(
                UserFollow(
                    follow_id=f["follow_id"],
                    follower_id=f["follower_id"],
                    followed_id=f["followed_id"],
                    created_at=(
                        datetime.fromisoformat(f["created_at"].replace("Z", "+00:00"))
                        if isinstance(f["created_at"], str)
                        else f["created_at"]
                    ),
                    user_name=_display_name(user),
                    user_avatar=user.get("profile_picture_url"),
                )
            )
        return following

    @strawberry.field
    async def user_social_stats(self, info: strawberry.Info, user_id: str) -> SocialStats:
        """Get social statistics for a user"""
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])

        follower_count = await service.get_follower_count(user_id)
        following_count = await service.get_following_count(user_id)

        is_following = False
        try:
            current_user_id = get_current_user_id(info.context["request"])
            if current_user_id and current_user_id != user_id:
                is_following = await service.is_following(current_user_id, user_id)
        except Exception:
            pass

        return SocialStats(
            follower_count=follower_count,
            following_count=following_count,
            is_following=is_following,
        )

    @strawberry.field
    async def pitch_reels_feed(self, info: strawberry.Info, limit: int = 20) -> list[PitchReel]:
        """Published pitch reels joined with their Open Media clips (empty when Open Media is off)."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.integrations.open_media import settings as open_media_settings
        from app.services.pitch_reels.service import create_pitch_reel_service

        if not open_media_settings.enabled():
            return []
        service = create_pitch_reel_service(info.context["db"])
        reels_data = await service.list_feed(viewer_id=user_id, limit=max(1, min(limit, 50)))
        return [map_pitch_reel(reel) for reel in reels_data]

    @strawberry.field
    async def pitch_reel_comments(
        self, info: strawberry.Info, reel_id: str, limit: int = 120
    ) -> list[PitchReelComment]:
        """Open Media comments on a pitch reel's clip."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.pitch_reels.service import create_pitch_reel_service

        service = create_pitch_reel_service(info.context["db"])
        try:
            comments_data = await service.list_comments(
                reel_id=reel_id, viewer_id=user_id, limit=max(1, min(limit, 200))
            )
        except Exception as exc:
            raise Exception(str(exc)) from exc
        return [map_pitch_reel_comment(comment) for comment in comments_data]

    @strawberry.field
    async def universal_search(  # noqa: C901
        self,
        info: strawberry.Info,
        query: str,
        limit: int = 5,
        include_web: bool = False,
    ) -> UniversalSearchResults:
        user_id = get_current_user_id(info.context["request"])
        db = info.context["db"]
        search_query = (query or "").strip()
        search_limit = max(1, min(limit, 8))

        if not search_query:
            return UniversalSearchResults(
                query="",
                my_ideas=[],
                published_ideas=[],
                web_sources=[],
            )

        my_ideas_response = (
            db.table("ideas")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(160)
            .execute()
        )
        my_idea_matches = _search_idea_records(
            my_ideas_response.data or [], search_query, search_limit
        )

        published_query = (
            db.table("ideas")
            .select("*")
            .eq("is_published", True)
            .neq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(200)
        )
        published_response = published_query.execute()
        published_matches = _search_idea_records(
            published_response.data or [], search_query, search_limit
        )

        my_ideas = [
            UniversalSearchIdeaResult(
                idea_id=str(item.get("idea_id") or ""),
                title=str(item.get("title") or "Untitled Idea"),
                snippet=str(item.get("snippet") or ""),
                matched_in=item.get("matched_in"),
                created_at=_coerce_datetime(item.get("created_at")),
                user_id=str(item.get("user_id") or ""),
                is_published=bool(item.get("is_published") or False),
            )
            for item in my_idea_matches
        ]

        published_ideas: list[UniversalSearchIdeaResult] = []
        creators_by_id = _fetch_user_search_profiles(
            db, [item.get("user_id") for item in published_matches]
        )
        for item in published_matches:
            creator = creators_by_id.get(str(item.get("user_id") or ""), {})
            published_ideas.append(
                UniversalSearchIdeaResult(
                    idea_id=str(item.get("idea_id") or ""),
                    title=str(item.get("title") or "Untitled Idea"),
                    snippet=str(item.get("snippet") or ""),
                    matched_in=item.get("matched_in"),
                    created_at=_coerce_datetime(item.get("created_at")),
                    user_id=str(item.get("user_id") or ""),
                    is_published=bool(item.get("is_published") or False),
                    creator_name=_display_name(creator, "Manifest founder"),
                    creator_avatar=creator.get("profile_picture_url"),
                )
            )

        assistant_summary = None
        web_summary = None
        web_sources: list[UniversalSearchWebSource] = []

        if include_web:
            try:
                cached_web = _get_ai_cache("universal_search_web", search_query)

                if cached_web is None:
                    from app.managers.manifest_manager import manifest_manager

                    def perform_web_search() -> dict[str, Any] | None:
                        if not manifest_manager.ai_layer.is_available():
                            return None
                        web_result = manifest_manager.ai_layer.perform_web_search(search_query)
                        return {
                            "web_summary": _normalize_search_text(web_result.get("similar_ideas"))
                            or None,
                            "sources": web_result.get("sources") or [],
                        }

                    cached_web = await asyncio.to_thread(perform_web_search)
                    if cached_web is not None:
                        _set_ai_cache("universal_search_web", search_query, cached_web)

                if cached_web:
                    web_summary = cached_web.get("web_summary")
                    for url in (cached_web.get("sources") or [])[:6]:
                        source = _build_web_source(url)
                        if not source:
                            continue
                        web_sources.append(
                            UniversalSearchWebSource(
                                title=source["title"],
                                url=source["url"],
                                hostname=source["hostname"],
                            )
                        )
                    assistant_cache_context = "|".join(
                        [
                            search_query,
                            ",".join(result.idea_id for result in my_ideas),
                            ",".join(result.idea_id for result in published_ideas),
                            web_summary or "",
                        ]
                    )
                    cached_assistant_summary = _get_ai_cache(
                        "universal_search_assistant_summary",
                        assistant_cache_context,
                    )
                    if cached_assistant_summary is None:
                        cached_assistant_summary = await asyncio.to_thread(
                            _generate_universal_search_summary,
                            search_query,
                            my_ideas,
                            published_ideas,
                            web_summary,
                        )
                        _set_ai_cache(
                            "universal_search_assistant_summary",
                            assistant_cache_context,
                            cached_assistant_summary,
                        )
                    assistant_summary = cached_assistant_summary
            except Exception as exc:
                logger.warning(f"[universal_search] Web search failed: {exc}")

        return UniversalSearchResults(
            query=search_query,
            my_ideas=my_ideas,
            published_ideas=published_ideas,
            assistant_summary=assistant_summary,
            web_summary=web_summary,
            web_sources=web_sources,
        )

    @strawberry.field
    async def calculate_sweat_equity(
        self, hours: float, hourly_rate: float = 50, total_valuation: float = 100000
    ) -> SweatEquityCalculation:
        """Calculate sweat equity value and percentage"""
        sweat_value = hours * hourly_rate
        equity_percentage = (sweat_value / total_valuation) * 100 if total_valuation > 0 else 0

        return SweatEquityCalculation(
            sweat_value=sweat_value,
            equity_percentage=round(equity_percentage, 4),
            hours=hours,
            hourly_rate=hourly_rate,
        )

    @strawberry.field
    async def patents(self, info: strawberry.Info) -> list[Patent]:
        # Placeholder: Replace with actual DB logic
        return []

    @strawberry.field
    async def pitch_deck(self, info: strawberry.Info, idea_id: str) -> PitchDeckOutput:
        user_id = get_current_user_id(info.context["request"])
        result = (
            info.context["db"]
            .table("ideas")
            .select("pitch_deck")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if not result.data or not result.data.get("pitch_deck"):
            raise Exception("Pitch deck not found")
        return PitchDeckOutput(pitch_deck=result.data["pitch_deck"])

    @strawberry.field
    async def product_requirements_document(
        self, info: strawberry.Info, idea_id: str
    ) -> ProductRequirementsDocumentOutput:
        user_id = get_current_user_id(info.context["request"])
        result = (
            info.context["db"]
            .table("ideas")
            .select("product_requirements_document")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if not result.data or not result.data.get("product_requirements_document"):
            raise Exception("Product requirements document not found")
        return ProductRequirementsDocumentOutput(
            product_requirements_document=result.data["product_requirements_document"]
        )

    @strawberry.field
    async def provisional_patent(
        self, info: strawberry.Info, idea_id: str
    ) -> ProvisionalPatentOutput:
        # Try to get patent data from intellectual_properties table
        user_id = get_current_user_id(info.context["request"])

        coversheet_pdf = None
        specification_pdf = None
        provisional_patent_text = None

        # First, try to get from intellectual_properties table (for PDFs)
        try:
            ip_response = (
                info.context["db"]
                .table("intellectual_properties")
                .select("*")
                .eq("idea_id", idea_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if ip_response.data:
                # Get PDF URLs from intellectual_properties table
                pdf_url_data = ip_response.data.get("pdf_url")
                if pdf_url_data:
                    import json

                    try:
                        # Try to parse as JSON (new format with both PDFs)
                        pdf_urls = json.loads(pdf_url_data)
                        specification_pdf = pdf_urls.get("specification_pdf")
                        coversheet_pdf = pdf_urls.get("coversheet_pdf")
                    except (json.JSONDecodeError, TypeError):
                        # Fallback: if it's a plain string URL, assume it's the specification
                        specification_pdf = pdf_url_data
        except Exception:
            # If intellectual_properties query fails, continue to try ideas table
            pass

        # Also try to get text draft from ideas table
        idea_response = (
            info.context["db"]
            .table("ideas")
            .select("provisional_patent")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if idea_response.data and idea_response.data.get("provisional_patent"):
            provisional_patent_text = idea_response.data["provisional_patent"]

        if not provisional_patent_text and not coversheet_pdf and not specification_pdf:
            raise Exception("Provisional patent draft not found")

        return ProvisionalPatentOutput(
            provisional_patent=provisional_patent_text or "",
            coversheet_pdf=coversheet_pdf,
            specification_pdf=specification_pdf,
        )

    @strawberry.field
    def available_skills(self) -> list[str]:
        """Return the canonical list of skills available on the platform."""
        return AVAILABLE_SKILLS

    @strawberry.field
    async def my_conversations(
        self,
        info: strawberry.Info,
        limit: int = 50,
        offset: int = 0,
        all_apps: bool = False,
    ) -> list[Conversation]:
        """Open Media conversations; Manifest ones (``context.app = manifest``) unless ``allApps``."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.integrations.open_media import messaging as om_messaging

        convs = await call_open_media(
            om_messaging.list_conversations, user_id, app_only=not all_apps
        )
        start = max(0, offset)
        return [map_conversation(c) for c in convs[start : start + max(1, min(limit, 100))]]

    @strawberry.field
    async def conversation_messages(
        self,
        info: strawberry.Info,
        conversation_id: str,
        limit: int = 100,
        before_id: str | None = None,
    ) -> list[Message]:
        """Messages in an Open Media conversation, oldest first."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.integrations.open_media import identity as om_identity
        from app.services.integrations.open_media import messaging as om_messaging

        messages = await call_open_media(
            om_messaging.list_messages, user_id, conversation_id, limit=limit, before=before_id
        )
        me = await asyncio.to_thread(om_identity.om_user_id_for, user_id)
        return [map_message(m, me) for m in messages]

    @strawberry.field
    async def unread_message_count(self, info: strawberry.Info) -> UnreadCount:
        """Unread Manifest messages (0 when Open Media is off, unlinked or unreachable)."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.integrations.open_media import messaging as om_messaging
        from app.services.integrations.open_media import settings as open_media_settings

        if not open_media_settings.enabled():
            return UnreadCount(count=0)
        try:
            count = await call_open_media(om_messaging.unread_count, user_id)
        except Exception:
            count = 0  # never break the nav badge
        return UnreadCount(count=int(count or 0))

    @strawberry.field
    async def idea_owner(self, info: strawberry.Info, idea_id: str) -> Optional["IdeaOwner"]:
        """The founder of an idea, and whether the viewer can message them on Open Media."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.social.founder_contact import get_idea_owner

        data = await asyncio.to_thread(get_idea_owner, info.context["db"], idea_id, user_id)
        if not data:
            return None

        owner = data["owner"]
        return IdeaOwner(
            user_id=owner["user_id"],
            username=owner.get("username"),
            first_name=owner.get("first_name"),
            last_name=owner.get("last_name"),
            bio=owner.get("bio"),
            profile_picture_url=owner.get("profile_picture_url"),
            idea_id=data["idea_id"],
            idea_title=data.get("idea_title"),
            is_published=bool(data.get("is_published", False)),
            can_message=bool(data.get("can_message", False)),
            open_media_handle=data.get("open_media_handle"),
        )

    @strawberry.field
    async def open_media_link(self, info: strawberry.Info) -> OpenMediaLink:
        """Whether Open Media is enabled here and linked to the current account."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.integrations.open_media import identity as om_identity

        return map_link(await asyncio.to_thread(om_identity.link_status, user_id))

    @strawberry.field
    async def open_media_realtime_token(self, info: strawberry.Info) -> OpenMediaRealtimeToken:
        """Short-lived Open Media Supabase credentials for live message updates."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.integrations.open_media import messaging as om_messaging

        token = await call_open_media(om_messaging.realtime_token, user_id)
        return OpenMediaRealtimeToken(
            supabase_url=token["supabase_url"],
            anon_key=token["anon_key"],
            access_token=token["access_token"],
            expires_at=str(token["expires_at"]) if token.get("expires_at") else None,
            om_user_id=token.get("om_user_id"),
        )

    # ==================== COLLABORATION QUERIES ====================

    @strawberry.field
    async def idea_collaborators(self, info: strawberry.Info, idea_id: str) -> list["Collaborator"]:
        """Get all collaborators for an idea including the owner"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        has_access = await service.check_access(idea_id, user_id, "view")
        owner = await service.get_idea_owner(idea_id)
        if not has_access and user_id != owner:
            raise Exception("You don't have access to view collaborators")

        collaborators_data = await service.get_collaborators(idea_id)

        result = []
        for c in collaborators_data:
            invited_at = None
            accepted_at = None
            if c.get("invited_at"):
                invited_at = (
                    datetime.fromisoformat(c["invited_at"].replace("Z", "+00:00"))
                    if isinstance(c["invited_at"], str)
                    else c["invited_at"]
                )
            if c.get("accepted_at"):
                accepted_at = (
                    datetime.fromisoformat(c["accepted_at"].replace("Z", "+00:00"))
                    if isinstance(c["accepted_at"], str)
                    else c["accepted_at"]
                )

            result.append(
                Collaborator(
                    collaborator_id=c.get("collaborator_id"),
                    idea_id=c["idea_id"],
                    user_id=c["user_id"],
                    role=c["role"],
                    status=c.get("status", "accepted"),
                    user_email=c.get("user_email"),
                    user_name=c.get("user_name"),
                    user_avatar=c.get("user_avatar"),
                    invited_at=invited_at,
                    accepted_at=accepted_at,
                )
            )
        return result

    @strawberry.field
    async def my_shared_ideas(self, info: strawberry.Info) -> list["SharedIdea"]:
        """Get ideas shared with the current user"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        shared_data = await service.get_shared_ideas(user_id)

        result = []
        for idea in shared_data:
            result.append(
                SharedIdea(
                    idea_id=idea["idea_id"],
                    title=idea.get("title") or "Untitled Idea",
                    description=idea.get("description"),
                    user_role=idea["user_role"],
                    created_at=(
                        datetime.fromisoformat(idea["created_at"].replace("Z", "+00:00"))
                        if isinstance(idea["created_at"], str)
                        else idea["created_at"]
                    ),
                )
            )
        return result

    @strawberry.field
    async def my_collaboration_invitations(
        self, info: strawberry.Info
    ) -> list["CollaborationInvitation"]:
        """Get pending collaboration invitations for the current user"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        invitations_data = await service.get_pending_invitations(user_id)

        result = []
        for inv in invitations_data:
            invited_at = None
            if inv.get("invited_at"):
                invited_at = (
                    datetime.fromisoformat(inv["invited_at"].replace("Z", "+00:00"))
                    if isinstance(inv["invited_at"], str)
                    else inv["invited_at"]
                )

            result.append(
                CollaborationInvitation(
                    collaborator_id=inv["collaborator_id"],
                    idea_id=inv["idea_id"],
                    role=inv["role"],
                    status=inv["status"],
                    idea_title=inv.get("idea_title"),
                    idea_description=inv.get("idea_description"),
                    inviter_name=inv.get("inviter_name"),
                    invited_at=invited_at,
                )
            )
        return result

    @strawberry.field
    async def idea_versions(self, info: strawberry.Info, idea_id: str) -> list["IdeaVersion"]:
        """Get version history for an idea"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        versions_data = await service.get_versions(idea_id, user_id)

        result = []
        for v in versions_data:
            result.append(
                IdeaVersion(
                    version_id=v["version_id"],
                    idea_id=v["idea_id"],
                    version_number=v["version_number"],
                    title=v.get("title"),
                    description=v.get("description"),
                    created_by=v["created_by"],
                    created_at=(
                        datetime.fromisoformat(v["created_at"].replace("Z", "+00:00"))
                        if isinstance(v["created_at"], str)
                        else v["created_at"]
                    ),
                    change_summary=v.get("change_summary"),
                    creator_name=v.get("creator_name"),
                    creator_avatar=v.get("creator_avatar"),
                    version_kind=v.get("version_kind") or VERSION_KIND_MANUAL,
                )
            )
        return result

    @strawberry.field
    async def check_idea_access(self, info: strawberry.Info, idea_id: str) -> "AccessCheckResult":
        """Check if current user has access to an idea and get their role"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        owner = await service.get_idea_owner(idea_id)
        if user_id == owner:
            return AccessCheckResult(has_access=True, role="owner")

        role = await service.get_user_role(idea_id, user_id)
        return AccessCheckResult(has_access=role is not None, role=role)

    @strawberry.field
    async def idea_qualification_session(
        self, info: strawberry.Info, session_id: str
    ) -> IdeaQualificationSession | None:
        from app.services.ai import idea_qualification as qs

        user_id = get_current_user_id(info.context["request"])
        row = qs.get_session(db=info.context["db"], session_id=session_id, user_id=user_id)
        if row is None:
            return None
        return _map_qualification_session(row)

    @strawberry.field
    async def my_idea_qualification_sessions(
        self, info: strawberry.Info
    ) -> list[IdeaQualificationSession]:
        from app.services.ai import idea_qualification as qs

        user_id = get_current_user_id(info.context["request"])
        rows = qs.list_sessions(db=info.context["db"], user_id=user_id)
        return [_map_qualification_session(r) for r in rows]

    @strawberry.field
    async def my_cost_dashboard(self, info: strawberry.Info) -> UserCostDashboard:
        from app.services.ai import cost_tracking as cost_tracking_service

        user_id = get_current_user_id(info.context["request"])
        payload = cost_tracking_service.build_user_cost_dashboard(
            db=info.context["db"], user_id=user_id
        )
        return _map_cost_dashboard(payload)

    @strawberry.field
    async def my_agent_runs(self, info: strawberry.Info, limit: int = 20) -> list[AgentRunSummary]:
        from app.services.ai import cost_tracking as cost_tracking_service

        user_id = get_current_user_id(info.context["request"])
        rows = cost_tracking_service.list_recent_runs(
            db=info.context["db"], user_id=user_id, limit=limit
        )
        return [_map_agent_run(r) for r in rows]

    @strawberry.field
    async def my_cost_preflight(
        self,
        info: strawberry.Info,
        agent_kind: str | None = None,
        est_cost_usd: float | None = None,
    ) -> CostPreflight:
        """Preflight check: would a new run be allowed right now?

        Pass `agent_kind` to get the right estimated cost (the guard
        uses a per-kind calibration table). The mutation layer also
        enforces — this is just a UX preview so buttons can be
        disabled before the user clicks.
        """
        from app.services.ai import cost_tracking as cost_tracking_service

        user_id = get_current_user_id(info.context["request"])
        result = cost_tracking_service.guard_can_run(
            db=info.context["db"],
            user_id=user_id,
            agent_kind=agent_kind,
            est_cost_usd=est_cost_usd,
        )
        return CostPreflight(
            allowed=bool(result.get("allowed") or False),
            reason=result.get("reason"),
            monthly_usage_usd=float(result.get("monthly_usage_usd") or 0),
            cap_usd=float(result.get("cap_usd") or 0),
            remaining_usd=float(result.get("remaining_usd") or 0),
            estimated_cost_usd=float(result.get("estimated_cost_usd") or 0),
            paused=bool(result.get("paused") or False),
            agent_kind=result.get("agent_kind"),
        )

    @strawberry.field
    async def bmc_sections(self, info: strawberry.Info, idea_id: str) -> list[BmcSection]:
        """Per-section BMC content for an idea owned by the caller.

        Returns nine entries in canonical order; sections that have not
        been generated yet come back with `content = null`.
        """
        from app.services.canvas import orchestrator as bmc

        user_id = get_current_user_id(info.context["request"])
        ownership = (
            info.context["db"]
            .table("ideas")
            .select("idea_id")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not (ownership.data or []):
            return []
        rows = bmc.get_sections(db=info.context["db"], idea_id=idea_id)
        return [_map_bmc_section(r) for r in rows]

    @strawberry.field
    async def partner_candidates(
        self, info: strawberry.Info, idea_id: str
    ) -> list[PartnerCandidate]:
        """Ranked partner candidates for an idea owned by the caller.

        Returns an empty list (rather than an error) when the idea is
        not owned, so the frontend can render the empty-state cleanly
        for any non-owner view without revealing ownership info.
        """
        from app.services.ideas import partner_discovery as pd

        user_id = get_current_user_id(info.context["request"])
        ownership = (
            info.context["db"]
            .table("ideas")
            .select("idea_id")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not (ownership.data or []):
            return []
        rows = pd.list_candidates(db=info.context["db"], idea_id=idea_id)
        return [_map_partner_candidate(r) for r in rows]

    @strawberry.field
    async def admin_cost_overview(
        self, info: strawberry.Info, window_days: int | None = None
    ) -> AdminCostOverview:
        from app.services.ai import admin_costs as admin_cost_service

        payload = admin_cost_service.build_admin_cost_overview(
            db=info.context["db"], window_days=window_days
        )
        return _map_admin_overview(payload)

    @strawberry.field
    async def admin_agent_runs(
        self,
        info: strawberry.Info,
        limit: int = 50,
        agent_kind: str | None = None,
        status: str | None = None,
    ) -> list[AdminAgentRunRow]:
        from app.services.ai import admin_costs as admin_cost_service

        rows = admin_cost_service.list_recent_runs_cross_user(
            db=info.context["db"], limit=limit, agent_kind=agent_kind, status=status
        )
        return [_map_admin_agent_run(r) for r in rows]

    @strawberry.field
    async def admin_production_test_stats(
        self, info: strawberry.Info, hours: int = 24
    ) -> AdminProductionTestStats:
        from app.services.ai import admin_costs as admin_cost_service

        payload = admin_cost_service.build_production_test_health(
            db=info.context["db"], hours=hours
        )
        return _map_admin_test_stats(payload)

    @strawberry.field
    async def admin_voice_test_runs(
        self,
        info: strawberry.Info,
        limit: int = 50,
        scenario: str | None = None,
        emotion: str | None = None,
        pass_only: bool | None = None,
    ) -> list[VoiceTestRun]:
        from app.services.voice import evaluation as vts

        rows = vts.list_recent_runs(
            db=info.context["db"],
            limit=limit,
            scenario=scenario,
            emotion=emotion,
            pass_only=pass_only,
        )
        return [_map_voice_test_run(r) for r in rows]

    @strawberry.field
    async def admin_voice_test_stats(
        self, info: strawberry.Info, hours: int = 168
    ) -> VoiceTestStats:
        from app.services.voice import evaluation as vts

        payload = vts.get_test_stats(db=info.context["db"], hours=hours)
        return _map_voice_test_stats(payload)


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_idea(
        self, info: strawberry.Info, title: str, description: str | None = None
    ) -> Idea:
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.list_metadata import compute_idea_list_metadata

        data = {
            "idea_id": str(uuid.uuid4()),
            "title": title,
            "description": description,
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
        }
        data.update(compute_idea_list_metadata(data))
        response = info.context["db"].table("ideas").insert(data).execute()
        inserted = response.data
        if isinstance(inserted, dict):
            inserted = [inserted]

        if not inserted or len(inserted) == 0:
            raise Exception("Failed to create idea")

        idea_id = inserted[0].get("idea_id", data["idea_id"])
        _start_background_generation(idea_id, description)

        idea_fields = {field.name for field in Idea.__dataclass_fields__.values()}
        return Idea(**{k: v for k, v in inserted[0].items() if k in idea_fields})

    @strawberry.mutation
    async def update_idea(
        self,
        info: strawberry.Info,
        idea_id: str,
        title: str | None = None,
        description: str | None = None,
        required_skills: list[str] | None = None,
    ) -> Idea:
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        collab_gate = create_collaboration_service(info.context["db"])
        if not await collab_gate.check_access(idea_id, user_id, "edit"):
            raise Exception("Idea not found or you don't have permission to edit it")

        update_data = {}
        # Only include title/description in the UPDATE payload if they contain
        # meaningful content. This prevents accidental overwrites that would
        # wipe out previously-saved data when the frontend temporarily sends
        # an empty string (e.g. when switching between ideas before the
        # editor finishes loading).

        if title is not None and title.strip() != "":
            update_data["title"] = title

        if required_skills is not None:
            update_data["required_skills"] = required_skills

        def _has_meaningful_html(html: str) -> bool:
            """Return True if there is any non-whitespace text after stripping HTML tags & entities."""
            if not html or not isinstance(html, str):
                return False
            text_only = re.sub(r"<[^>]+>", "", html)
            text_only = re.sub(r"&nbsp;|&#160;", " ", text_only)
            text_only = text_only.strip()
            text_only = re.sub(r"[\u200B-\u200D\uFEFF]", "", text_only)
            return text_only != ""

        description_changed = description is not None and _has_meaningful_html(description)
        if description_changed:
            update_data["description"] = description
            update_data["has_description"] = True

        if not update_data:
            raise Exception("No valid fields provided for update")

        response = (
            info.context["db"].table("ideas").update(update_data).eq("idea_id", idea_id).execute()
        )
        if not response.data or len(response.data) == 0:
            raise Exception("Idea not found or not updated")

        # Drop the voice agent's cached conversation context for this idea so
        # the next voice turn sees the new title/description immediately.
        try:
            from app.services.shared.cache import cache_delete

            cache_delete(f"voice:context:{user_id}:{idea_id}")
        except Exception:  # cache invalidation must never fail the mutation
            pass

        _start_background_generation(idea_id, update_data.get("description"))

        title_changed = "title" in update_data
        if title_changed or description_changed:
            try:
                collab_service = create_collaboration_service(info.context["db"])
                await collab_service.maybe_record_auto_version_after_user_edit(idea_id, user_id)
            except Exception as e:
                logger.warning(f"Auto-version creation failed for idea {idea_id}: {e}")

        idea_fields = {field.name for field in Idea.__dataclass_fields__.values()}
        return Idea(**{k: v for k, v in response.data[0].items() if k in idea_fields})

    @strawberry.mutation
    async def delete_idea(self, info: strawberry.Info, idea_id: str) -> bool:
        """Delete an idea owned by the current user.

        Task #48: Hardened with structured logging and explicit error
        classification so production failures (especially FK constraint
        violations on related tables) surface as actionable messages
        instead of opaque "Failed to delete idea" errors. The companion
        startup migration in app/main.py enforces ON DELETE CASCADE on
        every child table that references ideas.idea_id, so a successful
        ownership check should always be followed by a successful delete.
        """
        user_id = get_current_user_id(info.context["request"])
        logger.info(
            "[delete_idea] start user_id=%s idea_id=%s",
            user_id,
            idea_id,
        )

        # Verify the idea exists and belongs to the user before deleting.
        # We deliberately avoid `.single()` here so the row-count handling
        # is explicit and behaves identically across in-memory and Postgres
        # backends: `.limit(1).execute()` always returns a list (possibly
        # empty), and the caller does the matched/unmatched decision.
        try:
            check_response = (
                info.context["db"]
                .table("ideas")
                .select("idea_id")
                .eq("idea_id", idea_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            logger.exception(
                "[delete_idea] ownership check failed user_id=%s idea_id=%s",
                user_id,
                idea_id,
            )
            raise Exception("Failed to delete idea: lookup error") from exc

        check_rows = check_response.data or []
        # Explicit row-count handling: 0 rows = not found / not owned;
        # 1 row = proceed; >1 should be impossible (PK on idea_id) but if
        # it ever happens we still want to refuse cleanly.
        if len(check_rows) != 1:
            logger.info(
                "[delete_idea] not found / not owned user_id=%s idea_id=%s rows=%d",
                user_id,
                idea_id,
                len(check_rows),
            )
            raise Exception(
                "Failed to delete idea: Idea not found or you don't have permission to delete it"
            )

        # Delete the idea. Cascade rules in the database remove all related
        # rows in a single transaction; if the cascade DDL has not been
        # applied yet (older deployment), psycopg2 raises a
        # ForeignKeyViolation, which we translate to a friendly message.
        try:
            delete_response = (
                info.context["db"]
                .table("ideas")
                .delete()
                .eq("idea_id", idea_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as exc:
            exc_name = type(exc).__name__
            # FK violations can surface under several attribute names
            # depending on the driver: psycopg2 uses `pgcode`, PostgREST /
            # supabase-py APIError objects use `code`, and some wrappers
            # expose `error_code`. We check all three so the friendly
            # "related records" classification is reached regardless of
            # which client raised it.
            pgcode = getattr(exc, "pgcode", None)
            api_code = getattr(exc, "code", None)
            err_code = getattr(exc, "error_code", None)
            logger.exception(
                "[delete_idea] delete raised exception user_id=%s idea_id=%s "
                "exc_type=%s pgcode=%s code=%s error_code=%s",
                user_id,
                idea_id,
                exc_name,
                pgcode,
                api_code,
                err_code,
            )
            # 23503 = foreign_key_violation in PostgreSQL
            fk_codes = {"23503"}
            is_fk_violation = (
                pgcode in fk_codes
                or api_code in fk_codes
                or err_code in fk_codes
                or "ForeignKeyViolation" in exc_name
            )
            if is_fk_violation:
                raise Exception(
                    "Failed to delete idea: related records prevented deletion. "
                    "Please contact support if this persists."
                ) from exc
            raise Exception("Failed to delete idea") from exc

        # Prefer RETURNING row count from our QueryBuilder; some clients or
        # edge paths omit deleted rows in `data`. If empty, re-check whether
        # the idea row still exists for this user — gone means success
        # (concurrent delete or driver quirk); still present is a real failure.
        returning_rows = delete_response.data or []
        if len(returning_rows) == 0:
            logger.warning(
                "[delete_idea] delete returned 0 rows in response user_id=%s idea_id=%s "
                "(verifying row existence)",
                user_id,
                idea_id,
            )
            try:
                verify_response = (
                    info.context["db"]
                    .table("ideas")
                    .select("idea_id")
                    .eq("idea_id", idea_id)
                    .eq("user_id", user_id)
                    .limit(1)
                    .execute()
                )
            except Exception as exc:
                logger.exception(
                    "[delete_idea] post-delete verify failed user_id=%s idea_id=%s",
                    user_id,
                    idea_id,
                )
                raise Exception("Failed to delete idea: lookup error") from exc

            verify_rows = verify_response.data or []
            if len(verify_rows) == 0:
                logger.info(
                    "[delete_idea] success after empty RETURNING user_id=%s idea_id=%s "
                    "(row absent on verify)",
                    user_id,
                    idea_id,
                )
                return True

            logger.warning(
                "[delete_idea] delete affected 0 rows and row still present user_id=%s idea_id=%s",
                user_id,
                idea_id,
            )
            raise Exception("Failed to delete idea")

        logger.info(
            "[delete_idea] success user_id=%s idea_id=%s rows_deleted=%d",
            user_id,
            idea_id,
            len(returning_rows),
        )
        return True

    @strawberry.mutation
    async def toggle_publish_idea(self, info: strawberry.Info, idea_id: str) -> PublishResult:
        """Toggle the publish status of an idea. Published ideas become available in public discovery."""
        user_id = _require_full_account(info.context["db"], info.context["request"])

        # First get current publish state and copy for pitch reel
        check_response = (
            info.context["db"]
            .table("ideas")
            .select("idea_id, is_published, title, description")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if not check_response.data:
            raise Exception("Idea not found or you don't have permission to modify it")

        idea_row = check_response.data
        current_status = idea_row.get("is_published", False)
        new_status = not current_status

        # Update the idea
        update_response = (
            info.context["db"]
            .table("ideas")
            .update({"is_published": new_status})
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not update_response.data or len(update_response.data) == 0:
            raise Exception("Failed to update idea publish status")

        if new_status:
            from app.services.pitch_reels.service import create_pitch_reel_service
            from app.services.pitch_reels.video_worker import schedule_pitch_reel_video_generation

            reel_service = create_pitch_reel_service(info.context["db"])
            reel_id, needs_video = reel_service.upsert_reel_for_published_idea(
                idea_id,
                user_id,
                idea_row.get("title"),
                idea_row.get("description"),
            )
            if needs_video:  # no-op unless Open Media and video generation are enabled
                schedule_pitch_reel_video_generation(
                    reel_id,
                    str(idea_row.get("title") or ""),
                    str(idea_row.get("description") or ""),
                )
        else:
            from app.services.pitch_reels.service import create_pitch_reel_service

            await asyncio.to_thread(
                create_pitch_reel_service(info.context["db"]).unpublish_reel_for_idea, idea_id
            )

        return PublishResult(idea_id=idea_id, is_published=new_status)

    @strawberry.mutation
    async def save_openai_api_key(self, info: strawberry.Info, api_key: str) -> AiKeyStatus:
        """Store the customer's own OpenAI key (validated, encrypted at rest)."""
        from app.services.ai.user_keys import InvalidOpenAIKeyError, save_user_key

        user_id = str(get_current_user_id(info.context["request"]))
        try:
            await asyncio.to_thread(save_user_key, user_id, api_key)
        except InvalidOpenAIKeyError as exc:
            raise Exception(str(exc)) from None
        info.context["request"].state.openai_key = None  # re-resolve on next AI call
        return await asyncio.to_thread(_ai_key_status, user_id)

    @strawberry.mutation
    async def remove_openai_api_key(self, info: strawberry.Info) -> AiKeyStatus:
        from app.services.ai.user_keys import delete_user_key

        user_id = str(get_current_user_id(info.context["request"]))
        await asyncio.to_thread(delete_user_key, user_id)
        return await asyncio.to_thread(_ai_key_status, user_id)

    @strawberry.mutation
    async def update_account(self, info: strawberry.Info, input: AccountUpdateInput) -> User:
        user_id = get_current_user_id(info.context["request"])
        update_data = {k: v for k, v in vars(input).items() if v is not None}
        if not update_data:
            raise Exception("No valid fields provided for update")

        # Filter out fields that don't exist in the users table
        allowed_fields = [
            "email",
            "username",
            "first_name",
            "last_name",
            "country",
            "bio",
            "address",
            "state",
            "gravatar_hash",
            "profile_picture_url",
            "skills",
        ]
        filtered_update_data = {k: v for k, v in update_data.items() if k in allowed_fields}

        if not filtered_update_data:
            raise Exception("No updatable fields provided")

        response = (
            info.context["db"]
            .table("users")
            .update(filtered_update_data)
            .eq("user_id", user_id)
            .execute()
        )
        if not response.data or len(response.data) == 0:
            raise Exception("User not found or not updated")
        user_fields = {field.name for field in User.__dataclass_fields__.values()}
        return User(**{k: v for k, v in response.data[0].items() if k in user_fields})

    @strawberry.mutation
    async def connect_integration(
        self, info: strawberry.Info, input: ConnectIntegrationInput
    ) -> Integration:
        user_id = get_current_user_id(info.context["request"])

        # Service name mapping (you can expand this)
        service_names = {
            "google": "Google",
            "apple": "Apple",
            "meta": "Meta",
            "reddit": "Reddit",
            "x": "X (Twitter)",
            "zapier": "Zapier",
            "n8n": "n8n",
            "canva": "Canva",
            "figma": "Figma",
            "openai": "OpenAI",
            "github": "GitHub",
            "microsoft": "Microsoft",
            "asana": "Asana",
            "notion": "Notion",
        }

        service_name = service_names.get(input.service_id, input.service_id.title())

        integration_data = {
            "user_id": user_id,
            "service_id": input.service_id,
            "service_name": service_name,
            "access_token": input.access_token,
            "refresh_token": input.refresh_token,
            "expires_at": input.expires_at.isoformat() if input.expires_at else None,
            "connected_at": datetime.utcnow().isoformat(),
            "metadata": input.metadata,
        }

        # Check if integration already exists
        existing = (
            info.context["db"]
            .table("integrations")
            .select("*")
            .eq("user_id", user_id)
            .eq("service_id", input.service_id)
            .execute()
        )

        if existing.data and len(existing.data) > 0:
            # Update existing integration
            response = (
                info.context["db"]
                .table("integrations")
                .update(integration_data)
                .eq("user_id", user_id)
                .eq("service_id", input.service_id)
                .execute()
            )
        else:
            # Create new integration
            import uuid

            integration_data["integration_id"] = str(uuid.uuid4())
            response = info.context["db"].table("integrations").insert(integration_data).execute()

        if not response.data:
            raise Exception("Failed to connect integration")

        # Handle both single object and array responses
        result_data = (
            response.data[0]
            if isinstance(response.data, list) and len(response.data) > 0
            else response.data
        )
        integration_fields = {field.name for field in Integration.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in result_data.items() if k in integration_fields}
        # Don't expose sensitive tokens in the response
        if "access_token" in filtered_data:
            filtered_data["access_token"] = "***" if filtered_data["access_token"] else None
        if "refresh_token" in filtered_data:
            filtered_data["refresh_token"] = "***" if filtered_data["refresh_token"] else None
        if "connected_at" in filtered_data and isinstance(filtered_data["connected_at"], str):
            filtered_data["connected_at"] = datetime.fromisoformat(
                filtered_data["connected_at"].replace("Z", "+00:00")
            )
        if "expires_at" in filtered_data and isinstance(filtered_data["expires_at"], str):
            filtered_data["expires_at"] = datetime.fromisoformat(
                filtered_data["expires_at"].replace("Z", "+00:00")
            )
        return Integration(**filtered_data)

    @strawberry.mutation
    async def disconnect_integration(self, info: strawberry.Info, service_id: str) -> bool:
        user_id = get_current_user_id(info.context["request"])

        (
            info.context["db"]
            .table("integrations")
            .delete()
            .eq("user_id", user_id)
            .eq("service_id", service_id)
            .execute()
        )

        return True

    @strawberry.mutation
    async def submit_contact_form(self, info: strawberry.Info, input: ContactFormInput) -> bool:
        data = {
            "first_name": input.first_name,
            "last_name": input.last_name,
            "email": input.email,
            "summary": input.message,
            "source": "contact_form",
            "created_at": datetime.utcnow().isoformat(),
        }
        info.context["db"].table("customers").insert(data).execute()
        return True

    @strawberry.mutation
    async def submit_survey(self, info: strawberry.Info, input: SubmitSurveyInput) -> bool:
        """Persist research (public) or product-feedback (authenticated) survey answers to Postgres."""
        raw_type = (input.survey_type or "").strip().lower()
        if raw_type not in ("research", "product_feedback"):
            raise Exception("Invalid survey type")

        payload = (input.answers_json or "").strip()
        if len(payload) > 120_000:
            raise Exception("Survey answers are too large")

        try:
            answers = json.loads(payload if payload else "{}")
        except json.JSONDecodeError as exc:
            raise Exception("Invalid answers JSON") from exc

        if not isinstance(answers, dict):
            raise Exception("Answers must be a JSON object")

        answers_payload = json.dumps(answers)

        if raw_type == "research":
            if not answers.get("consent_required"):
                raise Exception("You must agree before submitting")
        else:
            user_required = get_current_user_id_optional(info.context["request"])
            if not user_required:
                raise Exception("Sign in to submit product feedback")

        user_id = get_current_user_id_optional(info.context["request"])
        email = (input.contact_email or "").strip() or None

        row = {
            "response_id": str(uuid.uuid4()),
            "survey_type": raw_type,
            "user_id": user_id,
            "contact_email": email,
            "answers": answers_payload,
            "created_at": datetime.utcnow().isoformat(),
        }
        try:
            info.context["db"].table("survey_responses").insert(row).execute()
        except Exception as exc:
            logger.error(
                "[submit_survey] Failed to save survey response (survey_type=%s, user_id=%s): %s",
                raw_type,
                user_id,
                exc,
            )
            raise Exception("Could not save survey response") from exc
        return True

    @strawberry.mutation
    async def create_investment(
        self, info: strawberry.Info, input: CreateInvestmentInput
    ) -> Investment:
        """Create a new investment in an idea"""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.social.investments import create_investment_service

        service = create_investment_service(info.context["db"])

        result = await service.create_investment(
            idea_id=input.idea_id,
            investor_id=user_id,
            cash_amount=input.cash_amount,
            sweat_equity_hours=input.sweat_equity_hours,
            hourly_rate=input.hourly_rate,
            equity_percentage=input.equity_percentage,
            investment_type=input.investment_type,
            role=input.role,
            notes=input.notes,
        )

        return Investment(
            investment_id=result["investment_id"],
            idea_id=result["idea_id"],
            investor_id=result["investor_id"],
            cash_amount=float(result.get("cash_amount") or 0),
            sweat_equity_hours=float(result.get("sweat_equity_hours") or 0),
            sweat_equity_value=float(result.get("sweat_equity_value") or 0),
            equity_percentage=float(result.get("equity_percentage") or 0),
            investment_type=result.get("investment_type") or "cash",
            role=result.get("role"),
            status=result.get("status") or "pending",
            notes=result.get("notes"),
            created_at=(
                datetime.fromisoformat(result["created_at"].replace("Z", "+00:00"))
                if isinstance(result["created_at"], str)
                else result["created_at"]
            ),
        )

    @strawberry.mutation
    async def add_investment_contribution(
        self, info: strawberry.Info, input: AddContributionInput
    ) -> bool:
        """Add a contribution to an existing investment"""
        _require_full_account(info.context["db"], info.context["request"])
        from app.services.social.investments import create_investment_service

        service = create_investment_service(info.context["db"])

        await service.add_contribution(
            investment_id=input.investment_id,
            contribution_type=input.contribution_type,
            amount=input.amount,
            hours_worked=input.hours_worked,
            hourly_rate=input.hourly_rate,
            description=input.description,
        )
        return True

    @strawberry.mutation
    async def update_investment_status(
        self, info: strawberry.Info, investment_id: str, status: str
    ) -> bool:
        """Update the status of an investment (pending, confirmed, cancelled)"""
        _require_full_account(info.context["db"], info.context["request"])
        from app.services.social.investments import create_investment_service

        service = create_investment_service(info.context["db"])

        await service.update_investment_status(investment_id, status)
        return True

    @strawberry.mutation
    async def follow_user(self, info: strawberry.Info, followed_id: str) -> FollowResult:
        """Follow a user"""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])

        await service.follow_user(user_id, followed_id)
        return FollowResult(following=True, followed_id=followed_id)

    @strawberry.mutation
    async def unfollow_user(self, info: strawberry.Info, followed_id: str) -> FollowResult:
        """Unfollow a user"""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])

        await service.unfollow_user(user_id, followed_id)
        return FollowResult(following=False, followed_id=followed_id)

    @strawberry.mutation
    async def toggle_follow(self, info: strawberry.Info, followed_id: str) -> FollowResult:
        """Toggle follow status for a user"""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])

        result = await service.toggle_follow(user_id, followed_id)
        return FollowResult(following=result["following"], followed_id=result["followed_id"])

    @strawberry.mutation
    async def upvote_idea(self, info: strawberry.Info, idea_id: str) -> VoteResult:
        """Upvote an idea"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])

        await service.upvote_idea(idea_id, user_id)
        vote_count = await service.get_idea_vote_count(idea_id)
        return VoteResult(voted=True, idea_id=idea_id, vote_count=vote_count)

    @strawberry.mutation
    async def remove_vote(self, info: strawberry.Info, idea_id: str) -> VoteResult:
        """Remove vote from an idea"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])

        await service.remove_vote(idea_id, user_id)
        vote_count = await service.get_idea_vote_count(idea_id)
        return VoteResult(voted=False, idea_id=idea_id, vote_count=vote_count)

    @strawberry.mutation
    async def toggle_upvote(self, info: strawberry.Info, idea_id: str) -> VoteResult:
        """Toggle upvote on an idea"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])

        result = await service.toggle_upvote(idea_id, user_id)
        vote_count = await service.get_idea_vote_count(idea_id)
        return VoteResult(voted=result["voted"], idea_id=idea_id, vote_count=vote_count)

    @strawberry.mutation
    async def toggle_pitch_reel_like(
        self, info: strawberry.Info, reel_id: str, liked: bool
    ) -> PitchReelLikeResult:
        """Like (``liked: true``) or unlike a pitch reel's Open Media clip."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.pitch_reels.service import create_pitch_reel_service

        service = create_pitch_reel_service(info.context["db"])
        try:
            result = await service.set_like(reel_id=reel_id, user_id=user_id, liked=liked)
        except Exception as exc:
            raise Exception(str(exc)) from exc
        return PitchReelLikeResult(
            reel_id=result["reel_id"], liked=result["liked"], like_count=result["like_count"]
        )

    @strawberry.mutation
    async def reshare_pitch_reel(
        self, info: strawberry.Info, reel_id: str, reshared: bool
    ) -> PitchReelShareResult:
        """Reshare (or undo) a pitch reel's clip on the viewer's Open Media profile."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.pitch_reels.service import create_pitch_reel_service

        service = create_pitch_reel_service(info.context["db"])
        try:
            result = await service.set_reshare(reel_id=reel_id, user_id=user_id, reshared=reshared)
        except Exception as exc:
            raise Exception(str(exc)) from exc
        return PitchReelShareResult(
            reel_id=result["reel_id"],
            reshared=result["reshared"],
            share_count=result["share_count"],
        )

    @strawberry.mutation
    async def create_pitch_reel_comment(
        self, info: strawberry.Info, reel_id: str, body: str
    ) -> PitchReelCommentCreateResult:
        """Comment on a pitch reel's Open Media clip."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.pitch_reels.service import create_pitch_reel_service

        service = create_pitch_reel_service(info.context["db"])
        try:
            result = await service.create_comment(reel_id=reel_id, user_id=user_id, body=body)
        except Exception as exc:
            raise Exception(str(exc)) from exc
        return PitchReelCommentCreateResult(comment=map_pitch_reel_comment(result["comment"]))

    @strawberry.mutation
    async def generate_pitch_deck(
        self, info: strawberry.Info, idea_id: str, description: str
    ) -> PitchDeckOutput:
        # Offload the blocking LLM generation to a worker thread so the 10-30s
        # call doesn't stall the event loop; serialize singleton access with
        # _ai_request_lock (same pattern as find_similar_ideas).
        def _generate() -> str:
            with _ai_request_lock:
                return _get_pitch_deck(description)

        pitch_deck = await asyncio.to_thread(_generate)
        idea_row = (
            info.context["db"]
            .table("ideas")
            .select("user_id")
            .eq("idea_id", idea_id)
            .single()
            .execute()
        )
        user_id = idea_row.data["user_id"] if idea_row.data else None
        _update_idea_generated_field(info.context["db"], idea_id, user_id, "pitch_deck", pitch_deck)
        if user_id:
            info.context["db"].table("pitch_decks").upsert(
                {
                    "idea_id": idea_id,
                    "user_id": user_id,
                    "description": pitch_deck,
                },
                on_conflict=["idea_id"],
            ).execute()
        return PitchDeckOutput(pitch_deck=pitch_deck)

    @strawberry.mutation
    async def generate_product_requirements_document(
        self, info: strawberry.Info, idea_id: str, description: str
    ) -> ProductRequirementsDocumentOutput:
        def _generate() -> str:
            with _ai_request_lock:
                return _get_product_requirements_document(description)

        prd = await asyncio.to_thread(_generate)
        idea_row = (
            info.context["db"]
            .table("ideas")
            .select("user_id")
            .eq("idea_id", idea_id)
            .single()
            .execute()
        )
        user_id = idea_row.data["user_id"] if idea_row.data else None
        _update_idea_generated_field(
            info.context["db"], idea_id, user_id, "product_requirements_document", prd
        )
        if user_id:
            info.context["db"].table("product_requirements_documents").upsert(
                {
                    "idea_id": idea_id,
                    "user_id": user_id,
                    "description": prd,
                },
                on_conflict=["idea_id"],
            ).execute()
        return ProductRequirementsDocumentOutput(product_requirements_document=prd)

    @strawberry.mutation
    async def generate_provisional_patent(
        self, info: strawberry.Info, idea_id: str, description: str
    ) -> ProvisionalPatentOutput:
        def _generate() -> str:
            with _ai_request_lock:
                return _get_provisional_patent(description)

        draft = await asyncio.to_thread(_generate)
        idea_row = (
            info.context["db"]
            .table("ideas")
            .select("user_id")
            .eq("idea_id", idea_id)
            .single()
            .execute()
        )
        user_id = idea_row.data["user_id"] if idea_row.data else None
        _update_idea_generated_field(
            info.context["db"], idea_id, user_id, "provisional_patent", draft
        )

        spec_pdf_url = None
        coversheet_pdf_url = None
        try:
            from app.services.ideas.document_generation import generate_patent_pdfs

            spec_pdf_url, coversheet_pdf_url = generate_patent_pdfs(idea_id, user_id, draft)
        except Exception as exc:
            logger.warning(f"[GraphQL] Patent PDF generation failed: {exc}")

        return ProvisionalPatentOutput(
            provisional_patent=draft,
            specification_pdf=spec_pdf_url,
            coversheet_pdf=coversheet_pdf_url,
        )

    @strawberry.mutation
    async def start_guest_session(self, info: strawberry.Info) -> GuestSessionResult:
        """Create a server-backed guest user, set session cookie, return one-time merge secret."""
        if DEMO_MODE:
            raise Exception("Guest sessions are not available in demo mode.")

        import secrets

        from app.auth.current_user import create_session_token
        from app.db.database import get_db_connection
        from app.services.identity.guest_workspace import check_guest_start_rate_limit

        request = info.context["request"]
        client = getattr(request, "client", None)
        try:
            check_guest_start_rate_limit(getattr(client, "host", None) if client else None)
        except Exception:
            raise

        # Two attempts with fresh identifiers each time: this is the landing
        # page's try-before-signup CTA, and production shows intermittent
        # transient DB failures on the first insert (subsequent attempts
        # succeed). A fresh UUID per attempt keeps retries conflict-free; a
        # half-completed first attempt at worst leaves one orphan guest row
        # that the 30-day TTL cleans up.
        last_error: Exception | None = None
        for attempt in range(2):
            guest_id = str(uuid.uuid4())
            merge_secret = secrets.token_urlsafe(32)
            email = f"guest+{guest_id}@guest.manifest"

            try:
                with get_db_connection() as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO users (
                            user_id, email, auth_provider, is_guest,
                            guest_merge_secret, guest_created_at, guest_expires_at, created_at
                        )
                        VALUES (%s, %s, 'guest', TRUE, %s, NOW(), NOW() + INTERVAL '30 days', NOW())
                        """,
                        (guest_id, email.lower(), merge_secret),
                    )
                token = create_session_token(
                    guest_id, email=email.lower(), request=info.context.get("request")
                )
                _set_browser_auth_session(info, token)

                logger.info("[start_guest_session] Created guest user_id=%s", guest_id)
                record_security_event(
                    "guest_session_started",
                    user_id=guest_id,
                    request_ip=_request_ip(info),
                    actor_id=guest_id,
                    actor_type="guest",
                    action="guest_session_start",
                    target_type="user",
                    target_id=guest_id,
                    outcome="success",
                    user_agent=_user_agent(info),
                )
                return GuestSessionResult(
                    user_id=guest_id,
                    email=email,
                    token=token,
                    merge_secret=merge_secret,
                )
            except Exception as e:
                last_error = e
                logger.error(
                    "[start_guest_session] Attempt %s failed (%s): %s",
                    attempt + 1,
                    type(e).__name__,
                    e,
                )

        raise Exception("Could not start guest session") from last_error

    @strawberry.mutation
    async def logout_user(self, info: strawberry.Info) -> bool:
        """Clear auth cookies so the client is fully logged out.

        Session tokens are stateless JWTs, so we don't need to revoke them
        server-side – simply removing the cookie (and any client-side storage)
        is enough to end the session from the browser's perspective.
        """
        request = info.context["request"]
        user_id = get_current_user_id_optional(request)
        current_session_id = get_current_session_id_optional(request)
        if user_id and current_session_id:
            revoke_session(current_session_id, user_id)
            record_security_event(
                "logout",
                user_id=user_id,
                request_ip=_request_ip(info),
                session_id=current_session_id,
                actor_id=user_id,
                actor_type="user",
                action="logout",
                target_type="session",
                target_id=str(current_session_id) if current_session_id else None,
                outcome="success",
                user_agent=_user_agent(info),
            )
        response = info.context["response"]
        clear_auth_cookies(response, request)
        return True

    @strawberry.mutation
    async def revoke_account_session(self, info: strawberry.Info, session_id: str) -> bool:
        user_id = get_current_user_id(info.context["request"])
        current_session_id = get_current_session_id_optional(info.context["request"])
        if current_session_id and session_id == current_session_id:
            raise Exception("Use logout to end the current session.")
        revoked = revoke_session(session_id, user_id)
        if revoked:
            record_security_event(
                "session_revoked",
                user_id=user_id,
                request_ip=_request_ip(info),
                actor_id=user_id,
                actor_type="user",
                action="session_revoke",
                target_type="session",
                target_id=str(session_id),
                outcome="success",
                user_agent=_user_agent(info),
                metadata={"target_session_id": session_id},
            )
        return revoked

    @strawberry.mutation
    async def revoke_other_account_sessions(self, info: strawberry.Info) -> int:
        user_id = get_current_user_id(info.context["request"])
        current_session_id = get_current_session_id_optional(info.context["request"])
        revoked = revoke_all_other_sessions(user_id, current_session_id)
        record_security_event(
            "other_sessions_revoked",
            user_id=user_id,
            request_ip=_request_ip(info),
            session_id=current_session_id,
            actor_id=user_id,
            actor_type="user",
            action="session_revoke_others",
            target_type="user",
            target_id=user_id,
            outcome="success",
            user_agent=_user_agent(info),
            metadata={"revoked_count": revoked},
        )
        return revoked

    @strawberry.mutation
    async def request_account_deletion(
        self,
        info: strawberry.Info,
        confirm_email: str,
    ) -> bool:
        user_id = _require_full_account(info.context["db"], info.context["request"])
        user_row = _load_user_auth_record(user_id)
        if not user_row:
            raise Exception("User not found.")
        expected_email = str(user_row.get("email") or "").strip().lower()
        if (confirm_email or "").strip().lower() != expected_email:
            raise Exception("Enter your account email to confirm deletion.")

        from app.db.database import get_db_connection

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET deletion_requested_at = NOW() WHERE user_id = %s",
                    (user_id,),
                )
            conn.commit()
        revoke_all_other_sessions(user_id, None)
        clear_auth_cookies(info.context["response"], info.context.get("request"))
        record_security_event(
            "account_deletion_requested",
            user_id=user_id,
            request_ip=_request_ip(info),
            action="account_deletion_request",
            target_type="user",
            target_id=user_id,
            outcome="success",
            user_agent=_user_agent(info),
        )
        return True

    @strawberry.mutation
    async def run_background_tasks(
        self, info: strawberry.Info, idea_id: str, description: str
    ) -> bool:
        """Trigger asynchronous background tasks that were previously exposed via REST (POST /api/idea/{idea_id}/background-tasks)."""
        return _start_background_generation(idea_id, description)

    @strawberry.mutation
    async def enqueue_background_tasks(
        self,
        info: strawberry.Info,
        idea_id: str,
        document_types: list[str],
        idempotency_key: str | None = None,
    ) -> EnqueueJobResult:
        """Enqueue document generation as a durable job and return immediately
        (Phase 3). The dedicated worker drains the queue; poll ``generationJob``
        for status. Unlike the legacy fire-and-forget ``runBackgroundTasks``,
        the work survives a process restart and is deduplicated per
        ``idempotencyKey``. Returns the existing job if one is already in flight
        for that key.
        """
        user_id = get_current_user_id(info.context["request"])
        job = job_service.create_job(
            info.context["db"],
            user_id=user_id,
            idea_id=idea_id,
            document_types=document_types,
            idempotency_key=idempotency_key,
        )
        return EnqueueJobResult(job_id=str(job["id"]), status=str(job["status"]))

    @strawberry.mutation
    async def export_ideas(self, info: strawberry.Info, format: str = "json") -> ExportResult:
        """Export all user's ideas in the specified format (json, csv, markdown).

        Bulk export of user data is a sensitive action (full data
        exfiltration vector if a session token is stolen) so we require
        recent auth — fresh login OR live step-up verification — before
        producing the archive.
        """
        import base64

        from app.auth.current_user import get_current_session_id_optional
        from app.security.step_up import (
            DEFAULT_TTL_SECONDS,
            _recent_login_satisfies,
            has_recent_step_up,
        )
        from app.services.ideas.import_export import ImportExportService

        request = info.context["request"]
        user_id = get_current_user_id(request)
        if not _recent_login_satisfies(request, DEFAULT_TTL_SECONDS):
            session_id = get_current_session_id_optional(request)
            if not has_recent_step_up(user_id, session_id, max_age_seconds=DEFAULT_TTL_SECONDS):
                raise Exception("Re-authentication required for bulk export (step-up MFA needed).")

        # Fetch all ideas for the user
        response = info.context["db"].table("ideas").select("*").eq("user_id", user_id).execute()
        ideas = response.data if response.data else []

        if not ideas:
            raise Exception("No ideas found to export")

        service = ImportExportService()
        format_lower = format.lower()

        if format_lower == "json":
            content = service.export_to_json(ideas)
            filename = f"manifest_ideas_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        elif format_lower == "csv":
            content = service.export_to_csv(ideas)
            filename = f"manifest_ideas_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        elif format_lower == "markdown":
            content = service.export_to_markdown(ideas)
            filename = f"manifest_ideas_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.md"
        else:
            raise Exception(f"Unsupported export format: {format}")

        # Encode content as base64 for safe transmission
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        return ExportResult(content=content_b64, format=format_lower, filename=filename)

    @strawberry.mutation
    async def import_ideas(
        self, info: strawberry.Info, file_content: str, file_format: str, filename: str
    ) -> ImportResult:
        """Import startup ideas from note exports and backups."""
        import base64

        from app.services.ideas.import_export import ImportExportService

        user_id = get_current_user_id(info.context["request"])
        service = ImportExportService()

        imported_count = 0
        skipped_count = 0
        errors = []

        try:
            file_bytes = base64.b64decode(file_content)
            prepared_import = service.prepare_import(file_bytes, file_format, filename)
            imported_ideas = prepared_import["ideas"]
            skipped_count += prepared_import["skipped_non_ideas"]
            errors.extend(prepared_import["warnings"])

            existing_response = (
                info.context["db"]
                .table("ideas")
                .select("title, description")
                .eq("user_id", user_id)
                .execute()
            )
            existing_ideas = (
                existing_response.data if existing_response and existing_response.data else []
            )
            existing_fingerprints = {
                service.idea_fingerprint(existing_idea) for existing_idea in existing_ideas
            }

            # Insert imported ideas into database
            for idea_data in imported_ideas:
                try:
                    fingerprint = service.idea_fingerprint(idea_data)
                    if fingerprint in existing_fingerprints:
                        skipped_count += 1
                        continue

                    idea_id = str(uuid.uuid4())
                    data = {
                        "idea_id": idea_id,
                        "title": idea_data.get("title", "Imported Idea"),
                        "description": idea_data.get("description", ""),
                        "summary": idea_data.get("summary", ""),
                        "tags": idea_data.get("tags", ""),
                        "user_id": user_id,
                        "created_at": datetime.utcnow().isoformat(),
                    }
                    response = info.context["db"].table("ideas").insert(data).execute()
                    if response.data:
                        imported_count += 1
                        existing_fingerprints.add(fingerprint)
                    else:
                        skipped_count += 1
                except Exception as e:
                    skipped_count += 1
                    errors.append(
                        f"Failed to import '{idea_data.get('title', 'Untitled')}': {str(e)}"
                    )

            return ImportResult(
                imported_count=imported_count, skipped_count=skipped_count, errors=errors
            )
        except Exception as e:
            logger.error(f"Error importing ideas: {e}")
            raise Exception(f"Import failed: {str(e)}") from e

    # ==================== MESSAGING MUTATIONS ====================

    @strawberry.mutation
    async def start_conversation(
        self, info: strawberry.Info, other_user_id: str, idea_id: str | None = None
    ) -> Conversation:
        """Open (or reuse) an Open Media conversation with an idea's founder.

        ``otherUserId`` is the founder's Manifest user id; the founder must have
        linked Open Media. With ``ideaId`` the idea must be published and owned
        by that founder; the conversation is tagged with the idea.
        """
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.integrations.open_media import identity as om_identity
        from app.services.integrations.open_media import messaging as om_messaging
        from app.services.social.founder_contact import (
            FOUNDER_NOT_LINKED_MESSAGE,
            founder_handle_for_idea,
        )

        db = info.context["db"]
        context = None
        if idea_id:
            idea_owner = (
                db.table("ideas").select("user_id").eq("idea_id", idea_id).single().execute()
            )
            owner_row = idea_owner.data if isinstance(idea_owner.data, dict) else {}
            if str(owner_row.get("user_id") or "") != str(other_user_id):
                raise Exception("That conversation must be with the founder of this idea.")
            try:
                handle, title = await asyncio.to_thread(
                    founder_handle_for_idea, db, idea_id, user_id
                )
            except ValueError as exc:
                raise Exception(str(exc)) from exc
            context = om_messaging.idea_context(idea_id, title)
        else:
            handle = await asyncio.to_thread(om_identity.handle_for_user, other_user_id)
            if not handle:
                raise Exception(FOUNDER_NOT_LINKED_MESSAGE)

        conv = await call_open_media(
            om_messaging.start_conversation, user_id, handle=handle, context=context
        )
        return map_conversation(conv)

    @strawberry.mutation
    async def send_message(
        self,
        info: strawberry.Info,
        conversation_id: str,
        content: str,
        client_id: str | None = None,
    ) -> Message:
        """Send a message in an Open Media conversation (``clientId`` makes retries land once)."""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.integrations.open_media import messaging as om_messaging

        msg = await call_open_media(
            om_messaging.send_message, user_id, conversation_id, body=content, client_id=client_id
        )
        mapped = map_message(msg, None)
        mapped.is_mine = True
        return mapped

    @strawberry.mutation
    async def mark_conversation_read(self, info: strawberry.Info, conversation_id: str) -> bool:
        """Mark an Open Media conversation as read."""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.integrations.open_media import messaging as om_messaging

        return bool(await call_open_media(om_messaging.mark_read, user_id, conversation_id))

    # ==================== COLLABORATION MUTATIONS ====================

    @strawberry.mutation
    async def invite_collaborator(
        self, info: strawberry.Info, input: "InviteCollaboratorInput"
    ) -> "InviteResult":
        """Invite a user to collaborate on an idea"""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        try:
            await service.invite_collaborator(
                idea_id=input.idea_id,
                inviter_id=user_id,
                invitee_email=input.email,
                role=input.role,
            )
            return InviteResult(success=True, message=f"Invitation sent to {input.email}")
        except ValueError as e:
            return InviteResult(success=False, message=str(e))
        except PermissionError as e:
            return InviteResult(success=False, message=str(e))
        except Exception as e:
            return InviteResult(success=False, message=f"Failed to send invitation: {str(e)}")

    @strawberry.mutation
    async def respond_to_invitation(
        self, info: strawberry.Info, idea_id: str, accept: bool
    ) -> bool:
        """Accept or decline a collaboration invitation"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        await service.respond_to_invitation(idea_id, user_id, accept)
        return True

    @strawberry.mutation
    async def update_collaborator_role(
        self, info: strawberry.Info, idea_id: str, target_user_id: str, new_role: str
    ) -> bool:
        """Update a collaborator's role"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        await service.update_collaborator_role(idea_id, user_id, target_user_id, new_role)
        return True

    @strawberry.mutation
    async def remove_collaborator(
        self, info: strawberry.Info, idea_id: str, target_user_id: str
    ) -> bool:
        """Remove a collaborator from an idea"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        return await service.remove_collaborator(idea_id, user_id, target_user_id)

    @strawberry.mutation
    async def create_idea_version(
        self, info: strawberry.Info, idea_id: str, change_summary: str | None = None
    ) -> "IdeaVersion":
        """Create a new version snapshot of an idea"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        version_data = await service.create_version(
            idea_id, user_id, change_summary, version_kind=VERSION_KIND_MANUAL
        )

        return IdeaVersion(
            version_id=version_data["version_id"],
            idea_id=version_data["idea_id"],
            version_number=version_data["version_number"],
            title=version_data.get("title"),
            description=version_data.get("description"),
            created_by=version_data["created_by"],
            created_at=(
                datetime.fromisoformat(version_data["created_at"].replace("Z", "+00:00"))
                if isinstance(version_data["created_at"], str)
                else version_data["created_at"]
            ),
            change_summary=version_data.get("change_summary"),
            version_kind=version_data.get("version_kind") or VERSION_KIND_MANUAL,
        )

    @strawberry.mutation
    async def restore_idea_version(
        self, info: strawberry.Info, idea_id: str, version_id: str
    ) -> bool:
        """Restore an idea to a previous version"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        await service.restore_version(idea_id, version_id, user_id)
        return True

    @strawberry.mutation
    async def admin_set_user_role(
        self, info: strawberry.Info, target_user_id: str, role: str
    ) -> bool:
        """Admin: change a user's RBAC role.

        Required permission: ``admin.users.write`` (enforced by the
        default-deny extension via FIELD_PERMISSIONS).

        Side effects (SEC-031):
        * Persists the new role on ``users.role``.
        * Forcibly revokes every active session for the target user so
          the new permission grant takes effect immediately and any
          ongoing tokens stop trusting the old role.
        * Emits ``role_changed`` to the security audit log.
        """
        from app.db.database import get_db_connection
        from app.security.permissions import ASSIGNABLE_ROLES, resolve_principal
        from app.security.step_up import (
            DEFAULT_TTL_SECONDS,
            _recent_login_satisfies,
            has_recent_step_up,
        )
        from app.services.compliance.security_audit import record_security_event

        request = info.context["request"]
        actor_id = get_current_user_id(request)
        actor = resolve_principal(actor_id)
        if not actor.has("admin.users.write"):
            raise Exception("admin.users.write permission required.")
        # SEC-026: privileged admin mutations require a fresh identity
        # proof. A recent login (auth_iat) OR a live step-up record both
        # satisfy this — see require_recent_auth in app.security.step_up.
        actor_session_id = get_current_session_id_optional(request)
        if not (
            _recent_login_satisfies(request, DEFAULT_TTL_SECONDS)
            or has_recent_step_up(actor_id, actor_session_id, max_age_seconds=DEFAULT_TTL_SECONDS)
        ):
            raise Exception(
                "Re-authentication required: complete a step-up at "
                "/api/auth/step-up before changing roles."
            )
        new_role = (role or "").strip().lower()
        if new_role not in ASSIGNABLE_ROLES:
            raise Exception(
                f"Role '{role}' is not assignable. Choose one of: "
                + ", ".join(sorted(ASSIGNABLE_ROLES))
            )
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET role = %s WHERE user_id = %s",
                (new_role, target_user_id),
            )
            changed = cur.rowcount > 0
            conn.commit()
        if not changed:
            raise Exception("Target user not found.")
        revoked = revoke_all_sessions(target_user_id)
        record_security_event(
            "role_changed",
            user_id=target_user_id,
            request_ip=_request_ip(info),
            actor_id=actor_id,
            actor_type="user",
            action="role_change",
            target_type="user",
            target_id=target_user_id,
            outcome="success",
            user_agent=_user_agent(info),
            metadata={
                "actor_user_id": actor_id,
                "new_role": new_role,
                "sessions_revoked": revoked,
            },
        )
        # Detector: privilege-escalation watch (pages on grants to admin).
        from app.security.audit_detections import detect_privilege_escalation

        detect_privilege_escalation(
            actor_user_id=actor_id,
            target_user_id=target_user_id,
            new_role=new_role,
        )
        return True

    @strawberry.mutation
    async def start_idea_qualification(
        self, info: strawberry.Info, initial_idea_text: str
    ) -> IdeaQualificationSession:
        from app.services.ai import cost_tracking as cost_tracking_service
        from app.services.ai import idea_qualification as qs

        user_id = get_current_user_id(info.context["request"])
        try:
            cost_tracking_service.enforce_cap_or_raise(
                db=info.context["db"],
                user_id=user_id,
                agent_kind="qualification",
            )
        except cost_tracking_service.CapBlockedError as exc:
            raise Exception(str(exc)) from exc
        try:
            row = qs.start_session(
                db=info.context["db"],
                user_id=user_id,
                initial_idea_text=initial_idea_text,
            )
        except qs.QualificationError as exc:
            raise Exception(str(exc)) from exc
        return _map_qualification_session(row)

    @strawberry.mutation
    async def continue_idea_qualification(
        self, info: strawberry.Info, session_id: str, user_message: str
    ) -> IdeaQualificationSession:
        from app.managers.manifest_manager import manifest_manager
        from app.services.ai import cost_tracking as cost_tracking_service
        from app.services.ai import idea_qualification as qs

        user_id = get_current_user_id(info.context["request"])
        try:
            cost_tracking_service.enforce_cap_or_raise(
                db=info.context["db"],
                user_id=user_id,
                agent_kind="qualification",
            )
        except cost_tracking_service.CapBlockedError as exc:
            raise Exception(str(exc)) from exc
        try:
            row = qs.continue_session(
                db=info.context["db"],
                ai_layer=manifest_manager.ai_layer,
                session_id=session_id,
                user_id=user_id,
                user_message=user_message,
            )
        except qs.QualificationError as exc:
            raise Exception(str(exc)) from exc
        return _map_qualification_session(row)

    @strawberry.mutation
    async def set_variable_cost_cap(
        self,
        info: strawberry.Info,
        monthly_cap_usd: float | None = None,
        paused: bool | None = None,
    ) -> UserCostLimits:
        from app.services.ai import cost_tracking as cost_tracking_service

        user_id = get_current_user_id(info.context["request"])
        row = cost_tracking_service.set_user_cost_limits(
            db=info.context["db"],
            user_id=user_id,
            monthly_variable_cap_usd=monthly_cap_usd,
            paused=paused,
        )
        return UserCostLimits(
            monthly_variable_cap_usd=float(row.get("monthly_variable_cap_usd") or 0),
            paused=bool(row.get("paused") or False),
            base_subscription_usd=float(row.get("base_subscription_usd") or 0),
            currency=str(row.get("currency") or "USD"),
        )

    @strawberry.mutation
    async def regenerate_bmc_section(
        self, info: strawberry.Info, idea_id: str, section_name: str
    ) -> BmcSection:
        from app.managers.manifest_manager import manifest_manager
        from app.services.ai import cost_tracking as cost_tracking_service
        from app.services.canvas import orchestrator as bmc

        user_id = get_current_user_id(info.context["request"])
        ownership = (
            info.context["db"]
            .table("ideas")
            .select("idea_id")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not (ownership.data or []):
            raise Exception("Idea not found or you don't have permission to edit it")
        try:
            cost_tracking_service.enforce_cap_or_raise(
                db=info.context["db"],
                user_id=user_id,
                agent_kind=f"bmc_{section_name}",
            )
        except cost_tracking_service.CapBlockedError as exc:
            raise Exception(str(exc)) from exc
        try:
            row = bmc.regenerate_section(
                db=info.context["db"],
                ai_layer=manifest_manager.ai_layer,
                user_id=user_id,
                idea_id=idea_id,
                section_name=section_name,
            )
        except bmc.BmcSectionError as exc:
            raise Exception(str(exc)) from exc
        return _map_bmc_section(row)

    @strawberry.mutation
    async def regenerate_all_bmc_sections(
        self, info: strawberry.Info, idea_id: str
    ) -> list[BmcSection]:
        from app.managers.manifest_manager import manifest_manager
        from app.services.ai import cost_tracking as cost_tracking_service
        from app.services.canvas import orchestrator as bmc

        user_id = get_current_user_id(info.context["request"])
        ownership = (
            info.context["db"]
            .table("ideas")
            .select("idea_id")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not (ownership.data or []):
            raise Exception("Idea not found or you don't have permission to edit it")
        try:
            # 9 sections × ~$0.004 each — pass the full estimated cost so
            # the guard rejects "regenerate all" requests that one
            # section's estimate alone would have permitted.
            cost_tracking_service.enforce_cap_or_raise(
                db=info.context["db"],
                user_id=user_id,
                agent_kind="bmc_all",
                est_cost_usd=9
                * cost_tracking_service.ESTIMATED_COST_USD_PER_RUN.get(
                    "bmc_customer_segments", 0.004
                ),
            )
        except cost_tracking_service.CapBlockedError as exc:
            raise Exception(str(exc)) from exc
        try:
            rows = bmc.regenerate_all_sections(
                db=info.context["db"],
                ai_layer=manifest_manager.ai_layer,
                user_id=user_id,
                idea_id=idea_id,
            )
        except bmc.BmcSectionError as exc:
            raise Exception(str(exc)) from exc
        return [_map_bmc_section(r) for r in rows]

    @strawberry.mutation
    async def run_partner_discovery(
        self,
        info: strawberry.Info,
        idea_id: str,
        max_candidates: int | None = None,
    ) -> list[PartnerCandidate]:
        """Run the partner-discovery agent for an owned idea.

        Returns the candidates persisted on this run (ranked).
        """
        from app.managers.manifest_manager import manifest_manager
        from app.services.ai import cost_tracking as cost_tracking_service
        from app.services.ideas import partner_discovery as pd

        user_id = get_current_user_id(info.context["request"])
        ownership = (
            info.context["db"]
            .table("ideas")
            .select("idea_id")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not (ownership.data or []):
            raise Exception("Idea not found or you don't have permission to edit it")
        try:
            cost_tracking_service.enforce_cap_or_raise(
                db=info.context["db"],
                user_id=user_id,
                agent_kind="partner_discovery",
            )
        except cost_tracking_service.CapBlockedError as exc:
            raise Exception(str(exc)) from exc
        try:
            rows = pd.run_discovery(
                db=info.context["db"],
                ai_layer=manifest_manager.ai_layer,
                user_id=user_id,
                idea_id=idea_id,
                max_candidates=max_candidates or pd.DEFAULT_MAX_CANDIDATES,
            )
        except pd.PartnerDiscoveryError as exc:
            raise Exception(str(exc)) from exc
        return [_map_partner_candidate(r) for r in rows]

    @strawberry.mutation
    async def approve_partner_candidate(
        self,
        info: strawberry.Info,
        candidate_id: str,
        approved: bool = True,
    ) -> PartnerCandidate:
        """Flip the internal approval flag on a partner candidate.

        v1 SAFETY: this is internal-only state. Approving a candidate
        does NOT initiate outreach, share data, or call any third-party
        API. A future outreach agent will read approved=true rows.
        """
        from app.services.ideas import partner_discovery as pd

        user_id = get_current_user_id(info.context["request"])
        # Verify the candidate's idea is owned by the caller.
        candidate_response = (
            info.context["db"]
            .table("partner_candidates")
            .select("id, idea_id")
            .eq("id", candidate_id)
            .limit(1)
            .execute()
        )
        candidate_rows = candidate_response.data or []
        if not candidate_rows:
            raise Exception("Partner candidate not found")
        idea_id = candidate_rows[0].get("idea_id")
        ownership = (
            info.context["db"]
            .table("ideas")
            .select("idea_id")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not (ownership.data or []):
            raise Exception("Partner candidate not found")
        try:
            row = pd.approve_candidate(
                db=info.context["db"],
                user_id=user_id,
                candidate_id=candidate_id,
                approved=approved,
            )
        except pd.PartnerDiscoveryError as exc:
            raise Exception(str(exc)) from exc
        return _map_partner_candidate(row)

    @strawberry.mutation
    async def admin_run_voice_test_case(
        self,
        info: strawberry.Info,
        scenario: str,
        emotion: str,
        persona: str | None = None,
    ) -> VoiceTestRun:
        """Run one end-to-end voice test (simulator → executor → evaluator).

        The executor is the deterministic LLM stub in v1 (does NOT
        touch production voice_agent_service). Each phase opens its
        own cost-tracked agent_run so the spend shows up on the
        operator's billing dashboard.
        """
        from app.managers.manifest_manager import manifest_manager
        from app.services.voice import evaluation as vts

        user_id = get_current_user_id(info.context["request"])
        try:
            row = vts.run_test_case_end_to_end(
                db=info.context["db"],
                ai_layer=manifest_manager.ai_layer,
                triggered_by_user_id=user_id,
                scenario=scenario,
                emotion=emotion,
                persona=persona,
            )
        except vts.VoiceTestingError as exc:
            raise Exception(str(exc)) from exc
        return _map_voice_test_run(row)


# ==================== MESSAGING TYPES ====================


@strawberry.type
class IdeaOwner:
    user_id: str
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    bio: str | None = None
    profile_picture_url: str | None = None
    idea_id: str
    idea_title: str | None = None
    is_published: bool = False
    can_message: bool = False
    open_media_handle: str | None = None


# ==================== COLLABORATION TYPES ====================


@strawberry.type
class Collaborator:
    collaborator_id: str | None
    idea_id: str
    user_id: str
    role: str
    status: str
    user_email: str | None = None
    user_name: str | None = None
    user_avatar: str | None = None
    invited_at: datetime | None = None
    accepted_at: datetime | None = None


@strawberry.type
class IdeaVersion:
    version_id: str
    idea_id: str
    version_number: int
    title: str | None = None
    description: str | None = None
    created_by: str
    created_at: datetime
    change_summary: str | None = None
    creator_name: str | None = None
    creator_avatar: str | None = None
    version_kind: str | None = None


@strawberry.type
class CollaborationInvitation:
    collaborator_id: str
    idea_id: str
    role: str
    status: str
    idea_title: str | None = None
    idea_description: str | None = None
    inviter_name: str | None = None
    invited_at: datetime | None = None


@strawberry.type
class SharedIdea:
    idea_id: str
    title: str
    description: str | None = None
    user_role: str
    created_at: datetime


@strawberry.type
class AccessCheckResult:
    has_access: bool
    role: str | None = None


@strawberry.type
class InviteResult:
    success: bool
    message: str


@strawberry.input
class InviteCollaboratorInput:
    idea_id: str
    email: str
    role: str = "viewer"


from app.security.permissions import resolve_principal
from strawberry.extensions import SchemaExtension


class _DefaultDenyAuthExtension(SchemaExtension):
    """Default-deny authorization for every top-level Query/Mutation field.

    Strawberry doesn't have a notion of a global default permission, so we
    intercept every top-level resolve call here. A resolver listed in
    ``PUBLIC_FIELDS`` is allowed unauthenticated; anything else requires a
    valid session cookie / bearer token. Fields listed in
    ``FIELD_PERMISSIONS`` additionally require the named permission(s)
    from the RBAC catalog (`app.security.permissions`).

    The allowlists are intentionally explicit — every entry here was
    reviewed as an anonymous-safe or scope-bound operation. New fields
    default to authenticated; new sensitive fields should be added to
    ``FIELD_PERMISSIONS`` so they default-deny by RBAC, not just by auth.
    """

    PUBLIC_FIELDS = {
        # guest try-before-signup (signing in goes through /api/auth/open-media/*)
        "start_guest_session",
        "startGuestSession",
        "submit_contact_form",
        "submitContactForm",
        "submit_survey",
        "submitSurvey",
        # platform catalog (static skill pick-list for onboarding / idea forms)
        "available_skills",
        "availableSkills",
        # introspection / playground utility
        "__schema",
        "__type",
        "__typename",
    }

    # Map of top-level field name (snake_case and camelCase forms accepted
    # by Strawberry) -> required permission from the RBAC catalog. A
    # principal must hold the listed permission, or we 403 the field
    # before the resolver runs.
    FIELD_PERMISSIONS = {
        # --- Idea CRUD ---
        "ideas": "ideas.read",
        "idea": "ideas.read",
        "generation_job": "ideas.read",
        "generationJob": "ideas.read",
        "search_ideas": "ideas.read",
        "searchIdeas": "ideas.read",
        "shared_ideas": "ideas.read",
        "sharedIdeas": "ideas.read",
        "create_idea": "ideas.write",
        "createIdea": "ideas.write",
        "update_idea": "ideas.write",
        "updateIdea": "ideas.write",
        "delete_idea": "ideas.write",
        "deleteIdea": "ideas.write",
        "import_ideas": "ideas.write",
        "importIdeas": "ideas.write",
        "export_ideas": "ideas.read",
        "exportIdeas": "ideas.read",
        # --- Documents ---
        "documents": "documents.read",
        "create_document": "documents.write",
        "createDocument": "documents.write",
        "update_document": "documents.write",
        "updateDocument": "documents.write",
        "delete_document": "documents.write",
        "deleteDocument": "documents.write",
        # --- Account & sessions (self-service; 'sessions.manage' covers it) ---
        "account_sessions": "sessions.manage",
        "accountSessions": "sessions.manage",
        "revoke_account_session": "sessions.manage",
        "revokeAccountSession": "sessions.manage",
        "revoke_other_account_sessions": "sessions.manage",
        "revokeOtherAccountSessions": "sessions.manage",
        # --- MFA self-service ---
        # --- API key management ---
        "api_keys": "api_keys.manage",
        "apiKeys": "api_keys.manage",
        # --- Admin surfaces ---
        "admin_users": "admin.users.read",
        "adminUsers": "admin.users.read",
        "admin_set_user_role": "admin.users.write",
        "adminSetUserRole": "admin.users.write",
        "admin_disable_user": "admin.users.write",
        "adminDisableUser": "admin.users.write",
        "admin_clear_lockout": "admin.lockouts.clear",
        "adminClearLockout": "admin.lockouts.clear",
        "admin_audit_events": "admin.audit.read",
        "adminAuditEvents": "admin.audit.read",
        "sso_tenant_configs": "admin.sso.manage",
        "ssoTenantConfigs": "admin.sso.manage",
        # --- Account / profile / self-service ---
        "account": "account.read",
        "me": "account.read",
        "ai_key_status": "account.read",
        "aiKeyStatus": "account.read",
        "profile": "account.read",
        "privacy_status": "account.read",
        "privacyStatus": "account.read",
        "user_followers": "account.read",
        "userFollowers": "account.read",
        "user_following": "account.read",
        "userFollowing": "account.read",
        "user_social_stats": "account.read",
        "userSocialStats": "account.read",
        "my_sessions": "sessions.manage",
        "mySessions": "sessions.manage",
        "update_account": "account.write",
        "updateAccount": "account.write",
        "save_openai_api_key": "account.write",
        "saveOpenaiApiKey": "account.write",
        "remove_openai_api_key": "account.write",
        "removeOpenaiApiKey": "account.write",
        "request_account_deletion": "account.write",
        "requestAccountDeletion": "account.write",
        "logout_user": "account.read",
        "logoutUser": "account.read",
        "follow_user": "account.write",
        "followUser": "account.write",
        "unfollow_user": "account.write",
        "unfollowUser": "account.write",
        "toggle_follow": "account.write",
        "toggleFollow": "account.write",
        # --- Idea sub-features (votes, publish, versions, search, similarity) ---
        "find_similar_ideas": "ideas.read",
        "findSimilarIdeas": "ideas.read",
        "check_idea_access": "ideas.read",
        "checkIdeaAccess": "ideas.read",
        "idea_owner": "ideas.read",
        "ideaOwner": "ideas.read",
        "idea_versions": "ideas.read",
        "ideaVersions": "ideas.read",
        "my_shared_ideas": "ideas.read",
        "mySharedIdeas": "ideas.read",
        "universal_search": "ideas.read",
        "universalSearch": "ideas.read",
        "available_skills": "account.read",
        "availableSkills": "account.read",
        "survey_insights": "ideas.read",
        "surveyInsights": "ideas.read",
        "toggle_upvote": "ideas.write",
        "toggleUpvote": "ideas.write",
        "upvote_idea": "ideas.write",
        "upvoteIdea": "ideas.write",
        "remove_vote": "ideas.write",
        "removeVote": "ideas.write",
        "toggle_publish_idea": "ideas.write",
        "togglePublishIdea": "ideas.write",
        "create_idea_version": "ideas.write",
        "createIdeaVersion": "ideas.write",
        "restore_idea_version": "ideas.write",
        "restoreIdeaVersion": "ideas.write",
        "run_background_tasks": "ideas.write",
        "runBackgroundTasks": "ideas.write",
        "enqueue_background_tasks": "ideas.write",
        "enqueueBackgroundTasks": "ideas.write",
        # --- Idea qualification (multi-turn pre-build agent) ---
        "idea_qualification_session": "ideas.read",
        "ideaQualificationSession": "ideas.read",
        "my_idea_qualification_sessions": "ideas.read",
        "myIdeaQualificationSessions": "ideas.read",
        "start_idea_qualification": "ideas.write",
        "startIdeaQualification": "ideas.write",
        "continue_idea_qualification": "ideas.write",
        "continueIdeaQualification": "ideas.write",
        # --- Cost tracking + billing dashboard ---
        "my_cost_dashboard": "account.read",
        "myCostDashboard": "account.read",
        "my_agent_runs": "account.read",
        "myAgentRuns": "account.read",
        "my_cost_preflight": "account.read",
        "myCostPreflight": "account.read",
        "set_variable_cost_cap": "account.write",
        "setVariableCostCap": "account.write",
        # --- BMC per-section agents ---
        "bmc_sections": "ideas.read",
        "bmcSections": "ideas.read",
        "regenerate_bmc_section": "ideas.write",
        "regenerateBmcSection": "ideas.write",
        "regenerate_all_bmc_sections": "ideas.write",
        "regenerateAllBmcSections": "ideas.write",
        # --- Partner discovery agent (Key Partners helper) ---
        "partner_candidates": "ideas.read",
        "partnerCandidates": "ideas.read",
        "run_partner_discovery": "ideas.write",
        "runPartnerDiscovery": "ideas.write",
        "approve_partner_candidate": "ideas.write",
        "approvePartnerCandidate": "ideas.write",
        # --- Admin cost + agent run + production-test analytics ---
        "admin_cost_overview": "admin.cost.read",
        "adminCostOverview": "admin.cost.read",
        "admin_agent_runs": "admin.cost.read",
        "adminAgentRuns": "admin.cost.read",
        "admin_production_test_stats": "admin.cost.read",
        "adminProductionTestStats": "admin.cost.read",
        # --- Voice-platform testing (admin-only) ---
        "admin_voice_test_runs": "admin.voice_testing.read",
        "adminVoiceTestRuns": "admin.voice_testing.read",
        "admin_voice_test_stats": "admin.voice_testing.read",
        "adminVoiceTestStats": "admin.voice_testing.read",
        "admin_run_voice_test_case": "admin.voice_testing.write",
        "adminRunVoiceTestCase": "admin.voice_testing.write",
        # --- Collaboration / invites ---
        "idea_collaborators": "ideas.read",
        "ideaCollaborators": "ideas.read",
        "my_collaboration_invitations": "ideas.read",
        "myCollaborationInvitations": "ideas.read",
        "invite_collaborator": "ideas.write",
        "inviteCollaborator": "ideas.write",
        "remove_collaborator": "ideas.write",
        "removeCollaborator": "ideas.write",
        "update_collaborator_role": "ideas.write",
        "updateCollaboratorRole": "ideas.write",
        "respond_to_invitation": "ideas.write",
        "respondToInvitation": "ideas.write",
        # --- Investments / cap table / sweat equity ---
        "idea_cap_table": "ideas.read",
        "ideaCapTable": "ideas.read",
        "idea_investments": "ideas.read",
        "ideaInvestments": "ideas.read",
        "my_portfolio": "ideas.read",
        "myPortfolio": "ideas.read",
        "calculate_sweat_equity": "ideas.read",
        "calculateSweatEquity": "ideas.read",
        "create_investment": "ideas.write",
        "createInvestment": "ideas.write",
        "add_investment_contribution": "ideas.write",
        "addInvestmentContribution": "ideas.write",
        "update_investment_status": "ideas.write",
        "updateInvestmentStatus": "ideas.write",
        # --- Generated documents (pitch deck / PRD / provisional patent) ---
        "pitch_deck": "documents.read",
        "pitchDeck": "documents.read",
        "generate_pitch_deck": "documents.write",
        "generatePitchDeck": "documents.write",
        "product_requirements_document": "documents.read",
        "productRequirementsDocument": "documents.read",
        "generate_product_requirements_document": "documents.write",
        "generateProductRequirementsDocument": "documents.write",
        "provisional_patent": "documents.read",
        "provisionalPatent": "documents.read",
        "generate_provisional_patent": "documents.write",
        "generateProvisionalPatent": "documents.write",
        "patents": "documents.read",
        # --- Pitch reels (public-feed social surfaces still need auth) ---
        "pitch_reels_feed": "ideas.read",
        "pitchReelsFeed": "ideas.read",
        "pitch_reel_comments": "ideas.read",
        "pitchReelComments": "ideas.read",
        "create_pitch_reel_comment": "ideas.write",
        "createPitchReelComment": "ideas.write",
        "reshare_pitch_reel": "ideas.write",
        "resharePitchReel": "ideas.write",
        "toggle_pitch_reel_like": "ideas.write",
        "togglePitchReelLike": "ideas.write",
        # --- Conversations / DMs ---
        "my_conversations": "account.read",
        "myConversations": "account.read",
        "conversation_messages": "account.read",
        "conversationMessages": "account.read",
        "unread_message_count": "account.read",
        "unreadMessageCount": "account.read",
        "send_message": "account.write",
        "sendMessage": "account.write",
        "start_conversation": "account.write",
        "startConversation": "account.write",
        "mark_conversation_read": "account.write",
        "markConversationRead": "account.write",
        # --- Open Media account link (messages and pitch shorts) ---
        "open_media_link": "account.read",
        "openMediaLink": "account.read",
        "open_media_realtime_token": "account.read",
        "openMediaRealtimeToken": "account.read",
        # --- Third-party integrations (per-user OAuth links) ---
        "integration": "account.read",
        "integrations": "account.read",
        "connect_integration": "account.write",
        "connectIntegration": "account.write",
        "disconnect_integration": "account.write",
        "disconnectIntegration": "account.write",
    }

    def resolve(self, _next, root, info: strawberry.Info, *args, **kwargs):  # type: ignore[override]
        parent = getattr(info, "parent_type", None)
        parent_name = getattr(parent, "name", "") if parent else ""
        # Only enforce on the operation root – nested fields inherit the
        # decision from their parent resolve.
        if parent_name in {"Query", "Mutation"}:
            field_name = info.field_name
            if field_name not in self.PUBLIC_FIELDS:
                request = info.context.get("request") if isinstance(info.context, dict) else None
                uid = None
                if request is not None:
                    # Use the same `get_current_user_id` symbol that
                    # individual resolvers use, so existing test mocks
                    # (which patch this module's binding) keep working.
                    try:
                        uid = get_current_user_id(request)
                    except HTTPException:
                        uid = None
                    except Exception:
                        try:
                            uid = get_current_user_id_optional(request)
                        except Exception:
                            uid = None
                if not uid:
                    raise PermissionError(f"Authentication required for {parent_name}.{field_name}")
                required = self.FIELD_PERMISSIONS.get(field_name)
                if required:
                    try:
                        principal = resolve_principal(uid)
                    except Exception:
                        principal = None
                    if not principal or not principal.has(required):
                        raise PermissionError(
                            f"Permission '{required}' required for {parent_name}.{field_name}"
                        )
        return _next(root, info, *args, **kwargs)


# SEC-029: harden GraphQL surface — depth + alias + token caps to bound
# query cost, plus introspection lockdown in production.
from strawberry.extensions import (
    DisableIntrospection as _DisableIntrospection,
)
from strawberry.extensions import (
    MaxAliasesLimiter as _MaxAliasesLimiter,
)
from strawberry.extensions import (
    MaxTokensLimiter as _MaxTokensLimiter,
)
from strawberry.extensions import (
    QueryDepthLimiter as _QueryDepthLimiter,
)


def _graphql_extensions():
    exts = [
        _DefaultDenyAuthExtension,
        infrastructure_error_masker(),
        _QueryDepthLimiter(max_depth=int(os.getenv("GRAPHQL_MAX_DEPTH", "12"))),
        _MaxAliasesLimiter(max_alias_count=int(os.getenv("GRAPHQL_MAX_ALIASES", "30"))),
        _MaxTokensLimiter(max_token_count=int(os.getenv("GRAPHQL_MAX_TOKENS", "5000"))),
    ]
    env_label = (
        (os.getenv("MANIFEST_ENV") or os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "")
        .strip()
        .lower()
    )
    introspection_enabled = (os.getenv("GRAPHQL_INTROSPECTION") or "").strip().lower()
    is_prod = env_label in {"prod", "production", "staging"}
    if introspection_enabled in {"0", "false", "no", "off"} or (
        is_prod and introspection_enabled not in {"1", "true", "yes", "on"}
    ):
        exts.append(_DisableIntrospection())
    return exts


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=_graphql_extensions(),
)
