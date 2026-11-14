"""Tests for document generation and retrieval via GraphQL resolvers and background tasks."""

import pytest
from unittest.mock import MagicMock, Mock, patch, AsyncMock
from app.services.ideas.document_generation import generate_background_tasks


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
    return "\n".join([
        "# Title", "Test Invention",
        "# Abstract", "Abstract text",
        "# Description", "Description text",
        "# Claims", "Claim text",
        "# Suggested Drawings", "Drawing text",
    ])


class TestBackgroundTaskGeneration:

    def test_skips_when_no_description(self):
        with patch("app.services.ideas.document_generation.logger.info") as mock_log:
            generate_background_tasks(None, "idea-1")
            mock_log.assert_called_with(
                "No description provided for idea_id idea-1. Skipping background generation."
            )

    def test_skips_when_empty_description(self):
        with patch("app.services.ideas.document_generation.logger.info") as mock_log:
            generate_background_tasks("", "idea-1")
            mock_log.assert_called_with(
                "No description provided for idea_id idea-1. Skipping background generation."
            )

    def test_handles_manifest_manager_error(self):
        db_cm, conn, cursor = _mock_db_connection()

        with patch("app.managers.manifest_manager.manifest_manager") as mock_manager, \
             patch("app.services.ideas.document_generation.logger.error") as mock_error, \
             patch("app.services.ideas.document_generation.get_db_connection", return_value=db_cm), \
             patch("app.services.documents.patent_pdf.generate_specification_pdf"), \
             patch("app.services.documents.patent_pdf.fill_coversheet_with_pypdf"), \
             patch("app.services.documents.provisional_patent.ProvisionalPatent") as mock_patent_cls, \
             patch("app.services.ideas.document_generation.upload_pdf_to_supabase_storage", return_value=None):
            mock_manager.update.side_effect = Exception("AI service down")
            mock_manager.get_similar_ideas.return_value = None
            mock_manager.bmc.summary = None
            mock_manager.generate_pitch_deck.return_value = None
            mock_manager.generate_product_requirements_document.return_value = None

            mock_patent = Mock()
            mock_patent.generate.return_value = _patent_markdown()
            mock_patent_cls.return_value = mock_patent

            generate_background_tasks("test description", "idea-1")
            mock_error.assert_any_call("Error during manifest_manager.update(): AI service down")
            assert cursor.execute.called
            conn.commit.assert_called()

    def test_generates_all_documents(self):
        db_cm, conn, cursor = _mock_db_connection()

        with patch("app.managers.manifest_manager.manifest_manager") as mock_manager, \
             patch("app.services.ideas.document_generation.get_db_connection", return_value=db_cm), \
             patch("app.services.documents.patent_pdf.generate_specification_pdf"), \
             patch("app.services.documents.patent_pdf.fill_coversheet_with_pypdf"), \
             patch("app.services.documents.provisional_patent.ProvisionalPatent") as mock_patent_cls, \
             patch("app.services.ideas.document_generation.upload_pdf_to_supabase_storage", return_value=None):

            mock_manager.get_similar_ideas.return_value = "## Similar Ideas\n- Idea A\n- Idea B"
            mock_manager.bmc.summary = "## Key Partners\nPartner A\n## Value Propositions\nValue B"
            mock_manager.generate_pitch_deck.return_value = "## Slide 1\nIntro content"
            mock_manager.generate_product_requirements_document.return_value = "## Overview\nPRD content"

            mock_patent = Mock()
            mock_patent.generate.return_value = _patent_markdown()
            mock_patent_cls.return_value = mock_patent

            generate_background_tasks("A platform for connecting mentors with students", "idea-1")

        mock_manager.set_idea.assert_called()
        mock_manager.update.assert_called_once()
        mock_manager.generate_pitch_deck.assert_called_once()
        mock_manager.generate_product_requirements_document.assert_called_once()
        assert cursor.execute.called
        conn.commit.assert_called()

    def test_bmc_generation_stored_in_db(self):
        db_cm, conn, cursor = _mock_db_connection()

        with patch("app.managers.manifest_manager.manifest_manager") as mock_manager, \
             patch("app.services.ideas.document_generation.get_db_connection", return_value=db_cm), \
             patch("app.services.documents.patent_pdf.generate_specification_pdf"), \
             patch("app.services.documents.patent_pdf.fill_coversheet_with_pypdf"), \
             patch("app.services.documents.provisional_patent.ProvisionalPatent") as mock_patent_cls, \
             patch("app.services.ideas.document_generation.upload_pdf_to_supabase_storage", return_value=None):

            bmc_content = "## Key Partners\n- AWS\n## Key Activities\n- Development"
            mock_manager.get_similar_ideas.return_value = "similar"
            mock_manager.bmc.summary = bmc_content
            mock_manager.generate_pitch_deck.return_value = "pitch"
            mock_manager.generate_product_requirements_document.return_value = "prd"

            mock_patent = Mock()
            mock_patent.generate.return_value = _patent_markdown()
            mock_patent_cls.return_value = mock_patent

            generate_background_tasks("test idea", "idea-1")

        calls = cursor.execute.call_args_list
        sql_calls = [str(c) for c in calls]
        sql_joined = " ".join(sql_calls)
        assert "business_model_canvas" in sql_joined

    def test_pitch_deck_generation_stored_in_db(self):
        db_cm, conn, cursor = _mock_db_connection()

        with patch("app.managers.manifest_manager.manifest_manager") as mock_manager, \
             patch("app.services.ideas.document_generation.get_db_connection", return_value=db_cm), \
             patch("app.services.documents.patent_pdf.generate_specification_pdf"), \
             patch("app.services.documents.patent_pdf.fill_coversheet_with_pypdf"), \
             patch("app.services.documents.provisional_patent.ProvisionalPatent") as mock_patent_cls, \
             patch("app.services.ideas.document_generation.upload_pdf_to_supabase_storage", return_value=None):

            mock_manager.get_similar_ideas.return_value = "similar"
            mock_manager.bmc.summary = "bmc"
            mock_manager.generate_pitch_deck.return_value = "## Pitch Deck\nContent here"
            mock_manager.generate_product_requirements_document.return_value = "prd"

            mock_patent = Mock()
            mock_patent.generate.return_value = _patent_markdown()
            mock_patent_cls.return_value = mock_patent

            generate_background_tasks("test idea", "idea-1")

        calls = cursor.execute.call_args_list
        sql_calls = [str(c) for c in calls]
        sql_joined = " ".join(sql_calls)
        assert "pitch_deck" in sql_joined

    def test_prd_generation_stored_in_db(self):
        db_cm, conn, cursor = _mock_db_connection()

        with patch("app.managers.manifest_manager.manifest_manager") as mock_manager, \
             patch("app.services.ideas.document_generation.get_db_connection", return_value=db_cm), \
             patch("app.services.documents.patent_pdf.generate_specification_pdf"), \
             patch("app.services.documents.patent_pdf.fill_coversheet_with_pypdf"), \
             patch("app.services.documents.provisional_patent.ProvisionalPatent") as mock_patent_cls, \
             patch("app.services.ideas.document_generation.upload_pdf_to_supabase_storage", return_value=None):

            mock_manager.get_similar_ideas.return_value = "similar"
            mock_manager.bmc.summary = "bmc"
            mock_manager.generate_pitch_deck.return_value = "pitch"
            mock_manager.generate_product_requirements_document.return_value = "## PRD\nRequirements here"

            mock_patent = Mock()
            mock_patent.generate.return_value = _patent_markdown()
            mock_patent_cls.return_value = mock_patent

            generate_background_tasks("test idea", "idea-1")

        calls = cursor.execute.call_args_list
        sql_calls = [str(c) for c in calls]
        sql_joined = " ".join(sql_calls)
        assert "product_requirements_document" in sql_joined

    def test_patent_generation_stored_in_db(self):
        db_cm, conn, cursor = _mock_db_connection()

        with patch("app.managers.manifest_manager.manifest_manager") as mock_manager, \
             patch("app.services.ideas.document_generation.get_db_connection", return_value=db_cm), \
             patch("app.services.documents.patent_pdf.generate_specification_pdf"), \
             patch("app.services.documents.patent_pdf.fill_coversheet_with_pypdf"), \
             patch("app.services.documents.provisional_patent.ProvisionalPatent") as mock_patent_cls, \
             patch("app.services.ideas.document_generation.upload_pdf_to_supabase_storage", return_value=None):

            mock_manager.get_similar_ideas.return_value = "similar"
            mock_manager.bmc.summary = "bmc"
            mock_manager.generate_pitch_deck.return_value = "pitch"
            mock_manager.generate_product_requirements_document.return_value = "prd"

            mock_patent = Mock()
            mock_patent.generate.return_value = _patent_markdown()
            mock_patent_cls.return_value = mock_patent

            generate_background_tasks("test idea", "idea-1")

        calls = cursor.execute.call_args_list
        sql_calls = [str(c) for c in calls]
        sql_joined = " ".join(sql_calls)
        assert "provisional_patent" in sql_joined

    def test_patent_pdf_generation_receives_parsed_sections(self):
        db_cm, conn, cursor = _mock_db_connection()

        with patch("app.managers.manifest_manager.manifest_manager") as mock_manager, \
             patch("app.services.ideas.document_generation.get_db_connection", return_value=db_cm), \
             patch("app.services.documents.patent_pdf.generate_specification_pdf") as mock_generate_specification_pdf, \
             patch("app.services.documents.patent_pdf.fill_coversheet_with_pypdf"), \
             patch("app.services.documents.provisional_patent.ProvisionalPatent") as mock_patent_cls, \
             patch("app.services.ideas.document_generation.upload_pdf_to_supabase_storage", return_value=None):

            mock_manager.ai_layer.is_available.return_value = True
            mock_manager.get_similar_ideas.return_value = "similar"
            mock_manager.bmc.summary = "bmc"
            mock_manager.generate_pitch_deck.return_value = "pitch"
            mock_manager.generate_product_requirements_document.return_value = "prd"

            mock_patent = Mock()
            mock_patent.generate.return_value = _patent_markdown()
            mock_patent_cls.return_value = mock_patent

            generate_background_tasks("test idea", "idea-1")

        args = mock_generate_specification_pdf.call_args.args
        assert args[1] == "Test Invention"
        assert args[2] == "Abstract text"
        assert args[3] == "Description text"
        assert args[4] == "Claim text"

    def test_patent_coversheet_prefills_known_owner_profile(self):
        db_cm, conn, cursor = _mock_db_connection()
        cursor.fetchone.side_effect = [{
            "user_id": "test-user",
            "email": "ada@example.com",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "username": "adal",
            "address": "123 Innovation Way, San Francisco, CA 94105, USA",
            "state": "CA",
            "country": "USA",
        }]

        with patch("app.managers.manifest_manager.manifest_manager") as mock_manager, \
             patch("app.services.ideas.document_generation.get_db_connection", return_value=db_cm), \
             patch("app.services.documents.patent_pdf.generate_specification_pdf"), \
             patch("app.services.documents.patent_pdf.fill_coversheet_with_pypdf") as mock_fill_coversheet, \
             patch("app.services.documents.provisional_patent.ProvisionalPatent") as mock_patent_cls, \
             patch("app.services.ideas.document_generation.upload_pdf_to_supabase_storage", return_value=None):

            mock_manager.ai_layer.is_available.return_value = True
            mock_manager.get_similar_ideas.return_value = "similar"
            mock_manager.bmc.summary = "bmc"
            mock_manager.generate_pitch_deck.return_value = "pitch"
            mock_manager.generate_product_requirements_document.return_value = "prd"

            mock_patent = Mock()
            mock_patent.generate.return_value = _patent_markdown()
            mock_patent_cls.return_value = mock_patent

            generate_background_tasks("test idea", "idea-1")

        field_data = mock_fill_coversheet.call_args.args[2]
        assert field_data["given_name"] == "Ada"
        assert field_data["family_name"] == "Lovelace"
        assert field_data["first_named_inventor"] == ""
        assert field_data["name_of_applicant"] == "Ada Lovelace"
        assert field_data["correspondence_address"] == "123 Innovation Way"
        assert field_data["city"] == "San Francisco"
        assert field_data["state"] == "CA"
        assert field_data["zip_code"] == "94105"
        assert field_data["country"] == "USA"
        assert field_data["email"] == "ada@example.com"
        assert field_data["signature"] == "Ada Lovelace"
        assert "Complete before filing" not in field_data.values()
        assert "Applicant information required" not in field_data.values()

    def test_similar_ideas_stored_in_db(self):
        db_cm, conn, cursor = _mock_db_connection()

        with patch("app.managers.manifest_manager.manifest_manager") as mock_manager, \
             patch("app.services.ideas.document_generation.get_db_connection", return_value=db_cm), \
             patch("app.services.documents.patent_pdf.generate_specification_pdf"), \
             patch("app.services.documents.patent_pdf.fill_coversheet_with_pypdf"), \
             patch("app.services.documents.provisional_patent.ProvisionalPatent") as mock_patent_cls, \
             patch("app.services.ideas.document_generation.upload_pdf_to_supabase_storage", return_value=None):

            similar_content = "## Similar Ideas\n- Competitor A\n- Competitor B"
            mock_manager.get_similar_ideas.return_value = similar_content
            mock_manager.bmc.summary = "bmc"
            mock_manager.generate_pitch_deck.return_value = "pitch"
            mock_manager.generate_product_requirements_document.return_value = "prd"

            mock_patent = Mock()
            mock_patent.generate.return_value = _patent_markdown()
            mock_patent_cls.return_value = mock_patent

            generate_background_tasks("test idea", "idea-1")

        calls = cursor.execute.call_args_list
        sql_calls = [str(c) for c in calls]
        sql_joined = " ".join(sql_calls)
        assert "similar_ideas" in sql_joined


