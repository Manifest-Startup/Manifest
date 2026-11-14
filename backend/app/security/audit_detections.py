"""Lightweight anomaly detections over the audit stream (SEC-068).

These detections are deliberately simple SQL window aggregates so they
run cheaply on every relevant emit without needing a separate stream
processor. Each detector returns ``True`` and emits a
``Category.DETECTION`` event when a threshold trips, ``False``
otherwise. Callers wire detectors into the corresponding emit sites
(login_failed, login_success, document_export_completed, role_changed)
so an alert fires within seconds of the underlying event.

Thresholds are intentionally conservative defaults — operators tune
them via env vars without redeploying.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from app.db.database import get_db_connection
from app.utils.logger import logger


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    try:
        return max(int(raw), 1) if raw else default
    except ValueError:
        return default


# --- Brute force ---------------------------------------------------------


_BRUTE_FORCE_THRESHOLD = _env_int("AUDIT_BRUTE_FORCE_THRESHOLD", 10)
_BRUTE_FORCE_WINDOW_S = _env_int("AUDIT_BRUTE_FORCE_WINDOW_S", 300)


def detect_brute_force(*, user_id: str | None, request_ip: str | None) -> bool:
    """Trip when login_failed exceeds the threshold for one bucket.

    "Bucket" = (user_id, request_ip) — we evaluate either dimension
    independently so a spray attack against many users from one IP
    still trips, and a credential-stuffing campaign hammering one
    user from many IPs trips too.
    """
    bucket_clauses = []
    params: list = []
    if user_id:
        bucket_clauses.append("user_id = %s")
        params.append(user_id)
    if request_ip:
        bucket_clauses.append("request_ip = %s")
        params.append(request_ip)
    if not bucket_clauses:
        return False
    window_start = datetime.now(timezone.utc) - timedelta(seconds=_BRUTE_FORCE_WINDOW_S)
    where = " OR ".join(bucket_clauses)
    sql = f"""
        SELECT COUNT(*) AS hits
        FROM security_audit_events
        WHERE event_type = 'login_failed'
          AND created_at >= %s
          AND ({where})
    """
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(sql, [window_start, *params])
            row = cur.fetchone() or {}
            hits = int(row.get("hits") or 0)
    except Exception as exc:
        logger.debug("[audit_detections] brute-force read failed: %s", exc)
        return False
    if hits < _BRUTE_FORCE_THRESHOLD:
        return False
    _emit_detection(
        "detection_brute_force",
        user_id=user_id,
        request_ip=request_ip,
        metadata={
            "hits": hits,
            "threshold": _BRUTE_FORCE_THRESHOLD,
            "window_seconds": _BRUTE_FORCE_WINDOW_S,
        },
    )
    return True


# --- Impossible travel ---------------------------------------------------


_IMPOSSIBLE_TRAVEL_WINDOW_S = _env_int("AUDIT_IMPOSSIBLE_TRAVEL_WINDOW_S", 3600)


def _ip_prefix(ip: str | None) -> str | None:
    """Coarse IPv4/IPv6 region key.

    No GeoIP DB ships with the app — this gives us a low-cost proxy:
    successful logins from two unrelated /16 IPv4 networks (or two
    unrelated IPv6 /48s) within ``WINDOW`` seconds is a strong signal
    of credential reuse. Operators with a real GeoIP feed can override
    this function in a future iteration.
    """
    if not ip:
        return None
    parts = ip.split(":")
    if len(parts) > 1:  # IPv6
        return ":".join(parts[:3]).lower()
    octets = ip.split(".")
    if len(octets) == 4:
        return ".".join(octets[:2])
    return ip


def detect_impossible_travel(*, user_id: str | None, request_ip: str | None) -> bool:
    """Trip when the same user has a recent successful login from a different region."""
    if not user_id or not request_ip:
        return False
    current_region = _ip_prefix(request_ip)
    if not current_region:
        return False
    window_start = datetime.now(timezone.utc) - timedelta(seconds=_IMPOSSIBLE_TRAVEL_WINDOW_S)
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT request_ip
                    FROM security_audit_events
                    WHERE event_type = 'login_success'
                      AND user_id = %s
                      AND created_at >= %s
                      AND request_ip IS NOT NULL
                      AND request_ip <> %s
                    ORDER BY created_at DESC
                    LIMIT 25
                    """,
                (user_id, window_start, request_ip),
            )
            rows = list(cur.fetchall() or [])
    except Exception as exc:
        logger.debug("[audit_detections] impossible-travel read failed: %s", exc)
        return False
    other_regions = {_ip_prefix(str(r.get("request_ip"))) for r in rows}
    other_regions.discard(None)
    other_regions.discard(current_region)
    if not other_regions:
        return False
    _emit_detection(
        "detection_impossible_travel",
        user_id=user_id,
        request_ip=request_ip,
        metadata={
            "current_region": current_region,
            "other_regions": sorted(r for r in other_regions if r),
            "window_seconds": _IMPOSSIBLE_TRAVEL_WINDOW_S,
        },
    )
    return True


