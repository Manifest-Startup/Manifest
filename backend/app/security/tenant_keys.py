"""
Per-tenant DEK store + crypto-shred primitive.

A "tenant" here is whatever the caller wants to scope a DEK to:
- For SSO/SCIM rows we use ``sso_tenant_configs.tenant_id``.
- For per-user OAuth integrations we use ``user_id`` as the tenant key (each
  user is effectively their own tenant from a key-isolation standpoint).

The DEK is generated lazily on first use, wrapped with the active KEK, and
persisted in ``tenant_data_keys``. ``purge_tenant_keys()`` deletes every DEK
row for a tenant — once the wrapped DEK is gone, every ciphertext encrypted
under it becomes permanently undecryptable. That is our crypto-shred /
right-to-erasure primitive.
"""

from __future__ import annotations

import threading

from app.db.database import get_db_connection
from app.security.crypto import (
    WrappedDEK,
    generate_dek,
    unwrap_dek,
    wrap_dek,
)
from app.utils.logger import logger

_DEK_CACHE: dict[tuple[str, str], bytes] = {}
_DEK_LOCK = threading.Lock()


def _cache_key(tenant_kind: str, tenant_id: str) -> tuple[str, str]:
    return (tenant_kind or "default", str(tenant_id))


def get_or_create_tenant_dek(tenant_kind: str, tenant_id: str) -> bytes:
    """Return the (decrypted) DEK for a tenant, generating one if necessary.

    Wrapped DEKs are stored in ``tenant_data_keys``. The DEK itself is cached
    in-process for the lifetime of the worker so repeated encrypt/decrypt
    operations don't pay the unwrap cost on every row.
    """
    key = _cache_key(tenant_kind, tenant_id)
    with _DEK_LOCK:
        cached = _DEK_CACHE.get(key)
        if cached is not None:
            return cached

    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
                SELECT wrapped_dek
                FROM tenant_data_keys
                WHERE tenant_kind = %s AND tenant_id = %s AND revoked_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
            (tenant_kind, str(tenant_id)),
        )
        row = cur.fetchone()
        if row and row.get("wrapped_dek"):
            blob = bytes(row["wrapped_dek"])
            dek = unwrap_dek(WrappedDEK.from_blob(blob))
        else:
            # Race-safe insert: two workers can hit this branch concurrently
            # for the same tenant. ON CONFLICT DO NOTHING + RETURNING means
            # the loser of the race gets no row back; we then re-select.
            dek = generate_dek()
            wrapped = wrap_dek(dek)
            cur.execute(
                """
                    INSERT INTO tenant_data_keys (tenant_kind, tenant_id, wrapped_dek, kek_version)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (tenant_kind, tenant_id, kek_version) DO NOTHING
                    RETURNING wrapped_dek
                    """,
                (tenant_kind, str(tenant_id), wrapped.to_blob(), wrapped.kek_version),
            )
            inserted = cur.fetchone()
            if not inserted:
                cur.execute(
                    """
                        SELECT wrapped_dek
                        FROM tenant_data_keys
                        WHERE tenant_kind = %s AND tenant_id = %s AND revoked_at IS NULL
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                    (tenant_kind, str(tenant_id)),
                )
                existing = cur.fetchone()
                if not existing or not existing.get("wrapped_dek"):
                    raise RuntimeError(
                        "tenant_data_keys race resolution failed: no row visible after conflict"
                    )
                dek = unwrap_dek(WrappedDEK.from_blob(bytes(existing["wrapped_dek"])))
        conn.commit()

    with _DEK_LOCK:
        _DEK_CACHE[key] = dek
    return dek


def purge_tenant_keys_with_cursor(cur, tenant_kind: str, tenant_id: str) -> int:
    """Crypto-shred within a caller-supplied cursor/transaction.

    Use this when the crypto-shred must be atomic with other purge work
    (e.g. ``tenant_purge_service.purge_user_data``). Caller is responsible
    for commit/rollback.
    """
    cur.execute(
        """
        DELETE FROM tenant_data_keys
        WHERE tenant_kind = %s AND tenant_id = %s
        """,
        (tenant_kind, str(tenant_id)),
    )
    deleted = cur.rowcount or 0
    with _DEK_LOCK:
        _DEK_CACHE.pop(_cache_key(tenant_kind, tenant_id), None)
    logger.info(
        "[tenant_keys] crypto-shred (tx): deleted %s DEK row(s) for %s/%s",
        deleted,
        tenant_kind,
        tenant_id,
    )
    return deleted


def purge_tenant_keys(tenant_kind: str, tenant_id: str) -> int:
    """Crypto-shred: delete every wrapped DEK for the tenant.

    Returns the number of rows deleted. Once this returns, every ciphertext
    encrypted under those DEKs is permanently unrecoverable — even an attacker
    with database backups and the KEK cannot decrypt them.
    """
    with get_db_connection() as conn, conn.cursor() as cur:
        deleted = purge_tenant_keys_with_cursor(cur, tenant_kind, tenant_id)
        conn.commit()
    return deleted


def reset_dek_cache_for_test() -> None:  # pragma: no cover - test helper
    with _DEK_LOCK:
        _DEK_CACHE.clear()


__all__ = [
    "get_or_create_tenant_dek",
    "purge_tenant_keys",
    "reset_dek_cache_for_test",
]
