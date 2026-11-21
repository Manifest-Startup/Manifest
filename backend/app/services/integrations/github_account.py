"""A person's own GitHub connection: verify, store (always encrypted) and load it.

GitHub connects two ways, and both end here:

* **Sign in with GitHub** (OAuth app, when ``GITHUB_CLIENT_ID``/``SECRET`` are set):
  ``/auth/github/callback`` hands the token to :func:`save_github_token`.
* **A personal access token** pasted in Account → Integrations, or sent by
  ``manifest github connect`` (which can reuse the GitHub CLI's login).

The token lives in ``integrations`` (service_id ``github``), encrypted with the
person's tenant data key; the plaintext column stays NULL. Who the token
belongs to (login, name, scopes) is kept in clear in ``metadata`` so the app
can show it without decrypting anything.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from app.db.database import get_db_connection
from app.security.crypto import encrypt_field, get_active_kek_version
from app.security.tenant_keys import get_or_create_tenant_dek
from app.services.integrations.token_crypto import decrypt_integration_tokens
from app.utils.logger import logger

SERVICE_ID = "github"
SERVICE_NAME = "GitHub"
GITHUB_API = "https://api.github.com"
_TENANT_KIND = "integration_user"  # shared with token_crypto and the OpenAI key
# Everything a person can do in their own GitHub, including deleting repositories
# (Manifest always asks before it does). Fine-grained tokens carry no scopes.
OAUTH_SCOPES = ["repo", "workflow", "read:org", "read:user", "user:email", "delete_repo"]
_PLACEHOLDER_TOKENS = frozenset({"", "***", "null", "none"})


class GitHubConnectError(ValueError):
    """The token is malformed, GitHub rejected it, or it could not be stored."""


@dataclass(frozen=True)
class GitHubIdentity:
    login: str
    name: str | None = None
    avatar_url: str | None = None
    html_url: str | None = None
    scopes: list[str] = field(default_factory=list)
    method: str = "token"  # "oauth" or "token"
    connected_at: str | None = None

    def to_metadata(self) -> str:
        return json.dumps(
            {
                "login": self.login,
                "name": self.name,
                "avatar_url": self.avatar_url,
                "html_url": self.html_url,
                "scopes": self.scopes,
                "method": self.method,
                "connected_at": self.connected_at,
            }
        )

    @classmethod
    def from_metadata(cls, raw: object) -> GitHubIdentity | None:
        try:
            data = raw if isinstance(raw, dict) else json.loads(str(raw or "{}"))
        except (TypeError, ValueError):
            return None
        if not isinstance(data, dict) or not data.get("login"):
            return None
        scopes = data.get("scopes") or []
        return cls(
            login=str(data["login"]),
            name=data.get("name"),
            avatar_url=data.get("avatar_url"),
            html_url=data.get("html_url"),
            scopes=[str(s) for s in scopes] if isinstance(scopes, list) else [],
            method=str(data.get("method") or "token"),
            connected_at=data.get("connected_at"),
        )


def oauth_available() -> bool:
    """Whether "Sign in with GitHub" is set up on this deployment."""
    return bool(os.getenv("GITHUB_CLIENT_ID") and os.getenv("GITHUB_CLIENT_SECRET"))


def _aad(user_id: str) -> bytes:
    # Same binding as token_crypto._aad, so decrypt_integration_tokens reads it.
    return f"integrations:{user_id}:{SERVICE_ID}".encode()


def clean_token(raw: str | None) -> str:
    token = (raw or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if (
        token.lower() in _PLACEHOLDER_TOKENS
        or len(token) < 20
        or len(token) > 255
        or any(c.isspace() for c in token)
    ):
        raise GitHubConnectError(
            "That doesn't look like a GitHub token. Create one at "
            "github.com/settings/tokens (it starts with ghp_ or github_pat_)."
        )
    return token


def verify_token(
    token: str, *, method: str = "token", transport: httpx.BaseTransport | None = None
) -> GitHubIdentity:
    """Ask GitHub who the token belongs to (and which scopes it has)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Manifest",
    }
    try:
        with httpx.Client(timeout=15.0, transport=transport) as client:
            resp = client.get(f"{GITHUB_API}/user", headers=headers)
    except httpx.HTTPError as exc:
        raise GitHubConnectError("Could not reach GitHub. Try again in a moment.") from exc
    if resp.status_code in (401, 403):
        raise GitHubConnectError(
            "GitHub rejected this token. Check it hasn't expired and try again."
        )
    if resp.status_code != 200:
        raise GitHubConnectError(f"GitHub answered {resp.status_code}. Try again in a moment.")
    user = resp.json()
    scopes_header = resp.headers.get("x-oauth-scopes") or ""
    return GitHubIdentity(
        login=str(user.get("login") or ""),
        name=user.get("name"),
        avatar_url=user.get("avatar_url"),
        html_url=user.get("html_url"),
        scopes=[s.strip() for s in scopes_header.split(",") if s.strip()],
        method=method,
        connected_at=datetime.now(UTC).isoformat(),
    )


