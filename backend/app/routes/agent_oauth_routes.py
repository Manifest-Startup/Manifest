"""OAuth for AI agents using the Manifest MCP server (ADR 0004).

- ``GET  /.well-known/oauth-protected-resource[/mcp]`` and
  ``GET  /.well-known/oauth-authorization-server``: discovery (RFC 9728, RFC 8414).
- ``POST /api/oauth/register``: stateless dynamic client registration (RFC 7591).
- ``GET  /api/oauth/authorize``: the browser approval page ("Allow <agent> to use Manifest?"),
  with the same sign-in, guest and fresh-sign-in rules as the CLI (ADR 0003).
- ``POST /api/oauth/token``: ``authorization_code`` (PKCE) and ``refresh_token`` grants.
- ``POST /api/oauth/revoke``: revoke a token's session (RFC 7009).
"""

from __future__ import annotations

import html
import json
import time
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from app.auth.current_user import (
    DEMO_MODE,
    create_cli_session_token,
    decode_session_token,
    get_current_token_payload_optional,
    get_current_user_id_optional,
)
from app.routes.cli_auth_routes import _client_ip, _is_guest, _page
from app.security.step_up import DEFAULT_TTL_SECONDS as STEP_UP_SECONDS
from app.services.compliance.security_audit import record_security_event
from app.services.identity import agent_oauth, cli_auth
from app.services.identity.sessions import (
    CLI_SESSION_IDLE_TIMEOUT_SECONDS,
    is_session_active,
    revoke_session,
)
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

router = APIRouter(tags=["agent-oauth"])

