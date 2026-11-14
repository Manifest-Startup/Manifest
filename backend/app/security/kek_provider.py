"""
KEK provider abstraction (Task #12 — managed-KMS hook).

The default ``EnvKEKProvider`` reads ``MANIFEST_KEK_V<n>`` from the
environment — appropriate for self-hosted Replit deployments where the
secret manager *is* the platform's encrypted env-var store. Production
deployments that mandate a managed KMS (AWS KMS, GCP KMS, Azure Key
Vault, HashiCorp Vault Transit, etc.) implement this interface and
register themselves via ``MANIFEST_KEK_PROVIDER``.

Selecting a provider
--------------------
Set ``MANIFEST_KEK_PROVIDER`` to one of:

* ``env`` (default)            — read from ``MANIFEST_KEK_V<n>`` env vars.
* ``aws-kms``                  — fetch KEK material via AWS KMS Decrypt
  on a base64 ciphertext stored at ``MANIFEST_KEK_V<n>_AWS_BLOB``. The
  effective KEK is the plaintext data key returned by KMS. Requires
  boto3 and IAM perms ``kms:Decrypt`` on the configured key alias.
* ``vault-transit``            — POST to Vault's Transit ``decrypt``
  endpoint at ``VAULT_ADDR``/``VAULT_TOKEN`` using the ciphertext at
  ``MANIFEST_KEK_V<n>_VAULT_CT``.

Both managed providers cache the unwrapped KEK in-process for the life
of the worker so we don't pay the KMS round-trip on every encrypt.
Cache invalidation = process restart, which is the same cadence as a
KEK rotation deployment.

This file deliberately stays small: the heavy lifting (envelope
encryption, DEK wrap/unwrap) lives in ``crypto.py``. The provider only
answers “give me the raw bytes for KEK version N”.
"""

from __future__ import annotations

import base64
import os
from typing import Protocol

from app.utils.logger import logger


class KEKProvider(Protocol):
    name: str

    def load(self, version: int) -> bytes | None:
        """Return the 32-byte KEK for ``version`` or ``None`` if unset."""
        ...


# ---------------------------------------------------------------------------
# Env-backed (default)
# ---------------------------------------------------------------------------


class EnvKEKProvider:
    name = "env"

    def load(self, version: int) -> bytes | None:
        # Defer to crypto._load_kek_from_env so behaviour stays in lock-step
        # with the historical default. Imported lazily to avoid a cycle.
        from app.security.crypto import _load_kek_from_env

        return _load_kek_from_env(version)


# ---------------------------------------------------------------------------
# AWS KMS
# ---------------------------------------------------------------------------


class AwsKmsKEKProvider:
    """Resolve KEKs by asking AWS KMS to decrypt a stored ciphertext blob.

    Operationally:

    1. Operator calls ``aws kms encrypt`` once per KEK version with the
       desired raw 32-byte KEK and a CMK alias they control.
    2. The base64 ciphertext is stored as
       ``MANIFEST_KEK_V<n>_AWS_BLOB``.
    3. At process boot, the first encrypt/decrypt triggers a single
       ``kms:Decrypt`` call; the resulting plaintext is cached.

    No KEK material ever lives in the env var — only the ciphertext.
    """

    name = "aws-kms"

    def __init__(self) -> None:
        self._region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")

    def load(self, version: int) -> bytes | None:
        ct_b64 = os.getenv(f"MANIFEST_KEK_V{version}_AWS_BLOB")
        if not ct_b64:
            return None
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "MANIFEST_KEK_PROVIDER=aws-kms requires boto3 to be installed"
            ) from exc
        ct = base64.b64decode(ct_b64.strip())
        client = boto3.client("kms", region_name=self._region)
        resp = client.decrypt(CiphertextBlob=ct)
        plaintext = resp["Plaintext"]
        if len(plaintext) != 32:
            raise RuntimeError(f"AWS KMS returned KEK of length {len(plaintext)}; expected 32")
        logger.info(
            "[kek_provider] AWS KMS unwrapped KEK v%s (%d bytes)",
            version,
            len(plaintext),
        )
        return plaintext


# ---------------------------------------------------------------------------
# HashiCorp Vault Transit
# ---------------------------------------------------------------------------


class VaultTransitKEKProvider:
    """Resolve KEKs via HashiCorp Vault's Transit secrets engine."""

    name = "vault-transit"

    def __init__(self) -> None:
        self._addr = os.getenv("VAULT_ADDR")
        self._token = os.getenv("VAULT_TOKEN")
        self._mount = os.getenv("VAULT_TRANSIT_MOUNT", "transit")
        self._key = os.getenv("VAULT_TRANSIT_KEY", "manifest-kek")

    def load(self, version: int) -> bytes | None:
        ct = os.getenv(f"MANIFEST_KEK_V{version}_VAULT_CT")
        if not ct:
            return None
        if not (self._addr and self._token):
            raise RuntimeError(
                "MANIFEST_KEK_PROVIDER=vault-transit requires VAULT_ADDR and VAULT_TOKEN"
            )
        import json as _json
        import urllib.request

        body = _json.dumps({"ciphertext": ct}).encode()
        req = urllib.request.Request(
            f"{self._addr.rstrip('/')}/v1/{self._mount}/decrypt/{self._key}",
            data=body,
            headers={"X-Vault-Token": self._token, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = _json.loads(resp.read())
        plaintext_b64 = payload["data"]["plaintext"]
        plaintext = base64.b64decode(plaintext_b64)
        if len(plaintext) != 32:
            raise RuntimeError(f"Vault returned KEK of length {len(plaintext)}; expected 32")
        logger.info(
            "[kek_provider] Vault Transit unwrapped KEK v%s (%d bytes)",
            version,
            len(plaintext),
        )
        return plaintext


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


_PROVIDERS = {
    "env": EnvKEKProvider,
    "aws-kms": AwsKmsKEKProvider,
    "vault-transit": VaultTransitKEKProvider,
}


def get_provider() -> KEKProvider:
    name = (os.getenv("MANIFEST_KEK_PROVIDER") or "env").strip().lower()
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise RuntimeError(
            f"Unknown MANIFEST_KEK_PROVIDER={name!r}; choose one of: "
            + ", ".join(sorted(_PROVIDERS))
        )
    return cls()


__all__ = [
    "AwsKmsKEKProvider",
    "EnvKEKProvider",
    "KEKProvider",
    "VaultTransitKEKProvider",
    "get_provider",
]
