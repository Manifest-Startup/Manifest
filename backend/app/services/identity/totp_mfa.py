import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from urllib.parse import quote

from app.db.database import get_db_connection
from app.security.config import is_production_environment, session_secret
from app.utils.logger import logger


def _mfa_encryption_key() -> str:
    key = (os.getenv("MFA_ENCRYPTION_KEY") or "").strip()
    if key:
        return key
    if is_production_environment():
        raise RuntimeError("MFA_ENCRYPTION_KEY must be configured in production.")
    return session_secret()


def generate_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode("utf-8").rstrip("=")


def generate_recovery_codes(count: int = 8) -> list[str]:
    return [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(count)]


def _hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode("utf-8")).hexdigest()


def _normalized_secret(secret: str) -> bytes:
    padded = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - (len(padded) % 8)) % 8)
    return base64.b32decode(f"{padded}{padding}")


def _totp_at(secret: str, counter: int, digits: int = 6) -> str:
    key = _normalized_secret(secret)
    message = struct.pack(">Q", counter)
    digest = hmac.new(key, message, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**digits)).zfill(digits)


def verify_totp(secret: str, code: str, *, window: int = 1, time_step: int = 30) -> bool:
    normalized_code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(normalized_code) != 6:
        return False
    current_counter = int(time.time() // time_step)
    for offset in range(-window, window + 1):
        if hmac.compare_digest(_totp_at(secret, current_counter + offset), normalized_code):
            return True
    return False


def otp_auth_uri(*, email: str, secret: str) -> str:
    issuer = "Manifest"
    return (
        f"otpauth://totp/{quote(issuer)}:{quote(email)}"
        f"?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )


def get_user_mfa_record(user_id: str) -> dict[str, object] | None:
    if not user_id:
        return None
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT
                        user_id,
                        pgp_sym_decrypt(secret_ciphertext::bytea, %s) AS secret,
                        recovery_codes,
                        enabled_at,
                        created_at
                    FROM user_totp_mfa
                    WHERE user_id = %s
                    """,
                (_mfa_encryption_key(), user_id),
            )
            return cur.fetchone()
    except Exception as exc:
        logger.warning("[totp_mfa] Failed to load MFA record for %s: %s", user_id, exc)
        return None


def get_user_mfa_status(user_id: str) -> dict[str, object]:
    record = get_user_mfa_record(user_id)
    recovery_codes = record.get("recovery_codes") if record else []
    return {
        "enabled": bool(record),
        "enabled_at": record.get("enabled_at") if record else None,
        "recovery_codes_remaining": len(recovery_codes or []),
    }


def enable_user_totp(user_id: str, secret: str, recovery_codes: list[str]) -> None:
    hashed_codes = [_hash_recovery_code(code) for code in recovery_codes]
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_totp_mfa (user_id, secret_ciphertext, recovery_codes, created_at, enabled_at)
                    VALUES (
                        %s,
                        pgp_sym_encrypt(%s, %s),
                        %s::jsonb,
                        NOW(),
                        NOW()
                    )
                    ON CONFLICT (user_id) DO UPDATE SET
                        secret_ciphertext = EXCLUDED.secret_ciphertext,
                        recovery_codes = EXCLUDED.recovery_codes,
                        enabled_at = NOW()
                    """,
                    (user_id, secret, _mfa_encryption_key(), json.dumps(hashed_codes)),
                )
            conn.commit()
    except Exception as exc:
        logger.error("[totp_mfa] Failed to enable MFA for %s: %s", user_id, exc)
        raise


def disable_user_totp(user_id: str) -> bool:
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM user_totp_mfa WHERE user_id = %s", (user_id,))
                deleted = cur.rowcount > 0
            conn.commit()
        return deleted
    except Exception as exc:
        logger.warning("[totp_mfa] Failed to disable MFA for %s: %s", user_id, exc)
        return False


def verify_user_mfa_code(user_id: str, code: str) -> bool:
    record = get_user_mfa_record(user_id)
    if not record:
        return False
    secret = str(record.get("secret") or "")
    if secret and verify_totp(secret, code):
        return True
    hashed_codes = list(record.get("recovery_codes") or [])
    code_hash = _hash_recovery_code(code)
    if code_hash not in hashed_codes:
        return False
    hashed_codes.remove(code_hash)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE user_totp_mfa SET recovery_codes = %s::jsonb WHERE user_id = %s",
                    (json.dumps(hashed_codes), user_id),
                )
            conn.commit()
    except Exception as exc:
        logger.warning("[totp_mfa] Failed to consume recovery code for %s: %s", user_id, exc)
    return True
