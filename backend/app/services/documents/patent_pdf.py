import re
from html import escape
from io import BytesIO

from pypdf import PageObject, PdfReader, PdfWriter

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.pagesizes import letter as rl_letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.pdfgen.canvas import Canvas as rl_Canvas
    from reportlab.platypus import (
        ListFlowable,
        ListItem,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )
except Exception:
    colors = None
    rl_letter = (612, 792)
    rl_canvas = None
    rl_Canvas = None
    ParagraphStyle = None
    getSampleStyleSheet = None
    inch = 72
    ListFlowable = None
    ListItem = None
    PageBreak = None
    Paragraph = None
    SimpleDocTemplate = None
    Spacer = None
    pdfmetrics = None


DEFAULT_COVERSHEET_OVERLAY_MAP = {
    "given_name": {
        "page": 0,
        "x": 84,
        "y": 623,
        "width": 126,
        "font_size": 8,
        "min_font_size": 6,
        "max_lines": 1,
    },
    "family_name": {
        "page": 0,
        "x": 225,
        "y": 623,
        "width": 140,
        "font_size": 8,
        "min_font_size": 6,
        "max_lines": 1,
    },
    "first_named_inventor": {
        "page": 0,
        "x": 84,
        "y": 623,
        "width": 281,
        "font_size": 8,
        "min_font_size": 6,
        "max_lines": 1,
    },
    "residence_location": {
        "page": 0,
        "x": 382,
        "y": 623,
        "width": 140,
        "font_size": 8,
        "min_font_size": 6,
        "max_lines": 1,
    },
    "title_of_invention": {
        "page": 0,
        "x": 84,
        "y": 486,
        "width": 438,
        "font_size": 11,
        "min_font_size": 8,
        "max_lines": 3,
        "line_height": 12,
    },
    "name_of_applicant": {
        "page": 0,
        "x": 138,
        "y": 403,
        "width": 381,
        "font_size": 8,
        "min_font_size": 6,
        "max_lines": 1,
    },
    "correspondence_address": {
        "page": 0,
        "x": 118,
        "y": 381,
        "width": 401,
        "font_size": 8,
        "min_font_size": 6,
        "max_lines": 1,
    },
    "city": {
        "page": 0,
        "x": 110,
        "y": 347,
        "width": 150,
        "font_size": 8,
        "min_font_size": 6,
        "max_lines": 1,
    },
    "state": {
        "page": 0,
        "x": 306,
        "y": 347,
        "width": 82,
        "font_size": 8,
        "min_font_size": 6,
        "max_lines": 1,
    },
    "zip_code": {
        "page": 0,
        "x": 434,
        "y": 347,
        "width": 72,
        "font_size": 8,
        "min_font_size": 6,
        "max_lines": 1,
    },
    "country": {
        "page": 0,
        "x": 110,
        "y": 325,
        "width": 150,
        "font_size": 8,
        "min_font_size": 6,
        "max_lines": 1,
    },
    "phone_number": {
        "page": 0,
        "x": 270,
        "y": 325,
        "width": 110,
        "font_size": 8,
        "min_font_size": 6,
        "max_lines": 1,
    },
    "email": {
        "page": 0,
        "x": 430,
        "y": 325,
        "width": 97,
        "font_size": 8,
        "min_font_size": 6,
        "max_lines": 1,
    },
    "signature": {
        "page": 1,
        "x": 113,
        "y": 271,
        "width": 245,
        "font_size": 9,
        "min_font_size": 7,
        "max_lines": 1,
    },
    "date": {
        "page": 1,
        "x": 404,
        "y": 271,
        "width": 85,
        "font_size": 9,
        "min_font_size": 8,
        "max_lines": 1,
    },
    "typed_or_printed_name": {
        "page": 1,
        "x": 162,
        "y": 249,
        "width": 198,
        "font_size": 9,
        "min_font_size": 7,
        "max_lines": 1,
    },
    "registration_number": {
        "page": 1,
        "x": 469,
        "y": 249,
        "width": 64,
        "font_size": 8,
        "min_font_size": 6,
        "max_lines": 1,
    },
    "telephone": {
        "page": 1,
        "x": 118,
        "y": 215,
        "width": 176,
        "font_size": 9,
        "min_font_size": 7,
        "max_lines": 1,
    },
    "docket_number": {
        "page": 1,
        "x": 364,
        "y": 215,
        "width": 126,
        "font_size": 8,
        "min_font_size": 6,
        "max_lines": 1,
    },
}


