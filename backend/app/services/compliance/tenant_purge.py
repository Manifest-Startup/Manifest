"""
Tenant purge / right-to-erasure.

``purge_tenant(tenant_id)`` performs **crypto-shred** as the primary
mechanism: deleting the wrapped DEK row in ``tenant_data_keys`` renders
every ciphertext encrypted under that DEK permanently undecryptable. We
then scrub the plaintext rows that hold non-encrypted residue (PII columns
not yet covered by field-level encryption) and emit an admin audit event.

This is the GDPR Art. 17 / CCPA §1798.105 primitive. It runs in a single
DB transaction so a partial purge is impossible.
"""

from __future__ import annotations

from app.db.database import get_db_connection
from app.security.tenant_keys import purge_tenant_keys_with_cursor
from app.utils.logger import logger

# Tables that may not exist in every deployment (e.g. older test fixtures
# that don't run every migration). DELETE failures against these are
# downgraded to a warning so the purge still succeeds. Every other table
# in the plan is required: a failure aborts the whole purge.
OPTIONAL_PURGE_TABLES: frozenset = frozenset(
    {
        "scim_group_members",
        "step_up_verifications",
        # Legacy TOTP store: sign-in moved to Open Media (ADR 0002) and no table exists now.
        "user_totp_mfa",
        "privacy_consents",
        "vault_files",
        # Goals (ADR 0020): optional until the migration is applied everywhere.
        "standing_authorizations",
        "knowledge_facts",
        "goal_events",
        "approval_requests",
        "goal_tasks",
        "goals",
    }
)


# Tables that hold per-user PII/PHI we should null/delete on purge.
# Order matters when there are FKs: leaf rows first.
USER_DATA_PURGE_PLAN: list[dict[str, str]] = [
    {"table": "integrations", "where": "user_id = %s", "mode": "delete"},
    {"table": "user_totp_mfa", "where": "user_id = %s", "mode": "delete"},
    {"table": "webauthn_credentials", "where": "user_id = %s", "mode": "delete"},
    {"table": "password_reset_tokens", "where": "user_id = %s", "mode": "delete"},
    {"table": "password_history", "where": "user_id = %s", "mode": "delete"},
    {"table": "step_up_verifications", "where": "user_id = %s", "mode": "delete"},
    {"table": "user_sessions", "where": "user_id = %s", "mode": "delete"},
    {"table": "privacy_consents", "where": "user_id = %s", "mode": "delete"},
    {"table": "scim_group_members", "where": "user_id = %s", "mode": "delete"},
    {"table": "vault_files", "where": "user_id = %s", "mode": "delete"},
    # Goals hold contacts and their replies (ADR 0020); leaf tables first.
    {"table": "standing_authorizations", "where": "user_id = %s", "mode": "delete"},
    {"table": "knowledge_facts", "where": "user_id = %s", "mode": "delete"},
    {"table": "goal_events", "where": "user_id = %s", "mode": "delete"},
    {"table": "approval_requests", "where": "user_id = %s", "mode": "delete"},
    {"table": "goal_tasks", "where": "user_id = %s", "mode": "delete"},
    {"table": "goals", "where": "user_id = %s", "mode": "delete"},
]


