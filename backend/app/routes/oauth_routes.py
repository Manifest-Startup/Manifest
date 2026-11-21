"""
OAuth routes for third-party integrations.
Handles OAuth flow for Google, Apple, GitHub, and other providers.

SECURITY NOTES:
- OAuth state is tied to user_id and validated on callback via HMAC-SHA256 signed tokens
- State tokens expire after 10 minutes and include replay protection via nonce tracking
- Integration storage goes through authenticated GraphQL mutation context
- Requires SESSION_SECRET environment variable for signing

KNOWN LIMITATIONS:
- Nonce tracking is process-local (in-memory). For multi-worker deployments, consider
  migrating to Redis or database-backed nonce storage for cross-instance replay protection.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import urllib.parse
from datetime import datetime, timedelta

from app.db.database import get_db_connection
from app.services.integrations.github_account import OAUTH_SCOPES as GITHUB_OAUTH_SCOPES
from app.utils.logger import logger
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/auth", tags=["oauth"])

OAUTH_SIGNING_KEY = os.getenv("SESSION_SECRET", "")


def validate_oauth_config():
    """Validate OAuth configuration at startup. Call from app initialization."""
    if not OAUTH_SIGNING_KEY:
        logger.warning(
            "OAuth signing key not configured. OAuth endpoints will return errors. "
            "Set SESSION_SECRET environment variable."
        )


_used_nonces: dict = {}


def _cleanup_expired_nonces():
    """Remove expired nonces to prevent memory growth."""
    cutoff = datetime.utcnow() - timedelta(minutes=15)
    expired = [n for n, t in _used_nonces.items() if t < cutoff]
    for n in expired:
        del _used_nonces[n]


def _get_signing_key() -> bytes:
    """Get the signing key, raising an error if not configured."""
    if not OAUTH_SIGNING_KEY:
        raise ValueError(
            "OAuth signing key not configured. Set SESSION_SECRET environment variable."
        )
    return OAUTH_SIGNING_KEY.encode()


def create_signed_state(user_id: str, provider: str) -> str:
    """Create a cryptographically signed state token that ties the flow to a user."""
    nonce = secrets.token_hex(16)
    payload = {
        "user_id": user_id,
        "provider": provider,
        "created_at": datetime.utcnow().isoformat(),
        "nonce": nonce,
    }
    payload_json = json.dumps(payload, sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()
    signature = hmac.new(_get_signing_key(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_signed_state(state: str, max_age_minutes: int = 10) -> dict | None:
    """Verify and decode a signed state token. Returns None if invalid or already used."""
    try:
        parts = state.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature = parts
        expected_signature = hmac.new(
            _get_signing_key(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            logger.warning("OAuth state signature mismatch")
            return None
        payload_json = base64.urlsafe_b64decode(payload_b64.encode()).decode()
        payload = json.loads(payload_json)
        created_at = datetime.fromisoformat(payload["created_at"])
        if datetime.utcnow() - created_at > timedelta(minutes=max_age_minutes):
            logger.warning("OAuth state expired")
            return None
        nonce = payload.get("nonce")
        if nonce in _used_nonces:
            logger.warning("OAuth state nonce already used (replay attempt)")
            return None
        _used_nonces[nonce] = datetime.utcnow()
        _cleanup_expired_nonces()
        return payload
    except ValueError as e:
        logger.error(f"OAuth signing key not configured: {e}")
        return None
    except Exception as e:
        logger.error(f"Error verifying OAuth state: {e}")
        return None


def save_integration(user_id: str, provider: str, data: dict) -> bool:
    """Save or update an integration. Encrypts OAuth tokens when the
    ``ENCRYPT_INTEGRATIONS_TOKENS`` feature flag is on (see Task #12).

    Enforces data residency: refuses to write tokens to a database serving a
    region other than the user's pinned ``data_region``.
    """
    try:
        from app.security.data_residency import (
            RegionMismatchError,
            assert_region_match,
        )
        from app.services.integrations.token_crypto import encrypt_integration_tokens

        # Residency gate — fail closed before any plaintext touches storage.
        try:
            with get_db_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT data_region FROM users WHERE user_id = %s",
                    (user_id,),
                )
                user_row = cur.fetchone()
            tenant_region = (user_row or {}).get("data_region") if user_row else None
            assert_region_match(tenant_region, context="integrations.save")
        except RegionMismatchError:
            logger.error(
                "[oauth] save_integration blocked by data residency for user=%s provider=%s",
                user_id,
                provider,
            )
            return False

        token_payload = encrypt_integration_tokens(
            user_id,
            provider,
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
        )
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    INSERT INTO integrations (
                        user_id, service_id, service_name,
                        access_token, refresh_token,
                        access_token_ciphertext, refresh_token_ciphertext, token_key_version,
                        expires_at, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, service_id) DO UPDATE SET
                        access_token = EXCLUDED.access_token,
                        refresh_token = EXCLUDED.refresh_token,
                        access_token_ciphertext = EXCLUDED.access_token_ciphertext,
                        refresh_token_ciphertext = EXCLUDED.refresh_token_ciphertext,
                        token_key_version = EXCLUDED.token_key_version,
                        expires_at = EXCLUDED.expires_at,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    """,
                (
                    user_id,
                    provider,
                    provider,
                    token_payload["access_token"],
                    token_payload["refresh_token"],
                    token_payload["access_token_ciphertext"],
                    token_payload["refresh_token_ciphertext"],
                    token_payload["token_key_version"],
                    data.get("token_expiry"),
                    json.dumps(data.get("raw_data", {})),
                ),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving integration: {e}")
        return False


# OAuth provider configurations
OAUTH_PROVIDERS = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": ["openid", "email", "profile", "https://www.googleapis.com/auth/drive.readonly"],
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
    },
    "apple": {
        "auth_url": "https://appleid.apple.com/auth/authorize",
        "token_url": "https://appleid.apple.com/auth/token",
        "scopes": ["name", "email"],
        "client_id_env": "APPLE_CLIENT_ID",
        "client_secret_env": "APPLE_CLIENT_SECRET",
    },
    "github": {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": GITHUB_OAUTH_SCOPES,
        "client_id_env": "GITHUB_CLIENT_ID",
        "client_secret_env": "GITHUB_CLIENT_SECRET",
    },
    "microsoft": {
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scopes": ["openid", "email", "profile", "offline_access", "User.Read"],
        "client_id_env": "MICROSOFT_CLIENT_ID",
        "client_secret_env": "MICROSOFT_CLIENT_SECRET",
    },
    "slack": {
        "auth_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scopes": ["channels:read", "chat:write", "users:read"],
        "client_id_env": "SLACK_CLIENT_ID",
        "client_secret_env": "SLACK_CLIENT_SECRET",
    },
    "notion": {
        "auth_url": "https://api.notion.com/v1/oauth/authorize",
        "token_url": "https://api.notion.com/v1/oauth/token",
        "scopes": [],
        "client_id_env": "NOTION_CLIENT_ID",
        "client_secret_env": "NOTION_CLIENT_SECRET",
    },
    "linkedin": {
        "auth_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "scopes": ["openid", "profile", "email"],
        "client_id_env": "LINKEDIN_CLIENT_ID",
        "client_secret_env": "LINKEDIN_CLIENT_SECRET",
    },
    "stripe": {
        "auth_url": "https://connect.stripe.com/oauth/authorize",
        "token_url": "https://connect.stripe.com/oauth/token",
        "scopes": ["read_write"],
        "client_id_env": "STRIPE_CLIENT_ID",
        "client_secret_env": "STRIPE_SECRET_KEY",
    },
}


