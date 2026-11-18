"""OAuth 2.1 for AI agents connecting to the Manifest MCP server (ADR 0004).

Any MCP client (Claude, ChatGPT, Codex, Cursor, VS Code, Gemini CLI…) can sign a person in:

- **Discovery.** ``/.well-known/oauth-protected-resource[/mcp]`` (RFC 9728) names this
  server as the authorization server for ``https://manifeststartup.com/mcp``;
  ``/.well-known/oauth-authorization-server`` (RFC 8414) lists the endpoints below.
- **Clients.** Either a Client ID Metadata Document (an ``https://`` ``client_id`` whose
  JSON lists its ``redirect_uris``), or Dynamic Client Registration (RFC 7591) at
  ``/api/oauth/register``. Registration is stateless: the ``client_id`` is the signed
  client metadata, so there is no table to grow or clean up.
- **Authorization.** Code flow with PKCE (S256 only), the same browser approval as the CLI
  (ADR 0003): a signed-in, non-guest person with a fresh Open Media sign-in clicks Allow.
- **Tokens.** The access token is a Manifest session JWT (``kind=agent``, 24 hours) backed
  by a ``user_sessions`` row labelled ``AI agent · <client name>``, so it shows up and can be
  revoked under Account → Security. The refresh token is bound to that session; refreshing
  rotates to a new session and revokes the old one, so a replayed refresh token fails.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import jwt
from app.security import safe_http
from app.security.config import session_secret
from app.services.identity.sessions import AGENT_SESSION_LABEL_PREFIX
from app.services.shared import cache

ISSUER = "https://manifeststartup.com"
RESOURCE = f"{ISSUER}/mcp"
SCOPE = "manifest"
CODE_AUDIENCE = "manifest-agent-code"
REFRESH_AUDIENCE = "manifest-agent-refresh"
ACCESS_TOKEN_SECONDS = 24 * 60 * 60
REFRESH_TOKEN_SECONDS = 30 * 24 * 60 * 60
CLIENT_PREFIX = "mcp_"
MAX_REDIRECT_URIS = 10
MAX_URI_LENGTH = 512
MAX_NAME_LENGTH = 80
METADATA_MAX_BYTES = 64 * 1024
METADATA_CACHE_SECONDS = 3600

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})
# Schemes that can never be a safe redirect target.
BLOCKED_SCHEMES = frozenset(
    {
        "javascript",
        "data",
        "file",
        "vbscript",
        "about",
        "blob",
        "ftp",
        "ws",
        "wss",
        "chrome",
        "intent",
    }
)
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]{1,40}$")
_UNSAFE_NAME = re.compile(r"[^\w .,'()&+:/-]+", re.UNICODE)


class AgentOAuthError(ValueError):
    """An OAuth error: ``code`` is the RFC 6749 error, the message its description."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class Client:
    client_id: str
    name: str
    redirect_uris: tuple[str, ...]
    verified_domain: str | None  # set for metadata-document clients (the https host)


def _key(purpose: str) -> bytes:
    return hashlib.sha256(f"{session_secret()}:{purpose}".encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def clean_name(name: object, fallback: str = "AI agent") -> str:
    text = _UNSAFE_NAME.sub("", str(name or "")).strip()[:MAX_NAME_LENGTH].strip()
    return text or fallback


# -- metadata documents -------------------------------------------------------------


def authorization_server_metadata() -> dict:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/api/oauth/authorize",
        "token_endpoint": f"{ISSUER}/api/oauth/token",
        "registration_endpoint": f"{ISSUER}/api/oauth/register",
        "revocation_endpoint": f"{ISSUER}/api/oauth/revoke",
        "scopes_supported": [SCOPE],
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        "client_id_metadata_document_supported": True,
        "service_documentation": f"{ISSUER}/agents.md",
    }


def protected_resource_metadata() -> dict:
    return {
        "resource": RESOURCE,
        "authorization_servers": [ISSUER],
        "scopes_supported": [SCOPE],
        "bearer_methods_supported": ["header"],
        "resource_name": "Manifest",
        "resource_documentation": f"{ISSUER}/agents.md",
    }


# -- redirect URIs -------------------------------------------------------------------


def _is_loopback(parts) -> bool:
    return parts.scheme == "http" and (parts.hostname or "") in LOOPBACK_HOSTS


