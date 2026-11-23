"""GraphQL types for Manifest memory and saved conversations (ADR 0021)."""

import strawberry


@strawberry.type
class Memory:
    """One lasting fact, kept as a Markdown file in the person's vault (Memory/…)."""

    id: str
    text: str
    kind: str
    idea_id: str | None = None
    idea_title: str | None = None
    source: str | None = None
    conversation: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    path: str = ""


@strawberry.type
class RememberResult:
    """``saved``, ``already_known`` (the same fact was there; it was refreshed) or ``replaced``."""

    status: str
    memory: Memory


@strawberry.input
class ConversationTurnInput:
    role: str  # "user" or "assistant"
    text: str


@strawberry.type
class SavedConversation:
    """Where the transcript was saved and what was remembered during it."""

    path: str | None
    turns: int
    memories: list[Memory]


def to_memory(m: dict) -> Memory:
    return Memory(
        id=str(m["id"]),
        text=str(m["text"]),
        kind=str(m.get("kind") or "fact"),
        idea_id=m.get("idea_id"),
        idea_title=m.get("idea_title"),
        source=m.get("source"),
        conversation=m.get("conversation"),
        created_at=m.get("created_at"),
        updated_at=m.get("updated_at"),
        path=m.get("path") or "",
    )
