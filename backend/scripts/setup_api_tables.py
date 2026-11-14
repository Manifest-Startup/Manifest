"""
Setup API Access Database Tables

Creates the necessary tables for API key management, usage tracking, and billing.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import get_db_connection
from app.utils.logger import logger


def setup_api_tables():
    """Create all API-related tables."""
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        logger.info("Creating api_clients table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_clients (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL,
                name VARCHAR(255) NOT NULL,
                tier VARCHAR(50) DEFAULT 'free',
                status VARCHAR(50) DEFAULT 'active',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                last_used_at TIMESTAMP WITH TIME ZONE,
                metadata JSONB DEFAULT '{}'::jsonb
            );
            
            CREATE INDEX IF NOT EXISTS idx_api_clients_user_id ON api_clients(user_id);
            CREATE INDEX IF NOT EXISTS idx_api_clients_status ON api_clients(status);
        """)
        
        logger.info("Creating api_keys table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES api_clients(id) ON DELETE CASCADE,
                name VARCHAR(255) DEFAULT 'Default Key',
                key_prefix VARCHAR(20) NOT NULL,
                key_hash VARCHAR(64) NOT NULL,
                status VARCHAR(50) DEFAULT 'active',
                expires_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                last_used_at TIMESTAMP WITH TIME ZONE,
                revoked_at TIMESTAMP WITH TIME ZONE,
                UNIQUE(key_prefix, key_hash)
            );
            
            CREATE INDEX IF NOT EXISTS idx_api_keys_client_id ON api_keys(client_id);
            CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);
            CREATE INDEX IF NOT EXISTS idx_api_keys_status ON api_keys(status);
        """)
        
        logger.info("Creating api_usage_events table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_usage_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES api_clients(id) ON DELETE CASCADE,
                key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL,
                endpoint VARCHAR(255) NOT NULL,
                response_code INTEGER NOT NULL,
                latency_ms INTEGER,
                tokens_used INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                metadata JSONB DEFAULT '{}'::jsonb
            );
            
            CREATE INDEX IF NOT EXISTS idx_api_usage_events_client_id ON api_usage_events(client_id);
            CREATE INDEX IF NOT EXISTS idx_api_usage_events_created_at ON api_usage_events(created_at);
        """)
        
        logger.info("Creating api_usage_daily table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_usage_daily (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES api_clients(id) ON DELETE CASCADE,
                date DATE NOT NULL,
                request_count INTEGER DEFAULT 0,
                tokens_used INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(client_id, date)
            );
            
            CREATE INDEX IF NOT EXISTS idx_api_usage_daily_client_id ON api_usage_daily(client_id);
            CREATE INDEX IF NOT EXISTS idx_api_usage_daily_date ON api_usage_daily(date);
        """)
        
        logger.info("All API tables created successfully!")


if __name__ == "__main__":
    setup_api_tables()