def _normalize_coversheet_text(value):
    if value is None:
        return ""

    text = str(value)
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = re.sub(r"[`*_#>]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _split_long_token(token, max_width, font_name, font_size):
    if pdfmetrics is None:
        return [token]

    parts = []
    current = ""
    for character in token:
        candidate = f"{current}{character}"
        if not current or pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
            continue
        parts.append(current)
        current = character

    if current:
        parts.append(current)
    return parts or [token]


def _wrap_coversheet_text(text, max_width, font_name, font_size):
    normalized = _normalize_coversheet_text(text)
    if not normalized or pdfmetrics is None or max_width <= 0:
        return [normalized] if normalized else []

    tokens = []
    for raw_token in normalized.split():
        if pdfmetrics.stringWidth(raw_token, font_name, font_size) <= max_width:
            tokens.append(raw_token)
            continue
        tokens.extend(_split_long_token(raw_token, max_width, font_name, font_size))

    lines = []
    current = ""
    for token in tokens:
        candidate = token if not current else f"{current} {token}"
        if current and pdfmetrics.stringWidth(candidate, font_name, font_size) > max_width:
            lines.append(current)
            current = token
            continue
        current = candidate

    if current:
        lines.append(current)
    return lines


def _truncate_to_width(text, max_width, font_name, font_size):
    normalized = _normalize_coversheet_text(text)
    if pdfmetrics is None or not normalized or max_width <= 0:
        return normalized

    if pdfmetrics.stringWidth(normalized, font_name, font_size) <= max_width:
        return normalized

    ellipsis = "..."
    working = normalized
    while (
        working and pdfmetrics.stringWidth(f"{working}{ellipsis}", font_name, font_size) > max_width
    ):
        working = working[:-1].rstrip()
    return f"{working}{ellipsis}" if working else ellipsis


def _fit_coversheet_lines(text, spec):
    normalized = _normalize_coversheet_text(text)
    if not normalized:
        return [], spec.get("font_size", 10)

    font_name = spec.get("font_name", "Helvetica")
    width = spec.get("width", 0)
    max_lines = max(spec.get("max_lines", 1), 1)
    font_size = spec.get("font_size", 10)
    min_font_size = spec.get("min_font_size", font_size)

    for size in range(font_size, min_font_size - 1, -1):
        lines = _wrap_coversheet_text(normalized, width, font_name, size) if width else [normalized]
        if len(lines) <= max_lines:
            if max_lines == 1 and width:
                return [_truncate_to_width(lines[0], width, font_name, size)], size
            return lines, size

    if max_lines == 1 and width:
        return [_truncate_to_width(normalized, width, font_name, min_font_size)], min_font_size

    lines = (
        _wrap_coversheet_text(normalized, width, font_name, min_font_size)
        if width
        else [normalized]
    )
    return lines[:max_lines], min_font_size


def _draw_coversheet_value(canvas, value, spec):
    lines, font_size = _fit_coversheet_lines(value, spec)
    if not lines:
        return

    font_name = spec.get("font_name", "Helvetica")
    line_height = spec.get("line_height", font_size + 2)
    x = spec["x"]
    y = spec["y"]

    canvas.setFont(font_name, font_size)
    for index, line in enumerate(lines):
        canvas.drawString(x, y - (index * line_height), line)


def _build_styles():
    base = getSampleStyleSheet()
    return {
        "cover_label": ParagraphStyle(
            "CoverLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            alignment=TA_CENTER,
            spaceAfter=18,
            textColor=colors.HexColor("#4B5563"),
        ),
        "cover_title": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=28,
            alignment=TA_CENTER,
            spaceAfter=12,
            textColor=colors.HexColor("#111827"),
        ),
        "cover_meta": ParagraphStyle(
            "CoverMeta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#374151"),
            spaceAfter=8,
        ),
        "cover_note": ParagraphStyle(
            "CoverNote",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#6B7280"),
            leftIndent=40,
            rightIndent=40,
        ),
        "heading": ParagraphStyle(
            "SectionHeading",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#111827"),
            spaceBefore=8,
            spaceAfter=8,
        ),
        "subheading": ParagraphStyle(
            "SubsectionHeading",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#1F2937"),
            spaceBefore=8,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Times-Roman",
            fontSize=12,
            leading=18,
            alignment=TA_JUSTIFY,
            textColor=colors.HexColor("#111827"),
            spaceAfter=8,
        ),
        "claim": ParagraphStyle(
            "Claim",
            parent=base["BodyText"],
            fontName="Times-Roman",
            fontSize=12,
            leading=18,
            leftIndent=18,
            firstLineIndent=-12,
            textColor=colors.HexColor("#111827"),
            spaceAfter=6,
        ),
    }


