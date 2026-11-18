"""GraphQL resolvers for the pitch reel feed, likes, reshares and comments."""

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.pitch_reel_types import (
    PitchReel,
    PitchReelComment,
    PitchReelCommentCreateResult,
    PitchReelLikeResult,
    PitchReelShareResult,
    map_pitch_reel,
    map_pitch_reel_comment,
)


@strawberry.type
class PitchReelsQuery:
    @strawberry.field
    async def pitch_reels_feed(self, info: strawberry.Info, limit: int = 20) -> list[PitchReel]:
        """Published pitch reels joined with their Open Media clips (empty when Open Media is off)."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.integrations.open_media import settings as open_media_settings
        from app.services.pitch_reels.service import create_pitch_reel_service

        if not open_media_settings.enabled():
            return []
        service = create_pitch_reel_service(info.context["db"])
        reels_data = await service.list_feed(viewer_id=user_id, limit=max(1, min(limit, 50)))
        return [map_pitch_reel(reel) for reel in reels_data]

    @strawberry.field
    async def pitch_reel_comments(
        self, info: strawberry.Info, reel_id: str, limit: int = 120
    ) -> list[PitchReelComment]:
        """Open Media comments on a pitch reel's clip."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.pitch_reels.service import create_pitch_reel_service

        service = create_pitch_reel_service(info.context["db"])
        try:
            comments_data = await service.list_comments(
                reel_id=reel_id, viewer_id=user_id, limit=max(1, min(limit, 200))
            )
        except Exception as exc:
            raise Exception(str(exc)) from exc
        return [map_pitch_reel_comment(comment) for comment in comments_data]


@strawberry.type
class PitchReelsMutation:
    @strawberry.mutation
    async def toggle_pitch_reel_like(
        self, info: strawberry.Info, reel_id: str, liked: bool
    ) -> PitchReelLikeResult:
        """Like (``liked: true``) or unlike a pitch reel's Open Media clip."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.pitch_reels.service import create_pitch_reel_service

        service = create_pitch_reel_service(info.context["db"])
        try:
            result = await service.set_like(reel_id=reel_id, user_id=user_id, liked=liked)
        except Exception as exc:
            raise Exception(str(exc)) from exc
        return PitchReelLikeResult(
            reel_id=result["reel_id"], liked=result["liked"], like_count=result["like_count"]
        )

    @strawberry.mutation
    async def reshare_pitch_reel(
        self, info: strawberry.Info, reel_id: str, reshared: bool
    ) -> PitchReelShareResult:
        """Reshare (or undo) a pitch reel's clip on the viewer's Open Media profile."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.pitch_reels.service import create_pitch_reel_service

        service = create_pitch_reel_service(info.context["db"])
        try:
            result = await service.set_reshare(reel_id=reel_id, user_id=user_id, reshared=reshared)
        except Exception as exc:
            raise Exception(str(exc)) from exc
        return PitchReelShareResult(
            reel_id=result["reel_id"],
            reshared=result["reshared"],
            share_count=result["share_count"],
        )

    @strawberry.mutation
    async def create_pitch_reel_comment(
        self, info: strawberry.Info, reel_id: str, body: str
    ) -> PitchReelCommentCreateResult:
        """Comment on a pitch reel's Open Media clip."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.pitch_reels.service import create_pitch_reel_service

        service = create_pitch_reel_service(info.context["db"])
        try:
            result = await service.create_comment(reel_id=reel_id, user_id=user_id, body=body)
        except Exception as exc:
            raise Exception(str(exc)) from exc
        return PitchReelCommentCreateResult(comment=map_pitch_reel_comment(result["comment"]))
