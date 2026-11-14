"""
Envelope encryption primitives (Task #12 — Data protection, encryption & secrets).

Design
------
We follow standard KMS envelope-encryption mechanics:

    plaintext --(DEK, AES-256-GCM)--> ciphertext_field
    DEK -------(KEK, AES-256-GCM)--> wrapped_dek (stored in `tenant_data_keys`)

* The **KEK** ("key-encryption key") never touches user data. It is supplied
  via the ``MANIFEST_KEK_<version>`` environment variables (base64-url encoded
  32 bytes). The active KEK version is selected by ``MANIFEST_KEK_ACTIVE_VERSION``.
  Multiple versions can coexist so that key rotation is online: writers always
  use the active version, readers can unwrap any wrapped DEK whose KEK version
  is still configured.
* The **DEK** ("data-encryption key") is per-tenant (or per-row for
  cross-tenant tables) and lives in the database, AES-GCM-wrapped under the
  KEK. We never persist a DEK in the clear. ``crypto_shred_tenant()``
  deletes the wrapped DEK row, which renders every ciphertext encrypted with
  it permanently unrecoverable — the cryptographic-erasure primitive that
  backs ``purge_tenant`` (GDPR Art. 17).
* **Field encryption** uses AES-256-GCM. We persist a single opaque blob laid
  out as ``b"\\x01" || kek_version(2 bytes BE) || nonce(12 bytes) || ciphertext+tag``.
  The leading ``\\x01`` is the *envelope format version* so we can change the
  layout without ambiguity in the future.

Operational rules
-----------------
* **Fail closed on decrypt errors.** If a row's ciphertext is corrupt or the
  KEK version is unknown, ``decrypt_field`` raises — the caller is expected to
  surface the failure rather than leak plaintext-or-empty.
* **Never log keys, never log plaintext.** All log lines reference key
  versions and ciphertext lengths only.
* **Backwards compatibility.** Reader helpers tolerate a missing ciphertext
  column and fall back to the legacy plaintext column when
  ``ENCRYPT_INTEGRATIONS_TOKENS`` (or its peers) is off, so the migration is
  online and reversible.
"""

from __future__ import annotations

import base64
import hashlib
import os
import struct
import threading
from dataclasses import dataclass

from app.utils.logger import logger
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# -----------------------------------------------------------------------------
# KEK loading
# -----------------------------------------------------------------------------

ENVELOPE_VERSION = 0x01
NONCE_BYTES = 12
KEY_BYTES = 32  # AES-256

_kek_lock = threading.Lock()
_kek_cache: dict[int, bytes] = {}


def _decode_b64(value: str) -> bytes:
    """Accept either standard or URL-safe base64 with optional padding."""
    cleaned = value.strip().replace("-", "+").replace("_", "/")
    padding = "=" * ((4 - len(cleaned) % 4) % 4)
    return base64.b64decode(cleaned + padding)


def _load_kek_from_env(version: int) -> bytes | None:
    raw = os.getenv(f"MANIFEST_KEK_V{version}")
    if not raw:
        return None
    try:
        key = _decode_b64(raw)
    except Exception as exc:
        raise RuntimeError(f"MANIFEST_KEK_V{version} is not valid base64") from exc
    if len(key) != KEY_BYTES:
        raise RuntimeError(
            f"MANIFEST_KEK_V{version} must decode to {KEY_BYTES} bytes (got {len(key)})"
        )
    return key


def _dev_fallback_kek() -> bytes:
    """Deterministic dev-only KEK derived from SESSION_SECRET.

    NEVER reachable in production: ``get_kek()`` raises if no real KEK is
    configured and ``MANIFEST_ENV=production``. This exists only so unit
    tests and local dev don't need to manage a separate base64 secret.
    """
    seed = (os.getenv("SESSION_SECRET") or "manifest-dev-kek-fallback").encode()
    return hashlib.sha256(b"manifest:kek:v0:" + seed).digest()


def get_active_kek_version() -> int:
    raw = (os.getenv("MANIFEST_KEK_ACTIVE_VERSION") or "1").strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"MANIFEST_KEK_ACTIVE_VERSION must be an int (got {raw!r})") from exc


def get_kek(version: int) -> bytes:
    """Resolve a KEK by version via the configured provider.

    Provider selection (see ``app.security.kek_provider``) is controlled by
    ``MANIFEST_KEK_PROVIDER``. The default ``env`` provider preserves the
    historical behaviour (``MANIFEST_KEK_V<n>``); production deployments
    should switch to ``aws-kms`` or ``vault-transit``.

    A dev-only deterministic fallback is used when no provider returns a
    key AND ``MANIFEST_ENV`` is not ``production``.
    """
    with _kek_lock:
        cached = _kek_cache.get(version)
        if cached is not None:
            return cached
        # Lazy import to avoid a cycle at module load.
        from app.security.kek_provider import get_provider

        provider = get_provider()
        key = provider.load(version)
        if key is None:
            env = (os.getenv("MANIFEST_ENV") or os.getenv("ENVIRONMENT") or "").lower()
            if env == "production":
                raise RuntimeError(
                    f"KEK v{version} is not configured for provider "
                    f"{provider.name!r}. Refusing to use the dev fallback in production."
                )
            logger.warning(
                "[crypto] Using dev-fallback KEK v%s (provider=%s) — configure a real KEK for production.",
                version,
                provider.name,
            )
            key = _dev_fallback_kek()
        if len(key) != KEY_BYTES:
            raise RuntimeError(
                f"KEK v{version} from provider {provider.name!r} has wrong length: {len(key)}"
            )
        _kek_cache[version] = key
        return key


