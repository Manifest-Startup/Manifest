import base64
import hashlib
import hmac
import os

try:
    import bcrypt  # type: ignore
except ModuleNotFoundError:
    bcrypt = None


PBKDF2_PREFIX = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 390000


def hash_password(password: str) -> str:
    """Hash password with bcrypt when available, fallback to PBKDF2-SHA256."""
    if bcrypt is not None:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    salt_b64 = base64.b64encode(salt).decode()
    digest_b64 = base64.b64encode(digest).decode()
    return f"{PBKDF2_PREFIX}${PBKDF2_ITERATIONS}${salt_b64}${digest_b64}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify bcrypt hashes and PBKDF2 fallback hashes."""
    if password_hash.startswith(f"{PBKDF2_PREFIX}$"):
        try:
            _, iter_str, salt_b64, digest_b64 = password_hash.split("$", 3)
            iterations = int(iter_str)
            salt = base64.b64decode(salt_b64.encode())
            expected_digest = base64.b64decode(digest_b64.encode())
            actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
            return hmac.compare_digest(actual_digest, expected_digest)
        except Exception:
            return False

    if bcrypt is None:
        return False

    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False
