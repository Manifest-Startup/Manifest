"""Canonical security-audit event schema + tamper-evident hash chain (SEC-068).

This module is the single source of truth for "what is a security-audit
event in Manifest". Three concerns live here:

1. **Canonical schema** — every event has a stable ``EventType``,
   ``Category``, ``Severity`` and ``Sensitivity`` so downstream pipelines
   (SIEM, alerting, retention, breach-disclosure timers) can route on
   typed fields instead of grepping free-form strings.

2. **Field-level redaction** — ``sanitize_metadata`` walks the metadata
   dict and runs every string value through the redactors in
   ``app.security.ai_safety``. Auditors require that we never persist
   secrets / API keys / full prompts / unredacted PII inside an
   immutable log; the redactor enforces that *before* the row is
   inserted, so even a developer who accidentally stuffs an OpenAI key
   into ``metadata={"raw_prompt": ...}`` cannot leak it through the
   audit table.

3. **Tamper-evident hash chain** — ``compute_event_hash`` deterministically
   hashes each event together with the previous event's hash. The chain
   property means that if any historical row is modified, deleted, or
   re-ordered, every subsequent ``event_hash`` becomes inconsistent and
   ``audit_verifier.verify_chain`` will surface the break. We do *not*
   rely on this alone — the row is also INSERT-only at the application
   layer, the table has no UPDATE/DELETE grants in production, and the
   JSONL SIEM stream provides an off-host copy. Defence in depth.

This file is import-cheap and dependency-free aside from ai_safety so
it can be used from both request hot paths and background jobs.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.security.ai_safety import redact_for_logs

# Conservative secondary redactors that fire on top of the ai_safety
# allowlist. These catch broad classes of secret-looking values that
# the format-specific patterns in ai_safety miss (opaque bearer tokens,
# arbitrary high-entropy hex/base64 blobs adjacent to sensitive
# keywords, "Authorization: Bearer …" lines, etc.). Conservative on
# purpose — we'd rather over-redact in audit metadata than leak.
_SECONDARY_REDACTORS: list[tuple[re.Pattern[str], str]] = [
    # Authorization headers in any form. The token follows either a
    # ``: `` (header form: ``Authorization: Bearer xyz``), an ``=``
    # (query/url form), or whitespace (``Bearer xyz`` standalone).
    (
        re.compile(r"(?i)\b(authorization|bearer|x-api-key)\s*[:=\s]+[A-Za-z0-9._\-+/=]{12,}"),
        "[REDACTED_AUTH_HEADER]",
    ),
    # Long opaque hex blobs (≥40 chars) — covers SHA-1 hashes, API
    # secrets, raw key material. 40 is the minimum SHA-1 length, so
    # below that we'd hit far too many false positives (UUIDs already
    # have hyphens and are intentionally allowed through).
    (re.compile(r"\b[A-Fa-f0-9]{40,}\b"), "[REDACTED_HEX_SECRET]"),
    # Base64-ish high-entropy blobs ≥32 chars with mixed case+digits.
    # Anchored to a word boundary so it doesn't eat plain prose.
    (
        re.compile(
            r"\b(?=[A-Za-z0-9+/_\-]*[A-Z])(?=[A-Za-z0-9+/_\-]*[a-z])(?=[A-Za-z0-9+/_\-]*\d)[A-Za-z0-9+/_\-]{32,}={0,2}\b"
        ),
        "[REDACTED_OPAQUE_SECRET]",
    ),
]


def _apply_secondary_redactors(text: str) -> str:
    out = text
    for pattern, replacement in _SECONDARY_REDACTORS:
        out = pattern.sub(replacement, out)
    return out


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Category(str, Enum):
    """High-level grouping of an audit event.

    Drives SIEM routing rules, dashboard tiles, and retention windows.
    Adding a new category is a deliberate, reviewed change — auditors
    map controls onto these strings.
    """

    AUTH = "auth"  # login / logout / signup / lockout
    SESSION = "session"  # session lifecycle + anomalies
    MFA = "mfa"  # totp / webauthn / recovery
    SSO = "sso"  # SAML / OIDC / SCIM
    API_KEY = "api_key"  # API client + key lifecycle
    ACCOUNT = "account"  # role change / disable / delete request
    PRIVACY = "privacy"  # consent / DSAR / export / delete
    ADMIN = "admin"  # privileged operations (mirrored to admin_audit_events)
    DATA = "data"  # bulk export / mass read / file generation
    AI = "ai"  # AI prompt safety + abnormal usage
    INTEGRATION = "integration"  # outbound third-party calls
    SECURITY = "security"  # CSP report, abuse signal, secret-scan hit
    DETECTION = "detection"  # alerts emitted by audit_detections


class Severity(str, Enum):
    """Severity follows the IR runbook severity matrix.

    INFO     — routine telemetry. Stored, never paged.
    LOW      — single-actor noise (one failed login). Aggregated only.
    MEDIUM   — investigate within business day (lockout, MFA disable).
    HIGH     — page on-call (impossible travel, mass export, priv-esc).
    CRITICAL — declare incident (chain break, secret leak, mass account
               compromise).
    """

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Sensitivity(str, Enum):
    """How carefully the row's metadata must be handled.

    PUBLIC      — safe to surface in user-facing security logs.
    INTERNAL    — only authorised admins (default for most events).
    RESTRICTED  — admin + audit role only; redacted in dashboards.
    SECRET      — must never leave the primary store; SIEM stream
                  drops the metadata payload entirely.
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    SECRET = "secret"


