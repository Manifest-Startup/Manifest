"""GraphQL types and mappers for ideas: list, read, create, update, delete, publish, votes, import and export."""

from datetime import datetime

import strawberry


@strawberry.type
class Idea:
    idea_id: str
    user_id: str
    title: str
    description: str | None
    created_at: datetime
    pitch_deck: str | None = None
    product_requirements_document: str | None = None
    provisional_patent: str | None = None
    business_model_canvas: str | None = None
    similar_ideas: str | None = None
    is_published: bool = False
    required_skills: list[str] = strawberry.field(default_factory=list)
    updated_at: datetime | None = strawberry.field(
        default=None, description="When the idea (note or documents) last changed."
    )


@strawberry.type
class IdeaSummary:
    """Lightweight row for workspace idea lists — avoids serializing large generated documents."""

    idea_id: str
    user_id: str
    title: str
    description: str | None
    has_description: bool = False
    created_at: datetime
    is_published: bool = False
    generated_asset_count: int = 0
    updated_at: datetime | None = None


@strawberry.type
class VoteResult:
    voted: bool
    idea_id: str
    vote_count: int


@strawberry.type
class PublishResult:
    idea_id: str
    is_published: bool


@strawberry.type
class SimilarIdeas:
    similar_ideas: str


@strawberry.type
class ExportResult:
    content: str
    format: str
    filename: str


@strawberry.type
class ImportResult:
    imported_count: int
    skipped_count: int
    errors: list[str]
