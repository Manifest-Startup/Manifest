"""Helpers for generating and verifying password reset tokens.

The raw token is what we send to the user via email. Only the SHA-256
hash is ever persisted, so a database leak does not let an attacker
forge a usable reset link.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

RAW_TOKEN_BYTES = 32


def generate_reset_token() -> tuple[str, str]:
    """Return ``(raw_token, token_hash)``.

    ``raw_token`` is a 256-bit URL-safe string suitable for embedding in
    a reset link. ``token_hash`` is the hex-encoded SHA-256 digest of
    the raw token and is what we store in the database.
    """

    raw_token = secrets.token_urlsafe(RAW_TOKEN_BYTES)
    return raw_token, hash_token(raw_token)


def hash_token(raw_token: str) -> str:
    """Hash a raw reset token for DB lookup / comparison."""

    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def compare_token_hashes(a: str, b: str) -> bool:
    """Constant-time equality check for two token hashes.

    The primary reset flow finds tokens via a unique-indexed lookup on
    the digest column, so this helper is mostly defense-in-depth: any
    future code path that needs to compare two hashes (for example,
    out-of-band verification or audit tooling) should use this rather
    than ``==`` to avoid leaking timing information.
    """

    return hmac.compare_digest(a or "", b or "")
