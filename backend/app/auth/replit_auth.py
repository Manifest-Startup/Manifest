import os
import uuid
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from app.db.database import get_db_connection
from app.security.config import session_secret
from app.services.identity.sessions import create_user_session, is_session_active, touch_session
from app.utils.logger import logger
from fastapi import Request

REPL_ID = os.environ.get("REPL_ID")
ISSUER_URL = os.environ.get("ISSUER_URL", "https://replit.com/oidc")
SESSION_SECRET = session_secret()


class ReplitAuth:
    def __init__(self):
        self.client_id = REPL_ID
        self.issuer_url = ISSUER_URL
        self.token_url = f"{ISSUER_URL}/token"
        self.auth_url = f"{ISSUER_URL}/auth"
        self.userinfo_url = f"{ISSUER_URL}/userinfo"
        self.end_session_url = f"{ISSUER_URL}/session/end"
        self.scopes = ["openid", "profile", "email", "offline_access"]

    def _generate_pkce(self) -> tuple[str, str]:
        import base64
        import hashlib

        code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8").rstrip("=")
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest())
            .decode("utf-8")
            .rstrip("=")
        )
        return code_verifier, code_challenge

    def prepare_login(self, redirect_uri: str) -> tuple[str, str, str]:
        state = uuid.uuid4().hex
        code_verifier, code_challenge = self._generate_pkce()

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "login consent",
        }

        return f"{self.auth_url}?{urlencode(params)}", state, code_verifier

    async def exchange_code(
        self, code: str, code_verifier: str, redirect_uri: str
    ) -> dict[str, Any] | None:
        if not code_verifier:
            logger.error("[ReplitAuth] Missing PKCE code verifier in callback")
            return None

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.token_url,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "client_id": self.client_id,
                        "code_verifier": code_verifier,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if response.status_code != 200:
                    logger.error(
                        f"[ReplitAuth] Token exchange failed: {response.status_code} {response.text}"
                    )
                    return None

                return response.json()
            except Exception as e:
                logger.error(f"[ReplitAuth] Token exchange error: {e}")
                return None

    async def refresh_token(self, refresh_token: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": self.client_id,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if response.status_code != 200:
                    logger.error(f"[ReplitAuth] Token refresh failed: {response.status_code}")
                    return None

                return response.json()
            except Exception as e:
                logger.error(f"[ReplitAuth] Token refresh error: {e}")
                return None

    def decode_id_token(self, id_token: str, *, nonce: str | None = None) -> dict[str, Any] | None:
        """Verify an ID token's signature, issuer, audience, and expiry.

        Closes SEC-003. Previously this function called jwt.decode with
        ``verify_signature=False`` which accepted forged tokens. We now
        delegate to ``app.security.oidc_verification.verify_id_token``
        which fetches the IdP JWKS and validates the JWT in full.
        """
        from app.security.oidc_verification import verify_id_token

        return verify_id_token(
            id_token,
            audience=self.client_id,
            issuer=self.issuer_url,
            nonce=nonce,
        )

    def get_logout_url(self, post_logout_redirect_uri: str) -> str:
        from urllib.parse import urlencode

        params = {
            "client_id": self.client_id,
            "post_logout_redirect_uri": post_logout_redirect_uri,
        }
        return f"{self.end_session_url}?{urlencode(params)}"


replit_auth = ReplitAuth()


def create_session_token(
    user_id: str,
    replit_id: str | None = None,
    email: str | None = None,
    request: Request | None = None,
) -> str:
    session_id = create_user_session(user_id, request)
    now = datetime.utcnow()
    payload = {
        "sub": user_id,
        "email": email,
        "sid": session_id,
        "iat": now,
        # ``auth_iat`` records the moment the user actually presented credentials
        # — used by the step-up dependency to short-circuit recent re-auth checks.
        "auth_iat": int(now.timestamp()),
        "exp": now + timedelta(days=7),
    }
    if replit_id:
        payload["replit_id"] = replit_id

    # Stamp the user's current password_changed_at into the token so that
    # a password reset invalidates every session issued before that moment.
    try:
        from app.services.identity.password_reset import get_password_changed_at_epoch

        pwd_iat = get_password_changed_at_epoch(user_id)
        if pwd_iat is not None:
            payload["pwd_iat"] = int(pwd_iat)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("[ReplitAuth] Could not stamp pwd_iat into token: %s", exc)

    return jwt.encode(payload, SESSION_SECRET, algorithm="HS256")


def decode_session_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, SESSION_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        logger.info("[ReplitAuth] Session token expired")
        return None
    except Exception as e:
        logger.error(f"[ReplitAuth] Failed to decode session token: {e}")
        return None


def save_or_update_user(claims: dict[str, Any]) -> str:
    replit_id = str(claims.get("sub"))
    email = claims.get("email")
    first_name = claims.get("first_name")
    last_name = claims.get("last_name")
    profile_image_url = claims.get("profile_image_url")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users WHERE replit_id = %s", (replit_id,))
            existing = cur.fetchone()

            if existing:
                user_id = str(existing.get("user_id", ""))
                cur.execute(
                    """
                    UPDATE users 
                    SET email = COALESCE(%s, email),
                        first_name = COALESCE(%s, first_name),
                        last_name = COALESCE(%s, last_name),
                        profile_picture_url = COALESCE(%s, profile_picture_url),
                        updated_at = NOW()
                    WHERE replit_id = %s
                """,
                    (email, first_name, last_name, profile_image_url, replit_id),
                )
                logger.info(f"[ReplitAuth] Updated existing user: {user_id}")
            else:
                cur.execute(
                    """
                    INSERT INTO users (replit_id, email, first_name, last_name, profile_picture_url, auth_provider)
                    VALUES (%s, %s, %s, %s, %s, 'replit')
                    RETURNING user_id
                """,
                    (replit_id, email, first_name, last_name, profile_image_url),
                )
                result = cur.fetchone()
                user_id = str(result.get("user_id", "")) if result else ""
                logger.info(f"[ReplitAuth] Created new user: {user_id}")

            conn.commit()
            return str(user_id)


def get_current_user_from_session(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split("Bearer ")[1]

    if not token:
        return None

    payload = decode_session_token(token)
    if not payload:
        return None

    # Reject any token that was issued before the user's most recent
    # password change (e.g. after a successful password reset). Mirrors
    # the same check enforced by ``app.auth.current_user``.
    user_id = payload.get("sub") or payload.get("user_id")
    session_id = payload.get("sid")
    if user_id and session_id and not is_session_active(str(session_id), str(user_id)):
        return None
    if user_id:
        try:
            from app.services.identity.password_reset import (
                get_password_changed_at_epoch,
            )

            current = get_password_changed_at_epoch(str(user_id))
            if current is not None:
                token_pwd_iat = payload.get("pwd_iat")
                if token_pwd_iat is None:
                    iat = payload.get("iat")
                    try:
                        token_pwd_iat = int(iat) if iat is not None else None
                    except (TypeError, ValueError):
                        token_pwd_iat = None
                if token_pwd_iat is not None and int(token_pwd_iat) < int(current):
                    logger.info(
                        "[ReplitAuth] Rejecting session token: password changed "
                        "after issue (user_id=%s)",
                        user_id,
                    )
                    return None
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("[ReplitAuth] pwd invalidation check failed: %s", exc)

    touch_session(str(session_id) if session_id else None, request)
    return payload
