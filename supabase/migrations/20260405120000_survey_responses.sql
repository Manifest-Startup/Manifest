-- Customer research and product feedback survey responses (stored as JSONB for flexible questions).

CREATE TABLE IF NOT EXISTS "public"."survey_responses" (
    "response_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "survey_type" text NOT NULL,
    "user_id" text,
    "contact_email" text,
    "answers" jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT "survey_responses_pkey" PRIMARY KEY ("response_id"),
    CONSTRAINT "survey_responses_survey_type_check" CHECK (("survey_type" = ANY (ARRAY['research'::text, 'product_feedback'::text])))
);

COMMENT ON TABLE "public"."survey_responses" IS 'Anonymous or authenticated survey submissions from in-app research and feedback flows.';
COMMENT ON COLUMN "public"."survey_responses"."survey_type" IS 'research = pre-signup; product_feedback = post-use';
COMMENT ON COLUMN "public"."survey_responses"."user_id" IS 'Optional; set when submitter is logged in';
COMMENT ON COLUMN "public"."survey_responses"."answers" IS 'Structured question key -> value (strings, arrays, numbers)';

CREATE INDEX IF NOT EXISTS "idx_survey_responses_type_created"
    ON "public"."survey_responses" USING btree ("survey_type", "created_at" DESC);

ALTER TABLE "public"."survey_responses" ENABLE ROW LEVEL SECURITY;

GRANT ALL ON TABLE "public"."survey_responses" TO "anon";
GRANT ALL ON TABLE "public"."survey_responses" TO "authenticated";
GRANT ALL ON TABLE "public"."survey_responses" TO "service_role";
