"""
Backfill legacy DB-backed pitch reel videos into object storage.

Usage:
    python backend/scripts/migrate_pitch_reel_videos_to_storage.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.pitch_reel_media_service import publish_reel_video_bytes, storage_is_configured
from app.utils.logger import logger


def run() -> None:
    if not storage_is_configured():
        logger.error("Supabase storage is not configured; cannot migrate pitch reel videos.")
        sys.exit(1)

    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        logger.error("DATABASE_URL is not set; cannot migrate pitch reel videos.")
        sys.exit(1)

    migrated = 0
    skipped = 0

    conn = psycopg2.connect(dsn)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT reel_id, video_url, video_data
                    FROM pitch_reels
                    WHERE video_data IS NOT NULL
                    """
                )
                rows = cur.fetchall()

        for reel_id, existing_url, video_data in rows:
            if not video_data:
                skipped += 1
                continue

            published_media = publish_reel_video_bytes(str(reel_id), bytes(video_data))
            if published_media is None:
                raise RuntimeError(f"Storage publish returned no URL for reel {reel_id}")

            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE pitch_reels
                        SET video_url = %s,
                            video_data = NULL,
                            updated_at = NOW()
                        WHERE reel_id = %s
                        """,
                        (published_media.playback_url, str(reel_id)),
                    )

            migrated += 1
            logger.info(
                "[PitchReelMigration] Migrated reel %s from %s to %s",
                reel_id,
                existing_url,
                published_media.playback_url,
            )
    finally:
        conn.close()

    logger.info("[PitchReelMigration] Completed. migrated=%d skipped=%d", migrated, skipped)


if __name__ == "__main__":
    run()