def purge_user_data(
    user_id: str,
    *,
    actor_user_id: str | None = None,
    audit_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Crypto-shred the user's DEK and scrub residual PII rows.

    Returns a dict containing the per-table delete counts (under
    ``counts``) and the persisted ``admin_audit_event_id`` so callers
    (DSAR /erase) can publish a tamper-evident deletion certificate
    that points at a real audit row.

    Idempotent: running again on a purged user is a no-op.

    ``audit_metadata`` is merged into the audit row's metadata column
    so DSAR-issued certificate identifiers are recorded in the audit
    trail at the same instant the deletion is committed.
    """
    if not user_id:
        raise ValueError("user_id is required")

    counts: dict[str, int] = {}
    audit_event_id: str | None = None

    # Single transaction: crypto-shred + scrubs + tombstone + audit must
    # all commit together or roll back together. If any required step or
    # the mandatory audit insert fails, the whole purge is aborted so we
    # never end up in a "data still recoverable, no audit trail" state.
    with get_db_connection() as conn:
        try:
            with conn.cursor() as cur:
                # 1) Crypto-shred — once committed, every integrations
                #    ciphertext encrypted under this DEK is unrecoverable.
                counts["crypto_shredded"] = purge_tenant_keys_with_cursor(
                    cur, "integration_user", str(user_id)
                )

                # 2) Delete leaf PII/PHI rows. Optional tables get a
                #    savepoint so a missing-table error in dev/test doesn't
                #    abort the surrounding transaction.
                for step in USER_DATA_PURGE_PLAN:
                    is_optional = step["table"] in OPTIONAL_PURGE_TABLES
                    sp = None
                    if is_optional:
                        sp = f"sp_{step['table']}"
                        cur.execute(f"SAVEPOINT {sp}")
                    try:
                        cur.execute(
                            f"DELETE FROM {step['table']} WHERE {step['where']}",
                            (user_id,),
                        )
                        counts[step["table"]] = cur.rowcount or 0
                        if sp:
                            cur.execute(f"RELEASE SAVEPOINT {sp}")
                    except Exception as exc:
                        if is_optional and sp:
                            logger.warning(
                                "[tenant_purge] optional table %s skipped: %s",
                                step["table"],
                                exc,
                            )
                            counts[step["table"]] = 0
                            cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                            continue
                        # Required table failure — abort the whole purge.
                        raise

                # 3) Tombstone the user row so the rest of the app sees
                #    them as gone.
                cur.execute(
                    """
                    UPDATE users
                    SET email = CONCAT('purged-', user_id::text, '@invalid.local'),
                        password_hash = NULL,
                        disabled_at = COALESCE(disabled_at, NOW()),
                        disabled_reason = COALESCE(disabled_reason, 'gdpr_purge')
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                counts["users_tombstoned"] = cur.rowcount or 0

                # 4) Mandatory audit event — failure here aborts the purge
                #    so we never erase data without a trace. We RETURN
                #    the persisted event_id so the caller (DSAR /erase)
                #    can publish a deletion certificate that points at
                #    a real audit row, not an opaque random UUID.
                merged_meta = dict(counts)
                if audit_metadata:
                    merged_meta.update(audit_metadata)
                cur.execute(
                    """
                    INSERT INTO admin_audit_events
                        (actor_user_id, target_user_id, action, resource, metadata)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    RETURNING event_id
                    """,
                    (
                        actor_user_id or user_id,
                        user_id,
                        "tenant_purge",
                        "user",
                        _json(merged_meta),
                    ),
                )
                row = cur.fetchone()
                if row:
                    if isinstance(row, dict):
                        audit_event_id = str(row.get("event_id"))
                    else:
                        audit_event_id = str(row[0])
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("[tenant_purge] aborted (rolled back) for user_id=%s", user_id)
            raise

    logger.info("[tenant_purge] purged user_id=%s counts=%s", user_id, counts)
    return {"counts": counts, "admin_audit_event_id": audit_event_id}


def _json(payload: object) -> str:
    import json

    return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Public erasure interface
# ---------------------------------------------------------------------------


def purge_tenant(
    tenant_id: str,
    *,
    actor_user_id: str | None = None,
    audit_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """GDPR Art. 17 / CCPA §1798.105 right-to-erasure entry point.

    A "tenant" in Manifest's per-user model maps 1:1 to ``users.user_id``;
    this helper exists so privacy/audit code (T6/T15) has a single, named
    primitive to call. It crypto-shreds the tenant's wrapped DEK,
    deletes leaf PII/PHI rows, tombstones the user row and writes a
    mandatory audit event in a single transaction. Returns
    ``{"counts": {...}, "admin_audit_event_id": <UUID>}``.
    """
    return purge_user_data(
        tenant_id,
        actor_user_id=actor_user_id,
        audit_metadata=audit_metadata,
    )


__all__ = ["USER_DATA_PURGE_PLAN", "purge_tenant", "purge_user_data"]
