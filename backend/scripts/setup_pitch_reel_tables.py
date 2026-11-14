"""
Setup Pitch Reel Database Tables

Creates the necessary tables for the pitch reels feed and its social interactions.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import get_db_connection
from app.utils.logger import logger


def setup_pitch_reel_tables():
    """Create all pitch reel related tables."""

    with get_db_connection() as conn:
        cursor = conn.cursor()

        logger.info("Creating pitch_reels table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pitch_reels (
                reel_id UUID PRIMARY KEY,
                slug VARCHAR(255) NOT NULL UNIQUE,
                creator_user_id UUID NOT NULL,
                idea_id UUID,
                title TEXT NOT NULL,
                subtitle TEXT,
                thesis TEXT,
                description TEXT,
                creator_role VARCHAR(255),
                tags JSONB DEFAULT '[]'::jsonb,
                video_url TEXT,
                workspace_path TEXT,
                accent_from VARCHAR(50),
                accent_to VARCHAR(50),
                featured_rank INTEGER DEFAULT 0,
                baseline_like_count INTEGER DEFAULT 0,
                baseline_comment_count INTEGER DEFAULT 0,
                baseline_save_count INTEGER DEFAULT 0,
                baseline_share_count INTEGER DEFAULT 0,
                is_published BOOLEAN DEFAULT FALSE,
                video_status VARCHAR(50),
                video_generation_error TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_pitch_reels_creator_user_id ON pitch_reels(creator_user_id);
            CREATE INDEX IF NOT EXISTS idx_pitch_reels_is_published ON pitch_reels(is_published);
            CREATE INDEX IF NOT EXISTS idx_pitch_reels_featured_rank ON pitch_reels(featured_rank DESC);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pitch_reels_idea_id_unique ON pitch_reels(idea_id) WHERE idea_id IS NOT NULL;
        """)

        logger.info("Creating pitch_reel_likes table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pitch_reel_likes (
                like_id UUID PRIMARY KEY,
                reel_id UUID NOT NULL REFERENCES pitch_reels(reel_id) ON DELETE CASCADE,
                user_id UUID NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(reel_id, user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_pitch_reel_likes_reel_id ON pitch_reel_likes(reel_id);
            CREATE INDEX IF NOT EXISTS idx_pitch_reel_likes_user_id ON pitch_reel_likes(user_id);
        """)

        logger.info("Creating pitch_reel_saves table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pitch_reel_saves (
                save_id UUID PRIMARY KEY,
                reel_id UUID NOT NULL REFERENCES pitch_reels(reel_id) ON DELETE CASCADE,
                user_id UUID NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(reel_id, user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_pitch_reel_saves_reel_id ON pitch_reel_saves(reel_id);
            CREATE INDEX IF NOT EXISTS idx_pitch_reel_saves_user_id ON pitch_reel_saves(user_id);
        """)

        logger.info("Creating pitch_reel_share_events table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pitch_reel_share_events (
                share_id UUID PRIMARY KEY,
                reel_id UUID NOT NULL REFERENCES pitch_reels(reel_id) ON DELETE CASCADE,
                user_id UUID NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_pitch_reel_share_events_reel_id ON pitch_reel_share_events(reel_id);
            CREATE INDEX IF NOT EXISTS idx_pitch_reel_share_events_user_id ON pitch_reel_share_events(user_id);
        """)

        logger.info("Creating pitch_reel_comments table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pitch_reel_comments (
                comment_id UUID PRIMARY KEY,
                reel_id UUID NOT NULL REFERENCES pitch_reels(reel_id) ON DELETE CASCADE,
                user_id UUID NOT NULL,
                body TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_pitch_reel_comments_reel_id ON pitch_reel_comments(reel_id);
            CREATE INDEX IF NOT EXISTS idx_pitch_reel_comments_user_id ON pitch_reel_comments(user_id);
            CREATE INDEX IF NOT EXISTS idx_pitch_reel_comments_created_at ON pitch_reel_comments(created_at);
        """)

        conn.commit()
        logger.info("All pitch reel tables created successfully!")


if __name__ == "__main__":
    setup_pitch_reel_tables()
