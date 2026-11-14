"""Enterprise SSO admin + JIT login routes.

Two surfaces:

1. ``/api/sso/admin/...`` — admin-only management of tenant configs
   (require_admin → admin role + recent step-up).
2. ``/api/sso/login`` — public endpoint that, given an email, tells the
   client whether the email belongs to an SSO tenant and where to start.
   The actual SAML/OIDC redirect handlers are at ``/auth/sso/<slug>/...``.

The OIDC path delegates to ``app.security.oidc_verification.verify_id_token``.
The SAML POST-binding handler is intentionally guarded behind
``enterprise_sso_service.saml_enabled()`` until ``python3-saml`` is added
to requirements and tenant-specific signing certs are wired through KMS.
"""

from __future__ import annotations

import os
from typing import Any

from app.auth.replit_auth import create_session_token
from app.routes.dependencies import require_admin
from app.security.config import secure_cookies_enabled
from app.security.cookies import set_auth_cookies
from app.security.oidc_verification import verify_id_token
from app.services.admin_audit_service import record_admin_event
from app.services.enterprise_sso_service import (
    find_tenant_for_email,
    issue_scim_token,
    jit_provision_user,
    list_tenants,
    saml_enabled,
    upsert_tenant,
)
from app.services.security_audit_service import record_security_event
from app.utils.logger import logger
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/sso", tags=["SSO"])


def _sso_login_redirect(
    request: Request, user_id: str, email: str | None, binding_cookie: str, binding_path: str
) -> RedirectResponse:
    """Finish an SSO login exactly like every other login path.

    Issues the session through the shared cookie policy (session, legacy alias
    and CSRF cookies) and burns the one-shot SAML/OIDC binding cookie.
    """
    session_token = create_session_token(user_id, email=email, request=request)
    response = RedirectResponse(url=os.getenv("OIDC_SUCCESS_REDIRECT", "/"), status_code=302)
    set_auth_cookies(response, session_token, request)
    response.delete_cookie(binding_cookie, path=binding_path)
    return response


# ----- public surface -------------------------------------------------------


class SsoDiscoverRequest(BaseModel):
    email: str = Field(..., description="Email address to look up tenant for")


@router.post("/discover")
async def sso_discover(req: SsoDiscoverRequest) -> dict[str, Any]:
    """Tell the client whether an email should use SSO and where to start."""
    tenant = find_tenant_for_email(req.email)
    if not tenant:
        return {"sso": False}
    return {
        "sso": True,
        "tenant_slug": tenant["slug"],
        "protocol": tenant["protocol"],
        "display_name": tenant["display_name"],
        # Must match the implemented router path below.
        "start_url": f"/api/sso/start/{tenant['slug']}",
    }


# ----- admin surface --------------------------------------------------------


class TenantUpsertRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    protocol: str = Field(..., pattern="^(saml|oidc)$")
    email_domain: str = Field(..., min_length=3, max_length=253)
    idp_entity_id: str | None = None
    idp_sso_url: str | None = None
    idp_x509_cert: str | None = None
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    jit_provisioning: bool = True
    require_mfa: bool = True
    default_role: str = "member"
    scim_token: str | None = Field(
        default=None,
        description="If provided, replaces the stored SCIM bearer token.",
    )


@router.get("/admin/tenants")
async def admin_list_tenants(admin_id: str = Depends(require_admin)) -> dict[str, list[Any]]:
    return {"tenants": list_tenants()}


@router.post("/admin/tenants")
async def admin_upsert_tenant(
    req: TenantUpsertRequest,
    request: Request,
    admin_id: str = Depends(require_admin),
):
    try:
        row = upsert_tenant(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_admin_event(
        actor_user_id=admin_id,
        action="sso.tenant_upsert",
        resource=req.slug,
        request_ip=getattr(getattr(request, "client", None), "host", None),
        user_agent=request.headers.get("user-agent"),
        metadata={"protocol": req.protocol, "email_domain": req.email_domain},
    )
    return {"tenant": row}


@router.post("/admin/tenants/{slug}/scim-token")
async def admin_rotate_scim_token(
    slug: str,
    request: Request,
    admin_id: str = Depends(require_admin),
):
    """Issue a fresh SCIM bearer token for a tenant. Only the plaintext is
    returned (and only once). Hash is persisted by ``upsert_tenant``."""
    new_token = issue_scim_token()
    import hashlib

    new_hash = hashlib.sha256(new_token.encode()).hexdigest()
    from app.db.database import get_db_connection

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE sso_tenant_configs SET scim_token_hash = %s, updated_at = NOW() "
                    "WHERE slug = %s AND disabled_at IS NULL",
                    (new_hash, slug),
                )
                if cur.rowcount == 0:
                    raise HTTPException(status_code=404, detail="Tenant not found")
            conn.commit()
    except HTTPException:
        raise
    except Exception:
        logger.exception("[sso] scim token rotation failed for %s", slug)
        raise HTTPException(status_code=500, detail="Failed to rotate SCIM token") from None
    record_admin_event(
        actor_user_id=admin_id,
        action="sso.scim_token_rotate",
        resource=slug,
        request_ip=getattr(getattr(request, "client", None), "host", None),
        user_agent=request.headers.get("user-agent"),
    )
    return {"token": new_token, "message": "Store securely; will not be shown again."}


