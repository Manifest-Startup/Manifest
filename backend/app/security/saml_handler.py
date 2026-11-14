"""Production SAML 2.0 handler — built on ``python3-saml``.

Exposes two functions used by the route layer:

- ``build_authn_request(tenant, http_host)`` returns the redirect URL
  the browser should be sent to (HTTP-Redirect binding) and a small
  ``RelayState`` token bound to the tenant slug.
- ``process_acs_response(tenant, http_host, post_body)`` validates the
  POSTed ``SAMLResponse`` against the tenant's IdP X.509 certificate
  and returns ``(subject, attributes)`` on success or raises
  ``SamlError`` otherwise.

The minimum tenant fields required:
    - ``slug``
    - ``idp_entity_id``
    - ``idp_sso_url``
    - ``idp_x509_cert``  (PEM body, with or without BEGIN/END markers)

Replay protection: the ``InResponseTo`` ID and ``NotOnOrAfter`` window
are enforced by the underlying library; on top of that we record
processed Assertion IDs in ``saml_processed_assertions`` (one-shot)
so a replay within the validity window also fails.
"""

from __future__ import annotations

import os
import re
from typing import Any

from app.db.database import get_db_connection
from app.utils.logger import logger


class SamlError(Exception):
    """Raised when the SAML flow fails for any reason (parse, signature,
    replay, missing attribute). The message is safe to log; never echo
    raw upstream errors back to the browser unless explicitly cleaned.
    """


def _normalize_cert(pem: str) -> str:
    """Return the base64 body of a cert, stripping BEGIN/END markers if
    present — what python3-saml expects for ``x509cert``.
    """
    if not pem:
        return ""
    body = re.sub(r"-----(BEGIN|END) CERTIFICATE-----", "", pem).strip()
    return re.sub(r"\s+", "", body)


def _settings_for(tenant: dict[str, Any], http_host: str) -> dict[str, Any]:
    slug = tenant["slug"]
    sp_entity_id = os.getenv(
        "SAML_SP_ENTITY_ID", f"https://{http_host}/api/sso/saml/{slug}/metadata"
    )
    acs_url = f"https://{http_host}/api/sso/saml/{slug}/acs"
    return {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": sp_entity_id,
            "assertionConsumerService": {
                "url": acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        },
        "idp": {
            "entityId": tenant["idp_entity_id"],
            "singleSignOnService": {
                "url": tenant["idp_sso_url"],
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": _normalize_cert(tenant.get("idp_x509_cert") or ""),
        },
        "security": {
            "wantAssertionsSigned": True,
            "wantMessagesSigned": False,
            "wantNameIdEncrypted": False,
            "wantAssertionsEncrypted": False,
            "requestedAuthnContext": False,
            "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
            "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256",
        },
    }


def _request_data(http_host: str, post_data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "https": "on",
        "http_host": http_host,
        "server_port": "443",
        "script_name": "/",
        "get_data": {},
        "post_data": post_data or {},
    }


def build_authn_request(
    tenant: dict[str, Any], http_host: str, relay_state: str
) -> tuple[str, str]:
    """Return ``(redirect_url, authn_request_id)``.

    The caller is expected to bind ``authn_request_id`` to the browser
    (e.g. signed HttpOnly cookie scoped to the ACS path) and pass it
    back to :func:`process_acs_response` as ``expected_request_id`` so
    unsolicited / login-CSRF responses are rejected.
    """
    from onelogin.saml2.auth import OneLogin_Saml2_Auth

    auth = OneLogin_Saml2_Auth(_request_data(http_host), _settings_for(tenant, http_host))
    url = auth.login(return_to=relay_state)
    request_id = auth.get_last_request_id() or ""
    return url, request_id


def _record_assertion_or_replay(assertion_id: str, slug: str) -> bool:
    """One-shot replay protection on the assertion ID. Returns True on
    success (first time we see it), False if we've seen it already.
    """
    if not assertion_id:
        return False
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO saml_processed_assertions (assertion_id, tenant_slug, processed_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (assertion_id) DO NOTHING
                    RETURNING assertion_id
                    """,
                    (assertion_id, slug),
                )
                row = cur.fetchone()
            conn.commit()
        return row is not None
    except Exception as exc:
        # Fail closed — if we cannot record, treat as replay to avoid
        # accepting an unrepeatable token.
        logger.error("[saml] replay-table write failed: %s", exc)
        return False


def process_acs_response(
    tenant: dict[str, Any],
    http_host: str,
    post_body: dict[str, Any],
    *,
    expected_request_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Validate a SAMLResponse posted to the ACS endpoint.

    Returns ``(subject_email_or_nameid, attributes_dict)``.
    Raises ``SamlError`` on any validation failure.
    """
    from onelogin.saml2.auth import OneLogin_Saml2_Auth

    if not post_body.get("SAMLResponse"):
        raise SamlError("Missing SAMLResponse")

    if not (
        tenant.get("idp_x509_cert") and tenant.get("idp_entity_id") and tenant.get("idp_sso_url")
    ):
        raise SamlError("Tenant SAML config incomplete")

    try:
        auth = OneLogin_Saml2_Auth(
            _request_data(http_host, post_data=post_body),
            _settings_for(tenant, http_host),
        )
        # Binding the response to a specific outstanding AuthnRequest
        # rejects unsolicited / login-CSRF style responses.
        auth.process_response(request_id=expected_request_id or None)
    except Exception as exc:
        raise SamlError(f"SAML response parse failed: {exc}") from exc

    errors = auth.get_errors()
    if errors:
        reason = auth.get_last_error_reason() or ",".join(errors)
        raise SamlError(f"SAML validation failed: {reason}")
    if not auth.is_authenticated():
        raise SamlError("SAML response did not authenticate the subject")

    # Extract assertion ID for replay protection.
    try:
        assertion_id = auth.get_last_assertion_id()
    except Exception:
        assertion_id = None
    if not _record_assertion_or_replay(assertion_id or "", tenant["slug"]):
        raise SamlError("SAML assertion replay detected")

    name_id = auth.get_nameid()
    attributes = auth.get_attributes() or {}
    if not name_id:
        raise SamlError("SAML response missing NameID")
    return name_id, attributes
