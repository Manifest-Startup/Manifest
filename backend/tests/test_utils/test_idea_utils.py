import json
from unittest.mock import MagicMock, Mock, patch

from app.db.database import InMemoryDatabaseClient
from app.services.documents.demo_documents import DemoDocumentBundle
from app.services.ideas.document_generation import (
    GENERATED_PDF_ROOT,
    USPTO_COVERSHEET_TEMPLATE,
    generate_background_tasks,
    generate_patent_pdfs,
    store_pdf_file,
    upload_pdf_to_supabase_storage,
)


def _mock_db_connection():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = {"user_id": "test-user"}

    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = False

    cm = MagicMock()
    cm.__enter__.return_value = conn
    cm.__exit__.return_value = False
    return cm, conn, cursor


def _patent_markdown():
    return "\n".join(
        [
            "# Title",
            "Test Invention",
            "# Abstract",
            "Abstract text",
            "# Description",
            "Description text",
            "# Claims",
            "Claim text",
            "# Suggested Drawings",
            "Drawing text",
        ]
    )


def test_generate_background_tasks_no_description():
    with patch("app.services.ideas.document_generation.logger.info") as mock_log:
        generate_background_tasks(None, "idea-1")
        mock_log.assert_called_with("No description provided for idea_id idea-1. Skipping background generation.")


def test_generate_background_tasks_error_handling():
    db_cm, conn, cursor = _mock_db_connection()

    with patch("app.managers.manifest_manager.manifest_manager") as mock_manager, \
         patch("app.services.ideas.document_generation.logger.error") as mock_error, \
         patch("app.services.ideas.document_generation.get_db_connection", return_value=db_cm), \
         patch("app.services.documents.patent_pdf.generate_specification_pdf"), \
         patch("app.services.documents.patent_pdf.fill_coversheet_with_pypdf"), \
         patch("app.services.documents.provisional_patent.ProvisionalPatent") as mock_patent_cls, \
         patch("app.services.ideas.document_generation.upload_pdf_to_supabase_storage", return_value=None):
        mock_manager.update.side_effect = Exception("Test exception")
        mock_manager.get_similar_ideas.return_value = None
        mock_manager.bmc.summary = None
        mock_manager.generate_pitch_deck.return_value = None
        mock_manager.generate_product_requirements_document.return_value = None

        mock_patent = Mock()
        mock_patent.generate.return_value = _patent_markdown()
        mock_patent_cls.return_value = mock_patent

        generate_background_tasks("test description", "idea-1")

        mock_error.assert_any_call("Error during manifest_manager.update(): Test exception")
        assert cursor.execute.called
        conn.commit.assert_called()


def test_generate_background_tasks_success():
    db_cm, conn, cursor = _mock_db_connection()

    with patch("app.managers.manifest_manager.manifest_manager") as mock_manager, \
         patch("app.services.ideas.document_generation.get_db_connection", return_value=db_cm), \
         patch("app.services.documents.patent_pdf.generate_specification_pdf"), \
         patch("app.services.documents.patent_pdf.fill_coversheet_with_pypdf"), \
         patch("app.services.documents.provisional_patent.ProvisionalPatent") as mock_patent_cls, \
         patch("app.services.ideas.document_generation.upload_pdf_to_supabase_storage", return_value=None):
        mock_manager.get_similar_ideas.return_value = "similar ideas markdown"
        mock_manager.bmc.summary = "bmc markdown"
        mock_manager.generate_pitch_deck.return_value = "pitch deck"
        mock_manager.generate_product_requirements_document.return_value = "prd"

        mock_patent = Mock()
        mock_patent.generate.return_value = _patent_markdown()
        mock_patent_cls.return_value = mock_patent

        generate_background_tasks("test description", "idea-1")

    mock_manager.set_idea.assert_called()
    mock_manager.update.assert_called_once()
    assert cursor.execute.called
    conn.commit.assert_called()


