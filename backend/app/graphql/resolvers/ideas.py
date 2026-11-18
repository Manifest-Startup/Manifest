"""GraphQL resolvers for ideas: list, read, create, update, delete, publish, votes, import and export."""

import asyncio
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.resolvers.documents import _start_background_generation
from app.graphql.resolvers.shared import (
    _ai_request_lock,
    _coerce_datetime,
    _get_ai_cache,
    _require_full_account,
    _set_ai_cache,
)
from app.graphql.types.ideas import (
    ExportResult,
    Idea,
    IdeaSummary,
    ImportResult,
    PublishResult,
    SimilarIdeas,
    VoteResult,
)
from app.services.documents.demo_documents import build_demo_documents
from app.utils.logger import logger


def _ensure_idea_identifier(db, idea_data: dict[str, object]) -> str:
    """Backfill a stable idea_id for older imported rows that were saved without one."""
    existing_idea_id = str(idea_data.get("idea_id") or "").strip()
    if existing_idea_id:
        return existing_idea_id

    generated_idea_id = str(uuid.uuid4())
    idea_data["idea_id"] = generated_idea_id

    try:
        query = db.table("ideas").update({"idea_id": generated_idea_id}).is_("idea_id", None)

        if idea_data.get("user_id") is not None:
            query = query.eq("user_id", idea_data.get("user_id"))
        if idea_data.get("created_at") is not None:
            query = query.eq("created_at", idea_data.get("created_at"))
        if idea_data.get("title") is not None:
            query = query.eq("title", idea_data.get("title"))
        if idea_data.get("description") is not None:
            query = query.eq("description", idea_data.get("description"))

        query.execute()
    except Exception as exc:  # pragma: no cover
        logger.warning(f"[ideas] Failed to backfill missing idea_id: {exc}")

    return generated_idea_id


IDEA_SUMMARY_DB_COLUMNS = (
    "idea_id, user_id, title, created_at, is_published, " "generated_asset_count, has_description"
)


IDEA_DETAIL_DB_COLUMNS = (
    "idea_id, user_id, title, description, created_at, pitch_deck, "
    "product_requirements_document, provisional_patent, business_model_canvas, "
    "similar_ideas, is_published"
)


def _idea_detail_columns(info: strawberry.Info) -> str:
    """Read large text columns only when the operation selects them.

    Strawberry expands named and inline fragments in selected_fields. SQL
    identifiers come exclusively from this allowlist, never from query text.
    """
    columns = ["idea_id", "user_id", "title", "created_at", "is_published"]
    optional = {
        "description": "description",
        "pitchDeck": "pitch_deck",
        "productRequirementsDocument": "product_requirements_document",
        "provisionalPatent": "provisional_patent",
        "businessModelCanvas": "business_model_canvas",
        "similarIdeas": "similar_ideas",
    }

    def collect(selections):
        for selection in selections:
            column = optional.get(getattr(selection, "name", ""))
            if column and column not in columns:
                columns.append(column)
            collect(getattr(selection, "selections", []))

    collect(info.selected_fields)
    return ", ".join(columns)


