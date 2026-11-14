-- Migration: Add pitch reels social tables and seed featured reels
-- Created: March 26, 2026

CREATE TABLE IF NOT EXISTS "public"."pitch_reels" (
    "reel_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "slug" "text" NOT NULL,
    "creator_user_id" "uuid" NOT NULL,
    "idea_id" "uuid",
    "title" "text" NOT NULL,
    "subtitle" "text",
    "thesis" "text",
    "description" "text",
    "creator_role" "text",
    "tags" "jsonb" DEFAULT '[]'::jsonb NOT NULL,
    "video_url" "text" NOT NULL,
    "workspace_path" "text" DEFAULT '/ideas'::text NOT NULL,
    "accent_from" "text" DEFAULT '#09111f'::text NOT NULL,
    "accent_to" "text" DEFAULT '#2f62e8'::text NOT NULL,
    "featured_rank" integer DEFAULT 0 NOT NULL,
    "baseline_like_count" integer DEFAULT 0 NOT NULL,
    "baseline_comment_count" integer DEFAULT 0 NOT NULL,
    "baseline_save_count" integer DEFAULT 0 NOT NULL,
    "baseline_share_count" integer DEFAULT 0 NOT NULL,
    "is_published" boolean DEFAULT true NOT NULL,
    CONSTRAINT "pitch_reels_pkey" PRIMARY KEY ("reel_id"),
    CONSTRAINT "pitch_reels_slug_key" UNIQUE ("slug"),
    CONSTRAINT "pitch_reels_creator_user_id_fkey" FOREIGN KEY ("creator_user_id") REFERENCES "public"."users"("user_id") ON DELETE CASCADE,
    CONSTRAINT "pitch_reels_idea_id_fkey" FOREIGN KEY ("idea_id") REFERENCES "public"."ideas"("idea_id") ON DELETE SET NULL
);

COMMENT ON TABLE "public"."pitch_reels" IS 'Published short-form startup pitch reels shown in the immersive discovery feed.';

CREATE TABLE IF NOT EXISTS "public"."pitch_reel_likes" (
    "like_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "reel_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    CONSTRAINT "pitch_reel_likes_pkey" PRIMARY KEY ("like_id"),
    CONSTRAINT "pitch_reel_likes_unique" UNIQUE ("reel_id", "user_id"),
    CONSTRAINT "pitch_reel_likes_reel_id_fkey" FOREIGN KEY ("reel_id") REFERENCES "public"."pitch_reels"("reel_id") ON DELETE CASCADE,
    CONSTRAINT "pitch_reel_likes_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("user_id") ON DELETE CASCADE
);

COMMENT ON TABLE "public"."pitch_reel_likes" IS 'Tracks user likes on pitch reels.';

CREATE TABLE IF NOT EXISTS "public"."pitch_reel_saves" (
    "save_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "reel_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    CONSTRAINT "pitch_reel_saves_pkey" PRIMARY KEY ("save_id"),
    CONSTRAINT "pitch_reel_saves_unique" UNIQUE ("reel_id", "user_id"),
    CONSTRAINT "pitch_reel_saves_reel_id_fkey" FOREIGN KEY ("reel_id") REFERENCES "public"."pitch_reels"("reel_id") ON DELETE CASCADE,
    CONSTRAINT "pitch_reel_saves_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("user_id") ON DELETE CASCADE
);

COMMENT ON TABLE "public"."pitch_reel_saves" IS 'Tracks user saves/bookmarks on pitch reels.';

CREATE TABLE IF NOT EXISTS "public"."pitch_reel_share_events" (
    "share_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "reel_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    CONSTRAINT "pitch_reel_share_events_pkey" PRIMARY KEY ("share_id"),
    CONSTRAINT "pitch_reel_share_events_reel_id_fkey" FOREIGN KEY ("reel_id") REFERENCES "public"."pitch_reels"("reel_id") ON DELETE CASCADE,
    CONSTRAINT "pitch_reel_share_events_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("user_id") ON DELETE CASCADE
);

COMMENT ON TABLE "public"."pitch_reel_share_events" IS 'Append-only share events for pitch reels.';

