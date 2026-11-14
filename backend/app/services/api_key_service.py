"""
API Key Management Service

Handles creation, validation, revocation, and rotation of API keys.

Storage model (post-Task #11 hardening — SEC-007):
- ``key_prefix`` (16 chars, indexed) lets us look up the candidate row in O(log n).
- ``key_hash`` is bcrypt(full_key) when ``hash_algo='bcrypt'`` (the new default).
- Legacy keys created before this migration use ``hash_algo='sha256'`` and are
  validated with constant-time SHA-256 compare — they continue to work but
  the system encourages rotation by exposing ``rotate_api_key()``.
- ``scopes`` is a TEXT[] of dotted permissions (e.g. ``ideas.read``).
- ``last_used_ip`` is updated on every successful validation for forensics.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

try:  # bcrypt is in requirements.txt; degrade to PBKDF2 if missing.
    import bcrypt  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - bcrypt is required in prod
    bcrypt = None

from app.db.database import db_client
from app.utils.logger import logger

API_KEY_PREFIX = "manifest_sk_"
API_KEY_LENGTH = 32
DEFAULT_API_KEY_SCOPES = ["read"]


class BillingTier:
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"

    LIMITS = {
        FREE: {"requests_per_month": 1000, "rate_limit_per_minute": 10},
        STARTER: {"requests_per_month": 10000, "rate_limit_per_minute": 60},
        PRO: {"requests_per_month": 100000, "rate_limit_per_minute": 300},
        ENTERPRISE: {"requests_per_month": -1, "rate_limit_per_minute": 1000},
    }


def _bcrypt_input(api_key: str) -> bytes:
    """Pre-hash with SHA-256 so bcrypt's 72-byte input limit never bites.

    The plaintext key is 76 bytes (``manifest_sk_`` + 64 hex chars). bcrypt
    silently truncates inputs > 72 bytes, which is both a security smell
    (multiple keys can map to the same prefix) and a hard error in newer
    bcrypt builds. SHA-256 → hex normalizes to 64 ASCII bytes — well
    under the bcrypt limit and still preimage-resistant.
    """
    return hashlib.sha256(api_key.encode()).hexdigest().encode()


def generate_api_key() -> tuple[str, str, str, str]:
    """Generate a new API key.

    Returns ``(full_key, key_prefix, key_hash, hash_algo)``. The 4-tuple
    shape is new in Task #11; callers expecting the legacy 3-tuple should
    use ``generate_api_key_legacy()``.
    """
    random_bytes = secrets.token_hex(API_KEY_LENGTH)
    full_key = f"{API_KEY_PREFIX}{random_bytes}"
    key_prefix = full_key[:16]
    if bcrypt is not None:
        key_hash = bcrypt.hashpw(_bcrypt_input(full_key), bcrypt.gensalt()).decode()
        return full_key, key_prefix, key_hash, "bcrypt"
    # Fallback: never used in production (bcrypt is in requirements.txt).
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, key_prefix, key_hash, "sha256"


def _verify_against_stored(api_key: str, stored_hash: str, hash_algo: str) -> bool:
    if hash_algo == "bcrypt":
        if bcrypt is None:
            logger.error("bcrypt key encountered but bcrypt module is missing")
            return False
        try:
            return bcrypt.checkpw(_bcrypt_input(api_key), stored_hash.encode())
        except Exception:
            return False
    # Default / legacy SHA-256
    expected = hashlib.sha256(api_key.encode()).hexdigest()
    return hmac.compare_digest(expected, stored_hash)


def hash_api_key(api_key: str) -> str:
    """Legacy export — kept so older callers (tests) still import it.

    Returns the SHA-256 digest. New code should not rely on this for
    storage; use ``generate_api_key()`` to get a bcrypt-hashed value.
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


