"""GraphQL types and mappers for idea collaborators, invitations and versions."""

from datetime import datetime

import strawberry


@strawberry.type
class Collaborator:
    collaborator_id: str | None
    idea_id: str
    user_id: str
    role: str
    status: str
    user_email: str | None = None
    user_name: str | None = None
    user_avatar: str | None = None
    invited_at: datetime | None = None
    accepted_at: datetime | None = None


@strawberry.type
class IdeaVersion:
    version_id: str
    idea_id: str
    version_number: int
    title: str | None = None
    description: str | None = None
    created_by: str
    created_at: datetime
    change_summary: str | None = None
    creator_name: str | None = None
    creator_avatar: str | None = None
    version_kind: str | None = None


@strawberry.type
class CollaborationInvitation:
    collaborator_id: str
    idea_id: str
    role: str
    status: str
    idea_title: str | None = None
    idea_description: str | None = None
    inviter_name: str | None = None
    invited_at: datetime | None = None


@strawberry.type
class SharedIdea:
    idea_id: str
    title: str
    description: str | None = None
    user_role: str
    created_at: datetime


@strawberry.type
class AccessCheckResult:
    has_access: bool
    role: str | None = None


@strawberry.type
class InviteResult:
    success: bool
    message: str


@strawberry.input
class InviteCollaboratorInput:
    idea_id: str
    email: str
    role: str = "viewer"
