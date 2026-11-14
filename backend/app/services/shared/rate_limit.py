import hashlib
from datetime import datetime, timedelta, timezone

from app.db.database import get_db_connection
from app.utils.logger import logger


def _hash_bucket(bucket_key: str) -> str:
    return hashlib.sha256(bucket_key.encode("utf-8")).hexdigest()


class RateLimitService:
    def allow(self, bucket_key: str, *, limit: int, window_seconds: int) -> bool:
        if limit <= 0:
            return False
        bucket_hash = _hash_bucket(bucket_key)
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=window_seconds)
        expires_at = now + timedelta(seconds=window_seconds)
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM rate_limit_events WHERE expires_at < NOW()")
                    cur.execute(
                        """
                        SELECT COUNT(*) AS hit_count
                        FROM rate_limit_events
                        WHERE bucket_hash = %s AND created_at >= %s
                        """,
                        (bucket_hash, window_start),
                    )
                    row = cur.fetchone() or {}
                    hit_count = int(row.get("hit_count") or 0)
                    if hit_count >= limit:
                        conn.commit()
                        return False
                    cur.execute(
                        """
                        INSERT INTO rate_limit_events (bucket_hash, bucket_key_hint, created_at, expires_at)
                        VALUES (%s, %s, NOW(), %s)
                        """,
                        (bucket_hash, bucket_key[:120], expires_at),
                    )
                conn.commit()
            return True
        except Exception as exc:
            logger.warning("[rate_limit] Falling back to allow for %s: %s", bucket_key, exc)
            return True


rate_limit_service = RateLimitService()