def test_generate_background_tasks_uses_demo_documents_when_ai_unavailable():
    db_cm, conn, cursor = _mock_db_connection()
    demo_documents = DemoDocumentBundle(
        similar_ideas="# Similar Ideas\n- Workflow software",
        business_model_canvas="# Key Partners\n- Design partners",
        pitch_deck="# Slide 1: Opportunity\n- Demo pitch",
        product_requirements_document="# Product Requirements Document\n- Demo PRD",
        provisional_patent="# Title\nDemo invention\n# Abstract\nDemo abstract\n# Description\nDemo description\n# Claims\nDemo claims\n# Suggested Drawings\nDemo drawings",
    )

    with patch("app.managers.manifest_manager.manifest_manager") as mock_manager, \
         patch("app.services.ideas.document_generation.build_demo_documents", return_value=demo_documents), \
         patch("app.services.ideas.document_generation.get_db_connection", return_value=db_cm):
        mock_manager.ai_layer.is_available.return_value = False

        generate_background_tasks("test description", "idea-1")

    mock_manager.update.assert_not_called()
    mock_manager.generate_pitch_deck.assert_not_called()
    mock_manager.generate_product_requirements_document.assert_not_called()
    assert cursor.execute.called
    conn.commit.assert_called()


def test_generate_background_tasks_persists_to_in_memory_database_when_sql_is_unavailable():
    demo_documents = DemoDocumentBundle(
        similar_ideas="# Similar Ideas\n- Workflow software",
        business_model_canvas="# Key Partners\n- Design partners",
        pitch_deck="# Slide 1: Opportunity\n- Demo pitch",
        product_requirements_document="# Product Requirements Document\n- Demo PRD",
        provisional_patent="# Title\nDemo invention\n# Abstract\nDemo abstract\n# Description\nDemo description\n# Claims\nDemo claims\n# Suggested Drawings\nDemo drawings",
    )
    db_client = InMemoryDatabaseClient()
    db_client.table("ideas").insert(
        {
            "idea_id": "idea-1",
            "title": "Test idea",
            "description": "test description",
            "user_id": "test-user",
            "created_at": "2026-03-06T00:00:00",
        }
    ).execute()

    with patch("app.managers.manifest_manager.manifest_manager") as mock_manager, \
         patch("app.services.ideas.document_generation.build_demo_documents", return_value=demo_documents), \
         patch("app.services.ideas.document_generation.create_database_client", return_value=db_client), \
         patch("app.services.ideas.document_generation.get_db_connection", side_effect=RuntimeError("DATABASE_URL environment variable is not set")):
        mock_manager.ai_layer.is_available.return_value = False

        generate_background_tasks("test description", "idea-1")

    updated = db_client.table("ideas").select("*").eq("idea_id", "idea-1").single().execute().data
    assert updated["business_model_canvas"] == demo_documents.business_model_canvas
    assert updated["pitch_deck"] == demo_documents.pitch_deck
    assert updated["product_requirements_document"] == demo_documents.product_requirements_document
    assert updated["provisional_patent"] == demo_documents.provisional_patent


def test_upload_pdf_to_supabase_storage_falls_back_to_local_when_unconfigured():
    with patch("app.services.ideas.document_generation._supabase_configured", return_value=False), \
         patch("app.services.ideas.document_generation.store_pdf_file", return_value="/generated/pdfs/patents/path/file.pdf") as store_mock:
        url = upload_pdf_to_supabase_storage("/tmp/test.pdf", "patents", "path/file.pdf")

    assert url == "/generated/pdfs/patents/path/file.pdf"
    store_mock.assert_called_once_with("/tmp/test.pdf", "patents", "path/file.pdf")


def test_upload_pdf_to_supabase_storage_uploads_when_configured(tmp_path):
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 test")

    with patch("app.services.ideas.document_generation._supabase_configured", return_value=True), \
         patch("app.services.ideas.document_generation._upload_pdf_to_supabase", return_value="https://supabase.example.com/storage/v1/object/public/patents/path/file.pdf") as supabase_mock:
        url = upload_pdf_to_supabase_storage(str(pdf_file), "patents", "path/file.pdf")

    assert url == "https://supabase.example.com/storage/v1/object/public/patents/path/file.pdf"
    supabase_mock.assert_called_once_with(str(pdf_file), "patents", "path/file.pdf")


