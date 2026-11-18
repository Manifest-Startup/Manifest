"""Manifest CLI sign-in: a browser-approved loopback flow with PKCE (ADR 0003).

1. ``manifest login`` listens on ``http://127.0.0.1:<port>/callback`` and opens
   ``GET /api/cli/authorize?redirect_uri=…&state=…&code_challenge=…&code_challenge_method=S256``.
2. The signed-in (non-guest) person confirms; the browser is sent to the loopback
   address with a one-time ``code`` and the CLI's ``state``.
3. The CLI posts ``code`` + ``code_verifier`` to ``POST /api/cli/token`` and gets a
   revocable CLI session token (``kind=cli``, labelled ``Manifest CLI · <hostname>``).

The code is a short-lived signed token (its own key and audience, so it can never be
used as a session) bound to the redirect URI and the PKCE challenge. A ``jti``
denylist in the shared cache (Redis when configured, in-process otherwise) makes it
single-use; PKCE means a stolen code is useless without the CLI's verifier anyway.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import jwt
from app.security.config import session_secret
from app.services.identity.sessions import CLI_SESSION_LABEL_PREFIX
from app.services.shared import cache

CODE_TTL_SECONDS = 120
CODE_AUDIENCE = "manifest-cli-code"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
CALLBACK_PATH = "/callback"
_STATE = re.compile(r"^[A-Za-z0-9._~-]{8,256}$")
_CHALLENGE = re.compile(r"^[A-Za-z0-9_-]{43,128}$")
_VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
_HOSTNAME_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

_used_lock = threading.Lock()
_used_codes: dict[str, float] = {}


class CliAuthError(ValueError):
    """A request the CLI flow refuses; ``code`` is an OAuth-style error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CodeGrant:
    user_id: str
    email: str | None
    browser_session_id: str | None
    auth_iat: int | None
    scope: str | None = None


def _key(purpose: str) -> bytes:
    return hashlib.sha256(f"{session_secret()}:{purpose}".encode()).digest()


def validate_loopback_redirect(redirect_uri: str | None) -> str:
    """Accept only ``http://127.0.0.1:<port>/callback`` or ``http://localhost:<port>/callback``."""
    value = (redirect_uri or "").strip()
    if not value or len(value) > 200:
        raise CliAuthError("invalid_redirect_uri", "redirect_uri is required.")
    parts = urlsplit(value)
    try:
        port = parts.port
    except ValueError:
        port = None
    if (
        parts.scheme != "http"
        or "@" in parts.netloc
        or parts.hostname not in LOOPBACK_HOSTS
        or port is None
        or not 1 <= port <= 65535
        or parts.path != CALLBACK_PATH
        or parts.query
        or parts.fragment
    ):
        raise CliAuthError(
            "invalid_redirect_uri",
            "redirect_uri must be http://127.0.0.1:<port>/callback or http://localhost:<port>/callback.",
        )
    return value


def validate_authorize_params(
    redirect_uri: str | None,
    state: str | None,
    code_challenge: str | None,
    code_challenge_method: str | None,
) -> str:
    """Validate everything ``/api/cli/authorize`` receives; returns the redirect URI."""
    uri = validate_loopback_redirect(redirect_uri)
    if not state or not _STATE.match(state):
        raise CliAuthError("invalid_request", "state must be 8-256 URL-safe characters.")
    if (code_challenge_method or "") != "S256":
        raise CliAuthError("invalid_request", "code_challenge_method must be S256.")
    if not code_challenge or not _CHALLENGE.match(code_challenge):
        raise CliAuthError("invalid_request", "code_challenge must be a base64url SHA-256 digest.")
    return uri


def confirm_token(browser_session_id: str | None, user_id: str, *params: str) -> str:
    """CSRF token for the Allow link, bound to this browser session and these params."""
    message = "\n".join([browser_session_id or "", user_id, *params]).encode()
    return hmac.new(_key("cli-confirm"), message, hashlib.sha256).hexdigest()


def confirm_token_valid(token: str | None, expected: str) -> bool:
    return bool(token) and hmac.compare_digest(str(token), expected)


def issue_code(
    *,
    user_id: str,
    email: str | None,
    browser_session_id: str | None,
    auth_iat: int | None,
    redirect_uri: str,
    code_challenge: str,
    audience: str = CODE_AUDIENCE,
    client_id: str | None = None,
    scope: str | None = None,
) -> str:
    """A one-time code; agents (ADR 0004) use their own ``audience`` and bind ``client_id``."""
    now = int(time.time())
    claims = {
        "aud": audience,
        "cid": client_id,
        "scope": scope,
        "sub": user_id,
        "email": email,
        "bsid": browser_session_id,
        "auth_iat": auth_iat,
        "ruri": redirect_uri,
        "chal": code_challenge,
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + CODE_TTL_SECONDS,
    }
    return jwt.encode(claims, _key("cli-code"), algorithm="HS256")


def _s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _claim_once(jti: str, expires_at: float) -> bool:
    """Mark a code as used; False if it was used before (here or on another worker)."""
    now = time.time()
    with _used_lock:
        for key in [k for k, exp in _used_codes.items() if exp < now]:
            _used_codes.pop(key, None)
        if jti in _used_codes or cache.cache_get(f"cli-code-used:{jti}"):
            return False
        _used_codes[jti] = expires_at
    cache.cache_set(f"cli-code-used:{jti}", True, CODE_TTL_SECONDS + 60)
    return True


def redeem_code(
    code: str | None,
    code_verifier: str | None,
    redirect_uri: str | None,
    *,
    audience: str = CODE_AUDIENCE,
    client_id: str | None = None,
) -> CodeGrant:
    """Check the code, its PKCE verifier, redirect URI and client, and spend it."""
    if not code or not code_verifier:
        raise CliAuthError("invalid_request", "code and code_verifier are required.")
    if not _VERIFIER.match(code_verifier):
        raise CliAuthError("invalid_grant", "code_verifier is malformed.")
    try:
        claims = jwt.decode(code, _key("cli-code"), algorithms=["HS256"], audience=audience)
    except jwt.ExpiredSignatureError:
        raise CliAuthError(
            "invalid_grant", "The sign-in code expired. Run `manifest login` again."
        ) from None
    except jwt.PyJWTError:
        raise CliAuthError("invalid_grant", "The sign-in code is invalid.") from None
    if redirect_uri is not None and redirect_uri != claims.get("ruri"):
        raise CliAuthError(
            "invalid_grant", "redirect_uri does not match the authorization request."
        )
    if (claims.get("cid") or None) != (client_id or None):
        raise CliAuthError("invalid_grant", "The code was issued to a different client.")
    if not hmac.compare_digest(_s256(code_verifier), str(claims.get("chal") or "")):
        raise CliAuthError("invalid_grant", "code_verifier does not match the code_challenge.")
    if not _claim_once(str(claims.get("jti") or ""), float(claims.get("exp") or 0)):
        raise CliAuthError("invalid_grant", "The sign-in code was already used.")
    return CodeGrant(
        user_id=str(claims["sub"]),
        email=claims.get("email"),
        browser_session_id=claims.get("bsid"),
        auth_iat=claims.get("auth_iat"),
        scope=claims.get("scope"),
    )


def session_label(hostname: str | None) -> str:
    """``Manifest CLI · <hostname>``, with the hostname reduced to safe characters."""
    clean = _HOSTNAME_UNSAFE.sub("-", (hostname or "").strip())[:64].strip("-.")
    return f"{CLI_SESSION_LABEL_PREFIX}{clean or 'unknown host'}"


def _reset_for_tests() -> None:
    with _used_lock:
        _used_codes.clear()
