"""Create a private GitHub repository from a Manifest idea (voice / integrations flow)."""

from __future__ import annotations

import re
from html import unescape
from typing import Any

from app.services.integrations.github_account import load_github_token
from app.services.integrations.github_api import (
    NOT_CONNECTED,
    GitHubError,
    client_for,
    create_repo,
)
from app.utils.logger import logger


def _plain_text_from_html(html: str, max_len: int = 4000) -> str:
    if not html:
        return ""
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def _fetch_owned_idea(db, user_id: str, idea_id: str) -> dict[str, Any] | None:
    try:
        res = (
            db.table("ideas")
            .select("idea_id, user_id, title, description")
            .eq("idea_id", idea_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("[GitHubBootstrap] idea load failed: %s", exc)
        return None
    return res.data if res.data else None


def _validate_repo_name(name: str) -> bool:
    if not name or len(name) > 100:
        return False
    return bool(re.match(r"^[A-Za-z0-9._-]+$", name))


def idea_readme(db, user_id: str, idea_id: str) -> str | None:
    """README text seeded from an idea the person owns, or None when it isn't theirs."""
    idea = _fetch_owned_idea(db, user_id, idea_id)
    if not idea:
        return None
    title = (idea.get("title") or "Manifest idea").strip()
    body_text = _plain_text_from_html(idea.get("description") or "")
    return f"# {title}\n\n{body_text}\n" if body_text else f"# {title}\n\n_Seeded from Manifest._\n"


def create_private_repo_for_idea(
    db,
    user_id: str,
    idea_id: str,
    repo_name: str,
) -> tuple[str | None, str | None, str | None]:
    """Create a private repository seeded from an idea.

    Returns (html_url, error_detail, error_code); error_code is 'validation',
    'github_auth', 'not_found', 'upstream' or GitHub's HTTP status.
    """
    if not _validate_repo_name(repo_name):
        return (
            None,
            "Repository name must be 1-100 characters: letters, numbers, dots, hyphens, underscores.",
            "validation",
        )
    if not load_github_token(user_id):
        return None, NOT_CONNECTED, "github_auth"

    readme = idea_readme(db, user_id, idea_id)
    if readme is None:
        return None, "Idea not found or you do not have access.", "not_found"
    title = readme.splitlines()[0].lstrip("# ").strip()

    try:
        with client_for(user_id) as gh:
            repo = create_repo(
                gh,
                name=repo_name,
                description=f"Manifest idea: {title}",
                private=True,
                readme=readme,
            )
    except GitHubError as exc:
        logger.warning("[GitHubBootstrap] create repo failed status=%s", exc.status)
        return None, str(exc), str(exc.status) if exc.status else "upstream"
    return repo["html_url"], None, None