def test_uspto_coversheet_template_path_exists():
    assert USPTO_COVERSHEET_TEMPLATE.exists()
    assert USPTO_COVERSHEET_TEMPLATE.name == "sb0016.pdf"


def test_store_pdf_file_uses_generated_pdf_root(tmp_path, monkeypatch):
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"%PDF-1.4 sample")

    storage_root = tmp_path / "generated" / "pdfs"
    monkeypatch.setattr("app.services.ideas.document_generation.GENERATED_PDF_ROOT", storage_root)

    url = store_pdf_file(str(source), "patents", "idea-1/specification.pdf")

    expected_file = storage_root / "patents" / "idea-1" / "specification.pdf"
    assert expected_file.exists()
    assert expected_file.read_bytes() == b"%PDF-1.4 sample"
    assert url == "/generated/pdfs/patents/idea-1/specification.pdf"


def test_generate_background_tasks_persists_patent_pdf_urls_to_served_directory(tmp_path, monkeypatch):
    db_client = InMemoryDatabaseClient()
    db_client.table("ideas").insert(
        {
            "idea_id": "idea-1",
            "title": "Test idea",
            "description": "test description",
            "user_id": "test-user",
            "created_at": "2026-03-06T00:00:00",
        }
    ).execute()

    storage_root = tmp_path / "generated" / "pdfs"
    monkeypatch.setattr("app.services.ideas.document_generation.GENERATED_PDF_ROOT", storage_root)

    def _write_pdf(path, *args, **kwargs):
        with open(path, "wb") as handle:
            handle.write(b"%PDF-1.4 test")

    with patch("app.managers.manifest_manager.manifest_manager") as mock_manager, \
         patch("app.services.ideas.document_generation.create_database_client", return_value=db_client), \
         patch("app.services.ideas.document_generation.get_db_connection", side_effect=RuntimeError("DATABASE_URL environment variable is not set")), \
         patch("app.services.ideas.document_generation._supabase_configured", return_value=False), \
         patch("app.services.documents.patent_pdf.generate_specification_pdf", side_effect=_write_pdf), \
         patch("app.services.documents.patent_pdf.fill_coversheet_with_pypdf", side_effect=lambda template, output, fields: _write_pdf(output)), \
         patch("app.services.documents.provisional_patent.ProvisionalPatent") as mock_patent_cls:
        mock_manager.ai_layer.is_available.return_value = True
        mock_manager.get_similar_ideas.return_value = "similar"
        mock_manager.bmc.summary = "bmc"
        mock_manager.generate_pitch_deck.return_value = "pitch"
        mock_manager.generate_product_requirements_document.return_value = "prd"

        mock_patent = Mock()
        mock_patent.generate.return_value = _patent_markdown()
        mock_patent_cls.return_value = mock_patent

        generate_background_tasks("test description", "idea-1")

    ip_record = db_client.table("intellectual_properties").select("*").eq("idea_id", "idea-1").single().execute().data
    assert ip_record is not None

    pdf_urls = json.loads(ip_record["pdf_url"])
    assert pdf_urls["specification_pdf"].startswith("/generated/pdfs/patents/")
    assert pdf_urls["coversheet_pdf"].startswith("/generated/pdfs/patents/")

    spec_relative = pdf_urls["specification_pdf"].replace("/generated/pdfs/", "")
    cover_relative = pdf_urls["coversheet_pdf"].replace("/generated/pdfs/", "")
    assert (storage_root / spec_relative).exists()
    assert (storage_root / cover_relative).exists()


# ---------------------------------------------------------------------------
# generate_patent_pdfs helper
# ---------------------------------------------------------------------------

def test_generate_patent_pdfs_returns_none_when_sections_missing():
    spec_url, cover_url = generate_patent_pdfs("idea-1", "user-1", "No sections here")
    assert spec_url is None
    assert cover_url is None


