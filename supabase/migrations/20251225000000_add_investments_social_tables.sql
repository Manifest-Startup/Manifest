-- Migration: Add investments, cap table, social follows, and idea votes tables
-- Created: December 25, 2025

-- Investments table: Track user investments in ideas
CREATE TABLE IF NOT EXISTS "public"."investments" (
    "investment_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone,
    "idea_id" "uuid" NOT NULL,
    "investor_id" "uuid" NOT NULL,
    "cash_amount" numeric DEFAULT 0,
    "sweat_equity_hours" numeric DEFAULT 0,
    "sweat_equity_value" numeric DEFAULT 0,
    "equity_percentage" numeric DEFAULT 0,
    "investment_type" "text" DEFAULT 'cash',
    "role" "text",
    "status" "text" DEFAULT 'pending',
    "notes" "text",
    CONSTRAINT "investments_pkey" PRIMARY KEY ("investment_id"),
    CONSTRAINT "unique_idea_investor" UNIQUE ("idea_id", "investor_id"),
    CONSTRAINT "investments_idea_id_fkey" FOREIGN KEY ("idea_id") REFERENCES "public"."ideas"("idea_id") ON DELETE CASCADE,
    CONSTRAINT "investments_investor_id_fkey" FOREIGN KEY ("investor_id") REFERENCES "public"."users"("user_id") ON DELETE CASCADE
);

COMMENT ON TABLE "public"."investments" IS 'Tracks investments (cash and sweat equity) in ideas';
COMMENT ON COLUMN "public"."investments"."investment_type" IS 'Type: cash, sweat, or both';
COMMENT ON COLUMN "public"."investments"."status" IS 'Status: pending, confirmed, cancelled';

-- Investment contributions: Detailed log of contributions
CREATE TABLE IF NOT EXISTS "public"."investment_contributions" (
    "contribution_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "investment_id" "uuid" NOT NULL,
    "contribution_type" "text" NOT NULL,
    "amount" numeric DEFAULT 0,
    "hours_worked" numeric DEFAULT 0,
    "hourly_rate" numeric DEFAULT 0,
    "description" "text",
    "verified" boolean DEFAULT false,
    CONSTRAINT "investment_contributions_pkey" PRIMARY KEY ("contribution_id"),
    CONSTRAINT "contributions_investment_id_fkey" FOREIGN KEY ("investment_id") REFERENCES "public"."investments"("investment_id") ON DELETE CASCADE
);

COMMENT ON TABLE "public"."investment_contributions" IS 'Detailed contributions for each investment (cash deposits or sweat equity entries)';
COMMENT ON COLUMN "public"."investment_contributions"."contribution_type" IS 'Type: cash or sweat';

-- Cap table entries: Equity ownership snapshot per idea
CREATE TABLE IF NOT EXISTS "public"."cap_table_entries" (
    "entry_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone,
    "idea_id" "uuid" NOT NULL,
    "stakeholder_id" "uuid" NOT NULL,
    "stakeholder_type" "text" DEFAULT 'user',
    "equity_percentage" numeric DEFAULT 0 NOT NULL,
    "shares_owned" numeric DEFAULT 0,
    "share_class" "text" DEFAULT 'common',
    "vesting_status" "text" DEFAULT 'none',
    "vesting_start_date" "date",
    "vesting_end_date" "date",
    "cliff_months" integer DEFAULT 0,
    "vested_percentage" numeric DEFAULT 100,
    "notes" "text",
    CONSTRAINT "cap_table_entries_pkey" PRIMARY KEY ("entry_id"),
    CONSTRAINT "unique_idea_stakeholder" UNIQUE ("idea_id", "stakeholder_id"),
    CONSTRAINT "cap_table_idea_id_fkey" FOREIGN KEY ("idea_id") REFERENCES "public"."ideas"("idea_id") ON DELETE CASCADE,
    CONSTRAINT "cap_table_stakeholder_id_fkey" FOREIGN KEY ("stakeholder_id") REFERENCES "public"."users"("user_id") ON DELETE CASCADE
);

COMMENT ON TABLE "public"."cap_table_entries" IS 'Capitalization table entries showing equity ownership per idea';
COMMENT ON COLUMN "public"."cap_table_entries"."stakeholder_type" IS 'Type: user, company, or pool (for option pools)';
COMMENT ON COLUMN "public"."cap_table_entries"."share_class" IS 'Class: common, preferred, or option';