def validate_redirect_uri(uri: object) -> str:
    """https anywhere, http on loopback only, or a private-use app scheme (RFC 8252)."""
    value = str(uri or "").strip()
    if not value or len(value) > MAX_URI_LENGTH:
        raise AgentOAuthError("invalid_redirect_uri", "Each redirect_uri must be 1-512 characters.")
    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if (
        parts.fragment
        or "@" in parts.netloc
        or not _SCHEME.match(scheme)
        or scheme in BLOCKED_SCHEMES
    ):
        raise AgentOAuthError("invalid_redirect_uri", f"redirect_uri is not allowed: {value}")
    if scheme == "http" and not _is_loopback(parts):
        raise AgentOAuthError(
            "invalid_redirect_uri", "http redirect URIs must use 127.0.0.1, [::1] or localhost."
        )
    if scheme == "https" and not parts.hostname:
        raise AgentOAuthError("invalid_redirect_uri", "https redirect URIs need a host.")
    return value


def redirect_matches(requested: str, registered: tuple[str, ...]) -> bool:
    """Exact match, except loopback URIs may use any port (RFC 8252 §7.3)."""
    if requested in registered:
        return True
    req = urlsplit(requested)
    if not _is_loopback(req):
        return False
    for uri in registered:
        reg = urlsplit(uri)
        if (
            _is_loopback(reg)
            and reg.hostname == req.hostname
            and reg.path == req.path
            and reg.query == req.query
        ):
            return True
    return False


# -- clients -------------------------------------------------------------------------


def register_client(metadata: dict) -> dict:
    """RFC 7591 registration. The returned ``client_id`` is the signed metadata itself."""
    if not isinstance(metadata, dict):
        raise AgentOAuthError("invalid_client_metadata", "Send a JSON object.")
    uris = metadata.get("redirect_uris")
    if not isinstance(uris, list) or not uris or len(uris) > MAX_REDIRECT_URIS:
        raise AgentOAuthError(
            "invalid_redirect_uri", f"redirect_uris must list 1-{MAX_REDIRECT_URIS} URIs."
        )
    clean = [validate_redirect_uri(u) for u in uris]
    method = metadata.get("token_endpoint_auth_method") or "none"
    if method != "none":
        raise AgentOAuthError(
            "invalid_client_metadata",
            "Only public clients (token_endpoint_auth_method none) are supported.",
        )
    for grant in metadata.get("grant_types") or ["authorization_code"]:
        if grant not in ("authorization_code", "refresh_token"):
            raise AgentOAuthError("invalid_client_metadata", f"Unsupported grant type: {grant}")
    name = clean_name(metadata.get("client_name"))
    body = _b64(
        json.dumps({"n": name, "r": clean, "t": int(time.time())}, separators=(",", ":")).encode()
    )
    sig = _b64(hmac.new(_key("agent-client"), body.encode(), hashlib.sha256).digest()[:16])
    client_id = f"{CLIENT_PREFIX}{body}.{sig}"
    return {
        "client_id": client_id,
        "client_id_issued_at": int(time.time()),
        "client_name": name,
        "redirect_uris": clean,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": SCOPE,
    }


def _registered_client(client_id: str) -> Client:
    try:
        body, sig = client_id[len(CLIENT_PREFIX) :].rsplit(".", 1)
        expected = _b64(hmac.new(_key("agent-client"), body.encode(), hashlib.sha256).digest()[:16])
        if not hmac.compare_digest(sig, expected):
            raise ValueError
        data = json.loads(_unb64(body))
        return Client(client_id, clean_name(data["n"]), tuple(data["r"]), None)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise AgentOAuthError(
            "invalid_client", "Unknown client_id. Register the client again.", 401
        ) from None


