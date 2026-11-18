"""GraphQL types and mappers for voice-platform test runs (admin only)."""

import json
from typing import Any

import strawberry


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
