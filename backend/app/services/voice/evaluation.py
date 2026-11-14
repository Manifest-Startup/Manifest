"""AI-driven voice-platform testing.

Three cost-tracked LLM agents run per end-to-end test:

  1. User Simulation Agent (`agent_kind = voice_test_simulator`)
     Generates a single realistic voice utterance for a
     (scenario, emotion) tuple — what the user would actually SAY OUT
     LOUD, including filler words and natural speech patterns.
  2. Voice executor (`agent_kind = voice_test_executor`)
     Produces the response that's being graded. v1 default executor
     is a self-contained LLM stub so tests don't pollute prod user
     data. A future slice swaps in the real
     `voice_agent_service.VoiceAgentService.process_message` path.
  3. Evaluation Agent (`agent_kind = voice_test_evaluator`)
     Scores the response 1-5 on intent_understanding,
     emotional_awareness, and helpfulness; returns pass/fail +
     failure taxonomy + rewrite suggestion.

Test results land in `voice_test_runs` with provenance pointers back
to each phase's `agent_runs` row, so the cost dashboard reflects
real spend.

See docs/VOICE_TESTING.md.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.prompts import prompt_path
from app.services.ai import cost_tracking as cost_tracking_service
from app.utils.logger import logger

TABLE = "voice_test_runs"

VALID_SCENARIOS = ("support_request", "product_question", "complaint")
VALID_EMOTIONS = ("neutral", "confused", "frustrated", "angry", "happy")
VALID_FAILURES = {
    "incorrect_intent",
    "tone_mismatch",
    "robotic_response",
    "missed_emotion",
    "hallucinated_policy",
    "over_apologizing",
    "ignored_question",
    "no_next_step",
    "unsafe_advice",
    "context_loss",
    "other",
}

# Pass-bar: every score must be >= 3.
PASS_THRESHOLD_PER_DIMENSION = 3

# v1 cost calibration (per agent_kind). The cost cap-enforcement layer
# reads these; tests typically run from an admin context so the cap
# rarely fires.
ESTIMATED_COSTS_USD = {
    "voice_test_simulator": 0.002,
    "voice_test_executor": 0.003,
    "voice_test_evaluator": 0.004,
}

_PROMPT_CACHE: dict[str, dict[str, Any]] = {}


class VoiceTestingError(Exception):
    """Raised when an end-to-end test cannot complete."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_prompt(name: str) -> dict[str, Any]:
    if name in _PROMPT_CACHE:
        return _PROMPT_CACHE[name]
    path = prompt_path(f"{name}.mcp.json")
    with open(path, encoding="utf-8") as f:
        _PROMPT_CACHE[name] = json.load(f)
    return _PROMPT_CACHE[name]


# ---------- 1. User Simulation Agent ----------


def generate_test_case(
    *,
    ai_layer,
    scenario: str,
    emotion: str,
    persona: str | None = None,
) -> dict[str, Any]:
    """Run the User Simulation Agent.

    Returns a dict with: user_persona, user_goal, user_input,
    expected_behavior, success_criteria, failure_conditions.
    Caller wraps this in an agent_run + logs the cost event.
    """
    if scenario not in VALID_SCENARIOS:
        raise VoiceTestingError(
            f"scenario {scenario!r} invalid; expected one of {list(VALID_SCENARIOS)}"
        )
    if emotion not in VALID_EMOTIONS:
        raise VoiceTestingError(
            f"emotion {emotion!r} invalid; expected one of {list(VALID_EMOTIONS)}"
        )
    if ai_layer is None or not getattr(ai_layer, "is_available", lambda: False)():
        raise VoiceTestingError("AI layer is not available; cannot generate test case")

    prompt = _load_prompt("voice_user_simulator")
    user_template = prompt["prompt"]["user"]
    rendered = (
        user_template.replace("{{scenario}}", scenario)
        .replace("{{emotion}}", emotion)
        .replace("{{persona}}", persona or "(no specific persona; generate naturally)")
    )
    messages = [
        {"role": "system", "content": prompt["prompt"]["system"]},
        {"role": "user", "content": rendered},
    ]
    try:
        parsed = ai_layer.generate_structured_response(messages)
    except Exception as exc:
        raise VoiceTestingError(f"simulator LLM call failed: {exc}") from exc
    if not isinstance(parsed, dict):
        raise VoiceTestingError(f"simulator returned non-dict: {parsed!r}")
    if not (parsed.get("user_input") or "").strip():
        raise VoiceTestingError("simulator returned empty user_input")
    return {
        "scenario": scenario,
        "emotion": emotion,
        "user_persona": str(parsed.get("user_persona") or "")[:300],
        "user_goal": str(parsed.get("user_goal") or "")[:500],
        "user_input": str(parsed.get("user_input")).strip(),
        "expected_behavior": str(parsed.get("expected_behavior") or "")[:1000],
        "success_criteria": list(parsed.get("success_criteria") or [])[:6],
        "failure_conditions": list(parsed.get("failure_conditions") or [])[:6],
    }


