"""WebAuthn / passkey support (SEC-018).

Wraps the ``webauthn`` reference implementation. Stores credentials in
``webauthn_credentials`` and exposes the four ceremonies needed by
`@simplewebauthn/browser` on the frontend:

* ``begin_registration``  → returns options + a server-side challenge.
* ``finish_registration`` → verifies the attestation, persists the credential.
* ``begin_authentication``→ returns request options + challenge.
* ``finish_authentication``→ verifies the assertion, returns the credential
  row so the caller can mint a session and emit a step-up proof.

Challenges are stashed in ``step_up_verifications.method='webauthn_challenge'``
with a 5-min TTL — same table we already use for short-lived auth proofs.
A correctness bug in WebAuthn is silent and catastrophic, so the verify
helpers refuse to run unless the dependency is installed AND
``ENABLE_WEBAUTHN`` is explicitly truthy.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
from typing import Any

from app.db.database import get_db_connection
from app.utils.logger import logger

try:
    import webauthn  # type: ignore
    from webauthn.helpers.structs import (  # type: ignore
        AuthenticationCredential,
        PublicKeyCredentialDescriptor,
        RegistrationCredential,
    )

    _WEBAUTHN_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    webauthn = None  # type: ignore
    _WEBAUTHN_AVAILABLE = False


def webauthn_enabled() -> bool:
    if not _WEBAUTHN_AVAILABLE:
        return False
    flag = os.getenv("ENABLE_WEBAUTHN", "").strip().lower()
    return flag in {"1", "true", "yes"}


def _rp_id() -> str:
    return os.getenv("WEBAUTHN_RP_ID", "manifeststartup.com")


def _rp_name() -> str:
    return os.getenv("WEBAUTHN_RP_NAME", "Manifest Startup")


def _expected_origin() -> str:
    return os.getenv("WEBAUTHN_ORIGIN", f"https://{_rp_id()}")


# ---------------------------------------------------------------------------
# challenge stash  (uses step_up_verifications with method='webauthn_challenge')
# ---------------------------------------------------------------------------


def _stash_challenge(user_id: str, kind: str, challenge: bytes) -> None:
    payload = base64.urlsafe_b64encode(challenge).decode().rstrip("=")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # 5-min TTL is plenty for an interactive ceremony; older rows
            # for the same (user, kind) are revoked so only the latest
            # challenge is valid.
            cur.execute(
                "UPDATE step_up_verifications SET revoked_at = NOW() "
                "WHERE user_id = %s AND method = %s AND revoked_at IS NULL",
                (user_id, kind),
            )
            cur.execute(
                "INSERT INTO step_up_verifications "
                "(user_id, method, expires_at, user_agent) "
                "VALUES (%s, %s, NOW() + INTERVAL '5 minutes', %s)",
                (user_id, kind, payload),
            )
        conn.commit()


def _consume_challenge(user_id: str, kind: str) -> bytes | None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_agent FROM step_up_verifications "
                "WHERE user_id = %s AND method = %s "
                "  AND revoked_at IS NULL AND expires_at > NOW() "
                "ORDER BY verified_at DESC LIMIT 1",
                (user_id, kind),
            )
            row = cur.fetchone()
            if not row:
                return None
            cur.execute(
                "UPDATE step_up_verifications SET revoked_at = NOW() WHERE id = %s",
                (row["id"],),
            )
        conn.commit()
    raw = row["user_agent"]
    pad = "=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(raw + pad)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# credential storage
# ---------------------------------------------------------------------------


def list_credentials(user_id: str) -> list[dict[str, Any]]:
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, nickname, transports, created_at, last_used_at "
                "FROM webauthn_credentials "
                "WHERE user_id = %s AND revoked_at IS NULL "
                "ORDER BY created_at DESC",
                (user_id,),
            )
            return cur.fetchall() or []
    except Exception as exc:
        logger.warning("[webauthn] list failed: %s", exc)
        return []


def revoke_credential(user_id: str, credential_id: str) -> bool:
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE webauthn_credentials SET revoked_at = NOW() "
                    "WHERE id = %s AND user_id = %s AND revoked_at IS NULL",
                    (credential_id, user_id),
                )
                ok = cur.rowcount > 0
            conn.commit()
        return ok
    except Exception as exc:
        logger.warning("[webauthn] revoke failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# registration ceremony
# ---------------------------------------------------------------------------


def begin_registration(user_id: str, email: str) -> dict[str, Any]:
    if not webauthn_enabled():
        raise RuntimeError(
            "WebAuthn is disabled. Install the `webauthn` package and set ENABLE_WEBAUTHN=1."
        )
    challenge = secrets.token_bytes(32)
    options = webauthn.generate_registration_options(  # type: ignore[attr-defined]
        rp_id=_rp_id(),
        rp_name=_rp_name(),
        user_id=user_id.encode(),
        user_name=email,
        challenge=challenge,
    )
    _stash_challenge(user_id, "webauthn_register_challenge", challenge)
    return {"options": json.loads(webauthn.options_to_json(options))}  # type: ignore[attr-defined]


def finish_registration(
    user_id: str, credential_json: dict[str, Any], nickname: str | None = None
) -> dict[str, Any]:
    if not webauthn_enabled():
        raise RuntimeError("WebAuthn disabled")
    challenge = _consume_challenge(user_id, "webauthn_register_challenge")
    if not challenge:
        raise ValueError("Registration challenge expired or not found")
    credential = RegistrationCredential.parse_raw(json.dumps(credential_json))  # type: ignore[attr-defined]
    verification = webauthn.verify_registration_response(  # type: ignore[attr-defined]
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=_rp_id(),
        expected_origin=_expected_origin(),
        require_user_verification=True,
    )
    transports = credential_json.get("response", {}).get("transports") or []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO webauthn_credentials
                    (user_id, credential_id, public_key, sign_count, transports, aaguid, nickname)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (credential_id) DO UPDATE SET
                    public_key = EXCLUDED.public_key,
                    sign_count = EXCLUDED.sign_count,
                    revoked_at = NULL
                RETURNING id
                """,
                (
                    user_id,
                    bytes(verification.credential_id),
                    bytes(verification.credential_public_key),
                    int(verification.sign_count),
                    transports,
                    str(
                        getattr(verification, "aaguid", None)
                        or "00000000-0000-0000-0000-000000000000"
                    ),
                    nickname,
                ),
            )
            cred_row = cur.fetchone()
        conn.commit()
    return {"credential_db_id": str(cred_row["id"])}


