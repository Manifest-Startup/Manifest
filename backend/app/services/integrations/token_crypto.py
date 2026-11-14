"""
Field-level encryption for ``integrations.access_token`` / ``refresh_token``.

The integrations table holds long-lived OAuth bearer tokens for Google,
GitHub, Notion, etc. A leak of those plaintext columns is a one-step path
to full impersonation against every connected third-party. We encrypt them
with envelope encryption (per-user DEK wrapped under the active KEK).

Online + reversible
-------------------
Both the legacy plaintext columns (``access_token``, ``refresh_token``) and
the new ciphertext columns (``access_token_ciphertext``,
``refresh_token_ciphertext``) coexist during the cutover window:

* When ``ENCRYPT_INTEGRATIONS_TOKENS`` is true, the writer encrypts and
  populates the ciphertext columns and writes ``NULL`` to the plaintext
  columns. The reader prefers ciphertext.
* When the flag is false, behaviour is unchanged (plaintext only). The
  reader still understands ciphertext rows, so flipping the flag back off
  does not break any row that was already encrypted.

Backfill is provided by ``backfill_encrypted_tokens()`` which migrates
plaintext rows in batches and is safe to run while the flag is off (rows
encrypt-once, are read transparently afterward).
"""

from __future__ import annotations

import os

from app.db.database import get_db_connection
from app.security.crypto import (
    decrypt_field,
    encrypt_field,
    get_active_kek_version,
    is_encrypted_blob,
)
from app.security.tenant_keys import get_or_create_tenant_dek
from app.utils.logger import logger

INTEGRATION_TENANT_KIND = "integration_user"


def encryption_enabled() -> bool:
    return (os.getenv("ENCRYPT_INTEGRATIONS_TOKENS") or "").lower() in ("1", "true", "yes")


def _aad(user_id: str, service_id: str) -> bytes:
    """Bind ciphertext to its owning row so a swapped-in blob from a different
    user/service won't decrypt — AES-GCM rejects mismatched AAD."""
    return f"integrations:{user_id}:{service_id}".encode()


def encrypt_integration_tokens(
    user_id: str,
    service_id: str,
    *,
    access_token: str | None,
    refresh_token: str | None,
) -> dict[str, object]:
    """Return a dict of column→value for INSERT/UPDATE.

    When the feature flag is OFF, callers get the legacy plaintext shape so
    nothing changes. When ON, the plaintext columns are nulled out and the
    ciphertext columns + ``token_key_version`` are populated.
    """
    if not encryption_enabled():
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "access_token_ciphertext": None,
            "refresh_token_ciphertext": None,
            "token_key_version": None,
        }
    dek = get_or_create_tenant_dek(INTEGRATION_TENANT_KIND, str(user_id))
    aad = _aad(str(user_id), str(service_id))
    return {
        "access_token": None,
        "refresh_token": None,
        "access_token_ciphertext": (
            encrypt_field(access_token, dek, aad=aad) if access_token else None
        ),
        "refresh_token_ciphertext": (
            encrypt_field(refresh_token, dek, aad=aad) if refresh_token else None
        ),
        "token_key_version": get_active_kek_version(),
    }


def decrypt_integration_tokens(row: dict[str, object]) -> tuple[str | None, str | None]:
    """Return (access_token, refresh_token) for a row, preferring ciphertext.

    Fail-closed: if a ciphertext column is present but cannot be decrypted
    (KEK gone, blob corrupt, tenant key crypto-shredded) we raise rather than
    silently returning the legacy plaintext fallback.
    """
    user_id = row.get("user_id")
    service_id = row.get("service_id")
    ct_access = row.get("access_token_ciphertext")
    ct_refresh = row.get("refresh_token_ciphertext")
    if ct_access is None and ct_refresh is None:
        return row.get("access_token"), row.get("refresh_token")  # type: ignore[return-value]

    dek = get_or_create_tenant_dek(INTEGRATION_TENANT_KIND, str(user_id))
    aad = _aad(str(user_id), str(service_id))

    def _decode(blob) -> str | None:
        if blob is None:
            return None
        if isinstance(blob, memoryview):
            blob = bytes(blob)
        if not is_encrypted_blob(blob):
            raise ValueError("integration token ciphertext has unexpected envelope")
        return decrypt_field(blob, dek, aad=aad)

    access = _decode(ct_access) if ct_access is not None else row.get("access_token")
    refresh = _decode(ct_refresh) if ct_refresh is not None else row.get("refresh_token")
    return access, refresh  # type: ignore[return-value]


