"""GraphQL resolvers for voice-platform test runs (admin only)."""

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.types.voice import (
    VoiceTestRun,
    VoiceTestStats,
    _map_voice_test_run,
    _map_voice_test_stats,
)


@strawberry.type
class VoiceQuery:
    @strawberry.field
    async def admin_voice_test_runs(
        self,
        info: strawberry.Info,
        limit: int = 50,
        scenario: str | None = None,
        emotion: str | None = None,
        pass_only: bool | None = None,
    ) -> list[VoiceTestRun]:
        """Voice-agent test runs, filterable by scenario, emotion and result."""
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
        """Voice-agent test pass rates over the last hours."""
        from app.services.voice import evaluation as vts

        payload = vts.get_test_stats(db=info.context["db"], hours=hours)
        return _map_voice_test_stats(payload)


@strawberry.type
class VoiceMutation:
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
