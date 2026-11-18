"""GraphQL resolvers for idea collaborators, invitations and versions."""

from datetime import datetime

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.resolvers.shared import _require_full_account
from app.graphql.types.collaboration import (
    AccessCheckResult,
    CollaborationInvitation,
    Collaborator,
    IdeaVersion,
    InviteCollaboratorInput,
    InviteResult,
    SharedIdea,
)
from app.services.ideas.versioning_policy import VERSION_KIND_MANUAL


@strawberry.type
class CollaborationQuery:
    @strawberry.field
    async def idea_collaborators(self, info: strawberry.Info, idea_id: str) -> list["Collaborator"]:
        """Get all collaborators for an idea including the owner"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        has_access = await service.check_access(idea_id, user_id, "view")
        owner = await service.get_idea_owner(idea_id)
        if not has_access and user_id != owner:
            raise Exception("You don't have access to view collaborators")

        collaborators_data = await service.get_collaborators(idea_id)

        result = []
        for c in collaborators_data:
            invited_at = None
            accepted_at = None
            if c.get("invited_at"):
                invited_at = (
                    datetime.fromisoformat(c["invited_at"].replace("Z", "+00:00"))
                    if isinstance(c["invited_at"], str)
                    else c["invited_at"]
                )
            if c.get("accepted_at"):
                accepted_at = (
                    datetime.fromisoformat(c["accepted_at"].replace("Z", "+00:00"))
                    if isinstance(c["accepted_at"], str)
                    else c["accepted_at"]
                )

            result.append(
                Collaborator(
                    collaborator_id=c.get("collaborator_id"),
                    idea_id=c["idea_id"],
                    user_id=c["user_id"],
                    role=c["role"],
                    status=c.get("status", "accepted"),
                    user_email=c.get("user_email"),
                    user_name=c.get("user_name"),
                    user_avatar=c.get("user_avatar"),
                    invited_at=invited_at,
                    accepted_at=accepted_at,
                )
            )
        return result

    @strawberry.field
    async def my_shared_ideas(self, info: strawberry.Info) -> list["SharedIdea"]:
        """Get ideas shared with the current user"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        shared_data = await service.get_shared_ideas(user_id)

        result = []
        for idea in shared_data:
            result.append(
                SharedIdea(
                    idea_id=idea["idea_id"],
                    title=idea.get("title") or "Untitled Idea",
                    description=idea.get("description"),
                    user_role=idea["user_role"],
                    created_at=(
                        datetime.fromisoformat(idea["created_at"].replace("Z", "+00:00"))
                        if isinstance(idea["created_at"], str)
                        else idea["created_at"]
                    ),
                )
            )
        return result

    @strawberry.field
    async def my_collaboration_invitations(
        self, info: strawberry.Info
    ) -> list["CollaborationInvitation"]:
        """Get pending collaboration invitations for the current user"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        invitations_data = await service.get_pending_invitations(user_id)

        result = []
        for inv in invitations_data:
            invited_at = None
            if inv.get("invited_at"):
                invited_at = (
                    datetime.fromisoformat(inv["invited_at"].replace("Z", "+00:00"))
                    if isinstance(inv["invited_at"], str)
                    else inv["invited_at"]
                )

            result.append(
                CollaborationInvitation(
                    collaborator_id=inv["collaborator_id"],
                    idea_id=inv["idea_id"],
                    role=inv["role"],
                    status=inv["status"],
                    idea_title=inv.get("idea_title"),
                    idea_description=inv.get("idea_description"),
                    inviter_name=inv.get("inviter_name"),
                    invited_at=invited_at,
                )
            )
        return result

    @strawberry.field
    async def idea_versions(self, info: strawberry.Info, idea_id: str) -> list["IdeaVersion"]:
        """Get version history for an idea"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        versions_data = await service.get_versions(idea_id, user_id)

        result = []
        for v in versions_data:
            result.append(
                IdeaVersion(
                    version_id=v["version_id"],
                    idea_id=v["idea_id"],
                    version_number=v["version_number"],
                    title=v.get("title"),
                    description=v.get("description"),
                    created_by=v["created_by"],
                    created_at=(
                        datetime.fromisoformat(v["created_at"].replace("Z", "+00:00"))
                        if isinstance(v["created_at"], str)
                        else v["created_at"]
                    ),
                    change_summary=v.get("change_summary"),
                    creator_name=v.get("creator_name"),
                    creator_avatar=v.get("creator_avatar"),
                    version_kind=v.get("version_kind") or VERSION_KIND_MANUAL,
                )
            )
        return result

    @strawberry.field
    async def check_idea_access(self, info: strawberry.Info, idea_id: str) -> "AccessCheckResult":
        """Check if current user has access to an idea and get their role"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        owner = await service.get_idea_owner(idea_id)
        if user_id == owner:
            return AccessCheckResult(has_access=True, role="owner")

        role = await service.get_user_role(idea_id, user_id)
        return AccessCheckResult(has_access=role is not None, role=role)


@strawberry.type
class CollaborationMutation:
    @strawberry.mutation
    async def invite_collaborator(
        self, info: strawberry.Info, input: "InviteCollaboratorInput"
    ) -> "InviteResult":
        """Invite a user to collaborate on an idea"""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        try:
            await service.invite_collaborator(
                idea_id=input.idea_id,
                inviter_id=user_id,
                invitee_email=input.email,
                role=input.role,
            )
            return InviteResult(success=True, message=f"Invitation sent to {input.email}")
        except ValueError as e:
            return InviteResult(success=False, message=str(e))
        except PermissionError as e:
            return InviteResult(success=False, message=str(e))
        except Exception as e:
            return InviteResult(success=False, message=f"Failed to send invitation: {str(e)}")

    @strawberry.mutation
    async def respond_to_invitation(
        self, info: strawberry.Info, idea_id: str, accept: bool
    ) -> bool:
        """Accept or decline a collaboration invitation"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        await service.respond_to_invitation(idea_id, user_id, accept)
        return True

    @strawberry.mutation
    async def update_collaborator_role(
        self, info: strawberry.Info, idea_id: str, target_user_id: str, new_role: str
    ) -> bool:
        """Update a collaborator's role"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        await service.update_collaborator_role(idea_id, user_id, target_user_id, new_role)
        return True

    @strawberry.mutation
    async def remove_collaborator(
        self, info: strawberry.Info, idea_id: str, target_user_id: str
    ) -> bool:
        """Remove a collaborator from an idea"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        return await service.remove_collaborator(idea_id, user_id, target_user_id)

    @strawberry.mutation
    async def create_idea_version(
        self, info: strawberry.Info, idea_id: str, change_summary: str | None = None
    ) -> "IdeaVersion":
        """Create a new version snapshot of an idea"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        version_data = await service.create_version(
            idea_id, user_id, change_summary, version_kind=VERSION_KIND_MANUAL
        )

        return IdeaVersion(
            version_id=version_data["version_id"],
            idea_id=version_data["idea_id"],
            version_number=version_data["version_number"],
            title=version_data.get("title"),
            description=version_data.get("description"),
            created_by=version_data["created_by"],
            created_at=(
                datetime.fromisoformat(version_data["created_at"].replace("Z", "+00:00"))
                if isinstance(version_data["created_at"], str)
                else version_data["created_at"]
            ),
            change_summary=version_data.get("change_summary"),
            version_kind=version_data.get("version_kind") or VERSION_KIND_MANUAL,
        )

    @strawberry.mutation
    async def restore_idea_version(
        self, info: strawberry.Info, idea_id: str, version_id: str
    ) -> bool:
        """Restore an idea to a previous version"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        service = create_collaboration_service(info.context["db"])

        await service.restore_version(idea_id, version_id, user_id)
        return True