def _assert_residency(user_id: str) -> None:
    from app.security.data_residency import RegionMismatchError, assert_region_match

    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT data_region FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
    region = (
        row.get("data_region") if isinstance(row, dict) else (row[0] if row else None)
    ) or None
    try:
        assert_region_match(region, context="integrations.github")
    except RegionMismatchError as exc:
        raise GitHubConnectError("Your account's data region doesn't allow this here.") from exc


def save_github_token(
    user_id: str,
    raw_token: str,
    *,
    method: str = "token",
    transport: httpx.BaseTransport | None = None,
) -> GitHubIdentity:
    """Verify ``raw_token`` with GitHub, then store it encrypted for ``user_id``."""
    token = clean_token(raw_token)
    identity = verify_token(token, method=method, transport=transport)
    if not identity.login:
        raise GitHubConnectError("GitHub didn't say who this token belongs to.")
    _assert_residency(str(user_id))
    dek = get_or_create_tenant_dek(_TENANT_KIND, str(user_id))
    ciphertext = encrypt_field(token, dek, aad=_aad(str(user_id)))
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO integrations (
                user_id, service_id, service_name, access_token, refresh_token,
                access_token_ciphertext, refresh_token_ciphertext, token_key_version,
                expires_at, metadata
            )
            VALUES (%s, %s, %s, NULL, NULL, %s, NULL, %s, NULL, %s)
            ON CONFLICT (user_id, service_id) DO UPDATE SET
                service_name = EXCLUDED.service_name,
                access_token = NULL,
                refresh_token = NULL,
                access_token_ciphertext = EXCLUDED.access_token_ciphertext,
                refresh_token_ciphertext = NULL,
                token_key_version = EXCLUDED.token_key_version,
                expires_at = NULL,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            """,
            (
                user_id,
                SERVICE_ID,
                SERVICE_NAME,
                ciphertext,
                get_active_kek_version(),
                identity.to_metadata(),
            ),
        )
        conn.commit()
    logger.info(
        "[github] connected",
        extra={"enduser.id": str(user_id), "github.login": identity.login, "github.method": method},
    )
    return identity


def _load_row(user_id: str) -> dict[str, Any] | None:
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_id, service_id, access_token, access_token_ciphertext,
                   refresh_token, refresh_token_ciphertext, metadata
            FROM integrations WHERE user_id = %s AND service_id = %s
            """,
            (user_id, SERVICE_ID),
        )
        row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    keys = (
        "user_id",
        "service_id",
        "access_token",
        "access_token_ciphertext",
        "refresh_token",
        "refresh_token_ciphertext",
        "metadata",
    )
    return dict(zip(keys, row, strict=False))


def load_github_token(user_id: str) -> str | None:
    """The person's GitHub token (decrypted), or None when GitHub isn't connected."""
    try:
        row = _load_row(str(user_id))
    except Exception as exc:  # noqa: BLE001 - a lookup failure means "not connected"
        logger.warning("[github] token lookup failed: %s", type(exc).__name__)
        return None
    if not row:
        return None
    access, _ = decrypt_integration_tokens(row)
    if not access or not isinstance(access, str) or access.strip().lower() in _PLACEHOLDER_TOKENS:
        return None
    return access.strip()


def github_identity(user_id: str) -> GitHubIdentity | None:
    """Who the connected token belongs to (no decryption), or None."""
    try:
        row = _load_row(str(user_id))
    except Exception:  # noqa: BLE001
        return None
    if not row or not (row.get("access_token") or row.get("access_token_ciphertext")):
        return None
    return GitHubIdentity.from_metadata(row.get("metadata")) or GitHubIdentity(login="")


def disconnect_github(user_id: str) -> None:
    """Forget the token. (Revoke it on GitHub too: Settings → Applications or Tokens.)"""
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM integrations WHERE user_id = %s AND service_id = %s",
            (user_id, SERVICE_ID),
        )
        conn.commit()