-- User follows: Social graph for following users
CREATE TABLE IF NOT EXISTS "public"."user_follows" (
    "follow_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "follower_id" "uuid" NOT NULL,
    "followed_id" "uuid" NOT NULL,
    CONSTRAINT "user_follows_pkey" PRIMARY KEY ("follow_id"),
    CONSTRAINT "unique_follow_pair" UNIQUE ("follower_id", "followed_id"),
    CONSTRAINT "follows_follower_id_fkey" FOREIGN KEY ("follower_id") REFERENCES "public"."users"("user_id") ON DELETE CASCADE,
    CONSTRAINT "follows_followed_id_fkey" FOREIGN KEY ("followed_id") REFERENCES "public"."users"("user_id") ON DELETE CASCADE,
    CONSTRAINT "no_self_follow" CHECK ("follower_id" <> "followed_id")
);

COMMENT ON TABLE "public"."user_follows" IS 'Tracks which users follow other users';

-- Idea votes: Upvotes/downvotes on ideas
CREATE TABLE IF NOT EXISTS "public"."idea_votes" (
    "vote_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "idea_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "vote_type" "text" DEFAULT 'upvote' NOT NULL,
    CONSTRAINT "idea_votes_pkey" PRIMARY KEY ("vote_id"),
    CONSTRAINT "unique_idea_user_vote" UNIQUE ("idea_id", "user_id"),
    CONSTRAINT "votes_idea_id_fkey" FOREIGN KEY ("idea_id") REFERENCES "public"."ideas"("idea_id") ON DELETE CASCADE,
    CONSTRAINT "votes_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("user_id") ON DELETE CASCADE
);

COMMENT ON TABLE "public"."idea_votes" IS 'Tracks user votes (upvote/downvote) on ideas';
COMMENT ON COLUMN "public"."idea_votes"."vote_type" IS 'Type: upvote or downvote';

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS "idx_investments_idea_id" ON "public"."investments" ("idea_id");
CREATE INDEX IF NOT EXISTS "idx_investments_investor_id" ON "public"."investments" ("investor_id");
CREATE INDEX IF NOT EXISTS "idx_investments_status" ON "public"."investments" ("status");
CREATE INDEX IF NOT EXISTS "idx_contributions_investment_id" ON "public"."investment_contributions" ("investment_id");
CREATE INDEX IF NOT EXISTS "idx_cap_table_idea_id" ON "public"."cap_table_entries" ("idea_id");
CREATE INDEX IF NOT EXISTS "idx_user_follows_follower" ON "public"."user_follows" ("follower_id");
CREATE INDEX IF NOT EXISTS "idx_user_follows_followed" ON "public"."user_follows" ("followed_id");
CREATE INDEX IF NOT EXISTS "idx_idea_votes_idea" ON "public"."idea_votes" ("idea_id");
CREATE INDEX IF NOT EXISTS "idx_idea_votes_user" ON "public"."idea_votes" ("user_id");

-- Enable RLS on new tables
ALTER TABLE "public"."investments" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."investment_contributions" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."cap_table_entries" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."user_follows" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."idea_votes" ENABLE ROW LEVEL SECURITY;

-- Grant permissions
GRANT ALL ON TABLE "public"."investments" TO "anon";
GRANT ALL ON TABLE "public"."investments" TO "authenticated";
GRANT ALL ON TABLE "public"."investments" TO "service_role";

GRANT ALL ON TABLE "public"."investment_contributions" TO "anon";
GRANT ALL ON TABLE "public"."investment_contributions" TO "authenticated";
GRANT ALL ON TABLE "public"."investment_contributions" TO "service_role";

GRANT ALL ON TABLE "public"."cap_table_entries" TO "anon";
GRANT ALL ON TABLE "public"."cap_table_entries" TO "authenticated";
GRANT ALL ON TABLE "public"."cap_table_entries" TO "service_role";

GRANT ALL ON TABLE "public"."user_follows" TO "anon";
GRANT ALL ON TABLE "public"."user_follows" TO "authenticated";
GRANT ALL ON TABLE "public"."user_follows" TO "service_role";

GRANT ALL ON TABLE "public"."idea_votes" TO "anon";
GRANT ALL ON TABLE "public"."idea_votes" TO "authenticated";
GRANT ALL ON TABLE "public"."idea_votes" TO "service_role";
