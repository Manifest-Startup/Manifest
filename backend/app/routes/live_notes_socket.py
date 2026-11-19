"""Socket.IO events for live notes (ADR 0008).

The handshake in ``app.main`` already authenticates the socket; each event here
checks that the session still has a user, then hands off to
``app.services.ideas.live_notes``. Handlers return their result as the
Socket.IO acknowledgement.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from app.services.ideas.live_notes import live_notes


def register_live_note_events(
    sio: Any, require_user: Callable[[str], Awaitable[str | None]]
) -> None:
    live_notes.configure(sio)

    @sio.on("note:join")
    async def note_join(sid: str, data: Any) -> dict[str, Any]:
        user_id = await require_user(sid)
        if not user_id or not isinstance(data, dict):
            return {"ok": False, "error": "Sign in to edit together"}
        return await live_notes.join(sid, str(user_id), data)

    @sio.on("note:update")
    async def note_update(sid: str, data: Any) -> dict[str, Any]:
        if not await require_user(sid) or not isinstance(data, dict):
            return {"ok": False, "error": "Sign in to edit together"}
        return await live_notes.update(sid, data)

    @sio.on("note:awareness")
    async def note_awareness(sid: str, data: Any) -> None:
        if await require_user(sid) and isinstance(data, dict):
            await live_notes.awareness(sid, data)

    @sio.on("note:leave")
    async def note_leave(sid: str, data: Any) -> None:
        idea_id = data.get("ideaId") if isinstance(data, dict) else None
        await live_notes.leave(sid, str(idea_id) if idea_id else None)
