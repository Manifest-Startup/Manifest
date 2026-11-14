"""Pitch reel GraphQL types and payload mappers (split from schema.py for maintainability)."""

from __future__ import annotations

from datetime import datetime

import strawberry


def _coerce_datetime(value: object | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return datetime.utcnow()
    return datetime.utcnow()


@strawberry.type
class PitchReelCreator:
    user_id: str
    handle: str | None = None
    name: str
    role: str | None = None
    initials: str
    avatar: str | None = None
    follower_count: int = 0
    is_following: bool = False


@strawberry.type
class PitchReelSocialStats:
    like_count: int
    comment_count: int
    save_count: int
    share_count: int


@strawberry.type
class PitchReelViewerState:
    liked: bool = False
    saved: bool = False


@strawberry.type
class PitchReel:
    reel_id: str
    slug: str
    title: str
    subtitle: str | None = None
    thesis: str | None = None
    description: str | None = None
    tags: list[str]
    video_url: str
    video_status: str = "ready"
    workspace_path: str
    accent_from: str
    accent_to: str
    created_at: datetime
    creator: PitchReelCreator
    stats: PitchReelSocialStats
    viewer_state: PitchReelViewerState
    idea_id: str | None = None


@strawberry.type
class PitchReelComment:
    comment_id: str
    reel_id: str
    author_id: str
    author_name: str
    author_avatar: str | None = None
    body: str
    created_at: datetime
    is_mine: bool = False


@strawberry.type
class PitchReelLikeResult:
    reel_id: str
    liked: bool
    like_count: int


@strawberry.type
class PitchReelSaveResult:
    reel_id: str
    saved: bool
    save_count: int


@strawberry.type
class PitchReelShareResult:
    reel_id: str
    share_count: int


@strawberry.type
class PitchReelCommentCreateResult:
    comment: PitchReelComment
    comment_count: int


def map_pitch_reel(payload: dict[str, object]) -> PitchReel:
    creator = payload.get("creator", {}) or {}
    stats = payload.get("stats", {}) or {}
    viewer_state = payload.get("viewer_state", {}) or {}
    raw_idea_id = payload.get("idea_id")
    if raw_idea_id is None:
        mapped_idea_id: str | None = None
    else:
        s = str(raw_idea_id).strip()
        mapped_idea_id = s if s else None

    return PitchReel(
        reel_id=str(payload.get("reel_id") or ""),
        slug=str(payload.get("slug") or ""),
        title=str(payload.get("title") or ""),
        subtitle=payload.get("subtitle"),
        thesis=payload.get("thesis"),
        description=payload.get("description"),
        tags=[str(tag) for tag in (payload.get("tags") or [])],
        video_url=str(payload.get("video_url") or ""),
        video_status=str(payload.get("video_status") or "ready"),
        workspace_path=str(payload.get("workspace_path") or "/ideas"),
        accent_from=str(payload.get("accent_from") or "#09111f"),
        accent_to=str(payload.get("accent_to") or "#2f62e8"),
        created_at=_coerce_datetime(payload.get("created_at")),
        creator=PitchReelCreator(
            user_id=str(creator.get("user_id") or ""),
            handle=creator.get("handle"),
            name=str(creator.get("name") or "Manifest founder"),
            role=creator.get("role"),
            initials=str(creator.get("initials") or "MF"),
            avatar=creator.get("avatar"),
            follower_count=int(creator.get("follower_count") or 0),
            is_following=bool(creator.get("is_following") or False),
        ),
        stats=PitchReelSocialStats(
            like_count=int(stats.get("like_count") or 0),
            comment_count=int(stats.get("comment_count") or 0),
            save_count=int(stats.get("save_count") or 0),
            share_count=int(stats.get("share_count") or 0),
        ),
        viewer_state=PitchReelViewerState(
            liked=bool(viewer_state.get("liked") or False),
            saved=bool(viewer_state.get("saved") or False),
        ),
        idea_id=mapped_idea_id,
    )


def map_pitch_reel_comment(payload: dict[str, object]) -> PitchReelComment:
    return PitchReelComment(
        comment_id=str(payload.get("comment_id") or ""),
        reel_id=str(payload.get("reel_id") or ""),
        author_id=str(payload.get("author_id") or ""),
        author_name=str(payload.get("author_name") or "Manifest founder"),
        author_avatar=payload.get("author_avatar"),
        body=str(payload.get("body") or ""),
        created_at=_coerce_datetime(payload.get("created_at")),
        is_mine=bool(payload.get("is_mine") or False),
    )
