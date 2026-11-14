"""Shared GitHub issue creation helpers for internal Manifest automation."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx
from app.services.integrations.github_projects import maybe_add_created_issues_to_project

LABEL_COLORS = {
    "website-audit": "0e8a16",
    "survey-feedback": "1d4ed8",
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
    "research": "0e8a16",
    "product-feedback": "1d76db",
    "theme:trust": "5319e7",
    "theme:onboarding": "fbca04",
    "theme:research": "1d76db",
    "theme:documents": "a2eeef",
    "theme:collaboration": "c5def5",
    "theme:discovery": "bfdadc",
    "theme:performance": "f9d0c4",
    "theme:marketability": "0e8a16",
    "theme:feasibility": "bfe5bf",
    "production-signal": "d73a4a",
    "severity:p0": "b60205",
    "severity:p1": "d93f0b",
    "severity:p2": "fbca04",
}


class GitHubIssueConfigurationError(RuntimeError):
    """Raised when GitHub issue sync is requested without required credentials."""


@dataclass
class GitHubIssueDraft:
    """Minimal GitHub issue payload used by internal automations."""

    title: str
    body: str
    labels: list[str]


class GitHubIssueService:
    """Create GitHub issues with de-duplication and label bootstrapping."""

    def __init__(self, *, github_api_base: str = "https://api.github.com"):
        self.github_api_base = github_api_base.rstrip("/")

    async def create_issues(
        self,
        client: httpx.AsyncClient,
        *,
        repo: str,
        issue_drafts: Iterable[GitHubIssueDraft],
        extra_labels: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        github_token = os.getenv("MANIFEST_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise GitHubIssueConfigurationError(
                "GitHub issue sync requires MANIFEST_GITHUB_TOKEN or GITHUB_TOKEN."
            )

        drafts = list(issue_drafts)
        extra_labels_list = [label for label in (extra_labels or []) if label]

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        existing_titles = await self._fetch_existing_issue_titles(client, repo, headers=headers)
        all_labels = set()
        for draft in drafts:
            all_labels.update(self._merge_labels(draft.labels, extra_labels_list))
        await self._ensure_labels(client, repo, headers=headers, labels=sorted(all_labels))

        created_issues = []
        skipped_issues = []
        created_title_keys = set()

        for draft in drafts:
            title_key = self._normalize_title_key(draft.title)
            if title_key in existing_titles or title_key in created_title_keys:
                skipped_issues.append({"title": draft.title, "reason": "existing_open_issue"})
                continue

            labels = self._merge_labels(draft.labels, extra_labels_list)
            payload = {"title": draft.title, "body": draft.body, "labels": labels}
            response = await client.post(
                f"{self.github_api_base}/repos/{repo}/issues", json=payload, headers=headers
            )
            response.raise_for_status()
            issue = response.json()
            created_issues.append(
                {
                    "title": draft.title,
                    "number": issue.get("number"),
                    "url": issue.get("html_url"),
                    "node_id": issue.get("node_id"),
                }
            )
            created_title_keys.add(title_key)

        if created_issues:
            await maybe_add_created_issues_to_project(client, created_issues)

        return {
            "repo": repo,
            "create_requested": True,
            "dry_run": False,
            "created_count": len(created_issues),
            "skipped_existing_count": len(skipped_issues),
            "created_issues": created_issues,
            "skipped_issues": skipped_issues,
        }

    async def _fetch_existing_issue_titles(
        self,
        client: httpx.AsyncClient,
        repo: str,
        *,
        headers: dict[str, str],
    ) -> set[str]:
        response = await client.get(
            f"{self.github_api_base}/repos/{repo}/issues",
            headers=headers,
            params={"state": "open", "per_page": 100},
        )
        response.raise_for_status()
        issues = response.json()
        return {
            self._normalize_title_key(issue.get("title", ""))
            for issue in issues
            if not issue.get("pull_request")
        }

    async def _ensure_labels(
        self,
        client: httpx.AsyncClient,
        repo: str,
        *,
        headers: dict[str, str],
        labels: list[str],
    ) -> None:
        existing_response = await client.get(
            f"{self.github_api_base}/repos/{repo}/labels",
            headers=headers,
            params={"per_page": 100},
        )
        existing_response.raise_for_status()
        existing = {
            (label.get("name") or "").strip().lower()
            for label in existing_response.json()
            if label.get("name")
        }

        for label_name in labels:
            normalized = self._normalize_label(label_name)
            if not normalized or normalized in existing:
                continue

            create_response = await client.post(
                f"{self.github_api_base}/repos/{repo}/labels",
                headers=headers,
                json={
                    "name": label_name,
                    "color": LABEL_COLORS.get(normalized, "cfd3d7"),
                    "description": f"Created by Manifest internal automation for {normalized}.",
                },
            )

            if create_response.status_code not in (200, 201, 422):
                create_response.raise_for_status()

    def _merge_labels(self, labels: Iterable[str], extra_labels: Iterable[str]) -> list[str]:
        merged: list[str] = []
        seen = set()
        for raw_label in [*(labels or []), *(extra_labels or [])]:
            normalized = self._normalize_label(raw_label)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
        return merged

    def _normalize_label(self, label: str | None) -> str:
        return " ".join((label or "").strip().lower().split())

    def _normalize_title_key(self, title: str | None) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", (title or "").lower())
        return " ".join(cleaned.split())
