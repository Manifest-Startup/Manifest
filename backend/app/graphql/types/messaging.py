"""GraphQL types and mappers for Open Media conversations, messages and account link."""

import strawberry


@strawberry.type
class IdeaOwner:
    user_id: str
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    bio: str | None = None
    profile_picture_url: str | None = None
    idea_id: str
    idea_title: str | None = None
    is_published: bool = False
    can_message: bool = False
    open_media_handle: str | None = None
