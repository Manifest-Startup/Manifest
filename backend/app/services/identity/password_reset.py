"""Business logic for the password reset flow.

Keeps the GraphQL resolver thin and centralises rate limiting,
token generation, and DB writes so they can be tested in isolation.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone

from app.db.database import get_database_url, get_db_connection
from app.services.identity.reset_tokens import generate_reset_token, hash_token
from app.utils.logger import logger

RESET_TOKEN_TTL_MINUTES = 30
MIN_PASSWORD_LENGTH = 8

_RATE_LIMIT_WINDOW_SEC = 15 * 60  # 15 minutes
_REQUEST_PER_EMAIL_LIMIT = 5
_REQUEST_PER_IP_LIMIT = 20
_RESET_ATTEMPT_PER_IP_LIMIT = 20

_RATE_LIMIT_TABLE = "password_reset_rate_limit_events"


# ---------------------------------------------------------------------------
# Rate limit backends
#
# The shared (cross-process / cross-host) backend stores one row per
# request in Postgres and counts rows in the sliding window. A per-key
# advisory lock makes the read-then-insert atomic so two app instances
# can't both slip past the limit by racing.
#
# When DATABASE_URL is not configured (unit tests, local dev without a
# DB) we fall back to a per-process in-memory bucket so the limiter is
# still functional. This is the historical behaviour and is what the
# existing test suite exercises.
# ---------------------------------------------------------------------------


_in_memory_buckets: dict[str, list[float]] = {}
_in_memory_lock = threading.Lock()

# When True, _check_bucket skips the shared Postgres backend entirely.
# Flipped on by _reset_buckets_for_test() so unit tests that mock the
# db layer never try to hit a (possibly non-existent) shared table.
_force_in_memory_only = False


def _check_bucket_in_memory(key: str, limit: int, window: int) -> bool:
    now = time.time()
    cutoff = now - window
    with _in_memory_lock:
        bucket = _in_memory_buckets.setdefault(key, [])
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


def _check_bucket_postgres(key: str, limit: int, window: int) -> bool:
    """Sliding-window limiter backed by a shared Postgres table.

    Uses pg_advisory_xact_lock(hashtext(key)) so concurrent workers
    serialise on the same bucket key only — different keys still run
    in parallel. The lock is released automatically at COMMIT.
    """

    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            (key,),
        )
        cur.execute(
            f"""
                DELETE FROM {_RATE_LIMIT_TABLE}
                WHERE bucket_key = %s
                  AND created_at < NOW() - (%s || ' seconds')::interval
                """,
            (key, str(window)),
        )
        cur.execute(
            f"""
                SELECT COUNT(*) AS cnt
                FROM {_RATE_LIMIT_TABLE}
                WHERE bucket_key = %s
                  AND created_at >= NOW() - (%s || ' seconds')::interval
                """,
            (key, str(window)),
        )
        row = cur.fetchone()
        count = int(row["cnt"]) if row else 0
        if count >= limit:
            return False
        cur.execute(
            f"INSERT INTO {_RATE_LIMIT_TABLE} (bucket_key) VALUES (%s)",
            (key,),
        )
        return True


def _check_bucket(key: str, limit: int, window: int = _RATE_LIMIT_WINDOW_SEC) -> bool:
    """Sliding-window rate limit. Returns True if the request is allowed.

    Prefers the shared Postgres backend so the limit is enforced across
    every app instance and survives restarts. Falls back to a
    per-process in-memory bucket only when no database is configured or
    a DB error occurs (so a transient outage degrades to local-only
    enforcement instead of disabling protection entirely).
    """

    if not _force_in_memory_only and get_database_url():
        try:
            return _check_bucket_postgres(key, limit, window)
        except Exception as exc:
            logger.error(
                "[password_reset] Shared rate limit backend failed (%s); "
                "falling back to in-process bucket for key=%s",
                exc,
                key,
            )
    return _check_bucket_in_memory(key, limit, window)


def sweep_stale_rate_limit_rows(window: int = _RATE_LIMIT_WINDOW_SEC) -> int:
    """Delete every row in the rate-limit table older than the window.

    Returns the number of rows deleted, or 0 when the shared backend is
    not available (no DATABASE_URL, in-memory backend forced for tests,
    or a transient DB error).

    Rationale: the limiter only deletes rows lazily — when the same
    bucket key is hit again. Buckets that fire once and never repeat
    (one-off attacker IPs, churned email addresses) leave rows behind
    forever. A periodic sweep keeps the table bounded so the
    sliding-window queries stay fast.
    """

    if _force_in_memory_only or not get_database_url():
        return 0
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                    DELETE FROM {_RATE_LIMIT_TABLE}
                    WHERE created_at < NOW() - (%s || ' seconds')::interval
                    """,
                (str(window),),
            )
            deleted = cur.rowcount or 0
        logger.info(
            "[password_reset] Swept %d stale rate-limit row(s) older than %ds",
            deleted,
            window,
        )
        return int(deleted)
    except Exception as exc:
        logger.warning(
            "[password_reset] Rate-limit sweep failed (will retry next interval): %s",
            exc,
        )
        return 0


