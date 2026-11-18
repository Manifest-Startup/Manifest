"""GraphQL types and mappers for profiles, follows and social stats."""

from datetime import datetime

import strawberry


@strawberry.type
class UserFollow:
    follow_id: str
    follower_id: str
    followed_id: str
    created_at: datetime
    user_name: str | None = None
    user_avatar: str | None = None


@strawberry.type
class FollowResult:
    following: bool
    followed_id: str


@strawberry.type
class SocialStats:
    follower_count: int
    following_count: int
    is_following: bool = False
