"""Pitch Shorts as Open Media clips: upload, post, like, comment, reshare, feed.

Clips are Open Media posts with a video and ``context.app = "manifest"``.
The public clips feed is cached briefly (it carries like/comment counts) and
dropped by ``post.*`` webhooks; a linked viewer's feed is fetched live because
it carries ``viewer.liked``.
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import quote

from app.services.integrations.open_media import settings, store
from app.services.integrations.open_media.client import (
    UPLOAD_TIMEOUT,
    OpenMediaError,
    OpenMediaNotLinked,
    get_client,
    person,
    pick,
)
from app.services.shared.cache import cache_delete, cache_get, cache_set
from app.utils.logger import logger

FEED_FETCH_LIMIT = 50
PUBLIC_FEED_TTL_SECONDS = 60
MAX_VIDEO_BYTES = 100 * 1024 * 1024
MAX_COMMENT_CHARS = 2000
_PUBLIC_FEED_KEY = "open_media:clips:public"


def invalidate_clip_stats(post_ids: list[str] | None = None) -> None:
    """Drop cached counts (the public feed is cached as one list)."""
    cache_delete(_PUBLIC_FEED_KEY)


def _post_path(post_id: str, suffix: str = "") -> str:
    return f"/posts/{quote(str(post_id), safe='')}{suffix}"


def normalize_post(raw: dict[str, Any]) -> dict[str, Any]:
    video = raw.get("video") if isinstance(raw.get("video"), dict) else {}
    counts = pick(raw, "counts", "engagement", default={}) or {}
    viewer = raw.get("viewer") if isinstance(raw.get("viewer"), dict) else {}
    context = raw.get("context") if isinstance(raw.get("context"), dict) else {}
    return {
        "id": str(pick(raw, "id", default="")),
        "body": str(pick(raw, "body", default="") or ""),
        "created_at": pick(raw, "created_at", "createdAt"),
        "author": person(raw.get("author")),
        "video_url": str(pick(video, "url", default="") or ""),
        "poster_url": pick(video, "poster_url", "posterUrl"),
        "context": context,
        "like_count": int(pick(counts, "likes", default=0) or 0),
        "comment_count": int(pick(counts, "comments", "replies", default=0) or 0),
        "reshare_count": int(pick(counts, "reshares", "reposts", default=0) or 0),
        "viewer_liked": bool(pick(viewer, "liked", default=pick(counts, "liked", default=False))),
        "viewer_reshared": bool(
            pick(viewer, "reshared", default=pick(counts, "reshared", default=False))
        ),
    }


def _posts(body: dict[str, Any]) -> list[dict[str, Any]]:
    items = pick(body, "posts", "items", "feed", "data", default=[]) or []
    return [normalize_post(p) for p in items if isinstance(p, dict)]


def _public_feed() -> list[dict[str, Any]]:
    cached = cache_get(_PUBLIC_FEED_KEY)
    if isinstance(cached, list):
        return cached
    body = get_client().public(
        "/v1/feed", params={"kind": "clips", "app": settings.APP_TAG, "limit": FEED_FETCH_LIMIT}
    )
    posts = _posts(body)
    cache_set(_PUBLIC_FEED_KEY, posts, PUBLIC_FEED_TTL_SECONDS)
    return posts


def feed(viewer_user_id: str | None) -> list[dict[str, Any]]:
    """Manifest clips, newest first. Uses the viewer's token when linked (adds ``viewer_liked``)."""
    if viewer_user_id:
        metadata = store.link_metadata(str(viewer_user_id))
        if metadata and not metadata.get("needs_reconnect"):
            try:
                body = get_client().connected(
                    str(viewer_user_id),
                    "GET",
                    "/feed",
                    params={"kind": "clips", "app": settings.APP_TAG, "limit": FEED_FETCH_LIMIT},
                )
                return _posts(body)
            except OpenMediaNotLinked:
                pass
    return _public_feed()