def backfill_encrypted_tokens(*, batch_size: int = 100, max_batches: int = 1000) -> int:
    """One-shot backfill: encrypt any plaintext token rows that lack ciphertext.

    Idempotent. Safe to run with the feature flag OFF (the writer keeps
    populating plaintext, but rows already encrypted by the backfill will
    be read transparently because the reader prefers ciphertext). Safe to
    run with the flag ON too.
    """
    encrypted = 0
    for _ in range(max_batches):
        with get_db_connection() as conn, conn.cursor() as cur:
            # Pick up *any* row where a plaintext value still exists but
            # the corresponding ciphertext column is NULL. Earlier
            # versions of this query required BOTH ciphertexts to be NULL
            # which left rows half-migrated forever.
            cur.execute(
                """
                    SELECT integration_id, user_id, service_id,
                           access_token, refresh_token,
                           access_token_ciphertext, refresh_token_ciphertext
                    FROM integrations
                    WHERE (access_token IS NOT NULL AND access_token_ciphertext IS NULL)
                       OR (refresh_token IS NOT NULL AND refresh_token_ciphertext IS NULL)
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                    """,
                (batch_size,),
            )
            rows = cur.fetchall() or []
            if not rows:
                conn.commit()
                return encrypted
            for row in rows:
                # Backfill must always produce ciphertext irrespective of
                # the env flag — that is its whole purpose.
                dek = get_or_create_tenant_dek(INTEGRATION_TENANT_KIND, str(row["user_id"]))
                aad = _aad(str(row["user_id"]), str(row["service_id"]))

                # Only encrypt and clear the plaintext columns that are
                # actually still in plaintext. This makes the operation
                # safe for half-migrated rows.
                new_access_ct = row.get("access_token_ciphertext")
                new_refresh_ct = row.get("refresh_token_ciphertext")
                clear_access_pt = False
                clear_refresh_pt = False
                if row.get("access_token") and new_access_ct is None:
                    new_access_ct = encrypt_field(row["access_token"], dek, aad=aad)
                    clear_access_pt = True
                if row.get("refresh_token") and new_refresh_ct is None:
                    new_refresh_ct = encrypt_field(row["refresh_token"], dek, aad=aad)
                    clear_refresh_pt = True

                cur.execute(
                    """
                        UPDATE integrations
                        SET access_token_ciphertext = %s,
                            refresh_token_ciphertext = %s,
                            token_key_version = %s,
                            access_token = CASE WHEN %s THEN NULL ELSE access_token END,
                            refresh_token = CASE WHEN %s THEN NULL ELSE refresh_token END,
                            updated_at = NOW()
                        WHERE integration_id = %s
                        """,
                    (
                        new_access_ct,
                        new_refresh_ct,
                        get_active_kek_version(),
                        clear_access_pt,
                        clear_refresh_pt,
                        row["integration_id"],
                    ),
                )
                encrypted += 1
            conn.commit()
        if len(rows) < batch_size:
            break
    logger.info("[integration_token_crypto] backfilled %s rows", encrypted)
    return encrypted


__all__ = [
    "INTEGRATION_TENANT_KIND",
    "backfill_encrypted_tokens",
    "decrypt_integration_tokens",
    "encrypt_integration_tokens",
    "encryption_enabled",
]
