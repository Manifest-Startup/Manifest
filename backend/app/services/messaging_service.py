"""
Messaging Service for Manifest
Handles encrypted messaging between users for startup collaboration.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.utils.logger import logger


class MessagingService:
    """Service for managing encrypted messaging between users."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _first_row(data: Any) -> dict[str, Any] | None:
        """Normalize db responses that may return either a list or a single row dict."""
        if isinstance(data, list):
            return data[0] if data else None
        if isinstance(data, dict):
            return data
        return None

    @staticmethod
    def _rows_by_id(rows: Any, key: str) -> dict[str, dict[str, Any]]:
        if not isinstance(rows, list):
            return {}
        return {str(row.get(key)): row for row in rows if row.get(key)}

    def _fetch_users_by_id(self, user_ids: list[str], columns: str) -> dict[str, dict[str, Any]]:
        unique_ids = sorted({user_id for user_id in user_ids if user_id})
        if not unique_ids:
            return {}

        response = self.db.table("users").select(columns).in_("user_id", unique_ids).execute()
        return self._rows_by_id(response.data, "user_id")

    def _fetch_ideas_by_id(self, idea_ids: list[str]) -> dict[str, dict[str, Any]]:
        unique_ids = sorted({idea_id for idea_id in idea_ids if idea_id})
        if not unique_ids:
            return {}

        response = (
            self.db.table("ideas").select("idea_id, title").in_("idea_id", unique_ids).execute()
        )
        return self._rows_by_id(response.data, "idea_id")

    async def get_or_create_conversation(
        self, user_id: str, other_user_id: str, idea_id: str | None = None
    ) -> dict[str, Any]:
        """Get existing conversation or create a new one between two users."""
        try:
            if user_id == other_user_id:
                raise ValueError("You cannot start a conversation with yourself")

            # Normalize participant order for consistent lookups
            p1, p2 = sorted([user_id, other_user_id])

            # Try to find existing conversation
            query = self.db.table("conversations").select("*")
            query = query.eq("idea_id", idea_id) if idea_id else query.is_("idea_id", None)

            response = query.eq("participant_1", p1).eq("participant_2", p2).execute()

            existing_conversation = self._first_row(response.data)
            if existing_conversation:
                return existing_conversation

            # Create new conversation
            new_conversation = {
                "conversation_id": str(uuid4()),
                "participant_1": p1,
                "participant_2": p2,
                "idea_id": idea_id,
                "last_message_at": datetime.utcnow().isoformat(),
                "participant_1_unread_count": 0,
                "participant_2_unread_count": 0,
            }

            response = self.db.table("conversations").insert(new_conversation).execute()

            created_conversation = self._first_row(response.data)
            if created_conversation:
                return created_conversation

            return new_conversation

        except Exception as e:
            logger.error(f"[MessagingService] Error in get_or_create_conversation: {e}")
            raise

    async def get_user_conversations(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Get all conversations for a user, sorted by most recent."""
        try:
            response = (
                self.db.table("conversations")
                .select("*")
                .or_(f"participant_1.eq.{user_id},participant_2.eq.{user_id}")
                .order("last_message_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )

            conversations = response.data or []

            users_by_id = self._fetch_users_by_id(
                [
                    participant_id
                    for conv in conversations
                    for participant_id in (conv.get("participant_1"), conv.get("participant_2"))
                    if participant_id
                ],
                "user_id, username, first_name, last_name, email, profile_picture_url",
            )
            ideas_by_id = self._fetch_ideas_by_id(
                [conv.get("idea_id") for conv in conversations if conv.get("idea_id")]
            )

            for conv in conversations:
                conv["participant_1_user"] = users_by_id.get(str(conv.get("participant_1")), {})
                conv["participant_2_user"] = users_by_id.get(str(conv.get("participant_2")), {})
                conv["idea"] = (
                    ideas_by_id.get(str(conv.get("idea_id")), {}) if conv.get("idea_id") else {}
                )

            return conversations

        except Exception as e:
            logger.error(f"[MessagingService] Error in get_user_conversations: {e}")
            raise

    async def get_conversation_messages(
        self, conversation_id: str, user_id: str, limit: int = 100, before_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get messages for a conversation, with pagination."""
        try:
            # Verify user is part of conversation
            conv_response = (
                self.db.table("conversations")
                .select("*")
                .eq("conversation_id", conversation_id)
                .single()
                .execute()
            )

            if not conv_response.data:
                raise Exception("Conversation not found")

            conv = conv_response.data
            if conv["participant_1"] != user_id and conv["participant_2"] != user_id:
                raise Exception("User is not part of this conversation")

            # Get messages
            query = self.db.table("messages").select("*").eq("conversation_id", conversation_id)

            if before_id:
                # Get the created_at of the before message
                before_msg = (
                    self.db.table("messages")
                    .select("created_at")
                    .eq("message_id", before_id)
                    .single()
                    .execute()
                )
                if before_msg.data:
                    query = query.lt("created_at", before_msg.data["created_at"])

            response = query.order("created_at", desc=True).limit(limit).execute()

            # Return in chronological order
            messages = response.data or []

            users_by_id = self._fetch_users_by_id(
                [str(msg.get("sender_id")) for msg in messages if msg.get("sender_id")],
                "user_id, username, first_name, last_name, profile_picture_url",
            )
            for msg in messages:
                msg["sender"] = users_by_id.get(str(msg.get("sender_id")), {})

            return list(reversed(messages))

        except Exception as e:
            logger.error(f"[MessagingService] Error in get_conversation_messages: {e}")
            raise

    async def send_message(
        self,
        conversation_id: str,
        sender_id: str,
        content: str,
        message_type: str = "text",
        metadata: dict | None = None,
        is_encrypted: bool = True,
    ) -> dict[str, Any]:
        """Send a message in a conversation."""
        try:
            # Verify sender is part of conversation
            conv_response = (
                self.db.table("conversations")
                .select("*")
                .eq("conversation_id", conversation_id)
                .single()
                .execute()
            )

            if not conv_response.data:
                raise Exception("Conversation not found")

            conv = conv_response.data
            if conv["participant_1"] != sender_id and conv["participant_2"] != sender_id:
                raise Exception("User is not part of this conversation")

            # Create message
            new_message = {
                "message_id": str(uuid4()),
                "conversation_id": conversation_id,
                "sender_id": sender_id,
                "content": content,
                "message_type": message_type,
                "metadata": metadata,
                "is_encrypted": is_encrypted,
                "encryption_version": 1 if is_encrypted else 0,
                "is_read": False,
                "created_at": datetime.utcnow().isoformat(),
            }

            response = self.db.table("messages").insert(new_message).execute()

            created_message = self._first_row(response.data)
            if created_message:
                return created_message

            return new_message

        except Exception as e:
            logger.error(f"[MessagingService] Error in send_message: {e}")
            raise

    async def mark_messages_as_read(self, conversation_id: str, user_id: str) -> bool:
        """Mark all unread messages in a conversation as read for a user."""
        try:
            # Get conversation to determine which unread count to reset
            conv_response = (
                self.db.table("conversations")
                .select("*")
                .eq("conversation_id", conversation_id)
                .single()
                .execute()
            )

            if not conv_response.data:
                return False

            conv = conv_response.data
            if conv["participant_1"] != user_id and conv["participant_2"] != user_id:
                return False

            # Mark messages as read (messages NOT sent by this user)
            self.db.table("messages").update(
                {"is_read": True, "read_at": datetime.utcnow().isoformat()}
            ).eq("conversation_id", conversation_id).neq("sender_id", user_id).eq(
                "is_read", False
            ).execute()

            # Reset unread count for this user
            if conv["participant_1"] == user_id:
                self.db.table("conversations").update({"participant_1_unread_count": 0}).eq(
                    "conversation_id", conversation_id
                ).execute()
            else:
                self.db.table("conversations").update({"participant_2_unread_count": 0}).eq(
                    "conversation_id", conversation_id
                ).execute()

            return True

        except Exception as e:
            logger.error(f"[MessagingService] Error in mark_messages_as_read: {e}")
            return False

    async def get_unread_count(self, user_id: str) -> int:
        """Get total unread message count for a user."""
        try:
            response = (
                self.db.table("conversations")
                .select(
                    "participant_1, participant_2, participant_1_unread_count, participant_2_unread_count"
                )
                .or_(f"participant_1.eq.{user_id},participant_2.eq.{user_id}")
                .execute()
            )

            total = 0
            for conv in response.data or []:
                if conv["participant_1"] == user_id:
                    total += conv.get("participant_1_unread_count", 0)
                else:
                    total += conv.get("participant_2_unread_count", 0)

            return total

        except Exception as e:
            logger.error(f"[MessagingService] Error in get_unread_count: {e}")
            return 0

    async def get_user_public_key(self, user_id: str) -> str | None:
        """Get a user's public encryption key."""
        try:
            response = (
                self.db.table("user_encryption_keys")
                .select("public_key")
                .eq("user_id", user_id)
                .eq("is_active", True)
                .single()
                .execute()
            )

            if response.data:
                return response.data.get("public_key")
            return None

        except Exception as e:
            logger.error(f"[MessagingService] Error in get_user_public_key: {e}")
            return None

    async def set_user_public_key(self, user_id: str, public_key: str) -> bool:
        """Set or update a user's public encryption key."""
        try:
            # Upsert the key
            response = (
                self.db.table("user_encryption_keys")
                .upsert(
                    {
                        "user_id": user_id,
                        "public_key": public_key,
                        "is_active": True,
                        "created_at": datetime.utcnow().isoformat(),
                    },
                    on_conflict="user_id",
                )
                .execute()
            )

            return bool(response.data)

        except Exception as e:
            logger.error(f"[MessagingService] Error in set_user_public_key: {e}")
            return False

    async def require_messaging_allowed_for_idea(
        self, idea_id: str, requester_user_id: str
    ) -> None:
        """
        Enforce: non-owners may only start/link conversations about published ideas.
        No-op if the idea row is missing (caller may still be creating a context-free thread).
        """
        idea_response = (
            self.db.table("ideas")
            .select("user_id, is_published")
            .eq("idea_id", idea_id)
            .single()
            .execute()
        )
        row = idea_response.data
        if not row:
            return
        owner_uid = str(row.get("user_id") or "")
        published = bool(row.get("is_published"))
        if owner_uid != requester_user_id and not published:
            raise ValueError("Messaging is only available for published ideas")

    async def get_idea_owner(self, idea_id: str, viewer_user_id: str) -> dict[str, Any] | None:
        """Get the owner details of an idea for messaging (includes publish + can_message for viewer)."""
        try:
            idea_response = (
                self.db.table("ideas")
                .select("user_id, title, is_published")
                .eq("idea_id", idea_id)
                .single()
                .execute()
            )

            if not idea_response.data:
                return None

            idea = idea_response.data
            owner_id = str(idea["user_id"])
            is_published = bool(idea.get("is_published"))
            is_owner = viewer_user_id == owner_id
            can_message = (not is_owner) and is_published

            user_response = (
                self.db.table("users")
                .select("user_id, username, first_name, last_name, email, bio, profile_picture_url")
                .eq("user_id", owner_id)
                .single()
                .execute()
            )

            if not user_response.data:
                return None

            return {
                "idea_id": idea_id,
                "idea_title": idea.get("title"),
                "owner": user_response.data,
                "is_published": is_published,
                "can_message": can_message,
            }

        except Exception as e:
            logger.error(f"[MessagingService] Error in get_idea_owner: {e}")
            return None


def create_messaging_service(db) -> MessagingService:
    """Factory function to create a MessagingService instance."""
    return MessagingService(db)