def upload_video(
    user_id: str,
    data: bytes,
    content_type: str = "video/mp4",
    *,
    duration_ms: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    """Upload raw video bytes as the user. Returns the opaque ``video`` object.

    httpx sends ``Content-Length`` for a bytes body (Open Media answers 411
    without it). Pass the metadata when known; Open Media may answer 422 for a
    file without ``moov`` metadata otherwise. Clips can be up to 180 s.
    """
    if not data:
        raise ValueError("No video bytes to upload.")
    if len(data) > MAX_VIDEO_BYTES:
        raise ValueError("Videos can be up to 100 MB.")
    body = get_client().connected(
        user_id,
        "POST",
        "/media/videos",
        content=data,
        headers={"Content-Type": content_type},
        params={"duration_ms": duration_ms, "width": width, "height": height},
        timeout=UPLOAD_TIMEOUT,
        idempotent=False,
    )
    video = body.get("video")
    if not isinstance(video, dict):
        raise OpenMediaError("Open Media did not accept the video.")
    return video


def create_post(
    user_id: str,
    *,
    body: str,
    video: dict[str, Any] | None,
    context: dict[str, Any],
    client_id: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"body": body[:2000], "context": context, "client_id": client_id}
    if video is not None:
        payload["video"] = video
    response = get_client().connected(
        user_id,
        "POST",
        "/posts",
        json=payload,
        headers={"Idempotency-Key": client_id},
        idempotent=True,
    )
    # Open Media returns the post under ``post`` and also at the top level.
    post = response.get("post") if isinstance(response.get("post"), dict) else response
    if not post.get("id"):
        raise OpenMediaError("Open Media did not create the post.")
    invalidate_clip_stats()
    return normalize_post(post)


def delete_post(user_id: str, post_id: str) -> None:
    try:
        get_client().connected(user_id, "DELETE", _post_path(post_id))
    except OpenMediaError as exc:
        if exc.status != 404:
            raise
    invalidate_clip_stats()


def _engagement(response: dict[str, Any]) -> dict[str, Any]:
    source = pick(response, "engagement", "counts", "post", default=response) or {}
    return {
        "like_count": pick(source, "likes"),
        "reshare_count": pick(source, "reshares", "reposts"),
    }


def set_like(user_id: str, post_id: str, liked: bool) -> dict[str, Any]:
    client = get_client()
    path = _post_path(post_id, "/like")
    if liked:
        try:
            # Liking is a set, not a toggle, so a retried POST is safe.
            response = client.connected(user_id, "POST", path, idempotent=True)
        except OpenMediaError as exc:
            if exc.status != 405:
                raise
            response = client.connected(user_id, "PUT", path)  # older /v1/me routes
    else:
        response = client.connected(user_id, "DELETE", path)
    invalidate_clip_stats()
    return _engagement(response)


def set_reshare(user_id: str, post_id: str, reshared: bool) -> dict[str, Any]:
    response = get_client().connected(
        user_id, "PUT" if reshared else "DELETE", _post_path(post_id, "/reshare")
    )
    invalidate_clip_stats()
    return _engagement(response)


def _comment(raw: dict[str, Any], post_id: str) -> dict[str, Any]:
    author = raw.get("author") if isinstance(raw.get("author"), dict) else {}
    if not author and pick(raw, "author_id", "authorId"):
        author = {"id": pick(raw, "author_id", "authorId")}
    return {
        "id": str(pick(raw, "id", default="")),
        "post_id": str(pick(raw, "post_id", "postId", default=post_id)),
        "body": str(pick(raw, "body", "text", default="") or ""),
        "created_at": pick(raw, "created_at", "createdAt"),
        "author": person(author),
    }


def comments(post_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    body = get_client().public(
        f"/v1/posts/{quote(str(post_id), safe='')}/comments",
        params={"limit": max(1, min(int(limit), 200))},
    )
    items = pick(body, "comments", "data", default=[]) or []
    return [_comment(c, post_id) for c in items if isinstance(c, dict)]


def add_comment(user_id: str, post_id: str, body: str) -> dict[str, Any]:
    text = (body or "").strip()
    if not text:
        raise ValueError("Write the comment first.")
    if len(text) > MAX_COMMENT_CHARS:
        raise ValueError("Comments can be up to 2,000 characters.")
    key = str(uuid.uuid4())
    response = get_client().connected(
        user_id,
        "POST",
        _post_path(post_id, "/comments"),
        json={"body": text, "client_id": key},
        headers={"Idempotency-Key": key},
        idempotent=True,
    )
    invalidate_clip_stats()
    raw = pick(response, "comment", default=response) or {}
    comment = _comment(raw if isinstance(raw, dict) else {}, post_id)
    if not comment["body"]:
        comment["body"] = text
    logger.info("[open_media] comment posted", extra={"open_media.post_id": post_id})
    return comment