@strawberry.type
class IdeasQuery:
    @strawberry.field
    async def ideas(
        self,
        info: strawberry.Info,
        first: int = 100,
        after: str | None = None,
    ) -> list[IdeaSummary]:
        """List your startup ideas, newest first (paginate with first/after)."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.list_metadata import (
            IDEA_SUMMARY_DB_COLUMNS as summary_columns,
        )
        from app.services.ideas.list_metadata import (
            decode_ideas_cursor,
            normalize_ideas_page_size,
            read_list_metadata,
        )

        page_size = normalize_ideas_page_size(first)
        db = info.context["db"]

        # Sync DB work (list query + per-row legacy id backfill) runs in a
        # worker thread so the sidebar list never blocks the event loop.
        def _load() -> list[IdeaSummary]:
            query = (
                db.table("ideas")
                .select(summary_columns)
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(page_size)
            )
            if after:
                try:
                    cursor_at, _cursor_id = decode_ideas_cursor(after)
                except ValueError as exc:
                    raise Exception("Invalid pagination cursor") from exc
                query = (
                    db.table("ideas")
                    .select(summary_columns)
                    .eq("user_id", user_id)
                    .lt("created_at", cursor_at.isoformat())
                    .order("created_at", desc=True)
                    .limit(page_size)
                )

            response = query.execute()
            if not response.data:
                return []

            mapped_ideas: list[IdeaSummary] = []
            for idea_data in response.data:
                idea_id = _ensure_idea_identifier(db, idea_data)
                gac, has_desc = read_list_metadata(idea_data)
                raw_ca = idea_data.get("created_at")
                created_at = (
                    _coerce_datetime(raw_ca) if raw_ca is not None else datetime.now(timezone.utc)
                )
                mapped_ideas.append(
                    IdeaSummary(
                        idea_id=idea_id,
                        user_id=str(idea_data.get("user_id") or ""),
                        title=idea_data.get("title", "") or "",
                        description=None,
                        has_description=has_desc,
                        created_at=created_at,
                        is_published=bool(idea_data.get("is_published", False)),
                        generated_asset_count=gac,
                    )
                )
            return mapped_ideas

        return await asyncio.to_thread(_load)

    @strawberry.field
    async def idea(self, info: strawberry.Info, idea_id: str) -> Idea:
        """Read one idea in full: description, stage, generated documents and scores."""
        user_id = get_current_user_id(info.context["request"])

        # A note-only request must not fetch every generated document blob.
        columns = _idea_detail_columns(info)

        def _load() -> Any:
            return (
                info.context["db"]
                .table("ideas")
                .select(columns)
                .eq("idea_id", idea_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

        response = await asyncio.to_thread(_load)
        if not response.data:
            raise Exception("Idea not found")
        idea_data = response.data
        mapped_data = {
            "idea_id": idea_data.get("idea_id"),
            "user_id": idea_data.get("user_id"),
            "title": idea_data.get("title", ""),
            "description": idea_data.get("description"),
            "created_at": idea_data.get("created_at"),
            "pitch_deck": idea_data.get("pitch_deck"),
            "product_requirements_document": idea_data.get("product_requirements_document"),
            "provisional_patent": idea_data.get("provisional_patent"),
            "business_model_canvas": idea_data.get("business_model_canvas"),
            "is_published": idea_data.get("is_published", False),
            "similar_ideas": idea_data.get("similar_ideas"),
        }
        return Idea(**mapped_data)

    @strawberry.field
    async def find_similar_ideas(
        self, info: strawberry.Info, idea_description: str
    ) -> SimilarIdeas:
        """Find existing ideas similar to a description, to check novelty and competition."""
        from app.managers.manifest_manager import manifest_manager

        normalized_description = (idea_description or "").strip()
        cached_result = _get_ai_cache("find_similar_ideas", normalized_description)
        if cached_result is not None:
            return SimilarIdeas(similar_ideas=cached_result or "")

        def generate_similar_ideas() -> str:
            with _ai_request_lock:
                manifest_manager.set_idea(normalized_description)
                manifest_manager.similar_ideas.update()
                return manifest_manager.get_similar_ideas() or ""

        try:
            if manifest_manager.ai_layer.is_available():
                result = await asyncio.to_thread(generate_similar_ideas)
            else:
                result = build_demo_documents(normalized_description).similar_ideas
            _set_ai_cache("find_similar_ideas", normalized_description, result or "")
            return SimilarIdeas(similar_ideas=result or "")
        except Exception as e:
            logger.error(f"Error generating similar ideas: {e}")
            return SimilarIdeas(
                similar_ideas=build_demo_documents(normalized_description).similar_ideas
            )


@strawberry.type
class IdeasMutation:
    @strawberry.mutation
    async def create_idea(
        self, info: strawberry.Info, title: str, description: str | None = None
    ) -> Idea:
        """Create a new startup idea from a title and an optional description."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.list_metadata import compute_idea_list_metadata

        data = {
            "idea_id": str(uuid.uuid4()),
            "title": title,
            "description": description,
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
        }
        data.update(compute_idea_list_metadata(data))
        response = info.context["db"].table("ideas").insert(data).execute()
        inserted = response.data
        if isinstance(inserted, dict):
            inserted = [inserted]

        if not inserted or len(inserted) == 0:
            raise Exception("Failed to create idea")

        idea_id = inserted[0].get("idea_id", data["idea_id"])
        _start_background_generation(idea_id, description)

        idea_fields = {field.name for field in Idea.__dataclass_fields__.values()}
        return Idea(**{k: v for k, v in inserted[0].items() if k in idea_fields})

    @strawberry.mutation
    async def update_idea(
        self,
        info: strawberry.Info,
        idea_id: str,
        title: str | None = None,
        description: str | None = None,
        required_skills: list[str] | None = None,
    ) -> Idea:
        """Change an idea's title, description or required skills."""
        user_id = get_current_user_id(info.context["request"])
        from app.services.ideas.collaboration import create_collaboration_service

        collab_gate = create_collaboration_service(info.context["db"])
        if not await collab_gate.check_access(idea_id, user_id, "edit"):
            raise Exception("Idea not found or you don't have permission to edit it")

        update_data = {}
        # Only include title/description in the UPDATE payload if they contain
        # meaningful content. This prevents accidental overwrites that would
        # wipe out previously-saved data when the frontend temporarily sends
        # an empty string (e.g. when switching between ideas before the
        # editor finishes loading).

        if title is not None and title.strip() != "":
            update_data["title"] = title

        if required_skills is not None:
            update_data["required_skills"] = required_skills

        def _has_meaningful_html(html: str) -> bool:
            """Return True if there is any non-whitespace text after stripping HTML tags & entities."""
            if not html or not isinstance(html, str):
                return False
            text_only = re.sub(r"<[^>]+>", "", html)
            text_only = re.sub(r"&nbsp;|&#160;", " ", text_only)
            text_only = text_only.strip()
            text_only = re.sub(r"[\u200B-\u200D\uFEFF]", "", text_only)
            return text_only != ""

        description_changed = description is not None and _has_meaningful_html(description)
        if description_changed:
            update_data["description"] = description
            update_data["has_description"] = True

        if not update_data:
            raise Exception("No valid fields provided for update")

        response = (
            info.context["db"].table("ideas").update(update_data).eq("idea_id", idea_id).execute()
        )
        if not response.data or len(response.data) == 0:
            raise Exception("Idea not found or not updated")

        # Drop the voice agent's cached conversation context for this idea so
        # the next voice turn sees the new title/description immediately.
        try:
            from app.services.shared.cache import cache_delete

            cache_delete(f"voice:context:{user_id}:{idea_id}")
        except Exception:  # cache invalidation must never fail the mutation
            pass

        _start_background_generation(idea_id, update_data.get("description"))

        title_changed = "title" in update_data
        if title_changed or description_changed:
            try:
                collab_service = create_collaboration_service(info.context["db"])
                await collab_service.maybe_record_auto_version_after_user_edit(idea_id, user_id)
            except Exception as e:
                logger.warning(f"Auto-version creation failed for idea {idea_id}: {e}")

        idea_fields = {field.name for field in Idea.__dataclass_fields__.values()}
        return Idea(**{k: v for k, v in response.data[0].items() if k in idea_fields})

    @strawberry.mutation
    async def delete_idea(self, info: strawberry.Info, idea_id: str) -> bool:
        """Delete an idea owned by the current user.

        Task #48: Hardened with structured logging and explicit error
        classification so production failures (especially FK constraint
        violations on related tables) surface as actionable messages
        instead of opaque "Failed to delete idea" errors. The companion
        startup migration in app/main.py enforces ON DELETE CASCADE on
        every child table that references ideas.idea_id, so a successful
        ownership check should always be followed by a successful delete.
        """
        user_id = get_current_user_id(info.context["request"])
        logger.info(
            "[delete_idea] start user_id=%s idea_id=%s",
            user_id,
            idea_id,
        )

        # Verify the idea exists and belongs to the user before deleting.
        # We deliberately avoid `.single()` here so the row-count handling
        # is explicit and behaves identically across in-memory and Postgres
        # backends: `.limit(1).execute()` always returns a list (possibly
        # empty), and the caller does the matched/unmatched decision.
        try:
            check_response = (
                info.context["db"]
                .table("ideas")
                .select("idea_id")
                .eq("idea_id", idea_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            logger.exception(
                "[delete_idea] ownership check failed user_id=%s idea_id=%s",
                user_id,
                idea_id,
            )
            raise Exception("Failed to delete idea: lookup error") from exc

        check_rows = check_response.data or []
        # Explicit row-count handling: 0 rows = not found / not owned;
        # 1 row = proceed; >1 should be impossible (PK on idea_id) but if
        # it ever happens we still want to refuse cleanly.
        if len(check_rows) != 1:
            logger.info(
                "[delete_idea] not found / not owned user_id=%s idea_id=%s rows=%d",
                user_id,
                idea_id,
                len(check_rows),
            )
            raise Exception(
                "Failed to delete idea: Idea not found or you don't have permission to delete it"
            )

        # Delete the idea. Cascade rules in the database remove all related
        # rows in a single transaction; if the cascade DDL has not been
        # applied yet (older deployment), psycopg2 raises a
        # ForeignKeyViolation, which we translate to a friendly message.
        try:
            delete_response = (
                info.context["db"]
                .table("ideas")
                .delete()
                .eq("idea_id", idea_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as exc:
            exc_name = type(exc).__name__
            # FK violations can surface under several attribute names
            # depending on the driver: psycopg2 uses `pgcode`, PostgREST /
            # supabase-py APIError objects use `code`, and some wrappers
            # expose `error_code`. We check all three so the friendly
            # "related records" classification is reached regardless of
            # which client raised it.
            pgcode = getattr(exc, "pgcode", None)
            api_code = getattr(exc, "code", None)
            err_code = getattr(exc, "error_code", None)
            logger.exception(
                "[delete_idea] delete raised exception user_id=%s idea_id=%s "
                "exc_type=%s pgcode=%s code=%s error_code=%s",
                user_id,
                idea_id,
                exc_name,
                pgcode,
                api_code,
                err_code,
            )
            # 23503 = foreign_key_violation in PostgreSQL
            fk_codes = {"23503"}
            is_fk_violation = (
                pgcode in fk_codes
                or api_code in fk_codes
                or err_code in fk_codes
                or "ForeignKeyViolation" in exc_name
            )
            if is_fk_violation:
                raise Exception(
                    "Failed to delete idea: related records prevented deletion. "
                    "Please contact support if this persists."
                ) from exc
            raise Exception("Failed to delete idea") from exc

        # Prefer RETURNING row count from our QueryBuilder; some clients or
        # edge paths omit deleted rows in `data`. If empty, re-check whether
        # the idea row still exists for this user — gone means success
        # (concurrent delete or driver quirk); still present is a real failure.
        returning_rows = delete_response.data or []
        if len(returning_rows) == 0:
            logger.warning(
                "[delete_idea] delete returned 0 rows in response user_id=%s idea_id=%s "
                "(verifying row existence)",
                user_id,
                idea_id,
            )
            try:
                verify_response = (
                    info.context["db"]
                    .table("ideas")
                    .select("idea_id")
                    .eq("idea_id", idea_id)
                    .eq("user_id", user_id)
                    .limit(1)
                    .execute()
                )
            except Exception as exc:
                logger.exception(
                    "[delete_idea] post-delete verify failed user_id=%s idea_id=%s",
                    user_id,
                    idea_id,
                )
                raise Exception("Failed to delete idea: lookup error") from exc

            verify_rows = verify_response.data or []
            if len(verify_rows) == 0:
                logger.info(
                    "[delete_idea] success after empty RETURNING user_id=%s idea_id=%s "
                    "(row absent on verify)",
                    user_id,
                    idea_id,
                )
                return True

            logger.warning(
                "[delete_idea] delete affected 0 rows and row still present user_id=%s idea_id=%s",
                user_id,
                idea_id,
            )
            raise Exception("Failed to delete idea")

        logger.info(
            "[delete_idea] success user_id=%s idea_id=%s rows_deleted=%d",
            user_id,
            idea_id,
            len(returning_rows),
        )
        return True

    @strawberry.mutation
    async def toggle_publish_idea(self, info: strawberry.Info, idea_id: str) -> PublishResult:
        """Toggle the publish status of an idea. Published ideas become available in public discovery."""
        user_id = _require_full_account(info.context["db"], info.context["request"])

        # First get current publish state and copy for pitch reel
        check_response = (
            info.context["db"]
            .table("ideas")
            .select("idea_id, is_published, title, description")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if not check_response.data:
            raise Exception("Idea not found or you don't have permission to modify it")

        idea_row = check_response.data
        current_status = idea_row.get("is_published", False)
        new_status = not current_status

        # Update the idea
        update_response = (
            info.context["db"]
            .table("ideas")
            .update({"is_published": new_status})
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not update_response.data or len(update_response.data) == 0:
            raise Exception("Failed to update idea publish status")

        if new_status:
            from app.services.pitch_reels.service import create_pitch_reel_service
            from app.services.pitch_reels.video_worker import schedule_pitch_reel_video_generation

            reel_service = create_pitch_reel_service(info.context["db"])
            reel_id, needs_video = reel_service.upsert_reel_for_published_idea(
                idea_id,
                user_id,
                idea_row.get("title"),
                idea_row.get("description"),
            )
            if needs_video:  # no-op unless Open Media and video generation are enabled
                schedule_pitch_reel_video_generation(
                    reel_id,
                    str(idea_row.get("title") or ""),
                    str(idea_row.get("description") or ""),
                )
        else:
            from app.services.pitch_reels.service import create_pitch_reel_service

            await asyncio.to_thread(
                create_pitch_reel_service(info.context["db"]).unpublish_reel_for_idea, idea_id
            )

        return PublishResult(idea_id=idea_id, is_published=new_status)

    @strawberry.mutation
    async def upvote_idea(self, info: strawberry.Info, idea_id: str) -> VoteResult:
        """Upvote an idea"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])

        await service.upvote_idea(idea_id, user_id)
        vote_count = await service.get_idea_vote_count(idea_id)
        return VoteResult(voted=True, idea_id=idea_id, vote_count=vote_count)

    @strawberry.mutation
    async def remove_vote(self, info: strawberry.Info, idea_id: str) -> VoteResult:
        """Remove vote from an idea"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])

        await service.remove_vote(idea_id, user_id)
        vote_count = await service.get_idea_vote_count(idea_id)
        return VoteResult(voted=False, idea_id=idea_id, vote_count=vote_count)

    @strawberry.mutation
    async def toggle_upvote(self, info: strawberry.Info, idea_id: str) -> VoteResult:
        """Toggle upvote on an idea"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.social.graph import create_social_graph_service

        service = create_social_graph_service(info.context["db"])

        result = await service.toggle_upvote(idea_id, user_id)
        vote_count = await service.get_idea_vote_count(idea_id)
        return VoteResult(voted=result["voted"], idea_id=idea_id, vote_count=vote_count)

    @strawberry.mutation
    async def export_ideas(self, info: strawberry.Info, format: str = "json") -> ExportResult:
        """Export all user's ideas in the specified format (json, csv, markdown).

        Bulk export of user data is a sensitive action (full data
        exfiltration vector if a session token is stolen) so we require
        recent auth — fresh login OR live step-up verification — before
        producing the archive.
        """
        import base64

        from app.auth.current_user import get_current_session_id_optional
        from app.security.step_up import (
            DEFAULT_TTL_SECONDS,
            _recent_login_satisfies,
            has_recent_step_up,
        )
        from app.services.ideas.import_export import ImportExportService

        request = info.context["request"]
        user_id = get_current_user_id(request)
        if not _recent_login_satisfies(request, DEFAULT_TTL_SECONDS):
            session_id = get_current_session_id_optional(request)
            if not has_recent_step_up(user_id, session_id, max_age_seconds=DEFAULT_TTL_SECONDS):
                raise Exception("Re-authentication required for bulk export (step-up MFA needed).")

        # Fetch all ideas for the user
        response = info.context["db"].table("ideas").select("*").eq("user_id", user_id).execute()
        ideas = response.data if response.data else []

        if not ideas:
            raise Exception("No ideas found to export")

        service = ImportExportService()
        format_lower = format.lower()

        if format_lower == "json":
            content = service.export_to_json(ideas)
            filename = f"manifest_ideas_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        elif format_lower == "csv":
            content = service.export_to_csv(ideas)
            filename = f"manifest_ideas_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        elif format_lower == "markdown":
            content = service.export_to_markdown(ideas)
            filename = f"manifest_ideas_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.md"
        else:
            raise Exception(f"Unsupported export format: {format}")

        # Encode content as base64 for safe transmission
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        return ExportResult(content=content_b64, format=format_lower, filename=filename)

    @strawberry.mutation
    async def import_ideas(
        self, info: strawberry.Info, file_content: str, file_format: str, filename: str
    ) -> ImportResult:
        """Import startup ideas from note exports and backups."""
        import base64

        from app.services.ideas.import_export import ImportExportService

        user_id = get_current_user_id(info.context["request"])
        service = ImportExportService()

        imported_count = 0
        skipped_count = 0
        errors = []

        try:
            file_bytes = base64.b64decode(file_content)
            prepared_import = service.prepare_import(file_bytes, file_format, filename)
            imported_ideas = prepared_import["ideas"]
            skipped_count += prepared_import["skipped_non_ideas"]
            errors.extend(prepared_import["warnings"])

            existing_response = (
                info.context["db"]
                .table("ideas")
                .select("title, description")
                .eq("user_id", user_id)
                .execute()
            )
            existing_ideas = (
                existing_response.data if existing_response and existing_response.data else []
            )
            existing_fingerprints = {
                service.idea_fingerprint(existing_idea) for existing_idea in existing_ideas
            }

            # Insert imported ideas into database
            for idea_data in imported_ideas:
                try:
                    fingerprint = service.idea_fingerprint(idea_data)
                    if fingerprint in existing_fingerprints:
                        skipped_count += 1
                        continue

                    idea_id = str(uuid.uuid4())
                    data = {
                        "idea_id": idea_id,
                        "title": idea_data.get("title", "Imported Idea"),
                        "description": idea_data.get("description", ""),
                        "summary": idea_data.get("summary", ""),
                        "tags": idea_data.get("tags", ""),
                        "user_id": user_id,
                        "created_at": datetime.utcnow().isoformat(),
                    }
                    response = info.context["db"].table("ideas").insert(data).execute()
                    if response.data:
                        imported_count += 1
                        existing_fingerprints.add(fingerprint)
                    else:
                        skipped_count += 1
                except Exception as e:
                    skipped_count += 1
                    errors.append(
                        f"Failed to import '{idea_data.get('title', 'Untitled')}': {str(e)}"
                    )

            return ImportResult(
                imported_count=imported_count, skipped_count=skipped_count, errors=errors
            )
        except Exception as e:
            logger.error(f"Error importing ideas: {e}")
            raise Exception(f"Import failed: {str(e)}") from e