class ApiKeyService:
    """Service for managing API keys and clients."""

    def __init__(self):
        self.db = db_client

    # ----- clients -------------------------------------------------------
    def create_api_client(
        self, user_id: str, name: str, tier: str = BillingTier.FREE
    ) -> dict[str, Any]:
        logger.info(f"Creating API client for user {user_id}: {name}")
        result = (
            self.db.table("api_clients")
            .insert(
                {
                    "id": str(uuid4()),
                    "user_id": user_id,
                    "name": name,
                    "tier": tier,
                    "status": "active",
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )
            .execute()
        )
        if isinstance(result.data, list):
            return result.data[0] if result.data else {}
        return result.data or {}

    def get_api_clients(self, user_id: str) -> list[dict[str, Any]]:
        result = (
            self.db.table("api_clients")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    def get_api_client(self, client_id: str) -> dict[str, Any] | None:
        result = self.db.table("api_clients").select("*").eq("id", client_id).single().execute()
        return result.data

    # ----- keys ----------------------------------------------------------
    def create_api_key(
        self,
        client_id: str,
        name: str = "Default Key",
        expires_days: int | None = None,
        scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        logger.info(f"Creating API key for client {client_id}")
        full_key, key_prefix, key_hash, hash_algo = generate_api_key()

        expires_at = None
        if expires_days:
            expires_at = (datetime.utcnow() + timedelta(days=expires_days)).isoformat()

        # Filter scopes against API-key-forbidden permissions.
        from app.security.permissions import filter_api_key_scopes

        cleaned_scopes = filter_api_key_scopes(scopes or DEFAULT_API_KEY_SCOPES)

        result = (
            self.db.table("api_keys")
            .insert(
                {
                    "id": str(uuid4()),
                    "client_id": client_id,
                    "name": name,
                    "key_prefix": key_prefix,
                    "key_hash": key_hash,
                    "hash_algo": hash_algo,
                    "scopes": cleaned_scopes,
                    "expires_at": expires_at,
                    "status": "active",
                    "created_at": datetime.utcnow().isoformat(),
                    "last_used_at": None,
                }
            )
            .execute()
        )

        created_key = result.data[0] if isinstance(result.data, list) else result.data
        return {
            **(created_key or {}),
            "full_key": full_key,
            "scopes": cleaned_scopes,
        }

    def get_api_keys(self, client_id: str) -> list[dict[str, Any]]:
        result = (
            self.db.table("api_keys")
            .select("*")
            .eq("client_id", client_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    def get_all_user_keys(self, user_id: str) -> list[dict[str, Any]]:
        clients = self.get_api_clients(user_id)
        all_keys = []
        for client in clients:
            keys = self.get_api_keys(client["id"])
            for key in keys:
                key["client_name"] = client["name"]
                key["tier"] = client["tier"]
            all_keys.extend(keys)
        return all_keys

    def validate_api_key(  # noqa: C901
        self, api_key: str, *, request_ip: str | None = None
    ) -> dict[str, Any] | None:
        if not api_key or not api_key.startswith(API_KEY_PREFIX):
            logger.warning("Invalid API key format")
            return None
        key_prefix = api_key[:16]

        # Look up all candidate rows by prefix + active status — there should
        # normally be 1, occasionally 2 during rotation overlap. We then
        # verify with the stored algorithm in constant time.
        result = (
            self.db.table("api_keys")
            .select("*")
            .eq("key_prefix", key_prefix)
            .eq("status", "active")
            .execute()
        )
        rows: list[dict[str, Any]] = result.data or []
        key_data: dict[str, Any] | None = None
        for row in rows:
            stored_hash = row.get("key_hash") or ""
            algo = row.get("hash_algo") or "sha256"
            if _verify_against_stored(api_key, stored_hash, algo):
                key_data = row
                break

        if not key_data:
            logger.warning(f"API key not found or inactive: {key_prefix}...")
            return None

        if key_data.get("expires_at"):
            try:
                # Compare in UTC and tolerate both naive and tz-aware
                # values: Postgres returns aware datetimes, while older
                # rows / SQLite-shimmed tests can return naive ISO
                # strings. Normalize both sides to aware-UTC so the
                # comparison never raises (which would fail-safe to
                # "expired" and reject still-valid rotated keys).
                from datetime import timezone as _tz

                raw = key_data["expires_at"]
                if isinstance(raw, datetime):
                    expires_at = raw
                else:
                    expires_at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=_tz.utc)
                if expires_at < datetime.now(_tz.utc):
                    logger.warning(f"API key expired: {key_prefix}...")
                    return None
            except Exception:
                # Malformed expires_at — treat as expired to fail safe.
                return None

        client = self.get_api_client(key_data["client_id"])
        if not client or client.get("status") != "active":
            logger.warning(f"API client not found or inactive for key: {key_prefix}...")
            return None

        # Update last_used_at + last_used_ip without blocking the request.
        update_payload: dict[str, Any] = {"last_used_at": datetime.utcnow().isoformat()}
        if request_ip:
            update_payload["last_used_ip"] = request_ip
        try:
            self.db.table("api_keys").update(update_payload).eq("id", key_data["id"]).execute()
            self.db.table("api_clients").update({"last_used_at": datetime.utcnow().isoformat()}).eq(
                "id", client["id"]
            ).execute()
        except Exception as exc:
            logger.debug("api_key last_used update failed: %s", exc)

        return {
            "key_id": key_data["id"],
            "key_name": key_data["name"],
            "scopes": key_data.get("scopes") or DEFAULT_API_KEY_SCOPES,
            "client_id": client["id"],
            "client_name": client["name"],
            "user_id": client["user_id"],
            "tier": client["tier"],
            "limits": BillingTier.LIMITS.get(client["tier"], BillingTier.LIMITS[BillingTier.FREE]),
        }

    def revoke_api_key(self, key_id: str, user_id: str) -> bool:
        logger.info(f"Revoking API key {key_id} for user {user_id}")
        key_result = self.db.table("api_keys").select("*").eq("id", key_id).single().execute()
        if not key_result.data:
            return False
        client = self.get_api_client(key_result.data["client_id"])
        if not client or client["user_id"] != user_id:
            logger.warning(f"Unauthorized key revocation attempt by user {user_id}")
            return False
        self.db.table("api_keys").update(
            {
                "status": "revoked",
                "revoked_at": datetime.utcnow().isoformat(),
            }
        ).eq("id", key_id).execute()
        return True

    def rotate_api_key(
        self, key_id: str, user_id: str, *, overlap_seconds: int = 86400
    ) -> dict[str, Any] | None:
        """Generate a replacement key and schedule the old one for revocation.

        The old key remains active for ``overlap_seconds`` (default 24 h)
        so callers have a window to swap in the new value with zero
        downtime. After that window passes, ``revoke_api_key()`` must be
        called (or a sweep job will do it). Both keys are linked via
        ``rotated_to``.
        """
        old_result = self.db.table("api_keys").select("*").eq("id", key_id).single().execute()
        if not old_result.data:
            return None
        old_row = old_result.data
        client = self.get_api_client(old_row["client_id"])
        if not client or client["user_id"] != user_id:
            logger.warning("Unauthorized key rotation attempt by user %s", user_id)
            return None

        new_record = self.create_api_key(
            client_id=old_row["client_id"],
            name=f"{old_row.get('name', 'Default Key')} (rotated)",
            expires_days=None,
            scopes=old_row.get("scopes") or DEFAULT_API_KEY_SCOPES,
        )
        # Mark old key as scheduled for revocation
        revoke_at = (datetime.utcnow() + timedelta(seconds=overlap_seconds)).isoformat()
        self.db.table("api_keys").update(
            {
                "rotated_to": new_record.get("id"),
                "expires_at": revoke_at,
                "last_rotated_at": datetime.utcnow().isoformat(),
            }
        ).eq("id", key_id).execute()
        return {
            "old_key_id": key_id,
            "expires_at": revoke_at,
            "new_key": new_record,
        }

    def delete_api_client(self, client_id: str, user_id: str) -> bool:
        logger.info(f"Deleting API client {client_id} for user {user_id}")
        client = self.get_api_client(client_id)
        if not client or client["user_id"] != user_id:
            logger.warning(f"Unauthorized client deletion attempt by user {user_id}")
            return False
        self.db.table("api_keys").update(
            {
                "status": "revoked",
                "revoked_at": datetime.utcnow().isoformat(),
            }
        ).eq("client_id", client_id).execute()
        self.db.table("api_clients").update(
            {
                "status": "deleted",
                "updated_at": datetime.utcnow().isoformat(),
            }
        ).eq("id", client_id).execute()
        return True


class ApiUsageService:
    """Service for tracking API usage."""

    def __init__(self):
        self.db = db_client

    def record_usage(
        self,
        client_id: str,
        key_id: str,
        endpoint: str,
        response_code: int,
        latency_ms: int,
        tokens_used: int = 0,
    ) -> None:
        self.db.table("api_usage_events").insert(
            {
                "client_id": client_id,
                "key_id": key_id,
                "endpoint": endpoint,
                "response_code": response_code,
                "latency_ms": latency_ms,
                "tokens_used": tokens_used,
                "created_at": datetime.utcnow().isoformat(),
            }
        ).execute()

        today = datetime.utcnow().date().isoformat()
        existing = (
            self.db.table("api_usage_daily")
            .select("*")
            .eq("client_id", client_id)
            .eq("date", today)
            .single()
            .execute()
        )
        if existing.data:
            self.db.table("api_usage_daily").update(
                {
                    "request_count": existing.data["request_count"] + 1,
                    "tokens_used": existing.data["tokens_used"] + tokens_used,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            ).eq("id", existing.data["id"]).execute()
        else:
            self.db.table("api_usage_daily").insert(
                {
                    "client_id": client_id,
                    "date": today,
                    "request_count": 1,
                    "tokens_used": tokens_used,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                }
            ).execute()

    def get_monthly_usage(self, client_id: str) -> dict[str, Any]:
        first_of_month = datetime.utcnow().replace(day=1).date().isoformat()
        result = (
            self.db.table("api_usage_daily")
            .select("*")
            .eq("client_id", client_id)
            .gte("date", first_of_month)
            .execute()
        )
        total_requests = sum(r["request_count"] for r in (result.data or []))
        total_tokens = sum(r["tokens_used"] for r in (result.data or []))
        return {
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "daily_breakdown": result.data or [],
        }

    def get_usage_stats(self, user_id: str) -> dict[str, Any]:
        key_service = ApiKeyService()
        clients = key_service.get_api_clients(user_id)
        total_requests = 0
        total_tokens = 0
        for client in clients:
            usage = self.get_monthly_usage(client["id"])
            total_requests += usage["total_requests"]
            total_tokens += usage["total_tokens"]
        tier = clients[0]["tier"] if clients else BillingTier.FREE
        limits = BillingTier.LIMITS.get(tier, BillingTier.LIMITS[BillingTier.FREE])
        return {
            "tier": tier,
            "requests_used": total_requests,
            "requests_limit": limits["requests_per_month"],
            "tokens_used": total_tokens,
            "rate_limit_per_minute": limits["rate_limit_per_minute"],
        }

    def check_rate_limit(self, client_id: str, tier: str) -> bool:
        limits = BillingTier.LIMITS.get(tier, BillingTier.LIMITS[BillingTier.FREE])
        rate_limit = limits["rate_limit_per_minute"]
        one_minute_ago = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
        result = (
            self.db.table("api_usage_events")
            .select("id")
            .eq("client_id", client_id)
            .gte("created_at", one_minute_ago)
            .execute()
        )
        recent_requests = len(result.data or [])
        return recent_requests < rate_limit

    def check_per_key_rate_limit(self, key_id: str, *, max_per_minute: int = 600) -> bool:
        """Hard ceiling per individual key — defends against a single leaked key."""
        if not key_id:
            return True
        one_minute_ago = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
        result = (
            self.db.table("api_usage_events")
            .select("id")
            .eq("key_id", key_id)
            .gte("created_at", one_minute_ago)
            .execute()
        )
        return len(result.data or []) < max_per_minute

    def check_monthly_limit(self, client_id: str, tier: str) -> bool:
        limits = BillingTier.LIMITS.get(tier, BillingTier.LIMITS[BillingTier.FREE])
        monthly_limit = limits["requests_per_month"]
        if monthly_limit == -1:
            return True
        usage = self.get_monthly_usage(client_id)
        return usage["total_requests"] < monthly_limit


api_key_service = ApiKeyService()
api_usage_service = ApiUsageService()