def get_redirect_uri(request: Request, provider: str) -> str:
    """Generate the redirect URI for OAuth callback."""
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        base_url = f"{forwarded_proto}://{forwarded_host}"
    else:
        base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/auth/{provider}/callback"


def get_user_id_from_request(request: Request) -> str | None:
    """Extract user ID from request token."""
    from app.auth.current_user import get_current_user_id

    try:
        return get_current_user_id(request)
    except Exception:
        return None


@router.get("/{provider}/start")
async def oauth_start(request: Request, provider: str):
    """
    Start OAuth flow for a provider.
    Returns the authorization URL to redirect the user to.
    """
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    config = OAUTH_PROVIDERS[provider]
    client_id = os.getenv(config["client_id_env"])

    if not client_id:
        logger.warning(f"OAuth client ID not configured for {provider}")
        return {
            "error": "not_configured",
            "message": f"{provider.capitalize()} integration is not yet configured. Please contact support.",
            "provider": provider,
        }

    user_id = get_user_id_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    state = create_signed_state(user_id, provider)

    redirect_uri = get_redirect_uri(request, provider)
    scopes = " ".join(config["scopes"])

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "scope": scopes,
    }

    if provider == "google":
        params["access_type"] = "offline"
        params["prompt"] = "consent"
    elif provider == "apple":
        params["response_mode"] = "form_post"

    auth_url = f"{config['auth_url']}?{urllib.parse.urlencode(params)}"

    logger.info(f"OAuth flow started for {provider}, user_id: {user_id}")

    return {"auth_url": auth_url, "provider": provider, "state": state}