def _fetch_metadata_document(url: str) -> dict:
    """Fetch a Client ID Metadata Document through the SSRF-safe client (SEC-008)."""
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.path in ("", "/")
        or parts.fragment
        or "@" in parts.netloc
    ):
        raise AgentOAuthError(
            "invalid_client", "A URL client_id must be an https URL with a path.", 401
        )
    try:
        response = safe_http.safe_request(
            "GET",
            url,
            timeout=5,
            max_response_bytes=METADATA_MAX_BYTES,
            allow_redirects=False,
            headers={"accept": "application/json", "user-agent": "Manifest-OAuth/1.0"},
        )
    except Exception:  # SSRFError, connection and timeout errors alike
        raise AgentOAuthError(
            "invalid_client", "The client metadata document could not be fetched.", 401
        ) from None
    if response.status_code != 200 or len(response.content) > METADATA_MAX_BYTES:
        raise AgentOAuthError(
            "invalid_client", "The client metadata document could not be used.", 401
        )
    try:
        document = json.loads(response.content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise AgentOAuthError(
            "invalid_client", "The client metadata document is not JSON.", 401
        ) from None
    if not isinstance(document, dict) or document.get("client_id") != url:
        raise AgentOAuthError(
            "invalid_client", "The metadata document's client_id must equal its URL.", 401
        )
    return document


def resolve_client(client_id: str | None) -> Client:
    """A registered (signed) client or a Client ID Metadata Document URL."""
    value = (client_id or "").strip()
    if not value or len(value) > 4096:
        raise AgentOAuthError("invalid_client", "client_id is required.", 401)
    if value.startswith(CLIENT_PREFIX):
        return _registered_client(value)
    if value.startswith("https://"):
        cache_key = "agent-cimd:" + hashlib.sha256(value.encode()).hexdigest()
        cached = cache.cache_get(cache_key)
        document = cached if isinstance(cached, dict) else _fetch_metadata_document(value)
        if not isinstance(cached, dict):
            cache.cache_set(cache_key, document, METADATA_CACHE_SECONDS)
        uris = document.get("redirect_uris")
        if not isinstance(uris, list) or not uris or len(uris) > MAX_REDIRECT_URIS:
            raise AgentOAuthError(
                "invalid_client", "The metadata document must list redirect_uris.", 401
            )
        host = urlsplit(value).hostname
        return Client(
            value,
            clean_name(document.get("client_name"), fallback=host or "AI agent"),
            tuple(validate_redirect_uri(u) for u in uris),
            host,
        )
    raise AgentOAuthError("invalid_client", "Unknown client_id.", 401)


def check_resource(resource: str | None) -> None:
    """RFC 8707: tokens are only for the Manifest MCP server."""
    if resource and resource.rstrip("/") not in (RESOURCE, ISSUER):
        raise AgentOAuthError("invalid_target", f"This server only issues tokens for {RESOURCE}.")


def check_scope(scope: str | None) -> str:
    requested = set((scope or SCOPE).split())
    unknown = requested - {SCOPE, "openid", "profile", "email", "offline_access"}
    if unknown:
        raise AgentOAuthError("invalid_scope", f"Unknown scope: {' '.join(sorted(unknown))}")
    return SCOPE


def session_label(client: Client) -> str:
    where = f" ({client.verified_domain})" if client.verified_domain else ""
    return f"{AGENT_SESSION_LABEL_PREFIX}{client.name}{where}"[:200]


# -- refresh tokens ------------------------------------------------------------------


def issue_refresh_token(
    *, user_id: str, session_id: str, client_id: str, auth_iat: int | None, email: str | None = None
) -> str:
    now = int(time.time())
    claims = {
        "aud": REFRESH_AUDIENCE,
        "sub": user_id,
        "sid": session_id,
        "cid": hashlib.sha256(client_id.encode()).hexdigest(),
        "auth_iat": auth_iat,
        "email": email,
        "iat": now,
        "exp": now + REFRESH_TOKEN_SECONDS,
    }
    return jwt.encode(claims, _key("agent-refresh"), algorithm="HS256")


def read_refresh_token(token: str | None, client_id: str) -> dict:
    if not token:
        raise AgentOAuthError("invalid_request", "refresh_token is required.")
    try:
        claims = jwt.decode(
            token, _key("agent-refresh"), algorithms=["HS256"], audience=REFRESH_AUDIENCE
        )
    except jwt.PyJWTError:
        raise AgentOAuthError("invalid_grant", "The refresh token is invalid or expired.") from None
    if not hmac.compare_digest(
        str(claims.get("cid")), hashlib.sha256(client_id.encode()).hexdigest()
    ):
        raise AgentOAuthError("invalid_grant", "The refresh token belongs to a different client.")
    return claims
