"""GraphQL resolvers for generated documents (pitch deck, PRD, provisional patent) and generation jobs."""

import asyncio

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.resolvers.shared import _ai_request_lock
from app.graphql.types.documents import (
    EnqueueJobResult,
    GenerationJob,
    Patent,
    PitchDeckOutput,
    ProductRequirementsDocumentOutput,
    ProvisionalPatentOutput,
    _to_generation_job,
)
from app.services.ai.credentials import start_thread_with_current_key
from app.services.documents.demo_documents import build_demo_documents
from app.services.ideas import generation_jobs as job_service
from app.utils.logger import logger


def _generate_documents_for_idea(idea_id: str, description: str):
    """Generate all documents (BMC, pitch deck, PRD, patent) for an idea using AI and save to DB."""
    from app.services.ideas.document_generation import generate_background_tasks

    generate_background_tasks(description, idea_id)


def _start_background_generation(idea_id: str, description: str | None) -> bool:
    """Start fire-and-forget document generation when a description is present."""
    if not description or not description.strip():
        return False

    start_thread_with_current_key(_generate_documents_for_idea, idea_id, description)
    return True


def _get_pitch_deck(description: str) -> str:
    from app.managers.manifest_manager import manifest_manager

    manifest_manager.set_idea(description)
    if manifest_manager.ai_layer.is_available():
        try:
            return manifest_manager.generate_pitch_deck()
        except Exception as exc:
            logger.error(f"[GraphQL] Falling back to demo pitch deck generation: {exc}")

    return build_demo_documents(description).pitch_deck


def _get_product_requirements_document(description: str) -> str:
    from app.managers.manifest_manager import manifest_manager

    manifest_manager.set_idea(description)
    if manifest_manager.ai_layer.is_available():
        try:
            return manifest_manager.generate_product_requirements_document()
        except Exception as exc:
            logger.error(f"[GraphQL] Falling back to demo PRD generation: {exc}")

    return build_demo_documents(description).product_requirements_document


def _get_provisional_patent(description: str) -> str:
    from app.managers.manifest_manager import manifest_manager

    manifest_manager.set_idea(description)
    if manifest_manager.ai_layer.is_available():
        try:
            from app.services.documents.provisional_patent import ProvisionalPatent

            patent_service = ProvisionalPatent(manifest_manager)
            return patent_service.generate()
        except Exception as exc:
            logger.error(f"[GraphQL] Falling back to demo provisional patent generation: {exc}")

    return build_demo_documents(description).provisional_patent


def _update_idea_generated_field(
    db, idea_id: str, user_id: str | None, field_name: str, value: str
) -> None:
    if not user_id:
        return

    (
        db.table("ideas")
        .update({field_name: value})
        .eq("idea_id", idea_id)
        .eq("user_id", user_id)
        .execute()
    )
    from app.services.ideas.list_metadata import refresh_idea_list_metadata

    refresh_idea_list_metadata(db, idea_id, user_id)


