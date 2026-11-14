import os
from unittest.mock import MagicMock, patch

from app.services.documents.patent_pdf import (
    DEFAULT_COVERSHEET_OVERLAY_MAP,
    _fit_coversheet_lines,
    fill_coversheet_with_pypdf,
    generate_specification_pdf,
)


def test_generate_specification_pdf(tmpdir):
    """Test the generation of a specification PDF."""
    output_path = os.path.join(str(tmpdir), "spec.pdf")
    generate_specification_pdf(
        output_path,
        title="Test Title",
        abstract="Test Abstract",
        description="Test Description",
        claims="Test Claims",
        drawings="Test Drawings",
    )
    assert os.path.exists(output_path)
    # Ideally, we would also check the content of the PDF here,
    # but for now, we'll just check that it was created.


@patch("app.services.documents.patent_pdf.PdfReader")
@patch("app.services.documents.patent_pdf.PdfWriter")
def test_fill_coversheet_with_pypdf(mock_writer, mock_reader, tmpdir):
    """Test filling a coversheet PDF."""
    original_pages = [MagicMock(), MagicMock(), MagicMock()]
    overlay_pages = [MagicMock(), MagicMock(), MagicMock()]
    mock_reader.side_effect = [
        MagicMock(pages=original_pages),
        MagicMock(pages=overlay_pages),
    ]

    output_path = os.path.join(str(tmpdir), "coversheet.pdf")
    template_path = "dummy_template.pdf"  # This won't be read due to mocking

    field_data = {
        "first_named_inventor": "John Doe",
        "signature": "John Doe",
    }

    fill_coversheet_with_pypdf(template_path, output_path, field_data)

    mock_writer.return_value.write.assert_called_once()
    assert original_pages[0].merge_page.called
    assert original_pages[1].merge_page.called
    assert original_pages[2].merge_page.called
    assert mock_writer.return_value.add_page.call_count == 3


def test_fit_coversheet_lines_strips_markdown_and_wraps_title():
    lines, font_size = _fit_coversheet_lines(
        "**AquaChain** [Patent Title](https://example.com) Blockchain-Based System for Monitoring Water Quality",
        DEFAULT_COVERSHEET_OVERLAY_MAP["title_of_invention"],
    )

    assert 1 <= len(lines) <= 3
    assert font_size <= DEFAULT_COVERSHEET_OVERLAY_MAP["title_of_invention"]["font_size"]
    assert all("**" not in line for line in lines)
    assert all("[" not in line for line in lines)
    assert any("AquaChain" in line for line in lines)


def test_specification_preserves_content_and_separates_optional_claims_and_abstract(tmp_path):
    from pypdf import PdfReader

    output = tmp_path / "specification.pdf"
    generate_specification_pdf(
        str(output),
        "Sample sensor",
        "A sensor measures water quality.",
        "## Detailed Description\n[0001] A sensor measures a sample.",
        "1. A sensor comprising a probe.",
        "FIG. 1: Sensor assembly to be prepared.",
    )
    pages = [page.extract_text() for page in PdfReader(output).pages]
    assert "[0001]" in pages[0]
    assert "FIG. 1" in "\n".join(pages)
    assert "OPTIONAL DRAFT CLAIMS" in pages[-2]
    assert "1. A sensor" in pages[-2]
    assert "ABSTRACT" in pages[-1]
    assert "A sensor measures water quality." in pages[-1]
    assert "Official provisional application cover sheet" not in "\n".join(pages)
