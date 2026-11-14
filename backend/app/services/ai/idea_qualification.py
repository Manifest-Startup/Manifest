"""Conversational idea-qualification agent.

Owns `idea_qualification_sessions`. One agent turn extracts structured
fields from the latest user reply and either asks the next best question
or marks the session complete with a 0–100 score + explanation.

GraphQL surface lives in app.graphql.schema (startIdeaQualification,
continueIdeaQualification, ideaQualificationSession). Prompt template is
loaded from app/prompts/idea_qualification.mcp.json.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.prompts import prompt_path
from app.services.ai import cost_tracking as cost_tracking_service
from app.utils.logger import logger

TABLE = "idea_qualification_sessions"
AGENT_KIND = "qualification"

# All 13 fields the agent tries to populate. The order matters for the
# completion heuristic (we count how many are non-null).
QUALIFICATION_FIELDS: tuple[str, ...] = (
    "user_seriousness",
    "user_domain_knowledge",
    "user_goals",
    "user_budget",
    "user_timeline",
    "user_execution_ability",
    "idea_market_need",
    "idea_target_customer",
    "idea_feasibility",
    "idea_defensibility",
    "idea_revenue_potential",
    "idea_competition",
    "idea_risks",
)

OPENING_QUESTION = (
    "Tell me what you're trying to build, in your own words — what's the "
    "idea, who is it for, and why now?"
)

MAX_TURNS = 8

_PROMPT_CACHE: dict[str, Any] | None = None


class QualificationError(Exception):
    """Raised when the qualification flow cannot proceed."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_prompt() -> dict[str, Any]:
    global _PROMPT_CACHE
    if _PROMPT_CACHE is not None:
        return _PROMPT_CACHE
    path = prompt_path("idea_qualification.mcp.json")
    with open(path, encoding="utf-8") as f:
        _PROMPT_CACHE = json.load(f)
    return _PROMPT_CACHE


def _known_fields(session: dict[str, Any]) -> dict[str, Any]:
    return {field: session.get(field) for field in QUALIFICATION_FIELDS}


def _filled_field_count(session: dict[str, Any]) -> int:
    return sum(1 for f in QUALIFICATION_FIELDS if session.get(f) not in (None, ""))


def _render_transcript(transcript: list[dict[str, str]]) -> str:
    if not transcript:
        return "(no turns yet)"
    return "\n".join(
        f"{turn.get('role', '?').upper()}: {turn.get('content', '')}" for turn in transcript
    )


def _build_messages(session: dict[str, Any]) -> list[dict[str, str]]:
    prompt = _load_prompt()
    system_prompt = prompt["prompt"]["system"]
    user_template = prompt["prompt"]["user"]
    known = _known_fields(session)
    transcript = session.get("transcript") or []
    rendered = (
        user_template.replace("{{initial_idea_text}}", session.get("initial_idea_text", ""))
        .replace("{{known_fields_json}}", json.dumps(known, indent=2))
        .replace("{{transcript_text}}", _render_transcript(transcript))
        .replace("{{turn_count}}", str(session.get("turn_count", 0)))
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": rendered},
    ]


def _coerce_int_1_10(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 10 else None


def _coerce_int_0_100(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, n))


_INT_FIELDS = {
    "user_seriousness",
    "user_domain_knowledge",
    "user_execution_ability",
    "idea_market_need",
    "idea_feasibility",
    "idea_defensibility",
    "idea_revenue_potential",
}


def _merge_extracted(session: dict[str, Any], extracted: dict[str, Any]) -> dict[str, Any]:
    """Only fill nulls — never overwrite a value the agent already locked in."""
    updates: dict[str, Any] = {}
    for field in QUALIFICATION_FIELDS:
        if session.get(field) not in (None, ""):
            continue
        raw = extracted.get(field) if isinstance(extracted, dict) else None
        if raw is None:
            continue
        if field in _INT_FIELDS:
            coerced = _coerce_int_1_10(raw)
            if coerced is not None:
                updates[field] = coerced
        else:
            text = str(raw).strip()
            if text:
                updates[field] = text
    return updates