@router.get("/{provider}/callback")
@router.post("/{provider}/callback")
async def oauth_callback(request: Request, provider: str):  # noqa: C901
    """
    Handle OAuth callback from provider.
    Exchanges code for tokens and stores the integration.
    """
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    if request.method == "POST":
        form_data = await request.form()
        code = str(form_data.get("code", "")) or None
        state = str(form_data.get("state", "")) or None
        error = str(form_data.get("error", "")) or None
    else:
        params = request.query_params
        code = params.get("code")
        state = params.get("state")
        error = params.get("error")

    if error:
        logger.error(f"OAuth error for {provider}: {error}")
        return _render_callback_page(success=False, error=str(error), provider=provider)

    if not state:
        logger.error(f"No state received for {provider}")
        return _render_callback_page(success=False, error="Invalid state", provider=provider)

    state_data = verify_signed_state(state)
    if not state_data:
        logger.error(f"Invalid or expired OAuth state for {provider}")
        return _render_callback_page(
            success=False, error="Invalid or expired session", provider=provider
        )

    if state_data.get("provider") != provider:
        logger.error(
            f"Provider mismatch in OAuth state: expected {provider}, got {state_data.get('provider')}"
        )
        return _render_callback_page(success=False, error="Invalid state", provider=provider)

    user_id = state_data["user_id"]

    if not code:
        logger.error(f"No code received for {provider}")
        return _render_callback_page(
            success=False, error="No authorization code", provider=provider
        )

    config = OAUTH_PROVIDERS[provider]
    client_id = os.getenv(config["client_id_env"])
    client_secret = os.getenv(config["client_secret_env"])

    if not client_id or not client_secret:
        logger.error(f"OAuth credentials not configured for {provider}")
        return _render_callback_page(
            success=False, error="Integration not configured", provider=provider
        )

    import httpx

    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": get_redirect_uri(request, provider),
        "grant_type": "authorization_code",
    }

    try:
        async with httpx.AsyncClient() as client:
            headers = {"Accept": "application/json"}
            if provider == "notion":
                import base64

                credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
                headers["Authorization"] = f"Basic {credentials}"
                del token_data["client_id"]
                del token_data["client_secret"]

            response = await client.post(config["token_url"], data=token_data, headers=headers)

            if response.status_code != 200:
                logger.error(f"Token exchange failed for {provider}: {response.text}")
                return _render_callback_page(
                    success=False, error="Token exchange failed", provider=provider
                )

            tokens = response.json()

    except Exception as e:
        logger.error(f"Error during token exchange for {provider}: {e}")
        return _render_callback_page(success=False, error=str(e), provider=provider)

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    if provider == "github":
        # GitHub answers 200 with {"error": ...} when the code is bad or reused.
        from app.services.integrations.github_account import (
            GitHubConnectError,
            save_github_token,
        )

        if not access_token:
            logger.error("GitHub token exchange returned no token: %s", tokens.get("error"))
            return _render_callback_page(
                success=False, error="GitHub did not return a token", provider=provider
            )
        try:
            import asyncio

            await asyncio.to_thread(save_github_token, user_id, access_token, method="oauth")
        except GitHubConnectError as exc:
            return _render_callback_page(success=False, error=str(exc), provider=provider)
        return _render_callback_page(success=True, provider=provider)
    expires_in = tokens.get("expires_in")

    expires_at = None
    if expires_in:
        expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))

    try:
        integration_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_expiry": expires_at.isoformat() if expires_at else None,
            "raw_data": {
                "scope": tokens.get("scope"),
                "connected_at": datetime.utcnow().isoformat(),
            },
        }

        if save_integration(user_id, provider, integration_data):
            logger.info(f"Successfully stored {provider} integration for user {user_id}")
        else:
            raise Exception("Failed to save integration to database")

    except Exception as e:
        logger.error(f"Error storing integration for {provider}: {e}")
        return _render_callback_page(
            success=False, error="Failed to save integration", provider=provider
        )

    return _render_callback_page(success=True, provider=provider)


