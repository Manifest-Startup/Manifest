"""GraphQL resolvers for universal search across ideas, people and the web."""

import asyncio
import re
from typing import Any
from urllib.parse import unquote, urlparse

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.resolvers.shared import (
    _coerce_datetime,
    _display_name,
    _get_ai_cache,
    _set_ai_cache,
)
from app.graphql.types.search import (
    UniversalSearchIdeaResult,
    UniversalSearchResults,
    UniversalSearchWebSource,
)
from app.utils.logger import logger

SEARCHABLE_IDEA_FIELDS = [
    ("Description", "description", 6),
    ("Business model", "business_model_canvas", 5),
    ("Pitch deck", "pitch_deck", 4),
    ("Product requirements", "product_requirements_document", 4),
    ("Patent", "provisional_patent", 3),
    ("Research", "similar_ideas", 3),
]


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


@strawberry.type
class SearchQuery:
    @strawberry.field
    async def universal_search(  # noqa: C901
        self,
        info: strawberry.Info,
        query: str,
        limit: int = 5,
        include_web: bool = False,
    ) -> UniversalSearchResults:
        """Search your ideas, documents and people at once (optionally the web)."""
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
