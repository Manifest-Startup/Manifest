import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.db.database import get_database_url, get_db_connection
from app.utils.auth_utils import get_current_user_id_optional
from app.utils.logger import logger
from fastapi import Request, Response

PRIVACY_CONSENT_COOKIE = "manifest_privacy_consent"
PRIVACY_VISITOR_COOKIE = "manifest_privacy_visitor"
ANALYTICS_VISITOR_COOKIE = "visitor_id"
PRIVACY_POLICY_VERSION = os.getenv("MANIFEST_PRIVACY_POLICY_VERSION", "2026-04")
PRIVACY_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 180
_IP_HASH_SALT = os.getenv("MANIFEST_PRIVACY_IP_HASH_SALT", "manifest-privacy")


def default_privacy_preferences() -> dict[str, Any]:
    return {
        "has_stored_preference": False,
        "necessary_enabled": True,
        "analytics_enabled": False,
        "communications_enabled": False,
        # Granular GDPR/CCPA purposes (Task 15). Each purpose is its own
        # boolean so the frontend can render per-purpose toggles and the
        # backend can prove per-purpose lawful basis at audit time.
        "marketing_enabled": False,
        "ai_training_enabled": False,
        "cookies_enabled": False,
        "do_not_sell_or_share": False,
        "policy_version": PRIVACY_POLICY_VERSION,
        "consent_updated_at": None,
        "source": "default",
    }


# Purposes the consent ledger tracks. Adding a new purpose here flows
# through the cookie payload, the JSONB consent_payload column, and the
# /api/privacy/consent + /withdraw responses without further changes.
GRANULAR_PURPOSES: tuple = (
    "analytics_enabled",
    "communications_enabled",
    "marketing_enabled",
    "ai_training_enabled",
    "cookies_enabled",
    "do_not_sell_or_share",
)


