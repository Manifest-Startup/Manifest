"""GraphQL resolvers for profiles, follows and social stats."""

import asyncio
from datetime import datetime

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.resolvers.shared import _display_name, _require_full_account
from app.graphql.types.account import AuthUser
from app.graphql.types.social import FollowResult, SocialStats, UserFollow
from app.utils.logger import logger
from fastapi import HTTPException


@strawberry.type
class SocialQuery:
    @strawberry.field
    async def profile(self, info: strawberry.Info) -> AuthUser | None:
        # Attempt to resolve the current user.  If no access_token is
        # present (first page load, logged-out visitor), `get_current_user_id`
        # raises HTTP 401.  We intercept that specific case so the resolver
        # simply returns `null` instead of bubbling an error up the GraphQL
        # stack – this keeps the backend logs clean on startup.
        """The signed-in person's basic identity (id, email, display name)."""
        try:
            user_id = get_current_user_id(info.context["request"])
        except HTTPException as exc:
            if exc.status_code == 401:  # Missing/invalid token – treat as anonymous user
                logger.info("[schema.profile] No valid session detected – returning null profile")
                return None
            raise  # Re-raise other auth errors
        if not user_id:
            return None

        # Profile gates the entire workspace on a reload. Keep its database
        # read off the event loop and avoid loading unrelated account fields.
        def _load_profile():
            return (
                info.context["db"]
                .table("users")
                .select("user_id, email, is_guest")
                .eq("user_id", user_id)
                .single()
                .execute()
            )

        response = await asyncio.to_thread(_load_profile)
        if not response.data:
            return None

        token = (
            info.context["request"].cookies.get("session_token")
            or info.context["request"].cookies.get("access_token")
            or ""
        )

        user_data = response.data
        if not user_data.get("user_id") or not user_data.get("email"):
            return None

        is_guest = bool(user_data.get("is_guest", False))
        return AuthUser(
            user_id=user_data["user_id"],
            email=user_data["email"],
            token=token,
            is_guest=is_guest,
        )

    @strawberry.field
    async def user_followers(self, info: strawberry.Info, user_id: str) -> list[UserFollow]:
        """Get followers for a user"""
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])
        followers_data = await service.get_followers(user_id)

        followers = []
        for f in followers_data:
            user = f.get("follower", {}) or {}
            followers.append(
                UserFollow(
                    follow_id=f["follow_id"],
                    follower_id=f["follower_id"],
                    followed_id=f["followed_id"],
                    created_at=(
                        datetime.fromisoformat(f["created_at"].replace("Z", "+00:00"))
                        if isinstance(f["created_at"], str)
                        else f["created_at"]
                    ),
                    user_name=_display_name(user),
                    user_avatar=user.get("profile_picture_url"),
                )
            )
        return followers

    @strawberry.field
    async def user_following(self, info: strawberry.Info, user_id: str) -> list[UserFollow]:
        """Get users that a user is following"""
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])
        following_data = await service.get_following(user_id)

        following = []
        for f in following_data:
            user = f.get("followed", {}) or {}
            following.append(
                UserFollow(
                    follow_id=f["follow_id"],
                    follower_id=f["follower_id"],
                    followed_id=f["followed_id"],
                    created_at=(
                        datetime.fromisoformat(f["created_at"].replace("Z", "+00:00"))
                        if isinstance(f["created_at"], str)
                        else f["created_at"]
                    ),
                    user_name=_display_name(user),
                    user_avatar=user.get("profile_picture_url"),
                )
            )
        return following

    @strawberry.field
    async def user_social_stats(self, info: strawberry.Info, user_id: str) -> SocialStats:
        """Get social statistics for a user"""
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])

        follower_count = await service.get_follower_count(user_id)
        following_count = await service.get_following_count(user_id)

        is_following = False
        try:
            current_user_id = get_current_user_id(info.context["request"])
            if current_user_id and current_user_id != user_id:
                is_following = await service.is_following(current_user_id, user_id)
        except Exception:
            pass

        return SocialStats(
            follower_count=follower_count,
            following_count=following_count,
            is_following=is_following,
        )


@strawberry.type
class SocialMutation:
    @strawberry.mutation
    async def follow_user(self, info: strawberry.Info, followed_id: str) -> FollowResult:
        """Follow a user"""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])

        await service.follow_user(user_id, followed_id)
        return FollowResult(following=True, followed_id=followed_id)

    @strawberry.mutation
    async def unfollow_user(self, info: strawberry.Info, followed_id: str) -> FollowResult:
        """Unfollow a user"""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])

        await service.unfollow_user(user_id, followed_id)
        return FollowResult(following=False, followed_id=followed_id)

    @strawberry.mutation
    async def toggle_follow(self, info: strawberry.Info, followed_id: str) -> FollowResult:
        """Toggle follow status for a user"""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])

        result = await service.toggle_follow(user_id, followed_id)
        return FollowResult(following=result["following"], followed_id=result["followed_id"])
