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


@strawberry.type
class KnowledgePassage:
    """A sentence of the idea note (``p1``…) or one interview answer (``a1``…)."""

    id: str
    kind: str
    text: str


@strawberry.type
class KnowledgeIdeaRef:
    idea_id: str
    title: str
    path: str
    concepts: list[str] = strawberry.field(default_factory=list)


@strawberry.type
class KnowledgeConcept:
    label: str
    path: str
    passage_ids: list[str]
    document_types: list[str]
    ideas: list[KnowledgeIdeaRef]


@strawberry.type
class CitedDocument:
    document_type: str
    markdown: str


@strawberry.type
class IdeaKnowledgeGraph:
    """One idea's knowledge graph (ADR 0006); wiki-link targets match the local vault."""

    idea_id: str
    idea_path: str
    passages: list[KnowledgePassage]
    concepts: list[KnowledgeConcept]
    related: list[KnowledgeIdeaRef]
    documents: list[CitedDocument]