# ---------- 2. Voice executor ----------


STUB_EXECUTOR_SYSTEM_PROMPT = (
    "You are Manifest's voice assistant. The user just spoke ONE sentence. "
    "Respond briefly (1-3 short sentences), naturally, and helpfully. Acknowledge "
    "their emotional state when it's evident in their words. If they're frustrated, "
    "acknowledge briefly and propose ONE next step. If they're confused, simplify. "
    "If they're angry, stay calm and don't get defensive. If their request is "
    "ambiguous, ask ONE focused clarifying question. No bullet points — speak "
    "as a person would speak. No marketing copy."
)


VoiceExecutor = Callable[[dict[str, Any], Any], str]
"""A voice executor takes (test_case, ai_layer) and returns the assistant's
response text. The default is the LLM stub; integration tests can swap in
the real voice agent."""


def stub_voice_executor(test_case: dict[str, Any], ai_layer) -> str:
    """Default executor: a self-contained LLM call mirroring what a
    generic Manifest voice assistant would say. Does NOT touch the
    production voice_agent_service so tests don't pollute real user
    DB rows.
    """
    if ai_layer is None or not getattr(ai_layer, "is_available", lambda: False)():
        raise VoiceTestingError("AI layer is not available; cannot execute test response")
    messages = [
        {"role": "system", "content": STUB_EXECUTOR_SYSTEM_PROMPT},
        {"role": "user", "content": str(test_case.get("user_input") or "")},
    ]
    try:
        # The stub uses plain text generation — the real voice agent
        # returns structured payloads, which the evaluator doesn't need.
        return ai_layer.generate_text(messages)
    except Exception as exc:
        raise VoiceTestingError(f"executor LLM call failed: {exc}") from exc


# ---------- 3. Evaluation Agent ----------


def evaluate_response(
    *,
    ai_layer,
    test_case: dict[str, Any],
    assistant_response: str,
) -> dict[str, Any]:
    """Run the Evaluation Agent on a single test case + response."""
    if not assistant_response or not assistant_response.strip():
        # Don't burn evaluator tokens on an empty string — auto-fail.
        return {
            "scores": {
                "intent_understanding": 1,
                "emotional_awareness": 1,
                "helpfulness": 1,
            },
            "pass_status": False,
            "detected_failures": ["no_next_step", "ignored_question"],
            "root_cause_analysis": "Assistant produced no response.",
            "recommended_fixes": ["Investigate why the assistant returned an empty response."],
            "improved_response_example": "",
        }

    if ai_layer is None or not getattr(ai_layer, "is_available", lambda: False)():
        raise VoiceTestingError("AI layer is not available; cannot evaluate response")

    prompt = _load_prompt("voice_evaluator")
    user_template = prompt["prompt"]["user"]
    rendered = (
        user_template.replace("{{scenario}}", str(test_case.get("scenario") or ""))
        .replace("{{emotion}}", str(test_case.get("emotion") or ""))
        .replace("{{user_input}}", str(test_case.get("user_input") or ""))
        .replace("{{expected_behavior}}", str(test_case.get("expected_behavior") or ""))
        .replace("{{success_criteria}}", json.dumps(test_case.get("success_criteria") or []))
        .replace("{{failure_conditions}}", json.dumps(test_case.get("failure_conditions") or []))
        .replace("{{assistant_response}}", assistant_response)
    )
    messages = [
        {"role": "system", "content": prompt["prompt"]["system"]},
        {"role": "user", "content": rendered},
    ]
    try:
        parsed = ai_layer.generate_structured_response(messages)
    except Exception as exc:
        raise VoiceTestingError(f"evaluator LLM call failed: {exc}") from exc
    if not isinstance(parsed, dict):
        raise VoiceTestingError(f"evaluator returned non-dict: {parsed!r}")
    return _normalize_evaluation(parsed)


