"""Website audit and GitHub issue sync service for Manifest agents."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover - exercised only in lean environments
    BeautifulSoup = None  # type: ignore[assignment]

from app.services.ai_router import AIRouter
from app.services.github_issue_service import (
    GitHubIssueConfigurationError,
    GitHubIssueDraft,
    GitHubIssueService,
)
from app.utils.logger import logger

SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

ALLOWED_CATEGORIES = {
    "bug",
    "ux",
    "feature",
    "performance",
    "accessibility",
    "seo",
}

LABEL_COLORS = {
    "website-audit": "0e8a16",
    "bug": "d73a4a",
    "ux": "fbca04",
    "feature": "a2eeef",
    "performance": "5319e7",
    "accessibility": "1d76db",
    "seo": "0052cc",
    "priority:critical": "b60205",
    "priority:high": "d93f0b",
    "priority:medium": "fbca04",
    "priority:low": "0e8a16",
}


@dataclass
class CrawledPage:
    """Normalized representation of a crawled public page."""

    url: str
    status_code: int | None
    response_time_ms: int | None
    content_type: str
    html_size_bytes: int
    title: str | None
    meta_description: str | None
    canonical_url: str | None
    h1_text: str | None
    text_excerpt: str
    internal_links: list[str]
    js_required_banner: bool
    error: str | None = None
    html_signature: str | None = None


@dataclass
class IssueCandidate:
    """GitHub-ready issue candidate extracted from a website audit."""

    title: str
    category: str
    severity: str
    page_url: str
    summary: str
    suggested_fix: str
    evidence: list[str]
    labels: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WebsiteIssueSyncConfigurationError(RuntimeError):
    """Raised when required GitHub configuration is missing."""


class WebsiteIssueSyncService:
    """Audit public website pages and optionally sync findings to GitHub Issues."""

    ANALYSIS_PROMPT = """You are Manifest's website quality triage agent.

You are given:
1. Public crawl summaries from manifeststartup.com (or another Manifest target)
2. Deterministic heuristic findings already detected from those pages

Your job is to convert them into GitHub-ready issue candidates.

