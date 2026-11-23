import asyncio
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from threading import Lock
from urllib.parse import quote

from dotenv import load_dotenv

try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore[assignment]

from app.assets import ASSETS_DIR
from app.db.database import create_database_client, get_db_connection
from app.services.documents.demo_documents import build_demo_documents
from app.services.integrations.connections import connected_partner_names
from app.utils.logger import logger

if os.path.exists(".env"):
    load_dotenv()

logger.info("idea_utils loaded with PostgreSQL database")

PROJECT_ROOT = (
    Path(__file__).resolve().parents[4]
)  # repository root (generated/ lives here locally)
GENERATED_PDF_ROOT = PROJECT_ROOT / "generated" / "pdfs"
USPTO_COVERSHEET_TEMPLATE = ASSETS_DIR / "uspto" / "sb0016.pdf"

# Lock to serialize access to manifest_manager during document generation
# This prevents race conditions when multiple ideas are being processed concurrently
_manifest_manager_lock = Lock()


def _get_idea_user_id(idea_id):
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT user_id FROM ideas WHERE idea_id = %s", (idea_id,))
            row = cur.fetchone()
            return str(row["user_id"]) if row else None
    except RuntimeError as exc:
        logger.info(f"Falling back to database client for user lookup on idea_id {idea_id}: {exc}")
        result = (
            create_database_client()
            .table("ideas")
            .select("user_id")
            .eq("idea_id", idea_id)
            .single()
            .execute()
        )
        row = result.data if result else None
        return str(row["user_id"]) if row and row.get("user_id") else None