CREATE TABLE IF NOT EXISTS "public"."pitch_reel_comments" (
    "comment_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "reel_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "parent_comment_id" "uuid",
    "body" "text" NOT NULL,
    CONSTRAINT "pitch_reel_comments_pkey" PRIMARY KEY ("comment_id"),
    CONSTRAINT "pitch_reel_comments_reel_id_fkey" FOREIGN KEY ("reel_id") REFERENCES "public"."pitch_reels"("reel_id") ON DELETE CASCADE,
    CONSTRAINT "pitch_reel_comments_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("user_id") ON DELETE CASCADE,
    CONSTRAINT "pitch_reel_comments_parent_comment_id_fkey" FOREIGN KEY ("parent_comment_id") REFERENCES "public"."pitch_reel_comments"("comment_id") ON DELETE CASCADE
);

COMMENT ON TABLE "public"."pitch_reel_comments" IS 'Thread-capable comments for pitch reels.';

CREATE INDEX IF NOT EXISTS "idx_pitch_reels_published_rank" ON "public"."pitch_reels" ("is_published", "featured_rank" DESC, "created_at" DESC);
CREATE INDEX IF NOT EXISTS "idx_pitch_reels_creator" ON "public"."pitch_reels" ("creator_user_id");
CREATE INDEX IF NOT EXISTS "idx_pitch_reel_likes_reel" ON "public"."pitch_reel_likes" ("reel_id");
CREATE INDEX IF NOT EXISTS "idx_pitch_reel_likes_user" ON "public"."pitch_reel_likes" ("user_id");
CREATE INDEX IF NOT EXISTS "idx_pitch_reel_saves_reel" ON "public"."pitch_reel_saves" ("reel_id");
CREATE INDEX IF NOT EXISTS "idx_pitch_reel_saves_user" ON "public"."pitch_reel_saves" ("user_id");
CREATE INDEX IF NOT EXISTS "idx_pitch_reel_share_events_reel" ON "public"."pitch_reel_share_events" ("reel_id");
CREATE INDEX IF NOT EXISTS "idx_pitch_reel_comments_reel_created" ON "public"."pitch_reel_comments" ("reel_id", "created_at");

ALTER TABLE "public"."pitch_reels" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."pitch_reel_likes" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."pitch_reel_saves" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."pitch_reel_share_events" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."pitch_reel_comments" ENABLE ROW LEVEL SECURITY;

GRANT ALL ON TABLE "public"."pitch_reels" TO "anon";
GRANT ALL ON TABLE "public"."pitch_reels" TO "authenticated";
GRANT ALL ON TABLE "public"."pitch_reels" TO "service_role";

GRANT ALL ON TABLE "public"."pitch_reel_likes" TO "anon";
GRANT ALL ON TABLE "public"."pitch_reel_likes" TO "authenticated";
GRANT ALL ON TABLE "public"."pitch_reel_likes" TO "service_role";

GRANT ALL ON TABLE "public"."pitch_reel_saves" TO "anon";
GRANT ALL ON TABLE "public"."pitch_reel_saves" TO "authenticated";
GRANT ALL ON TABLE "public"."pitch_reel_saves" TO "service_role";

GRANT ALL ON TABLE "public"."pitch_reel_share_events" TO "anon";
GRANT ALL ON TABLE "public"."pitch_reel_share_events" TO "authenticated";
GRANT ALL ON TABLE "public"."pitch_reel_share_events" TO "service_role";

GRANT ALL ON TABLE "public"."pitch_reel_comments" TO "anon";
GRANT ALL ON TABLE "public"."pitch_reel_comments" TO "authenticated";
GRANT ALL ON TABLE "public"."pitch_reel_comments" TO "service_role";

INSERT INTO "public"."users" ("user_id", "email", "username", "first_name", "last_name", "created_at", "updated_at")
VALUES
    ('00000000-0000-0000-0000-00000000a101', 'manifest.lab@manifeststartup.com', 'manifestlab', 'Manifest', 'Lab', now(), now()),
    ('00000000-0000-0000-0000-00000000a102', 'operator.desk@manifeststartup.com', 'operatordesk', 'Operator', 'Desk', now(), now()),
    ('00000000-0000-0000-0000-00000000a103', 'fintech.hq@manifeststartup.com', 'fintechhq', 'Fintech', 'HQ', now(), now())
ON CONFLICT ("user_id") DO NOTHING;

