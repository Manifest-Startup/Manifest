"""People's feedback, bugs and ideas about Manifest, filed as GitHub issues without duplicates.

Anyone signed in can say "the pitch deck export is broken" to the voice agent (or any agent, the
CLI or the app); this module turns it into one issue in Manifest's own repository, using the
server's ``MANIFEST_GITHUB_TOKEN`` (never the person's GitHub connection).

De-duplication, in order:
1. ``duplicate_of`` given (the agent picked an existing issue) → add this person to it.
2. A close match among open issues (title similarity ≥ ``STRONG_MATCH``) → add this person to it.
3. Partial matches (a shared meaningful word) and no ``force_new`` → return them without filing, so the
   agent, which understands paraphrases, can pick one or say it's new.
4. Otherwise → a new issue.

"Adding a person" keeps a hidden list of reporter hashes in the issue body (so the same person
counts once), updates a visible "Reported by N people" line, and posts their wording as a comment.
The repository is public: details are redacted (emails, phone numbers, long numbers, key-like
strings) and nothing that identifies the person is posted.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from app.services.integrations.github_issues import GitHubIssueService, github_token
from app.services.shared.rate_limit import rate_limit_service
from app.utils.logger import logger

DEFAULT_REPO = "Manifest-Startup/Manifest"
KIND_LABELS = {
    "bug": "bug",
    "enhancement": "enhancement",
    "improvement": "enhancement",
    "feedback": "product-feedback",
}
SOURCES = {"voice", "app", "agent", "cli"}
FEEDBACK_LABEL = "user-feedback"
STRONG_MATCH = 0.72
# Anything sharing a meaningful word and scoring above this goes back to the agent to judge:
# word matching can't tell paraphrases apart ("voice replies take long" / "voice is slow").
POSSIBLE_MATCH = 0.12
MAX_TITLE = 120
MAX_DETAILS = 4000
RATE_LIMIT_PER_HOUR = 10

MARKER = re.compile(r"<!-- manifest-feedback (\{.*?\}) -->", re.S)
COUNT_LINE = re.compile(r"^> \*\*Reported by \d+ (?:person|people)\*\*.*$", re.M)
STOPWORDS = frozenset(
    "a an the and or but to of in on for with is are was be it this that i my me we you when "
    "can cant cannot not no should would could please manifest app doesnt dont does do have has "
    "there their them want wish like just its at as from by so if into".split()
)
REDACTIONS = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"\b(?:sk|pk|ghp|gho|github_pat|xox[abp])[-_][A-Za-z0-9_-]{8,}\b"), "[secret]"),
    (re.compile(r"\+?\d[\d\s().-]{7,}\d"), "[number]"),
)


class FeedbackError(RuntimeError):
    """A feedback report that can't be filed; the message is safe to show the person."""


@dataclass
class FeedbackResult:
    status: str  # created | added | already_reported | possible_duplicates
    issue_number: int | None = None
    issue_url: str | None = None
    issue_title: str | None = None
    reporters: int = 0
    candidates: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""


def feedback_repo() -> str:
    return (
        os.getenv("MANIFEST_FEEDBACK_REPO")
        or os.getenv("MANIFEST_GITHUB_REPO")
        or os.getenv("GITHUB_REPOSITORY")
        or DEFAULT_REPO
    )


def redact(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text.strip()


def reporter_hash(user_id: str) -> str:
    """Stable, non-reversible id so one person counts once (user ids are random UUIDs)."""
    return hashlib.sha256(f"manifest-feedback:{user_id}".encode()).hexdigest()[:16]


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower().replace("'", ""))
    out = set()
    for word in words:
        if word in STOPWORDS or len(word) < 2:
            continue
        for suffix in ("ing", "ed", "es", "s"):
            if len(word) > len(suffix) + 2 and word.endswith(suffix):
                word = word[: -len(suffix)]
                break
        out.add(word)
    return out


def similarity(a: str, b: str) -> float:
    """0..1 title similarity: word overlap (light stemming) or character similarity."""
    ta, tb = _tokens(a), _tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    # Overlap relative to the shorter title catches "voice slow" vs "voice is slow on mobile".
    containment = len(ta & tb) / min(len(ta), len(tb)) if ta and tb else 0.0
    ratio = difflib.SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    return round(max(jaccard, 0.85 * containment if len(ta & tb) >= 2 else 0.0, ratio * 0.9), 3)