# --- Mass export ---------------------------------------------------------


_MASS_EXPORT_THRESHOLD = _env_int("AUDIT_MASS_EXPORT_THRESHOLD", 50)
_MASS_EXPORT_WINDOW_S = _env_int("AUDIT_MASS_EXPORT_WINDOW_S", 600)


_EXPORT_EVENT_TYPES = {
    "document_generated",
    "document_exported",
    "data_export_requested",
    "pdf_generated",
}


def detect_mass_export(*, user_id: str | None, event_type: str) -> bool:
    """Trip when a single user racks up too many export-class events.

    The detector accepts the event_type that just fired so it can also
    be used to short-circuit on irrelevant events (cheap noop).
    """
    if not user_id or event_type not in _EXPORT_EVENT_TYPES:
        return False
    window_start = datetime.now(timezone.utc) - timedelta(seconds=_MASS_EXPORT_WINDOW_S)
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT COUNT(*) AS hits
                    FROM security_audit_events
                    WHERE user_id = %s
                      AND event_type = ANY(%s)
                      AND created_at >= %s
                    """,
                (user_id, list(_EXPORT_EVENT_TYPES), window_start),
            )
            row = cur.fetchone() or {}
            hits = int(row.get("hits") or 0)
    except Exception as exc:
        logger.debug("[audit_detections] mass-export read failed: %s", exc)
        return False
    if hits < _MASS_EXPORT_THRESHOLD:
        return False
    _emit_detection(
        "detection_mass_export",
        user_id=user_id,
        metadata={
            "hits": hits,
            "threshold": _MASS_EXPORT_THRESHOLD,
            "window_seconds": _MASS_EXPORT_WINDOW_S,
        },
    )
    return True


# --- Privilege escalation ------------------------------------------------


def detect_privilege_escalation(
    *,
    actor_user_id: str | None,
    target_user_id: str | None,
    new_role: str | None,
) -> bool:
    """Always alert when the target gains 'admin'.

    Role flips to admin are rare and should be visible in real time.
    The audit row itself is also still recorded as ``role_changed`` —
    this just adds a tagged DETECTION row that paging rules can match.
    """
    if (new_role or "").lower() != "admin":
        return False
    _emit_detection(
        "detection_priv_escalation",
        user_id=actor_user_id,
        metadata={
            "actor_user_id": actor_user_id,
            "target_user_id": target_user_id,
            "new_role": new_role,
        },
    )
    return True


# --- MFA bypass ----------------------------------------------------------


def detect_mfa_bypass_attempt(
    *,
    user_id: str | None,
    request_ip: str | None = None,
    reason: str | None = None,
) -> bool:
    """Page when a login completes for an MFA-enrolled user without MFA."""
    _emit_detection(
        "detection_mfa_bypass_attempt",
        user_id=user_id,
        request_ip=request_ip,
        metadata={"reason": reason or "mfa_required_but_skipped"},
    )
    return True


# --- Secret-scan / dep-vuln / error-spike (operational hooks) -----------


def detect_secret_scan_hit(*, source: str, identifier: str | None = None) -> None:
    _emit_detection(
        "detection_secret_scan_hit",
        metadata={"source": source, "identifier": (identifier or "")[:120]},
    )


def detect_dependency_vulnerability(
    *,
    package: str,
    severity: str,
    advisory_id: str | None = None,
) -> None:
    _emit_detection(
        "detection_dependency_vulnerability",
        metadata={"package": package, "severity": severity, "advisory_id": advisory_id},
    )


def detect_error_spike(*, window_seconds: int, error_count: int, baseline: float) -> None:
    _emit_detection(
        "detection_error_spike",
        metadata={
            "window_seconds": window_seconds,
            "error_count": error_count,
            "baseline": round(baseline, 2),
        },
    )


def detect_abnormal_ai_usage(
    *,
    user_id: str | None,
    window_seconds: int,
    call_count: int,
    threshold: int,
) -> None:
    _emit_detection(
        "detection_abnormal_ai_usage",
        user_id=user_id,
        metadata={
            "window_seconds": window_seconds,
            "call_count": call_count,
            "threshold": threshold,
        },
    )


# --- Internal emit -------------------------------------------------------


def _emit_detection(
    event_type: str,
    *,
    user_id: str | None = None,
    request_ip: str | None = None,
    metadata: dict | None = None,
) -> None:
    # Imported lazily to avoid a circular import (security_audit_service -> audit_detections).
    from app.services.compliance.security_audit import record_security_event

    try:
        record_security_event(
            event_type,
            user_id=user_id,
            request_ip=request_ip,
            metadata=metadata or {},
        )
    except Exception as exc:  # pragma: no cover - never break the caller
        logger.debug("[audit_detections] emit failed for %s: %s", event_type, exc)