def _reset_buckets_for_test() -> None:  # pragma: no cover - test helper
    """Clear all rate limit state and force the in-memory backend.

    Tests stub out ``get_db_connection`` for the password-reset data
    layer with pre-staged rows; routing the rate limiter through the
    same patched cursor would consume those rows. Switching to the
    in-process backend keeps tests hermetic without disabling the
    shared backend in production.
    """
    global _force_in_memory_only
    _force_in_memory_only = True
    with _in_memory_lock:
        _in_memory_buckets.clear()


def check_request_rate_limit(email: str, ip: str | None) -> bool:
    """Return False if either per-email or per-IP request limit is hit."""

    email_ok = _check_bucket(
        f"pwreset:email:{(email or '').lower().strip()}",
        _REQUEST_PER_EMAIL_LIMIT,
    )
    ip_ok = _check_bucket(
        f"pwreset:ip:{(ip or 'unknown').strip() or 'unknown'}",
        _REQUEST_PER_IP_LIMIT,
    )
    return email_ok and ip_ok


def check_reset_attempt_rate_limit(ip: str | None) -> bool:
    """Slow brute-force token guessing on the reset endpoint."""

    return _check_bucket(
        f"pwreset:attempt:ip:{(ip or 'unknown').strip() or 'unknown'}",
        _RESET_ATTEMPT_PER_IP_LIMIT,
    )


_GUEST_UPGRADE_EMAIL_LIMIT = 5
_GUEST_UPGRADE_IP_LIMIT = 25


def check_guest_upgrade_request_rate_limit(email: str, ip: str | None) -> bool:
    """Throttle guest upgrade link requests (per email and per IP)."""

    email_ok = _check_bucket(
        f"gupgrade:email:{(email or '').lower().strip()}",
        _GUEST_UPGRADE_EMAIL_LIMIT,
    )
    ip_ok = _check_bucket(
        f"gupgrade:ip:{(ip or 'unknown').strip() or 'unknown'}",
        _GUEST_UPGRADE_IP_LIMIT,
    )
    return email_ok and ip_ok


def check_guest_upgrade_attempt_rate_limit(ip: str | None) -> bool:
    """Slow token guessing on complete-guest-upgrade."""

    return _check_bucket(
        f"gupgrade:attempt:ip:{(ip or 'unknown').strip() or 'unknown'}",
        _RESET_ATTEMPT_PER_IP_LIMIT,
    )


def validate_password_strength(password: str) -> str | None:
    """Return an error string if invalid, else None.

    Composition + length only. Breach and history checks are layered on top
    by ``validate_password_for_user`` so the cheap checks fail fast.
    """

    if password is None:
        return "Password is required."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > 256:
        return "Password is too long."
    classes = sum(
        bool(any(check(c) for c in password))
        for check in (str.isupper, str.islower, str.isdigit, lambda c: not c.isalnum())
    )
    if classes < 3:
        return (
            "Password must contain at least three of: uppercase, lowercase, "
            "digit, and symbol characters."
        )
    return None


def validate_password_for_user(password: str, user_id: str | None) -> str | None:
    """Composition + HIBP breach + recent-history reuse checks combined.

    Used by both signup and password-reset flows so policy is enforced
    identically. Breach check is fail-open on HIBP outage.
    """
    base = validate_password_strength(password)
    if base:
        return base

    try:
        from app.security.breached_passwords import is_password_breached

        if is_password_breached(password):
            return (
                "This password has appeared in known data breaches. "
                "Please choose a different one."
            )
    except Exception as exc:
        logger.debug("[password_reset] HIBP check failed: %s", exc)

    if user_id:
        try:
            from app.security.password_history import is_recent_reuse

            if is_recent_reuse(user_id, password):
                return "This password matches one of your recent passwords. Please pick a new one."
        except Exception as exc:
            logger.debug("[password_reset] history check failed: %s", exc)

    return None


def find_resettable_user(email: str) -> dict[str, object] | None:
    """Look up a user eligible for password reset.

    Returns ``None`` for: unknown email, OAuth-only accounts (no
    ``password_hash``), and guest accounts.
    """

    normalised = (email or "").lower().strip()
    if not normalised:
        return None

    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
                SELECT user_id, email, password_hash,
                       COALESCE(is_guest, FALSE) AS is_guest
                FROM users
                WHERE email = %s
                """,
            (normalised,),
        )
        row = cur.fetchone()

    if not row:
        return None
    if row.get("is_guest"):
        return None
    if not row.get("password_hash"):
        return None
    return row


def create_reset_token_for_user(user_id: str, request_ip: str | None) -> str:
    """Invalidate any outstanding tokens, insert a fresh one, return raw token."""

    raw_token, token_hash = generate_reset_token()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)

    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
                UPDATE password_reset_tokens
                SET used_at = NOW()
                WHERE user_id = %s AND used_at IS NULL
                """,
            (user_id,),
        )
        cur.execute(
            """
                INSERT INTO password_reset_tokens
                    (user_id, token_hash, expires_at, request_ip)
                VALUES (%s, %s, %s, %s)
                """,
            (user_id, token_hash, expires_at, (request_ip or None)),
        )

    return raw_token