# ---------------------------------------------------------------------------
# authentication ceremony
# ---------------------------------------------------------------------------


def begin_authentication(user_id: str) -> dict[str, Any]:
    if not webauthn_enabled():
        raise RuntimeError("WebAuthn disabled")
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT credential_id, transports FROM webauthn_credentials "
            "WHERE user_id = %s AND revoked_at IS NULL",
            (user_id,),
        )
        rows = cur.fetchall() or []
    if not rows:
        raise ValueError("No registered credentials")
    descriptors = [
        PublicKeyCredentialDescriptor(  # type: ignore[call-arg]
            id=bytes(r["credential_id"]),
            transports=r.get("transports") or None,
        )
        for r in rows
    ]
    challenge = secrets.token_bytes(32)
    options = webauthn.generate_authentication_options(  # type: ignore[attr-defined]
        rp_id=_rp_id(),
        challenge=challenge,
        allow_credentials=descriptors,
    )
    _stash_challenge(user_id, "webauthn_auth_challenge", challenge)
    return {"options": json.loads(webauthn.options_to_json(options))}  # type: ignore[attr-defined]


def finish_authentication(user_id: str, credential_json: dict[str, Any]) -> dict[str, Any]:
    if not webauthn_enabled():
        raise RuntimeError("WebAuthn disabled")
    challenge = _consume_challenge(user_id, "webauthn_auth_challenge")
    if not challenge:
        raise ValueError("Authentication challenge expired or not found")
    credential = AuthenticationCredential.parse_raw(json.dumps(credential_json))  # type: ignore[attr-defined]
    cred_id_bytes = bytes(credential.raw_id)
    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, public_key, sign_count FROM webauthn_credentials "
            "WHERE user_id = %s AND credential_id = %s AND revoked_at IS NULL",
            (user_id, cred_id_bytes),
        )
        cred = cur.fetchone()
    if not cred:
        raise ValueError("Unknown credential")
    verification = webauthn.verify_authentication_response(  # type: ignore[attr-defined]
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=_rp_id(),
        expected_origin=_expected_origin(),
        credential_public_key=bytes(cred["public_key"]),
        credential_current_sign_count=int(cred["sign_count"]),
        require_user_verification=True,
    )
    new_count = int(verification.new_sign_count)
    # Authenticator counter regression is a strong cloning indicator.
    if new_count <= int(cred["sign_count"]) and new_count != 0:
        logger.warning(
            "[webauthn] sign-count regression for cred=%s user=%s (old=%s new=%s)",
            cred["id"],
            user_id,
            cred["sign_count"],
            new_count,
        )
        raise ValueError("Authenticator counter regression — possible cloned credential")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE webauthn_credentials "
                "SET sign_count = %s, last_used_at = NOW() WHERE id = %s",
                (new_count, cred["id"]),
            )
        conn.commit()
    return {"verified": True, "credential_db_id": str(cred["id"])}
