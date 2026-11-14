"""Security-audit event writer (SEC-068).

This is the ONE place application code is allowed to insert into
``security_audit_events``. Every emit goes through three stages:

1. **Sanitise.** Metadata is deep-copied through
   ``audit_chain.sanitize_metadata`` so secrets / API keys / unredacted
   PII never reach the audit table — even if a developer accidentally
   stuffs a raw prompt into ``metadata``.

2. **Link into the hash chain.** We grab the most recent row's hash
   under a per-table advisory lock so two concurrent writers cannot
   produce two rows that both claim the same predecessor. The new row
   stores both ``prev_hash`` and the freshly computed ``event_hash``.
   ``audit_verifier.verify_chain`` later reproduces the hash and flags
   any tampering / re-ordering / deletion.

3. **Mirror to the SIEM JSONL stream** so off-host preservation can
   pick up the event before any DB-level compromise can rewrite the
   row. The sink is best-effort: a sink outage never breaks the request
   path, the DB row is the source of truth.

Backwards compatibility: the public ``record_security_event(event_type,
**kwargs)`` signature is unchanged — older call sites continue to work
without modification. New emit sites should additionally pass
``request_id`` and consider using one of the typed ``EventType``
constants in ``app.security.audit_chain`` so a typo can't introduce a
silent gap in the audit trail.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.database import get_db_connection
from app.security import audit_sink
from app.security.audit_chain import (
    GENESIS_HASH,
    get_definition,
    link_event,
    sanitize_metadata,
)
from app.utils.logger import logger

_TABLE = "security_audit_events"
_CHAIN_LOCK_KEY = 0x5ECAD117  # advisory-lock identifier ("SEC AUDIT", arbitrary 32-bit constant)


def _json_safe(value: dict[str, Any] | None) -> str:
    try:
        return json.dumps(value or {}, default=str, sort_keys=True, separators=(",", ":"))
    except Exception:
        return "{}"


def _read_latest_hash(cur) -> str:
    """Return the ``event_hash`` of the most recent row, or GENESIS.

    Caller MUST already hold the per-table advisory lock so the
    "read latest, then insert linked" pair is atomic against other
    writers in the same database.
    """
    try:
        # IMPORTANT: only chained rows count as predecessors. A legacy
        # row (NULL event_hash from the pre-migration era, or a
        # fallback insert that bypassed the chain) must not reset us
        # back to GENESIS — that would create a fake chain break the
        # next time the verifier runs.
        cur.execute(f"""
            SELECT event_hash FROM {_TABLE}
            WHERE event_hash IS NOT NULL
            ORDER BY seq DESC LIMIT 1
            """)
        row = cur.fetchone() or {}
        return (row.get("event_hash") or "").strip().lower() or GENESIS_HASH
    except Exception:
        # Most likely cause: the chain columns haven't been migrated yet.
        # Fail-safe to genesis so the chain restarts at the next deploy
        # rather than crashing the request path.
        return GENESIS_HASH


def record_security_event(  # noqa: C901
    event_type: str,
    *,
    user_id: str | None = None,
    request_ip: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    # Extended canonical contract — optional for backwards compatibility
    # with legacy emit sites; new sites are expected to populate them.
    actor_id: str | None = None,
    actor_type: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    tenant_id: str | None = None,
    user_agent: str | None = None,
    outcome: str | None = None,
) -> None:
    """Persist one security-audit event (sanitised, hash-chained, SIEM-mirrored).

    Best-effort: any DB or sink failure is logged at WARNING and the
    event is also written to the application log so an operator can
    still recover the timeline from container logs in the worst case.

    Extended fields encode the SOC 2 / ISO 27001 / HIPAA audit-record
    contract — *who* (``actor_id`` + ``actor_type`` such as ``user`` /
    ``api_key`` / ``system``), *what* (``action`` + ``target_type`` +
    ``target_id``), *where* (``tenant_id``, ``request_ip``,
    ``user_agent``), *when* (``created_at``), and *outcome* (``allowed``
    / ``denied`` / ``failed``). Missing values are stored as NULL but
    are still hashed into the chain so they cannot be backfilled later
    without breaking verification.
    """
    sanitized = sanitize_metadata(metadata)
    event_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    created_iso = created_at.isoformat()

    # Canonical-schema enforcement: warn loudly when a security-relevant
    # event is emitted without the required who/what/outcome fields.
    # This is intentionally a non-blocking warning (we still write the
    # row) because failing the request path on an audit-logging shape
    # bug would be worse than a partially-populated row — but the
    # warning surfaces in CI/log-monitoring so the gap is fixed.
    try:
        from app.security.audit_chain import get_definition as _get_def

        _defn = _get_def(event_type)
        _is_sensitive = _defn.severity.value in {"high", "critical"} or _defn.category.value in {
            "auth",
            "authz",
            "mfa",
            "session",
            "data_access",
        }
        if _is_sensitive:
            _missing = [
                name
                for name, val in (
                    ("action", action),
                    ("target_type", target_type),
                    ("outcome", outcome),
                )
                if not val
            ]
            if _missing:
                logger.warning(
                    "[security_audit] canonical-schema gap: event=%s missing=%s",
                    event_type,
                    ",".join(_missing),
                )
    except Exception:  # pragma: no cover - never block on validation
        pass

    # If actor_id is not given, fall back to user_id so legacy sites get
    # a sensible "who" automatically.
    effective_actor_id = actor_id or user_id
    effective_actor_type = actor_type or ("user" if effective_actor_id else None)

    # Defense-in-depth on user_agent: clamp length and strip control
    # characters before it ever hits the canonical payload, the DB,
    # or the SIEM sink. We never want a malicious header smuggling
    # newlines or ANSI escapes into operator log viewers, and an
    # absurdly long UA must not blow up the chain hash budget.
    safe_ua: str | None = None
    if user_agent:
        ua_str = str(user_agent)[:500]
        safe_ua = "".join(c for c in ua_str if c.isprintable() and c not in "\r\n") or None

    # Defense-in-depth on free-text identifiers we expose at the top
    # level — clamp them so a hostile target_id / tenant_id can't
    # bloat the chain payload or leak unexpected control bytes.
    def _clip(value: str | None, n: int = 256) -> str | None:
        if value is None:
            return None
        s = str(value)[:n]
        s = "".join(c for c in s if c.isprintable() and c not in "\r\n")
        return s or None

    # PII REDACTION on top-level canonical identity fields. The chain
    # row is permanent and the SIEM stream is exported off-host, so
    # we MUST NOT persist raw email addresses or other unredacted PII
    # there even if the caller passed them. We replace any
    # email-shaped value with a stable, non-reversible token of the
    # form ``email:<sha256-prefix>`` so cross-row correlation still
    # works for incident response while the original address never
    # leaves the request scope.
    import hashlib as _hashlib
    import re as _re

    _EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def _pseudonymize(value: str | None) -> str | None:
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        if _EMAIL_RE.match(s):
            digest = _hashlib.sha256(s.lower().encode("utf-8")).hexdigest()[:32]
            return f"email:{digest}"
        return s

    extended = dict(
        actor_id=_clip(_pseudonymize(effective_actor_id)),
        actor_type=_clip(effective_actor_type, 64),
        action=_clip(action, 128),
        target_type=_clip(target_type, 128),
        target_id=_clip(_pseudonymize(target_id)),
        tenant_id=_clip(_pseudonymize(tenant_id), 128),
        user_agent=safe_ua,
        outcome=_clip(outcome, 64),
    )

    # Pre-compute *something* we can fall back to for the JSONL sink
    # even if the DB write fails. The chain gap will be picked up by
    # the next successful row's prev_hash mismatch.
    fallback_defn, fallback_canonical, fallback_hash = link_event(
        GENESIS_HASH,
        event_id=event_id,
        event_type=event_type,
        user_id=user_id,
        request_ip=request_ip,
        session_id=session_id,
        request_id=request_id,
        metadata=sanitized,
        created_at_iso=created_iso,
        **extended,
    )

    persisted_hash: str = fallback_hash
    persisted_prev: str = GENESIS_HASH
    persisted = False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Serialise chain writers — different scopes still parallelise
                # because the rest of the request never touches this lock.
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (_CHAIN_LOCK_KEY,))
                prev_hash = _read_latest_hash(cur)
                defn, _canonical, event_hash = link_event(
                    prev_hash,
                    event_id=event_id,
                    event_type=event_type,
                    user_id=user_id,
                    request_ip=request_ip,
                    session_id=session_id,
                    request_id=request_id,
                    metadata=sanitized,
                    created_at_iso=created_iso,
                    **extended,
                )
                # NOTE: created_at is passed explicitly so the value we
                # hashed and the value Postgres stores are byte-identical.
                cur.execute(
                    f"""
                    INSERT INTO {_TABLE} (
                        event_id, event_type, category, severity, sensitivity,
                        user_id, request_ip, session_id, request_id,
                        actor_id, actor_type, action, target_type, target_id,
                        tenant_id, user_agent, outcome,
                        metadata, prev_hash, event_hash, created_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s::jsonb, %s, %s, %s
                    )
                    """,
                    (
                        event_id,
                        defn.event_type,
                        defn.category.value,
                        defn.severity.value,
                        defn.sensitivity.value,
                        user_id,
                        request_ip,
                        session_id,
                        request_id,
                        extended["actor_id"],
                        extended["actor_type"],
                        extended["action"],
                        extended["target_type"],
                        extended["target_id"],
                        extended["tenant_id"],
                        extended["user_agent"],
                        extended["outcome"],
                        _json_safe(sanitized),
                        prev_hash,
                        event_hash,
                        created_at,
                    ),
                )
            conn.commit()
        persisted = True
        persisted_hash = event_hash
        persisted_prev = prev_hash
    except Exception as exc:
        # FAIL-CLOSED for chain integrity: in production we refuse to
        # write a non-chained legacy row because that would create a
        # silent gap an attacker could hide behind. The legacy
        # fallback is gated on AUDIT_ALLOW_LEGACY_FALLBACK=1, intended
        # only for the brief window during a forward migration when
        # the new chain columns haven't been deployed yet. Even then
        # we emit a `detection_audit_chain_break` marker so the SIEM
        # sees a degraded-mode alert.
        allow_legacy = (os.getenv("AUDIT_ALLOW_LEGACY_FALLBACK") or "").strip() == "1"
        if not allow_legacy:
            logger.error(
                "[security_audit] FAIL-CLOSED chained insert failed for %s: %s",
                event_type,
                exc,
            )
            try:
                audit_sink.emit(
                    event_id=str(uuid.uuid4()),
                    event_type="detection_audit_chain_break",
                    category="detection",
                    severity="critical",
                    sensitivity="restricted",
                    user_id=None,
                    request_ip=None,
                    session_id=None,
                    request_id=None,
                    metadata={
                        "reason": "chained_insert_failed",
                        "failed_event_type": event_type,
                        "error": str(exc)[:500],
                    },
                    event_hash="",
                    prev_hash="",
                    created_at_iso=created_iso,
                )
            except Exception:  # pragma: no cover - sink is best-effort
                pass
        else:
            try:
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            f"""
                            INSERT INTO {_TABLE} (
                                event_id, event_type, user_id, request_ip,
                                session_id, metadata, created_at
                            )
                            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                            """,
                            (
                                event_id,
                                event_type,
                                user_id,
                                request_ip,
                                session_id,
                                _json_safe(sanitized),
                                created_at,
                            ),
                        )
                    conn.commit()
                persisted = True
                logger.warning(
                    "[security_audit] DEGRADED legacy fallback used for %s "
                    "(AUDIT_ALLOW_LEGACY_FALLBACK=1): %s",
                    event_type,
                    exc,
                )
            except Exception as exc2:
                logger.error(
                    "[security_audit] persist failed for %s: chained=%s legacy=%s",
                    event_type,
                    exc,
                    exc2,
                )

    defn = get_definition(event_type)
    if not persisted:
        # Last resort: log line so the timeline is at least reconstructable.
        logger.info(
            "[security_audit] %s user=%s ip=%s session=%s sev=%s meta=%s",
            event_type,
            user_id,
            request_ip,
            session_id,
            defn.severity.value,
            sanitized,
        )

    # Mirror to the JSONL SIEM stream regardless of DB outcome — the
    # sink is opt-in and always best-effort.
    try:
        audit_sink.emit(
            event_id=event_id,
            event_type=defn.event_type,
            category=defn.category.value,
            severity=defn.severity.value,
            sensitivity=defn.sensitivity.value,
            user_id=user_id,
            request_ip=request_ip,
            session_id=session_id,
            request_id=request_id,
            metadata=sanitized,
            event_hash=persisted_hash,
            prev_hash=persisted_prev,
            created_at_iso=created_iso,
            actor_id=extended["actor_id"],
            actor_type=extended["actor_type"],
            action=extended["action"],
            target_type=extended["target_type"],
            target_id=extended["target_id"],
            tenant_id=extended["tenant_id"],
            user_agent=extended["user_agent"],
            outcome=extended["outcome"],
        )
    except Exception as exc:  # pragma: no cover - sink is best-effort
        logger.debug("[security_audit] sink emit failed: %s", exc)
