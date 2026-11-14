-- Migration: Add integrations table for third-party service connections
-- Created: 2025-01-20

CREATE TABLE IF NOT EXISTS "public"."integrations" (
    "integration_id" uuid DEFAULT gen_random_uuid() NOT NULL,
    "user_id" uuid DEFAULT auth.uid() NOT NULL,
    "service_id" text NOT NULL,
    "service_name" text NOT NULL,
    "access_token" text,
    "refresh_token" text,
    "expires_at" timestamp with time zone,
    "connected_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now(),
    "metadata" text, -- JSON string for additional service-specific data
    CONSTRAINT "integrations_pkey" PRIMARY KEY ("integration_id"),
    CONSTRAINT "integrations_user_service_unique" UNIQUE ("user_id", "service_id")
);

ALTER TABLE "public"."integrations" OWNER TO "postgres";

COMMENT ON TABLE "public"."integrations" IS 'Stores third-party service integrations for users (OAuth tokens, API keys, etc.)';

COMMENT ON COLUMN "public"."integrations"."service_id" IS 'Unique identifier for the service (e.g., "google", "github", "notion")';
COMMENT ON COLUMN "public"."integrations"."service_name" IS 'Human-readable name of the service (e.g., "Google", "GitHub", "Notion")';
COMMENT ON COLUMN "public"."integrations"."access_token" IS 'OAuth access token (encrypted in production)';
COMMENT ON COLUMN "public"."integrations"."refresh_token" IS 'OAuth refresh token (encrypted in production)';
COMMENT ON COLUMN "public"."integrations"."expires_at" IS 'Token expiration timestamp';
COMMENT ON COLUMN "public"."integrations"."metadata" IS 'Additional service-specific data stored as JSON string';

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS "integrations_user_id_idx" ON "public"."integrations" ("user_id");
CREATE INDEX IF NOT EXISTS "integrations_service_id_idx" ON "public"."integrations" ("service_id");

-- Enable Row Level Security (RLS)
ALTER TABLE "public"."integrations" ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Users can only see their own integrations
CREATE POLICY "Users can view their own integrations"
    ON "public"."integrations"
    FOR SELECT
    USING (auth.uid() = user_id);

-- RLS Policy: Users can insert their own integrations
CREATE POLICY "Users can insert their own integrations"
    ON "public"."integrations"
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- RLS Policy: Users can update their own integrations
CREATE POLICY "Users can update their own integrations"
    ON "public"."integrations"
    FOR UPDATE
    USING (auth.uid() = user_id);

-- RLS Policy: Users can delete their own integrations
CREATE POLICY "Users can delete their own integrations"
    ON "public"."integrations"
    FOR DELETE
    USING (auth.uid() = user_id);