def build_reset_url(raw_token: str, request_base_url: str | None = None) -> str:
    """Compose the public link the user clicks in their email.

    The URL host is taken **only** from the ``APP_BASE_URL`` environment
    variable. The ``request_base_url`` argument is intentionally
    ignored: trusting the inbound request's Host / X-Forwarded-Host
    header would let an attacker poison the emailed link with their own
    domain (full account takeover via the captured token). If
    ``APP_BASE_URL`` is unset we fall back to localhost, which is safe
    in development and effectively unusable in production.
    """

    _ = request_base_url  # kept for backwards compatibility, deliberately unused
    base = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    if not base:
        logger.warning(
            "[password_reset] APP_BASE_URL not set; reset link will use localhost. "
            "Set APP_BASE_URL to your public URL to deliver real reset emails."
        )
        base = "http://localhost:5000"
    return f"{base}/auth/reset-password?token={raw_token}"


def consume_token_and_reset_password(
    raw_token: str, new_password_hash: str
) -> dict[str, object] | None:
    """Atomically validate the token, mark it used, update the user's password,
    bump ``password_changed_at``, and invalidate any other outstanding tokens.

    Returns the updated user row, or ``None`` if the token is invalid,
    expired, already used, or the user disappeared. The whole flow runs
    in a single DB transaction so a failure during password update will
    not consume the token.
    """

    if not raw_token:
        return None

    digest = hash_token(raw_token)

    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
                SELECT token_id, user_id, expires_at, used_at
                FROM password_reset_tokens
                WHERE token_hash = %s
                FOR UPDATE
                """,
            (digest,),
        )
        token_row = cur.fetchone()
        if not token_row:
            return None
        if token_row.get("used_at") is not None:
            return None
        expires_at = token_row.get("expires_at")
        if expires_at is None or expires_at < datetime.now(timezone.utc):
            return None

        user_id = token_row["user_id"]

        cur.execute(
            """
                UPDATE users
                SET password_hash = %s,
                    password_changed_at = NOW()
                WHERE user_id = %s
                RETURNING user_id, email,
                          EXTRACT(EPOCH FROM password_changed_at)::BIGINT AS pwd_iat
                """,
            (new_password_hash, user_id),
        )
        user_row = cur.fetchone()
        if not user_row:
            # Will roll back when the context manager exits with an exception.
            raise RuntimeError(f"password_reset: token referenced unknown user_id={user_id}")

        cur.execute(
            """
                UPDATE password_reset_tokens
                SET used_at = NOW()
                WHERE user_id = %s AND used_at IS NULL
                """,
            (user_id,),
        )

    # Persist the new hash in password_history so future reset attempts
    # cannot reuse it (best-effort, non-fatal).
    try:
        from app.security.password_history import record_password

        record_password(str(user_id), new_password_hash)
    except Exception as exc:
        logger.debug("[password_reset] history record failed: %s", exc)

    # Invalidate every active session for this user so a stolen cookie
    # acquired before the reset cannot continue acting as the account.
    # ``pwd_iat`` already invalidates JWTs but explicit revocation is
    # what auditors and the SOC 2 control story actually want to see.
    try:
        from app.services.identity.sessions import revoke_all_sessions

        revoke_all_sessions(str(user_id))
    except Exception as exc:
        logger.debug("[password_reset] session revocation failed: %s", exc)

    # Clear any account-lockout for the email so the user can immediately log in.
    try:
        from app.db.database import get_db_connection as _gdc
        from app.security.account_lockout import admin_clear_lockout

        with _gdc() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT email FROM users WHERE user_id = %s",
                (user_id,),
            )
            u_row = cur.fetchone()
        if u_row and u_row.get("email"):
            admin_clear_lockout(email=str(u_row["email"]))
    except Exception as exc:
        logger.debug("[password_reset] lockout clear failed: %s", exc)

    logger.info("[password_reset] Password updated for user_id=%s", user_id)
    return user_row


def get_password_changed_at_epoch(user_id: str) -> int | None:
    """Return ``password_changed_at`` for a user as an epoch second, or None."""

    if not user_id:
        return None
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT EXTRACT(EPOCH FROM password_changed_at)::BIGINT AS pwd_iat
                    FROM users WHERE user_id = %s
                    """,
                (user_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return row.get("pwd_iat")
    except Exception as exc:  # pragma: no cover - column may not exist before migration
        logger.debug("[password_reset] pwd_iat lookup failed for %s: %s", user_id, exc)
        return None