# ---------------------------------------------------------------------------
# Event registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventDefinition:
    """Static metadata about a known event type.

    Lives in code (not in the DB) so lints / type-checks / code review
    catch typos at PR time. Unregistered event types still flow through
    ``record_security_event`` (degraded to ``Category.SECURITY`` /
    ``Severity.INFO``) so we never lose telemetry, but ``MISSING`` shows
    up in the verification report so we notice and add a registration.
    """

    event_type: str
    category: Category
    severity: Severity
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    description: str = ""


_REGISTRY: dict[str, EventDefinition] = {}


def _register(defn: EventDefinition) -> EventDefinition:
    _REGISTRY[defn.event_type] = defn
    return defn


# Auth -----------------------------------------------------------------
LOGIN_SUCCESS = _register(
    EventDefinition(
        "login_success",
        Category.AUTH,
        Severity.INFO,
        description="Interactive login succeeded.",
    )
)
LOGIN_FAILED = _register(
    EventDefinition(
        "login_failed",
        Category.AUTH,
        Severity.LOW,
        description="Bad password or unknown user.",
    )
)
LOGIN_BLOCKED_LOCKOUT = _register(
    EventDefinition(
        "login_blocked_lockout",
        Category.AUTH,
        Severity.MEDIUM,
        description="Account / IP lockout rejected the attempt.",
    )
)
SIGNUP_SUCCESS = _register(
    EventDefinition(
        "signup_success",
        Category.AUTH,
        Severity.INFO,
    )
)
LOGOUT = _register(
    EventDefinition(
        "logout",
        Category.AUTH,
        Severity.INFO,
    )
)
GUEST_SESSION_STARTED = _register(
    EventDefinition(
        "guest_session_started",
        Category.AUTH,
        Severity.INFO,
    )
)
PASSWORD_RESET_REQUESTED = _register(
    EventDefinition(
        "password_reset_requested",
        Category.AUTH,
        Severity.LOW,
    )
)
PASSWORD_RESET_COMPLETED = _register(
    EventDefinition(
        "password_reset_completed",
        Category.AUTH,
        Severity.MEDIUM,
    )
)
PASSWORD_RESET_REQUEST_RATE_LIMITED = _register(
    EventDefinition(
        "password_reset_request_rate_limited",
        Category.AUTH,
        Severity.LOW,
    )
)

