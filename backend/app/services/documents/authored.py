"""Documents written by the person's own AI agent (ADR 0005).

Manifest generates a Business Model Canvas, pitch deck, PRD and provisional patent with
the person's own OpenAI key. When there is no key, the agent they are already talking to
(Claude, ChatGPT, Codex, Cursor…) is the writer: it reads :func:`guide` — Manifest's own
prompt for that document, so the structure matches — writes the document, and saves it
with :func:`save`. Saved documents land in exactly the places generated ones do.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from typing import Any

from app.prompts import prompt_path

MAX_CHARS = 200_000


@dataclass(frozen=True)
class DocumentKind:
    key: str
    title: str
    column: str  # ideas.<column>
    table: str | None = None  # per-document table the read queries also use
    prompt: str | None = None  # app/prompts/<prompt>.mcp.json


KINDS: dict[str, DocumentKind] = {
    kind.key: kind
    for kind in (
        DocumentKind(
            "business_model_canvas",
            "Business Model Canvas",
            "business_model_canvas",
            prompt="business_model_canvas",
        ),
        DocumentKind("similar_ideas", "Similar ideas and competitors", "similar_ideas"),
        DocumentKind(
            "pitch_deck", "Pitch deck", "pitch_deck", table="pitch_decks", prompt="pitch_deck"
        ),
        DocumentKind(
            "product_requirements_document",
            "Product requirements document",
            "product_requirements_document",
            table="product_requirements_documents",
            prompt="product_requirements_document",
        ),
        DocumentKind(
            "provisional_patent",
            "Provisional patent draft",
            "provisional_patent",
            prompt="provisional_patent",
        ),
    )
}
ALIASES = {
    "bmc": "business_model_canvas",
    "canvas": "business_model_canvas",
    "prd": "product_requirements_document",
    "patent": "provisional_patent",
    "deck": "pitch_deck",
    "competitors": "similar_ideas",
}

SIMILAR_IDEAS_GUIDE = {
    "system": (
        "You are a startup analyst mapping the competitive landscape for one specific idea. "
        "Be concrete and verifiable: real companies and projects with links, no invented names. "
        "Use Markdown only."
    ),
    "user": (
        "For the idea below, write:\n\n# Similar Landscape\n## Comparable Companies\n"
        "### <Company or project>\n- URL:\n- Summary:\n- Why Similar:\n- Distinguishing Signal:\n"
        "(4-8 entries; search the web when you can and only list things you could verify)\n\n"
        "## Research Watchlist\n### <Question to validate>\n- Suggested Sources:\n- Why It Matters:\n"
        "- What To Validate:\n\nIdea: {{idea_description}}"
    ),
}


class DocumentError(ValueError):
    """A request the caller can fix (unknown type, empty or oversized content)."""


def kind_for(document_type: str) -> DocumentKind:
    key = (document_type or "").strip().lower().replace("-", "_").replace(" ", "_")
    key = ALIASES.get(key, key)
    if key not in KINDS:
        raise DocumentError(
            f"Unknown document type {document_type!r}; use one of {', '.join(KINDS)}."
        )
    return KINDS[key]


@cache
def _prompt(name: str) -> dict[str, Any]:
    with open(prompt_path(f"{name}.mcp.json"), encoding="utf-8") as handle:
        return json.load(handle)["prompt"]


def guide(document_type: str) -> dict[str, str]:
    """Manifest's own instructions for a document, for an agent to follow."""
    kind = kind_for(document_type)
    prompt = SIMILAR_IDEAS_GUIDE if kind.prompt is None else _prompt(kind.prompt)
    instructions = (
        str(prompt.get("user", ""))
        .replace("{{idea_description}}", "<the idea's description: read it with the idea tool>")
        .replace(
            "{{connected_partners}}",
            "<the founder's connected partners: list them with the integrations tool; they are "
            "current partners, so list the relevant ones first under Key Partners>",
        )
    )
    return {
        "document_type": kind.key,
        "title": kind.title,
        "system": str(prompt.get("system", "")),
        "instructions": instructions,
        "save_with": (
            "save_bmc_section for one canvas section, or save_idea_document "
            "(documentType business_model_canvas) for the whole canvas"
            if kind.key == "business_model_canvas"
            else f"save_idea_document with documentType {kind.key}"
        ),
    }


def clean_content(content: str) -> str:
    text = (content or "").strip()
    if not text:
        raise DocumentError("The document is empty.")
    if len(text) > MAX_CHARS:
        raise DocumentError(f"The document is longer than {MAX_CHARS:,} characters.")
    return text


def save(*, idea_id: str, owner_id: str, document_type: str, content: str) -> DocumentKind:
    """Store a written document exactly where generated ones are stored."""
    from app.services.ideas import document_generation

    kind = kind_for(document_type)
    text = clean_content(content)
    document_generation._update_idea_documents(idea_id, {kind.column: text, "user_id": owner_id})
    if kind.table:
        document_generation._upsert_generated_document(kind.table, idea_id, owner_id, text)
    return kind