Rules:
- Only use the supplied crawl data. Do not invent hidden states, broken auth, or private pages.
- Prioritize issues that reduce onboarding friction, improve robustness, or improve low-maintenance product quality.
- You may include bugs, UX enhancements, accessibility/performance/SEO fixes, and grounded new feature ideas.
- Prefer a small number of strong issues over a long list of weak ones.
- If multiple pages show the same root problem, collapse them into one issue.
- Return valid JSON only using this shape:
{
  "issues": [
    {
      "title": "Concise GitHub issue title",
      "category": "bug|ux|feature|performance|accessibility|seo",
      "severity": "critical|high|medium|low",
      "page_url": "https://...",
      "summary": "Why this matters in 1-2 sentences.",
      "suggested_fix": "Practical fix direction.",
      "evidence": ["bullet evidence 1", "bullet evidence 2"],
      "labels": ["optional-extra-label"]
    }
  ]
}
"""

    def __init__(
        self,
        *,
        router: AIRouter | None = None,
        timeout_seconds: float = 15.0,
        github_api_base: str = "https://api.github.com",
        github_issue_service: GitHubIssueService | None = None,
    ):
        self.model = os.getenv("WEBSITE_ISSUE_SYNC_MODEL", "gpt-4o-mini")
        self.router = router or AIRouter(model=self.model)
        self.timeout_seconds = timeout_seconds
        self.github_api_base = github_api_base.rstrip("/")
        self.github_issue_service = github_issue_service or GitHubIssueService(
            github_api_base=self.github_api_base
        )

    async def audit_website_and_sync_issues(
        self,
        target_url: str,
        *,
        max_pages: int = 6,
        max_issues: int = 6,
        create_github_issues: bool = True,
        dry_run: bool = False,
        github_repo: str | None = None,
        extra_labels: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Crawl public pages, generate issue candidates, and sync them to GitHub."""
        normalized_target = self._normalize_target_url(target_url)
        repo = (
            github_repo
            or os.getenv("MANIFEST_GITHUB_REPO")
            or os.getenv("GITHUB_REPOSITORY")
            or "Manifest-Startup/Manifest"
        )
        scanned_at = datetime.now(timezone.utc).isoformat()
        extra_labels_list = [label for label in (extra_labels or []) if label]

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "ManifestWebsiteIssueSync/1.0"},
        ) as client:
            urls = await self._discover_candidate_urls(
                client, normalized_target, max_pages=max_pages
            )
            pages = await self._crawl_pages(client, urls)
            heuristic_candidates = self._build_heuristic_candidates(pages)
            issue_candidates = await self._build_issue_candidates(
                normalized_target,
                pages,
                heuristic_candidates,
                max_issues=max_issues,
            )

            github_summary = {
                "repo": repo,
                "create_requested": bool(create_github_issues),
                "dry_run": bool(dry_run),
                "created_count": 0,
                "skipped_existing_count": 0,
                "created_issues": [],
                "skipped_issues": [],
            }

            if issue_candidates and create_github_issues:
                if dry_run:
                    github_summary["skipped_issues"] = [
                        {"title": candidate.title, "reason": "dry_run"}
                        for candidate in issue_candidates
                    ]
                else:
                    issue_drafts = [
                        GitHubIssueDraft(
                            title=candidate.title,
                            body=self._build_issue_body(
                                candidate, target_url=normalized_target, scanned_at=scanned_at
                            ),
                            labels=self._merge_labels(
                                [
                                    "website-audit",
                                    candidate.category,
                                    f"priority:{candidate.severity}",
                                    *candidate.labels,
                                ],
                                [],
                            ),
                        )
                        for candidate in issue_candidates
                    ]
                    try:
                        github_summary = await self.github_issue_service.create_issues(
                            client,
                            repo=repo,
                            issue_drafts=issue_drafts,
                            extra_labels=extra_labels_list,
                        )
                    except GitHubIssueConfigurationError as exc:
                        raise WebsiteIssueSyncConfigurationError(str(exc)) from exc

        return {
            "target_url": normalized_target,
            "repo": repo,
            "scanned_at": scanned_at,
            "pages_scanned": len(pages),
            "pages": [asdict(page) for page in pages],
            "issue_candidates": [candidate.to_dict() for candidate in issue_candidates],
            "github": github_summary,
        }

    def _normalize_target_url(self, target_url: str) -> str:
        raw = (target_url or "").strip()
        if not raw:
            raise ValueError("A target URL is required.")
        if not raw.startswith(("http://", "https://")):
            raw = f"https://{raw}"

        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Target URL must include a valid host.")

        cleaned = parsed._replace(fragment="", params="", query="").geturl().rstrip("/")
        return cleaned

    async def _discover_candidate_urls(
        self,
        client: httpx.AsyncClient,
        target_url: str,
        *,
        max_pages: int,
    ) -> list[str]:
        parsed_target = urlparse(target_url)
        same_origin = f"{parsed_target.scheme}://{parsed_target.netloc}"
        discovered: list[str] = [target_url]

        sitemap_urls = await self._discover_urls_from_sitemap(client, same_origin)
        for url in sitemap_urls:
            if self._should_include_url(url, same_origin) and url not in discovered:
                discovered.append(url)
                if len(discovered) >= max_pages:
                    return discovered[:max_pages]

        homepage_links = await self._discover_urls_from_homepage(client, target_url)
        for url in homepage_links:
            if self._should_include_url(url, same_origin) and url not in discovered:
                discovered.append(url)
                if len(discovered) >= max_pages:
                    break

        return discovered[:max_pages]

    async def _discover_urls_from_sitemap(
        self, client: httpx.AsyncClient, base_url: str
    ) -> list[str]:
        sitemap_url = urljoin(f"{base_url}/", "sitemap.xml")
        try:
            response = await client.get(sitemap_url)
            response.raise_for_status()
        except Exception as exc:
            logger.info("[WebsiteIssueSync] Sitemap fetch skipped for %s: %s", sitemap_url, exc)
            return []

        matches = re.findall(r"<loc>(.*?)</loc>", response.text, flags=re.IGNORECASE)
        return [match.strip() for match in matches if match.strip()]

    async def _discover_urls_from_homepage(
        self, client: httpx.AsyncClient, target_url: str
    ) -> list[str]:
        try:
            response = await client.get(target_url)
            response.raise_for_status()
        except Exception as exc:
            logger.info(
                "[WebsiteIssueSync] Homepage link discovery skipped for %s: %s", target_url, exc
            )
            return []

        return self._extract_internal_links(response.text, target_url)

    def _should_include_url(self, url: str, same_origin: str) -> bool:
        if not url.startswith(same_origin):
            return False
        parsed = urlparse(url)
        path = parsed.path or "/"
        if path.startswith("/api") or path.startswith("/graphql"):
            return False
        return not path.endswith((".xml", ".json", ".txt", ".pdf"))

    async def _crawl_pages(self, client: httpx.AsyncClient, urls: list[str]) -> list[CrawledPage]:
        return await asyncio.gather(*(self._crawl_page(client, url) for url in urls))

    async def _crawl_page(self, client: httpx.AsyncClient, page_url: str) -> CrawledPage:
        started_at = time.perf_counter()
        try:
            response = await client.get(page_url)
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            content_type = response.headers.get("content-type", "")

            if "text/html" not in content_type and not response.text.lstrip().startswith(
                "<!doctype html"
            ):
                return CrawledPage(
                    url=page_url,
                    status_code=response.status_code,
                    response_time_ms=elapsed_ms,
                    content_type=content_type,
                    html_size_bytes=len(response.content or b""),
                    title=None,
                    meta_description=None,
                    canonical_url=None,
                    h1_text=None,
                    text_excerpt="",
                    internal_links=[],
                    js_required_banner=False,
                    error=None,
                    html_signature=None,
                )

            title = self._extract_title(response.text)
            meta_description = self._extract_meta_description(response.text)
            canonical_url = self._extract_canonical_url(response.text)
            h1_text = self._extract_h1_text(response.text)
            text_excerpt = self._extract_text_excerpt(response.text)
            internal_links = self._extract_internal_links(response.text, page_url)
            normalized_html = re.sub(r"\s+", " ", response.text).strip().lower()
            html_signature = str(hash(normalized_html[:10000])) if normalized_html else None

            return CrawledPage(
                url=page_url,
                status_code=response.status_code,
                response_time_ms=elapsed_ms,
                content_type=content_type,
                html_size_bytes=len(response.content or b""),
                title=title,
                meta_description=meta_description,
                canonical_url=canonical_url,
                h1_text=h1_text,
                text_excerpt=text_excerpt,
                internal_links=internal_links,
                js_required_banner="enable javascript" in text_excerpt.lower(),
                error=None,
                html_signature=html_signature,
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            logger.warning("[WebsiteIssueSync] Crawl failed for %s: %s", page_url, exc)
            return CrawledPage(
                url=page_url,
                status_code=None,
                response_time_ms=elapsed_ms,
                content_type="",
                html_size_bytes=0,
                title=None,
                meta_description=None,
                canonical_url=None,
                h1_text=None,
                text_excerpt="",
                internal_links=[],
                js_required_banner=False,
                error=str(exc),
                html_signature=None,
            )

    def _extract_title(self, html: str) -> str | None:
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            return self._clean_text(soup.title.string if soup.title and soup.title.string else None)
        return self._clean_text(self._extract_with_regex(r"<title[^>]*>(.*?)</title>", html))

    def _extract_meta_description(self, html: str) -> str | None:
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            description_node = soup.find("meta", attrs={"name": "description"})
            return self._clean_text(description_node.get("content") if description_node else None)
        return self._clean_text(
            self._extract_with_regex(
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
                html,
            )
        )

    def _extract_canonical_url(self, html: str) -> str | None:
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            canonical_node = soup.find("link", rel=lambda value: value and "canonical" in value)
            return self._clean_text(canonical_node.get("href") if canonical_node else None)
        return self._clean_text(
            self._extract_with_regex(
                r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\'](.*?)["\']',
                html,
            )
        )

    def _extract_h1_text(self, html: str) -> str | None:
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            h1_node = soup.find("h1")
            return self._clean_text(h1_node.get_text(" ", strip=True) if h1_node else None)
        raw = self._extract_with_regex(r"<h1[^>]*>(.*?)</h1>", html)
        return self._clean_text(self._strip_tags(raw or ""))

    def _extract_text_excerpt(self, html: str) -> str:
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            body = soup.body or soup
            text = " ".join(part.strip() for part in body.stripped_strings if part.strip())
            return text[:1000]
        return self._strip_tags(html)[:1000]

    def _extract_internal_links(self, html: str, page_url: str) -> list[str]:
        parsed_page = urlparse(page_url)
        same_origin = f"{parsed_page.scheme}://{parsed_page.netloc}"
        links: list[str] = []
        seen = set()
        hrefs: list[str] = []
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            hrefs = [(anchor.get("href") or "").strip() for anchor in soup.select("a[href]")]
        else:
            hrefs = re.findall(r'<a[^>]+href=["\'](.*?)["\']', html, flags=re.IGNORECASE)

        for href in hrefs:
            if not href:
                continue
            absolute = urljoin(page_url, href)
            if absolute.startswith(same_origin) and absolute not in seen:
                seen.add(absolute)
                links.append(absolute)
        return links[:20]

    def _extract_with_regex(self, pattern: str, html: str) -> str | None:
        match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
        return match.group(1) if match else None

    def _strip_tags(self, html: str) -> str:
        without_scripts = re.sub(
            r"<script.*?>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL
        )
        without_styles = re.sub(
            r"<style.*?>.*?</style>", " ", without_scripts, flags=re.IGNORECASE | re.DOTALL
        )
        without_tags = re.sub(r"<[^>]+>", " ", without_styles)
        collapsed = re.sub(r"\s+", " ", without_tags).strip()
        return collapsed

    def _build_heuristic_candidates(self, pages: list[CrawledPage]) -> list[IssueCandidate]:
        candidates: list[IssueCandidate] = []
        signature_to_pages: dict[str, list[CrawledPage]] = {}

        for page in pages:
            if page.html_signature:
                signature_to_pages.setdefault(page.html_signature, []).append(page)

            if page.error:
                candidates.append(
                    IssueCandidate(
                        title=f"Audit crawler could not load {self._short_path(page.url)}",
                        category="bug",
                        severity="high",
                        page_url=page.url,
                        summary="The public page could not be fetched during the audit, which likely indicates an availability or routing problem.",
                        suggested_fix="Reproduce the failing request in production logs and confirm the route returns a successful HTML response for anonymous visitors.",
                        evidence=[page.error],
                        labels=self._base_labels("bug", "high"),
                    )
                )
                continue

            if page.status_code and page.status_code >= 400:
                candidates.append(
                    IssueCandidate(
                        title=f"Fix public route failure on {self._short_path(page.url)}",
                        category="bug",
                        severity="critical" if page.status_code >= 500 else "high",
                        page_url=page.url,
                        summary="A public Manifest page returned an error status during the audit.",
                        suggested_fix="Investigate the production route handler or deploy configuration and restore a successful response for anonymous visitors.",
                        evidence=[f"HTTP {page.status_code} for {page.url}"],
                        labels=self._base_labels(
                            "bug", "critical" if page.status_code >= 500 else "high"
                        ),
                    )
                )

            if not page.title:
                candidates.append(
                    IssueCandidate(
                        title=f"Add a descriptive HTML title for {self._short_path(page.url)}",
                        category="seo",
                        severity="medium",
                        page_url=page.url,
                        summary="This page does not expose a descriptive document title in the initial HTML response, which weakens SEO and browser clarity.",
                        suggested_fix="Render a route-specific `<title>` tag in the server-delivered HTML or via a reliable metadata pipeline.",
                        evidence=[f"No `<title>` detected for {page.url}"],
                        labels=self._base_labels("seo", "medium"),
                    )
                )

            if not page.meta_description:
                candidates.append(
                    IssueCandidate(
                        title=f"Add a meta description for {self._short_path(page.url)}",
                        category="seo",
                        severity="medium",
                        page_url=page.url,
                        summary="The page is missing a meta description, which makes search snippets and social previews less intentional.",
                        suggested_fix="Provide route-aware meta descriptions that explain the user value and expected next action.",
                        evidence=[f"No meta description detected for {page.url}"],
                        labels=self._base_labels("seo", "medium"),
                    )
                )

            if not page.h1_text:
                candidates.append(
                    IssueCandidate(
                        title=f"Expose a clear primary heading on {self._short_path(page.url)}",
                        category="accessibility",
                        severity="medium",
                        page_url=page.url,
                        summary="This route does not expose a primary heading in the HTML shell, making the page harder to parse for assistive tech and crawlers.",
                        suggested_fix="Ensure each public route renders one clear, route-specific `<h1>` near the top of the content hierarchy.",
                        evidence=[f"No `<h1>` detected for {page.url}"],
                        labels=self._base_labels("accessibility", "medium"),
                    )
                )

            if page.js_required_banner:
                candidates.append(
                    IssueCandidate(
                        title=f"Improve no-JavaScript and crawler resilience for {self._short_path(page.url)}",
                        category="ux",
                        severity="medium",
                        page_url=page.url,
                        summary="The initial HTML still shows a JavaScript-required message, which creates a brittle experience for crawlers and degraded browsers.",
                        suggested_fix="Ship richer server-rendered shell content or a more helpful progressive enhancement fallback for critical landing-page messaging.",
                        evidence=[page.text_excerpt[:180]],
                        labels=self._base_labels("ux", "medium"),
                    )
                )

        duplicate_shell_pages = [
            pages_for_signature
            for pages_for_signature in signature_to_pages.values()
            if len(pages_for_signature) > 1
        ]
        if duplicate_shell_pages:
            largest_group = max(duplicate_shell_pages, key=len)
            route_list = ", ".join(self._short_path(page.url) for page in largest_group[:4])
            candidates.append(
                IssueCandidate(
                    title="Different public routes expose the same pre-hydration shell",
                    category="seo",
                    severity="medium",
                    page_url=largest_group[0].url,
                    summary="Multiple public routes appear to deliver the same initial HTML shell, which can weaken SEO, previews, and route clarity before hydration completes.",
                    suggested_fix="Add route-specific metadata and critical above-the-fold content to the server-delivered shell for each major landing route.",
                    evidence=[f"Matching HTML shell detected for: {route_list}"],
                    labels=self._base_labels("seo", "medium"),
                )
            )

        return self._dedupe_candidates(candidates)

    async def _build_issue_candidates(
        self,
        target_url: str,
        pages: list[CrawledPage],
        heuristic_candidates: list[IssueCandidate],
        *,
        max_issues: int,
    ) -> list[IssueCandidate]:
        if not pages:
            return []

        if not self.router.is_available():
            logger.info(
                "[WebsiteIssueSync] AI unavailable, falling back to heuristic candidates only."
            )
            return self._rank_candidates(heuristic_candidates)[:max_issues]

        prompt_payload = {
            "target_url": target_url,
            "max_issues": max_issues,
            "pages": [asdict(page) for page in pages],
            "heuristic_candidates": [candidate.to_dict() for candidate in heuristic_candidates],
        }

        try:
            raw = self.router.chat_json(
                prompt=json.dumps(prompt_payload),
                model=self.model,
                system_prompt=self.ANALYSIS_PROMPT,
                temperature=0.2,
            )
            ai_candidates = self._normalize_ai_candidates(raw.get("issues", []))
            combined = self._dedupe_candidates([*ai_candidates, *heuristic_candidates])
            return self._rank_candidates(combined)[:max_issues]
        except Exception as exc:
            logger.warning("[WebsiteIssueSync] AI analysis failed, using heuristics only: %s", exc)
            return self._rank_candidates(heuristic_candidates)[:max_issues]

    def _normalize_ai_candidates(self, raw_issues: Any) -> list[IssueCandidate]:
        if not isinstance(raw_issues, list):
            return []

        candidates: list[IssueCandidate] = []
        for raw_issue in raw_issues:
            if not isinstance(raw_issue, dict):
                continue

            title = self._clean_text(raw_issue.get("title"))
            category = self._normalize_category(raw_issue.get("category"))
            severity = self._normalize_severity(raw_issue.get("severity"))
            page_url = self._clean_text(raw_issue.get("page_url")) or ""
            summary = self._clean_text(raw_issue.get("summary"))
            suggested_fix = self._clean_text(raw_issue.get("suggested_fix"))
            evidence = (
                raw_issue.get("evidence") if isinstance(raw_issue.get("evidence"), list) else []
            )
            labels = [
                self._normalize_label(label)
                for label in raw_issue.get("labels", [])
                if self._normalize_label(label)
            ]

            if not title or not summary or not suggested_fix or not page_url:
                continue

            candidates.append(
                IssueCandidate(
                    title=title[:120],
                    category=category,
                    severity=severity,
                    page_url=page_url,
                    summary=summary,
                    suggested_fix=suggested_fix,
                    evidence=[
                        self._clean_text(item) or "" for item in evidence if self._clean_text(item)
                    ],
                    labels=self._base_labels(category, severity, labels),
                )
            )

        return candidates

    def _build_issue_body(
        self, candidate: IssueCandidate, *, target_url: str, scanned_at: str
    ) -> str:
        evidence_lines = (
            "\n".join(f"- {item}" for item in candidate.evidence)
            if candidate.evidence
            else "- No additional evidence captured."
        )
        return (
            f"## Summary\n{candidate.summary}\n\n"
            f"## Page\n- {candidate.page_url}\n\n"
            f"## Evidence\n{evidence_lines}\n\n"
            f"## Suggested Fix\n{candidate.suggested_fix}\n\n"
            "## Audit Metadata\n"
            f"- Category: {candidate.category}\n"
            f"- Severity: {candidate.severity}\n"
            f"- Target URL: {target_url}\n"
            f"- Scanned At: {scanned_at}\n"
            "- Generated By: Manifest website issue sync\n"
        )

    def _dedupe_candidates(self, candidates: list[IssueCandidate]) -> list[IssueCandidate]:
        deduped: dict[str, IssueCandidate] = {}
        for candidate in candidates:
            key = f"{self._normalize_title_key(candidate.title)}::{candidate.page_url}"
            existing = deduped.get(key)
            if existing is None:
                deduped[key] = candidate
                continue

            if SEVERITY_ORDER[candidate.severity] < SEVERITY_ORDER[existing.severity]:
                deduped[key] = candidate
        return list(deduped.values())

    def _rank_candidates(self, candidates: list[IssueCandidate]) -> list[IssueCandidate]:
        return sorted(
            candidates,
            key=lambda candidate: (
                SEVERITY_ORDER.get(candidate.severity, 99),
                candidate.category,
                candidate.title.lower(),
            ),
        )

    def _normalize_category(self, category: Any) -> str:
        normalized = self._normalize_label(category) or "ux"
        return normalized if normalized in ALLOWED_CATEGORIES else "ux"

    def _normalize_severity(self, severity: Any) -> str:
        normalized = self._normalize_label(severity) or "medium"
        return normalized if normalized in SEVERITY_ORDER else "medium"

    def _base_labels(
        self, category: str, severity: str, extra: list[str] | None = None
    ) -> list[str]:
        labels = [
            "website-audit",
            self._normalize_category(category),
            f"priority:{self._normalize_severity(severity)}",
        ]
        labels.extend(extra or [])
        return self._merge_labels(labels)

    def _merge_labels(
        self, labels: Iterable[str], extra_labels: Iterable[str] | None = None
    ) -> list[str]:
        merged = []
        seen = set()
        for label in [*labels, *(extra_labels or [])]:
            normalized = self._normalize_label(label)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
        return merged

    def _normalize_label(self, value: Any) -> str:
        cleaned = self._clean_text(value)
        if not cleaned:
            return ""
        return re.sub(r"\s+", "-", cleaned.strip().lower())[:50]

    def _normalize_title_key(self, title: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()

    def _short_path(self, url: str) -> str:
        parsed = urlparse(url)
        return parsed.path or "/"

    def _clean_text(self, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = re.sub(r"\s+", " ", str(value)).strip()
        return cleaned or None


website_issue_sync_service = WebsiteIssueSyncService()
