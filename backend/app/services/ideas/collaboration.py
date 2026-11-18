"""
Collaboration Service
Handles team collaboration, access management (Google Docs-style), and version control for ideas
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from app.services.ideas.versioning_policy import (
    VERSION_KIND_AUTO,
    VERSION_KIND_MANUAL,
    VERSION_KIND_SYSTEM,
    auto_version_max_auto_per_idea,
    auto_version_min_interval_seconds,
    compute_content_hash,
    compute_content_hash_from_version_row,
)
from app.utils.logger import logger


class CollaborationService:
    """Service for managing idea collaboration, access control, and version history"""

    ROLE_OWNER = "owner"
    ROLE_EDITOR = "editor"
    ROLE_COMMENTER = "commenter"
    ROLE_VIEWER = "viewer"

    ROLE_PERMISSIONS = {
        "owner": {"view", "edit", "comment", "delete", "share", "manage_access"},
        "editor": {"view", "edit", "comment"},
        "commenter": {"view", "comment"},
        "viewer": {"view"},
    }

    def __init__(self, db):
        self.db = db
        self.collaborators_table = "idea_collaborators"
        self.versions_table = "idea_versions"
        self.ideas_table = "ideas"
        # Deprecated: use AUTO_VERSION_MIN_INTERVAL_SECONDS (see idea_versioning_policy).
        self.AUTO_VERSION_INTERVAL_MINUTES = 5

    async def get_idea_owner(self, idea_id: str) -> str | None:
        """Get the owner user_id of an idea"""
        try:
            response = (
                self.db.table(self.ideas_table)
                .select("user_id")
                .eq("idea_id", idea_id)
                .single()
                .execute()
            )
            return response.data.get("user_id") if response.data else None
        except Exception as e:
            logger.error(f"[CollaborationService] Error getting idea owner: {e}")
            return None

    async def check_access(self, idea_id: str, user_id: str, permission: str = "view") -> bool:
        """Check if a user has a specific permission on an idea"""
        try:
            idea_owner = await self.get_idea_owner(idea_id)
            if idea_owner == user_id:
                return True

            response = (
                self.db.table(self.collaborators_table)
                .select("role, status")
                .eq("idea_id", idea_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if not response.data or response.data.get("status") != "accepted":
                return False

            role = response.data.get("role", "viewer")
            allowed_permissions = self.ROLE_PERMISSIONS.get(role, set())
            return permission in allowed_permissions

        except Exception as e:
            logger.error(f"[CollaborationService] Error checking access: {e}")
            return False

    async def get_user_role(self, idea_id: str, user_id: str) -> str | None:
        """Get the user's role for an idea"""
        try:
            idea_owner = await self.get_idea_owner(idea_id)
            if idea_owner == user_id:
                return self.ROLE_OWNER

            response = (
                self.db.table(self.collaborators_table)
                .select("role")
                .eq("idea_id", idea_id)
                .eq("user_id", user_id)
                .eq("status", "accepted")
                .single()
                .execute()
            )

            return response.data.get("role") if response.data else None
        except Exception:
            return None

    async def invite_collaborator(
        self, idea_id: str, inviter_id: str, invitee_email: str, role: str = "viewer"
    ) -> dict[str, Any]:
        """Invite a user to collaborate on an idea"""
        if role not in self.ROLE_PERMISSIONS:
            raise ValueError(f"Invalid role: {role}")

        has_access = await self.check_access(idea_id, inviter_id, "share")
        if not has_access:
            raise PermissionError("You don't have permission to share this idea")

        try:
            user_response = (
                self.db.table("users")
                .select("user_id")
                .eq("email", invitee_email)
                .single()
                .execute()
            )

            if not user_response.data:
                raise ValueError("User not found with that email")

            invitee_id = user_response.data["user_id"]

            if invitee_id == inviter_id:
                raise ValueError("You cannot invite yourself")

            idea_owner = await self.get_idea_owner(idea_id)
            if invitee_id == idea_owner:
                raise ValueError("Cannot change the owner's access")

            collaborator_data = {
                "collaborator_id": str(uuid4()),
                "idea_id": idea_id,
                "user_id": invitee_id,
                "role": role,
                "invited_by": inviter_id,
                "invited_at": datetime.utcnow().isoformat(),
                "status": "pending",
            }

            response = (
                self.db.table(self.collaborators_table)
                .upsert(collaborator_data, on_conflict="idea_id,user_id")
                .execute()
            )

            if response.data:
                logger.info(
                    f"[CollaborationService] Invited {invitee_email} to idea {idea_id} as {role}"
                )
                return response.data
            raise Exception("Failed to invite collaborator")

        except Exception as e:
            logger.error(f"[CollaborationService] Error inviting collaborator: {e}")
            raise

    async def respond_to_invitation(
        self, idea_id: str, user_id: str, accept: bool
    ) -> dict[str, Any]:
        """Accept or decline a collaboration invitation"""
        try:
            status = "accepted" if accept else "declined"
            update_data = {
                "status": status,
                "accepted_at": datetime.utcnow().isoformat() if accept else None,
            }

            response = (
                self.db.table(self.collaborators_table)
                .update(update_data)
                .eq("idea_id", idea_id)
                .eq("user_id", user_id)
                .eq("status", "pending")
                .execute()
            )

            if response.data:
                logger.info(
                    f"[CollaborationService] User {user_id} {status} invitation for idea {idea_id}"
                )
                return response.data
            raise Exception("Invitation not found or already responded")

        except Exception as e:
            logger.error(f"[CollaborationService] Error responding to invitation: {e}")
            raise

    async def update_collaborator_role(
        self, idea_id: str, updater_id: str, target_user_id: str, new_role: str
    ) -> dict[str, Any]:
        """Update a collaborator's role"""
        if new_role not in self.ROLE_PERMISSIONS or new_role == "owner":
            raise ValueError(f"Invalid role: {new_role}")

        has_access = await self.check_access(idea_id, updater_id, "manage_access")
        if not has_access:
            raise PermissionError("You don't have permission to manage access")

        idea_owner = await self.get_idea_owner(idea_id)
        if target_user_id == idea_owner:
            raise ValueError("Cannot change the owner's role")

        try:
            response = (
                self.db.table(self.collaborators_table)
                .update({"role": new_role})
                .eq("idea_id", idea_id)
                .eq("user_id", target_user_id)
                .execute()
            )

            if response.data:
                logger.info(
                    f"[CollaborationService] Updated role for {target_user_id} to {new_role}"
                )
                return response.data
            raise Exception("Collaborator not found")

        except Exception as e:
            logger.error(f"[CollaborationService] Error updating role: {e}")
            raise

    async def remove_collaborator(self, idea_id: str, remover_id: str, target_user_id: str) -> bool:
        """Remove a collaborator from an idea"""
        has_access = await self.check_access(idea_id, remover_id, "manage_access")
        is_self_removal = remover_id == target_user_id

        if not has_access and not is_self_removal:
            raise PermissionError("You don't have permission to remove collaborators")

        idea_owner = await self.get_idea_owner(idea_id)
        if target_user_id == idea_owner:
            raise ValueError("Cannot remove the owner")

        try:
            self.db.table(self.collaborators_table).delete().eq("idea_id", idea_id).eq(
                "user_id", target_user_id
            ).execute()

            logger.info(
                f"[CollaborationService] Removed collaborator {target_user_id} from idea {idea_id}"
            )
            return True

        except Exception as e:
            logger.error(f"[CollaborationService] Error removing collaborator: {e}")
            raise

    async def get_collaborators(self, idea_id: str) -> list[dict[str, Any]]:
        """Get all collaborators for an idea including the owner"""
        try:
            idea_owner = await self.get_idea_owner(idea_id)

            owner_response = (
                self.db.table("users")
                .select("user_id, email, username, first_name, last_name, profile_picture_url")
                .eq("user_id", idea_owner)
                .single()
                .execute()
            )

            collaborators = []
            if owner_response.data:
                owner = owner_response.data
                collaborators.append(
                    {
                        "collaborator_id": None,
                        "idea_id": idea_id,
                        "user_id": owner["user_id"],
                        "role": "owner",
                        "status": "accepted",
                        "user_email": owner.get("email"),
                        "user_name": _full_name(owner)
                        or owner.get("username")
                        or owner.get("email"),
                        "user_avatar": owner.get("profile_picture_url"),
                    }
                )

            collab_response = (
                self.db.table(self.collaborators_table).select("*").eq("idea_id", idea_id).execute()
            )

            if collab_response.data:
                for collab in collab_response.data:
                    user_response = (
                        self.db.table("users")
                        .select("email, username, first_name, last_name, profile_picture_url")
                        .eq("user_id", collab["user_id"])
                        .single()
                        .execute()
                    )

                    user = user_response.data or {}
                    collaborators.append(
                        {
                            **collab,
                            "user_email": user.get("email"),
                            "user_name": _full_name(user)
                            or user.get("username")
                            or user.get("email"),
                            "user_avatar": user.get("profile_picture_url"),
                        }
                    )

            return collaborators

        except Exception as e:
            logger.error(f"[CollaborationService] Error getting collaborators: {e}")
            return []

    async def get_shared_ideas(self, user_id: str) -> list[dict[str, Any]]:
        """Get all ideas shared with a user"""
        try:
            response = (
                self.db.table(self.collaborators_table)
                .select("idea_id, role, status")
                .eq("user_id", user_id)
                .eq("status", "accepted")
                .execute()
            )

            if not response.data:
                return []

            shared_ideas = []
            for collab in response.data:
                idea_response = (
                    self.db.table(self.ideas_table)
                    .select("*")
                    .eq("idea_id", collab["idea_id"])
                    .single()
                    .execute()
                )

                if idea_response.data:
                    shared_ideas.append(
                        {
                            **idea_response.data,
                            "user_role": collab["role"],
                        }
                    )

            return shared_ideas

        except Exception as e:
            logger.error(f"[CollaborationService] Error getting shared ideas: {e}")
            return []

    async def get_pending_invitations(self, user_id: str) -> list[dict[str, Any]]:
        """Get pending collaboration invitations for a user"""
        try:
            response = (
                self.db.table(self.collaborators_table)
                .select("*")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .execute()
            )

            if not response.data:
                return []

            invitations = []
            for inv in response.data:
                idea_response = (
                    self.db.table(self.ideas_table)
                    .select("title, description")
                    .eq("idea_id", inv["idea_id"])
                    .single()
                    .execute()
                )

                inviter_response = (
                    self.db.table("users")
                    .select("email, username, first_name, last_name")
                    .eq("user_id", inv["invited_by"])
                    .single()
                    .execute()
                )

                idea = idea_response.data or {}
                inviter = inviter_response.data or {}

                invitations.append(
                    {
                        **inv,
                        "idea_title": idea.get("title"),
                        "idea_description": idea.get("description"),
                        "inviter_name": _full_name(inviter)
                        or inviter.get("username")
                        or inviter.get("email"),
                    }
                )

            return invitations

        except Exception as e:
            logger.error(f"[CollaborationService] Error getting invitations: {e}")
            return []

    async def create_version(
        self,
        idea_id: str,
        user_id: str,
        change_summary: str | None = None,
        *,
        version_kind: str = VERSION_KIND_MANUAL,
        content_hash: str | None = None,
    ) -> dict[str, Any]:
        """Create a new version snapshot of an idea"""
        has_access = await self.check_access(idea_id, user_id, "edit")
        idea_owner = await self.get_idea_owner(idea_id)

        if not has_access and user_id != idea_owner:
            raise PermissionError("You don't have permission to create versions")

        try:
            idea_response = (
                self.db.table(self.ideas_table)
                .select("*")
                .eq("idea_id", idea_id)
                .single()
                .execute()
            )

            if not idea_response.data:
                raise ValueError("Idea not found")

            idea = idea_response.data
            snapshot_hash = content_hash or compute_content_hash(idea)

            latest_version = (
                self.db.table(self.versions_table)
                .select("version_number")
                .eq("idea_id", idea_id)
                .order("version_number", desc=True)
                .limit(1)
                .execute()
            )

            next_version = 1
            if latest_version.data:
                next_version = latest_version.data[0]["version_number"] + 1

            version_data = {
                "version_id": str(uuid4()),
                "idea_id": idea_id,
                "version_number": next_version,
                "title": idea.get("title"),
                "description": idea.get("description"),
                "business_model_canvas": idea.get("business_model_canvas"),
                "pitch_deck": idea.get("pitch_deck"),
                "product_requirements_document": idea.get("product_requirements_document"),
                "provisional_patent": idea.get("provisional_patent"),
                "created_by": user_id,
                "created_at": datetime.utcnow().isoformat(),
                "change_summary": change_summary or f"Version {next_version}",
                "version_kind": version_kind,
                "content_hash": snapshot_hash,
            }

            response = self.db.table(self.versions_table).insert(version_data).execute()

            if response.data:
                logger.info(
                    f"[CollaborationService] Created version {next_version} for idea {idea_id}"
                )
                out = response.data
                if isinstance(out, list) and len(out) > 0:
                    out = out[0]
                return out
            raise Exception("Failed to create version")

        except Exception as e:
            logger.error(f"[CollaborationService] Error creating version: {e}")
            raise

    async def get_versions(self, idea_id: str, user_id: str) -> list[dict[str, Any]]:
        """Get version history for an idea"""
        has_access = await self.check_access(idea_id, user_id, "view")
        idea_owner = await self.get_idea_owner(idea_id)

        if not has_access and user_id != idea_owner:
            raise PermissionError("You don't have permission to view versions")

        try:
            response = (
                self.db.table(self.versions_table)
                .select("*")
                .eq("idea_id", idea_id)
                .order("version_number", desc=True)
                .execute()
            )

            if not response.data:
                return []

            versions = []
            for ver in response.data:
                user_response = (
                    self.db.table("users")
                    .select("email, username, first_name, last_name, profile_picture_url")
                    .eq("user_id", ver["created_by"])
                    .single()
                    .execute()
                )

                user = user_response.data or {}
                versions.append(
                    {
                        **ver,
                        "creator_name": _full_name(user)
                        or user.get("username")
                        or user.get("email"),
                        "creator_avatar": user.get("profile_picture_url"),
                    }
                )

            return versions

        except Exception as e:
            logger.error(f"[CollaborationService] Error getting versions: {e}")
            return []

    async def restore_version(self, idea_id: str, version_id: str, user_id: str) -> dict[str, Any]:
        """Restore an idea to a previous version"""
        has_access = await self.check_access(idea_id, user_id, "edit")
        idea_owner = await self.get_idea_owner(idea_id)

        if not has_access and user_id != idea_owner:
            raise PermissionError("You don't have permission to restore versions")

        try:
            await self.create_version(
                idea_id,
                user_id,
                "Auto-saved before restore",
                version_kind=VERSION_KIND_SYSTEM,
            )

            version_response = (
                self.db.table(self.versions_table)
                .select("*")
                .eq("version_id", version_id)
                .eq("idea_id", idea_id)
                .single()
                .execute()
            )

            if not version_response.data:
                raise ValueError("Version not found")

            version = version_response.data

            update_data = {
                "title": version.get("title"),
                "description": version.get("description"),
                "business_model_canvas": version.get("business_model_canvas"),
                "pitch_deck": version.get("pitch_deck"),
                "product_requirements_document": version.get("product_requirements_document"),
                "provisional_patent": version.get("provisional_patent"),
            }

            response = (
                self.db.table(self.ideas_table).update(update_data).eq("idea_id", idea_id).execute()
            )

            if response.data:
                await self.create_version(
                    idea_id,
                    user_id,
                    f"Restored to version {version.get('version_number')}",
                    version_kind=VERSION_KIND_SYSTEM,
                )
                logger.info(
                    f"[CollaborationService] Restored idea {idea_id} to version {version_id}"
                )
                return response.data
            raise Exception("Failed to restore version")

        except Exception as e:
            logger.error(f"[CollaborationService] Error restoring version: {e}")
            raise

    @staticmethod
    def _parse_to_naive_utc(value) -> datetime | None:
        """Parse a datetime value into a naive UTC datetime for safe comparison."""
        if value is None:
            return None
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if hasattr(value, "tzinfo") and value.tzinfo is not None:
            value = value.replace(tzinfo=None)
        return value

    async def _prune_excess_auto_versions(self, idea_id: str) -> int:
        """Delete oldest auto snapshots when a per-idea cap is configured. Returns rows removed."""
        max_keep = auto_version_max_auto_per_idea()
        if max_keep <= 0:
            return 0
        deleted = 0
        try:
            resp = (
                self.db.table(self.versions_table)
                .select("version_id")
                .eq("idea_id", idea_id)
                .eq("version_kind", VERSION_KIND_AUTO)
                .order("created_at", desc=False)
                .execute()
            )
            rows = resp.data or []
            if isinstance(rows, dict):
                rows = [rows]
            excess = len(rows) - max_keep
            if excess <= 0:
                return 0
            for row in rows[:excess]:
                vid = row.get("version_id")
                if vid:
                    self.db.table(self.versions_table).delete().eq("version_id", vid).execute()
                    deleted += 1
            if deleted:
                logger.info(
                    f"[CollaborationService] Pruned {deleted} auto version(s) for idea {idea_id}"
                )
        except Exception as e:
            logger.warning(f"[CollaborationService] Auto-version prune skipped: {e}")
        return deleted

    async def maybe_record_auto_version_after_user_edit(
        self, idea_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """
        After a successful user-driven save (GraphQL/REST), record an auto snapshot when
        content changed vs the latest version and the min interval since the last *auto*
        snapshot has elapsed.
        """
        has_access = await self.check_access(idea_id, user_id, "edit")
        idea_owner = await self.get_idea_owner(idea_id)
        if not has_access and user_id != idea_owner:
            return None

        try:
            idea_response = (
                self.db.table(self.ideas_table)
                .select("*")
                .eq("idea_id", idea_id)
                .single()
                .execute()
            )
            if not idea_response.data:
                return None
            idea = idea_response.data
            current_hash = compute_content_hash(idea)

            latest = (
                self.db.table(self.versions_table)
                .select(
                    "version_number,content_hash,title,description,business_model_canvas,"
                    "pitch_deck,product_requirements_document,provisional_patent"
                )
                .eq("idea_id", idea_id)
                .order("version_number", desc=True)
                .limit(1)
                .execute()
            )
            rows = latest.data
            if isinstance(rows, dict):
                rows = [rows]
            if rows:
                ver = rows[0]
                prev_hash = ver.get("content_hash") if isinstance(ver, dict) else None
                if not prev_hash:
                    prev_hash = compute_content_hash_from_version_row(ver)
                if prev_hash == current_hash:
                    return None

            latest_auto = (
                self.db.table(self.versions_table)
                .select("created_at")
                .eq("idea_id", idea_id)
                .eq("version_kind", VERSION_KIND_AUTO)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            auto_rows = latest_auto.data
            if isinstance(auto_rows, dict):
                auto_rows = [auto_rows]
            if auto_rows:
                last_auto_raw = (
                    auto_rows[0].get("created_at") if isinstance(auto_rows[0], dict) else None
                )
                last_auto = self._parse_to_naive_utc(last_auto_raw)
                if last_auto is not None:
                    min_sec = auto_version_min_interval_seconds()
                    if datetime.utcnow() - last_auto < timedelta(seconds=min_sec):
                        return None

            created = await self.create_version(
                idea_id,
                user_id,
                "Auto-saved",
                version_kind=VERSION_KIND_AUTO,
                content_hash=current_hash,
            )
            await self._prune_excess_auto_versions(idea_id)
            return created
        except Exception as e:
            logger.warning(f"[CollaborationService] maybe_record_auto_version_after_user_edit: {e}")
            return None

    async def prune_auto_versions_for_idea(self, idea_id: str) -> int:
        """Enforce auto-version cap for one idea (e.g. maintenance). Returns rows deleted."""
        return await self._prune_excess_auto_versions(idea_id)

    async def prune_excess_auto_versions_all_ideas(self) -> int:
        """Run auto-version retention across all ideas (optional cron / script)."""
        total = 0
        try:
            ideas_resp = self.db.table(self.ideas_table).select("idea_id").execute()
            rows = ideas_resp.data or []
            if isinstance(rows, dict):
                rows = [rows]
            for row in rows:
                iid = row.get("idea_id") if isinstance(row, dict) else None
                if iid:
                    total += await self._prune_excess_auto_versions(iid)
        except Exception as e:
            logger.warning(f"[CollaborationService] prune_excess_auto_versions_all_ideas: {e}")
        return total

    async def get_version_diff(
        self, idea_id: str, version_id_a: str, version_id_b: str, user_id: str
    ) -> dict[str, Any]:
        """Get the differences between two versions"""
        has_access = await self.check_access(idea_id, user_id, "view")
        idea_owner = await self.get_idea_owner(idea_id)

        if not has_access and user_id != idea_owner:
            raise PermissionError("You don't have permission to view versions")

        try:
            version_a = (
                self.db.table(self.versions_table)
                .select("*")
                .eq("version_id", version_id_a)
                .single()
                .execute()
            )

            version_b = (
                self.db.table(self.versions_table)
                .select("*")
                .eq("version_id", version_id_b)
                .single()
                .execute()
            )

            if not version_a.data or not version_b.data:
                raise ValueError("One or both versions not found")

            diff = {
                "version_a": version_a.data,
                "version_b": version_b.data,
                "changes": {},
            }

            fields = [
                "title",
                "description",
                "business_model_canvas",
                "pitch_deck",
                "product_requirements_document",
                "provisional_patent",
            ]

            for field in fields:
                val_a = version_a.data.get(field)
                val_b = version_b.data.get(field)
                if val_a != val_b:
                    diff["changes"][field] = {
                        "old": val_a,
                        "new": val_b,
                    }

            return diff

        except Exception as e:
            logger.error(f"[CollaborationService] Error getting version diff: {e}")
            raise


def _full_name(user: dict) -> str:
    """First and last name; never "None None" when the profile has no name yet."""
    return " ".join(part for part in (user.get("first_name"), user.get("last_name")) if part)


def create_collaboration_service(db) -> CollaborationService:
    """Factory function to create a CollaborationService instance"""
    return CollaborationService(db)
