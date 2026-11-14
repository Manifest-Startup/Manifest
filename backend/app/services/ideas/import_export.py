"""
Import/export helpers for Manifest ideas.

Import support focuses on real user workflows from note apps:
- Apple Notes exports as Markdown or PDF on macOS
- Google Keep exports via Google Takeout archives (.zip or .tgz)
- Existing Manifest backups in JSON / CSV / Markdown

Uploaded notes are parsed first, then filtered so that only startup/product
ideas are imported into the workspace.
"""

import csv
import html
import io
import json
import re
import tarfile
import zipfile
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from app.services.ai.router import AIRouter
from app.utils.logger import logger
from pypdf import PdfReader


class ImportExportService:
    """Service for exporting ideas and importing note-app exports."""

    MAX_AI_NOTES_PER_BATCH = 10
    MAX_AI_NOTE_CHARS = 1400
    POSITIVE_IDEA_HINTS = (
        "idea",
        "startup",
        "business",
        "product",
        "feature",
        "app",
        "platform",
        "tool",
        "automation",
        "prototype",
        "mvp",
        "market",
        "customer",
        "problem",
        "solution",
        "workflow",
        "revenue",
        "pitch",
        "founder",
        "saas",
        "venture",
    )
    NEGATIVE_IDEA_HINTS = (
        "grocery",
        "shopping list",
        "errands",
        "reminder",
        "journal",
        "diary",
        "recipe",
        "packing list",
        "chores",
        "birthday",
        "password",
        "medication",
        "homework",
    )
    IDEA_CLASSIFIER_SYSTEM_PROMPT = """
You help import personal notes into a founder workspace.

Decide whether each note should become a Manifest idea.

A note IS an idea when it clearly contains:
- a startup, product, service, workflow automation, or venture concept
- a customer problem paired with a possible solution
- a product or business opportunity worth developing further

A note is NOT an idea when it is mainly:
- a personal reminder, shopping list, errands, journaling, recipe, quote, or generic reference note
- meeting logistics or notes without a real product/business concept

Return valid JSON only in this shape:
{
  "results": [
    {
      "index": 0,
      "is_idea": true,
      "confidence": 0.92,
      "normalized_title": "Short clear title",
      "summary": "One or two concise sentences about the venture concept."
    }
  ]
}

Rules:
- Include one result per note index.
- If a note is not an idea, set "is_idea" to false and leave title/summary blank.
- Keep normalized_title under 80 characters.
- Do not invent details not present in the note.
""".strip()

    def __init__(self, ai_router: AIRouter | None = None):
        self.log = logger
        self.ai_router = ai_router or AIRouter()

    def export_to_json(self, ideas: list[dict[str, Any]]) -> str:
        """Export ideas to JSON format."""
        export_data = {
            "version": "1.0",
            "export_date": datetime.utcnow().isoformat(),
            "format": "manifest_ideas",
            "ideas": [],
        }

        for idea in ideas:
            export_data["ideas"].append(
                {
                    "title": idea.get("title", ""),
                    "description": idea.get("description", ""),
                    "summary": idea.get("summary", ""),
                    "tags": idea.get("tags", ""),
                    "created_at": idea.get("created_at", ""),
                    "updated_at": idea.get("updated_at", ""),
                    "business_model_canvas": idea.get("business_model_canvas", ""),
                }
            )

        return json.dumps(export_data, indent=2, ensure_ascii=False)

    def export_to_csv(self, ideas: list[dict[str, Any]]) -> str:
        """Export ideas to CSV format."""
        output = io.StringIO()
        fieldnames = ["title", "description", "summary", "tags", "created_at", "updated_at"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for idea in ideas:
            writer.writerow(
                {
                    "title": idea.get("title", ""),
                    "description": self._strip_html(idea.get("description", "")),
                    "summary": idea.get("summary", ""),
                    "tags": idea.get("tags", ""),
                    "created_at": idea.get("created_at", ""),
                    "updated_at": idea.get("updated_at", ""),
                }
            )

        return output.getvalue()

    def export_to_markdown(self, ideas: list[dict[str, Any]]) -> str:
        """Export ideas to Markdown format."""
        markdown_content = (
            "# Manifest Ideas Export\n"
            f"*Exported on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC*\n\n"
        )

        for index, idea in enumerate(ideas, 1):
            title = idea.get("title", "Untitled Idea")
            description = self._strip_html(idea.get("description", ""))
            summary = idea.get("summary", "")
            tags = idea.get("tags", "")
            created_at = idea.get("created_at", "")

            markdown_content += f"## {index}. {title}\n\n"
            if summary:
                markdown_content += f"**Summary:** {summary}\n\n"
            if description:
                markdown_content += f"{description}\n\n"
            if tags:
                markdown_content += f"**Tags:** {tags}\n\n"
            if created_at:
                markdown_content += f"*Created: {created_at}*\n\n"
            markdown_content += "---\n\n"

        return markdown_content

    def prepare_import(self, file_bytes: bytes, file_format: str, filename: str) -> dict[str, Any]:
        """Parse an uploaded file or archive and keep only startup-like ideas."""
        candidates, warnings = self._load_note_candidates(file_bytes, file_format, filename)
        deduped_candidates = self._dedupe_candidates(candidates)
        ideas = self._select_idea_candidates(deduped_candidates)
        skipped_non_ideas = max(len(deduped_candidates) - len(ideas), 0)

        if not deduped_candidates:
            warnings.append("We couldn't find readable notes in that file.")
        elif not ideas:
            warnings.append("We didn't detect startup ideas in that upload.")

        return {
            "ideas": ideas,
            "skipped_non_ideas": skipped_non_ideas,
            "warnings": warnings,
        }

    def import_from_google_keep_takeout(
        self, archive_bytes: bytes, filename: str = "keep-export.zip"
    ) -> list[dict[str, Any]]:
        """Backward-compatible helper for Google Keep archives."""
        return self.prepare_import(archive_bytes, "zip", filename)["ideas"]

    def idea_fingerprint(self, idea: dict[str, Any]) -> str:
        """Create a stable fingerprint to avoid duplicate imports."""
        title = self._normalize_text(idea.get("title", "")).lower()
        description = self._normalize_text(idea.get("description", "")).lower()
        return f"{title}|{description[:320]}"

    def _load_note_candidates(
        self, file_bytes: bytes, file_format: str, filename: str
    ) -> tuple[list[dict[str, Any]], list[str]]:
        format_lower = self._detect_format(file_format, filename)

        if format_lower == "json":
            return self.import_from_json(self._decode_text(file_bytes), filename), []
        if format_lower == "csv":
            return self.import_from_csv(self._decode_text(file_bytes), filename), []
        if format_lower == "markdown":
            return self.import_from_markdown(self._decode_text(file_bytes), filename), []
        if format_lower == "html":
            return self.import_from_html(self._decode_text(file_bytes), filename), []
        if format_lower == "text":
            return self.import_from_text(self._decode_text(file_bytes), filename), []
        if format_lower == "pdf":
            return self.import_from_pdf(file_bytes, filename), []
        if format_lower in {"zip", "tgz"}:
            return self.import_from_archive(file_bytes, filename)

        raise ValueError(f"Unsupported import format: {file_format}")

    def import_from_archive(  # noqa: C901
        self, archive_bytes: bytes, filename: str
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Import note candidates from ZIP or TGZ archives."""
        candidates: list[dict[str, Any]] = []
        warnings: list[str] = []
        format_lower = self._detect_format("", filename)

        members: list[tuple[str, bytes]] = []
        if format_lower == "zip":
            try:
                with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                    for member_name in archive.namelist():
                        if member_name.endswith("/") or member_name.startswith("__MACOSX/"):
                            continue
                        members.append((member_name, archive.read(member_name)))
            except zipfile.BadZipFile as exc:
                raise ValueError("Invalid ZIP file format") from exc
        elif format_lower == "tgz":
            try:
                with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
                    for member in archive.getmembers():
                        if not member.isfile():
                            continue
                        extracted = archive.extractfile(member)
                        if extracted is None:
                            continue
                        members.append((member.name, extracted.read()))
            except tarfile.TarError as exc:
                raise ValueError("Invalid TGZ archive format") from exc
        else:
            raise ValueError(f"Unsupported archive format: {filename}")

        for member_name, member_bytes in members:
            member_format = self._detect_format("", member_name)
            if member_format not in {"json", "csv", "markdown", "html", "text", "pdf"}:
                continue

            try:
                member_candidates, member_warnings = self._load_note_candidates(
                    member_bytes, member_format, member_name
                )
                candidates.extend(member_candidates)
                warnings.extend(member_warnings)
            except Exception as exc:
                warnings.append(f"Skipped {PurePosixPath(member_name).name}: {exc}")

        return candidates, warnings

    def import_from_json(
        self, json_data: str, filename: str = "import.json"
    ) -> list[dict[str, Any]]:
        """Parse JSON exports into note candidates."""
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON format: {exc}") from exc

        if isinstance(data, dict) and "ideas" in data:
            records = data["ideas"]
        elif isinstance(data, dict) and "notes" in data:
            records = data["notes"]
        elif isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = [data]
        else:
            raise ValueError(
                "Invalid JSON format: expected a note object, list, or Manifest export."
            )

        candidates = []
        fallback_title = self._basename_without_extension(filename)
        for index, record in enumerate(records, 1):
            if not isinstance(record, dict):
                continue
            candidate = self._candidate_from_mapping(
                record,
                fallback_title=f"{fallback_title} {index}".strip(),
                source_hint=self._source_hint_from_name(filename),
            )
            if candidate:
                candidates.append(candidate)

        return candidates

    def import_from_csv(self, csv_data: str, filename: str = "import.csv") -> list[dict[str, Any]]:
        """Parse CSV exports into note candidates."""
        reader = csv.DictReader(io.StringIO(csv_data))
        candidates = []
        fallback_title = self._basename_without_extension(filename)

        for index, row in enumerate(reader, 1):
            candidate = self._candidate_from_mapping(
                row,
                fallback_title=f"{fallback_title} {index}".strip(),
                source_hint=self._source_hint_from_name(filename),
            )
            if candidate:
                candidates.append(candidate)

        return candidates

    def import_from_markdown(
        self, markdown_data: str, filename: str = "import.md"
    ) -> list[dict[str, Any]]:
        """Parse Markdown note exports."""
        markdown_data = markdown_data.replace("\ufeff", "").strip()
        if not markdown_data:
            return []

        if "# Manifest Ideas Export" in markdown_data:
            candidates = []
            sections = re.split(r"\n---+\n", markdown_data)
            for section in sections:
                title, description, summary, tags = self._parse_manifest_markdown_section(section)
                if title or description:
                    candidates.append(
                        self._build_candidate(
                            title=title or self._basename_without_extension(filename),
                            description=description,
                            summary=summary,
                            tags=tags,
                            source_hint=self._source_hint_from_name(filename),
                        )
                    )
            return [candidate for candidate in candidates if candidate]

        title, body = self._extract_title_and_body(
            markdown_data, self._basename_without_extension(filename)
        )
        return [
            self._build_candidate(
                title=title,
                description=body or markdown_data,
                summary="",
                tags="",
                source_hint=self._source_hint_from_name(filename),
            )
        ]

    def import_from_html(
        self, html_data: str, filename: str = "import.html"
    ) -> list[dict[str, Any]]:
        """Parse HTML note exports, including Google Keep and Apple Notes HTML."""
        source_hint = self._source_hint_from_name(filename)
        fallback_title = self._basename_without_extension(filename)

        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html_data, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()

            title = ""
            if soup.title and soup.title.get_text(strip=True):
                title = soup.title.get_text(strip=True)
            if not title:
                heading = soup.find(["h1", "h2", "h3"])
                if heading:
                    title = heading.get_text(" ", strip=True)

            body_text = soup.get_text("\n", strip=True)
        except Exception:
            title = ""
            body_text = self._strip_html(html_data)

        title, body = self._extract_title_and_body(body_text, title or fallback_title)
        return [
            self._build_candidate(
                title=title,
                description=body or body_text,
                summary="",
                tags="",
                source_hint=source_hint,
            )
        ]

    def import_from_text(
        self, text_data: str, filename: str = "import.txt"
    ) -> list[dict[str, Any]]:
        """Parse plain text note exports."""
        title, body = self._extract_title_and_body(
            text_data, self._basename_without_extension(filename)
        )
        return [
            self._build_candidate(
                title=title,
                description=body or text_data,
                summary="",
                tags="",
                source_hint=self._source_hint_from_name(filename),
            )
        ]

    def import_from_pdf(
        self, pdf_bytes: bytes, filename: str = "import.pdf"
    ) -> list[dict[str, Any]]:
        """Parse Apple Notes PDF exports or generic note PDFs."""
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        except Exception as exc:
            raise ValueError(f"Unable to read PDF: {exc}") from exc

        if not text:
            return []

        title, body = self._extract_title_and_body(text, self._basename_without_extension(filename))
        return [
            self._build_candidate(
                title=title,
                description=body or text,
                summary="",
                tags="",
                source_hint=self._source_hint_from_name(filename),
            )
        ]

    def _candidate_from_mapping(
        self,
        mapping: dict[str, Any],
        *,
        fallback_title: str,
        source_hint: str,
    ) -> dict[str, Any] | None:
        title = self._first_text(
            mapping.get("title"),
            mapping.get("name"),
            mapping.get("heading"),
            mapping.get("subject"),
        )

        description_parts = [
            self._normalize_text(mapping.get("description")),
            self._normalize_text(mapping.get("content")),
            self._normalize_text(mapping.get("body")),
            self._normalize_text(mapping.get("note")),
            self._normalize_text(mapping.get("text")),
            self._normalize_text(mapping.get("textContent")),
        ]

        checklist = self._flatten_list_items(
            mapping.get("listContent") or mapping.get("items") or mapping.get("listItems")
        )
        if checklist:
            description_parts.append(checklist)

        summary = self._normalize_text(mapping.get("summary"))
        if summary and summary not in description_parts:
            description_parts.append(summary)

        description = "\n\n".join(part for part in description_parts if part)
        labels = self._extract_tag_list(mapping.get("tags")) + self._extract_tag_list(
            mapping.get("labels")
        )

        if not title and description:
            title, description = self._extract_title_and_body(description, fallback_title)

        return self._build_candidate(
            title=title or fallback_title,
            description=description,
            summary=summary,
            tags=",".join(labels),
            source_hint=source_hint,
        )

    def _build_candidate(
        self,
        *,
        title: str,
        description: str,
        summary: str,
        tags: str,
        source_hint: str,
    ) -> dict[str, Any] | None:
        clean_title = self._normalize_text(title)
        clean_description = self._normalize_text(description)
        clean_summary = self._normalize_text(summary)
        merged_tags = self._merge_tags(tags, source_hint)

        if not clean_title and not clean_description:
            return None

        if not clean_title:
            clean_title = self._title_from_content(clean_description, "Imported note")

        if clean_title and clean_description and clean_description.startswith(clean_title):
            clean_description = clean_description[len(clean_title) :].strip(" -:\n")

        if not clean_summary:
            clean_summary = self._build_summary(clean_description)

        return {
            "title": clean_title[:120],
            "description": clean_description,
            "summary": clean_summary,
            "tags": merged_tags,
            "source_hint": source_hint,
        }

    def _dedupe_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen = set()

        for candidate in candidates:
            fingerprint = self.idea_fingerprint(candidate)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            deduped.append(candidate)

        return deduped

    def _select_idea_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not candidates:
            return []

        decisions: dict[int, dict[str, Any]] = {}
        if self.ai_router.is_available():
            try:
                decisions.update(self._classify_with_ai(candidates))
            except Exception as exc:
                self.log.warning("AI note classification failed, using heuristic fallback: %s", exc)

        ideas: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            heuristic_decision = self._heuristic_decision(candidate)
            decision = decisions.get(index)
            is_idea = (
                bool(decision.get("is_idea"))
                if decision
                else bool(heuristic_decision.get("is_idea"))
            )

            # Keep strongly idea-like notes even when AI returns a false negative.
            if not is_idea and heuristic_decision.get("is_idea"):
                is_idea = True

            if not is_idea:
                continue

            normalized_title = (
                self._normalize_text((decision or {}).get("normalized_title"))
                or self._normalize_text(heuristic_decision.get("normalized_title"))
                or candidate["title"]
            )
            summary = (
                self._normalize_text((decision or {}).get("summary"))
                or self._normalize_text(heuristic_decision.get("summary"))
                or candidate.get("summary")
                or self._build_summary(candidate.get("description", ""))
            )
            idea = {
                "title": normalized_title[:120],
                "description": candidate.get("description", ""),
                "summary": summary,
                "tags": candidate.get("tags", ""),
            }
            ideas.append(idea)

        return ideas

    def _classify_with_ai(self, candidates: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        decisions: dict[int, dict[str, Any]] = {}

        for offset in range(0, len(candidates), self.MAX_AI_NOTES_PER_BATCH):
            batch = candidates[offset : offset + self.MAX_AI_NOTES_PER_BATCH]
            payload = {
                "notes": [
                    {
                        "index": offset + index,
                        "title": candidate.get("title", ""),
                        "content": (candidate.get("description", "") or "")[
                            : self.MAX_AI_NOTE_CHARS
                        ],
                        "tags": candidate.get("tags", ""),
                    }
                    for index, candidate in enumerate(batch)
                ]
            }

            result = self.ai_router.chat_json(
                prompt=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                system_prompt=self.IDEA_CLASSIFIER_SYSTEM_PROMPT,
                temperature=0.1,
            )

            for item in result.get("results", []):
                if not isinstance(item, dict) or "index" not in item:
                    continue
                decisions[int(item["index"])] = item

        return decisions

    def _heuristic_decision(self, candidate: dict[str, Any]) -> dict[str, Any]:
        title = (candidate.get("title") or "").lower()
        description = (candidate.get("description") or "").lower()
        text = f"{title}\n{description}"

        positive_score = sum(1 for hint in self.POSITIVE_IDEA_HINTS if hint in text)
        negative_score = sum(1 for hint in self.NEGATIVE_IDEA_HINTS if hint in text)

        if "idea" in title or "startup" in title or "product" in title:
            positive_score += 2
        if "problem" in text and ("solution" in text or "customer" in text or "market" in text):
            positive_score += 2
        if len(text.split()) >= 40:
            positive_score += 1

        is_idea = positive_score >= 3 and positive_score >= negative_score

        return {
            "is_idea": is_idea,
            "normalized_title": candidate.get("title", ""),
            "summary": candidate.get("summary")
            or self._build_summary(candidate.get("description", "")),
        }

    def _parse_manifest_markdown_section(self, section: str) -> tuple[str, str, str, str]:
        section = section.strip()
        if not section or section.startswith("# Manifest Ideas Export"):
            return "", "", "", ""

        lines = [line.rstrip() for line in section.splitlines()]
        title = ""
        summary = ""
        tags = ""
        description_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if not title and (stripped.startswith("## ") or re.match(r"^##\s*\d+\.", stripped)):
                title = re.sub(r"^##\s*\d+\.?\s*", "", stripped).strip()
                continue
            if stripped.startswith("**Summary:**"):
                summary = stripped.replace("**Summary:**", "").strip()
                continue
            if stripped.startswith("**Tags:**"):
                tags = stripped.replace("**Tags:**", "").strip()
                continue
            if stripped.startswith("*Created:"):
                continue
            description_lines.append(stripped)

        return title, "\n".join(description_lines).strip(), summary, tags

    def _extract_title_and_body(self, text: str, fallback_title: str) -> tuple[str, str]:
        normalized_lines = [self._normalize_text(line) for line in text.splitlines()]
        non_empty_lines = [line for line in normalized_lines if line]
        if not non_empty_lines:
            return fallback_title, ""

        first_line = non_empty_lines[0]
        heading_title = re.sub(r"^#+\s*", "", first_line).strip()
        title = fallback_title
        body_lines = list(non_empty_lines)

        if first_line.startswith("#"):
            title = heading_title or fallback_title
            body_lines = non_empty_lines[1:]
        elif len(first_line) <= 90 and len(non_empty_lines) > 1:
            title = first_line
            body_lines = non_empty_lines[1:]

        body = "\n".join(body_lines).strip()
        return title or fallback_title, body

    def _build_summary(self, text: str) -> str:
        normalized = self._normalize_text(text)
        if not normalized:
            return ""
        sentences = re.split(r"(?<=[.!?])\s+", normalized)
        summary = " ".join(sentences[:2]).strip()
        if len(summary) > 200:
            summary = summary[:197].rstrip() + "..."
        return summary

    def _flatten_list_items(self, items: Any) -> str:
        if not items:
            return ""

        flattened = []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    text = self._first_text(
                        item.get("text"),
                        item.get("itemText"),
                        item.get("content"),
                        item.get("value"),
                    )
                    if not text:
                        continue
                    checked = item.get("isChecked") or item.get("checked")
                    prefix = "- [x]" if checked else "- [ ]"
                    flattened.append(f"{prefix} {text}")
                else:
                    text = self._normalize_text(item)
                    if text:
                        flattened.append(f"- {text}")

        return "\n".join(flattened)

    def _extract_tag_list(self, value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            tags: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    tag = self._first_text(item.get("name"), item.get("title"), item.get("value"))
                else:
                    tag = self._normalize_text(item)
                if tag:
                    tags.append(tag)
            return tags
        return []

    def _merge_tags(self, tags: str, source_hint: str) -> str:
        tag_values = self._extract_tag_list(tags)
        if source_hint:
            tag_values.append(source_hint)

        deduped = []
        seen = set()
        for tag in tag_values:
            normalized = tag.strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)

        return ", ".join(deduped)

    def _detect_format(self, file_format: str, filename: str) -> str:
        lower_name = (filename or "").lower()
        lower_format = (file_format or "").lower()

        if lower_name.endswith(".tar.gz") or lower_name.endswith(".tgz") or lower_format == "tgz":
            return "tgz"
        if lower_name.endswith(".zip") or lower_format == "zip":
            return "zip"
        if (
            lower_name.endswith(".markdown")
            or lower_name.endswith(".md")
            or lower_format == "markdown"
        ):
            return "markdown"
        if lower_name.endswith(".html") or lower_name.endswith(".htm") or lower_format == "html":
            return "html"
        if lower_name.endswith(".txt") or lower_format == "txt":
            return "text"
        if lower_name.endswith(".pdf") or lower_format == "pdf":
            return "pdf"
        if lower_name.endswith(".csv") or lower_format == "csv":
            return "csv"
        if lower_name.endswith(".json") or lower_format == "json":
            return "json"
        return lower_format

    def _source_hint_from_name(self, filename: str) -> str:
        lower_name = (filename or "").lower()
        if "keep" in lower_name or "takeout" in lower_name:
            return "google-keep"
        if lower_name.endswith((".md", ".markdown", ".pdf", ".html", ".htm", ".txt")):
            return "apple-notes"
        if lower_name.endswith((".json", ".csv")):
            return "manifest-import"
        return "imported-notes"

    def _decode_text(self, file_bytes: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "utf-16", "latin-1"):
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        return file_bytes.decode("utf-8", errors="ignore")

    def _basename_without_extension(self, filename: str) -> str:
        name = PurePosixPath(filename or "Imported note").name
        if name.endswith(".tar.gz"):
            return name[:-7]
        return re.sub(r"\.[^.]+$", "", name) or "Imported note"

    def _title_from_content(self, text: str, fallback_title: str) -> str:
        first_meaningful_line = next(
            (line for line in text.splitlines() if self._normalize_text(line)), ""
        )
        cleaned = re.sub(r"^[-*#\d.\s]+", "", first_meaningful_line).strip()
        if not cleaned:
            cleaned = fallback_title
        return cleaned[:80]

    def _first_text(self, *values: Any) -> str:
        for value in values:
            normalized = self._normalize_text(value)
            if normalized:
                return normalized
        return ""

    def _normalize_text(self, value: Any) -> str:
        if value is None:
            return ""
        text = str(value).replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\u00a0", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def _strip_html(self, html_content: str) -> str:
        if not html_content:
            return ""
        text = re.sub(r"<[^>]+>", "", html_content)
        return html.unescape(text).strip()
