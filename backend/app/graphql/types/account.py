"""GraphQL types and mappers for your account, sessions, guest sessions and privacy status."""

from datetime import datetime

import strawberry


@strawberry.type
class User:
    user_id: str
    email: str
    created_at: datetime
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    country: str | None = None
    bio: str | None = None
    address: str | None = None
    state: str | None = None
    gravatar_hash: str | None = None
    profile_picture_url: str | None = None
    skills: list[str] = strawberry.field(default_factory=list)


@strawberry.input
class AccountUpdateInput:
    email: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    country: str | None = None
    bio: str | None = None
    address: str | None = None
    state: str | None = None
    gravatar_hash: str | None = None
    profile_picture_url: str | None = None
    skills: list[str] | None = None


@strawberry.type
class AuthUser:
    user_id: str
    email: str
    token: str
    is_guest: bool = False


@strawberry.type
class SessionInfo:
    session_id: str
    current: bool
    created_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_seen_at: datetime | None = None
    request_ip: str | None = None
    user_agent: str | None = None
    kind: str = strawberry.field(
        default="browser",
        description="`browser` or `cli` (a Manifest CLI session; `userAgent` holds its label).",
    )


@strawberry.type
class PrivacyStatus:
    export_available: bool
    deletion_requested_at: datetime | None = None
    guest_retention_days: int = 30


@strawberry.type
class GuestSessionResult:
    """Returned only from start_guest_session; includes one-time merge secret."""

    user_id: str
    email: str
    token: str
    merge_secret: str