# Session --------------------------------------------------------------
SESSION_REVOKED = _register(
    EventDefinition(
        "session_revoked",
        Category.SESSION,
        Severity.MEDIUM,
    )
)
CLI_SESSION_CREATED = _register(
    EventDefinition(
        "cli_session_created",
        Category.SESSION,
        Severity.MEDIUM,
        description="A signed-in person approved a Manifest CLI session (ADR 0003).",
    )
)
OTHER_SESSIONS_REVOKED = _register(
    EventDefinition(
        "other_sessions_revoked",
        Category.SESSION,
        Severity.MEDIUM,
    )
)
SESSION_STOLEN_SUSPECTED = _register(
    EventDefinition(
        "session_stolen_suspected",
        Category.SESSION,
        Severity.HIGH,
        description="Session active after the user's password was changed.",
    )
)
SESSION_IP_CHANGE = _register(
    EventDefinition(
        "session_ip_change",
        Category.SESSION,
        Severity.LOW,
    )
)
SESSION_USER_AGENT_CHANGE = _register(
    EventDefinition(
        "session_user_agent_change",
        Category.SESSION,
        Severity.LOW,
    )
)

# MFA ------------------------------------------------------------------
MFA_ENABLED = _register(
    EventDefinition(
        "mfa_enabled",
        Category.MFA,
        Severity.MEDIUM,
    )
)
MFA_DISABLED = _register(
    EventDefinition(
        "mfa_disabled",
        Category.MFA,
        Severity.HIGH,
        description="MFA removal — paged because it is a common ATO post-step.",
    )
)
MFA_RECOVERY_CODES_REGENERATED = _register(
    EventDefinition(
        "mfa_recovery_codes_regenerated",
        Category.MFA,
        Severity.MEDIUM,
    )
)
WEBAUTHN_REGISTER_SUCCESS = _register(
    EventDefinition(
        "webauthn_register_success",
        Category.MFA,
        Severity.INFO,
    )
)
WEBAUTHN_REGISTER_FAILED = _register(
    EventDefinition(
        "webauthn_register_failed",
        Category.MFA,
        Severity.LOW,
    )
)
WEBAUTHN_LOGIN_SUCCESS = _register(
    EventDefinition(
        "webauthn_login_success",
        Category.MFA,
        Severity.INFO,
    )
)
WEBAUTHN_LOGIN_FAILED = _register(
    EventDefinition(
        "webauthn_login_failed",
        Category.MFA,
        Severity.LOW,
    )
)

# SSO ------------------------------------------------------------------
SSO_SAML_LOGIN_SUCCESS = _register(
    EventDefinition(
        "sso_saml_login_success",
        Category.SSO,
        Severity.INFO,
    )
)
SSO_SAML_UNKNOWN_TENANT = _register(
    EventDefinition(
        "sso_saml_unknown_tenant",
        Category.SSO,
        Severity.MEDIUM,
    )
)
SSO_SAML_RESPONSE_REJECTED = _register(
    EventDefinition(
        "sso_saml_response_rejected",
        Category.SSO,
        Severity.HIGH,
    )
)
SSO_OIDC_LOGIN_SUCCESS = _register(
    EventDefinition(
        "sso_oidc_login_success",
        Category.SSO,
        Severity.INFO,
    )
)
SSO_OIDC_ID_TOKEN_REJECTED = _register(
    EventDefinition(
        "sso_oidc_id_token_rejected",
        Category.SSO,
        Severity.HIGH,
    )
)
SSO_OIDC_JIT_BLOCKED = _register(
    EventDefinition(
        "sso_oidc_jit_blocked",
        Category.SSO,
        Severity.MEDIUM,
    )
)

# API keys -------------------------------------------------------------
API_CLIENT_CREATED = _register(
    EventDefinition(
        "api_client_created",
        Category.API_KEY,
        Severity.INFO,
    )
)
API_CLIENT_DELETED = _register(
    EventDefinition(
        "api_client_deleted",
        Category.API_KEY,
        Severity.MEDIUM,
    )
)
API_KEY_CREATED = _register(
    EventDefinition(
        "api_key_created",
        Category.API_KEY,
        Severity.INFO,
    )
)
API_KEY_ROTATED = _register(
    EventDefinition(
        "api_key_rotated",
        Category.API_KEY,
        Severity.MEDIUM,
    )
)
API_KEY_REVOKED = _register(
    EventDefinition(
        "api_key_revoked",
        Category.API_KEY,
        Severity.MEDIUM,
    )
)

