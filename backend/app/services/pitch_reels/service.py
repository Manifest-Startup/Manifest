"""
Pitch Reel Service
Handles the immersive pitch reels feed and its social interactions.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from typing import Any

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover - exercised only in lean environments
    BeautifulSoup = None  # type: ignore[assignment]

from app.db.database import DatabaseClient
from app.services.social.graph import create_social_graph_service
from app.utils.logger import logger

USER_REEL_PLACEHOLDER_VIDEO = "/videos/tutorial.mov"
USER_REEL_FEATURED_RANK = 175
# Only the three fixtures from 20260326000000_add_pitch_reels_social.sql.
DEMO_REEL_IDS = tuple(f"00000000-0000-0000-0000-00000000b20{i}" for i in range(1, 4))


def _html_to_plain_text(value: str | None) -> str:
    """Strip HTML from rich-text fields (e.g. TipTap idea descriptions) for pitch reel copy."""
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    if "<" not in raw and ">" not in raw:
        return raw
    if BeautifulSoup is not None:
        text = BeautifulSoup(raw, "html.parser").get_text(separator=" ")
    else:
        text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", text).strip()


def _feed_preview(value: str | None) -> str:
    text = _html_to_plain_text(value)
    return text if len(text) <= 640 else text[:640].rstrip() + "…"


def _display_name(record: dict[str, Any] | None, default: str = "User") -> str:
    if not record:
        return default

    first_name = str(record.get("first_name") or "").strip()
    last_name = str(record.get("last_name") or "").strip()
    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        return full_name

    username = str(record.get("username") or "").strip()
    if username:
        return username

    email = str(record.get("email") or "").strip()
    if email:
        return email.split("@", 1)[0]

    return default


def _make_initials(record: dict[str, Any] | None, fallback: str = "M") -> str:
    name = _display_name(record, fallback).strip()
    parts = [part[0].upper() for part in name.split() if part]
    if len(parts) >= 2:
        return "".join(parts[:2])
    if parts:
        return parts[0]
    return fallback[:2].upper()


def _normalize_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
        return [part.strip() for part in stripped.split(",") if part.strip()]

    return []


class PitchReelService:
    def __init__(self, db):
        self.db = db
        self.reels_table = "pitch_reels"
        self.likes_table = "pitch_reel_likes"
        self.saves_table = "pitch_reel_saves"
        self.shares_table = "pitch_reel_share_events"
        self.comments_table = "pitch_reel_comments"
        self.users_table = "users"
        self.social_graph_service = create_social_graph_service(db)

    _FEED_COLUMNS = (
        "reel_id,slug,creator_user_id,idea_id,title,subtitle,thesis,description,"
        "creator_role,tags,video_url,video_status,video_generation_error,"
        "workspace_path,accent_from,accent_to,featured_rank,"
        "baseline_like_count,baseline_comment_count,baseline_save_count,"
        "baseline_share_count,is_published,created_at,updated_at"
    )

    def _fetch_reel_ids_with_video_data(self, reel_ids: list[str]) -> set:
        """Return the subset of reel_ids that have non-null video_data stored in the DB."""
        import os

        try:
            import psycopg2
        except ImportError:
            return set()

        dsn = os.getenv("DATABASE_URL")
        if not dsn or not reel_ids:
            return set()

        try:
            conn = psycopg2.connect(dsn)
            try:
                with conn.cursor() as cur:
                    placeholders = ",".join(["%s"] * len(reel_ids))
                    cur.execute(
                        f"SELECT reel_id FROM pitch_reels WHERE reel_id IN ({placeholders}) AND video_data IS NOT NULL",
                        reel_ids,
                    )
                    return {str(row[0]) for row in cur.fetchall()}
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("[PitchReelService] Could not batch-check video_data: %s", exc)
            return set()

    def _list_feed_postgres(self, viewer_id: str, limit: int) -> list[dict[str, Any]]:
        """One pooled query; aggregate in SQL and never transfer video bytes."""
        columns = ",".join(
            (
                f"LEFT(r.{column}, 641) AS {column}"
                if column in {"subtitle", "thesis", "description"}
                else f"r.{column}"
            )
            for column in self._FEED_COLUMNS.split(",")
        )
        response = self.db.execute_raw(
            f"""
            WITH feed AS (
                SELECT {columns}, r.video_data IS NOT NULL AS has_video_data,
                    (r.video_data IS NOT NULL OR (
                        COALESCE(r.video_status, 'ready') = 'ready'
                        AND r.video_url <> ''
                        AND r.video_url NOT IN ('/videos/tutorial.mov', '/videos/founders-video.mov')
                    )) AS has_playable_video
                FROM pitch_reels r
                WHERE r.is_published = TRUE AND r.reel_id NOT IN (%s, %s, %s)
                ORDER BY has_playable_video DESC, r.featured_rank DESC, r.created_at DESC, r.reel_id
                LIMIT %s
            )
            SELECT f.*,
                json_build_object(
                    'user_id', u.user_id, 'username', u.username,
                    'first_name', u.first_name, 'last_name', u.last_name,
                    'profile_picture_url', u.profile_picture_url
                ) AS creator_record,
                (SELECT count(*) FROM pitch_reel_likes l WHERE l.reel_id = f.reel_id) AS likes,
                (SELECT count(*) FROM pitch_reel_saves s WHERE s.reel_id = f.reel_id) AS saves,
                (SELECT count(*) FROM pitch_reel_share_events s WHERE s.reel_id = f.reel_id) AS shares,
                (SELECT count(*) FROM pitch_reel_comments c WHERE c.reel_id = f.reel_id) AS comments,
                EXISTS(SELECT 1 FROM pitch_reel_likes l WHERE l.reel_id = f.reel_id AND l.user_id = %s) AS liked,
                EXISTS(SELECT 1 FROM pitch_reel_saves s WHERE s.reel_id = f.reel_id AND s.user_id = %s) AS saved,
                (SELECT count(*) FROM user_follows uf WHERE uf.followed_id = f.creator_user_id) AS followers,
                EXISTS(SELECT 1 FROM user_follows uf WHERE uf.followed_id = f.creator_user_id AND uf.follower_id = %s) AS following
            FROM feed f LEFT JOIN users u ON u.user_id = f.creator_user_id
            ORDER BY f.has_playable_video DESC, f.featured_rank DESC, f.created_at DESC, f.reel_id
            """,
            (*DEMO_REEL_IDS, limit, viewer_id, viewer_id, viewer_id),
        )
        payloads = []
        for row in response.data or []:
            rid = str(row["reel_id"])
            uid = str(row["creator_user_id"])
            payloads.append(
                self._build_reel_payload_batch(
                    row,
                    viewer_id,
                    {rid} if row["has_video_data"] else set(),
                    {rid: row["likes"]},
                    {rid: row["saves"]},
                    {rid: row["shares"]},
                    {rid: row["comments"]},
                    {rid} if row["liked"] else set(),
                    {rid} if row["saved"] else set(),
                    {uid: row["creator_record"]},
                    {uid} if row["following"] else set(),
                    {uid: row["followers"]},
                )
            )
        return payloads

    async def list_feed(self, viewer_id: str, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 50))
        if isinstance(self.db, DatabaseClient):
            # Keep synchronous Postgres I/O off the server's event loop.
            return await asyncio.to_thread(self._list_feed_postgres, viewer_id, limit)

        query = self.db.table(self.reels_table).select(self._FEED_COLUMNS).eq("is_published", True)
        for demo_id in DEMO_REEL_IDS:
            query = query.neq("reel_id", demo_id)
        response = query.order("created_at", desc=True).limit(limit).execute()

        reels = response.data or []
        if not reels:
            return []

        reel_ids = [str(reel.get("reel_id") or "") for reel in reels if reel.get("reel_id")]
        creator_ids = list(
            {
                str(reel.get("creator_user_id") or "")
                for reel in reels
                if reel.get("creator_user_id")
            }
        )

        # --- Batch all DB lookups upfront (replaces N+1 per-reel queries) ---
        reels_with_video_data = self._fetch_reel_ids_with_video_data(reel_ids)
        like_counts = self._batch_count_by_reel(self.likes_table, reel_ids)
        save_counts = self._batch_count_by_reel(self.saves_table, reel_ids)
        share_counts = self._batch_count_by_reel(self.shares_table, reel_ids)
        comment_counts = self._batch_count_by_reel(self.comments_table, reel_ids)
        liked_set = self._batch_user_relation_set(self.likes_table, reel_ids, viewer_id)
        saved_set = self._batch_user_relation_set(self.saves_table, reel_ids, viewer_id)
        users_map = self._batch_get_users(creator_ids)

        follower_counts = await self.social_graph_service.get_follower_counts(creator_ids)
        following_set = await self.social_graph_service.get_following_set(viewer_id, creator_ids)

        return [
            self._build_reel_payload_batch(
                reel,
                viewer_id,
                reels_with_video_data,
                like_counts,
                save_counts,
                share_counts,
                comment_counts,
                liked_set,
                saved_set,
                users_map,
                following_set,
                follower_counts,
            )
            for reel in reels
        ]

    def _build_reel_payload_batch(
        self,
        reel: dict[str, Any],
        viewer_id: str,
        reels_with_video_data: set,
        like_counts: dict[str, int],
        save_counts: dict[str, int],
        share_counts: dict[str, int],
        comment_counts: dict[str, int],
        liked_set: set,
        saved_set: set,
        users_map: dict[str, dict[str, Any]],
        following_set: set,
        follower_counts: dict[str, int],
    ) -> dict[str, Any]:
        """Build a reel payload using pre-fetched batch data (no per-reel DB queries)."""
        reel_id = str(reel.get("reel_id") or "")
        creator_user_id = str(reel.get("creator_user_id") or "")
        creator = users_map.get(creator_user_id) or {}

        like_count = self._baseline_int(reel, "baseline_like_count") + like_counts.get(reel_id, 0)
        save_count = self._baseline_int(reel, "baseline_save_count") + save_counts.get(reel_id, 0)
        share_count = self._baseline_int(reel, "baseline_share_count") + share_counts.get(
            reel_id, 0
        )
        comment_count = self._baseline_int(reel, "baseline_comment_count") + comment_counts.get(
            reel_id, 0
        )

        has_video_data = reel_id in reels_with_video_data
        stored_video_url = str(reel.get("video_url") or "")
        effective_video_url = self._effective_video_url(
            reel_id=reel_id,
            stored_video_url=stored_video_url,
            has_video_data=has_video_data,
        )

        payload = self._reel_payload(
            reel,
            creator,
            video_url=effective_video_url,
            preview=True,
            follower_count=follower_counts.get(creator_user_id, 0),
            is_following=creator_user_id in following_set,
            stats=(like_count, comment_count, save_count, share_count),
            liked=reel_id in liked_set,
            saved=reel_id in saved_set,
        )
        payload["idea_id"] = str(reel.get("idea_id") or "")
        return payload

    async def list_comments(
        self, reel_id: str, viewer_id: str, limit: int = 120
    ) -> list[dict[str, Any]]:
        self._get_reel_or_raise(reel_id)

        response = (
            self.db.table(self.comments_table)
            .select("*")
            .eq("reel_id", reel_id)
            .order("created_at")
            .limit(limit)
            .execute()
        )
        comments = response.data or []
        return [self._build_comment_payload(comment, viewer_id) for comment in comments]

    async def toggle_like(self, reel_id: str, user_id: str) -> dict[str, Any]:
        reel = self._get_reel_or_raise(reel_id)
        liked = self._toggle_user_relation(self.likes_table, "like_id", reel_id, user_id)

        return {
            "reel_id": reel_id,
            "liked": liked,
            "like_count": self._baseline_int(reel, "baseline_like_count")
            + self._count_rows(self.likes_table, reel_id),
        }

    async def toggle_save(self, reel_id: str, user_id: str) -> dict[str, Any]:
        reel = self._get_reel_or_raise(reel_id)
        saved = self._toggle_user_relation(self.saves_table, "save_id", reel_id, user_id)

        return {
            "reel_id": reel_id,
            "saved": saved,
            "save_count": self._baseline_int(reel, "baseline_save_count")
            + self._count_rows(self.saves_table, reel_id),
        }

    async def record_share(self, reel_id: str, user_id: str) -> dict[str, Any]:
        reel = self._get_reel_or_raise(reel_id)

        now = datetime.utcnow().isoformat()
        self.db.table(self.shares_table).insert(
            {
                "share_id": str(uuid.uuid4()),
                "reel_id": reel_id,
                "user_id": user_id,
                "created_at": now,
            }
        ).execute()

        return {
            "reel_id": reel_id,
            "share_count": self._baseline_int(reel, "baseline_share_count")
            + self._count_rows(self.shares_table, reel_id),
        }

    async def create_comment(self, reel_id: str, user_id: str, body: str) -> dict[str, Any]:
        reel = self._get_reel_or_raise(reel_id)

        normalized_body = (body or "").strip()
        if not normalized_body:
            raise ValueError("Comment body cannot be empty")
        if len(normalized_body) > 1200:
            raise ValueError("Comment body must be 1200 characters or less")

        now = datetime.utcnow().isoformat()
        comment_row = {
            "comment_id": str(uuid.uuid4()),
            "reel_id": reel_id,
            "user_id": user_id,
            "body": normalized_body,
            "created_at": now,
            "updated_at": now,
        }
        inserted = self.db.table(self.comments_table).insert(comment_row).execute().data
        inserted_comment = inserted if isinstance(inserted, dict) else comment_row

        return {
            "comment": self._build_comment_payload(inserted_comment, user_id),
            "comment_count": self._baseline_int(reel, "baseline_comment_count")
            + self._count_rows(self.comments_table, reel_id),
        }

    async def get_reel_counts(self, reel_id: str) -> dict[str, int]:
        reel = self._get_reel_or_raise(reel_id)
        return {
            "like_count": self._baseline_int(reel, "baseline_like_count")
            + self._count_rows(self.likes_table, reel_id),
            "save_count": self._baseline_int(reel, "baseline_save_count")
            + self._count_rows(self.saves_table, reel_id),
            "share_count": self._baseline_int(reel, "baseline_share_count")
            + self._count_rows(self.shares_table, reel_id),
            "comment_count": self._baseline_int(reel, "baseline_comment_count")
            + self._count_rows(self.comments_table, reel_id),
        }

    def _get_reel_or_raise(self, reel_id: str) -> dict[str, Any]:
        response = (
            self.db.table(self.reels_table)
            .select(self._FEED_COLUMNS)
            .eq("reel_id", reel_id)
            .single()
            .execute()
        )
        if not response.data:
            raise ValueError("Pitch reel not found")
        return response.data

    def _get_user_or_default(self, user_id: str) -> dict[str, Any]:
        response = (
            self.db.table(self.users_table).select("*").eq("user_id", user_id).single().execute()
        )
        return response.data or {}

    def _count_rows(self, table_name: str, reel_id: str) -> int:
        response = self.db.table(table_name).select("*").eq("reel_id", reel_id).execute()
        return len(response.data or [])

    def _has_user_relation(self, table_name: str, reel_id: str, user_id: str) -> bool:
        response = (
            self.db.table(table_name)
            .select("*")
            .eq("reel_id", reel_id)
            .eq("user_id", user_id)
            .execute()
        )
        return bool(response.data)

    def _toggle_user_relation(
        self, table_name: str, id_column: str, reel_id: str, user_id: str
    ) -> bool:
        existing = (
            self.db.table(table_name)
            .select(id_column)
            .eq("reel_id", reel_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if existing.data and existing.data.get(id_column):
            (
                self.db.table(table_name)
                .delete()
                .eq("reel_id", reel_id)
                .eq("user_id", user_id)
                .execute()
            )
            return False

        now = datetime.utcnow().isoformat()
        self.db.table(table_name).insert(
            {
                id_column: str(uuid.uuid4()),
                "reel_id": reel_id,
                "user_id": user_id,
                "created_at": now,
            }
        ).execute()
        return True

    def _baseline_int(self, reel: dict[str, Any], key: str) -> int:
        value = reel.get(key)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _batch_count_by_reel(self, table_name: str, reel_ids: list[str]) -> dict[str, int]:
        """Return {reel_id: count} in a single query instead of one query per reel."""
        counts: dict[str, int] = {rid: 0 for rid in reel_ids}
        if not reel_ids:
            return counts
        try:
            resp = self.db.table(table_name).select("reel_id").in_("reel_id", reel_ids).execute()
            for row in resp.data or []:
                rid = str(row.get("reel_id") or "")
                if rid in counts:
                    counts[rid] += 1
        except Exception as exc:
            logger.warning(
                "[PitchReelService] _batch_count_by_reel(%s) failed: %s", table_name, exc
            )
        return counts

    def _batch_user_relation_set(self, table_name: str, reel_ids: list[str], user_id: str) -> set:
        """Return set of reel_ids where user_id has a relation (liked/saved)."""
        if not reel_ids or not user_id:
            return set()
        try:
            resp = (
                self.db.table(table_name)
                .select("reel_id")
                .in_("reel_id", reel_ids)
                .eq("user_id", user_id)
                .execute()
            )
            return {str(row.get("reel_id") or "") for row in (resp.data or [])}
        except Exception as exc:
            logger.warning(
                "[PitchReelService] _batch_user_relation_set(%s) failed: %s", table_name, exc
            )
            return set()

    def _batch_get_users(self, user_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Return {user_id: user_row} in a single query."""
        if not user_ids:
            return {}
        try:
            resp = (
                self.db.table(self.users_table)
                .select("user_id,username,first_name,last_name,profile_picture_url")
                .in_("user_id", user_ids)
                .execute()
            )
            return {str(row.get("user_id") or ""): row for row in (resp.data or [])}
        except Exception as exc:
            logger.warning("[PitchReelService] _batch_get_users failed: %s", exc)
            return {}

    def upsert_reel_for_published_idea(
        self,
        idea_id: str,
        owner_user_id: str,
        title: str | None,
        description: str | None,
    ) -> tuple[str, bool]:
        """
        Ensure a pitch_reel exists for a published idea (one reel per idea_id).
        Returns (reel_id, needs_video_generation).
        needs_video_generation is False when the reel already has a ready video
        stored in the database — no API call should be made in that case.
        """
        logger.info(
            "[PitchReelService] upsert_reel_for_published_idea: idea_id=%s user=%s",
            idea_id,
            owner_user_id,
        )
        now = datetime.utcnow().isoformat()
        plain_title = _html_to_plain_text(title or "")
        safe_title = plain_title or "Untitled idea"
        desc = _html_to_plain_text(description or "")
        subtitle = (desc[:220] + "…") if len(desc) > 220 else desc if desc else None
        thesis = subtitle or safe_title
        compact_idea = idea_id.replace("-", "")
        slug = f"idea-{compact_idea[:16]}"

        existing = (
            self.db.table(self.reels_table)
            .select("reel_id, slug, video_status, video_url")
            .eq("idea_id", idea_id)
            .limit(1)
            .execute()
        )
        existing_row = (existing.data or [None])[0]

        # Preserve video fields if a generated video already exists — never
        # reset a "ready" reel back to "pending" or wipe its video_url.
        already_has_video = existing_row is not None and existing_row.get("video_status") == "ready"

        base_payload: dict[str, Any] = {
            "updated_at": now,
            "creator_user_id": owner_user_id,
            "idea_id": idea_id,
            "title": safe_title,
            "subtitle": subtitle,
            "thesis": thesis,
            "description": (desc[:4000] if desc else None),
            "creator_role": "Founder",
            "tags": json.dumps([]),
            "workspace_path": f"/ideas/{idea_id}",
            "accent_from": "#09111f",
            "accent_to": "#2f62e8",
            "is_published": True,
            "featured_rank": USER_REEL_FEATURED_RANK,
        }

        if already_has_video:
            # Keep the existing video_url and video_status intact.
            logger.info(
                "[PitchReelService] Reel for idea %s already has a ready video — skipping re-generation.",
                idea_id,
            )
        else:
            base_payload["video_url"] = USER_REEL_PLACEHOLDER_VIDEO
            base_payload["video_status"] = "pending"
            base_payload["video_generation_error"] = None

        if existing_row:
            reel_id = str(existing_row["reel_id"])
            self.db.table(self.reels_table).update(base_payload).eq("reel_id", reel_id).execute()
            return reel_id, not already_has_video

        reel_id = str(uuid.uuid4())
        insert_payload = {
            **base_payload,
            "reel_id": reel_id,
            "slug": slug,
            "created_at": now,
            "baseline_like_count": 0,
            "baseline_comment_count": 0,
            "baseline_save_count": 0,
            "baseline_share_count": 0,
        }
        try:
            self.db.table(self.reels_table).insert(insert_payload).execute()
        except Exception as exc:
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
                alt_slug = f"{slug}-{uuid.uuid4().hex[:6]}"
                insert_payload["slug"] = alt_slug
                self.db.table(self.reels_table).insert(insert_payload).execute()
            else:
                raise
        return reel_id, True

    def unpublish_reel_for_idea(self, idea_id: str) -> None:
        now = datetime.utcnow().isoformat()
        self.db.table(self.reels_table).update({"is_published": False, "updated_at": now}).eq(
            "idea_id", idea_id
        ).execute()

    def update_reel_video_fields(
        self,
        reel_id: str,
        *,
        video_status: str,
        video_url: str | None = None,
        video_generation_error: str | None = None,
    ) -> None:
        now = datetime.utcnow().isoformat()
        patch: dict[str, Any] = {"video_status": video_status, "updated_at": now}
        if video_url is not None:
            patch["video_url"] = video_url
        patch["video_generation_error"] = video_generation_error
        self.db.table(self.reels_table).update(patch).eq("reel_id", reel_id).execute()

    def store_reel_video_data(self, reel_id: str, video_bytes: bytes) -> None:
        """Persist generated video bytes directly in the database (survives redeployment)."""
        import os

        import psycopg2

        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL not set; cannot store video data")

        conn = psycopg2.connect(dsn)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE pitch_reels SET video_data = %s, updated_at = NOW() WHERE reel_id = %s",
                    (psycopg2.Binary(video_bytes), reel_id),
                )
        finally:
            conn.close()

        logger.info(
            "[PitchReelService] Stored %d bytes for reel %s in DB.", len(video_bytes), reel_id
        )

    def clear_reel_video_data(self, reel_id: str) -> None:
        """Drop legacy DB video bytes after a reel has been moved to object storage."""
        import os

        import psycopg2

        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL not set; cannot clear stored video data")

        conn = psycopg2.connect(dsn)
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE pitch_reels SET video_data = NULL, updated_at = NOW() WHERE reel_id = %s",
                        (reel_id,),
                    )
        finally:
            conn.close()

    def get_reel_video_data(self, reel_id: str) -> bytes | None:
        """Retrieve stored video bytes for a reel. Returns None if not stored."""
        import os

        import psycopg2

        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            return None

        conn = psycopg2.connect(dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT video_data FROM pitch_reels WHERE reel_id = %s",
                    (reel_id,),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if not row or row[0] is None:
            return None

        raw = row[0]
        return bytes(raw) if not isinstance(raw, bytes) else raw

    async def _build_reel_payload(
        self, reel: dict[str, Any], viewer_id: str, reels_with_video_data: set | None = None
    ) -> dict[str, Any]:
        creator = self._get_user_or_default(str(reel.get("creator_user_id") or ""))
        like_count = self._baseline_int(reel, "baseline_like_count") + self._count_rows(
            self.likes_table, str(reel.get("reel_id"))
        )
        save_count = self._baseline_int(reel, "baseline_save_count") + self._count_rows(
            self.saves_table, str(reel.get("reel_id"))
        )
        share_count = self._baseline_int(reel, "baseline_share_count") + self._count_rows(
            self.shares_table, str(reel.get("reel_id"))
        )
        comment_count = self._baseline_int(reel, "baseline_comment_count") + self._count_rows(
            self.comments_table, str(reel.get("reel_id"))
        )

        creator_user_id = str(reel.get("creator_user_id") or "")
        is_following = False
        if viewer_id and creator_user_id and viewer_id != creator_user_id:
            is_following = await self.social_graph_service.is_following(viewer_id, creator_user_id)

        reel_id = str(reel.get("reel_id") or "")
        stored_video_url = str(reel.get("video_url") or "")
        has_video_data = reels_with_video_data is not None and reel_id in reels_with_video_data
        effective_video_url = self._effective_video_url(
            reel_id=reel_id,
            stored_video_url=stored_video_url,
            has_video_data=has_video_data,
        )

        follower_count = (
            await self.social_graph_service.get_follower_count(creator_user_id)
            if creator_user_id
            else 0
        )
        return self._reel_payload(
            reel,
            creator,
            video_url=effective_video_url,
            preview=False,
            follower_count=follower_count,
            is_following=is_following,
            stats=(like_count, comment_count, save_count, share_count),
            liked=self._has_user_relation(self.likes_table, str(reel.get("reel_id")), viewer_id),
            saved=self._has_user_relation(self.saves_table, str(reel.get("reel_id")), viewer_id),
        )

    @staticmethod
    def _reel_payload(
        reel: dict[str, Any],
        creator: dict[str, Any],
        *,
        video_url: str,
        preview: bool,
        follower_count: int,
        is_following: bool,
        stats: tuple[int, int, int, int],
        liked: bool,
        saved: bool,
    ) -> dict[str, Any]:
        """Single shape for feed items and reel detail (``preview`` truncates long text)."""
        text = _feed_preview if preview else (lambda value: value)
        like_count, comment_count, save_count, share_count = stats
        return {
            "reel_id": str(reel.get("reel_id") or ""),
            "slug": str(reel.get("slug") or ""),
            "title": str(reel.get("title") or ""),
            "subtitle": text(reel.get("subtitle")),
            "thesis": text(reel.get("thesis")),
            "description": text(reel.get("description")),
            "tags": _normalize_tags(reel.get("tags")),
            "video_url": video_url,
            "video_status": str(reel.get("video_status") or "ready"),
            "workspace_path": str(reel.get("workspace_path") or "/ideas"),
            "accent_from": str(reel.get("accent_from") or "#09111f"),
            "accent_to": str(reel.get("accent_to") or "#2f62e8"),
            "created_at": reel.get("created_at"),
            "creator": {
                "user_id": str(reel.get("creator_user_id") or ""),
                "handle": str(creator.get("username") or ""),
                "name": _display_name(creator, "Manifest founder"),
                "role": str(reel.get("creator_role") or ""),
                "initials": _make_initials(creator, "MF"),
                "avatar": creator.get("profile_picture_url"),
                "follower_count": follower_count,
                "is_following": is_following,
            },
            "stats": {
                "like_count": like_count,
                "comment_count": comment_count,
                "save_count": save_count,
                "share_count": share_count,
            },
            "viewer_state": {"liked": liked, "saved": saved},
        }

    @staticmethod
    def _effective_video_url(*, reel_id: str, stored_video_url: str, has_video_data: bool) -> str:
        if stored_video_url in {"/videos/tutorial.mov", "/videos/founders-video.mov"}:
            stored_video_url = ""
        if has_video_data and (
            not stored_video_url or stored_video_url.startswith("/api/pitch-reels/")
        ):
            return f"/api/pitch-reels/{reel_id}/video"
        return stored_video_url

    def _build_comment_payload(self, comment: dict[str, Any], viewer_id: str) -> dict[str, Any]:
        author = self._get_user_or_default(str(comment.get("user_id") or ""))
        return {
            "comment_id": str(comment.get("comment_id") or ""),
            "reel_id": str(comment.get("reel_id") or ""),
            "author_id": str(comment.get("user_id") or ""),
            "author_name": _display_name(author, "Manifest founder"),
            "author_avatar": author.get("profile_picture_url"),
            "body": str(comment.get("body") or ""),
            "created_at": comment.get("created_at"),
            "is_mine": str(comment.get("user_id") or "") == viewer_id,
        }


def create_pitch_reel_service(db) -> PitchReelService:
    return PitchReelService(db)
