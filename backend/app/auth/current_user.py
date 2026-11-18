import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from app.security.config import demo_mode_enabled, session_secret
from app.services.identity.sessions import (
    CLI_SESSION_IDLE_TIMEOUT_SECONDS,
    CLI_SESSION_TTL_DAYS,
    create_user_session,
    is_session_active,
    touch_session,
)
from app.utils.logger import logger
from dotenv import load_dotenv
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer


def _is_user_disabled(user_id: str) -> bool:
    """Return True if the user has been deactivated (e.g. by SCIM).

    Disabled accounts must not be able to use existing tokens — this is
    the second half of SCIM deprovisioning (the first half being the
    session revocation done at PATCH/DELETE time).
    """
    try:
        from app.db.database import get_db_connection

        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT disabled_at FROM users WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        return bool(row and row.get("disabled_at") is not None)
    except Exception as exc:  # pragma: no cover - fail-closed only on real check
        logger.debug("[auth_utils] disabled-user check failed (allowing): %s", exc)
        return False


if os.path.exists(".env"):
    load_dotenv()

security = HTTPBearer()

SESSION_SECRET = session_secret()

# Backward-compatible aliases used by older tests/routes.
SUPABASE_JWT_SECRET = SESSION_SECRET
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://test.supabase.co")

DEMO_MODE = demo_mode_enabled()
if DEMO_MODE and not os.getenv("DEMO_MODE"):
    logger.info("[auth_utils] DEMO_MODE auto-enabled for non-production local development")
# .env can contain empty keys (e.g. DEMO_USER_EMAIL=) — use defaults instead of a blank value.
DEMO_USER_ID = os.getenv("DEMO_USER_ID", "demo-user-123") or "demo-user-123"
DEMO_USER_EMAIL = (
    os.getenv("DEMO_USER_EMAIL", "hello@manifeststartup.com") or "hello@manifeststartup.com"
)


def _extract_token(request: Request):
    """Try to pull the session token from either an HTTP-only cookie or
    from an `Authorization: Bearer <token>` header.

    Returns:
        str | None – The raw JWT if found, otherwise None.
    """
    token = request.cookies.get("session_token")
    if token:
        return token

    token = request.cookies.get("access_token")
    if token:
        return token

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split("Bearer ")[1]
        return token

    return None


def generate_demo_token(user_id: str, email: str) -> str:
    """Create a signed JWT for demo mode."""
    payload = {
        "sub": user_id,
        "email": email,
        "iss": "manifest-demo",
    }
    return jwt.encode(payload, SESSION_SECRET, algorithm="HS256")


SESSION_TTL = timedelta(days=7)


def create_session_token(
    user_id: str,
    email: str | None = None,
    request: Request | None = None,
) -> str:
    """Mint the Manifest session JWT (HS256) backed by a ``user_sessions`` row.

    ``auth_iat`` records when the person actually signed in (with Open Media);
    ``app.security.step_up`` treats a recent one as a fresh re-authentication.
    """
    session_id = create_user_session(user_id, request)
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "email": email,
        "sid": session_id,
        "iat": now,
        "auth_iat": int(now.timestamp()),
        "exp": now + SESSION_TTL,
    }
    return jwt.encode(payload, SESSION_SECRET, algorithm="HS256")


# CLI and AI-agent sessions (ADR 0003, 0004): longer idle window, label kept on use.
LONG_LIVED_KINDS = frozenset({"cli", "agent"})


def create_cli_session_token(
    user_id: str,
    *,
    email: str | None,
    label: str,
    auth_iat: int | None,
    request: Request | None = None,
    kind: str = "cli",
    token_ttl: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, datetime]:
    """Mint a revocable, longer-lived Manifest CLI session (ADR 0003).

    ``auth_iat`` is copied from the browser session that approved the CLI, so a CLI
    token never looks like a fresher sign-in than the person actually did.
    Returns the token and its expiry.
    """
    session_id = create_user_session(user_id, request, ttl_days=CLI_SESSION_TTL_DAYS, label=label)
    now = datetime.now(UTC)
    expires_at = now + (token_ttl or timedelta(days=CLI_SESSION_TTL_DAYS))
    payload = {
        **(extra_claims or {}),
        "sub": user_id,
        "email": email,
        "sid": session_id,
        "kind": kind,
        "iat": now,
        "auth_iat": int(auth_iat or now.timestamp()),
        "exp": expires_at,
    }
    return jwt.encode(payload, SESSION_SECRET, algorithm="HS256"), expires_at


def _session_is_active(payload: dict[str, Any]) -> bool:
    """The ``user_sessions`` row behind a token is live (tokens without ``sid`` pass)."""
    session_id, user_id = payload.get("sid"), payload.get("sub")
    if not session_id or not user_id:
        return True
    if payload.get("kind") in LONG_LIVED_KINDS:
        return is_session_active(
            str(session_id), str(user_id), idle_timeout_seconds=CLI_SESSION_IDLE_TIMEOUT_SECONDS
        )
    return is_session_active(str(session_id), str(user_id))


def _touch(payload: dict[str, Any], request: Request) -> None:
    session_id = payload.get("sid")
    if payload.get("kind") in LONG_LIVED_KINDS:
        touch_session(str(session_id) if session_id else None, request, keep_user_agent=True)
    else:
        touch_session(str(session_id) if session_id else None, request)


def decode_session_token(token: str) -> dict[str, Any] | None:
    """The verified claims of a session JWT, or None when it is invalid or expired."""
    try:
        return jwt.decode(token, SESSION_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        logger.info("[auth_utils] Session token expired")
        return None
    except Exception as e:
        logger.info("[auth_utils] Failed to decode session token: %s", type(e).__name__)
        return None


def get_current_user_id(request: Request):
    """Decode the session JWT from the incoming request and return the user_id
    (`sub` claim). Raises HTTP 401 if the token is missing or invalid.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    try:
        payload = jwt.decode(
            token,
            SESSION_SECRET,
            algorithms=["HS256"],
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user ID")

        if not _session_is_active(payload):
            raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")

        if _is_user_disabled(user_id):
            logger.info("[auth_utils] Token rejected: user disabled (user_id=%s)", user_id)
            raise HTTPException(status_code=403, detail="Account disabled")

        _touch(payload, request)
        return user_id
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        logger.info("[auth_utils] Token has expired")
        raise HTTPException(status_code=401, detail="Token has expired") from None
    except Exception as e:
        logger.error(f"[auth_utils] Token validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token") from e


def get_current_user_id_optional(request: Request):
    """Same as get_current_user_id but returns None instead of raising
    an exception if the user is not authenticated.
    """
    token = _extract_token(request)
    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            SESSION_SECRET,
            algorithms=["HS256"],
        )
        user_id = payload.get("sub")
        if not _session_is_active(payload):
            return None
        if user_id and _is_user_disabled(user_id):
            return None
        _touch(payload, request)
        return user_id
    except Exception as e:
        logger.info(f"[auth_utils] Token validation failed (optional): {e}")
        return None


def get_current_token_payload_optional(request: Request) -> dict | None:
    token = _extract_token(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, SESSION_SECRET, algorithms=["HS256"])
        if not _session_is_active(payload):
            return None
        _touch(payload, request)
        return payload
    except Exception:
        return None


def get_current_session_id_optional(request: Request) -> str | None:
    payload = get_current_token_payload_optional(request)
    if not payload:
        return None
    session_id = payload.get("sid")
    return str(session_id) if session_id else None


def require_user_id(request: Request) -> str:
    """FastAPI dependency: the signed-in user's id, or HTTP 401."""
    return get_current_user_id(request)
