"""Bring-your-own-key storage for customers' API keys (OpenAI, and Apollo.io for prospects).

Keys live in ``integrations`` (service_id ``openai`` or ``apollo``) and are always encrypted
with the user's tenant data key: the plaintext ``access_token`` column stays
NULL. Only the last four characters are kept in clear (``metadata``) so the
UI can show which key is connected.
"""

from __future__ import annotations

import json

from app.db.database import get_db_connection
from app.security.crypto import decrypt_field, encrypt_field, get_active_kek_version
from app.security.tenant_keys import get_or_create_tenant_dek
from app.utils.logger import logger

SERVICE_ID = "openai"
SERVICE_NAME = "OpenAI"
_TENANT_KIND = "integration_user"  # shared with integration_token_crypto


class InvalidOpenAIKeyError(ValueError):
    """The key is malformed or OpenAI rejected it."""


def _column(row: object, name: str) -> object:
    """Read one column from a dict row (RealDictCursor) or a plain tuple row."""
    if row is None:
        return None
    return row[name] if isinstance(row, dict) else row[0]  # type: ignore[index]


def _aad(user_id: str, service_id: str = SERVICE_ID) -> bytes:
    return f"integrations:{user_id}:{service_id}".encode()


def mask(key: str) -> str:
    return key[-4:]


def validate_key(api_key: str) -> str:
    """Normalise and verify a key against OpenAI (a cheap models list call)."""
    key = (api_key or "").strip()
    if not key.startswith("sk-") or len(key) < 20 or any(c.isspace() for c in key):
        raise InvalidOpenAIKeyError(
            "That doesn't look like an OpenAI API key (it should start with 'sk-')."
        )
    from openai import AuthenticationError, OpenAI, PermissionDeniedError

    try:
        OpenAI(api_key=key, timeout=15.0, max_retries=0).models.list()
    except (AuthenticationError, PermissionDeniedError):
        raise InvalidOpenAIKeyError("OpenAI rejected this key. Check it and try again.") from None
    except Exception as exc:  # network trouble: don't block saving on OpenAI downtime
        logger.warning("[byok] could not verify OpenAI key (saving anyway): %s", type(exc).__name__)
    return key


def save_user_key(user_id: str, api_key: str) -> str:
    """Validate, encrypt and store the OpenAI key. Returns its last four characters."""
    return store_key(user_id, validate_key(api_key))


def store_key(
    user_id: str, key: str, *, service_id: str = SERVICE_ID, service_name: str = SERVICE_NAME
) -> str:
    """Encrypt and store an already-validated key for one service. Returns its last four."""
    dek = get_or_create_tenant_dek(_TENANT_KIND, str(user_id))
    ciphertext = encrypt_field(key, dek, aad=_aad(str(user_id), service_id))
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO integrations (
                user_id, service_id, service_name, access_token, refresh_token,
                access_token_ciphertext, token_key_version, metadata
            )
            VALUES (%s, %s, %s, NULL, NULL, %s, %s, %s)
            ON CONFLICT (user_id, service_id) DO UPDATE SET
                access_token = NULL,
                access_token_ciphertext = EXCLUDED.access_token_ciphertext,
                token_key_version = EXCLUDED.token_key_version,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            """,
            (
                user_id,
                service_id,
                service_name,
                ciphertext,
                get_active_kek_version(),
                json.dumps({"last4": mask(key)}),
            ),
        )
        conn.commit()
    return mask(key)


def load_user_key(user_id: str, service_id: str = SERVICE_ID) -> str | None:
    """Decrypted key for ``user_id``, or None when they have not added one."""
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT access_token_ciphertext FROM integrations WHERE user_id = %s AND service_id = %s",
            (user_id, service_id),
        )
        row = cur.fetchone()
    blob = _column(row, "access_token_ciphertext")
    if blob is None:
        return None
    dek = get_or_create_tenant_dek(_TENANT_KIND, str(user_id))
    return decrypt_field(bytes(blob), dek, aad=_aad(str(user_id), service_id))


def key_last4(user_id: str, service_id: str = SERVICE_ID) -> str | None:
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT metadata FROM integrations WHERE user_id = %s AND service_id = %s",
            (user_id, service_id),
        )
        row = cur.fetchone()
    try:
        return json.loads(str(_column(row, "metadata") or "{}")).get("last4")
    except (TypeError, ValueError):
        return None


def delete_user_key(user_id: str, service_id: str = SERVICE_ID) -> None:
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM integrations WHERE user_id = %s AND service_id = %s",
            (user_id, service_id),
        )
        conn.commit()
