"""The user's linked Open Media account, stored in ``integrations``.

One row per user with ``service_id = 'open_media'``, following the same
envelope-encryption pattern as the bring-your-own OpenAI key
(``app.services.ai.user_keys``): tokens are encrypted with the user's tenant
data key and the plaintext ``access_token`` / ``refresh_token`` columns stay
NULL.

- ``refresh_token_ciphertext`` — the OAuth refresh token (about 90 days)
- ``access_token_ciphertext`` + ``expires_at`` — the current access token (about 1 hour)
- ``metadata`` (JSON text) — ``om_user_id``, ``handle``, ``display_name``,
  ``avatar_url``, ``scope``, ``linked_at`` and ``needs_reconnect``. No secrets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.database import get_db_connection
from app.security.crypto import decrypt_field, encrypt_field, get_active_kek_version
from app.security.tenant_keys import get_or_create_tenant_dek

SERVICE_ID = "open_media"
SERVICE_NAME = "Open Media"
_TENANT_KIND = "integration_user"  # shared with the other integration tokens


@dataclass
class OpenMediaLink:
    user_id: str
    om_user_id: str
    handle: str
    refresh_token: str | None
    access_token: str | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def needs_reconnect(self) -> bool:
        return bool(self.metadata.get("needs_reconnect"))


def _aad(user_id: str, column: str) -> bytes:
    return f"integrations:{user_id}:{SERVICE_ID}:{column}".encode()


def _encrypt(user_id: str, column: str, value: str | None) -> bytes | None:
    if not value:
        return None
    dek = get_or_create_tenant_dek(_TENANT_KIND, str(user_id))
    return encrypt_field(value, dek, aad=_aad(str(user_id), column))


def _decrypt(user_id: str, column: str, blob: Any) -> str | None:
    if blob is None:
        return None
    dek = get_or_create_tenant_dek(_TENANT_KIND, str(user_id))
    return decrypt_field(bytes(blob), dek, aad=_aad(str(user_id), column))


def _expiry(expires_in: Any) -> datetime:
    try:
        seconds = int(expires_in)
    except (TypeError, ValueError):
        seconds = 3600
    return datetime.now(UTC) + timedelta(seconds=max(60, seconds))


def _row_value(row: Any, index: int, name: str) -> Any:
    if row is None:
        return None
    return row[name] if isinstance(row, dict) else row[index]


def _parse_metadata(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def save_link(
    user_id: str,
    *,
    om_user_id: str,
    handle: str,
    access_token: str,
    refresh_token: str | None,
    expires_in: Any,
    profile: dict[str, Any] | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    """Create or replace the user's link. Returns the stored metadata."""
    profile = profile or {}
    metadata = {
        "om_user_id": str(om_user_id),
        "handle": str(handle),
        "display_name": profile.get("display_name"),
        "avatar_url": profile.get("avatar_url"),
        "scope": scope,
        "linked_at": datetime.now(UTC).isoformat(),
        "needs_reconnect": False,
    }
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO integrations (
                user_id, service_id, service_name, access_token, refresh_token,
                access_token_ciphertext, refresh_token_ciphertext, token_key_version,
                expires_at, metadata
            )
            VALUES (%s, %s, %s, NULL, NULL, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, service_id) DO UPDATE SET
                access_token = NULL,
                refresh_token = NULL,
                access_token_ciphertext = EXCLUDED.access_token_ciphertext,
                refresh_token_ciphertext = EXCLUDED.refresh_token_ciphertext,
                token_key_version = EXCLUDED.token_key_version,
                expires_at = EXCLUDED.expires_at,
                metadata = EXCLUDED.metadata,
                connected_at = NOW(),
                updated_at = NOW()
            """,
            (
                user_id,
                SERVICE_ID,
                SERVICE_NAME,
                _encrypt(user_id, "access", access_token),
                _encrypt(user_id, "refresh", refresh_token),
                get_active_kek_version(),
                _expiry(expires_in),
                json.dumps(metadata),
            ),
        )
        conn.commit()
    return metadata


def load_link(user_id: str) -> OpenMediaLink | None:
    """The decrypted link, or None when the user has not linked Open Media."""
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT access_token_ciphertext, refresh_token_ciphertext, expires_at, metadata
            FROM integrations WHERE user_id = %s AND service_id = %s
            """,
            (user_id, SERVICE_ID),
        )
        row = cur.fetchone()
    if row is None:
        return None
    metadata = _parse_metadata(_row_value(row, 3, "metadata"))
    expires_at = _row_value(row, 2, "expires_at")
    if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return OpenMediaLink(
        user_id=str(user_id),
        om_user_id=str(metadata.get("om_user_id") or ""),
        handle=str(metadata.get("handle") or ""),
        access_token=_decrypt(user_id, "access", _row_value(row, 0, "access_token_ciphertext")),
        refresh_token=_decrypt(user_id, "refresh", _row_value(row, 1, "refresh_token_ciphertext")),
        expires_at=expires_at if isinstance(expires_at, datetime) else None,
        metadata=metadata,
    )


def link_metadata(user_id: str) -> dict[str, Any] | None:
    """Non-secret link details (handle, ids) without decrypting any token."""
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT metadata FROM integrations WHERE user_id = %s AND service_id = %s",
            (user_id, SERVICE_ID),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return _parse_metadata(_row_value(row, 0, "metadata"))


def update_tokens(
    user_id: str, *, access_token: str, refresh_token: str | None, expires_in: Any
) -> None:
    """Store a refreshed access token (and the rotated refresh token, if any)."""
    access = _encrypt(user_id, "access", access_token)
    with get_db_connection() as conn, conn.cursor() as cur:
        if refresh_token:
            cur.execute(
                """
                UPDATE integrations SET access_token_ciphertext = %s,
                    refresh_token_ciphertext = %s, expires_at = %s, updated_at = NOW()
                WHERE user_id = %s AND service_id = %s
                """,
                (
                    access,
                    _encrypt(user_id, "refresh", refresh_token),
                    _expiry(expires_in),
                    user_id,
                    SERVICE_ID,
                ),
            )
        else:
            cur.execute(
                """
                UPDATE integrations SET access_token_ciphertext = %s, expires_at = %s,
                    updated_at = NOW()
                WHERE user_id = %s AND service_id = %s
                """,
                (access, _expiry(expires_in), user_id, SERVICE_ID),
            )
        conn.commit()


def mark_needs_reconnect(user_id: str) -> None:
    """Open Media rejected the refresh token: drop tokens, keep the handle for the UI."""
    metadata = link_metadata(user_id) or {}
    metadata["needs_reconnect"] = True
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE integrations SET access_token_ciphertext = NULL,
                refresh_token_ciphertext = NULL, expires_at = NULL, metadata = %s,
                updated_at = NOW()
            WHERE user_id = %s AND service_id = %s
            """,
            (json.dumps(metadata), user_id, SERVICE_ID),
        )
        conn.commit()