def normalize_privacy_preferences(
    payload: dict[str, Any] | None,
    *,
    source: str | None = None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    base = default_privacy_preferences()
    payload = payload or {}
    base["has_stored_preference"] = bool(payload.get("has_stored_preference", True))
    for purpose in GRANULAR_PURPOSES:
        base[purpose] = bool(payload.get(purpose))
    base["policy_version"] = str(payload.get("policy_version") or PRIVACY_POLICY_VERSION)
    base["consent_updated_at"] = payload.get("consent_updated_at") or updated_at
    base["source"] = str(payload.get("source") or source or "settings")
    return base


def serialize_privacy_preferences(preferences: dict[str, Any]) -> str:
    serialized: dict[str, Any] = {
        purpose: bool(preferences.get(purpose)) for purpose in GRANULAR_PURPOSES
    }
    serialized["policy_version"] = str(preferences.get("policy_version") or PRIVACY_POLICY_VERSION)
    serialized["consent_updated_at"] = preferences.get("consent_updated_at")
    serialized["source"] = str(preferences.get("source") or "settings")
    return json.dumps(serialized, separators=(",", ":"))


def parse_privacy_preferences(raw_cookie: str | None) -> dict[str, Any]:
    if not raw_cookie:
        return default_privacy_preferences()
    try:
        payload = json.loads(raw_cookie)
    except (TypeError, ValueError):
        logger.warning("[privacy] Failed to parse consent cookie payload")
        return default_privacy_preferences()
    if not isinstance(payload, dict):
        return default_privacy_preferences()
    return normalize_privacy_preferences(payload, source="cookie")


def get_request_privacy_preferences(request: Request) -> dict[str, Any]:
    return parse_privacy_preferences(request.cookies.get(PRIVACY_CONSENT_COOKIE))


def analytics_enabled_for_request(request: Request) -> bool:
    preferences = get_request_privacy_preferences(request)
    return bool(
        preferences.get("has_stored_preference")
        and preferences.get("analytics_enabled")
        and not preferences.get("do_not_sell_or_share")
    )


def analytics_enabled_for_cookie_header(raw_cookie_header: str | None) -> bool:
    if not raw_cookie_header:
        return False
    cookies: dict[str, str] = {}
    for part in raw_cookie_header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies[name.strip()] = value.strip()
    preferences = parse_privacy_preferences(cookies.get(PRIVACY_CONSENT_COOKIE))
    return bool(
        preferences.get("has_stored_preference")
        and preferences.get("analytics_enabled")
        and not preferences.get("do_not_sell_or_share")
    )


def _hash_ip(request_ip: str | None) -> str | None:
    if not request_ip:
        return None
    digest = hashlib.sha256(f"{_IP_HASH_SALT}:{request_ip}".encode()).hexdigest()
    return digest


def _latest_preference_for(*, user_id: str | None, visitor_id: str | None) -> dict[str, Any] | None:
    if not get_database_url():
        return None
    if not user_id and not visitor_id:
        return None

    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            # ``consent_payload`` carries the granular purposes
            # (marketing/ai_training/cookies) the dedicated columns
            # don't yet have. We read both and let the JSONB win
            # when it has a value, falling back to the columns for
            # the three legacy purposes.
            if user_id:
                cur.execute(
                    """
                        SELECT analytics_enabled,
                               communications_enabled,
                               do_not_sell_or_share,
                               consent_payload,
                               policy_version,
                               consent_updated_at,
                               source
                        FROM privacy_consents
                        WHERE user_id = %s
                        ORDER BY consent_updated_at DESC
                        LIMIT 1
                        """,
                    (user_id,),
                )
            else:
                cur.execute(
                    """
                        SELECT analytics_enabled,
                               communications_enabled,
                               do_not_sell_or_share,
                               consent_payload,
                               policy_version,
                               consent_updated_at,
                               source
                        FROM privacy_consents
                        WHERE visitor_id = %s
                        ORDER BY consent_updated_at DESC
                        LIMIT 1
                        """,
                    (visitor_id,),
                )
            row = cur.fetchone()
    except Exception as exc:
        logger.warning("[privacy] Failed to load privacy consent: %s", exc)
        return None

    if not row:
        return None
    payload_blob = row.get("consent_payload") or {}
    if isinstance(payload_blob, str):
        try:
            payload_blob = json.loads(payload_blob)
        except (TypeError, ValueError):
            payload_blob = {}
    if not isinstance(payload_blob, dict):
        payload_blob = {}
    merged: dict[str, Any] = {
        "has_stored_preference": True,
        "policy_version": row.get("policy_version"),
        "consent_updated_at": (
            row.get("consent_updated_at").isoformat() if row.get("consent_updated_at") else None
        ),
        "source": row.get("source"),
    }
    # Granular purposes round-trip via the JSONB blob; the three legacy
    # columns are the source of truth for the legacy purposes only.
    for purpose in GRANULAR_PURPOSES:
        if purpose in payload_blob:
            merged[purpose] = bool(payload_blob[purpose])
        elif purpose in {"analytics_enabled", "communications_enabled", "do_not_sell_or_share"}:
            merged[purpose] = bool(row.get(purpose))
        else:
            merged[purpose] = False
    return normalize_privacy_preferences(merged, source="database")


def set_privacy_cookies(
    response: Response,
    preferences: dict[str, Any],
    *,
    privacy_visitor_id: str | None = None,
    analytics_visitor_id: str | None = None,
) -> None:
    response.set_cookie(
        key=PRIVACY_CONSENT_COOKIE,
        value=serialize_privacy_preferences(preferences),
        max_age=PRIVACY_COOKIE_MAX_AGE_SECONDS,
        httponly=False,
        samesite="Lax",
    )
    if privacy_visitor_id:
        response.set_cookie(
            key=PRIVACY_VISITOR_COOKIE,
            value=privacy_visitor_id,
            max_age=PRIVACY_COOKIE_MAX_AGE_SECONDS,
            httponly=True,
            samesite="Lax",
        )
    if analytics_visitor_id:
        response.set_cookie(
            key=ANALYTICS_VISITOR_COOKIE,
            value=analytics_visitor_id,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="Lax",
        )
    else:
        response.delete_cookie(ANALYTICS_VISITOR_COOKIE, samesite="Lax")


def get_effective_privacy_preferences(request: Request) -> dict[str, Any]:
    cookie_preferences = get_request_privacy_preferences(request)
    user_id = get_current_user_id_optional(request)
    visitor_id = request.cookies.get(PRIVACY_VISITOR_COOKIE)

    if user_id:
        db_preferences = _latest_preference_for(user_id=user_id, visitor_id=None)
        if db_preferences:
            return db_preferences
    if visitor_id:
        db_preferences = _latest_preference_for(user_id=None, visitor_id=visitor_id)
        if db_preferences:
            return db_preferences
    return cookie_preferences


def persist_privacy_preferences(
    request: Request,
    response: Response,
    payload: dict[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    normalized = normalize_privacy_preferences(
        payload,
        source=source,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    user_id = get_current_user_id_optional(request)
    privacy_visitor_id = request.cookies.get(PRIVACY_VISITOR_COOKIE) or str(uuid4())
    analytics_visitor_id = request.cookies.get(ANALYTICS_VISITOR_COOKIE)
    if normalized["analytics_enabled"] and not normalized["do_not_sell_or_share"]:
        analytics_visitor_id = analytics_visitor_id or str(uuid4())
    else:
        analytics_visitor_id = None

    if get_database_url():
        try:
            with get_db_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                        INSERT INTO privacy_consents (
                            user_id,
                            visitor_id,
                            source,
                            policy_version,
                            analytics_enabled,
                            communications_enabled,
                            do_not_sell_or_share,
                            consent_payload,
                            ip_hash
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                        """,
                    (
                        user_id,
                        privacy_visitor_id,
                        normalized["source"],
                        normalized["policy_version"],
                        normalized["analytics_enabled"],
                        normalized["communications_enabled"],
                        normalized["do_not_sell_or_share"],
                        json.dumps(
                            {
                                "necessary_enabled": True,
                                **{purpose: normalized[purpose] for purpose in GRANULAR_PURPOSES},
                            }
                        ),
                        _hash_ip(getattr(getattr(request, "client", None), "host", None)),
                    ),
                )
        except Exception as exc:
            logger.warning("[privacy] Failed to persist consent preference: %s", exc)

    set_privacy_cookies(
        response,
        normalized,
        privacy_visitor_id=privacy_visitor_id,
        analytics_visitor_id=analytics_visitor_id,
    )
    return normalized