def test_generate_patent_pdfs_uploads_and_saves_to_db(tmp_path, monkeypatch):
    db_client = InMemoryDatabaseClient()
    db_client.table("ideas").insert(
        {"idea_id": "idea-1", "title": "Test", "description": "test", "user_id": "u1", "created_at": "2026-01-01"}
    ).execute()

    storage_root = tmp_path / "generated" / "pdfs"
    monkeypatch.setattr("app.services.ideas.document_generation.GENERATED_PDF_ROOT", storage_root)

    def _write_pdf(path, *args, **kwargs):
        with open(path, "wb") as f:
            f.write(b"%PDF-1.4 test")

    patent_draft = "\n".join([
        "# Title", "Invention", "# Abstract", "Abstract text",
        "# Description", "Desc text", "# Claims", "Claim 1",
    ])

    with patch("app.services.ideas.document_generation.create_database_client", return_value=db_client), \
         patch("app.services.ideas.document_generation.get_db_connection", side_effect=RuntimeError("no db")), \
         patch("app.services.ideas.document_generation._supabase_configured", return_value=False), \
         patch("app.services.documents.patent_pdf.generate_specification_pdf", side_effect=_write_pdf), \
         patch("app.services.documents.patent_pdf.fill_coversheet_with_pypdf", side_effect=lambda t, o, f: _write_pdf(o)):
        spec_url, cover_url = generate_patent_pdfs("idea-1", "u1", patent_draft)

    assert spec_url is not None
    assert cover_url is not None
    assert spec_url.startswith("/generated/pdfs/patents/")
    assert cover_url.startswith("/generated/pdfs/patents/")

    ip_record = db_client.table("intellectual_properties").select("*").eq("idea_id", "idea-1").single().execute().data
    assert ip_record is not None
    pdf_urls = json.loads(ip_record["pdf_url"])
    assert pdf_urls["specification_pdf"] == spec_url
    assert pdf_urls["coversheet_pdf"] == cover_url


def test_generate_patent_pdfs_uploads_to_supabase_when_configured(tmp_path):
    def _write_pdf(path, *args, **kwargs):
        with open(path, "wb") as f:
            f.write(b"%PDF-1.4 test")

    patent_draft = "\n".join([
        "# Title", "Invention", "# Abstract", "Abstract text",
        "# Description", "Desc text", "# Claims", "Claim 1",
    ])

    owner_profile = {"first_name": "Test", "last_name": "Owner", "email": "owner@example.com"}

    with patch("app.services.ideas.document_generation._supabase_configured", return_value=True), \
         patch("app.services.ideas.document_generation._upload_pdf_to_supabase", return_value="https://sb.example.com/storage/v1/object/public/patents/x/spec.pdf") as mock_upload, \
         patch("app.services.ideas.document_generation._upsert_patent_pdfs") as mock_upsert, \
         patch("app.services.ideas.document_generation._get_idea_owner_profile", return_value=owner_profile), \
         patch("app.services.documents.patent_pdf.generate_specification_pdf", side_effect=_write_pdf), \
         patch("app.services.documents.patent_pdf.fill_coversheet_with_pypdf", side_effect=lambda t, o, f: _write_pdf(o)):
        spec_url, cover_url = generate_patent_pdfs("idea-1", "u1", patent_draft)

    assert spec_url == "https://sb.example.com/storage/v1/object/public/patents/x/spec.pdf"
    assert mock_upload.call_count == 2
    mock_upsert.assert_called_once()


# ---------------------------------------------------------------------------
# _upload_pdf_to_supabase (unit)
# ---------------------------------------------------------------------------

def test_upload_pdf_to_supabase_sends_file_and_returns_public_url(tmp_path):
    from app.services.ideas.document_generation import _upload_pdf_to_supabase
    import app.services.ideas.document_generation as _idea_utils_mod

    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 test")

    mock_req = MagicMock()
    bucket_resp = MagicMock()
    bucket_resp.status_code = 200
    upload_resp = MagicMock()
    upload_resp.status_code = 200
    mock_req.get.return_value = bucket_resp
    mock_req.post.return_value = upload_resp

    with patch("app.services.ideas.document_generation._supabase_storage_url", return_value="https://proj.supabase.co"), \
         patch("app.services.ideas.document_generation._supabase_api_key", return_value="service-key"), \
         patch.object(_idea_utils_mod, "_requests", mock_req):
        url = _upload_pdf_to_supabase(str(pdf_file), "patents", "uid/specification.pdf")

    assert "proj.supabase.co" in url
    assert "patents" in url
    assert "specification.pdf" in url
