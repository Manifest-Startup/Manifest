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
class LiveNoteParticipant:
    """Someone in an idea's note right now (ADR 0008)."""

    user_id: str
    name: str
    avatar_url: str | None
    color: str
    via: str = strawberry.field(description="app, agent or cli")
    via_label: str
    can_edit: bool
    role: str | None = None
    last_active_at: datetime | None = None


def live_note_participant_from_dict(row: dict) -> LiveNoteParticipant:
    last = row.get("lastActiveAt")
    return LiveNoteParticipant(
        user_id=row["userId"],
        name=row.get("name") or "Someone",
        avatar_url=row.get("avatarUrl"),
        color=row.get("color") or "#2563eb",
        via=row.get("via") or "app",
        via_label=row.get("viaLabel") or "Manifest",
        can_edit=bool(row.get("canEdit")),
        role=row.get("role"),
        last_active_at=datetime.fromtimestamp(last).astimezone() if last else None,
    )


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