def _heuristic_complete(session: dict[str, Any]) -> bool:
    return _filled_field_count(session) >= 8 or session.get("turn_count", 0) >= MAX_TURNS


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, list):
        return row[0] if row else None
    return row


def start_session(
    *,
    db,
    user_id: str,
    initial_idea_text: str,
) -> dict[str, Any]:
    """Create a new qualification session and seed the opening question.

    Also opens an `agent_runs` row scoped to this session. The opening
    question is canned (no LLM call), so no cost event is logged at this
    point — cost events accrue from the first `continue_session`.
    """
    if not initial_idea_text or not initial_idea_text.strip():
        raise QualificationError("initial_idea_text is required")

    session_id = str(uuid.uuid4())
    now = _now_iso()
    transcript = [{"role": "assistant", "content": OPENING_QUESTION, "ts": now}]
    payload = {
        "id": session_id,
        "user_id": user_id,
        "initial_idea_text": initial_idea_text.strip(),
        "status": "in_progress",
        "transcript": json.dumps(transcript),
        "next_question": OPENING_QUESTION,
        "turn_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    response = db.table(TABLE).insert(payload).execute()
    row = _row_to_dict(response.data)
    if row is None:
        raise QualificationError("Failed to create qualification session")

    try:
        run_id = cost_tracking_service.start_agent_run(
            db=db,
            user_id=user_id,
            agent_kind=AGENT_KIND,
            qualification_session_id=session_id,
            metadata={"opening_question": OPENING_QUESTION},
        )
        # Record the run id on the session so future turns can find it
        # without an extra index. Stored in transcript-adjacent metadata
        # via the session row's update path; agent_runs.qualification_session_id
        # is the canonical link.
        db.table(TABLE).update({"updated_at": _now_iso()}).eq("id", session_id).execute()
        logger.info(
            "[qualification] start session_id=%s user_id=%s run_id=%s",
            session_id,
            user_id,
            run_id,
        )
    except Exception as exc:
        logger.warning("[qualification] cost-run start failed (continuing): %s", exc)

    return _normalize_row(row)


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Ensure transcript is a list (it may come back as a JSON string from SELECT)."""
    if isinstance(row.get("transcript"), str):
        try:
            row["transcript"] = json.loads(row["transcript"])
        except (TypeError, ValueError):
            row["transcript"] = []
    elif row.get("transcript") is None:
        row["transcript"] = []
    return row


def get_session(
    *,
    db,
    session_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    response = (
        db.table(TABLE).select("*").eq("id", session_id).eq("user_id", user_id).limit(1).execute()
    )
    rows = response.data or []
    if not rows:
        return None
    return _normalize_row(dict(rows[0]))


def list_sessions(*, db, user_id: str) -> list[dict[str, Any]]:
    response = (
        db.table(TABLE)
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    rows = response.data or []
    return [_normalize_row(dict(r)) for r in rows]


def continue_session(
    *,
    db,
    ai_layer,
    session_id: str,
    user_id: str,
    user_message: str,
) -> dict[str, Any]:
    """Advance a session by one turn. Calls the LLM, merges extraction, writes back."""
    if not user_message or not user_message.strip():
        raise QualificationError("user_message is required")

    session = get_session(db=db, session_id=session_id, user_id=user_id)
    if session is None:
        raise QualificationError("Session not found")
    if session.get("status") != "in_progress":
        raise QualificationError(f"Session is {session.get('status')}, cannot continue")

    transcript = list(session.get("transcript") or [])
    transcript.append(
        {
            "role": "user",
            "content": user_message.strip(),
            "ts": _now_iso(),
        }
    )
    session["transcript"] = transcript
    session["turn_count"] = int(session.get("turn_count") or 0) + 1

    run_id = _find_agent_run_id(db=db, session_id=session_id)

    parsed = _run_agent_turn(ai_layer, session)
    # Cost is logged for the LLM call we just made (if it ran). The tap
    # is a no-op when the AI layer is offline / mocked, so this is safe
    # to call unconditionally.
    try:
        cost_tracking_service.log_cost_event_from_tap(
            db=db,
            user_id=user_id,
            agent_kind=AGENT_KIND,
            run_id=run_id,
            note=f"qualification turn {session['turn_count']}",
        )
    except Exception as exc:
        logger.warning("[qualification] cost event log failed (continuing): %s", exc)

    updates = _merge_extracted(session, parsed.get("extracted_fields") or {})
    for field, value in updates.items():
        session[field] = value

    decision = parsed.get("decision", "ask_again")
    if decision == "complete" or _heuristic_complete(session):
        score = _coerce_int_0_100(parsed.get("qualification_score"))
        if score is None:
            score = _fallback_score(session)
        explanation = (parsed.get("qualification_explanation") or "").strip() or (
            "Qualification complete based on the information provided."
        )
        session["status"] = "complete"
        session["qualification_score"] = score
        session["qualification_explanation"] = explanation
        session["next_question"] = None
    else:
        next_q = (parsed.get("next_question") or "").strip()
        if not next_q:
            next_q = "What else would be useful for me to know to help you build this?"
        transcript.append(
            {
                "role": "assistant",
                "content": next_q,
                "ts": _now_iso(),
            }
        )
        session["transcript"] = transcript
        session["next_question"] = next_q

    session["updated_at"] = _now_iso()
    persisted = _persist_update(db=db, session_id=session_id, session=session)

    if persisted.get("status") == "complete" and run_id:
        try:
            cost_tracking_service.complete_agent_run(db=db, run_id=run_id, status="complete")
        except Exception as exc:
            logger.warning("[qualification] cost-run complete failed: %s", exc)

    return persisted


def _find_agent_run_id(*, db, session_id: str) -> str | None:
    """Look up the agent_runs.id associated with a qualification session.

    Returns None if no run is linked (older sessions started before the
    cost foundation, or insert failure during start_session).
    """
    try:
        response = (
            db.table("agent_runs")
            .select("id")
            .eq("qualification_session_id", session_id)
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if rows:
            return str(rows[0].get("id"))
    except Exception as exc:
        logger.debug("[qualification] agent_run lookup failed: %s", exc)
    return None


def _run_agent_turn(ai_layer, session: dict[str, Any]) -> dict[str, Any]:
    """Call the LLM. Return parsed structured response, or a safe fallback."""
    if ai_layer is None or not getattr(ai_layer, "is_available", lambda: False)():
        logger.warning("[qualification] ai_layer unavailable; using fallback turn")
        return {"extracted_fields": {}, "decision": "ask_again", "next_question": None}

    messages = _build_messages(session)
    try:
        parsed = ai_layer.generate_structured_response(messages)
    except Exception as exc:
        logger.error("[qualification] LLM call failed: %s", exc)
        return {"extracted_fields": {}, "decision": "ask_again", "next_question": None}

    if not isinstance(parsed, dict):
        logger.warning("[qualification] LLM returned non-dict: %r", parsed)
        return {"extracted_fields": {}, "decision": "ask_again", "next_question": None}
    return parsed


def _fallback_score(session: dict[str, Any]) -> int:
    """If the LLM didn't supply a score, average the 1–10 ints we have, then scale."""
    ints = [session.get(f) for f in _INT_FIELDS if isinstance(session.get(f), int)]
    if not ints:
        return 50
    avg = sum(ints) / len(ints)
    return max(0, min(100, int(round(avg * 10))))


def _persist_update(*, db, session_id: str, session: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": session.get("status"),
        "transcript": json.dumps(session.get("transcript") or []),
        "next_question": session.get("next_question"),
        "turn_count": session.get("turn_count"),
        "qualification_score": session.get("qualification_score"),
        "qualification_explanation": session.get("qualification_explanation"),
        "updated_at": session.get("updated_at"),
    }
    for field in QUALIFICATION_FIELDS:
        payload[field] = session.get(field)

    response = db.table(TABLE).update(payload).eq("id", session_id).execute()
    row = _row_to_dict(response.data)
    if row is None:
        raise QualificationError("Failed to persist qualification session update")
    return _normalize_row(dict(row))
