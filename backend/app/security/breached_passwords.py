"""HaveIBeenPwned k-anonymity password check (SEC-008).

Sends only the SHA-1 prefix (5 hex chars) of the candidate password to
``api.pwnedpasswords.com``; the full hash never leaves this process.
The request is HTTPS, has a 3-second timeout, and gracefully degrades
to "not breached" on network failure (we don't want HIBP downtime to
block password resets).

Reference: https://haveibeenpwned.com/API/v3#PwnedPasswords (k-anonymity model).
"""

from __future__ import annotations

import hashlib
import os

import httpx
from app.utils.logger import logger

HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"
HIBP_TIMEOUT_SECONDS = 3.0
HIBP_USER_AGENT = "manifest-startup-platform-security-check"


def is_password_breached(password: str, *, threshold: int = 1) -> bool:
    """Return True if the password appears at least ``threshold`` times in HIBP.

    ``threshold=1`` rejects any breached password (recommended for new
    accounts and resets). For step-up flows you can raise this to
    something like 100 if you want to allow weak-but-not-catastrophic
    reuse, but the default policy is strict.
    """
    if not password:
        return False
    if os.getenv("DISABLE_HIBP_CHECK", "").strip().lower() in {"1", "true", "yes"}:
        return False

    sha1 = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]

    try:
        with httpx.Client(timeout=HIBP_TIMEOUT_SECONDS) as client:
            resp = client.get(
                HIBP_RANGE_URL.format(prefix=prefix),
                headers={"User-Agent": HIBP_USER_AGENT, "Add-Padding": "true"},
            )
            if resp.status_code != 200:
                logger.warning("[hibp] non-200 response: %s", resp.status_code)
                return False
            for line in resp.text.splitlines():
                line = line.strip()
                if not line or ":" not in line:
                    continue
                hash_suffix, count_str = line.split(":", 1)
                if hash_suffix.upper() != suffix:
                    continue
                try:
                    count = int(count_str.strip())
                except ValueError:
                    continue
                return count >= threshold
            return False
    except Exception as exc:
        # Fail-open: don't block password resets on HIBP outage.
        logger.warning("[hibp] check failed (failing open): %s", exc)
        return False