# ----- start endpoints ------------------------------------------------------


_OIDC_STATE_COOKIE = "sso_oidc_state"
_OIDC_STATE_TTL_SECONDS = 600  # 10 min — enough for a slow IdP redirect
_SAML_REQID_COOKIE = "sso_saml_reqid"


def _verify_saml_reqid(slug: str, cookie_val: str | None) -> str | None:
    """Return the verified AuthnRequest ID, or ``None`` on any failure."""
    if not cookie_val:
        return None
    import base64
    import hashlib
    import hmac
    import time as _time

    from app.security.config import session_secret

    try:
        pad = "=" * (-len(cookie_val) % 4)
        decoded = base64.urlsafe_b64decode(cookie_val + pad).decode()
        parts = decoded.split("|")
        if len(parts) != 4:
            return None
        c_slug, c_req, c_exp, c_sig = parts
        payload = f"{c_slug}|{c_req}|{c_exp}"
        expected = hmac.new(session_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, c_sig):
            return None
        if c_slug != slug:
            return None
        if int(c_exp) < int(_time.time()):
            return None
        return c_req
    except Exception:
        return None


def _mint_oidc_state(slug: str) -> tuple[str, str, str]:
    """Return (state, nonce) and the signed cookie value to set on the
    response. We use the existing session secret so we don't need new
    KMS plumbing for an ephemeral, 10-minute, single-use binding.
    """
    import base64
    import hashlib
    import hmac
    import secrets
    import time

    from app.security.config import session_secret

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    expires = int(time.time()) + _OIDC_STATE_TTL_SECONDS
    payload = f"{slug}|{state}|{nonce}|{expires}"
    sig = hmac.new(session_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    cookie_val = base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode().rstrip("=")
    return state, nonce, cookie_val


def _verify_oidc_state(slug: str, presented_state: str, cookie_val: str | None) -> str | None:
    """Validate the signed cookie + state binding. Returns the bound nonce
    on success, or ``None`` on any failure. Always constant-time.
    """
    if not cookie_val or not presented_state:
        return None
    import base64
    import hashlib
    import hmac
    import time

    from app.security.config import session_secret

    try:
        pad = "=" * (-len(cookie_val) % 4)
        decoded = base64.urlsafe_b64decode(cookie_val + pad).decode()
        parts = decoded.split("|")
        if len(parts) != 5:
            return None
        c_slug, c_state, c_nonce, c_exp, c_sig = parts
        payload = f"{c_slug}|{c_state}|{c_nonce}|{c_exp}"
        expected_sig = hmac.new(
            session_secret().encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, c_sig):
            return None
        if c_slug != slug:
            return None
        if not hmac.compare_digest(c_state, presented_state):
            return None
        if int(c_exp) < int(time.time()):
            return None
        return c_nonce
    except Exception:
        return None


@router.get("/start/{slug}")
async def sso_start(slug: str, request: Request):
    """Begin an SSO flow.

    OIDC: returns the authorize URL for the tenant's IdP.
    SAML: returns 503 unless ``ENABLE_SAML_SSO=1`` is set, because the
          SAML response handler depends on ``python3-saml`` being installed
          and the tenant cert being loaded from KMS. This is intentional —
          turning SAML on without those pieces would be a footgun.
    """
    from app.db.database import get_db_connection

    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM sso_tenant_configs WHERE slug = %s AND disabled_at IS NULL",
            (slug,),
        )
        tenant = cur.fetchone()
    if not tenant:
        raise HTTPException(status_code=404, detail="Unknown SSO tenant")

    if tenant["protocol"] == "oidc":
        if not tenant.get("oidc_issuer") or not tenant.get("oidc_client_id"):
            raise HTTPException(status_code=503, detail="Tenant OIDC config incomplete")
        from urllib.parse import urlencode

        from fastapi.responses import JSONResponse

        state, nonce, cookie_val = _mint_oidc_state(slug)
        redirect_uri = (
            os.getenv("OIDC_REDIRECT_URI")
            or f"https://{os.getenv('REPLIT_DEV_DOMAIN', 'manifeststartup.com')}/api/sso/callback/{slug}"
        )
        params = {
            "client_id": tenant["oidc_client_id"],
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
        }
        url = f"{tenant['oidc_issuer'].rstrip('/')}/authorize?{urlencode(params)}"
        resp = JSONResponse({"authorize_url": url})
        # Browser-bound, single-use state. HttpOnly so JS can't read; SameSite=Lax
        # so it survives the IdP redirect back; Secure off only in dev.
        resp.set_cookie(
            _OIDC_STATE_COOKIE,
            cookie_val,
            httponly=True,
            secure=secure_cookies_enabled(request),
            samesite="lax",
            max_age=_OIDC_STATE_TTL_SECONDS,
            path=f"/api/sso/callback/{slug}",
        )
        return resp

    if not saml_enabled():
        raise HTTPException(
            status_code=503,
            detail="SAML SSO is not enabled in this deployment. Set ENABLE_SAML_SSO=1 to activate.",
        )
    if not (
        tenant.get("idp_sso_url") and tenant.get("idp_entity_id") and tenant.get("idp_x509_cert")
    ):
        raise HTTPException(status_code=503, detail="Tenant SAML config incomplete")

    import base64
    import hashlib
    import hmac
    import time as _time

    from app.security.config import session_secret
    from app.security.saml_handler import build_authn_request

    http_host = os.getenv(
        "SAML_PUBLIC_HOST",
        os.getenv("REPLIT_DEV_DOMAIN", "manifeststartup.com"),
    )
    relay_state = slug
    try:
        url, request_id = build_authn_request(tenant, http_host, relay_state=relay_state)
    except Exception as exc:
        logger.error("[sso] SAML AuthnRequest build failed for %s: %s", slug, exc)
        raise HTTPException(status_code=500, detail="SAML AuthnRequest build failed") from exc

    # Bind request_id to the browser via signed HttpOnly cookie scoped
    # to the ACS path. Validated on the ACS callback to reject
    # unsolicited responses / login CSRF.
    exp = int(_time.time()) + 600
    payload = f"{slug}|{request_id}|{exp}"
    sig = hmac.new(session_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    cookie_val = base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode().rstrip("=")
    resp = JSONResponse({"authorize_url": url})
    resp.set_cookie(
        _SAML_REQID_COOKIE,
        cookie_val,
        httponly=True,
        secure=secure_cookies_enabled(request),
        samesite="lax",
        max_age=600,
        path=f"/api/sso/saml/{slug}/acs",
    )
    return resp


@router.post("/saml/{slug}/acs")
async def sso_saml_acs(slug: str, request: Request):
    """SAML 2.0 HTTP-POST binding Assertion Consumer Service.

    Validates signed ``SAMLResponse``, JIT-provisions the subject, mints a
    session cookie and redirects to the post-login URL. Replays of the
    same assertion ID are rejected (one-shot via
    ``saml_processed_assertions``).
    """
    if not saml_enabled():
        raise HTTPException(status_code=503, detail="SAML SSO is not enabled")

    from app.db.database import get_db_connection
    from app.security.saml_handler import SamlError, process_acs_response

    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM sso_tenant_configs WHERE slug = %s LIMIT 1", (slug,))
        tenant = cur.fetchone()
    if not tenant or tenant.get("disabled_at") or tenant.get("protocol") != "saml":
        record_security_event(
            "sso_saml_unknown_tenant",
            metadata={"slug": slug},
            request_ip=getattr(getattr(request, "client", None), "host", None),
            actor_type="anonymous",
            action="sso_login",
            target_type="tenant",
            target_id=slug,
            outcome="failed",
        )
        raise HTTPException(status_code=404, detail="Unknown SAML tenant")

    form = await request.form()
    post_data = {k: form[k] for k in form}
    http_host = os.getenv(
        "SAML_PUBLIC_HOST",
        os.getenv("REPLIT_DEV_DOMAIN", "manifeststartup.com"),
    )

    expected_request_id = _verify_saml_reqid(slug, request.cookies.get(_SAML_REQID_COOKIE))
    if not expected_request_id:
        record_security_event(
            "sso_saml_unsolicited_response",
            metadata={"slug": slug},
            request_ip=getattr(getattr(request, "client", None), "host", None),
            actor_type="anonymous",
            action="sso_login",
            target_type="tenant",
            target_id=slug,
            outcome="rejected",
        )
        raise HTTPException(status_code=400, detail="Missing or invalid SAML request binding")

    try:
        name_id, attrs = process_acs_response(
            tenant, http_host, post_data, expected_request_id=expected_request_id
        )
    except SamlError as exc:
        record_security_event(
            "sso_saml_response_rejected",
            metadata={"slug": slug, "reason": str(exc)[:200]},
            request_ip=getattr(getattr(request, "client", None), "host", None),
            actor_type="anonymous",
            action="sso_login",
            target_type="tenant",
            target_id=slug,
            outcome="rejected",
        )
        raise HTTPException(status_code=400, detail="SAML response rejected") from exc

    email = (
        (attrs.get("email") or attrs.get("mail") or [None])[0]
        if isinstance(attrs.get("email") or attrs.get("mail"), list)
        else (attrs.get("email") or attrs.get("mail"))
    ) or name_id
    first = (
        (attrs.get("first_name") or attrs.get("givenName") or [None])[0]
        if isinstance(attrs.get("first_name") or attrs.get("givenName"), list)
        else None
    )
    last = (
        (attrs.get("last_name") or attrs.get("sn") or [None])[0]
        if isinstance(attrs.get("last_name") or attrs.get("sn"), list)
        else None
    )

    user_id = jit_provision_user(
        tenant=tenant,
        subject=name_id,
        email=email,
        first_name=first,
        last_name=last,
    )
    if not user_id:
        record_security_event(
            "sso_saml_provisioning_denied",
            metadata={"slug": slug, "subject": name_id},
            request_ip=getattr(getattr(request, "client", None), "host", None),
            actor_type="anonymous",
            action="sso_login",
            target_type="tenant",
            target_id=slug,
            outcome="denied",
        )
        raise HTTPException(status_code=403, detail="User not provisioned for tenant")

    # One-shot — burn the AuthnRequest binding cookie regardless.
    response = _sso_login_redirect(
        request, user_id, email, _SAML_REQID_COOKIE, f"/api/sso/saml/{slug}/acs"
    )
    record_security_event(
        "sso_saml_login_success",
        user_id=user_id,
        metadata={"slug": slug, "email": email},
        request_ip=getattr(getattr(request, "client", None), "host", None),
        actor_id=user_id,
        actor_type="user",
        action="sso_login",
        target_type="user",
        target_id=user_id,
        tenant_id=slug,
        outcome="success",
    )
    return response


@router.get("/callback/{slug}")
async def sso_oidc_callback(  # noqa: C901
    slug: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """OIDC authorization-code callback for an enterprise SSO tenant.

    Steps (every one of which is auth-critical):

    1. Confirm ``state`` matches the tenant slug (CSRF defence — minimal but
       prevents the obvious cross-tenant code-replay).
    2. Look up the tenant config; reject if disabled or missing client config.
    3. Exchange ``code`` at the IdP token endpoint for an ``id_token``.
    4. Verify the ID token signature, issuer, audience using the
       reusable ``verify_id_token`` helper (RS256/ES256 only, JWKS-cached).
    5. JIT-provision the local user (``jit_provision_user``) — fails closed
       when the tenant has JIT disabled and the subject is unknown.
    6. Mint a session JWT and set it as the standard ``session_token``
       HTTP-only cookie.
    7. Record both a generic security event and an admin-audit row.
    """
    import httpx

    if error:
        record_security_event(
            "sso_oidc_callback_idp_error",
            metadata={"slug": slug, "error": error},
            request_ip=getattr(getattr(request, "client", None), "host", None),
            actor_type="anonymous",
            action="sso_login",
            target_type="tenant",
            target_id=slug,
            outcome="failed",
        )
        raise HTTPException(status_code=400, detail=f"IdP returned error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    cookie_val = request.cookies.get(_OIDC_STATE_COOKIE)
    expected_nonce = _verify_oidc_state(slug, state or "", cookie_val)
    if not expected_nonce:
        record_security_event(
            "sso_oidc_state_mismatch",
            metadata={"slug": slug},
            request_ip=getattr(getattr(request, "client", None), "host", None),
            actor_type="anonymous",
            action="sso_login",
            target_type="tenant",
            target_id=slug,
            outcome="rejected",
        )
        raise HTTPException(status_code=400, detail="State mismatch or expired")

    from app.db.database import get_db_connection

    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM sso_tenant_configs "
            "WHERE slug = %s AND disabled_at IS NULL AND protocol = 'oidc'",
            (slug,),
        )
        tenant = cur.fetchone()
    if not tenant:
        raise HTTPException(status_code=404, detail="Unknown OIDC tenant")
    if not tenant.get("oidc_issuer") or not tenant.get("oidc_client_id"):
        raise HTTPException(status_code=503, detail="Tenant OIDC config incomplete")

    # Decrypt client secret if stored encrypted; otherwise allow env override
    # so a tenant can be tested before KMS-backed secret storage is wired.
    client_secret = os.getenv(f"OIDC_CLIENT_SECRET__{slug.upper()}")
    if not client_secret and tenant.get("oidc_client_secret_encrypted"):
        try:
            from app.services.kms_service import decrypt_blob  # type: ignore

            client_secret = decrypt_blob(tenant["oidc_client_secret_encrypted"]).decode()
        except Exception as exc:
            logger.error("[sso] failed to decrypt OIDC client secret for %s: %s", slug, exc)
    if not client_secret:
        raise HTTPException(status_code=503, detail="Tenant OIDC client secret not configured")

    redirect_uri = (
        os.getenv("OIDC_REDIRECT_URI")
        or f"https://{os.getenv('REPLIT_DEV_DOMAIN', 'manifeststartup.com')}/api/sso/callback/{slug}"
    )
    token_endpoint = f"{tenant['oidc_issuer'].rstrip('/')}/token"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": tenant["oidc_client_id"],
                    "client_secret": client_secret,
                },
                headers={"Accept": "application/json"},
            )
    except Exception as exc:
        logger.warning("[sso] OIDC token exchange transport failure for %s: %s", slug, exc)
        raise HTTPException(status_code=502, detail="IdP token exchange failed") from exc
    if resp.status_code >= 400:
        logger.warning(
            "[sso] OIDC token exchange failed (%s): %s", resp.status_code, resp.text[:200]
        )
        raise HTTPException(status_code=502, detail="IdP token exchange rejected")

    try:
        token_payload = resp.json()
    except Exception:
        raise HTTPException(
            status_code=502, detail="IdP returned non-JSON token response"
        ) from None
    id_token = token_payload.get("id_token")
    if not id_token:
        raise HTTPException(status_code=502, detail="IdP did not return id_token")

    claims = verify_id_token(
        id_token,
        audience=tenant["oidc_client_id"],
        issuer=tenant["oidc_issuer"],
        nonce=expected_nonce,
    )
    if not claims:
        record_security_event(
            "sso_oidc_id_token_rejected",
            metadata={"slug": slug},
            request_ip=getattr(getattr(request, "client", None), "host", None),
            actor_type="anonymous",
            action="sso_login",
            target_type="tenant",
            target_id=slug,
            outcome="rejected",
        )
        raise HTTPException(status_code=401, detail="ID token verification failed")

    subject = str(claims.get("sub") or "")
    email = str(claims.get("email") or "").lower()
    if not subject or not email:
        raise HTTPException(status_code=400, detail="ID token missing sub/email")

    user_id = jit_provision_user(
        tenant=tenant,
        subject=subject,
        email=email,
        first_name=claims.get("given_name"),
        last_name=claims.get("family_name"),
    )
    if not user_id:
        record_security_event(
            "sso_oidc_jit_blocked",
            metadata={"slug": slug, "email": email},
            request_ip=getattr(getattr(request, "client", None), "host", None),
            actor_type="anonymous",
            action="sso_login",
            target_type="tenant",
            target_id=slug,
            outcome="denied",
        )
        raise HTTPException(status_code=403, detail="User not provisioned for tenant")

    # One-shot state cookie — burn it now whether or not the rest succeeded.
    response = _sso_login_redirect(
        request, user_id, email, _OIDC_STATE_COOKIE, f"/api/sso/callback/{slug}"
    )
    record_security_event(
        "sso_oidc_login_success",
        user_id=user_id,
        metadata={"slug": slug, "email": email},
        request_ip=getattr(getattr(request, "client", None), "host", None),
        actor_id=user_id,
        actor_type="user",
        action="sso_login",
        target_type="user",
        target_id=user_id,
        tenant_id=slug,
        outcome="success",
    )
    record_admin_event(
        actor_user_id=user_id,
        action="sso.oidc_login",
        resource=slug,
        request_ip=getattr(getattr(request, "client", None), "host", None),
        user_agent=request.headers.get("user-agent"),
    )
    return response


__all__ = ["router", "jit_provision_user"]
