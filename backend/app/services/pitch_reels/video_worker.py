"""
Background worker: Gemini video generation for user pitch reels.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from threading import Thread

from app.db.database import create_database_client
from app.services.pitch_reels.gemini_video import generate_pitch_video_to_path
from app.services.pitch_reels.media import publish_reel_video_bytes
from app.services.pitch_reels.service import USER_REEL_PLACEHOLDER_VIDEO, create_pitch_reel_service
from app.utils.logger import logger


def _db_video_url(reel_id: str) -> str:
    return f"/api/pitch-reels/{reel_id}/video"


def _temp_output_path(reel_id: str) -> Path:
    root = Path(__file__).resolve().parents[4]
    return root / "generated" / "pdfs" / "pitch-reels" / f"{reel_id}.mp4"


def run_pitch_reel_video_job(reel_id: str, idea_title: str, idea_description: str) -> None:
    """Sync entry point: generates video, stores bytes in DB, updates reel record."""
    db = create_database_client()
    service = create_pitch_reel_service(db)

    if not os.getenv("GOOGLE_API_KEY", "").strip():
        logger.info(
            "[PitchReelVideo] No GOOGLE_API_KEY; leaving reel %s on placeholder video.", reel_id
        )
        service.update_reel_video_fields(
            reel_id,
            video_status="ready",
            video_url=USER_REEL_PLACEHOLDER_VIDEO,
            video_generation_error=None,
        )
        return

    service.update_reel_video_fields(
        reel_id,
        video_status="processing",
        video_generation_error=None,
    )

    out_path = _temp_output_path(reel_id)
    ok = generate_pitch_video_to_path(idea_title, idea_description, out_path)

    if ok:
        try:
            video_bytes = out_path.read_bytes()
            published_media = publish_reel_video_bytes(reel_id, video_bytes)
            if published_media is not None:
                logger.info(
                    "[PitchReelVideo] Uploaded reel %s to object storage at %s.",
                    reel_id,
                    published_media.playback_url,
                )
                try:
                    service.clear_reel_video_data(reel_id)
                except Exception as clear_exc:
                    logger.warning(
                        "[PitchReelVideo] Could not clear legacy DB bytes for %s: %s",
                        reel_id,
                        clear_exc,
                    )
                service.update_reel_video_fields(
                    reel_id,
                    video_status="ready",
                    video_url=published_media.playback_url,
                    video_generation_error=None,
                )
                return

            service.store_reel_video_data(reel_id, video_bytes)
            logger.info(
                "[PitchReelVideo] Stored %d bytes in DB for reel %s.", len(video_bytes), reel_id
            )
        except Exception as store_exc:
            logger.error("[PitchReelVideo] Failed to store video in DB: %s", store_exc)
            service.update_reel_video_fields(
                reel_id,
                video_status="failed",
                video_url=USER_REEL_PLACEHOLDER_VIDEO,
                video_generation_error=f"Video generated but could not be stored: {store_exc!s:.200}",
            )
            return
        finally:
            with contextlib.suppress(Exception):
                out_path.unlink(missing_ok=True)

        service.update_reel_video_fields(
            reel_id,
            video_status="ready",
            video_url=_db_video_url(reel_id),
            video_generation_error=None,
        )
    else:
        service.update_reel_video_fields(
            reel_id,
            video_status="failed",
            video_url=USER_REEL_PLACEHOLDER_VIDEO,
            video_generation_error="Video generation failed or API unavailable. Using placeholder.",
        )


def schedule_pitch_reel_video_generation(
    reel_id: str, idea_title: str, idea_description: str
) -> None:
    """Fire-and-forget background thread."""

    def _target() -> None:
        try:
            run_pitch_reel_video_job(reel_id, idea_title, idea_description)
        except Exception as exc:
            logger.error("[PitchReelVideo] Job crashed for %s: %s", reel_id, exc)
            try:
                db = create_database_client()
                create_pitch_reel_service(db).update_reel_video_fields(
                    reel_id,
                    video_status="failed",
                    video_generation_error=str(exc)[:500],
                )
            except Exception as inner:
                logger.error("[PitchReelVideo] Failed to mark reel failed: %s", inner)

    Thread(target=_target, name=f"pitch-reel-video-{reel_id[:8]}", daemon=True).start()
