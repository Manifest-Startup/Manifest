"""GraphQL resolvers for Business Model Canvas sections and partner discovery."""

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.types.canvas import (
    BmcSection,
    PartnerCandidate,
    _map_bmc_section,
    _map_partner_candidate,
)


@strawberry.type
class CanvasQuery:
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


@strawberry.type
class CanvasMutation:
    @strawberry.mutation
    async def save_bmc_section(
        self, info: strawberry.Info, idea_id: str, section_name: str, content: str
    ) -> BmcSection:
        """Save one Business Model Canvas section you wrote (Markdown), marked as a user edit.
        Sections: customer_segments, value_propositions, channels, customer_relationships,
        revenue_streams, key_resources, key_activities, key_partners, cost_structure."""
        from app.services.canvas import orchestrator as bmc
        from app.services.ideas.collaboration import CollaborationService

        user_id = str(get_current_user_id(info.context["request"]))
        role = await CollaborationService(info.context["db"]).get_user_role(idea_id, user_id)
        if role not in ("owner", "editor"):
            raise Exception("Idea not found or you don't have permission to edit it")
        try:
            row = bmc.save_user_section(
                db=info.context["db"], idea_id=idea_id, section_name=section_name, content=content
            )
        except bmc.BmcSectionError as exc:
            raise Exception(str(exc)) from exc
        return _map_bmc_section(row)

    @strawberry.mutation
    async def regenerate_bmc_section(
        self, info: strawberry.Info, idea_id: str, section_name: str
    ) -> BmcSection:
        """Regenerate one Business Model Canvas section of an idea."""
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
        """Regenerate every Business Model Canvas section of an idea."""
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
