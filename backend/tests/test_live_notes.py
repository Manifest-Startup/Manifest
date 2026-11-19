"""Live notes (ADR 0008): rooms, seeding, permissions, awareness stamping, external edits."""

import asyncio

import pycrdt
import pytest
from app.services.ideas.live_notes import (
    LiveNotes,
    color_for,
    decode_awareness,
    encode_awareness,
)

ACCESS = {
    ("idea-1", "owner"): ("owner", True),
    ("idea-1", "editor"): ("editor", True),
    ("idea-1", "viewer"): ("viewer", False),
}
PROFILES = {
    "owner": {"name": "Olivia Owner", "avatar_url": "https://img/o.png"},
    "editor": {"name": "Eddie Editor", "avatar_url": None},
    "viewer": {"name": "Vera Viewer", "avatar_url": None},
}


class FakeEmitter:
    def __init__(self):
        self.events = []
        self.rooms: dict[str, set[str]] = {}

    async def emit(self, event, data=None, to=None, room=None, skip_sid=None):
        self.events.append({"event": event, "data": data, "to": to, "room": room, "skip": skip_sid})

    async def enter_room(self, sid, room, namespace=None):
        self.rooms.setdefault(room, set()).add(sid)

    async def leave_room(self, sid, room, namespace=None):
        self.rooms.get(room, set()).discard(sid)

    def of(self, event):
        return [e for e in self.events if e["event"] == event]


async def _access(idea_id, user_id):
    return ACCESS.get((idea_id, user_id))


async def _profile(user_id):
    return PROFILES.get(user_id, {})


def make():
    emitter = FakeEmitter()
    return LiveNotes(emitter=emitter, access=_access, profile=_profile), emitter


def run(coro):
    return asyncio.run(coro)


def text_update(text: str, doc: pycrdt.Doc | None = None) -> tuple[pycrdt.Doc, bytes]:
    doc = doc or pycrdt.Doc()
    before = doc.get_state()
    doc.get("t", type=pycrdt.Text).insert(0, text)
    return doc, doc.get_update(before)


def test_first_editor_seeds_and_late_joiner_gets_the_document():
    async def scenario():
        notes, emitter = make()
        first = await notes.join("s1", "owner", {"ideaId": "idea-1", "clientId": 11})
        assert first["ok"] and first["seed"] and first["canEdit"]

        second = await notes.join("s2", "editor", {"ideaId": "idea-1", "clientId": 22})
        assert second["ok"] and not second["seed"]

        _, update = text_update("hello")
        assert (await notes.update("s1", {"ideaId": "idea-1", "update": update, "seed": True}))[
            "ok"
        ]
        relayed = emitter.of("note:update")[-1]
        assert relayed["room"] == "note:idea-1" and relayed["skip"] == "s1"

        late = await notes.join("s3", "viewer", {"ideaId": "idea-1", "clientId": 33})
        doc = pycrdt.Doc()
        doc.apply_update(late["update"])
        assert str(doc.get("t", type=pycrdt.Text)) == "hello"
        assert {p["name"] for p in late["peers"]} == {"Olivia Owner", "Eddie Editor", "Vera Viewer"}

    run(scenario())


def test_second_seed_is_refused_so_content_never_doubles():
    async def scenario():
        notes, _ = make()
        await notes.join("s1", "owner", {"ideaId": "idea-1", "clientId": 1})
        await notes.join("s2", "editor", {"ideaId": "idea-1", "clientId": 2})
        _, u1 = text_update("a")
        _, u2 = text_update("b")
        assert (await notes.update("s2", {"ideaId": "idea-1", "update": u2}))["ok"]
        refused = await notes.update("s1", {"ideaId": "idea-1", "update": u1, "seed": True})
        assert refused == {"ok": False, "error": "already-seeded"}

    run(scenario())


def test_viewers_and_strangers_cannot_write():
    async def scenario():
        notes, _ = make()
        assert not (await notes.join("x", "stranger", {"ideaId": "idea-1", "clientId": 9}))["ok"]
        await notes.join("v", "viewer", {"ideaId": "idea-1", "clientId": 3})
        _, update = text_update("nope")
        result = await notes.update("v", {"ideaId": "idea-1", "update": update})
        assert not result["ok"]
        assert not (await notes.update("x", {"ideaId": "idea-1", "update": update}))["ok"]

    run(scenario())


def test_awareness_is_stamped_with_the_real_identity_and_spoofs_are_dropped():
    async def scenario():
        notes, emitter = make()
        await notes.join("s1", "editor", {"ideaId": "idea-1", "clientId": 5})
        forged = encode_awareness(
            [
                (5, 1, {"user": {"name": "The CEO"}, "cursor": {"anchor": 1}}),
                (99, 1, {"user": {"name": "Someone else"}}),
            ]
        )
        await notes.awareness("s1", {"ideaId": "idea-1", "update": forged})
        sent = decode_awareness(emitter.of("note:awareness")[-1]["data"]["update"])
        assert len(sent) == 1
        client_id, _, state = sent[0]
        assert client_id == 5
        assert state["user"]["name"] == "Eddie Editor"
        assert state["user"]["color"] == color_for("editor")
        assert state["cursor"] == {"anchor": 1}

    run(scenario())


def test_leaving_announces_and_hands_seeding_to_another_editor():
    async def scenario():
        notes, emitter = make()
        await notes.join("s1", "owner", {"ideaId": "idea-1", "clientId": 1})
        await notes.join("s2", "editor", {"ideaId": "idea-1", "clientId": 2})
        await notes.disconnect("s1")
        assert emitter.of("note:left")[-1]["data"]["clientId"] == 1
        assert emitter.of("note:seed")[-1]["to"] == "s2"
        await notes.disconnect("s2")
        assert notes.rooms == {}

    run(scenario())


def test_agent_edit_goes_to_one_editor_and_shows_in_presence():
    async def scenario():
        notes, emitter = make()
        await notes.join("s1", "owner", {"ideaId": "idea-1", "clientId": 1})
        await notes.join("s2", "editor", {"ideaId": "idea-1", "clientId": 2})
        _, update = text_update("x")
        await notes.update("s1", {"ideaId": "idea-1", "update": update, "seed": True})

        assert await notes.announce_external_edit("idea-1", "editor", "<p>new</p>", "agent")
        sent = emitter.of("note:external")
        applying = [e for e in sent if e["data"]["apply"]]
        assert len(applying) == 1 and applying[0]["to"] == "s1"
        assert sent[-1]["data"]["by"]["viaLabel"] == "AI agent"

        presence = notes.presence("idea-1")
        assert [p["via"] for p in presence] == ["app", "app", "agent"]
        assert presence[-1]["name"] == "Eddie Editor"

        assert not await notes.announce_external_edit("idea-2", "owner", "<p>x</p>", "cli")

    run(scenario())


def test_external_edit_with_no_editor_online_resets_the_room():
    async def scenario():
        notes, emitter = make()
        await notes.join("v", "viewer", {"ideaId": "idea-1", "clientId": 3})
        await notes.announce_external_edit("idea-1", "owner", "<p>new</p>", "cli")
        assert emitter.of("note:reset")
        assert not notes.rooms["idea-1"].seeded

    run(scenario())


@pytest.mark.parametrize("value", [0, 1, 127, 128, 300, 2**31])
def test_awareness_codec_round_trips(value):
    entries = [(value, value, {"n": value}), (1, 2, None)]
    assert decode_awareness(encode_awareness(entries)) == entries