class TestSimilarIdeasService:

    def test_update_with_valid_idea(self):
        from app.services.ideas.similar_ideas import SimilarIdeas
        mock_model = MagicMock()
        mock_model.idea.description = "A test startup idea"
        mock_model.ai_layer.perform_web_search_json.return_value = {
            "data": {
                "comparables": [
                    {
                        "title": "Idea A",
                        "url": "https://example.com",
                        "summary": "Example summary.",
                        "why_similar": "Example reason.",
                        "signal": "Example signal.",
                    }
                ],
                "research_topics": [],
            }
        }

        service = SimilarIdeas(mock_model)
        service.update()

        mock_model.ai_layer.perform_web_search_json.assert_called_once()
        assert "## Comparable Companies" in service.results
        assert "Idea A" in service.results

    def test_update_with_no_description(self):
        from app.services.ideas.similar_ideas import SimilarIdeas
        mock_model = MagicMock()
        mock_model.idea.description = None

        service = SimilarIdeas(mock_model)
        service.update()

        mock_model.ai_layer.perform_web_search_json.assert_not_called()

    def test_find_returns_grounded_markdown(self):
        from app.services.ideas.similar_ideas import SimilarIdeas
        mock_model = MagicMock()
        mock_model.ai_layer.perform_web_search_json.return_value = {
            "data": {
                "comparables": [
                    {
                        "title": "Figma",
                        "url": "https://www.figma.com/",
                        "summary": "Collaborative design platform.",
                        "why_similar": "Shared workspace for product teams.",
                        "signal": "Strong product-led adoption.",
                    }
                ],
                "research_topics": [
                    {
                        "title": "Collaboration workflow lock-in",
                        "sources": [
                            {
                                "title": "Gartner",
                                "url": "https://www.gartner.com/en",
                                "publisher": "Gartner",
                            }
                        ],
                        "why_it_matters": "Retention improves when teams centralize workflow.",
                        "what_to_validate": "Which artifact becomes the durable system of record.",
                    }
                ],
            }
        }

        service = SimilarIdeas(mock_model)
        result = service.find("test idea description")

        assert "Figma" in result
        assert "[Gartner](https://www.gartner.com/en)" in result
        assert service.results == result

    def test_find_falls_back_to_markdown_generation_when_search_fails(self):
        from app.services.ideas.similar_ideas import SimilarIdeas
        mock_model = MagicMock()
        mock_model.ai_layer.perform_web_search_json.side_effect = Exception("Search timeout")
        mock_model.ai_layer.generate_rich_text.return_value = "# Similar Landscape"

        service = SimilarIdeas(mock_model)
        result = service.find("test idea")

        assert result == "# Similar Landscape"

    def test_find_handles_ai_error(self):
        from app.services.ideas.similar_ideas import SimilarIdeas
        mock_model = MagicMock()
        mock_model.ai_layer.perform_web_search_json.side_effect = Exception("Search timeout")
        mock_model.ai_layer.generate_rich_text.side_effect = Exception("API timeout")

        service = SimilarIdeas(mock_model)
        result = service.find("test idea")

        assert result == ""

    def test_find_without_ai_layer(self):
        from app.services.ideas.similar_ideas import SimilarIdeas
        service = SimilarIdeas(None)
        result = service.find("test idea")
        assert result == ""


class TestManifestManagerDocuments:

    def test_set_idea_and_update(self):
        from app.managers.manifest_manager import ManifestManager
        with patch("app.managers.manifest_manager.AILayer"), \
             patch("app.managers.manifest_manager.Idea"):
            manager = ManifestManager()
            manager.set_idea("A new social network for pets")
            assert manager.idea.description == "A new social network for pets"

    def test_get_similar_ideas_returns_results(self):
        from app.managers.manifest_manager import ManifestManager
        with patch("app.managers.manifest_manager.AILayer"), \
             patch("app.managers.manifest_manager.Idea"):
            manager = ManifestManager()
            manager.similar_ideas.results = "## Similar\n- Pet Connect"
            assert manager.get_similar_ideas() == "## Similar\n- Pet Connect"

    def test_similar_ideas_property(self):
        from app.managers.manifest_manager import ManifestManager
        with patch("app.managers.manifest_manager.AILayer"), \
             patch("app.managers.manifest_manager.Idea"):
            manager = ManifestManager()
            assert manager.similar_ideas is not None
            assert hasattr(manager.similar_ideas, 'update')
            assert hasattr(manager.similar_ideas, 'find')
