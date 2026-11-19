"""Live notes: people co-edit a shared idea's note in real time (ADR 0008).

The browser editor keeps the note in a Yjs document (TipTap's Collaboration
extension). This module is the server half: one room per idea note, holding a
``pycrdt`` copy of the document so late joiners get the current state, relaying
document updates to the room, and relaying *awareness* (cursors and selections)
with the sender's identity stamped by the server, so nobody can pose as someone
else's cursor.

Edits that arrive outside the live session (the agent plugin, the CLI, the iOS
app, a second tab that is not live) go through the ``updateIdea`` mutation as
before. ``announce_external_edit`` hands that new HTML to one editor in the room,
whose browser merges only the changed range into the shared document; the
others show the author's avatar and a labelled caret where the text changed.

State lives in process memory. That matches production (one backend process);
running several processes needs a shared Socket.IO manager (see the ADR).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import pycrdt
from app.utils.logger import logger

ROOM_PREFIX = "note:"
MAX_UPDATE_BYTES = 512 * 1024
MAX_DOC_BYTES = 4 * 1024 * 1024
MAX_AWARENESS_BYTES = 16 * 1024
EXTERNAL_PRESENCE_SECONDS = 45
VIA_LABELS = {"app": "Manifest", "agent": "AI agent", "cli": "CLI"}
# Readable on white and on the dark editor; picked by a hash of the user id.
CURSOR_COLORS = (
    "#2563eb",
    "#db2777",
    "#16a34a",
    "#ea580c",
    "#9333ea",
    "#0891b2",
    "#ca8a04",
    "#dc2626",
    "#4f46e5",
    "#059669",
)


class Emitter(Protocol):
    """The subset of ``socketio.AsyncServer`` this module uses."""

    async def emit(
        self,
        event: str,
        data: Any = None,
        to: str | None = None,
        room: str | None = None,
        skip_sid: str | None = None,
    ) -> None: ...
    async def enter_room(self, sid: str, room: str, namespace: str | None = None) -> None: ...
    async def leave_room(self, sid: str, room: str, namespace: str | None = None) -> None: ...


Access = tuple[str, bool]  # (role, can_edit)
AccessResolver = Callable[[str, str], Awaitable[Access | None]]
ProfileLoader = Callable[[str], Awaitable[dict[str, Any]]]


def color_for(user_id: str) -> str:
    digest = hashlib.sha256(user_id.encode("utf-8")).digest()
    return CURSOR_COLORS[digest[0] % len(CURSOR_COLORS)]


def room_name(idea_id: str) -> str:
    return f"{ROOM_PREFIX}{idea_id}"


@dataclass
class Peer:
    sid: str
    user_id: str
    client_id: int
    name: str
    avatar_url: str | None
    role: str
    can_edit: bool
    joined_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def public(self) -> dict[str, Any]:
        return {
            "clientId": self.client_id,
            "userId": self.user_id,
            "name": self.name,
            "avatarUrl": self.avatar_url,
            "color": color_for(self.user_id),
            "role": self.role,
            "canEdit": self.can_edit,
            "via": "app",
        }


@dataclass
class ExternalEditor:
    user_id: str
    name: str
    avatar_url: str | None
    via: str
    until: float

    def public(self) -> dict[str, Any]:
        return {
            "userId": self.user_id,
            "name": self.name,
            "avatarUrl": self.avatar_url,
            "color": color_for(self.user_id),
            "via": self.via,
            "viaLabel": VIA_LABELS.get(self.via, self.via),
            "until": self.until,
        }


@dataclass
class Room:
    idea_id: str
    doc: pycrdt.Doc = field(default_factory=pycrdt.Doc)
    peers: dict[str, Peer] = field(default_factory=dict)
    external: dict[str, ExternalEditor] = field(default_factory=dict)
    seeded: bool = False
    seeder_sid: str | None = None
    size: int = 0

    def live_external(self, now: float) -> list[ExternalEditor]:
        self.external = {k: v for k, v in self.external.items() if v.until > now}
        return list(self.external.values())

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else now
        return {
            "ideaId": self.idea_id,
            "peers": [p.public() for p in self.peers.values()],
            "external": [e.public() for e in self.live_external(now)],
        }


# ---------------------------------------------------------------------------
# y-protocols awareness wire format (lib0 varuint / varstring)
# ---------------------------------------------------------------------------


def _read_var_uint(buf: bytes, pos: int) -> tuple[int, int]:
    value, shift = 0, 0
    while True:
        if pos >= len(buf):
            raise ValueError("truncated varuint")
        byte = buf[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, pos
        shift += 7
        if shift > 63:
            raise ValueError("varuint too long")


def _write_var_uint(value: int) -> bytes:
    out = bytearray()
    while value > 0x7F:
        out.append(0x80 | (value & 0x7F))
        value >>= 7
    out.append(value)
    return bytes(out)


def decode_awareness(buf: bytes) -> list[tuple[int, int, Any]]:
    """Entries of an awareness update: ``(client_id, clock, state_or_None)``."""
    count, pos = _read_var_uint(buf, 0)
    entries = []
    for _ in range(count):
        client_id, pos = _read_var_uint(buf, pos)
        clock, pos = _read_var_uint(buf, pos)
        length, pos = _read_var_uint(buf, pos)
        raw = buf[pos : pos + length]
        if len(raw) != length:
            raise ValueError("truncated awareness state")
        pos += length
        entries.append((client_id, clock, json.loads(raw.decode("utf-8"))))
    return entries


def encode_awareness(entries: list[tuple[int, int, Any]]) -> bytes:
    out = bytearray(_write_var_uint(len(entries)))
    for client_id, clock, state in entries:
        raw = json.dumps(state, separators=(",", ":")).encode("utf-8")
        out += _write_var_uint(client_id) + _write_var_uint(clock) + _write_var_uint(len(raw)) + raw
    return bytes(out)


def _as_bytes(value: Any) -> bytes | None:
    if isinstance(value, bytes | bytearray | memoryview):
        return bytes(value)
    if isinstance(value, list) and all(isinstance(b, int) and 0 <= b < 256 for b in value):
        return bytes(value)
    return None


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------


class LiveNotes:
    def __init__(
        self,
        emitter: Emitter | None = None,
        access: AccessResolver | None = None,
        profile: ProfileLoader | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.emitter = emitter
        self.access = access or _default_access
        self.profile = profile or _default_profile
        self.clock = clock
        self.rooms: dict[str, Room] = {}
        self._lock = asyncio.Lock()

    def configure(self, emitter: Emitter) -> None:
        self.emitter = emitter

    async def _emit(self, event: str, data: Any, **kwargs: Any) -> None:
        if self.emitter is None:
            return
        try:
            await self.emitter.emit(event, data, **kwargs)
        except Exception as exc:  # noqa: BLE001 — a dropped socket must not break the caller
            logger.warning("[live_notes] emit %s failed: %s", event, exc)

    async def _broadcast_peers(self, room: Room) -> None:
        await self._emit("note:peers", room.snapshot(self.clock()), room=room_name(room.idea_id))

    # -- join / leave ------------------------------------------------------

    async def join(self, sid: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        idea_id = str(data.get("ideaId") or "").strip()
        client_id = data.get("clientId")
        if not idea_id or not isinstance(client_id, int) or client_id < 0:
            return {"ok": False, "error": "ideaId and clientId are required"}
        access = await self.access(idea_id, user_id)
        if access is None:
            return {"ok": False, "error": "You don't have access to this note"}
        role, can_edit = access
        profile = await self.profile(user_id)
        state_vector = _as_bytes(data.get("stateVector")) or b""

        async with self._lock:
            room = self.rooms.setdefault(idea_id, Room(idea_id))
            room.peers[sid] = Peer(
                sid=sid,
                user_id=user_id,
                client_id=client_id,
                name=profile.get("name") or "Someone",
                avatar_url=profile.get("avatar_url"),
                role=role,
                can_edit=can_edit,
            )
            seed = not room.seeded and can_edit and room.seeder_sid in (None, sid)
            if seed:
                room.seeder_sid = sid
            try:
                update = (
                    room.doc.get_update(state_vector) if state_vector else room.doc.get_update()
                )
            except Exception:  # noqa: BLE001 — a malformed state vector gets the full doc
                update = room.doc.get_update()
            server_state = room.doc.get_state()

        if self.emitter is not None:
            await self.emitter.enter_room(sid, room_name(idea_id))
        await self._broadcast_peers(room)
        return {
            "ok": True,
            "role": role,
            "canEdit": can_edit,
            "seed": seed,
            "seeded": room.seeded,
            "update": update,
            "stateVector": server_state,
            "self": room.peers[sid].public(),
            **room.snapshot(self.clock()),
        }

    async def leave(self, sid: str, idea_id: str | None = None) -> None:
        async with self._lock:
            targets = [
                room
                for room in self.rooms.values()
                if sid in room.peers and (idea_id is None or room.idea_id == idea_id)
            ]
            departed: list[tuple[Room, Peer, str | None]] = []
            for room in targets:
                peer = room.peers.pop(sid)
                next_seeder = None
                if room.seeder_sid == sid:
                    room.seeder_sid = None
                    if not room.seeded:
                        editor = next((p for p in room.peers.values() if p.can_edit), None)
                        if editor:
                            room.seeder_sid = next_seeder = editor.sid
                if not room.peers:
                    self.rooms.pop(room.idea_id, None)
                departed.append((room, peer, next_seeder))

        for room, peer, next_seeder in departed:
            name = room_name(room.idea_id)
            if self.emitter is not None:
                try:
                    await self.emitter.leave_room(sid, name)
                except Exception:  # noqa: BLE001
                    pass
            if not room.peers:
                continue
            await self._emit(
                "note:left", {"ideaId": room.idea_id, "clientId": peer.client_id}, room=name
            )
            if next_seeder:
                await self._emit("note:seed", {"ideaId": room.idea_id}, to=next_seeder)
            await self._broadcast_peers(room)

    async def disconnect(self, sid: str) -> None:
        await self.leave(sid)

    # -- document + awareness ---------------------------------------------

    def _peer(self, sid: str, idea_id: str) -> tuple[Room, Peer] | None:
        room = self.rooms.get(idea_id)
        if not room or sid not in room.peers:
            return None
        return room, room.peers[sid]

    async def update(self, sid: str, data: dict[str, Any]) -> dict[str, Any]:
        idea_id = str(data.get("ideaId") or "")
        update = _as_bytes(data.get("update"))
        found = self._peer(sid, idea_id)
        if not found:
            return {"ok": False, "error": "Join the note first"}
        room, peer = found
        if not peer.can_edit:
            return {"ok": False, "error": "You can view this note but not edit it"}
        if not update or len(update) > MAX_UPDATE_BYTES:
            return {"ok": False, "error": "Update is empty or too large"}
        if len(update) <= 2:
            return {"ok": True}  # an empty Yjs update changes nothing
        if data.get("seed") and room.seeded:
            # Someone else filled the room first; the seeder starts over from it.
            return {"ok": False, "error": "already-seeded"}
        if room.size + len(update) > MAX_DOC_BYTES:
            return {"ok": False, "error": "This note is too large to edit live"}
        try:
            room.doc.apply_update(update)
        except Exception as exc:  # noqa: BLE001
            logger.info("[live_notes] rejected update for %s: %s", idea_id, exc)
            return {"ok": False, "error": "Malformed update"}
        room.size += len(update)
        room.seeded = True
        peer.last_active = self.clock()
        await self._emit(
            "note:update",
            {"ideaId": idea_id, "update": update},
            room=room_name(idea_id),
            skip_sid=sid,
        )
        return {"ok": True}

    async def awareness(self, sid: str, data: dict[str, Any]) -> None:
        idea_id = str(data.get("ideaId") or "")
        payload = _as_bytes(data.get("update"))
        found = self._peer(sid, idea_id)
        if not found or not payload or len(payload) > MAX_AWARENESS_BYTES:
            return
        _, peer = found
        try:
            entries = decode_awareness(payload)
        except Exception:  # noqa: BLE001
            return
        stamped = []
        for client_id, clock, state in entries:
            if client_id != peer.client_id:
                continue  # a client may only speak for its own cursor
            if isinstance(state, dict):
                state = {**state, "user": peer.public()}
                if not peer.can_edit:
                    state.pop("cursor", None)
            elif state is not None:
                continue
            stamped.append((client_id, clock, state))
        if not stamped:
            return
        peer.last_active = self.clock()
        await self._emit(
            "note:awareness",
            {"ideaId": idea_id, "update": encode_awareness(stamped)},
            room=room_name(idea_id),
            skip_sid=sid,
        )

    # -- edits from outside the live session -------------------------------

    async def announce_external_edit(self, idea_id: str, user_id: str, html: str, via: str) -> bool:
        """Bring an edit saved through the API into the live room, if there is one.

        Returns True when a live room received it.
        """
        room = self.rooms.get(idea_id)
        if not room or not room.peers:
            return False
        profile = await self.profile(user_id)
        now = self.clock()
        author = ExternalEditor(
            user_id=user_id,
            name=profile.get("name") or "Someone",
            avatar_url=profile.get("avatar_url"),
            via=via if via in VIA_LABELS else "app",
            until=now + EXTERNAL_PRESENCE_SECONDS,
        )
        room.external[f"{user_id}:{author.via}"] = author
        editors = sorted((p for p in room.peers.values() if p.can_edit), key=lambda p: p.joined_at)
        name = room_name(idea_id)
        payload = {"ideaId": idea_id, "html": html, "by": author.public()}
        if editors and room.seeded:
            leader = editors[0]
            await self._emit("note:external", {**payload, "apply": True}, to=leader.sid)
            await self._emit(
                "note:external", {**payload, "apply": False}, room=name, skip_sid=leader.sid
            )
        else:
            # Nobody here can write the change into the shared document: start
            # the room again from the saved note.
            async with self._lock:
                room.doc = pycrdt.Doc()
                room.size = 0
                room.seeded = False
                room.seeder_sid = editors[0].sid if editors else None
            await self._emit("note:reset", {**payload, "apply": False}, room=name)
        await self._broadcast_peers(room)
        return True

    def presence(self, idea_id: str) -> list[dict[str, Any]]:
        """Who is in the note now: people in the app plus recent agent/CLI editors."""
        room = self.rooms.get(idea_id)
        if not room:
            return []
        now = self.clock()
        people: dict[str, dict[str, Any]] = {}
        for peer in sorted(room.peers.values(), key=lambda p: p.joined_at):
            entry = people.setdefault(
                peer.user_id,
                {**peer.public(), "lastActiveAt": peer.last_active, "viaLabel": "Manifest"},
            )
            entry["lastActiveAt"] = max(entry["lastActiveAt"], peer.last_active)
        external = [
            {
                **e.public(),
                "role": None,
                "canEdit": True,
                "lastActiveAt": e.until - EXTERNAL_PRESENCE_SECONDS,
            }
            for e in room.live_external(now)
        ]
        return list(people.values()) + external


# ---------------------------------------------------------------------------
# Production wiring (database-backed access and profiles)
# ---------------------------------------------------------------------------


def _db():
    from app.db.database import create_database_client

    return create_database_client()


async def _default_access(idea_id: str, user_id: str) -> Access | None:
    from app.services.ideas.collaboration import create_collaboration_service

    service = create_collaboration_service(_db())
    if await service.get_idea_owner(idea_id) == user_id:
        return ("owner", True)
    if not await service.check_access(idea_id, user_id, "view"):
        return None
    role = await service.get_user_role(idea_id, user_id) or "viewer"
    return (role, await service.check_access(idea_id, user_id, "edit"))


async def _default_profile(user_id: str) -> dict[str, Any]:
    def load() -> dict[str, Any]:
        try:
            row = (
                _db()
                .table("users")
                .select("email, username, first_name, last_name, profile_picture_url")
                .eq("user_id", user_id)
                .single()
                .execute()
            ).data or {}
        except Exception:  # noqa: BLE001
            row = {}
        full = " ".join(p for p in (row.get("first_name"), row.get("last_name")) if p).strip()
        email = row.get("email") or ""
        return {
            "name": full or row.get("username") or (email.split("@")[0] if email else None),
            "avatar_url": row.get("profile_picture_url"),
        }

    return await asyncio.to_thread(load)


live_notes = LiveNotes()