@strawberry.type
class DocumentsQuery:
    @strawberry.field
    async def generation_job(self, info: strawberry.Info, job_id: str) -> GenerationJob | None:
        """Poll the status of an async document-generation job (Phase 3).

        Only the job's owner can read it; returns null for a missing or
        not-owned job.
        """
        user_id = get_current_user_id(info.context["request"])
        job = job_service.get_job(info.context["db"], job_id)
        if not job:
            return None
        owner = job.get("user_id")
        if owner and owner != user_id:
            return None
        return _to_generation_job(job)

    @strawberry.field
    async def patents(self, info: strawberry.Info) -> list[Patent]:
        # Placeholder: Replace with actual DB logic
        """List your provisional patent drafts."""
        return []

    @strawberry.field
    async def pitch_deck(self, info: strawberry.Info, idea_id: str) -> PitchDeckOutput:
        """Read the pitch deck generated for an idea."""
        user_id = get_current_user_id(info.context["request"])
        result = (
            info.context["db"]
            .table("ideas")
            .select("pitch_deck")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if not result.data or not result.data.get("pitch_deck"):
            raise Exception("Pitch deck not found")
        return PitchDeckOutput(pitch_deck=result.data["pitch_deck"])

    @strawberry.field
    async def product_requirements_document(
        self, info: strawberry.Info, idea_id: str
    ) -> ProductRequirementsDocumentOutput:
        """Read the product requirements document (PRD) generated for an idea."""
        user_id = get_current_user_id(info.context["request"])
        result = (
            info.context["db"]
            .table("ideas")
            .select("product_requirements_document")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if not result.data or not result.data.get("product_requirements_document"):
            raise Exception("Product requirements document not found")
        return ProductRequirementsDocumentOutput(
            product_requirements_document=result.data["product_requirements_document"]
        )

    @strawberry.field
    async def provisional_patent(
        self, info: strawberry.Info, idea_id: str
    ) -> ProvisionalPatentOutput:
        # Try to get patent data from intellectual_properties table
        """Read the provisional patent draft generated for an idea."""
        user_id = get_current_user_id(info.context["request"])

        coversheet_pdf = None
        specification_pdf = None
        provisional_patent_text = None

        # First, try to get from intellectual_properties table (for PDFs)
        try:
            ip_response = (
                info.context["db"]
                .table("intellectual_properties")
                .select("*")
                .eq("idea_id", idea_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if ip_response.data:
                # Get PDF URLs from intellectual_properties table
                pdf_url_data = ip_response.data.get("pdf_url")
                if pdf_url_data:
                    import json

                    try:
                        # Try to parse as JSON (new format with both PDFs)
                        pdf_urls = json.loads(pdf_url_data)
                        specification_pdf = pdf_urls.get("specification_pdf")
                        coversheet_pdf = pdf_urls.get("coversheet_pdf")
                    except (json.JSONDecodeError, TypeError):
                        # Fallback: if it's a plain string URL, assume it's the specification
                        specification_pdf = pdf_url_data
        except Exception:
            # If intellectual_properties query fails, continue to try ideas table
            pass

        # Also try to get text draft from ideas table
        idea_response = (
            info.context["db"]
            .table("ideas")
            .select("provisional_patent")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if idea_response.data and idea_response.data.get("provisional_patent"):
            provisional_patent_text = idea_response.data["provisional_patent"]

        if not provisional_patent_text and not coversheet_pdf and not specification_pdf:
            raise Exception("Provisional patent draft not found")

        return ProvisionalPatentOutput(
            provisional_patent=provisional_patent_text or "",
            coversheet_pdf=coversheet_pdf,
            specification_pdf=specification_pdf,
        )


@strawberry.type
class DocumentsMutation:
    @strawberry.mutation
    async def generate_pitch_deck(
        self, info: strawberry.Info, idea_id: str, description: str
    ) -> PitchDeckOutput:
        # Offload the blocking LLM generation to a worker thread so the 10-30s
        # call doesn't stall the event loop; serialize singleton access with
        # _ai_request_lock (same pattern as find_similar_ideas).
        """Generate (or regenerate) the pitch deck for an idea. Uses your OpenAI key."""

        def _generate() -> str:
            with _ai_request_lock:
                return _get_pitch_deck(description)

        pitch_deck = await asyncio.to_thread(_generate)
        idea_row = (
            info.context["db"]
            .table("ideas")
            .select("user_id")
            .eq("idea_id", idea_id)
            .single()
            .execute()
        )
        user_id = idea_row.data["user_id"] if idea_row.data else None
        _update_idea_generated_field(info.context["db"], idea_id, user_id, "pitch_deck", pitch_deck)
        if user_id:
            info.context["db"].table("pitch_decks").upsert(
                {
                    "idea_id": idea_id,
                    "user_id": user_id,
                    "description": pitch_deck,
                },
                on_conflict=["idea_id"],
            ).execute()
        return PitchDeckOutput(pitch_deck=pitch_deck)

    @strawberry.mutation
    async def generate_product_requirements_document(
        self, info: strawberry.Info, idea_id: str, description: str
    ) -> ProductRequirementsDocumentOutput:
        """Generate (or regenerate) the PRD for an idea. Uses your OpenAI key."""

        def _generate() -> str:
            with _ai_request_lock:
                return _get_product_requirements_document(description)

        prd = await asyncio.to_thread(_generate)
        idea_row = (
            info.context["db"]
            .table("ideas")
            .select("user_id")
            .eq("idea_id", idea_id)
            .single()
            .execute()
        )
        user_id = idea_row.data["user_id"] if idea_row.data else None
        _update_idea_generated_field(
            info.context["db"], idea_id, user_id, "product_requirements_document", prd
        )
        if user_id:
            info.context["db"].table("product_requirements_documents").upsert(
                {
                    "idea_id": idea_id,
                    "user_id": user_id,
                    "description": prd,
                },
                on_conflict=["idea_id"],
            ).execute()
        return ProductRequirementsDocumentOutput(product_requirements_document=prd)

    @strawberry.mutation
    async def generate_provisional_patent(
        self, info: strawberry.Info, idea_id: str, description: str
    ) -> ProvisionalPatentOutput:
        """Draft a provisional patent for an idea. A draft, not legal advice. Uses your OpenAI key."""

        def _generate() -> str:
            with _ai_request_lock:
                return _get_provisional_patent(description)

        draft = await asyncio.to_thread(_generate)
        idea_row = (
            info.context["db"]
            .table("ideas")
            .select("user_id")
            .eq("idea_id", idea_id)
            .single()
            .execute()
        )
        user_id = idea_row.data["user_id"] if idea_row.data else None
        _update_idea_generated_field(
            info.context["db"], idea_id, user_id, "provisional_patent", draft
        )

        spec_pdf_url = None
        coversheet_pdf_url = None
        try:
            from app.services.ideas.document_generation import generate_patent_pdfs

            spec_pdf_url, coversheet_pdf_url = generate_patent_pdfs(idea_id, user_id, draft)
        except Exception as exc:
            logger.warning(f"[GraphQL] Patent PDF generation failed: {exc}")

        return ProvisionalPatentOutput(
            provisional_patent=draft,
            specification_pdf=spec_pdf_url,
            coversheet_pdf=coversheet_pdf_url,
        )

    @strawberry.mutation
    async def run_background_tasks(
        self, info: strawberry.Info, idea_id: str, description: str
    ) -> bool:
        """Trigger asynchronous background tasks that were previously exposed via REST (POST /api/idea/{idea_id}/background-tasks)."""
        return _start_background_generation(idea_id, description)

    @strawberry.mutation
    async def enqueue_background_tasks(
        self,
        info: strawberry.Info,
        idea_id: str,
        document_types: list[str],
        idempotency_key: str | None = None,
    ) -> EnqueueJobResult:
        """Enqueue document generation as a durable job and return immediately
        (Phase 3). The dedicated worker drains the queue; poll ``generationJob``
        for status. Unlike the legacy fire-and-forget ``runBackgroundTasks``,
        the work survives a process restart and is deduplicated per
        ``idempotencyKey``. Returns the existing job if one is already in flight
        for that key.
        """
        user_id = get_current_user_id(info.context["request"])
        job = job_service.create_job(
            info.context["db"],
            user_id=user_id,
            idea_id=idea_id,
            document_types=document_types,
            idempotency_key=idempotency_key,
        )
        return EnqueueJobResult(job_id=str(job["id"]), status=str(job["status"]))