AUTHORIZE_PATH = "/api/oauth/authorize"
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache", "X-Frame-Options": "DENY"}
_PUBLIC_JSON = {"Cache-Control": "public, max-age=3600", "Access-Control-Allow-Origin": "*"}
_CORS = {"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "Pragma": "no-cache"}


# -- discovery ---------------------------------------------------------------------


@router.get("/.well-known/oauth-authorization-server", include_in_schema=False)
def authorization_server_metadata():
    return JSONResponse(agent_oauth.authorization_server_metadata(), headers=_PUBLIC_JSON)


@router.get("/.well-known/oauth-protected-resource", include_in_schema=False)
@router.get("/.well-known/oauth-protected-resource/mcp", include_in_schema=False)
def protected_resource_metadata():
    return JSONResponse(agent_oauth.protected_resource_metadata(), headers=_PUBLIC_JSON)


def _oauth_error(
    exc: agent_oauth.AgentOAuthError | cli_auth.CliAuthError, status: int | None = None
):
    code = exc.code
    return JSONResponse(
        {"error": code, "error_description": str(exc)},
        status_code=status or getattr(exc, "status", 400),
        headers=_CORS,
    )


# -- registration ------------------------------------------------------------------


@router.post("/api/oauth/register", include_in_schema=False)
async def register(request: Request):
    try:
        raw = await request.body()
        if len(raw) > 16_384:
            raise agent_oauth.AgentOAuthError(
                "invalid_client_metadata", "Registration is too large."
            )
        metadata = json.loads(raw or b"{}")
        return JSONResponse(agent_oauth.register_client(metadata), status_code=201, headers=_CORS)
    except json.JSONDecodeError:
        return _oauth_error(agent_oauth.AgentOAuthError("invalid_client_metadata", "Send JSON."))
    except agent_oauth.AgentOAuthError as exc:
        return _oauth_error(exc)


# -- authorization -----------------------------------------------------------------


def _error_page(request: Request, message: str, status_code: int = 400) -> HTMLResponse:
    return _page(
        request,
        "Connect an AI agent",
        f"<h1>Can't connect this agent</h1><p>{html.escape(message)}</p>"
        '<p class="note">Go back to your AI app and try connecting Manifest again.</p>',
        status_code,
    )


def _redirect(uri: str, params: dict[str, str]) -> RedirectResponse:
    joiner = "&" if urlsplit(uri).query else "?"
    return RedirectResponse(f"{uri}{joiner}{urlencode(params)}", status_code=303, headers=_NO_STORE)


def _signed_in_recently(payload: dict) -> bool:
    if DEMO_MODE:
        return True
    try:
        auth_iat = int(payload.get("auth_iat") or 0)
    except (TypeError, ValueError):
        return False
    return auth_iat > 0 and time.time() - auth_iat <= STEP_UP_SECONDS


def _check_request(
    response_type: str | None,
    code_challenge: str | None,
    code_challenge_method: str | None,
    state: str,
    scope: str | None,
    resource: str | None,
) -> str:
    """Validate the authorization request after the client is known; returns the scope."""
    if response_type != "code":
        raise agent_oauth.AgentOAuthError(
            "unsupported_response_type", "response_type must be code."
        )
    if (code_challenge_method or "") != "S256" or not 43 <= len(code_challenge or "") <= 128:
        raise agent_oauth.AgentOAuthError("invalid_request", "PKCE with S256 is required.")
    if len(state) > 1024:
        raise agent_oauth.AgentOAuthError("invalid_request", "state is too long.")
    agent_oauth.check_resource(resource)
    return agent_oauth.check_scope(scope)


@router.get(AUTHORIZE_PATH, include_in_schema=False)
def authorize(
    request: Request,
    client_id: str | None = None,
    redirect_uri: str | None = None,
    response_type: str | None = None,
    state: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    scope: str | None = None,
    resource: str | None = None,
    confirm: str | None = None,
    deny: str | None = None,
    reauth: str | None = None,
):
    # Until the client and redirect URI are verified, errors are shown, never redirected.
    try:
        client = agent_oauth.resolve_client(client_id)
        uri = agent_oauth.validate_redirect_uri(redirect_uri)
        if not agent_oauth.redirect_matches(uri, client.redirect_uris):
            raise agent_oauth.AgentOAuthError(
                "invalid_redirect_uri", "redirect_uri is not registered for this client."
            )
    except agent_oauth.AgentOAuthError as exc:
        return _error_page(request, str(exc))

    state_value = state or ""
    with_state = {"state": state_value} if state else {}
    try:
        granted_scope = _check_request(
            response_type, code_challenge, code_challenge_method, state_value, scope, resource
        )
    except agent_oauth.AgentOAuthError as exc:
        return _redirect(uri, {"error": exc.code, "error_description": str(exc), **with_state})

    base = {
        "client_id": client.client_id,
        "redirect_uri": uri,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": granted_scope,
        **with_state,
        **({"resource": resource} if resource else {}),
    }
    payload = get_current_token_payload_optional(request) or {}
    user_id = get_current_user_id_optional(request) if payload else None
    if not user_id or payload.get("kind") in ("cli", "agent") or _is_guest(str(user_id)):
        next_path = f"{AUTHORIZE_PATH}?{urlencode(base)}"
        return RedirectResponse(
            f"/login?{urlencode({'next': next_path})}", status_code=303, headers=_NO_STORE
        )
    user_id = str(user_id)

    if deny:
        return _redirect(uri, {"error": "access_denied", **with_state})

    # Connecting an agent hands it the whole account: it needs a fresh sign-in (ADR 0003).
    if not _signed_in_recently(payload):
        if reauth:
            return _error_page(
                request, "Manifest could not confirm a fresh sign-in with Open Media.", 401
            )
        next_path = f"{AUTHORIZE_PATH}?{urlencode({**base, 'reauth': '1'})}"
        return RedirectResponse(
            f"/api/auth/open-media/start?{urlencode({'next': next_path})}",
            status_code=303,
            headers=_NO_STORE,
        )

    browser_sid = str(payload["sid"]) if payload.get("sid") else None
    expected = cli_auth.confirm_token(
        browser_sid,
        user_id,
        "agent",
        client.client_id,
        uri,
        state_value,
        code_challenge,
        resource or "",
    )
    if confirm is not None:
        if not cli_auth.confirm_token_valid(confirm, expected):
            return _error_page(request, "This approval link is not valid for your session.", 403)
        code = cli_auth.issue_code(
            user_id=user_id,
            email=payload.get("email"),
            browser_session_id=browser_sid,
            auth_iat=payload.get("auth_iat"),
            redirect_uri=uri,
            code_challenge=code_challenge,
            audience=agent_oauth.CODE_AUDIENCE,
            client_id=client.client_id,
            scope=granted_scope,
        )
        return _redirect(uri, {"code": code, **with_state, "iss": agent_oauth.ISSUER})

    allow_href = f"{AUTHORIZE_PATH}?{urlencode({**base, 'confirm': expected})}"
    deny_href = f"{AUTHORIZE_PATH}?{urlencode({**base, 'deny': '1'})}"
    who = html.escape(str(payload.get("email") or "your account"))
    name = html.escape(client.name)
    origin = html.escape(
        f"Verified domain: {client.verified_domain}"
        if client.verified_domain
        else f"It will return to {urlsplit(uri).scheme}://{urlsplit(uri).netloc or urlsplit(uri).path.split('/')[0]}"
    )
    return _page(
        request,
        "Connect an AI agent",
        f"""<h1>Allow {name} to use Manifest?</h1>
<p><strong>{name}</strong> will be able to do everything you can do in Manifest as <strong>{who}</strong>: read and edit your ideas, generate documents, message founders and change settings. It asks you before anything destructive.</p>
<p>{origin}.</p>
<a class="primary" data-testid="agent-allow" href="{html.escape(allow_href)}">Allow</a>
<a class="secondary" data-testid="agent-deny" href="{html.escape(deny_href)}">Cancel</a>
<p class="note">Only allow this if you just connected Manifest in an AI app. Disconnect it any time under Account → Security → Active sessions.</p>""",
    )


# -- tokens ------------------------------------------------------------------------


async def _form(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
        return {k: str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    form = await request.form()
    return {k: str(v) for k, v in form.items()}


def _mint(
    request: Request,
    *,
    user_id: str,
    email: str | None,
    client: agent_oauth.Client,
    auth_iat,
    scope: str,
):
    label = agent_oauth.session_label(client)
    access, _expires_at = create_cli_session_token(
        user_id,
        email=email,
        label=label,
        auth_iat=auth_iat,
        request=request,
        kind="agent",
        token_ttl=timedelta(seconds=agent_oauth.ACCESS_TOKEN_SECONDS),
        extra_claims={"aud_resource": agent_oauth.RESOURCE},
    )
    session_id = (decode_session_token(access) or {}).get("sid")
    refresh = agent_oauth.issue_refresh_token(
        user_id=user_id,
        session_id=str(session_id),
        client_id=client.client_id,
        auth_iat=auth_iat,
        email=email,
    )
    return (
        {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": agent_oauth.ACCESS_TOKEN_SECONDS,
            "refresh_token": refresh,
            "scope": scope,
        },
        label,
    )


@router.post("/api/oauth/token", include_in_schema=False)
async def token(request: Request):
    try:
        form = await _form(request)
    except Exception:
        return _oauth_error(
            agent_oauth.AgentOAuthError("invalid_request", "Send a form or JSON body.")
        )
    grant_type = form.get("grant_type")
    try:
        client = agent_oauth.resolve_client(form.get("client_id"))
        agent_oauth.check_resource(form.get("resource"))
        if grant_type == "authorization_code":
            grant = cli_auth.redeem_code(
                form.get("code"),
                form.get("code_verifier"),
                form.get("redirect_uri"),
                audience=agent_oauth.CODE_AUDIENCE,
                client_id=client.client_id,
            )
            user_id, email, auth_iat = grant.user_id, grant.email, grant.auth_iat
            if grant.browser_session_id and not is_session_active(
                grant.browser_session_id, user_id
            ):
                raise agent_oauth.AgentOAuthError(
                    "invalid_grant", "The approving browser session was signed out."
                )
            event = "agent_session_created"
        elif grant_type == "refresh_token":
            claims = agent_oauth.read_refresh_token(form.get("refresh_token"), client.client_id)
            user_id, email, auth_iat = (
                str(claims["sub"]),
                claims.get("email"),
                claims.get("auth_iat"),
            )
            old_sid = str(claims.get("sid") or "")
            if not old_sid or not is_session_active(
                old_sid, user_id, idle_timeout_seconds=CLI_SESSION_IDLE_TIMEOUT_SECONDS
            ):
                raise agent_oauth.AgentOAuthError(
                    "invalid_grant", "The agent was disconnected. Connect it again."
                )
            revoke_session(old_sid, user_id)  # rotation: the old refresh token stops working
            event = "agent_session_refreshed"
        else:
            raise agent_oauth.AgentOAuthError(
                "unsupported_grant_type", "grant_type must be authorization_code or refresh_token."
            )
    except (agent_oauth.AgentOAuthError, cli_auth.CliAuthError) as exc:
        return _oauth_error(exc)
    if _is_guest(user_id):
        return _oauth_error(
            agent_oauth.AgentOAuthError("access_denied", "Guest workspaces can't connect agents."),
            403,
        )

    body, label = _mint(
        request,
        user_id=user_id,
        email=email,
        client=client,
        auth_iat=auth_iat,
        scope=agent_oauth.SCOPE,
    )
    record_security_event(
        event,
        user_id=user_id,
        request_ip=_client_ip(request),
        actor_id=user_id,
        actor_type="user",
        action="agent_oauth",
        target_type="session",
        outcome="success",
        user_agent=request.headers.get("user-agent"),
        metadata={"label": label},
    )
    return JSONResponse(body, headers=_CORS)


@router.post("/api/oauth/revoke", include_in_schema=False)
async def revoke(request: Request):
    """RFC 7009: always 200; revokes the session behind an access or refresh token."""
    try:
        form = await _form(request)
    except Exception:
        return JSONResponse({}, headers=_CORS)
    value = form.get("token") or ""
    claims = decode_session_token(value) or {}
    if claims.get("kind") != "agent":
        try:
            claims = agent_oauth.read_refresh_token(value, form.get("client_id") or "")
        except agent_oauth.AgentOAuthError:
            claims = {}
    if claims.get("sid") and claims.get("sub"):
        revoke_session(str(claims["sid"]), str(claims["sub"]))
    return JSONResponse({}, headers=_CORS)