# Account / privilege --------------------------------------------------
ROLE_CHANGED = _register(
    EventDefinition(
        "role_changed",
        Category.ACCOUNT,
        Severity.HIGH,
        description="Privilege change — page if target gains admin.",
    )
)
ACCOUNT_DELETION_REQUESTED = _register(
    EventDefinition(
        "account_deletion_requested",
        Category.ACCOUNT,
        Severity.MEDIUM,
    )
)

# Detection alerts -----------------------------------------------------
DETECTION_BRUTE_FORCE = _register(
    EventDefinition(
        "detection_brute_force",
        Category.DETECTION,
        Severity.HIGH,
        description="Threshold of failed logins from one bucket exceeded.",
    )
)
DETECTION_IMPOSSIBLE_TRAVEL = _register(
    EventDefinition(
        "detection_impossible_travel",
        Category.DETECTION,
        Severity.HIGH,
        description="Two successful logins from incompatible locations within a short window.",
    )
)
DETECTION_MASS_EXPORT = _register(
    EventDefinition(
        "detection_mass_export",
        Category.DETECTION,
        Severity.HIGH,
        description="Single user exported / generated more than the abuse threshold.",
    )
)
DETECTION_PRIV_ESCALATION = _register(
    EventDefinition(
        "detection_priv_escalation",
        Category.DETECTION,
        Severity.HIGH,
    )
)
# Step-up re-authentication ----------------------------------------
STEP_UP_PASSWORD_FAILED = _register(
    EventDefinition(
        "step_up_password_failed",
        Category.AUTH,
        Severity.MEDIUM,
    )
)
STEP_UP_PASSWORD_SUCCESS = _register(
    EventDefinition(
        "step_up_password_success",
        Category.AUTH,
        Severity.LOW,
    )
)
STEP_UP_TOTP_FAILED = _register(
    EventDefinition(
        "step_up_totp_failed",
        Category.AUTH,
        Severity.MEDIUM,
    )
)
STEP_UP_TOTP_SUCCESS = _register(
    EventDefinition(
        "step_up_totp_success",
        Category.AUTH,
        Severity.LOW,
    )
)

# WebAuthn ----------------------------------------------------------
WEBAUTHN_CREDENTIAL_REGISTERED = _register(
    EventDefinition(
        "webauthn_credential_registered",
        Category.AUTH,
        Severity.LOW,
    )
)
WEBAUTHN_AUTHN_FAILED = _register(
    EventDefinition(
        "webauthn_authn_failed",
        Category.AUTH,
        Severity.MEDIUM,
    )
)
WEBAUTHN_AUTHN_SUCCESS = _register(
    EventDefinition(
        "webauthn_authn_success",
        Category.AUTH,
        Severity.LOW,
    )
)
WEBAUTHN_CREDENTIAL_REVOKED = _register(
    EventDefinition(
        "webauthn_credential_revoked",
        Category.AUTH,
        Severity.MEDIUM,
    )
)

# SSO failure modes -------------------------------------------------
SSO_SAML_UNSOLICITED_RESPONSE = _register(
    EventDefinition(
        "sso_saml_unsolicited_response",
        Category.AUTH,
        Severity.HIGH,
        description="ACS endpoint received a SAML response without a matching AuthnRequest binding.",
    )
)
SSO_SAML_PROVISIONING_DENIED = _register(
    EventDefinition(
        "sso_saml_provisioning_denied",
        Category.AUTH,
        Severity.MEDIUM,
    )
)
SSO_OIDC_CALLBACK_IDP_ERROR = _register(
    EventDefinition(
        "sso_oidc_callback_idp_error",
        Category.AUTH,
        Severity.MEDIUM,
    )
)
SSO_OIDC_STATE_MISMATCH = _register(
    EventDefinition(
        "sso_oidc_state_mismatch",
        Category.AUTH,
        Severity.HIGH,
        description="OIDC callback state cookie did not match the IdP-returned state.",
    )
)


