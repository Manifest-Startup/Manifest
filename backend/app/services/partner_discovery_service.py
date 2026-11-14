"""Partner-discovery sub-agent.

Given a startup idea, produces a ranked list of real-world partner
candidates with integration metadata (api / mcp / sdk / webhook /
zapier / manual / unknown) so the BMC key_partners section becomes
actionable for the founder.

Wraps an LLM call in the same cost-tracked agent_run / cost_event
plumbing every other agent uses (`agent_kind = partner_discovery`).
Per spec: NEVER contacts partners or sends data externally as a
side-effect of running. The `approve` mutation only flips an internal
flag; downstream outreach lives in a separate (future) slice.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.services import cost_tracking_service
from app.utils.logger import logger

TABLE = "partner_candidates"
AGENT_KIND = "partner_discovery"

VALID_INTEGRATION_TYPES = {"api", "mcp", "sdk", "webhook", "zapier", "manual", "unknown"}
VALID_DIFFICULTY = {"low", "medium", "high"}
VALID_CONFIDENCE = {"low", "medium", "high"}

DEFAULT_MAX_CANDIDATES = 10
MAX_CANDIDATES_CAP = 20

_PROMPT_CACHE: dict[str, Any] | None = None


class PartnerDiscoveryError(Exception):
    """Raised when partner discovery cannot complete."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_prompt() -> dict[str, Any]:
    global _PROMPT_CACHE
    if _PROMPT_CACHE is not None:
        return _PROMPT_CACHE
    path = os.path.join(os.path.dirname(__file__), "..", "prompts", "partner_discovery.mcp.json")
    with open(path, encoding="utf-8") as f:
        _PROMPT_CACHE = json.load(f)
    return _PROMPT_CACHE


# ---------- read ----------


def list_candidates(*, db, idea_id: str) -> list[dict[str, Any]]:
    """Return partner candidates for an idea, ordered by rank ascending."""
    response = (
        db.table(TABLE)
        .select("*")
        .eq("idea_id", idea_id)
        .order("rank", desc=False)
        .limit(200)
        .execute()
    )
    rows = list(response.data or [])
    # Stable secondary sort by relevance_score desc when rank ties.
    rows.sort(
        key=lambda r: (
            int(r.get("rank") or 999),
            -int(r.get("relevance_score") or 0),
        )
    )
    return [dict(r) for r in rows]


def _fetch_idea_description(*, db, idea_id: str) -> str | None:
    response = db.table("ideas").select("description").eq("idea_id", idea_id).limit(1).execute()
    rows = response.data or []
    if not rows:
        return None
    return rows[0].get("description") if isinstance(rows[0], dict) else None


def _fetch_qualification_summary(*, db, user_id: str) -> str:
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
        logger.debug("[partner_discovery] qualification lookup failed: %s", exc)
        return ""
    rows = response.data or []
    if not rows:
        return ""
    row = rows[0]
    score = row.get("qualification_score")
    explanation = (row.get("qualification_explanation") or "").strip()
    parts: list[str] = []
    if score is not None:
        parts.append(f"Qualification score: {score}/100.")
    if explanation:
        parts.append(explanation)
    return " ".join(parts)