def read_marker(body: str) -> dict[str, Any]:
    match = MARKER.search(body or "")
    if not match:
        return {"reporters": []}
    try:
        data = json.loads(match.group(1))
        return data if isinstance(data.get("reporters"), list) else {"reporters": []}
    except (ValueError, AttributeError):
        return {"reporters": []}


def write_marker(body: str, reporters: list[str]) -> str:
    """Return ``body`` with the reporter list and the visible count line updated."""
    count = len(reporters)
    line = (
        f"> **Reported by {count} {'person' if count == 1 else 'people'}** through Manifest "
        "(voice, app or agents). Each new report is added as a comment."
    )
    marker = f"<!-- manifest-feedback {json.dumps({'reporters': reporters})} -->"
    body = MARKER.sub("", body or "").rstrip()
    body = COUNT_LINE.sub(line, body) if COUNT_LINE.search(body) else f"{body}\n\n{line}".strip()
    return f"{body}\n\n{marker}"


class UserFeedbackService:
    def __init__(self, *, api_base: str = "https://api.github.com"):
        self.api_base = api_base.rstrip("/")
        self.issues = GitHubIssueService(github_api_base=api_base)

    async def report(
        self,
        *,
        user_id: str,
        kind: str,
        title: str,
        details: str = "",
        source: str = "agent",
        duplicate_of: int | None = None,
        force_new: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> FeedbackResult:
        kind = (kind or "feedback").strip().lower()
        if kind not in KIND_LABELS:
            raise FeedbackError("Kind must be one of: bug, feedback, enhancement, improvement.")
        source = source if source in SOURCES else "agent"
        title = redact(" ".join((title or "").split()))[:MAX_TITLE]
        details = redact(details or "")[:MAX_DETAILS]
        if len(title) < 4:
            raise FeedbackError("Give the feedback a short title (a few words).")
        token = github_token()
        if not token:
            raise FeedbackError(
                "Feedback filing isn't set up on this server yet (MANIFEST_GITHUB_TOKEN)."
            )
        if not rate_limit_service.allow(
            f"feedback:{user_id}", limit=RATE_LIMIT_PER_HOUR, window_seconds=3600
        ):
            raise FeedbackError("That's a lot of reports in an hour; please try again later.")

        repo = feedback_repo()
        headers = self.issues.headers(token)
        me = reporter_hash(user_id)
        own_client = client is None
        client = client or httpx.AsyncClient(timeout=20.0)
        try:
            if duplicate_of:
                issue = await self._get_open_issue(client, repo, headers, int(duplicate_of))
                return await self._add_reporter(client, repo, headers, issue, me, details, source)

            candidates = await self._candidates(client, repo, headers, title)
            best = candidates[0] if candidates else None
            if best and best["score"] >= STRONG_MATCH and not force_new:
                issue = best["issue"]
                return await self._add_reporter(client, repo, headers, issue, me, details, source)
            words = _tokens(title)
            possible = [
                c
                for c in candidates
                if c["score"] >= POSSIBLE_MATCH and words & _tokens(c["issue"].get("title", ""))
            ]
            if possible and not force_new:
                return FeedbackResult(
                    status="possible_duplicates",
                    candidates=[
                        {
                            "number": c["issue"]["number"],
                            "title": c["issue"]["title"],
                            "url": c["issue"]["html_url"],
                            "score": c["score"],
                        }
                        for c in possible[:5]
                    ],
                    message=(
                        "Similar open issues exist. If one is the same thing, call again with "
                        "duplicate_of set to its number; if it's different, call again with "
                        "force_new true."
                    ),
                )
            return await self._create(client, repo, headers, kind, title, details, source, me)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "[user_feedback] GitHub error",
                extra={"http.response.status_code": exc.response.status_code},
            )
            raise FeedbackError("GitHub didn't accept the report; please try again.") from exc
        finally:
            if own_client:
                await client.aclose()

    async def _get_open_issue(self, client, repo, headers, number: int) -> dict[str, Any]:
        response = await client.get(
            f"{self.api_base}/repos/{repo}/issues/{number}", headers=headers
        )
        if response.status_code == 404:
            raise FeedbackError(f"There's no issue #{number}.")
        response.raise_for_status()
        issue = response.json()
        if issue.get("pull_request") or issue.get("state") != "open":
            raise FeedbackError(f"#{number} isn't an open issue; file it as new instead.")
        return issue

    async def _candidates(self, client, repo, headers, title: str) -> list[dict[str, Any]]:
        """Open issues ranked by title similarity: a keyword search plus recent feedback issues."""
        seen: dict[int, dict[str, Any]] = {}
        words = sorted(_tokens(title), key=len, reverse=True)[:6]
        if words:
            response = await client.get(
                f"{self.api_base}/search/issues",
                headers=headers,
                params={
                    "q": f"repo:{repo} is:issue is:open {' '.join(words)}",
                    "per_page": 20,
                },
            )
            if response.status_code == 200:
                for issue in response.json().get("items", []):
                    seen[issue["number"]] = issue
            # Any-word fallback: search ANDs words, so a paraphrase can miss.
            response = await client.get(
                f"{self.api_base}/search/issues",
                headers=headers,
                params={
                    "q": f"repo:{repo} is:issue is:open {' OR '.join(words[:5])}",
                    "per_page": 30,
                },
            )
            if response.status_code == 200:
                for issue in response.json().get("items", []):
                    seen.setdefault(issue["number"], issue)
        response = await client.get(
            f"{self.api_base}/repos/{repo}/issues",
            headers=headers,
            params={"state": "open", "labels": FEEDBACK_LABEL, "per_page": 100},
        )
        if response.status_code == 200:
            for issue in response.json():
                if not issue.get("pull_request"):
                    seen.setdefault(issue["number"], issue)
        ranked = [
            {"issue": issue, "score": similarity(title, issue.get("title", ""))}
            for issue in seen.values()
        ]
        return sorted(ranked, key=lambda c: c["score"], reverse=True)

    async def _create(self, client, repo, headers, kind, title, details, source, me):
        labels = [KIND_LABELS[kind], FEEDBACK_LABEL, f"source:{source}"]
        await self.issues.ensure_labels(client, repo, headers=headers, labels=labels)
        body = (
            f"{details or '_No further details given._'}\n\n---\n"
            f"_Reported through Manifest ({source}). Kind: {kind}._"
        )
        response = await client.post(
            f"{self.api_base}/repos/{repo}/issues",
            headers=headers,
            json={"title": title, "body": write_marker(body, [me]), "labels": labels},
        )
        response.raise_for_status()
        issue = response.json()
        return FeedbackResult(
            status="created",
            issue_number=issue["number"],
            issue_url=issue["html_url"],
            issue_title=issue["title"],
            reporters=1,
            message="Filed as a new issue.",
        )

    async def _add_reporter(self, client, repo, headers, issue, me, details, source):
        reporters = [r for r in read_marker(issue.get("body") or "")["reporters"] if r]
        if not reporters:
            # Issues filed before this feature (or by hand) count their author as one person.
            reporters = ["original"]
        base = FeedbackResult(
            status="already_reported",
            issue_number=issue["number"],
            issue_url=issue["html_url"],
            issue_title=issue["title"],
            reporters=len(reporters),
        )
        if me in reporters:
            base.message = "This person already reported this issue; nothing changed."
            return base
        reporters.append(me)
        count = len(reporters)
        response = await client.patch(
            f"{self.api_base}/repos/{repo}/issues/{issue['number']}",
            headers=headers,
            json={"body": write_marker(issue.get("body") or "", reporters)},
        )
        response.raise_for_status()
        comment = (
            f"**Another person reported this** through Manifest ({source}); {count} people so far."
        )
        if details:
            quoted = "\n".join(f"> {line}" for line in details.splitlines())
            comment += f"\n\n{quoted}"
        response = await client.post(
            f"{self.api_base}/repos/{repo}/issues/{issue['number']}/comments",
            headers=headers,
            json={"body": comment},
        )
        response.raise_for_status()
        base.status, base.reporters = "added", count
        base.message = f"Added to the existing issue; {count} people have reported it."
        return base


user_feedback_service = UserFeedbackService()