def _get_idea_owner_profile(idea_id):
    query = """
        SELECT
            i.user_id,
            u.email,
            u.first_name,
            u.last_name,
            u.username,
            u.address,
            u.state,
            u.country
        FROM ideas i
        LEFT JOIN users u ON u.user_id = i.user_id
        WHERE i.idea_id = %s
    """

    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(query, (idea_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    except RuntimeError as exc:
        logger.info(f"Falling back to database client for owner lookup on idea_id {idea_id}: {exc}")
        idea_result = (
            create_database_client()
            .table("ideas")
            .select("user_id")
            .eq("idea_id", idea_id)
            .single()
            .execute()
        )
        idea_row = idea_result.data if idea_result else None
        if not idea_row or not idea_row.get("user_id"):
            return None

        user_result = (
            create_database_client()
            .table("users")
            .select("user_id, email, first_name, last_name, username, address, state, country")
            .eq("user_id", idea_row["user_id"])
            .single()
            .execute()
        )
        user_row = user_result.data if user_result else {}
        profile = {"user_id": str(idea_row["user_id"])}
        profile.update(user_row or {})
        return profile


def _normalize_profile_text(value):
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _display_name_from_profile(profile):
    if not profile:
        return ""

    first_name = _normalize_profile_text(profile.get("first_name"))
    last_name = _normalize_profile_text(profile.get("last_name"))
    if first_name or last_name:
        return " ".join(part for part in [first_name, last_name] if part)

    username = _normalize_profile_text(profile.get("username"))
    if username:
        return username

    email = _normalize_profile_text(profile.get("email"))
    if email:
        return email.split("@", 1)[0]

    return ""


def _split_address_components(address):
    normalized = _normalize_profile_text(address)
    if not normalized:
        return {
            "street": "",
            "city": "",
            "state": "",
            "zip_code": "",
            "country": "",
        }

    parts = [part.strip() for part in normalized.split(",") if part.strip()]
    street = normalized
    city = ""
    state = ""
    zip_code = ""
    country = ""

    if len(parts) >= 2:
        street = parts[0]
        city = parts[1]
    if len(parts) >= 3:
        state_zip = parts[2].split()
        if state_zip:
            state = state_zip[0]
            if len(state_zip) > 1:
                zip_code = " ".join(state_zip[1:])
    if len(parts) >= 4:
        country = parts[3]

    return {
        "street": street,
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "country": country,
    }


def _build_patent_coversheet_field_data(title, owner_profile):
    owner_profile = owner_profile or {}
    display_name = _display_name_from_profile(owner_profile)
    first_name = _normalize_profile_text(owner_profile.get("first_name"))
    last_name = _normalize_profile_text(owner_profile.get("last_name"))

    if not first_name and not last_name and display_name:
        name_parts = display_name.split()
        if len(name_parts) > 1:
            first_name = " ".join(name_parts[:-1])
            last_name = name_parts[-1]
        else:
            first_name = display_name

    address_parts = _split_address_components(owner_profile.get("address"))
    state = _normalize_profile_text(owner_profile.get("state")) or address_parts["state"]
    country = _normalize_profile_text(owner_profile.get("country")) or address_parts["country"]
    city = address_parts["city"]
    residence_location = ", ".join(part for part in [city, state or country] if part)

    email = _normalize_profile_text(owner_profile.get("email"))
    phone_number = _normalize_profile_text(owner_profile.get("phone_number"))

    return {
        "given_name": first_name,
        "family_name": last_name,
        "first_named_inventor": display_name if not (first_name or last_name) else "",
        "residence_location": residence_location,
        "title_of_invention": title,
        "name_of_applicant": display_name,
        "correspondence_address": address_parts["street"],
        "city": city,
        "state": state,
        "zip_code": address_parts["zip_code"],
        "country": country,
        "phone_number": phone_number,
        "email": email,
        "signature": display_name,
        "typed_or_printed_name": display_name,
        "registration_number": "",
        "telephone": phone_number,
        "docket_number": "",
        "date": datetime.utcnow().strftime("%m/%d/%Y"),
    }


def _authored_documents(idea_id, columns):
    """The ``columns`` whose stored document someone wrote (not a template), so keep it."""
    if not columns:
        return set()
    from app.services.documents.demo_documents import is_template

    wanted = sorted(columns)
    try:
        rows = (
            create_database_client()
            .table("ideas")
            .select(", ".join(wanted))
            .eq("idea_id", idea_id)
            .limit(1)
            .execute()
            .data
        )
    except Exception as exc:  # noqa: BLE001 — unknown means "nothing to protect"
        logger.info(f"Could not read stored documents for idea_id {idea_id}: {exc}")
        return set()
    row = (rows[0] if isinstance(rows, list) and rows else rows) or {}
    if not isinstance(row, dict):
        return set()
    return {c for c in wanted if not is_template(c, row.get(c))}


def _with_saved_sections(idea_id, canvas):
    """A template canvas with every section someone saved on its own laid over it."""
    from app.services.canvas.orchestrator import merge_section_into_canvas

    try:
        rows = (
            create_database_client()
            .table("business_model_canvas_sections")
            .select("section_name, content")
            .eq("idea_id", idea_id)
            .execute()
            .data
        )
    except Exception as exc:  # noqa: BLE001
        logger.info(f"Could not read canvas sections for idea_id {idea_id}: {exc}")
        return canvas
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and row.get("section_name") and (row.get("content") or "").strip():
            canvas = merge_section_into_canvas(canvas, row["section_name"], row["content"])
    return canvas


def _update_idea_documents(idea_id, update_data):
    document_fields = {
        key: value for key, value in update_data.items() if key not in ("idea_id", "user_id")
    }
    if not document_fields:
        return

    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            set_clauses = []
            values = []
            for key, value in document_fields.items():
                set_clauses.append(f"{key} = %s")
                values.append(value)
            values.append(idea_id)
            cur.execute(f"UPDATE ideas SET {', '.join(set_clauses)} WHERE idea_id = %s", values)
            conn.commit()
    except RuntimeError as exc:
        logger.info(f"Falling back to database client for idea update on idea_id {idea_id}: {exc}")
        create_database_client().table("ideas").update(document_fields).eq(
            "idea_id", idea_id
        ).execute()

    user_id = update_data.get("user_id")
    if user_id:
        from app.services.ideas.list_metadata import refresh_idea_list_metadata

        refresh_idea_list_metadata(create_database_client(), idea_id, str(user_id))


def _upsert_generated_document(table_name, idea_id, user_id, description):
    payload = {
        "idea_id": idea_id,
        "user_id": user_id,
        "description": description,
    }

    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                        INSERT INTO {table_name} (idea_id, user_id, description)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (idea_id) DO UPDATE SET description = EXCLUDED.description
                    """,
                (idea_id, user_id, description),
            )
            conn.commit()
    except RuntimeError as exc:
        logger.info(
            f"Falling back to database client for {table_name} upsert on idea_id {idea_id}: {exc}"
        )
        create_database_client().table(table_name).upsert(payload, on_conflict="idea_id").execute()


def _upsert_patent_pdfs(idea_id, user_id, title, spec_pdf_url, coversheet_pdf_url):
    import uuid

    ip_payload = {
        "ip_id": str(uuid.uuid4()),
        "idea_id": idea_id,
        "user_id": user_id,
        "type": "provisional_patent",
        "title_of_invention": title,
        "pdf_url": json.dumps(
            {
                "specification_pdf": spec_pdf_url,
                "coversheet_pdf": coversheet_pdf_url,
            }
        ),
        "status": "draft",
    }

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                        INSERT INTO intellectual_properties (ip_id, idea_id, user_id, type, title_of_invention, pdf_url, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (idea_id) DO UPDATE SET
                            pdf_url = EXCLUDED.pdf_url,
                            status = EXCLUDED.status
                    """,
                    (
                        ip_payload["ip_id"],
                        idea_id,
                        user_id,
                        ip_payload["type"],
                        title,
                        ip_payload["pdf_url"],
                        ip_payload["status"],
                    ),
                )
                conn.commit()
    except RuntimeError as exc:
        logger.info(
            f"Falling back to database client for patent PDF upsert on idea_id {idea_id}: {exc}"
        )
        create_database_client().table("intellectual_properties").upsert(
            ip_payload, on_conflict="idea_id"
        ).execute()


def _extract_markdown_section(section, text):
    match = re.search(rf"^# {re.escape(section)}\n(.+?)(?=^# |\Z)", text, re.DOTALL | re.MULTILINE)
    return match.group(1).strip() if match else ""


# Helper function to generate background tasks for updating the idea
def generate_background_tasks(  # noqa: C901
    idea_description, idea_id, sio=None, sid=None, loop=None
):
    from app.managers.manifest_manager import manifest_manager

    if not idea_description:
        logger.info(
            f"No description provided for idea_id {idea_id}. Skipping background generation."
        )
        return
    try:
        logger.info(
            f"Generating background tasks for idea_id {idea_id} with description length: {len(idea_description) if idea_description else 0}"
        )
        owner_profile = None
        try:
            owner_profile = _get_idea_owner_profile(idea_id)
        except Exception as e:
            logger.error(f"Error fetching owner profile for idea_id {idea_id}: {e}")

        demo_documents = build_demo_documents(idea_description)
        similar_ideas_markdown = None
        bmc_markdown = None
        pitch_deck = None
        prd = None
        patent_draft = None

        # Use lock to ensure thread-safe access to manifest_manager
        # This prevents race conditions where multiple tasks overwrite each other's idea state
        with _manifest_manager_lock:
            logger.info(f"[Lock] Acquired lock for idea_id {idea_id}")
            manifest_manager.set_idea(idea_description)
            manifest_manager.set_connected_partners(
                connected_partner_names((owner_profile or {}).get("user_id"))
            )

            # Verify the idea description was set correctly before proceeding
            current_description = manifest_manager.idea.description
            if current_description != idea_description:
                logger.warning(
                    f"[Lock] Idea description mismatch for idea_id {idea_id}. Expected length: {len(idea_description)}, got length: {len(current_description) if current_description else 0}"
                )
                # Reset with correct description
                manifest_manager.set_idea(idea_description)

            ai_available = manifest_manager.ai_layer.is_available()
            if ai_available:
                # Update the manifest; This will update the similar ideas and the BMC
                try:
                    manifest_manager.update()
                    logger.info("Manifest manager update completed successfully")
                except Exception as e:
                    logger.error(f"Error during manifest_manager.update(): {e}")

                # Get the similar ideas and the BMC
                try:
                    similar_ideas_markdown = manifest_manager.get_similar_ideas()
                    logger.info(
                        f"Similar ideas retrieved, length: {len(similar_ideas_markdown) if similar_ideas_markdown else 0}"
                    )
                except Exception as e:
                    logger.error(f"Error getting similar ideas: {e}")
                    similar_ideas_markdown = None

                try:
                    # Double-check that we're still using the correct idea description
                    current_description_check = manifest_manager.idea.description
                    if current_description_check != idea_description:
                        logger.error(
                            f"[Lock] CRITICAL: Idea description changed during BMC generation for idea_id {idea_id}! Regenerating with correct description..."
                        )
                        manifest_manager.set_idea(idea_description)
                        manifest_manager.bmc.update()

                    bmc_markdown = manifest_manager.bmc.summary
                    logger.info(
                        f"BMC summary retrieved, length: {len(bmc_markdown) if bmc_markdown else 0}"
                    )
                    if not bmc_markdown:
                        logger.warning(
                            f"BMC summary is None or empty for idea_id {idea_id}. Attempting to regenerate..."
                        )
                        # Ensure idea is set correctly before regenerating
                        manifest_manager.set_idea(idea_description)
                        # Try to regenerate BMC
                        manifest_manager.bmc.update()
                        bmc_markdown = manifest_manager.bmc.summary
                        logger.info(
                            f"After regeneration, BMC length: {len(bmc_markdown) if bmc_markdown else 0}"
                        )
                        if not bmc_markdown:
                            logger.error(
                                f"BMC regeneration failed for idea_id {idea_id}. Summary is still None/empty. Check AI layer and API configuration."
                            )
                except Exception as e:
                    import traceback

                    logger.error(f"Error getting BMC: {e}")
                    logger.error(f"BMC error traceback: {traceback.format_exc()}")
                    bmc_markdown = None

                # Generate pitch deck explicitly to ensure it's created
                try:
                    pitch_deck = manifest_manager.generate_pitch_deck()
                    logger.info(
                        f"Pitch deck generated successfully, length: {len(pitch_deck) if pitch_deck else 0}"
                    )
                except Exception as e:
                    logger.error(f"Error generating pitch deck: {e}")
                    pitch_deck = None

                # Generate product requirements document explicitly to ensure it's created
                try:
                    prd = manifest_manager.generate_product_requirements_document()
                    logger.info(f"PRD generated successfully, length: {len(prd) if prd else 0}")
                except Exception as e:
                    logger.error(f"Error generating PRD: {e}")
                    prd = None

                # Generate provisional patent draft and PDFs (also uses manifest_manager)
                try:
                    logger.info(
                        f"[Patent] Generating provisional patent draft for idea_id {idea_id}"
                    )
                    from app.services.documents.provisional_patent import ProvisionalPatent

                    patent_service = ProvisionalPatent(manifest_manager)
                    patent_draft = patent_service.generate()
                    logger.info(
                        f"[Patent] Generated provisional patent draft for idea_id {idea_id}"
                    )

                    user_id_for_pdfs = (
                        str(owner_profile["user_id"])
                        if owner_profile and owner_profile.get("user_id")
                        else None
                    )
                    spec_pdf_url, coversheet_pdf_url = generate_patent_pdfs(
                        idea_id, user_id_for_pdfs, patent_draft, owner_profile=owner_profile
                    )
                except Exception as e:
                    logger.error(f"[Patent] Error in patent background generation: {e}")
            else:
                logger.info(
                    f"AI unavailable for idea_id {idea_id}. Using deterministic demo document generation."
                )

            logger.info(f"[Lock] Releasing lock for idea_id {idea_id}")

        # A template only fills a gap: it never replaces a document the person's own agent
        # (or the person) wrote, so keyless edits stop reverting real writing to the template.
        templated = {
            column
            for column, value in (
                ("similar_ideas", similar_ideas_markdown),
                ("business_model_canvas", bmc_markdown),
                ("pitch_deck", pitch_deck),
                ("product_requirements_document", prd),
                ("provisional_patent", patent_draft),
            )
            if not value
        }
        keep = _authored_documents(idea_id, templated)
        if not similar_ideas_markdown and "similar_ideas" not in keep:
            similar_ideas_markdown = demo_documents.similar_ideas
        if not bmc_markdown and "business_model_canvas" not in keep:
            bmc_markdown = _with_saved_sections(idea_id, demo_documents.business_model_canvas)
        if not pitch_deck and "pitch_deck" not in keep:
            pitch_deck = demo_documents.pitch_deck
        if not prd and "product_requirements_document" not in keep:
            prd = demo_documents.product_requirements_document
        if not patent_draft and "provisional_patent" not in keep:
            patent_draft = demo_documents.provisional_patent
        if keep:
            logger.info(
                f"Kept written documents for idea_id {idea_id} instead of templates: {sorted(keep)}"
            )

        # Fetch user_id for the idea (outside lock - database operations don't need serialization)
        user_id = (
            str(owner_profile["user_id"])
            if owner_profile and owner_profile.get("user_id")
            else None
        )
        if not user_id:
            try:
                user_id = _get_idea_user_id(idea_id)
            except Exception as e:
                logger.error(f"Error fetching user_id for idea_id {idea_id}: {e}")

        # Prepare data for updating the idea
        # Only include fields that have actual content
        update_data = {
            "idea_id": idea_id,
            "user_id": user_id,
        }

        if bmc_markdown:
            update_data["business_model_canvas"] = bmc_markdown
            logger.info(f"BMC markdown generated successfully (length: {len(bmc_markdown)})")
        else:
            logger.warning(f"BMC markdown is None or empty - skipping update for idea_id {idea_id}")

        if similar_ideas_markdown:
            update_data["similar_ideas"] = similar_ideas_markdown
            logger.info(
                f"Similar ideas generated successfully (length: {len(similar_ideas_markdown)})"
            )
        else:
            logger.warning(
                f"Similar ideas markdown is None or empty - skipping update for idea_id {idea_id}"
            )

        if pitch_deck:
            update_data["pitch_deck"] = pitch_deck
            logger.info(f"Pitch deck added to update_data (length: {len(pitch_deck)})")

        if prd:
            update_data["product_requirements_document"] = prd
            logger.info(f"PRD added to update_data (length: {len(prd)})")

        if patent_draft:
            update_data["provisional_patent"] = patent_draft
            logger.info(f"Patent draft added to update_data (length: {len(patent_draft)})")

        logger.info(f"Upserting database with generated documents for idea_id {idea_id}")
        if len(update_data) > 2:  # Only upsert if we have more than just idea_id and user_id
            try:
                _update_idea_documents(idea_id, update_data)
                logger.info(f"Successfully updated idea {idea_id} with generated documents")
            except Exception as e:
                logger.error(f"Error updating idea {idea_id}: {e}")
        else:
            logger.warning(f"No documents to update for idea_id {idea_id}")

        # Upsert pitch deck into pitch_decks table (with user_id)
        if pitch_deck and user_id:
            try:
                _upsert_generated_document("pitch_decks", idea_id, user_id, pitch_deck)
            except Exception as e:
                logger.error(f"Error upserting pitch deck for idea_id {idea_id}: {e}")

        # Upsert product requirements document into product_requirements_documents table (with user_id)
        if prd and user_id:
            try:
                _upsert_generated_document("product_requirements_documents", idea_id, user_id, prd)
            except Exception as e:
                logger.error(f"Error upserting PRD for idea_id {idea_id}: {e}")

        logger.info("Asynchronous BMC and similar ideas update complete.")
        if sio and loop:
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(sio.emit("similar_ideas_ready", {"idea_id": idea_id}))
            )

        # Emit result to the client if sio, sid, and loop are provided
        if sio and sid and loop:
            coro = sio.emit(
                "similar_ideas_result",
                {"idea_id": idea_id, "similarIdeas": similar_ideas_markdown},
                to=sid,
            )
            asyncio.run_coroutine_threadsafe(coro, loop)
    except Exception as e:
        logger.error(f"Background generation failed: {e}")
        # Optionally emit error to client
        if sio and sid and loop:
            coro = sio.emit("similar_ideas_result", {"idea_id": idea_id, "error": str(e)}, to=sid)
            asyncio.run_coroutine_threadsafe(coro, loop)


