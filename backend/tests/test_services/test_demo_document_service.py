from app.services.demo_document_service import build_demo_documents


def test_build_demo_documents_returns_expected_sections():
    documents = build_demo_documents(
        "An AI platform that helps first-time founders turn startup ideas into execution-ready plans and investor materials."
    )

    assert "# Similar Landscape" in documents.similar_ideas
    assert "# Key Partners" in documents.business_model_canvas
    assert "# Revenue Streams" in documents.business_model_canvas
    assert "# Slide 1: Company Purpose" in documents.pitch_deck
    assert "# Product Requirements Document" in documents.product_requirements_document
    assert "# Title" in documents.provisional_patent
    assert "# Claims" in documents.provisional_patent


def test_build_demo_documents_reflects_input_domain():
    documents = build_demo_documents(
        "A marketplace that connects students with vetted mentors for career coaching, accountability, and structured learning plans."
    )

    assert "students, mentors, and academic programs" in documents.business_model_canvas
    assert "marketplace" in documents.provisional_patent.lower() or "mentor" in documents.provisional_patent.lower()
    assert "students" in documents.pitch_deck.lower()
