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
    paths: list[str] = strawberry.field(
        default_factory=list,
        description="Every file under Manifest/ right now, even ones not sent; a vault removes "
        "Manifest's own files that are no longer listed (renamed or deleted ideas). Empty "
        "when nothing changed since the fingerprint you passed.",
    )
    fingerprint: str | None = strawberry.field(
        default=None,
        description="Pass it back next time: when nothing changed, the export is empty.",
    )


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
    reason: str | None = strawberry.field(
        default=None, description="Why the ideas are related, in plain words."
    )


@strawberry.type
class KnowledgeConcept:
    """A concept from the founder's own words (ADR 0009)."""

    label: str
    path: str
    passage_ids: list[str]
    document_types: list[str]
    ideas: list[KnowledgeIdeaRef]
    role: str = strawberry.field(
        default="context",
        description="who, problem, solution, technology, business, context or skill",
    )
    role_label: str = "Context"
    aliases: list[str] = strawberry.field(default_factory=list)
    parent: str | None = strawberry.field(
        default=None, description="The broader concept this one sits under."
    )
    weight: float = 0.0
    why: str = strawberry.field(default="", description="How the concept was derived.")


@strawberry.type
class KnowledgeRelation:
    """Two concepts the founder connects in the same sentence, labelled by their roles."""

    source: str
    target: str
    label: str
    passage_ids: list[str]
    weight: int


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
    relations: list[KnowledgeRelation] = strawberry.field(default_factory=list)
    documents: list[CitedDocument]