DETECTION_AUDIT_CHAIN_BREAK = _register(
    EventDefinition(
        "detection_audit_chain_break",
        Category.DETECTION,
        Severity.CRITICAL,
        sensitivity=Sensitivity.RESTRICTED,
        description="Hash chain verification failed — possible tampering.",
    )
)
DETECTION_MFA_BYPASS_ATTEMPT = _register(
    EventDefinition(
        "detection_mfa_bypass_attempt",
        Category.DETECTION,
        Severity.HIGH,
        description="Login succeeded for an MFA-enrolled account without an MFA factor.",
    )
)
DETECTION_SECRET_SCAN_HIT = _register(
    EventDefinition(
        "detection_secret_scan_hit",
        Category.DETECTION,
        Severity.HIGH,
        sensitivity=Sensitivity.RESTRICTED,
        description="Secret scanner flagged a repository or env value.",
    )
)
DETECTION_ERROR_SPIKE = _register(
    EventDefinition(
        "detection_error_spike",
        Category.DETECTION,
        Severity.HIGH,
        description="Application error rate exceeded the rolling baseline.",
    )
)
DETECTION_DEPENDENCY_VULN = _register(
    EventDefinition(
        "detection_dependency_vulnerability",
        Category.DETECTION,
        Severity.HIGH,
        description="A new high/critical dependency vulnerability was introduced.",
    )
)
DETECTION_ABNORMAL_AI_USAGE = _register(
    EventDefinition(
        "detection_abnormal_ai_usage",
        Category.DETECTION,
        Severity.MEDIUM,
        description="AI tool usage exceeded the per-user abnormal-volume threshold.",
    )
)

# Data / export -------------------------------------------------------
DOCUMENT_EXPORT_COMPLETED = _register(
    EventDefinition(
        "document_export_completed",
        Category.DATA,
        Severity.LOW,
        description="A user-facing export (CSV / JSON / archive) finished.",
    )
)
DOCUMENT_EXPORT_FAILED = _register(
    EventDefinition(
        "document_export_failed",
        Category.DATA,
        Severity.LOW,
    )
)

# Retention -----------------------------------------------------------
AUDIT_RETENTION_PURGE = _register(
    EventDefinition(
        "audit_retention_purge",
        Category.ADMIN,
        Severity.MEDIUM,
        sensitivity=Sensitivity.RESTRICTED,
        description="Audit retention worker purged rows past the retention window.",
    )
)


def get_definition(event_type: str) -> EventDefinition:
    """Return the registered definition or a safe ``UNKNOWN`` placeholder.

    We never raise here so a typo in a brand-new emit site cannot drop
    the event; instead the verifier reports "unregistered event type"
    and we fix the registration in a follow-up PR.
    """
    defn = _REGISTRY.get(event_type)
    if defn is not None:
        return defn
    return EventDefinition(
        event_type=event_type,
        category=Category.SECURITY,
        severity=Severity.INFO,
        sensitivity=Sensitivity.INTERNAL,
        description="Unregistered event type — add to audit_chain registry.",
    )


def all_definitions() -> Iterable[EventDefinition]:
    return tuple(_REGISTRY.values())


# ---------------------------------------------------------------------------
# Field-level redaction
# ---------------------------------------------------------------------------


_MAX_STRING_LEN = 2_000  # truncate long blobs so a single event can't blow up the row


def _sanitize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        cleaned = _apply_secondary_redactors(redact_for_logs(value))
        if len(cleaned) > _MAX_STRING_LEN:
            return cleaned[:_MAX_STRING_LEN] + "…[truncated]"
        return cleaned
    if isinstance(value, Mapping):
        return {str(k): _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_sanitize_value(v) for v in value]
    # Fallback: stringify then redact.
    return _sanitize_value(str(value))