def _normalize_evaluation(raw: dict[str, Any]) -> dict[str, Any]:
    """Defensive normalization: clamp scores to 1-5, filter failure
    taxonomy to known values, ensure all three scores exist."""
    raw_scores = raw.get("scores") or {}
    scores: dict[str, int] = {}
    for key in ("intent_understanding", "emotional_awareness", "helpfulness"):
        v = raw_scores.get(key)
        try:
            n = int(v)
        except (TypeError, ValueError):
            n = 1
        scores[key] = max(1, min(5, n))

    failures_raw = raw.get("detected_failures") or []
    failures = [
        str(f).strip()
        for f in failures_raw
        if isinstance(f, str) and str(f).strip() in VALID_FAILURES
    ]

    pass_status = bool(raw.get("pass_status")) and all(
        scores[k] >= PASS_THRESHOLD_PER_DIMENSION for k in scores
    )

    return {
        "scores": scores,
        "pass_status": pass_status,
        "detected_failures": failures,
        "root_cause_analysis": str(raw.get("root_cause_analysis") or "").strip() or None,
        "recommended_fixes": list(raw.get("recommended_fixes") or [])[:8],
        "improved_response_example": str(raw.get("improved_response_example") or "").strip()
        or None,
    }


# ---------- End-to-end orchestration ----------


def run_test_case_end_to_end(
    *,
    db,
    ai_layer,
    triggered_by_user_id: str,
    scenario: str,
    emotion: str,
    persona: str | None = None,
    executor: VoiceExecutor | None = None,
    executor_kind: str = "stub",
) -> dict[str, Any]:
    """Run the three-agent pipeline for one test case and persist the result.

    Each phase opens its own cost-tracked `agent_run` (so the billing
    dashboard sees the spend), and the resulting test_run row links to
    all three. Failures in any phase mark the row as not-evaluated
    rather than dropping the data — operators can re-run.
    """
    executor = executor or stub_voice_executor

    test_run_id = str(uuid.uuid4())
    simulator_run_id: str | None = None
    executor_run_id: str | None = None
    evaluator_run_id: str | None = None
    test_case: dict[str, Any] | None = None
    assistant_response: str | None = None
    evaluation: dict[str, Any] | None = None
    error_message: str | None = None

    # ---- 1. simulator ----
    try:
        simulator_run_id = cost_tracking_service.start_agent_run(
            db=db,
            user_id=triggered_by_user_id,
            agent_kind="voice_test_simulator",
            metadata={"scenario": scenario, "emotion": emotion},
        )
        test_case = generate_test_case(
            ai_layer=ai_layer,
            scenario=scenario,
            emotion=emotion,
            persona=persona,
        )
        cost_tracking_service.log_cost_event_from_tap(
            db=db,
            user_id=triggered_by_user_id,
            agent_kind="voice_test_simulator",
            run_id=simulator_run_id,
            note="voice test simulator",
        )
        cost_tracking_service.complete_agent_run(db=db, run_id=simulator_run_id, status="complete")
    except VoiceTestingError as exc:
        error_message = f"simulator: {exc}"
        if simulator_run_id:
            cost_tracking_service.fail_agent_run(
                db=db, run_id=simulator_run_id, error_message=str(exc)
            )
        _persist_test_run(
            db=db,
            test_run_id=test_run_id,
            triggered_by_user_id=triggered_by_user_id,
            scenario=scenario,
            emotion=emotion,
            test_case=None,
            assistant_response=None,
            evaluation=None,
            simulator_run_id=simulator_run_id,
            executor_run_id=None,
            evaluator_run_id=None,
            executor_kind=executor_kind,
            error_message=error_message,
        )
        raise

    # ---- 2. executor ----
    try:
        executor_run_id = cost_tracking_service.start_agent_run(
            db=db,
            user_id=triggered_by_user_id,
            agent_kind="voice_test_executor",
            metadata={"executor_kind": executor_kind},
        )
        assistant_response = executor(test_case, ai_layer)
        cost_tracking_service.log_cost_event_from_tap(
            db=db,
            user_id=triggered_by_user_id,
            agent_kind="voice_test_executor",
            run_id=executor_run_id,
            note=f"voice test executor ({executor_kind})",
        )
        cost_tracking_service.complete_agent_run(db=db, run_id=executor_run_id, status="complete")
    except VoiceTestingError as exc:
        error_message = f"executor: {exc}"
        if executor_run_id:
            cost_tracking_service.fail_agent_run(
                db=db, run_id=executor_run_id, error_message=str(exc)
            )

    # ---- 3. evaluator ----
    if assistant_response is not None:
        try:
            evaluator_run_id = cost_tracking_service.start_agent_run(
                db=db,
                user_id=triggered_by_user_id,
                agent_kind="voice_test_evaluator",
                metadata={"scenario": scenario, "emotion": emotion},
            )
            evaluation = evaluate_response(
                ai_layer=ai_layer,
                test_case=test_case,
                assistant_response=assistant_response,
            )
            cost_tracking_service.log_cost_event_from_tap(
                db=db,
                user_id=triggered_by_user_id,
                agent_kind="voice_test_evaluator",
                run_id=evaluator_run_id,
                note="voice test evaluator",
            )
            cost_tracking_service.complete_agent_run(
                db=db, run_id=evaluator_run_id, status="complete"
            )
        except VoiceTestingError as exc:
            error_message = f"evaluator: {exc}"
            if evaluator_run_id:
                cost_tracking_service.fail_agent_run(
                    db=db, run_id=evaluator_run_id, error_message=str(exc)
                )

    return _persist_test_run(
        db=db,
        test_run_id=test_run_id,
        triggered_by_user_id=triggered_by_user_id,
        scenario=scenario,
        emotion=emotion,
        test_case=test_case,
        assistant_response=assistant_response,
        evaluation=evaluation,
        simulator_run_id=simulator_run_id,
        executor_run_id=executor_run_id,
        evaluator_run_id=evaluator_run_id,
        executor_kind=executor_kind,
        error_message=error_message,
    )


