"""
Public trust center endpoint.

Exposes a JSON snapshot of the security & privacy program at
``GET /api/trust-center``. The payload mirrors the static documents
under ``docs/privacy/`` and ``docs/security/`` and is safe to publish
unauthenticated — it is the same information we share with prospective
auditors and customers.

Keep this in sync with:
  - docs/privacy/SUB_PROCESSORS.md
  - docs/privacy/ROPA.md
  - docs/privacy/DPIA.md
  - docs/privacy/BREACH_NOTIFICATION.md
  - docs/security/HIPAA_PROGRAM.md
  - docs/security/DATA_RETENTION.md
  - docs/security/TRUST_CENTER.md
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["trust-center"])


_PROGRAM_VERSION = os.getenv("MANIFEST_TRUST_CENTER_VERSION", "2026-04-19")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_retention_exceptions() -> list:
    """Surface the active retention exception register on the trust
    center so external auditors and customers can see (without auth)
    which legal holds are currently postponing default deletion. The
    public view never includes the SQL match predicate."""
    try:
        from app.services.retention_exception_register import public_view

        return public_view()
    except Exception:
        return []


@router.get("/trust", response_class=HTMLResponse, include_in_schema=False)
async def trust_center_page() -> HTMLResponse:
    """Customer-facing trust center landing page.

    A small, dependency-free HTML page so prospective customers,
    auditors, and security teams have a real, indexable URL to land on
    (``/trust``). It links out to the JSON API for machine consumers
    and to the public privacy/security documents."""
    payload = await trust_center()
    rights = "".join(
        f"<li><code>{name}</code>: <code>{path}</code></li>"
        for name, path in payload["data_subject_rights"].items()
        if isinstance(path, str)
    )
    controls = "".join(
        f"<li><strong>{key.replace('_', ' ').title()}:</strong> {value}</li>"
        for key, value in payload["controls"].items()
    )
    html = f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\">
<title>Manifest Trust Center</title>
<meta name=\"description\" content=\"Manifest security & privacy program: SOC 2, ISO 27001, GDPR, CCPA, HIPAA.\">
<style>body{{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;line-height:1.55;color:#0f172a}}h1{{margin-bottom:.25rem}}code{{background:#f1f5f9;padding:.1rem .3rem;border-radius:.25rem}}</style>
</head><body>
<h1>Manifest Trust Center</h1>
<p>Program version <code>{payload['program_version']}</code> &middot; generated {payload['generated_at']}</p>
<h2>Frameworks</h2><ul>
<li>SOC 2 (Security, Confidentiality, Availability)</li>
<li>ISO 27001</li>
<li>GDPR &amp; UK GDPR</li>
<li>CCPA / CPRA</li>
<li>HIPAA (Business Associate, BAA available)</li>
</ul>
<h2>Data subject rights</h2><ul>{rights}</ul>
<h2>Controls</h2><ul>{controls}</ul>
<h2>Documents</h2><ul>
<li><a href=\"/docs/privacy/PRIVACY_POLICY.md\">Privacy policy</a></li>
<li><a href=\"/docs/privacy/SUB_PROCESSORS.md\">Sub-processors</a></li>
<li><a href=\"/docs/privacy/ROPA.md\">Records of processing</a></li>
<li><a href=\"/docs/privacy/DPIA.md\">Data protection impact assessment</a></li>
<li><a href=\"/docs/privacy/BREACH_NOTIFICATION.md\">Breach notification</a></li>
<li><a href=\"/docs/security/HIPAA_PROGRAM.md\">HIPAA program</a></li>
</ul>
<p>Machine-readable snapshot: <a href=\"/api/trust-center\"><code>/api/trust-center</code></a></p>
<p>Contact: <code>{payload['company']['privacy_contact']}</code> &middot; <code>{payload['company']['security_contact']}</code></p>
</body></html>"""
    return HTMLResponse(content=html)


@router.get("/api/trust-center")
async def trust_center() -> dict[str, Any]:
    return {
        "program_version": _PROGRAM_VERSION,
        "generated_at": _now_iso(),
        "company": {
            "name": "Manifest",
            "privacy_contact": "privacy@manifest.example",
            "security_contact": "security@manifest.example",
            "dpo_contact": "dpo@manifest.example",
            "responsible_disclosure": "security@manifest.example",
        },
        "frameworks": {
            "soc2": {
                "status": "in_scope_design",
                "trust_services": ["security", "confidentiality", "availability"],
            },
            "iso_27001": {"status": "in_scope_design"},
            "gdpr": {
                "status": "in_scope_implementation",
                "lawful_bases": ["contract", "consent", "legitimate_interest"],
            },
            "ccpa_cpra": {"status": "in_scope_implementation"},
            "hipaa": {"status": "ready_with_baa", "role": "business_associate"},
        },
        "data_subject_rights": {
            "access": "GET /api/dsar/access",
            "portability": "GET /api/dsar/portability",
            "rectification": "POST /api/dsar/rectify",
            "objection_optout": "POST /api/dsar/object",
            "erasure": "POST /api/dsar/erase",
            "consent": "GET|POST /api/privacy/consent",
            "sla_business_days": 30,
            "verification": "Authenticated session + email confirmation for destructive actions.",
        },
        "controls": {
            "encryption_in_transit": "TLS 1.2+ enforced; HSTS preload eligible.",
            "encryption_at_rest": "AES-256-GCM via per-tenant DEKs wrapped by KMS root key (T12).",
            "key_management": "Per-tenant DEKs; crypto-shred on right-to-erasure (T3).",
            "audit_logging": "Hash-chained, append-only, SIEM-mirrored, fail-closed (T14).",
            "mfa": "TOTP + WebAuthn; admin accounts require MFA (T11).",
            "session": "Rotating opaque cookies, step-up re-auth on sensitive actions (T11).",
            "secrets": "Replit secret store; no plaintext secrets in repo (T12).",
            "rate_limiting": "Per-route policies in app.security.rate_limit_policies (T19).",
            "vulnerability_management": "Dependency audit + SAST + HoundDog secret scan (T16).",
            "incident_response": "24x7 on-call, 72h GDPR + 60d HIPAA breach timers (BREACH_NOTIFICATION.md).",
        },
        "retention_exceptions": _safe_retention_exceptions(),
        "sub_processors_url": "/docs/privacy/SUB_PROCESSORS.md",
        "ropa_url": "/docs/privacy/ROPA.md",
        "dpia_url": "/docs/privacy/DPIA.md",
        "breach_notification_url": "/docs/privacy/BREACH_NOTIFICATION.md",
        "hipaa_program_url": "/docs/security/HIPAA_PROGRAM.md",
        "privacy_policy_url": "/docs/privacy/PRIVACY_POLICY.md",
    }


__all__ = ["router"]
