"""Per-section Business Model Canvas sub-agents.

One agent per canonical BMC section. Each regeneration:
  1. Opens a cost-tracked agent_run (agent_kind = bmc_<section>).
  2. Threads the qualification summary (if any) and already-generated
     sibling sections into the LLM context so the output stays
     consistent with the rest of the canvas.
  3. Calls the LLM with strict-JSON output.
  4. Logs the cost event via the llm_usage_tap.
  5. Upserts the result into business_model_canvas_sections.
  6. Closes the run.

Coexists with the legacy monolithic
`business_model_canvas_service.py`, which still backs the bulk-
generated `business_model_canvas` field on the Idea type for older UI
paths. Per-section panels read from this service.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from app.prompts import prompt_path
from app.services.ai import cost_tracking as cost_tracking_service
from app.services.integrations.connections import (
    connected_partner_names,
    partners_prompt_block,
)
from app.utils.logger import logger

TABLE = "business_model_canvas_sections"

# Canonical ordering — also what the frontend panel renders in.
SECTION_NAMES: tuple[str, ...] = (
    "customer_segments",
    "value_propositions",
    "channels",
    "customer_relationships",
    "revenue_streams",
    "key_resources",
    "key_activities",
    "key_partners",
    "cost_structure",
)

_PROMPT_CACHE: dict[str, Any] | None = None


class BmcSectionError(Exception):
    """Raised when a BMC sub-agent cannot complete a regeneration."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_prompt() -> dict[str, Any]:
    global _PROMPT_CACHE
    if _PROMPT_CACHE is not None:
        return _PROMPT_CACHE
    path = prompt_path("bmc_section.mcp.json")
    with open(path, encoding="utf-8") as f:
        _PROMPT_CACHE = json.load(f)
    return _PROMPT_CACHE


# ---------- read ----------


def get_sections(*, db, idea_id: str) -> list[dict[str, Any]]:
    """Return all 9 BMC sections for the idea in canonical order.

    Sections that have not been generated come back with `content=None`
    so the frontend can show placeholder cards without a separate
    "exists" query.
    """
    response = db.table(TABLE).select("*").eq("idea_id", idea_id).execute()
    by_name = {str(row.get("section_name")): dict(row) for row in (response.data or [])}
    out: list[dict[str, Any]] = []
    for name in SECTION_NAMES:
        row = by_name.get(name)
        if row is None:
            out.append(
                {
                    "id": None,
                    "idea_id": idea_id,
                    "section_name": name,
                    "content": None,
                    "content_format": "markdown",
                    "needs_user_review": False,
                    "generated_by_run_id": None,
                    "last_generated_at": None,
                    "last_user_edit_at": None,
                }
            )
        else:
            out.append(row)
    return out


def _fetch_idea_description(*, db, idea_id: str) -> str | None:
    response = db.table("ideas").select("description").eq("idea_id", idea_id).limit(1).execute()
    rows = response.data or []
    if not rows:
        return None
    return rows[0].get("description") if isinstance(rows[0], dict) else None


def _fetch_qualification_summary(*, db, user_id: str) -> str:
    """Best-effort lookup of the user's most recent COMPLETE qualification
    session. Returns a plain-language summary string, or empty if none.
    """
    try:
        response = (
            db.table("idea_qualification_sessions")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "complete")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.debug("[bmc] qualification lookup failed: %s", exc)
        return ""
    rows = response.data or []
    if not rows:
        return ""
    row = rows[0]
    score = row.get("qualification_score")
    explanation = (row.get("qualification_explanation") or "").strip()
    if score is None and not explanation:
        return ""
    parts: list[str] = []
    if score is not None:
        parts.append(f"Qualification score: {score}/100.")
    if explanation:
        parts.append(explanation)
    return " ".join(parts)


# ---------- regenerate ----------


