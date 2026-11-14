"""Create a private GitHub repository from a Manifest idea (voice / integrations flow)."""

from __future__ import annotations

import base64
import re
from html import unescape
from typing import Any

import httpx
from app.utils.logger import logger

_GITHUB_API = "https://api.github.com"
_PLACEHOLDER_TOKENS = frozenset({"", "***", "null", "none"})


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


def _load_github_token(db, user_id: str) -> str | None:
    try:
        res = (
            db.table("integrations")
            .select("access_token")
            .eq("user_id", user_id)
            .eq("service_id", "github")
            .limit(1)
            .execute()
        )
    except Exception as exc:  # pragma: no cover - network/db
        logger.warning("[GitHubBootstrap] integration lookup failed: %s", exc)
        return None

    rows = res.data or []
    if not rows:
        return None
    token = rows[0].get("access_token")
    if not token or not isinstance(token, str):
        return None
    cleaned = token.strip()
    if cleaned.lower() in _PLACEHOLDER_TOKENS or cleaned == "***":
        return None
    return cleaned


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


def create_private_repo_for_idea(
    db,
    user_id: str,
    idea_id: str,
    repo_name: str,
    timeout: float = 30.0,
) -> tuple[str | None, str | None, str | None]:
    """
    Returns (html_url, error_detail, error_code) where error_code is an HTTP status or 'validation'.
    On success, error fields are None.
    """
    if not _validate_repo_name(repo_name):
        return (
            None,
            "Repository name must be 1-100 characters: letters, numbers, dots, hyphens, underscores.",
            "validation",
        )

    token = _load_github_token(db, user_id)
    if not token:
        return None, "Connect GitHub under Account → integrations, then try again.", "github_auth"

    idea = _fetch_owned_idea(db, user_id, idea_id)
    if not idea:
        return None, "Idea not found or you do not have access.", "not_found"

    title = (idea.get("title") or "Manifest idea").strip()
    body_text = _plain_text_from_html(idea.get("description") or "")
    readme_body = (
        f"# {title}\n\n{body_text}\n" if body_text else f"# {title}\n\n_Seeded from Manifest._\n"
    )

    payload = {
        "name": repo_name,
        "private": True,
        "description": f"Manifest idea: {title}"[:350],
        "auto_init": False,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            create_resp = client.post(f"{_GITHUB_API}/user/repos", json=payload, headers=headers)
            if create_resp.status_code not in (200, 201):
                detail = "GitHub rejected the request."
                try:
                    err_json = create_resp.json()
                    if isinstance(err_json, dict) and err_json.get("message"):
                        detail = str(err_json["message"])
                except Exception:
                    pass
                logger.warning(
                    "[GitHubBootstrap] create repo failed status=%s body=%s",
                    create_resp.status_code,
                    create_resp.text[:500],
                )
                return None, detail, str(create_resp.status_code)

            repo_data = create_resp.json()
            html_url = repo_data.get("html_url") if isinstance(repo_data, dict) else None
            full_name = repo_data.get("full_name") if isinstance(repo_data, dict) else None
            if not full_name:
                return html_url, None, None

            readme_resp = client.put(
                f"{_GITHUB_API}/repos/{full_name}/contents/README.md",
                headers=headers,
                json={
                    "message": "Seed README from Manifest",
                    "content": base64.b64encode(readme_body.encode("utf-8")).decode("ascii"),
                },
            )
            if readme_resp.status_code not in (200, 201):
                logger.warning(
                    "[GitHubBootstrap] README update failed status=%s — repo may be empty",
                    readme_resp.status_code,
                )

            return html_url, None, None
    except httpx.HTTPError as exc:
        logger.error("[GitHubBootstrap] HTTP error: %s", exc)
        return None, "Could not reach GitHub. Try again later.", "upstream"