def _persist_test_run(
    *,
    db,
    test_run_id: str,
    triggered_by_user_id: str,
    scenario: str,
    emotion: str,
    test_case: dict[str, Any] | None,
    assistant_response: str | None,
    evaluation: dict[str, Any] | None,
    simulator_run_id: str | None,
    executor_run_id: str | None,
    evaluator_run_id: str | None,
    executor_kind: str,
    error_message: str | None,
) -> dict[str, Any]:
    """Idempotent insert. Always persists the row even on partial failure."""
    scores = (evaluation or {}).get("scores") or {}
    overall = None
    if scores:
        overall = round(
            (
                scores.get("intent_understanding", 0)
                + scores.get("emotional_awareness", 0)
                + scores.get("helpfulness", 0)
            )
            / 3.0,
            2,
        )

    insert = {
        "id": test_run_id,
        "scenario": scenario,
        "user_persona": (test_case or {}).get("user_persona") or "unknown",
        "user_emotion": emotion,
        "user_goal": (test_case or {}).get("user_goal"),
        "user_input": (test_case or {}).get("user_input") or "(simulator failed)",
        "expected_behavior": (test_case or {}).get("expected_behavior"),
        "success_criteria": json.dumps((test_case or {}).get("success_criteria") or []),
        "failure_conditions": json.dumps((test_case or {}).get("failure_conditions") or []),
        "assistant_response": assistant_response,
        "executor_kind": executor_kind,
        "score_intent_understanding": scores.get("intent_understanding") if evaluation else None,
        "score_emotional_awareness": scores.get("emotional_awareness") if evaluation else None,
        "score_helpfulness": scores.get("helpfulness") if evaluation else None,
        "overall_score": overall,
        "pass_status": (evaluation or {}).get("pass_status") if evaluation else None,
        "detected_failures": json.dumps((evaluation or {}).get("detected_failures") or []),
        "root_cause_analysis": (evaluation or {}).get("root_cause_analysis"),
        "recommended_fixes": json.dumps((evaluation or {}).get("recommended_fixes") or []),
        "improved_response_example": (evaluation or {}).get("improved_response_example"),
        "simulator_run_id": simulator_run_id,
        "executor_run_id": executor_run_id,
        "evaluator_run_id": evaluator_run_id,
        "triggered_by_user_id": triggered_by_user_id,
        "metadata": json.dumps({"error": error_message} if error_message else {}),
        "created_at": _now_iso(),
    }
    response = db.table(TABLE).insert(insert).execute()
    row = response.data
    if isinstance(row, list):
        row = row[0] if row else None
    if not row:
        raise VoiceTestingError("Failed to persist voice_test_run row")
    logger.info(
        "[voice_testing] run id=%s scenario=%s emotion=%s pass=%s overall=%s",
        test_run_id,
        scenario,
        emotion,
        (evaluation or {}).get("pass_status"),
        overall,
    )
    return dict(row)


