"""
Background worker: generate a pitch reel video with Veo and post it to Open Media.

Flow per reel (``video_status``): pending → processing → ready | failed |
needs_open_media.

Cost guard (Veo is the most expensive call in Manifest):
- nothing runs when ``OPEN_MEDIA_ENABLED`` is off or ``PITCH_REEL_VIDEO_MODE=disabled``;
- the founder must have linked Open Media *before* Veo runs, otherwise the reel
  waits in ``needs_open_media`` and is generated when they link;
- at most one successful generation per idea per ``VIDEO_REGENERATION_COOLDOWN``;
- if the upload fails after generation, the MP4 stays on local disk and the
  next attempt re-uploads it instead of calling Veo again.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from typing import Any

from app.db.database import create_database_client
from app.services.integrations.open_media import clips, identity, settings
from app.services.integrations.open_media.client import OpenMediaError, OpenMediaNotLinked
from app.services.pitch_reels.gemini_video import generate_pitch_video_to_path
from app.services.pitch_reels.service import STATUS_NEEDS_OPEN_MEDIA, create_pitch_reel_service
from app.utils.logger import logger

VIDEO_REGENERATION_COOLDOWN = timedelta(days=30)


def _temp_output_path(reel_id: str) -> Path:
    root = Path(__file__).resolve().parents[4]
    return root / "generated" / "pdfs" / "pitch-reels" / f"{reel_id}.mp4"


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def video_generation_enabled() -> bool:
    mode = (os.getenv("PITCH_REEL_VIDEO_MODE") or "thread").strip().lower()
    return settings.enabled() and mode != "disabled"


def _post_body(title: str, thesis: str) -> str:
    body = title.strip() or "A Manifest pitch"
    if thesis and thesis.strip() and thesis.strip() != body:
        body = f"{body}\n\n{thesis.strip()}"
    return body[:500]


def run_pitch_reel_video_job(reel_id: str, idea_title: str, idea_description: str) -> None:
    """Sync entry point (runs in a daemon thread)."""
    db = create_database_client()
    service = create_pitch_reel_service(db)
    reel = service.get_reel(reel_id)
    if not reel or not reel.get("is_published") or reel.get("om_post_id"):
        return
    creator_id = str(reel.get("creator_user_id") or "")

    if not identity.handle_for_user(creator_id):
        service.update_reel_video_fields(reel_id, video_status=STATUS_NEEDS_OPEN_MEDIA)
        return

    out_path = _temp_output_path(reel_id)
    cached = out_path.is_file() and out_path.stat().st_size >= 32
    if not cached:
        generated_at = _parse_time(reel.get("video_generated_at"))
        if generated_at and datetime.now(UTC) - generated_at < VIDEO_REGENERATION_COOLDOWN:
            retry_after = (generated_at + VIDEO_REGENERATION_COOLDOWN).date().isoformat()
            service.update_reel_video_fields(
                reel_id,
                video_status="failed",
                video_generation_error=(
                    "This idea already had a video recently. "
                    f"A new one can be generated after {retry_after}."
                ),
            )
            return
        if not os.getenv("GOOGLE_API_KEY", "").strip():
            logger.info("[PitchReelVideo] No GOOGLE_API_KEY; reel %s stays without video.", reel_id)
            service.update_reel_video_fields(
                reel_id,
                video_status="failed",
                video_generation_error="Video generation is not configured on this server.",
            )
            return
        service.update_reel_video_fields(reel_id, video_status="processing")
        if not generate_pitch_video_to_path(idea_title, idea_description, out_path):
            service.update_reel_video_fields(
                reel_id,
                video_status="failed",
                video_generation_error="Video generation failed or the API is unavailable.",
            )
            return
        service.update_reel_video_fields(reel_id, video_status="processing", video_generated=True)

    _publish_to_open_media(service, reel, out_path)


def _publish_to_open_media(service: Any, reel: dict[str, Any], video_path: Path) -> None:
    reel_id = str(reel["reel_id"])
    creator_id = str(reel.get("creator_user_id") or "")
    title = str(reel.get("title") or "")
    try:
        video = clips.upload_video(creator_id, video_path.read_bytes(), "video/mp4")
        post = clips.create_post(
            creator_id,
            body=_post_body(title, str(reel.get("thesis") or "")),
            video=video,
            context={
                "app": settings.APP_TAG,
                "idea_id": str(reel.get("idea_id") or ""),
                "title": title[:200],
                "url": settings.clip_url(reel_id),
            },
            client_id=str(uuid.uuid4()),
        )
    except OpenMediaNotLinked:
        # Keep the MP4 so linking again re-uploads it without another Veo call.
        service.update_reel_video_fields(reel_id, video_status=STATUS_NEEDS_OPEN_MEDIA)
        return
    except (OpenMediaError, OSError, ValueError) as exc:
        logger.error("[PitchReelVideo] Upload to Open Media failed for %s: %s", reel_id, exc)
        service.update_reel_video_fields(
            reel_id,
            video_status="failed",
            video_generation_error=f"Could not post the video to Open Media: {exc!s:.200}",
        )
        return

    service.update_reel_video_fields(reel_id, video_status="ready", om_post_id=post["id"])
    with contextlib.suppress(OSError):
        video_path.unlink(missing_ok=True)
    logger.info("[PitchReelVideo] Reel %s posted to Open Media as %s.", reel_id, post["id"])


def schedule_pitch_reel_video_generation(
    reel_id: str, idea_title: str, idea_description: str
) -> None:
    """Fire-and-forget background thread (no-op when Open Media or video is off)."""
    if not video_generation_enabled():
        return

    def _target() -> None:
        try:
            run_pitch_reel_video_job(reel_id, idea_title, idea_description)
        except Exception as exc:
            logger.error("[PitchReelVideo] Job crashed for %s: %s", reel_id, exc)
            try:
                create_pitch_reel_service(create_database_client()).update_reel_video_fields(
                    reel_id,
                    video_status="failed",
                    video_generation_error=str(exc)[:500],
                )
            except Exception as inner:
                logger.error("[PitchReelVideo] Failed to mark reel failed: %s", inner)

    Thread(target=_target, name=f"pitch-reel-video-{reel_id[:8]}", daemon=True).start()


def resume_reels_waiting_for_open_media(user_id: str) -> int:
    """Called after a founder links Open Media: generate and post their waiting reels."""
    service = create_pitch_reel_service(create_database_client())
    waiting = service.reels_waiting_for_open_media(user_id)
    for reel in waiting:
        service.update_reel_video_fields(str(reel["reel_id"]), video_status="pending")
        schedule_pitch_reel_video_generation(
            str(reel["reel_id"]),
            str(reel.get("title") or ""),
            str(reel.get("description") or ""),
        )
    return len(waiting)