def sanitize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a deep-copied, redacted, truncated metadata dict.

    Idempotent — running it twice yields the same output. Always returns
    a dict (never None) so downstream code can ``json.dumps`` without
    branching.
    """
    if not metadata:
        return {}
    cleaned = _sanitize_value(dict(metadata))
    return cleaned if isinstance(cleaned, dict) else {"value": cleaned}


# ---------------------------------------------------------------------------
# Hash chain
# ---------------------------------------------------------------------------


GENESIS_HASH = "0" * 64  # used when the chain has no prior row


def canonical_payload(
    *,
    event_id: str,
    event_type: str,
    category: str,
    severity: str,
    sensitivity: str,
    user_id: str | None,
    request_ip: str | None,
    session_id: str | None,
    request_id: str | None,
    metadata: Mapping[str, Any],
    created_at_iso: str,
    # Extended canonical contract (SOC 2 / ISO 27001 audit-row required):
    actor_id: str | None = None,
    actor_type: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    tenant_id: str | None = None,
    user_agent: str | None = None,
    outcome: str | None = None,
) -> str:
    """Deterministic JSON encoding of an event for hashing.

    The exact byte sequence matters: any change here invalidates every
    historical hash. ``sort_keys=True`` + ``separators`` give us a stable
    representation across Python versions.

    The canonical row models the SOC 2 / ISO 27001 / HIPAA audit-record
    contract: *who* (actor + actor type), *what* (action + target),
    *where* (tenant + ip + user agent), *when* (created_at), *outcome*,
    plus the always-present correlation fields and metadata payload.
    Optional fields are still hashed (as JSON ``null``) so the chain
    catches any later attempt to backfill them.
    """
    payload = {
        "event_id": event_id,
        "event_type": event_type,
        "category": category,
        "severity": severity,
        "sensitivity": sensitivity,
        "user_id": user_id,
        "request_ip": request_ip,
        "session_id": session_id,
        "request_id": request_id,
        "metadata": metadata,
        "created_at": created_at_iso,
        # Extended fields — always present in canonical, value may be null.
        "actor_id": actor_id,
        "actor_type": actor_type,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "tenant_id": tenant_id,
        "user_agent": user_agent,
        "outcome": outcome,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_event_hash(prev_hash: str | None, canonical: str) -> str:
    """``sha256(prev_hash || ":" || canonical)``.

    Using a separator stops a length-extension trick where the attacker
    moves bytes from ``canonical`` into ``prev_hash`` and gets the same
    hash. ``prev_hash`` defaults to ``GENESIS_HASH`` for the very first
    event so the chain has a well-defined root.
    """
    base = (prev_hash or GENESIS_HASH).strip().lower()
    h = hashlib.sha256()
    h.update(base.encode("ascii"))
    h.update(b":")
    h.update(canonical.encode("utf-8"))
    return h.hexdigest()


def link_event(
    prev_hash: str | None,
    *,
    event_id: str,
    event_type: str,
    user_id: str | None,
    request_ip: str | None,
    session_id: str | None,
    request_id: str | None,
    metadata: Mapping[str, Any],
    created_at_iso: str,
    actor_id: str | None = None,
    actor_type: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    tenant_id: str | None = None,
    user_agent: str | None = None,
    outcome: str | None = None,
) -> tuple[EventDefinition, str, str]:
    """Convenience wrapper: resolve definition, build canonical, hash.

    Returns ``(definition, canonical_payload_str, event_hash)``.
    """
    defn = get_definition(event_type)
    canonical = canonical_payload(
        event_id=event_id,
        event_type=defn.event_type,
        category=defn.category.value,
        severity=defn.severity.value,
        sensitivity=defn.sensitivity.value,
        user_id=user_id,
        request_ip=request_ip,
        session_id=session_id,
        request_id=request_id,
        metadata=metadata,
        created_at_iso=created_at_iso,
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        target_type=target_type,
        target_id=target_id,
        tenant_id=tenant_id,
        user_agent=user_agent,
        outcome=outcome,
    )
    return defn, canonical, compute_event_hash(prev_hash, canonical)
