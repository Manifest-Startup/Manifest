"""GraphQL types for the Obsidian-style vault export (ADR 0005)."""

import strawberry


@strawberry.type
class VaultFile:
    path: str
    content: str
    updated_at: str | None = None


@strawberry.type
class VaultExport:
    generated_at: str
    root: str
    idea_count: int
    files: list[VaultFile]
