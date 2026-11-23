"""Manifest memory: remember, recall, forget, and saved voice conversations (ADR 0021).

Thin on purpose: the rules live in ``app.services.memory.store``. Memories belong to the
signed-in person only; an idea they name must be one they can see.
"""

from __future__ import annotations

import asyncio
from typing import Any

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.types.memory import (
    ConversationTurnInput,
    Memory,
    RememberResult,
    SavedConversation,
    to_memory,
)
from app.services.memory import store
from app.utils.logger import logger

NO_IDEA = "Idea not found or you don't have permission to see it"


async def _idea(info: strawberry.Info, user_id: str, idea_id: str | None) -> dict | None:
    """The idea (id and title) when the person can see it; None for no idea."""
    if not idea_id:
        return None
    from app.services.ideas.collaboration import CollaborationService

    db = info.context["db"]
    role = await CollaborationService(db).get_user_role(idea_id, user_id)
    if role not in ("owner", "editor", "viewer", "commenter"):
        raise ValueError(NO_IDEA)
    rows = await asyncio.to_thread(
        lambda: db.table("ideas").select("idea_id, title").eq("idea_id", idea_id).limit(1).execute()
    )
    if not rows.data:
        raise ValueError(NO_IDEA)
    return dict(rows.data[0])


def _user(info: strawberry.Info) -> str:
    return str(get_current_user_id(info.context["request"]))


async def _call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except store.MemoryStoreError as exc:
        raise ValueError(str(exc)) from None


def _ai_layer() -> Any:
    from app.managers.manifest_manager import manifest_manager

    return manifest_manager.ai_layer


@strawberry.type
class MemoryQuery:
    @strawberry.field
    async def recall(
        self,
        info: strawberry.Info,
        query: str = "",
        idea_id: str | None = None,
        limit: int = 8,
    ) -> list[Memory]:
        """What you remember about the person and their ideas: decisions, preferences, people,
        plans. Call it at the start of Manifest work (with the idea's id) and whenever earlier
        context would help; query narrows it by words. Memories are Markdown files in the
        person's vault (Memory/), the same for every agent."""
        user_id = _user(info)
        if idea_id:
            await _idea(info, user_id, idea_id)
        found = await _call(store.recall, info.context["db"], user_id, query, idea_id, limit)
        return [to_memory(m) for m in found]

    @strawberry.field
    async def memories(self, info: strawberry.Info, idea_id: str | None = None) -> list[Memory]:
        """Every memory, newest first (only this idea's with ideaId), for reviewing them."""
        user_id = _user(info)
        found = await _call(store.all_memories, info.context["db"], user_id)
        return [to_memory(m) for m in found if not idea_id or m["idea_id"] == idea_id]


@strawberry.type
class MemoryMutation:
    @strawberry.mutation
    async def remember(
        self,
        info: strawberry.Info,
        text: str,
        idea_id: str | None = None,
        kind: str = "fact",
        source: str | None = None,
        replaces: str | None = None,
    ) -> RememberResult:
        """Remember one lasting fact the person told you, in one short sentence: a decision,
        preference, person and their role, plan or open question (kind: fact, decision,
        preference, person, plan, question). Use ideaId when it is about an idea. Saying the
        same thing again only refreshes it; when a fact changed, pass the old memory's id as
        replaces. Never store passwords, keys, account or ID numbers or health details.
        source names who is remembering (voice, claude-code, codex…)."""
        user_id = _user(info)
        idea = await _idea(info, user_id, idea_id)
        result = await _call(
            store.remember,
            info.context["db"],
            user_id,
            text,
            idea=idea,
            kind=kind,
            source=source,
            replaces=replaces,
        )
        return RememberResult(status=result["status"], memory=to_memory(result["memory"]))

    @strawberry.mutation
    async def update_memory(self, info: strawberry.Info, memory_id: str, text: str) -> Memory:
        """Correct a memory's wording."""
        memory = await _call(store.update, info.context["db"], _user(info), memory_id, text)
        return to_memory(memory)

    @strawberry.mutation
    async def forget_memory(self, info: strawberry.Info, memory_id: str) -> Memory:
        """Forget one memory when the person asks ("forget that"). Its file moves to the
        vault's .trash, so it can still be recovered there."""
        memory = await _call(store.forget, info.context["db"], _user(info), memory_id)
        return to_memory(memory)

    @strawberry.mutation
    async def save_voice_conversation(
        self,
        info: strawberry.Info,
        turns: list[ConversationTurnInput],
        idea_id: str | None = None,
        started_at: str | None = None,
        agent: str | None = None,
        extract: bool = True,
    ) -> SavedConversation:
        """Save a finished voice conversation to the vault (Conversations/) and link what was
        remembered during it. With extract and the person's OpenAI key, lasting facts the
        agent didn't save yet are remembered too. The app calls this when voice ends."""
        user_id = _user(info)
        db = info.context["db"]
        idea = await _idea(info, user_id, idea_id)
        raw = [{"role": t.role, "text": t.text} for t in turns]
        if extract:
            await _extract(db, user_id, raw, idea)
        saved = await _call(
            store.save_conversation,
            db,
            user_id,
            raw,
            idea=idea,
            started_at=started_at,
            agent=(agent or "")[:40] or None,
        )
        if saved is None:
            return SavedConversation(path=None, turns=0, memories=[])
        return SavedConversation(
            path=saved["path"],
            turns=saved["turns"],
            memories=[to_memory(m) for m in saved["memories"]],
        )


async def _extract(db: Any, user_id: str, turns: list[dict], idea: dict | None) -> None:
    """Best effort: a failed extraction never loses the transcript."""
    kept = store.clean_turns(turns)
    try:
        known = await asyncio.to_thread(
            store.recall, db, user_id, "", (idea or {}).get("idea_id"), 25
        )
        facts = await asyncio.to_thread(
            store.extract, _ai_layer(), kept, known, (idea or {}).get("title")
        )
        for fact in facts:
            await asyncio.to_thread(
                store.remember,
                db,
                user_id,
                fact["text"],
                idea=idea,
                kind=fact["kind"],
                source="voice",
            )
    except Exception as exc:  # noqa: BLE001 (extraction is optional)
        logger.warning("memory extraction skipped", extra={"exception.type": type(exc).__name__})