def reset_kek_cache_for_test() -> None:  # pragma: no cover - test helper
    with _kek_lock:
        _kek_cache.clear()


# -----------------------------------------------------------------------------
# DEK wrap / unwrap
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class WrappedDEK:
    kek_version: int
    nonce: bytes
    ciphertext: bytes  # includes GCM tag

    def to_blob(self) -> bytes:
        return (
            bytes([ENVELOPE_VERSION])
            + struct.pack(">H", self.kek_version)
            + self.nonce
            + self.ciphertext
        )

    @classmethod
    def from_blob(cls, blob: bytes) -> WrappedDEK:
        if not blob or blob[0] != ENVELOPE_VERSION:
            raise ValueError("Unknown envelope version")
        if len(blob) < 1 + 2 + NONCE_BYTES + 16:
            raise ValueError("Wrapped DEK blob too short")
        kek_version = struct.unpack(">H", blob[1:3])[0]
        nonce = blob[3 : 3 + NONCE_BYTES]
        ct = blob[3 + NONCE_BYTES :]
        return cls(kek_version=kek_version, nonce=nonce, ciphertext=ct)


def generate_dek() -> bytes:
    return os.urandom(KEY_BYTES)


def wrap_dek(dek: bytes, *, aad: bytes = b"manifest:dek") -> WrappedDEK:
    if len(dek) != KEY_BYTES:
        raise ValueError("DEK must be 32 bytes")
    version = get_active_kek_version()
    kek = get_kek(version)
    nonce = os.urandom(NONCE_BYTES)
    ct = AESGCM(kek).encrypt(nonce, dek, aad)
    return WrappedDEK(kek_version=version, nonce=nonce, ciphertext=ct)


def unwrap_dek(wrapped: WrappedDEK, *, aad: bytes = b"manifest:dek") -> bytes:
    kek = get_kek(wrapped.kek_version)
    return AESGCM(kek).decrypt(wrapped.nonce, wrapped.ciphertext, aad)


# -----------------------------------------------------------------------------
# Field encryption
# -----------------------------------------------------------------------------


def encrypt_field(plaintext: str, dek: bytes, *, aad: bytes | None = None) -> bytes:
    """Encrypt a UTF-8 string under ``dek`` and wrap it in our envelope.

    The envelope embeds the active KEK version (NOT the DEK itself — the DEK
    sits on the wrapped row keyed by tenant_id/row_id). On decrypt the caller
    re-fetches the wrapped DEK and unwraps with the matching KEK.
    """
    if plaintext is None:
        raise ValueError("plaintext is required")
    if len(dek) != KEY_BYTES:
        raise ValueError("DEK must be 32 bytes")
    nonce = os.urandom(NONCE_BYTES)
    ct = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), aad)
    # Same envelope shape as wrapped DEKs so consumers learn one layout.
    version = get_active_kek_version()
    return bytes([ENVELOPE_VERSION]) + struct.pack(">H", version) + nonce + ct


def decrypt_field(blob: bytes, dek: bytes, *, aad: bytes | None = None) -> str:
    """Decrypt and return UTF-8 plaintext. Raises on any failure (fail-closed)."""
    if not blob:
        raise ValueError("ciphertext is required")
    if blob[0] != ENVELOPE_VERSION:
        raise ValueError("Unknown ciphertext envelope version")
    if len(blob) < 1 + 2 + NONCE_BYTES + 16:
        raise ValueError("Ciphertext blob too short")
    nonce = blob[3 : 3 + NONCE_BYTES]
    ct = blob[3 + NONCE_BYTES :]
    return AESGCM(dek).decrypt(nonce, ct, aad).decode("utf-8")


def is_encrypted_blob(value: object) -> bool:
    """Cheap sniff so callers can detect already-encrypted columns mid-migration."""
    if isinstance(value, memoryview):
        value = bytes(value)
    if not isinstance(value, bytes | bytearray):
        return False
    return len(value) > 1 + 2 + NONCE_BYTES + 16 and value[0] == ENVELOPE_VERSION


__all__ = [
    "ENVELOPE_VERSION",
    "NONCE_BYTES",
    "KEY_BYTES",
    "WrappedDEK",
    "decrypt_field",
    "encrypt_field",
    "generate_dek",
    "get_active_kek_version",
    "get_kek",
    "is_encrypted_blob",
    "reset_kek_cache_for_test",
    "unwrap_dek",
    "wrap_dek",
]