def store_pdf_file(local_path, storage_bucket, storage_path):
    """Persist a generated PDF to the local web-served directory (fallback for local dev)."""
    source = Path(local_path)
    if not source.exists():
        raise FileNotFoundError(f"Generated PDF not found at {local_path}")

    destination = GENERATED_PDF_ROOT / storage_bucket / storage_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    logger.info(f"Stored generated PDF at {destination}")
    return f"/generated/pdfs/{storage_bucket}/{storage_path}"


def _supabase_storage_url() -> str:
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/")


def _supabase_api_key() -> str:
    return (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or "").strip()


def _supabase_configured() -> bool:
    return bool(_supabase_storage_url() and _supabase_api_key())


def upload_bytes_to_supabase(
    payload: bytes, bucket: str, storage_path: str, content_type: str
) -> str:
    """Upload bytes to a public Supabase Storage bucket and return the public URL."""
    if _requests is None:
        raise RuntimeError("requests library is not available for Supabase upload")

    base_url = _supabase_storage_url()
    api_key = _supabase_api_key()
    auth_headers = {"apikey": api_key, "Authorization": f"Bearer {api_key}"}

    # Ensure bucket exists, create as public if missing.
    bucket_check = _requests.get(
        f"{base_url}/storage/v1/bucket/{quote(bucket, safe='')}",
        headers=auth_headers,
        timeout=20,
    )
    if bucket_check.status_code != 200:
        create = _requests.post(
            f"{base_url}/storage/v1/bucket",
            headers={**auth_headers, "Content-Type": "application/json"},
            json={"id": bucket, "name": bucket, "public": True},
            timeout=20,
        )
        if create.status_code not in {200, 201, 409}:
            create.raise_for_status()

    object_url = (
        f"{base_url}/storage/v1/object/{quote(bucket, safe='')}/{quote(storage_path, safe='/')}"
    )
    resp = _requests.post(
        object_url,
        headers={**auth_headers, "Content-Type": content_type, "x-upsert": "true"},
        data=payload,
        timeout=120,
    )
    if resp.status_code not in {200, 201}:
        resp.raise_for_status()

    return (
        f"{base_url}/storage/v1/object/public"
        f"/{quote(bucket, safe='')}/{quote(storage_path, safe='/')}"
    )