def _page_chrome(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColorRGB(0.86, 0.89, 0.93)
    canvas.line(
        doc.leftMargin, rl_letter[1] - 36, rl_letter[0] - doc.rightMargin, rl_letter[1] - 36
    )
    canvas.setFont("Helvetica", 8)
    canvas.setFillColorRGB(0.42, 0.46, 0.52)
    canvas.drawString(doc.leftMargin, rl_letter[1] - 28, "Manifest provisional patent packet")
    canvas.drawRightString(
        rl_letter[0] - doc.rightMargin,
        24,
        f"Draft for review only · Page {canvas.getPageNumber()}",
    )
    canvas.restoreState()


def _flush_paragraph(story, lines, style):
    if not lines:
        return
    paragraph = " ".join(lines).strip()
    if paragraph:
        story.append(Paragraph(escape(paragraph), style))
    lines.clear()


def _flush_bullets(story, items, style):
    if not items:
        return
    if ListFlowable is None or ListItem is None:
        for item in items:
            story.append(Paragraph(escape(item), style))
    else:
        story.append(
            ListFlowable(
                [ListItem(Paragraph(escape(item), style)) for item in items],
                bulletType="bullet",
                leftIndent=18,
            )
        )
    items.clear()


def _append_markdown_blocks(story, text, styles, *, claim_mode=False):
    paragraph_lines = []
    bullet_lines = []

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            _flush_paragraph(
                story, paragraph_lines, styles["claim"] if claim_mode else styles["body"]
            )
            _flush_bullets(story, bullet_lines, styles["body"])
            continue

        if line.startswith("## "):
            _flush_paragraph(
                story, paragraph_lines, styles["claim"] if claim_mode else styles["body"]
            )
            _flush_bullets(story, bullet_lines, styles["body"])
            story.append(Paragraph(escape(line[3:].strip()), styles["subheading"]))
            continue

        bullet_match = re.match(r"^[-*]\s+(.+)$", line)
        if bullet_match:
            _flush_paragraph(
                story, paragraph_lines, styles["claim"] if claim_mode else styles["body"]
            )
            bullet_lines.append(bullet_match.group(1).strip())
            continue

        if claim_mode and re.match(r"^\d+\.\s+", line):
            _flush_paragraph(story, paragraph_lines, styles["claim"])
            _flush_bullets(story, bullet_lines, styles["body"])
            story.append(Paragraph(escape(line), styles["claim"]))
            continue

        _flush_bullets(story, bullet_lines, styles["body"])
        paragraph_lines.append(line)

    _flush_paragraph(story, paragraph_lines, styles["claim"] if claim_mode else styles["body"])
    _flush_bullets(story, bullet_lines, styles["body"])


def generate_specification_pdf(output_path, title, abstract, description, claims, drawings):
    """
    Generate a polished provisional patent packet PDF using reportlab when available.
    Falls back to a blank single-page PDF when reportlab is unavailable.
    """
    if rl_canvas is None or SimpleDocTemplate is None or Paragraph is None:
        writer = PdfWriter()
        writer.add_blank_page(width=rl_letter[0], height=rl_letter[1])
        with open(output_path, "wb") as pdf_file:
            writer.write(pdf_file)
        return output_path

    styles = _build_styles()
    doc = SimpleDocTemplate(
        output_path,
        pagesize=rl_letter,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.7 * inch,
    )

    story = [
        Paragraph("PROVISIONAL PATENT APPLICATION DRAFT", styles["cover_label"]),
        Paragraph(escape(title or "Untitled invention"), styles["cover_title"]),
        Paragraph(
            "Draft for inventor and attorney review. Suggested figures are not completed drawings. "
            "The official cover sheet is provided separately.",
            styles["cover_note"],
        ),
        Spacer(1, 0.25 * inch),
    ]

    sections = [
        ("Description", description),
        ("Suggested Drawings — To Be Prepared", drawings),
        ("Optional Draft Claims", claims),
        ("Abstract", abstract),
    ]

    for heading, body in sections:
        if not body:
            continue
        if heading in {"Optional Draft Claims", "Abstract"}:
            story.append(PageBreak())
        story.append(Paragraph(escape(heading.upper()), styles["heading"]))
        _append_markdown_blocks(story, body, styles, claim_mode=heading == "Optional Draft Claims")
        story.append(Spacer(1, 0.12 * inch))

    doc.build(story, onFirstPage=_page_chrome, onLaterPages=_page_chrome)
    return output_path


# Utility to fill the coversheet PDF using PyPDF (overlay text on sb0016.pdf)
def fill_coversheet_with_pypdf(template_pdf_path, output_pdf_path, field_data, overlay_map=None):
    """
    Fill the official coversheet PDF (e.g., sb0016.pdf) by overlaying text using PyPDF and ReportLab.
    field_data: dict mapping field names to values.
    overlay_map: dict mapping field names to overlay specs. Each spec may include
    page, x, y, width, font_size, min_font_size, max_lines, and line_height.
    """
    if overlay_map is None:
        overlay_map = DEFAULT_COVERSHEET_OVERLAY_MAP

    original = PdfReader(template_pdf_path)
    writer = PdfWriter()

    if rl_Canvas is not None:
        packet = BytesIO()
        can = rl_Canvas(packet, pagesize=rl_letter)

        for page_index in range(len(original.pages)):
            for field, value in field_data.items():
                spec = overlay_map.get(field)
                if not spec:
                    continue

                if isinstance(spec, tuple):
                    spec = {"page": 0, "x": spec[0], "y": spec[1]}

                if spec.get("page", 0) != page_index:
                    continue

                _draw_coversheet_value(can, value, spec)

            if page_index < len(original.pages) - 1:
                can.showPage()
        can.save()
        packet.seek(0)
        overlay = PdfReader(packet)
    else:
        overlay = None

    for page_index, page in enumerate(original.pages):
        if overlay is not None and page_index < len(overlay.pages):
            page.merge_page(overlay.pages[page_index])
        elif overlay is None:
            overlay_page = PageObject.create_blank_page(
                width=float(page.mediabox.width),
                height=float(page.mediabox.height),
            )
            page.merge_page(overlay_page)
        writer.add_page(page)

    with open(output_pdf_path, "wb") as f:
        writer.write(f)
    return output_pdf_path
