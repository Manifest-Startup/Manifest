"""
Migration: add video_data BYTEA column to pitch_reels table.
Run once: python backend/scripts/add_pitch_reel_video_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import create_database_client
from app.utils.logger import logger


def run() -> None:
    db = create_database_client()

    raw = db.postgrest.session if hasattr(db, "postgrest") else None

    import os
    import psycopg2

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        ALTER TABLE pitch_reels
        ADD COLUMN IF NOT EXISTS video_data BYTEA;
    """)
    logger.info("video_data column added (or already existed).")

    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