def _fetch_existing_key_partners(*, db, idea_id: str) -> str:
    try:
        response = (
            db.table("business_model_canvas_sections")
            .select("content")
            .eq("idea_id", idea_id)
            .eq("section_name", "key_partners")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.debug("[partner_discovery] key_partners lookup failed: %s", exc)
        return ""
    rows = response.data or []
    if not rows:
        return ""
    return str(rows[0].get("content") or "")


# ---------- discovery ----------


def run_discovery(
    *,
    db,
    ai_layer,
    user_id: str,
    idea_id: str,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> list[dict[str, Any]]:
    """Run one partner-discovery agent_run for an idea.

    Caller is responsible for the ownership check on idea_id.

    Returns the candidates persisted on this run (ordered by rank).
    Existing candidates with the same name are upserted; rank is
    refreshed each run so dashboards always see the latest ranking.
    """
    idea_description = _fetch_idea_description(db=db, idea_id=idea_id)
    if not idea_description or not str(idea_description).strip():
        raise PartnerDiscoveryError(
            "Idea has no description; partner discovery needs a description to reason about."
        )

    cap = max(4, min(int(max_candidates or DEFAULT_MAX_CANDIDATES), MAX_CANDIDATES_CAP))
    qualification_summary = _fetch_qualification_summary(db=db, user_id=user_id)
    existing_kp = _fetch_existing_key_partners(db=db, idea_id=idea_id)

    run_id = cost_tracking_service.start_agent_run(
        db=db,
        user_id=user_id,
        agent_kind=AGENT_KIND,
        idea_id=idea_id,
        metadata={"max_candidates": cap},
    )
    try:
        parsed = _call_llm(
            ai_layer=ai_layer,
            idea_description=str(idea_description),
            qualification_summary=qualification_summary,
            existing_key_partners=existing_kp,
            max_candidates=cap,
        )

        try:
            cost_tracking_service.log_cost_event_from_tap(
                db=db,
                user_id=user_id,
                agent_kind=AGENT_KIND,
                run_id=run_id,
                note="partner discovery",
            )
        except Exception as exc:
            logger.warning("[partner_discovery] cost event log failed: %s", exc)

        candidates = _normalize_candidates(parsed.get("candidates") or [])[:cap]
        persisted = _upsert_candidates(db=db, idea_id=idea_id, run_id=run_id, candidates=candidates)

        cost_tracking_service.complete_agent_run(db=db, run_id=run_id, status="complete")
        return persisted
    except PartnerDiscoveryError:
        cost_tracking_service.fail_agent_run(
            db=db, run_id=run_id, error_message="partner_discovery: agent error"
        )
        raise
    except Exception as exc:
        cost_tracking_service.fail_agent_run(db=db, run_id=run_id, error_message=str(exc)[:500])
        raise PartnerDiscoveryError(f"partner discovery failed: {exc}") from exc


def _call_llm(
    *,
    ai_layer,
    idea_description: str,
    qualification_summary: str,
    existing_key_partners: str,
    max_candidates: int,
) -> dict[str, Any]:
    if ai_layer is None or not getattr(ai_layer, "is_available", lambda: False)():
        raise PartnerDiscoveryError("AI layer is not available; cannot run discovery")

    prompt = _load_prompt()
    system_prompt = prompt["prompt"]["system"]
    user_template = prompt["prompt"]["user"]
    rendered = (
        user_template.replace("{{idea_description}}", idea_description)
        .replace("{{qualification_summary}}", qualification_summary or "(no qualification run yet)")
        .replace(
            "{{existing_key_partners_section}}",
            existing_key_partners or "(BMC key_partners not generated yet)",
        )
        .replace("{{max_candidates}}", str(max_candidates))
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": rendered},
    ]
    try:
        parsed = ai_layer.generate_structured_response(messages)
    except Exception as exc:
        raise PartnerDiscoveryError(f"LLM call failed: {exc}") from exc
    if not isinstance(parsed, dict):
        raise PartnerDiscoveryError(f"LLM returned non-dict: {parsed!r}")
    return parsed


def _normalize_one_candidate(entry: dict[str, Any]) -> dict[str, Any] | None:
    name = str(entry.get("name") or "").strip()
    category = str(entry.get("category") or "").strip()
    if not name or not category:
        return None

    integration_type = str(entry.get("integration_type") or "unknown").strip().lower()
    if integration_type not in VALID_INTEGRATION_TYPES:
        integration_type = "unknown"

    difficulty = entry.get("implementation_difficulty")
    if difficulty is not None:
        difficulty = str(difficulty).strip().lower()
        if difficulty not in VALID_DIFFICULTY:
            difficulty = None

    confidence = entry.get("confidence")
    if confidence is not None:
        confidence = str(confidence).strip().lower()
        if confidence not in VALID_CONFIDENCE:
            confidence = None

    relevance = entry.get("relevance_score")
    try:
        relevance_int = int(relevance) if relevance is not None else None
    except (TypeError, ValueError):
        relevance_int = None
    if relevance_int is not None:
        relevance_int = max(0, min(100, relevance_int))

    return {
        "name": name[:200],
        "website": (str(entry.get("website") or "").strip() or None),
        "category": category[:120],
        "why_relevant": (str(entry.get("why_relevant") or "").strip() or None),
        "suggested_use": (str(entry.get("suggested_use") or "").strip() or None),
        "integration_type": integration_type,
        "data_required": (str(entry.get("data_required") or "").strip() or None),
        "actions_possible": (str(entry.get("actions_possible") or "").strip() or None),
        "pricing_notes": (str(entry.get("pricing_notes") or "").strip() or None),
        "risk_notes": (str(entry.get("risk_notes") or "").strip() or None),
        "implementation_difficulty": difficulty,
        "recommended_next_step": (str(entry.get("recommended_next_step") or "").strip() or None),
        "relevance_score": relevance_int,
        "confidence": confidence,
    }


def _normalize_candidates(raw: list[Any]) -> list[dict[str, Any]]:
    """Defensive normalization. The LLM is told the schema, but we don't
    trust it absolutely: drop malformed entries, clamp enums, dedupe by
    (lowercased) name."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        normalized = _normalize_one_candidate(entry)
        if normalized is None:
            continue
        key = normalized["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)

    # Final rank ordering: by relevance_score desc, ties broken by name asc.
    out.sort(key=lambda c: (-(c.get("relevance_score") or 0), c["name"].lower()))
    for i, c in enumerate(out, start=1):
        c["rank"] = i
    return out


def _upsert_candidates(
    *,
    db,
    idea_id: str,
    run_id: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Insert new candidates with a fresh id; update existing rows by id.

    We do a per-candidate (idea_id, name) lookup rather than a single
    bulk upsert because the in-memory test client's upsert path would
    overwrite the existing id on conflict — breaking the stable id
    contract callers depend on (especially the approval mutation).
    """
    persisted: list[dict[str, Any]] = []
    now = _now_iso()
    for cand in candidates:
        existing_response = (
            db.table(TABLE)
            .select("*")
            .eq("idea_id", idea_id)
            .eq("name", cand["name"])
            .limit(1)
            .execute()
        )
        existing_rows = existing_response.data or []
        existing = existing_rows[0] if existing_rows else None

        body: dict[str, Any] = {
            "idea_id": idea_id,
            "name": cand["name"],
            "website": cand.get("website"),
            "category": cand["category"],
            "why_relevant": cand.get("why_relevant"),
            "suggested_use": cand.get("suggested_use"),
            "integration_type": cand["integration_type"],
            "data_required": cand.get("data_required"),
            "actions_possible": cand.get("actions_possible"),
            "pricing_notes": cand.get("pricing_notes"),
            "risk_notes": cand.get("risk_notes"),
            "implementation_difficulty": cand.get("implementation_difficulty"),
            "recommended_next_step": cand.get("recommended_next_step"),
            "relevance_score": cand.get("relevance_score"),
            "confidence": cand.get("confidence"),
            "rank": cand.get("rank") or 999,
            "generated_by_run_id": run_id,
            "last_generated_at": now,
            "updated_at": now,
        }

        if existing is None:
            body["id"] = str(uuid.uuid4())
            body["approved"] = False
            body["created_at"] = now
            response = db.table(TABLE).insert(body).execute()
        else:
            response = db.table(TABLE).update(body).eq("id", existing["id"]).execute()

        row = response.data
        if isinstance(row, list):
            row = row[0] if row else None
        if row:
            persisted.append(dict(row))
    return persisted


# ---------- approval ----------


def approve_candidate(
    *,
    db,
    user_id: str,
    candidate_id: str,
    approved: bool = True,
) -> dict[str, Any]:
    """Set the approval flag on a candidate. Caller verifies the idea
    is owned by user_id BEFORE invoking this — we don't repeat the
    ownership check here, but we record approved_by for the audit log.
    """
    updates: dict[str, Any] = {
        "approved": bool(approved),
        "updated_at": _now_iso(),
    }
    if approved:
        updates["approved_at"] = _now_iso()
        updates["approved_by"] = user_id
    else:
        updates["approved_at"] = None
        updates["approved_by"] = None

    response = db.table(TABLE).update(updates).eq("id", candidate_id).execute()
    row = response.data
    if isinstance(row, list):
        row = row[0] if row else None
    if not row:
        raise PartnerDiscoveryError(f"candidate not found: {candidate_id}")
    return dict(row)
