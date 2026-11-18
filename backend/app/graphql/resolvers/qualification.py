"""GraphQL resolvers for the multi-turn idea qualification agent."""

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.types.qualification import IdeaQualificationSession, _map_qualification_session


@strawberry.type
class QualificationQuery:
    @strawberry.field
    async def idea_qualification_session(
        self, info: strawberry.Info, session_id: str
    ) -> IdeaQualificationSession | None:
        """Read one idea-qualification interview: questions, answers and verdict."""
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
        """List your idea-qualification interviews."""
        from app.services.ai import idea_qualification as qs

        user_id = get_current_user_id(info.context["request"])
        rows = qs.list_sessions(db=info.context["db"], user_id=user_id)
        return [_map_qualification_session(r) for r in rows]


@strawberry.type
class QualificationMutation:
    @strawberry.mutation
    async def start_idea_qualification(
        self, info: strawberry.Info, initial_idea_text: str
    ) -> IdeaQualificationSession:
        """Start an idea-qualification interview from a rough idea; returns the first questions."""
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
        """Answer the current questions in an idea-qualification interview."""
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
