"""GraphQL types and mappers for generated documents (pitch deck, PRD, provisional patent) and generation jobs."""

from datetime import datetime
from typing import Any

import strawberry


@strawberry.type
class PitchDeckOutput:
    pitch_deck: str


@strawberry.type
class ProductRequirementsDocumentOutput:
    product_requirements_document: str


@strawberry.type
class ProvisionalPatentOutput:
    provisional_patent: str
    coversheet_pdf: str | None = None
    specification_pdf: str | None = None


@strawberry.type
class GenerationJob:
    """Status of an async document-generation job (Phase 3 queue)."""

    id: str
    status: str
    document_types: list[str]
    idea_id: str | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@strawberry.type
class EnqueueJobResult:
    job_id: str
    status: str


def _to_generation_job(job: dict[str, Any]) -> GenerationJob:
    return GenerationJob(
        id=str(job.get("id") or ""),
        status=str(job.get("status") or ""),
        document_types=list(job.get("document_types") or []),
        idea_id=job.get("idea_id"),
        error_message=job.get("error_message"),
        created_at=job.get("created_at"),
        updated_at=job.get("updated_at"),
    )


@strawberry.type
class Patent:
    patent_id: str
    title: str
    description: str | None
    created_at: datetime


@strawberry.type
class DocumentGuide:
    """Manifest's own instructions for a document, for the person's AI agent to follow."""

    document_type: str
    title: str
    system: str
    instructions: str
    save_with: str


@strawberry.type
class SavedDocument:
    idea_id: str
    document_type: str
    title: str
    characters: int
