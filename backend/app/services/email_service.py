"""Outbound transactional email via Resend.

Designed to be safe in environments where Resend is not configured: if
``RESEND_API_KEY`` is unset, calls log a warning and return without
raising, so the password-reset flow can still complete and (in dev)
the reset link is visible in the server console.
"""

from __future__ import annotations

import os
from html import escape

import httpx
from app.utils.logger import logger

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_FROM = "Manifest <noreply@manifeststartup.com>"


def _from_address() -> str:
    return os.getenv("RESEND_FROM_EMAIL", "").strip() or DEFAULT_FROM


def _build_password_reset_html(reset_url: str) -> str:
    safe_url = escape(reset_url, quote=True)
    return f"""<!doctype html>
<html lang="en">
  <body style="margin:0;padding:0;background:#f6f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0;">
      <tr><td align="center">
        <table role="presentation" width="520" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:16px;padding:40px;box-shadow:0 6px 24px rgba(15,23,42,0.06);">
          <tr><td>
            <h1 style="margin:0 0 16px;font-size:22px;line-height:1.3;">Reset your Manifest password</h1>
            <p style="margin:0 0 24px;font-size:15px;line-height:1.6;color:#334155;">
              We received a request to reset the password for your Manifest account.
              Click the button below to choose a new password. This link will expire
              in 30 minutes and can only be used once.
            </p>
            <p style="margin:0 0 32px;">
              <a href="{safe_url}"
                 style="display:inline-block;background:#0f172a;color:#ffffff;text-decoration:none;
                        padding:12px 22px;border-radius:10px;font-weight:600;font-size:15px;">
                Reset password
              </a>
            </p>
            <p style="margin:0 0 8px;font-size:13px;color:#64748b;">
              If the button doesn't work, paste this link into your browser:
            </p>
            <p style="margin:0 0 24px;font-size:13px;word-break:break-all;color:#475569;">
              <a href="{safe_url}" style="color:#475569;">{safe_url}</a>
            </p>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;" />
            <p style="margin:0;font-size:12px;color:#94a3b8;line-height:1.6;">
              If you didn't request a password reset, you can safely ignore this email —
              your password will not be changed.
            </p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def _build_password_reset_text(reset_url: str) -> str:
    return (
        "Reset your Manifest password\n"
        "----------------------------\n\n"
        "We received a request to reset the password for your Manifest account.\n"
        "Open the link below to choose a new password. It expires in 30 minutes\n"
        "and can only be used once.\n\n"
        f"{reset_url}\n\n"
        "If you didn't request a password reset, you can safely ignore this email —\n"
        "your password will not be changed.\n"
    )


def _build_guest_upgrade_html(claim_url: str) -> str:
    safe_url = escape(claim_url, quote=True)
    return f"""<!doctype html>
<html lang="en">
  <body style="margin:0;padding:0;background:#f6f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0;">
      <tr><td align="center">
        <table role="presentation" width="520" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:16px;padding:40px;box-shadow:0 6px 24px rgba(15,23,42,0.06);">
          <tr><td>
            <h1 style="margin:0 0 16px;font-size:22px;line-height:1.3;">Claim your Manifest account</h1>
            <p style="margin:0 0 24px;font-size:15px;line-height:1.6;color:#334155;">
              You asked to upgrade from a guest tryout. Choose a password on the next screen to keep your workspace
              under this email. This link expires in about an hour and works once.
            </p>
            <p style="margin:0 0 32px;">
              <a href="{safe_url}"
                 style="display:inline-block;background:#0f172a;color:#ffffff;text-decoration:none;
                        padding:12px 22px;border-radius:10px;font-weight:600;font-size:15px;">
                Claim account
              </a>
            </p>
            <p style="margin:0 0 8px;font-size:13px;color:#64748b;">
              If the button does not work, paste this link into your browser:
            </p>
            <p style="margin:0 0 24px;font-size:13px;word-break:break-all;color:#475569;">
              <a href="{safe_url}" style="color:#475569;">{safe_url}</a>
            </p>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;" />
            <p style="margin:0;font-size:12px;color:#94a3b8;line-height:1.6;">
              If you did not request this, you can ignore this email.
            </p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def _build_guest_upgrade_text(claim_url: str) -> str:
    return (
        "Claim your Manifest account\n"
        "---------------------------\n\n"
        "Open the link below to choose a password and keep your guest workspace under this email.\n"
        "The link expires in about an hour and works once.\n\n"
        f"{claim_url}\n\n"
        "If you did not request this, you can ignore this email.\n"
    )


async def send_guest_upgrade_email(to_email: str, claim_url: str) -> bool:
    """Send guest upgrade claim link. Returns True when Resend accepts the message."""

    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        logger.warning(
            "[email_service] RESEND_API_KEY not set; guest upgrade link for %s would have been: %s",
            to_email,
            claim_url,
        )
        return False

    payload = {
        "from": _from_address(),
        "to": [to_email],
        "subject": "Claim your Manifest account",
        "html": _build_guest_upgrade_html(claim_url),
        "text": _build_guest_upgrade_text(claim_url),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                RESEND_API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
        if response.status_code >= 400:
            logger.error(
                "[email_service] Resend guest-upgrade error for %s: status=%s body=%s",
                to_email,
                response.status_code,
                response.text[:500],
            )
            return False
        logger.info("[email_service] Guest upgrade email queued for %s", to_email)
        return True
    except Exception as exc:  # pragma: no cover - network errors
        logger.error("[email_service] Failed to send guest upgrade email to %s: %s", to_email, exc)
        return False


async def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    """Send a password reset email. Returns True on success.

    Never raises into the caller — failures are logged and the function
    returns False so the GraphQL resolver can keep returning the
    generic "if an account exists, we sent an email" response.
    """

    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        # Dev / unconfigured environments: surface the link in the logs
        # so contributors can still test the flow end-to-end.
        logger.warning(
            "[email_service] RESEND_API_KEY not set; password reset link for %s "
            "would have been sent. Link: %s",
            to_email,
            reset_url,
        )
        return False

    payload = {
        "from": _from_address(),
        "to": [to_email],
        "subject": "Reset your Manifest password",
        "html": _build_password_reset_html(reset_url),
        "text": _build_password_reset_text(reset_url),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                RESEND_API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
        if response.status_code >= 400:
            logger.error(
                "[email_service] Resend API error for %s: status=%s body=%s",
                to_email,
                response.status_code,
                response.text[:500],
            )
            return False
        logger.info("[email_service] Password reset email queued for %s", to_email)
        return True
    except Exception as exc:  # pragma: no cover - network errors
        logger.error("[email_service] Failed to send reset email to %s: %s", to_email, exc)
        return False