def _upload_pdf_to_supabase(local_path: str, bucket: str, storage_path: str) -> str:
    """Upload a PDF to Supabase Storage and return the public URL."""
    source = Path(local_path)
    if not source.exists():
        raise FileNotFoundError(f"Generated PDF not found at {local_path}")
    return upload_bytes_to_supabase(source.read_bytes(), bucket, storage_path, "application/pdf")


def upload_pdf_to_supabase_storage(local_path: str, storage_bucket: str, storage_path: str) -> str:
    """Upload a PDF to Supabase Storage when configured, otherwise store it locally."""
    if _supabase_configured():
        return _upload_pdf_to_supabase(local_path, storage_bucket, storage_path)
    return store_pdf_file(local_path, storage_bucket, storage_path)


def generate_patent_pdfs(idea_id: str, user_id: str, patent_draft: str, owner_profile=None):
    """
    Generate specification and coversheet PDFs from a patent draft text, upload them to
    Supabase Storage (or local fallback), persist URLs to the intellectual_properties table,
    and return (spec_pdf_url, coversheet_pdf_url).  Either value may be None on failure.
    """
    from app.services.documents.patent_pdf import (
        fill_coversheet_with_pypdf,
        generate_specification_pdf,
    )

    title = _extract_markdown_section("Title", patent_draft)
    abstract = _extract_markdown_section("Abstract", patent_draft)
    description = _extract_markdown_section("Description", patent_draft)
    claims = _extract_markdown_section("Claims", patent_draft)
    drawings = _extract_markdown_section("Suggested Drawings", patent_draft)

    if not (title and abstract and description and claims):
        logger.warning(f"[Patent] Skipping PDF generation for idea_id {idea_id}: missing sections")
        return None, None

    import uuid as _uuid

    ip_id = str(_uuid.uuid4())
    storage_bucket = "patents"
    spec_pdf_url = None
    coversheet_pdf_url = None

    spec_pdf_path = f"/tmp/specification_{idea_id}.pdf"
    try:
        generate_specification_pdf(spec_pdf_path, title, abstract, description, claims, drawings)
        spec_pdf_url = upload_pdf_to_supabase_storage(
            spec_pdf_path, storage_bucket, f"{ip_id}/specification.pdf"
        )
        logger.info(f"[Patent] Stored specification PDF at {spec_pdf_url}")
    except Exception as exc:
        logger.error(f"[Patent] Error generating/storing specification PDF: {exc}")

    coversheet_pdf_path = f"/tmp/coversheet_{idea_id}.pdf"
    try:
        if owner_profile is None:
            owner_profile = _get_idea_owner_profile(idea_id)
        field_data = _build_patent_coversheet_field_data(title, owner_profile)
        fill_coversheet_with_pypdf(str(USPTO_COVERSHEET_TEMPLATE), coversheet_pdf_path, field_data)
        coversheet_pdf_url = upload_pdf_to_supabase_storage(
            coversheet_pdf_path, storage_bucket, f"{ip_id}/coversheet.pdf"
        )
        logger.info(f"[Patent] Stored coversheet PDF at {coversheet_pdf_url}")
    except Exception as exc:
        logger.error(f"[Patent] Error generating/storing coversheet PDF: {exc}")

    if (spec_pdf_url or coversheet_pdf_url) and user_id:
        try:
            _upsert_patent_pdfs(idea_id, user_id, title, spec_pdf_url, coversheet_pdf_url)
            logger.info(
                f"[Patent] Saved patent PDFs to intellectual_properties for idea_id {idea_id}"
            )
        except Exception as exc:
            logger.error(f"[Patent] Error upserting patent PDFs: {exc}")

    return spec_pdf_url, coversheet_pdf_url