def regenerate_section(
    *,
    db,
    ai_layer,
    user_id: str,
    idea_id: str,
    section_name: str,
) -> dict[str, Any]:
    """Regenerate one section. Opens + closes a cost-tracked agent_run.

    Caller is responsible for the ownership check on idea_id.
    """
    if section_name not in SECTION_NAMES:
        raise BmcSectionError(
            f"unknown section {section_name!r}; expected one of {list(SECTION_NAMES)}"
        )

    idea_description = _fetch_idea_description(db=db, idea_id=idea_id)
    if not idea_description or not str(idea_description).strip():
        raise BmcSectionError("Idea has no description to base a BMC section on")

    sibling_sections = {
        row["section_name"]: row.get("content")
        for row in get_sections(db=db, idea_id=idea_id)
        if row.get("section_name") != section_name and row.get("content")
    }
    qualification_summary = _fetch_qualification_summary(db=db, user_id=user_id)

    run_id = cost_tracking_service.start_agent_run(
        db=db,
        user_id=user_id,
        agent_kind=f"bmc_{section_name}",
        idea_id=idea_id,
        metadata={"section_name": section_name},
    )
    try:
        parsed = _run_section_agent(
            ai_layer=ai_layer,
            section_name=section_name,
            idea_description=str(idea_description),
            qualification_summary=qualification_summary,
            sibling_sections=sibling_sections,
            connected_partners=connected_partner_names(user_id),
        )

        try:
            cost_tracking_service.log_cost_event_from_tap(
                db=db,
                user_id=user_id,
                agent_kind=f"bmc_{section_name}",
                run_id=run_id,
                note=f"bmc section: {section_name}",
            )
        except Exception as exc:
            logger.warning("[bmc] cost event log failed (continuing): %s", exc)

        row = _upsert_section(
            db=db,
            idea_id=idea_id,
            section_name=section_name,
            content=str(parsed.get("content") or "").strip(),
            needs_user_review=bool(parsed.get("needs_user_review") or False),
            run_id=run_id,
        )
        cost_tracking_service.complete_agent_run(db=db, run_id=run_id, status="complete")
        return row
    except BmcSectionError:
        cost_tracking_service.fail_agent_run(
            db=db, run_id=run_id, error_message=f"bmc {section_name}: agent error"
        )
        raise
    except Exception as exc:
        cost_tracking_service.fail_agent_run(db=db, run_id=run_id, error_message=str(exc)[:500])
        raise BmcSectionError(f"failed to generate {section_name}: {exc}") from exc


def regenerate_all_sections(
    *,
    db,
    ai_layer,
    user_id: str,
    idea_id: str,
) -> list[dict[str, Any]]:
    """Regenerate every section in canonical order.

    Sections are generated sequentially so each later section sees the
    earlier ones as siblings (better internal consistency).
    """
    results: list[dict[str, Any]] = []
    last_error: Exception | None = None
    for section_name in SECTION_NAMES:
        try:
            row = regenerate_section(
                db=db,
                ai_layer=ai_layer,
                user_id=user_id,
                idea_id=idea_id,
                section_name=section_name,
            )
            results.append(row)
        except BmcSectionError as exc:
            logger.warning("[bmc] regenerate_all: section %s failed: %s", section_name, exc)
            last_error = exc
            continue
    if not results and last_error is not None:
        raise last_error
    return results


# ---------- internals ----------


def _run_section_agent(
    *,
    ai_layer,
    section_name: str,
    idea_description: str,
    qualification_summary: str,
    sibling_sections: dict[str, Any],
    connected_partners: list[str] | None = None,
) -> dict[str, Any]:
    if ai_layer is None or not getattr(ai_layer, "is_available", lambda: False)():
        raise BmcSectionError("AI layer is not available; cannot generate BMC section")

    prompt = _load_prompt()
    system_prompt = prompt["prompt"]["system"]
    user_template = prompt["prompt"]["user"]
    siblings_block = _render_siblings(sibling_sections)
    rendered_user = (
        user_template.replace("{{section_name}}", section_name)
        .replace("{{idea_description}}", idea_description)
        .replace("{{qualification_summary}}", qualification_summary or "(no qualification run yet)")
        .replace("{{sibling_sections_block}}", siblings_block)
        .replace("{{connected_partners}}", partners_prompt_block(connected_partners or []))
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": rendered_user},
    ]
    try:
        parsed = ai_layer.generate_structured_response(messages)
    except Exception as exc:
        raise BmcSectionError(f"LLM call failed: {exc}") from exc
    if not isinstance(parsed, dict):
        raise BmcSectionError(f"LLM returned non-dict: {parsed!r}")
    if not str(parsed.get("content") or "").strip():
        raise BmcSectionError("LLM returned empty content for section")
    return parsed