@router.get("/{provider}/status")
async def oauth_status(request: Request, provider: str):
    """Check if OAuth is configured for a provider."""
    if provider not in OAUTH_PROVIDERS:
        return {"configured": False, "provider": provider}

    config = OAUTH_PROVIDERS[provider]
    client_id = os.getenv(config["client_id_env"])

    return {
        "configured": bool(client_id),
        "provider": provider,
        "display_name": provider.capitalize(),
    }


def _render_callback_page(success: bool, provider: str, error: str | None = None) -> HTMLResponse:
    """Render HTML page that communicates result to parent window."""
    status = "success" if success else "error"
    message = (
        f"Successfully connected to {provider.capitalize()}"
        if success
        else (error or "Connection failed")
    )

    import html as _html

    display = "GitHub" if provider == "github" else provider.capitalize()
    if success:
        message = f"Successfully connected to {display}"
    html_message = _html.escape(message)
    result_json = json.dumps({"status": status, "provider": provider, "message": message}).replace(
        "<", "\\u003c"
    )
    redirect_json = json.dumps(
        f"/account?oauth={status}&provider={urllib.parse.quote(provider)}"
        + ("&focusIntegration=github" if provider == "github" else "")
    ).replace("<", "\\u003c")

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>OAuth Callback</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: {'#f0fdf4' if success else '#fef2f2'};
            }}
            .container {{
                text-align: center;
                padding: 40px;
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                max-width: 400px;
            }}
            .icon {{
                font-size: 48px;
                margin-bottom: 16px;
            }}
            h1 {{
                margin: 0 0 8px 0;
                color: {'#166534' if success else '#991b1b'};
                font-size: 24px;
            }}
            p {{
                margin: 0;
                color: #6b7280;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="icon">{'✓' if success else '✗'}</div>
            <h1>{'Connected!' if success else 'Connection Failed'}</h1>
            <p>{html_message}</p>
        </div>
        <script>
            const result = {result_json};
            
            if (window.opener) {{
                window.opener.postMessage({{ type: 'oauth_callback', ...result }}, window.location.origin);
                setTimeout(() => window.close(), 1500);
            }} else {{
                setTimeout(() => {{
                    window.location.href = {redirect_json};
                }}, 1500);
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
