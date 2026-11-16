"""
Pitch Reel Service: Manifest's side of Pitch Shorts.

Manifest owns the reel row (idea pointer, pitch copy, video generation status,
``om_post_id``). Open Media owns the clip itself: the video file, likes,
comments and reshares. The feed joins the two by ``om_post_id``. All Open
Media calls go through ``app.services.integrations.open_media``.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover - exercised only in lean environments
    BeautifulSoup = None  # type: ignore[assignment]

from app.services.integrations.open_media import clips, identity
from app.services.integrations.open_media.client import OpenMediaError
from app.services.social.graph import create_social_graph_service
from app.utils.logger import logger

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


STATUS_NEEDS_OPEN_MEDIA = "needs_open_media"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class PitchReelService:
    def __init__(self, db):
        self.db = db
        self.reels_table = "pitch_reels"
        self.users_table = "users"
        self.social_graph_service = create_social_graph_service(db)

    _FEED_COLUMNS = (
        "reel_id,slug,creator_user_id,idea_id,title,subtitle,thesis,description,"
        "creator_role,tags,video_status,video_generation_error,om_post_id,"
        "workspace_path,accent_from,accent_to,featured_rank,is_published,created_at,updated_at"
    )

    # -- feed -------------------------------------------------------------

    async def list_feed(self, viewer_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Published reels joined with their Open Media clips (video, counts, viewer.liked).

        Reels with a clip come first (in Open Media's order); reels still waiting
        for a video follow, so a founder sees their own pending reel.
        """
        limit = max(1, min(limit, 50))
        reels = await asyncio.to_thread(self._published_reels, limit * 2)
        if not reels:
            return []
        posts_by_id: dict[str, dict[str, Any]] = {}
        try:
            posts = await asyncio.to_thread(clips.feed, viewer_id or None)
            posts_by_id = {p["id"]: p for p in posts if p.get("id")}
        except OpenMediaError as exc:
            # Open Media outage: still show pitch copy so ideas stay discoverable.
            logger.warning("[PitchReelService] clips feed unavailable: %s", exc.code or exc.status)

        rank = {post_id: index for index, post_id in enumerate(posts_by_id)}
        with_clip = [r for r in reels if str(r.get("om_post_id") or "") in posts_by_id]
        with_clip.sort(key=lambda r: rank[str(r["om_post_id"])])
        waiting = [r for r in reels if not r.get("om_post_id")]
        ordered = (with_clip + waiting)[:limit]

        creator_ids = list({str(r.get("creator_user_id") or "") for r in ordered} - {""})
        users_map = await asyncio.to_thread(self._batch_get_users, creator_ids)
        follower_counts = await self.social_graph_service.get_follower_counts(creator_ids)
        following_set = (
            await self.social_graph_service.get_following_set(viewer_id, creator_ids)
            if viewer_id
            else set()
        )
        payloads = []
        for reel in ordered:
            creator_id = str(reel.get("creator_user_id") or "")
            payloads.append(
                self._reel_payload(
                    reel,
                    users_map.get(creator_id) or {},
                    posts_by_id.get(str(reel.get("om_post_id") or "")),
                    follower_count=follower_counts.get(creator_id, 0),
                    is_following=creator_id in following_set,
                )
            )
        return payloads

    def _published_reels(self, limit: int) -> list[dict[str, Any]]:
        query = self.db.table(self.reels_table).select(self._FEED_COLUMNS).eq("is_published", True)
        for demo_id in DEMO_REEL_IDS:
            query = query.neq("reel_id", demo_id)
        response = query.order("created_at", desc=True).limit(max(limit, 50)).execute()
        return [r for r in (response.data or []) if isinstance(r, dict)]

    def _batch_get_users(self, user_ids: list[str]) -> dict[str, dict[str, Any]]:
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

    @staticmethod
    def _reel_payload(
        reel: dict[str, Any],
        creator: dict[str, Any],
        post: dict[str, Any] | None,
        *,
        follower_count: int,
        is_following: bool,
    ) -> dict[str, Any]:
        post = post or {}
        status = str(reel.get("video_status") or "pending")
        if reel.get("om_post_id") and not post:
            status = "ready"  # clip exists but is outside the fetched feed page
        return {
            "reel_id": str(reel.get("reel_id") or ""),
            "slug": str(reel.get("slug") or ""),
            "idea_id": str(reel.get("idea_id") or ""),
            "om_post_id": reel.get("om_post_id"),
            "title": str(reel.get("title") or ""),
            "subtitle": _feed_preview(reel.get("subtitle")),
            "thesis": _feed_preview(reel.get("thesis")),
            "description": _feed_preview(reel.get("description")),
            "tags": _normalize_tags(reel.get("tags")),
            "video_url": str(post.get("video_url") or ""),
            "poster_url": post.get("poster_url"),
            "video_status": status,
            "workspace_path": str(reel.get("workspace_path") or "/ideas"),
            "accent_from": str(reel.get("accent_from") or "#09111f"),
            "accent_to": str(reel.get("accent_to") or "#2f62e8"),
            "created_at": reel.get("created_at"),
            "creator": {
                "user_id": str(reel.get("creator_user_id") or ""),
                "handle": str(
                    (post.get("author") or {}).get("handle") or creator.get("username") or ""
                ),
                "name": _display_name(creator, "Manifest founder"),
                "role": str(reel.get("creator_role") or ""),
                "initials": _make_initials(creator, "MF"),
                "avatar": creator.get("profile_picture_url"),
                "follower_count": follower_count,
                "is_following": is_following,
            },
            "stats": {
                "like_count": int(post.get("like_count") or 0),
                "comment_count": int(post.get("comment_count") or 0),
                "share_count": int(post.get("reshare_count") or 0),
            },
            "viewer_state": {
                "liked": bool(post.get("viewer_liked")),
                "reshared": bool(post.get("viewer_reshared")),
            },
        }

    # -- social actions (Open Media) -------------------------------------

    def _post_id_or_raise(self, reel_id: str) -> str:
        response = (
            self.db.table(self.reels_table)
            .select("reel_id,om_post_id,is_published")
            .eq("reel_id", reel_id)
            .single()
            .execute()
        )
        reel = response.data if isinstance(response.data, dict) else None
        if not reel or not reel.get("is_published"):
            raise ValueError("Pitch reel not found")
        post_id = str(reel.get("om_post_id") or "")
        if not post_id:
            raise ValueError("This pitch reel's video is not ready yet.")
        return post_id

    async def set_like(self, reel_id: str, user_id: str, liked: bool) -> dict[str, Any]:
        post_id = self._post_id_or_raise(reel_id)
        result = await asyncio.to_thread(clips.set_like, user_id, post_id, liked)
        return {"reel_id": reel_id, "liked": liked, "like_count": result.get("like_count")}

    async def set_reshare(self, reel_id: str, user_id: str, reshared: bool) -> dict[str, Any]:
        post_id = self._post_id_or_raise(reel_id)
        result = await asyncio.to_thread(clips.set_reshare, user_id, post_id, reshared)
        return {
            "reel_id": reel_id,
            "reshared": reshared,
            "share_count": result.get("reshare_count"),
        }

    async def list_comments(
        self, reel_id: str, viewer_id: str, limit: int = 120
    ) -> list[dict[str, Any]]:
        try:
            post_id = self._post_id_or_raise(reel_id)
        except ValueError:
            return []
        items = await asyncio.to_thread(clips.comments, post_id, limit=limit)
        viewer_om_id = identity.om_user_id_for(viewer_id) if viewer_id else None
        return [self._comment_payload(c, reel_id, viewer_om_id) for c in items]

    async def create_comment(self, reel_id: str, user_id: str, body: str) -> dict[str, Any]:
        post_id = self._post_id_or_raise(reel_id)
        comment = await asyncio.to_thread(clips.add_comment, user_id, post_id, body)
        payload = self._comment_payload(comment, reel_id, None)
        payload["is_mine"] = True
        return {"comment": payload}

    @staticmethod
    def _comment_payload(
        comment: dict[str, Any], reel_id: str, viewer_om_id: str | None
    ) -> dict[str, Any]:
        author = comment.get("author") or {}
        return {
            "comment_id": str(comment.get("id") or ""),
            "reel_id": reel_id,
            "author_id": str(author.get("id") or ""),
            "author_name": str(
                author.get("display_name") or author.get("handle") or "Open Media user"
            ),
            "author_handle": author.get("handle") or None,
            "author_avatar": author.get("avatar_url"),
            "body": str(comment.get("body") or ""),
            "created_at": comment.get("created_at"),
            "is_mine": bool(viewer_om_id and author.get("id") == viewer_om_id),
        }

    # -- publishing ---------------------------------------------------------

    def upsert_reel_for_published_idea(
        self,
        idea_id: str,
        owner_user_id: str,
        title: str | None,
        description: str | None,
    ) -> tuple[str, bool]:
        """Ensure one reel row per published idea.

        Returns ``(reel_id, needs_video)``. ``needs_video`` is False when the
        reel already has an Open Media clip. The worker applies the Veo cost
        guard (``VIDEO_REGENERATION_COOLDOWN``) before generating anything.
        """
        now = _now_iso()
        plain_title = _html_to_plain_text(title or "")
        safe_title = plain_title or "Untitled idea"
        desc = _html_to_plain_text(description or "")
        subtitle = (desc[:220] + "…") if len(desc) > 220 else desc if desc else None
        thesis = subtitle or safe_title
        slug = f"idea-{idea_id.replace('-', '')[:16]}"

        existing = (
            self.db.table(self.reels_table)
            .select("reel_id, slug, video_status, om_post_id")
            .eq("idea_id", idea_id)
            .limit(1)
            .execute()
        )
        existing_row = (existing.data or [None])[0]

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

        if existing_row:
            reel_id = str(existing_row["reel_id"])
            needs_video = not existing_row.get("om_post_id")
            if needs_video:
                base_payload["video_status"] = "pending"
                base_payload["video_generation_error"] = None
            self.db.table(self.reels_table).update(base_payload).eq("reel_id", reel_id).execute()
            return reel_id, needs_video

        reel_id = str(uuid.uuid4())
        insert_payload = {
            **base_payload,
            "reel_id": reel_id,
            "slug": slug,
            "created_at": now,
            "video_url": "",
            "video_status": "pending",
            "video_generation_error": None,
        }
        try:
            self.db.table(self.reels_table).insert(insert_payload).execute()
        except Exception as exc:
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
                insert_payload["slug"] = f"{slug}-{uuid.uuid4().hex[:6]}"
                self.db.table(self.reels_table).insert(insert_payload).execute()
            else:
                raise
        return reel_id, True

    def unpublish_reel_for_idea(self, idea_id: str) -> None:
        """Hide the reel and delete its Open Media clip (best effort)."""
        response = (
            self.db.table(self.reels_table)
            .select("reel_id,creator_user_id,om_post_id")
            .eq("idea_id", idea_id)
            .limit(1)
            .execute()
        )
        row = (response.data or [None])[0]
        patch: dict[str, Any] = {"is_published": False, "updated_at": _now_iso()}
        if row and row.get("om_post_id"):
            try:
                clips.delete_post(str(row["creator_user_id"]), str(row["om_post_id"]))
                patch["om_post_id"] = None
            except OpenMediaError as exc:
                # Keep the pointer so a later unpublish/cleanup can retry the delete.
                logger.warning(
                    "[PitchReelService] could not delete clip: %s", exc.code or exc.status
                )
        self.db.table(self.reels_table).update(patch).eq("idea_id", idea_id).execute()

    def update_reel_video_fields(
        self,
        reel_id: str,
        *,
        video_status: str,
        video_generation_error: str | None = None,
        om_post_id: str | None = None,
        video_generated: bool = False,
    ) -> None:
        patch: dict[str, Any] = {
            "video_status": video_status,
            "video_generation_error": video_generation_error,
            "updated_at": _now_iso(),
        }
        if om_post_id is not None:
            patch["om_post_id"] = om_post_id
        if video_generated:
            patch["video_generated_at"] = _now_iso()
        self.db.table(self.reels_table).update(patch).eq("reel_id", reel_id).execute()

    def get_reel(self, reel_id: str) -> dict[str, Any] | None:
        response = (
            self.db.table(self.reels_table)
            .select(
                "reel_id,idea_id,creator_user_id,title,thesis,om_post_id,is_published,"
                "video_status,video_generated_at"
            )
            .eq("reel_id", reel_id)
            .single()
            .execute()
        )
        return response.data if isinstance(response.data, dict) else None

    def reels_waiting_for_open_media(self, user_id: str) -> list[dict[str, Any]]:
        response = (
            self.db.table(self.reels_table)
            .select("reel_id,idea_id,title,description,is_published,video_status")
            .eq("creator_user_id", user_id)
            .eq("video_status", STATUS_NEEDS_OPEN_MEDIA)
            .execute()
        )
        return [r for r in (response.data or []) if isinstance(r, dict) and r.get("is_published")]


def create_pitch_reel_service(db) -> PitchReelService:
    return PitchReelService(db)
