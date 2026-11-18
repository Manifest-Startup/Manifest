"""Sign in the Manifest CLI from the browser (loopback + PKCE, ADR 0003).

- ``GET  /api/cli/authorize?redirect_uri=http://127.0.0.1:<port>/callback&state=…&code_challenge=…&code_challenge_method=S256``
  needs a signed-in, non-guest browser session (otherwise it sends the browser to
  ``/login?next=…``, i.e. Continue with Open Media, so passkeys and MFA apply) whose
  sign-in is within the 5-minute step-up window (otherwise it signs in with Open Media
  again once, marked ``reauth=1``), shows
  "Allow Manifest CLI on this computer?", then redirects to the loopback address
  with a one-time ``code`` and the CLI's ``state``.
- ``POST /api/cli/token`` exchanges ``code`` + ``code_verifier`` for a revocable CLI
  session token (30 days, ``Manifest CLI · <hostname>`` in the Account session list).

``manifest logout`` revokes the CLI session through ``POST /api/auth/logout``.
"""

from __future__ import annotations

import html
import time
from urllib.parse import urlencode

from app.auth.current_user import (
    DEMO_MODE,
    create_cli_session_token,
    get_current_token_payload_optional,
    get_current_user_id_optional,
)
from app.db.database import create_database_client
from app.security.step_up import DEFAULT_TTL_SECONDS as STEP_UP_SECONDS
from app.services.compliance.security_audit import record_security_event
from app.services.identity import cli_auth
from app.services.identity.guest_workspace import fetch_user_is_guest
from app.services.identity.sessions import is_session_active
from app.utils.logger import logger
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/cli", tags=["cli"])

AUTHORIZE_PATH = "/api/cli/authorize"
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache", "X-Frame-Options": "DENY"}


def _is_guest(user_id: str) -> bool:
    try:
        return fetch_user_is_guest(create_database_client(), user_id)
    except Exception as exc:  # fail closed: an unknown account cannot authorize a CLI
        logger.warning("[cli_auth] guest check failed: %s", type(exc).__name__)
        return True


