import os

import jwt
from app.security.config import demo_mode_enabled, session_secret
from app.services.identity.sessions import is_session_active, touch_session
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
DEMO_USER_PASSWORD = os.getenv("DEMO_USER_PASSWORD", "manifest") or "manifest"


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


def _is_token_password_invalidated(user_id: str, payload: dict) -> bool:
    """Return True if the user's password has been changed since this
    token was issued. Used to invalidate stale JWTs after a reset.
    """
    try:
        from app.services.identity.password_reset import get_password_changed_at_epoch

        current = get_password_changed_at_epoch(user_id)
        if current is None:
            return False
        token_pwd_iat = payload.get("pwd_iat")
        # If the token was issued before pwd tracking existed, fall back to
        # comparing against `iat`.
        if token_pwd_iat is None:
            iat = payload.get("iat")
            if iat is None:
                return False
            try:
                token_pwd_iat = int(iat)
            except (TypeError, ValueError):
                return False
        return int(token_pwd_iat) < int(current)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("[auth_utils] pwd invalidation check failed: %s", exc)
        return False


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

        session_id = payload.get("sid")
        if session_id and not is_session_active(str(session_id), str(user_id)):
            raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")

        if _is_token_password_invalidated(user_id, payload):
            logger.info(
                "[auth_utils] Token rejected: password changed after issue (user_id=%s)", user_id
            )
            raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")

        if _is_user_disabled(user_id):
            logger.info("[auth_utils] Token rejected: user disabled (user_id=%s)", user_id)
            raise HTTPException(status_code=403, detail="Account disabled")

        touch_session(str(session_id) if session_id else None, request)
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
        session_id = payload.get("sid")
        if session_id and user_id and not is_session_active(str(session_id), str(user_id)):
            return None
        if user_id and _is_token_password_invalidated(user_id, payload):
            logger.info("[auth_utils] Optional token rejected: password changed after issue")
            return None
        if user_id and _is_user_disabled(user_id):
            return None
        touch_session(str(session_id) if session_id else None, request)
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
        user_id = payload.get("sub")
        session_id = payload.get("sid")
        if user_id and _is_token_password_invalidated(user_id, payload):
            return None
        if session_id and user_id and not is_session_active(str(session_id), str(user_id)):
            return None
        touch_session(str(session_id) if session_id else None, request)
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