def _render_siblings(sibling_sections: dict[str, Any]) -> str:
    if not sibling_sections:
        return "(no sibling sections generated yet)"
    parts: list[str] = []
    for name, content in sibling_sections.items():
        text = str(content or "").strip()
        if not text:
            continue
        parts.append(f"--- {name} ---\n{text}")
    return "\n\n".join(parts) if parts else "(no sibling sections generated yet)"


def _heading(section_name: str) -> str:
    return section_name.replace("_", " ").title()


def merge_section_into_canvas(canvas: str | None, section_name: str, content: str) -> str:
    """The whole canvas with one section replaced (or added), in the canvas's own format.

    The app, the vault and every document read the whole canvas (``ideas.business_model_canvas``),
    so a section saved or regenerated on its own has to land there too.
    """
    title = _heading(section_name)
    body = content.strip()
    text = (canvas or "").strip()
    pattern = re.compile(
        rf"^(#{{1,3}})\s*{re.escape(title)}\s*\n.*?(?=^#{{1,3}}\s|\Z)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if match:
        block = f"{match.group(1)} {title}\n{body}\n"
        merged = text[: match.start()] + block + ("\n" if text[match.end() :].strip() else "")
        return (merged + text[match.end() :].lstrip("\n")).strip()
    return f"{text}\n# {title}\n{body}".strip() if text else f"# {title}\n{body}"


def _sync_idea_canvas(db, idea_id: str, section_name: str, content: str) -> None:
    """Write the section into the idea's whole canvas; never fails the section save."""
    try:
        rows = (
            db.table("ideas")
            .select("business_model_canvas")
            .eq("idea_id", idea_id)
            .limit(1)
            .execute()
            .data
        )
        row = (rows[0] if isinstance(rows, list) and rows else rows) or {}
        current = row.get("business_model_canvas") if isinstance(row, dict) else None
        merged = merge_section_into_canvas(current, section_name, content)
        if merged != (current or ""):
            db.table("ideas").update({"business_model_canvas": merged}).eq(
                "idea_id", idea_id
            ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[bmc] could not update the whole canvas for idea {idea_id}: {exc}")


def _upsert_section(
    *,
    db,
    idea_id: str,
    section_name: str,
    content: str,
    needs_user_review: bool,
    run_id: str,
) -> dict[str, Any]:
    now = _now_iso()
    payload = {
        "idea_id": idea_id,
        "section_name": section_name,
        "content": content,
        "content_format": "markdown",
        "needs_user_review": needs_user_review,
        "generated_by_run_id": run_id,
        "last_generated_at": now,
        "updated_at": now,
    }
    response = db.table(TABLE).upsert(payload, on_conflict="idea_id,section_name").execute()
    row = response.data
    if isinstance(row, list):
        row = row[0] if row else None
    if not row:
        raise BmcSectionError("failed to persist BMC section row")
    _sync_idea_canvas(db, idea_id, section_name, payload["content"])
    return dict(row)


def save_user_section(*, db, idea_id: str, section_name: str, content: str) -> dict[str, Any]:
    """Store a section the person (or their AI agent) wrote, marked as a user edit."""
    if section_name not in SECTION_NAMES:
        raise BmcSectionError(
            f"unknown section {section_name!r}; expected one of {list(SECTION_NAMES)}"
        )
    text = (content or "").strip()
    if not text:
        raise BmcSectionError("the section is empty")
    now = _now_iso()
    payload = {
        "idea_id": idea_id,
        "section_name": section_name,
        "content": text[:20_000],
        "content_format": "markdown",
        "needs_user_review": False,
        "generated_by_run_id": None,
        "last_user_edit_at": now,
        "updated_at": now,
    }
    response = db.table(TABLE).upsert(payload, on_conflict="idea_id,section_name").execute()
    row = response.data
    if isinstance(row, list):
        row = row[0] if row else None
    if not row:
        raise BmcSectionError("failed to persist BMC section row")
    _sync_idea_canvas(db, idea_id, section_name, payload["content"])
    return dict(row)