def _page(request: Request, title: str, body: str, status_code: int = 200) -> HTMLResponse:
    """A small page styled like the Manifest login page (light and dark)."""
    nonce = getattr(request.state, "csp_nonce", "")
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{html.escape(title)} · Manifest</title>
<style nonce="{html.escape(nonce)}">
:root{{--bg:#fafaf9;--fg:#171717;--muted:#57534e;--btn:#171717;--btn-fg:#fff;--line:#e7e5e4}}
@media (prefers-color-scheme: dark){{:root{{--bg:#0a0a0a;--fg:#fafafa;--muted:#a8a29e;--btn:#fff;--btn-fg:#171717;--line:#292524}}}}
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--bg);color:var(--fg);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{width:100%;max-width:26rem;padding:2.5rem 1rem;text-align:center}}
.brand{{display:inline-flex;align-items:center;gap:.75rem;font-weight:700;font-size:1.125rem;letter-spacing:-.02em}}
.mark{{display:flex;width:2.5rem;height:2.5rem;align-items:center;justify-content:center;border-radius:1rem;background:var(--btn);color:var(--btn-fg);font-size:.875rem}}
h1{{margin:2.5rem 0 0;font-size:1.75rem;letter-spacing:-.03em}}
p{{margin:.75rem auto 0;max-width:24rem;font-size:.875rem;line-height:1.5rem;color:var(--muted)}}
.primary{{margin-top:2rem;display:flex;width:100%;justify-content:center;border-radius:9999px;background:var(--btn);color:var(--btn-fg);padding:.875rem 1.5rem;font-weight:600;text-decoration:none}}
.secondary{{display:inline-block;margin-top:1rem;font-size:.875rem;font-weight:600;color:var(--muted)}}
.note{{margin-top:2.5rem;font-size:.75rem;border-top:1px solid var(--line);padding-top:1rem}}
</style></head>
<body><main><span class="brand"><span class="mark">M</span>Manifest</span>{body}</main></body></html>"""
    return HTMLResponse(content, status_code=status_code, headers=_NO_STORE)


def _error_page(request: Request, message: str, status_code: int = 400) -> HTMLResponse:
    return _page(
        request,
        "Manifest CLI",
        f"<h1>Can't sign in the CLI</h1><p>{html.escape(message)}</p>"
        '<p class="note">Run <code>manifest login</code> again from your terminal.</p>',
        status_code,
    )


def _signed_in_recently(payload: dict) -> bool:
    """The browser session's Open Media sign-in is within the step-up window (5 min)."""
    if DEMO_MODE:  # local demo tokens carry no auth_iat and no Open Media sign-in
        return True
    try:
        auth_iat = int(payload.get("auth_iat") or 0)
    except (TypeError, ValueError):
        return False
    return auth_iat > 0 and time.time() - auth_iat <= STEP_UP_SECONDS


def _reauth_redirect(base: dict[str, str]) -> RedirectResponse:
    """Sign in with Open Media again, then come back here (marked so it cannot loop)."""
    next_path = f"{AUTHORIZE_PATH}?{urlencode({**base, 'reauth': '1'})}"
    return RedirectResponse(
        f"/api/auth/open-media/start?{urlencode({'next': next_path})}",
        status_code=303,
        headers=_NO_STORE,
    )


def _login_redirect(request: Request) -> RedirectResponse:
    next_path = f"{AUTHORIZE_PATH}?{request.url.query}" if request.url.query else AUTHORIZE_PATH
    return RedirectResponse(
        f"/login?{urlencode({'next': next_path})}", status_code=303, headers=_NO_STORE
    )


@router.get("/authorize", include_in_schema=False)
def cli_authorize(
    request: Request,
    redirect_uri: str | None = None,
    state: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    confirm: str | None = None,
    deny: str | None = None,
    reauth: str | None = None,
):
    try:
        uri = cli_auth.validate_authorize_params(
            redirect_uri, state, code_challenge, code_challenge_method
        )
    except cli_auth.CliAuthError as exc:
        # Never redirect to an unvalidated URI: explain on the page instead.
        return _error_page(request, str(exc))
    assert state is not None and code_challenge is not None

    payload = get_current_token_payload_optional(request) or {}
    user_id = get_current_user_id_optional(request) if payload else None
    if not user_id or payload.get("kind") in ("cli", "agent") or _is_guest(str(user_id)):
        # Guests and signed-out visitors sign in with Open Media first.
        return _login_redirect(request)
    user_id = str(user_id)
    browser_sid = str(payload["sid"]) if payload.get("sid") else None
    expected = cli_auth.confirm_token(browser_sid, user_id, uri, state, code_challenge)

    base = {
        "redirect_uri": uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if deny:
        query = urlencode({"error": "access_denied", "state": state})
        return RedirectResponse(f"{uri}?{query}", status_code=303, headers=_NO_STORE)

    # Approving a CLI is a sensitive action: it needs a fresh sign-in, which the
    # CLI session then inherits (auth_iat), so step-up routes work from the CLI.
    if not _signed_in_recently(payload):
        if reauth:
            return _error_page(
                request, "Manifest could not confirm a fresh sign-in with Open Media.", 401
            )
        return _reauth_redirect(base)

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
        )
        query = urlencode({"code": code, "state": state})
        return RedirectResponse(f"{uri}?{query}", status_code=303, headers=_NO_STORE)

    allow_href = f"{AUTHORIZE_PATH}?{urlencode({**base, 'confirm': expected})}"
    deny_href = f"{AUTHORIZE_PATH}?{urlencode({**base, 'deny': '1'})}"
    who = html.escape(str(payload.get("email") or "your account"))
    return _page(
        request,
        "Allow Manifest CLI",
        f"""<h1>Allow Manifest CLI on this computer?</h1>
<p>The <code>manifest</code> command line will be able to do everything you can do in Manifest as <strong>{who}</strong>.</p>
<a class="primary" data-testid="cli-allow" href="{html.escape(allow_href)}">Allow</a>
<a class="secondary" data-testid="cli-deny" href="{html.escape(deny_href)}">Cancel</a>
<p class="note">Only allow this if you just ran <code>manifest login</code>. You can revoke the CLI any time under Account → Security → Active sessions.</p>""",
    )


class CliTokenRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=4096)
    code_verifier: str = Field(..., min_length=43, max_length=128)
    redirect_uri: str | None = Field(None, max_length=200)
    hostname: str | None = Field(None, max_length=255)


def _token_error(code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": code, "error_description": message}, status_code=status_code, headers=_NO_STORE
    )


def _client_ip(request: Request) -> str | None:
    client = getattr(request, "client", None)
    return getattr(client, "host", None) if client else None


@router.post("/token", include_in_schema=False)
def cli_token(body: CliTokenRequest, request: Request):
    try:
        grant = cli_auth.redeem_code(body.code, body.code_verifier, body.redirect_uri)
    except cli_auth.CliAuthError as exc:
        return _token_error(exc.code, str(exc))
    if _is_guest(grant.user_id):
        return _token_error("access_denied", "Guest workspaces can't use the Manifest CLI.", 403)
    if grant.browser_session_id and not is_session_active(grant.browser_session_id, grant.user_id):
        return _token_error("invalid_grant", "The approving browser session was signed out.")

    label = cli_auth.session_label(body.hostname)
    token, expires_at = create_cli_session_token(
        grant.user_id,
        email=grant.email,
        label=label,
        auth_iat=grant.auth_iat,
        request=request,
    )
    record_security_event(
        "cli_session_created",
        user_id=grant.user_id,
        request_ip=_client_ip(request),
        session_id=grant.browser_session_id,
        actor_id=grant.user_id,
        actor_type="user",
        action="cli_login",
        target_type="session",
        outcome="success",
        user_agent=request.headers.get("user-agent"),
        metadata={"label": label},
    )
    return JSONResponse(
        {
            "access_token": token,
            "token_type": "Bearer",
            "expires_at": expires_at.isoformat(),
            "label": label,
            "user": {"user_id": grant.user_id, "email": grant.email},
        },
        headers=_NO_STORE,
    )