INSERT INTO "public"."pitch_reels" (
    "reel_id",
    "slug",
    "creator_user_id",
    "title",
    "subtitle",
    "thesis",
    "description",
    "creator_role",
    "tags",
    "video_url",
    "workspace_path",
    "accent_from",
    "accent_to",
    "featured_rank",
    "baseline_like_count",
    "baseline_comment_count",
    "baseline_save_count",
    "baseline_share_count",
    "is_published",
    "created_at",
    "updated_at"
) VALUES
    (
        '00000000-0000-0000-0000-00000000b201',
        'aqua-chain',
        '00000000-0000-0000-0000-00000000a101',
        'AquaChain',
        'Audit-ready water quality monitoring for utilities and field teams.',
        'Sensors, verification, and chain-of-custody records in one operating layer.',
        'AquaChain brings IoT telemetry, lab validation, and compliance reporting into a single founder-ready workflow.',
        'Climate + infrastructure',
        '["Climate", "IoT", "B2B"]'::jsonb,
        '/videos/founders-video.mov',
        '/ideas',
        '#09111f',
        '#2f62e8',
        300,
        1280,
        16,
        312,
        94,
        true,
        now(),
        now()
    ),
    (
        '00000000-0000-0000-0000-00000000b202',
        'dorm-grader',
        '00000000-0000-0000-0000-00000000a102',
        'DormGrader',
        'Housing quality intelligence for students before they sign.',
        'A trust layer for reviews, maintenance history, and move-in risk scoring.',
        'DormGrader turns scattered student anecdotes into a reliable decision system for campus housing and off-campus rentals.',
        'Consumer + education',
        '["Consumer", "Marketplace", "Trust"]'::jsonb,
        '/videos/tutorial.mov',
        '/ideas',
        '#18181b',
        '#f59e0b',
        200,
        870,
        7,
        164,
        52,
        true,
        now(),
        now()
    ),
    (
        '00000000-0000-0000-0000-00000000b203',
        'one-card',
        '00000000-0000-0000-0000-00000000a103',
        'OneCard OS',
        'One control layer for credit usage, alerts, and financial clarity.',
        'A cleaner operating system for card management, behavior design, and founder cash discipline.',
        'OneCard OS replaces fragmented card portals with one product surface for teams that want tighter financial control.',
        'Fintech + workflow',
        '["Fintech", "SaaS", "Ops"]'::jsonb,
        '/videos/tutorial.mov',
        '/ideas',
        '#0f172a',
        '#14b8a6',
        100,
        1460,
        21,
        401,
        118,
        true,
        now(),
        now()
    )
ON CONFLICT ("slug") DO NOTHING;

INSERT INTO "public"."pitch_reel_comments" ("comment_id", "reel_id", "user_id", "body", "created_at", "updated_at")
VALUES
    (
        '00000000-0000-0000-0000-00000000c301',
        '00000000-0000-0000-0000-00000000b201',
        '00000000-0000-0000-0000-00000000a102',
        'The compliance workflow feels especially strong here. I would love to see how lab verification gets surfaced for operators.',
        now() - interval '3 days',
        now() - interval '3 days'
    ),
    (
        '00000000-0000-0000-0000-00000000c302',
        '00000000-0000-0000-0000-00000000b201',
        '00000000-0000-0000-0000-00000000a103',
        'This is the kind of infrastructure product where clear ROI math could make the pitch really compelling.',
        now() - interval '2 days',
        now() - interval '2 days'
    ),
    (
        '00000000-0000-0000-0000-00000000c303',
        '00000000-0000-0000-0000-00000000b202',
        '00000000-0000-0000-0000-00000000a101',
        'Parents and students would both use this if the maintenance history becomes trustworthy and hard to game.',
        now() - interval '4 days',
        now() - interval '4 days'
    ),
    (
        '00000000-0000-0000-0000-00000000c304',
        '00000000-0000-0000-0000-00000000b202',
        '00000000-0000-0000-0000-00000000a103',
        'The wedge into off-campus rentals feels practical. The review moderation model will matter a lot.',
        now() - interval '1 day',
        now() - interval '1 day'
    ),
    (
        '00000000-0000-0000-0000-00000000c305',
        '00000000-0000-0000-0000-00000000b203',
        '00000000-0000-0000-0000-00000000a101',
        'The cash-discipline angle is smart. Teams usually stitch together alerts from too many portals.',
        now() - interval '5 days',
        now() - interval '5 days'
    ),
    (
        '00000000-0000-0000-0000-00000000c306',
        '00000000-0000-0000-0000-00000000b203',
        '00000000-0000-0000-0000-00000000a102',
        'Would be interesting to pair this with policy controls and recurring spend intelligence for finance leads.',
        now() - interval '2 days',
        now() - interval '2 days'
    )
ON CONFLICT ("comment_id") DO NOTHING;
