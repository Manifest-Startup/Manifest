"""Deduped production signals → GitHub issues (threshold per time window)."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from app.services.integrations.github_issues import (
    GitHubIssueConfigurationError,
    GitHubIssueDraft,
    GitHubIssueService,
)
from app.utils.logger import logger

ISSUE_EVENT_ALLOWLIST = frozenset(
    {
        "client_error_boundary",
        "graphql_mutation_failed",
        "checkout_failed",
        "voice_session_aborted",
        "api_5xx_spike",
    }
)

_SANITIZE = re.compile(r"\s+")


def _window_start_utc(now: datetime, *, window_seconds: int) -> datetime:
    ts = int(now.timestamp())
    bucket = (ts // window_seconds) * window_seconds
    return datetime.fromtimestamp(bucket, tz=timezone.utc)


def _fingerprint(event_name: str, route: str | None, error_code: str | None) -> str:
    parts = [
        (event_name or "unknown").strip().lower(),
        (route or "-").strip()[:200],
        (error_code or "-").strip()[:80],
    ]
    raw = ":".join(parts)
    return raw[:500]


def _redact_sample(text: str | None, *, max_len: int = 180) -> str:
    if not text:
        return ""
    cleaned = _SANITIZE.sub(" ", str(text)).strip()
    if "@" in cleaned:
        cleaned = re.sub(r"\S+@\S+", "[redacted-email]", cleaned)
    return cleaned[:max_len]


def _severity_rank(severity: str) -> int:
    return {"info": 0, "warn": 1, "error": 2, "critical": 3}.get(
        (severity or "").lower().strip(), 0
    )


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class ProductionSignalService:
    def __init__(self, *, github_issue_service: GitHubIssueService | None = None):
        self.github_issue_service = github_issue_service or GitHubIssueService()

    def _window_seconds(self) -> int:
        raw = os.getenv("PRODUCTION_SIGNAL_WINDOW_SECONDS", "900")
        try:
            return max(60, min(int(raw), 86400))
        except ValueError:
            return 900

    def _threshold(self) -> int:
        raw = os.getenv("PRODUCTION_SIGNAL_THRESHOLD", "5")
        try:
            return max(1, min(int(raw), 10_000))
        except ValueError:
            return 5

    def _eligible_for_github(self, *, event_name: str, severity: str) -> bool:
        if _severity_rank(severity) >= 3:
            return True
        return bool(event_name.strip() in ISSUE_EVENT_ALLOWLIST and _severity_rank(severity) >= 2)

    def ingest(
        self,
        db,
        *,
        event_name: str,
        route: str | None,
        severity: str,
        error_code: str | None = None,
        session_id: str | None = None,
        sample: str | None = None,
    ) -> dict[str, Any]:
        """Record a signal and update rolling window counters (no GitHub I/O)."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        window_seconds = self._window_seconds()
        bucket = _window_start_utc(now, window_seconds=window_seconds)
        bucket_iso = bucket.isoformat()
        fp = _fingerprint(event_name, route, error_code)

        rank = _severity_rank(severity)
        if rank == 0:
            return {
                "accepted": True,
                "fingerprint": fp,
                "window_start": bucket_iso,
                "event_count": 0,
                "github_issue_created": False,
                "skipped_reason": "info_severity_not_counted",
            }

        response = (
            db.table("production_signal_state").select("*").eq("fingerprint", fp).limit(1).execute()
        )
        rows = response.data or []
        row = rows[0] if rows else None
        sample_text = _redact_sample(sample)

        if row:
            prev_start = _parse_ts(row.get("window_start"))
            if prev_start and prev_start < bucket:
                event_count = 1
                db.table("production_signal_state").update(
                    {
                        "window_start": bucket_iso,
                        "event_count": event_count,
                        "last_issue_window_start": None,
                        "last_sample": sample_text or row.get("last_sample"),
                        "updated_at": now_iso,
                    }
                ).eq("fingerprint", fp).execute()
                last_issue_window = None
                gh_num = row.get("github_issue_number")
            else:
                event_count = int(row.get("event_count") or 0) + 1
                db.table("production_signal_state").update(
                    {
                        "event_count": event_count,
                        "last_sample": sample_text or row.get("last_sample"),
                        "updated_at": now_iso,
                    }
                ).eq("fingerprint", fp).execute()
                last_issue_window = row.get("last_issue_window_start")
                gh_num = row.get("github_issue_number")
        else:
            event_count = 1
            db.table("production_signal_state").insert(
                {
                    "fingerprint": fp,
                    "window_start": bucket_iso,
                    "event_count": event_count,
                    "github_issue_number": None,
                    "github_repo": None,
                    "last_issue_window_start": None,
                    "last_sample": sample_text or None,
                    "updated_at": now_iso,
                }
            ).execute()
            last_issue_window = None
            gh_num = None

        should_try_github = (
            self._eligible_for_github(event_name=event_name, severity=severity)
            and event_count >= self._threshold()
            and last_issue_window != bucket_iso
        )

        return {
            "accepted": True,
            "fingerprint": fp,
            "window_start": bucket_iso,
            "event_count": event_count,
            "github_issue_created": False,
            "github_eligible": should_try_github,
            "github_issue_number": gh_num,
            "session_hint": (session_id or "")[:64] or None,
        }

    async def ingest_and_maybe_open_github(
        self,
        db,
        *,
        event_name: str,
        route: str | None,
        severity: str,
        error_code: str | None = None,
        session_id: str | None = None,
        sample: str | None = None,
        create_github_issue: bool = True,
    ) -> dict[str, Any]:
        """Record signal; create a deduped GitHub issue when threshold met."""
        snapshot = self.ingest(
            db,
            event_name=event_name,
            route=route,
            severity=severity,
            error_code=error_code,
            session_id=session_id,
            sample=sample,
        )
        if not snapshot.get("github_eligible") or not create_github_issue:
            return snapshot

        fp = snapshot["fingerprint"]
        repo = (
            os.getenv("MANIFEST_GITHUB_REPO")
            or os.getenv("GITHUB_REPOSITORY")
            or "Manifest-Startup/Manifest"
        )
        sev_label = "severity:p2"
        if _severity_rank(severity) >= 3:
            sev_label = "severity:p0"
        elif _severity_rank(severity) >= 2:
            sev_label = "severity:p1"

        title = f"[production-signal] {event_name} — {route or 'unknown route'}"
        body = (
            "## Production signal (aggregated)\n\n"
            f"- **Fingerprint:** `{fp}`\n"
            f"- **Window start (UTC):** {snapshot['window_start']}\n"
            f"- **Events in window:** {snapshot['event_count']}\n"
            f"- **Severity:** {severity}\n"
            f"- **Error code:** {error_code or '—'}\n"
            f"- **Sample (redacted):** {_redact_sample(sample) or '—'}\n\n"
            "_Issue opened by Manifest production-signal automation. "
            "Do not paste PII into issue comments._\n"
        )
        draft = GitHubIssueDraft(
            title=title[:240],
            body=body,
            labels=["production-signal", sev_label, "bug"],
        )

        try:
            async with httpx.AsyncClient(
                timeout=25.0, headers={"User-Agent": "ManifestProductionSignal/1.0"}
            ) as client:
                gh = await self.github_issue_service.create_issues(
                    client,
                    repo=repo,
                    issue_drafts=[draft],
                    extra_labels=[],
                )
                created: list[dict[str, Any]] = gh.get("created_issues") or []
                if not created:
                    snapshot["skipped_reason"] = "github_deduped_or_failed"
                    return snapshot

                number = created[0].get("number")
                db.table("production_signal_state").update(
                    {
                        "github_issue_number": number,
                        "github_repo": repo,
                        "last_issue_window_start": snapshot["window_start"],
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("fingerprint", fp).execute()

                snapshot["github_issue_created"] = True
                snapshot["github_issue_number"] = number
                snapshot["github_issue_url"] = created[0].get("url")
        except GitHubIssueConfigurationError as exc:
            logger.warning("[ProductionSignal] GitHub not configured: %s", exc)
            snapshot["github_error"] = str(exc)

        return snapshot


production_signal_service = ProductionSignalService()
