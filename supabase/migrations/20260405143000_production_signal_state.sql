-- Rolling counters for production anomaly signals (deduped fingerprints; backend-only).

CREATE TABLE IF NOT EXISTS "public"."production_signal_state" (
    "fingerprint" text NOT NULL,
    "window_start" timestamp with time zone NOT NULL,
    "event_count" integer DEFAULT 0 NOT NULL,
    "github_issue_number" integer,
    "github_repo" text,
    "last_issue_window_start" timestamp with time zone,
    "last_sample" text,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT "production_signal_state_pkey" PRIMARY KEY ("fingerprint")
);

COMMENT ON TABLE "public"."production_signal_state" IS 'Per-fingerprint rolling window counts for production signal → GitHub issue automation (internal).';

CREATE INDEX IF NOT EXISTS "idx_production_signal_state_updated"
    ON "public"."production_signal_state" USING btree ("updated_at" DESC);

ALTER TABLE "public"."production_signal_state" ENABLE ROW LEVEL SECURITY;

GRANT ALL ON TABLE "public"."production_signal_state" TO "service_role";