# ---------- read APIs ----------


def list_recent_runs(
    *,
    db,
    limit: int = 50,
    scenario: str | None = None,
    emotion: str | None = None,
    pass_only: bool | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 50), 500))
    query = db.table(TABLE).select("*").order("created_at", desc=True).limit(limit)
    if scenario:
        query = query.eq("scenario", scenario)
    if emotion:
        query = query.eq("user_emotion", emotion)
    if pass_only is True:
        query = query.eq("pass_status", True)
    elif pass_only is False:
        query = query.eq("pass_status", False)
    response = query.execute()
    return [dict(r) for r in (response.data or [])]


def get_test_stats(*, db, hours: int = 168) -> dict[str, Any]:
    """Trailing-window roll-up for the admin dashboard. Default 7 days."""
    since_ts = datetime.now(timezone.utc).timestamp() - max(1, int(hours)) * 3600
    since_iso = datetime.fromtimestamp(since_ts, tz=timezone.utc).isoformat()
    response = (
        db.table(TABLE)
        .select("*")
        .gte("created_at", since_iso)
        .order("created_at", desc=True)
        .limit(2000)
        .execute()
    )
    rows = list(response.data or [])
    total = len(rows)
    passed = sum(1 for r in rows if r.get("pass_status") is True)
    failed = sum(1 for r in rows if r.get("pass_status") is False)
    not_evaluated = total - passed - failed

    by_scenario: dict[str, dict[str, int]] = {}
    by_emotion: dict[str, dict[str, int]] = {}
    failure_counts: dict[str, int] = {}
    score_sums = {"intent_understanding": 0, "emotional_awareness": 0, "helpfulness": 0}
    score_n = 0

    for r in rows:
        scen = str(r.get("scenario") or "unknown")
        emo = str(r.get("user_emotion") or "unknown")
        for table, key in ((by_scenario, scen), (by_emotion, emo)):
            slot = table.setdefault(key, {"total": 0, "pass": 0, "fail": 0})
            slot["total"] += 1
            if r.get("pass_status") is True:
                slot["pass"] += 1
            elif r.get("pass_status") is False:
                slot["fail"] += 1

        if r.get("score_intent_understanding") is not None:
            score_sums["intent_understanding"] += int(r.get("score_intent_understanding") or 0)
            score_sums["emotional_awareness"] += int(r.get("score_emotional_awareness") or 0)
            score_sums["helpfulness"] += int(r.get("score_helpfulness") or 0)
            score_n += 1

        failures_raw = r.get("detected_failures") or "[]"
        if isinstance(failures_raw, str):
            try:
                failures_raw = json.loads(failures_raw)
            except (TypeError, ValueError):
                failures_raw = []
        for f in failures_raw or []:
            failure_counts[str(f)] = failure_counts.get(str(f), 0) + 1

    avg_scores = {k: round(v / score_n, 2) if score_n else 0.0 for k, v in score_sums.items()}
    pass_rate = (passed / total) if total else 0.0
    return {
        "window_hours": hours,
        "total_runs": total,
        "passed": passed,
        "failed": failed,
        "not_evaluated": not_evaluated,
        "pass_rate": round(pass_rate, 4),
        "average_scores": avg_scores,
        "by_scenario": [{"scenario": k, **v} for k, v in by_scenario.items()],
        "by_emotion": [{"emotion": k, **v} for k, v in by_emotion.items()],
        "top_failures": sorted(
            ({"failure": k, "count": v} for k, v in failure_counts.items()),
            key=lambda item: item["count"],
            reverse=True,
        )[:10],
    }
