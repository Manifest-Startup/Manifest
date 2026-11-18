"""GraphQL resolvers for Open Media conversations, messages and account link."""

import asyncio
from typing import Optional

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.open_media_types import (
    Conversation,
    EmailThread,
    Message,
    OpenMediaLink,
    OpenMediaRealtimeToken,
    UnreadCount,
    call_open_media,
    map_conversation,
    map_email_thread,
    map_link,
    map_message,
)
from app.graphql.resolvers.shared import _require_full_account
from app.graphql.types.messaging import IdeaOwner


@strawberry.type
class MessagingQuery:
    @strawberry.field
    async def my_conversations(
        self,
        info: strawberry.Info,
        limit: int = 50,
        offset: int = 0,
        all_apps: bool = False,
    ) -> list[Conversation]:
        """Open Media conversations; Manifest ones (``context.app = manifest``) unless ``allApps``."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.integrations.open_media import messaging as om_messaging

        convs = await call_open_media(
            om_messaging.list_conversations, user_id, app_only=not all_apps
        )
        start = max(0, offset)
        return [map_conversation(c) for c in convs[start : start + max(1, min(limit, 100))]]

    @strawberry.field
    async def my_email_threads(self, info: strawberry.Info, limit: int = 200) -> list[EmailThread]:
        """Email from mailboxes connected in Open Media, grouped into threads (read-only, not stored)."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.integrations.open_media import email as om_email
        from app.services.integrations.open_media import settings as open_media_settings

        threads = await call_open_media(om_email.list_threads, user_id, limit=limit)
        reply_url = open_media_settings.web_origin()
        return [map_email_thread(t, reply_url) for t in threads]

    @strawberry.field
    async def conversation_messages(
        self,
        info: strawberry.Info,
        conversation_id: str,
        limit: int = 100,
        before_id: str | None = None,
    ) -> list[Message]:
        """Messages in an Open Media conversation, oldest first."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.integrations.open_media import identity as om_identity
        from app.services.integrations.open_media import messaging as om_messaging

        messages = await call_open_media(
            om_messaging.list_messages, user_id, conversation_id, limit=limit, before=before_id
        )
        me = await asyncio.to_thread(om_identity.om_user_id_for, user_id)
        return [map_message(m, me) for m in messages]

    @strawberry.field
    async def unread_message_count(self, info: strawberry.Info) -> UnreadCount:
        """Unread Manifest messages (0 when Open Media is off, unlinked or unreachable)."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.integrations.open_media import messaging as om_messaging
        from app.services.integrations.open_media import settings as open_media_settings

        if not open_media_settings.enabled():
            return UnreadCount(count=0)
        try:
            count = await call_open_media(om_messaging.unread_count, user_id)
        except Exception:
            count = 0  # never break the nav badge
        return UnreadCount(count=int(count or 0))

    @strawberry.field
    async def idea_owner(self, info: strawberry.Info, idea_id: str) -> Optional["IdeaOwner"]:
        """The founder of an idea, and whether the viewer can message them on Open Media."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.social.founder_contact import get_idea_owner

        data = await asyncio.to_thread(get_idea_owner, info.context["db"], idea_id, user_id)
        if not data:
            return None

        owner = data["owner"]
        return IdeaOwner(
            user_id=owner["user_id"],
            username=owner.get("username"),
            first_name=owner.get("first_name"),
            last_name=owner.get("last_name"),
            bio=owner.get("bio"),
            profile_picture_url=owner.get("profile_picture_url"),
            idea_id=data["idea_id"],
            idea_title=data.get("idea_title"),
            is_published=bool(data.get("is_published", False)),
            can_message=bool(data.get("can_message", False)),
            open_media_handle=data.get("open_media_handle"),
        )

    @strawberry.field
    async def open_media_link(self, info: strawberry.Info) -> OpenMediaLink:
        """Whether Open Media is enabled here and linked to the current account."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.integrations.open_media import identity as om_identity

        return map_link(await asyncio.to_thread(om_identity.link_status, user_id))

    @strawberry.field
    async def open_media_realtime_token(self, info: strawberry.Info) -> OpenMediaRealtimeToken:
        """Short-lived Open Media Supabase credentials for live message updates."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.integrations.open_media import messaging as om_messaging

        token = await call_open_media(om_messaging.realtime_token, user_id)
        return OpenMediaRealtimeToken(
            supabase_url=token["supabase_url"],
            anon_key=token["anon_key"],
            access_token=token["access_token"],
            expires_at=str(token["expires_at"]) if token.get("expires_at") else None,
            om_user_id=token.get("om_user_id"),
        )


@strawberry.type
class MessagingMutation:
    @strawberry.mutation
    async def start_conversation(
        self, info: strawberry.Info, other_user_id: str, idea_id: str | None = None
    ) -> Conversation:
        """Open (or reuse) an Open Media conversation with an idea's founder.

        ``otherUserId`` is the founder's Manifest user id; the founder must have
        linked Open Media. With ``ideaId`` the idea must be published and owned
        by that founder; the conversation is tagged with the idea.
        """
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.integrations.open_media import identity as om_identity
        from app.services.integrations.open_media import messaging as om_messaging
        from app.services.social.founder_contact import (
            FOUNDER_NOT_LINKED_MESSAGE,
            founder_handle_for_idea,
        )

        db = info.context["db"]
        context = None
        if idea_id:
            idea_owner = (
                db.table("ideas").select("user_id").eq("idea_id", idea_id).single().execute()
            )
            owner_row = idea_owner.data if isinstance(idea_owner.data, dict) else {}
            if str(owner_row.get("user_id") or "") != str(other_user_id):
                raise Exception("That conversation must be with the founder of this idea.")
            try:
                handle, title = await asyncio.to_thread(
                    founder_handle_for_idea, db, idea_id, user_id
                )
            except ValueError as exc:
                raise Exception(str(exc)) from exc
            context = om_messaging.idea_context(idea_id, title)
        else:
            handle = await asyncio.to_thread(om_identity.handle_for_user, other_user_id)
            if not handle:
                raise Exception(FOUNDER_NOT_LINKED_MESSAGE)

        conv = await call_open_media(
            om_messaging.start_conversation, user_id, handle=handle, context=context
        )
        return map_conversation(conv)

    @strawberry.mutation
    async def send_message(
        self,
        info: strawberry.Info,
        conversation_id: str,
        content: str,
        client_id: str | None = None,
    ) -> Message:
        """Send a message in an Open Media conversation (``clientId`` makes retries land once)."""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.integrations.open_media import messaging as om_messaging

        msg = await call_open_media(
            om_messaging.send_message, user_id, conversation_id, body=content, client_id=client_id
        )
        mapped = map_message(msg, None)
        mapped.is_mine = True
        return mapped

    @strawberry.mutation
    async def mark_conversation_read(self, info: strawberry.Info, conversation_id: str) -> bool:
        """Mark an Open Media conversation as read."""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.integrations.open_media import messaging as om_messaging

        return bool(await call_open_media(om_messaging.mark_read, user_id, conversation_id))
