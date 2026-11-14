-- Messaging System Tables for Manifest
-- Supports encrypted messaging between users for startup collaboration

-- Conversations table - stores metadata about chat threads
CREATE TABLE IF NOT EXISTS "public"."conversations" (
    "conversation_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "participant_1" "uuid" NOT NULL,
    "participant_2" "uuid" NOT NULL,
    "idea_id" "uuid",
    "last_message_at" timestamp with time zone DEFAULT "now"(),
    "last_message_preview" "text",
    "participant_1_unread_count" integer DEFAULT 0,
    "participant_2_unread_count" integer DEFAULT 0,
    CONSTRAINT "conversations_pkey" PRIMARY KEY ("conversation_id"),
    CONSTRAINT "conversations_unique_participants" UNIQUE ("participant_1", "participant_2", "idea_id"),
    CONSTRAINT "conversations_participant_1_fkey" FOREIGN KEY ("participant_1") REFERENCES "public"."users"("user_id") ON DELETE CASCADE,
    CONSTRAINT "conversations_participant_2_fkey" FOREIGN KEY ("participant_2") REFERENCES "public"."users"("user_id") ON DELETE CASCADE,
    CONSTRAINT "conversations_idea_id_fkey" FOREIGN KEY ("idea_id") REFERENCES "public"."ideas"("idea_id") ON DELETE SET NULL
);

ALTER TABLE "public"."conversations" OWNER TO "postgres";

COMMENT ON TABLE "public"."conversations" IS 'Stores conversation threads between users for startup collaboration.';

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS "idx_conversations_participant_1" ON "public"."conversations" ("participant_1");
CREATE INDEX IF NOT EXISTS "idx_conversations_participant_2" ON "public"."conversations" ("participant_2");
CREATE INDEX IF NOT EXISTS "idx_conversations_last_message_at" ON "public"."conversations" ("last_message_at" DESC);
CREATE INDEX IF NOT EXISTS "idx_conversations_idea_id" ON "public"."conversations" ("idea_id");

-- Messages table - stores individual messages (content is encrypted client-side)
CREATE TABLE IF NOT EXISTS "public"."messages" (
    "message_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "conversation_id" "uuid" NOT NULL,
    "sender_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "content" "text" NOT NULL,
    "is_encrypted" boolean DEFAULT true,
    "encryption_version" integer DEFAULT 1,
    "is_read" boolean DEFAULT false,
    "read_at" timestamp with time zone,
    "message_type" "text" DEFAULT 'text',
    "metadata" "jsonb",
    CONSTRAINT "messages_pkey" PRIMARY KEY ("message_id"),
    CONSTRAINT "messages_conversation_id_fkey" FOREIGN KEY ("conversation_id") REFERENCES "public"."conversations"("conversation_id") ON DELETE CASCADE,
    CONSTRAINT "messages_sender_id_fkey" FOREIGN KEY ("sender_id") REFERENCES "public"."users"("user_id") ON DELETE CASCADE
);

ALTER TABLE "public"."messages" OWNER TO "postgres";

COMMENT ON TABLE "public"."messages" IS 'Encrypted messages between users. Content is encrypted client-side for privacy.';
COMMENT ON COLUMN "public"."messages"."content" IS 'Message content - encrypted client-side for end-to-end encryption.';
COMMENT ON COLUMN "public"."messages"."message_type" IS 'Type of message: text, sweat_equity_offer, investment_proposal, etc.';
COMMENT ON COLUMN "public"."messages"."metadata" IS 'Additional data like deal terms, attachments, etc.';

-- Create indexes for faster message retrieval
CREATE INDEX IF NOT EXISTS "idx_messages_conversation_id" ON "public"."messages" ("conversation_id");
CREATE INDEX IF NOT EXISTS "idx_messages_created_at" ON "public"."messages" ("created_at" DESC);
CREATE INDEX IF NOT EXISTS "idx_messages_sender_id" ON "public"."messages" ("sender_id");
CREATE INDEX IF NOT EXISTS "idx_messages_unread" ON "public"."messages" ("conversation_id", "is_read") WHERE is_read = false;

-- User encryption keys table - stores public keys for E2E encryption
CREATE TABLE IF NOT EXISTS "public"."user_encryption_keys" (
    "key_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "public_key" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "is_active" boolean DEFAULT true,
    CONSTRAINT "user_encryption_keys_pkey" PRIMARY KEY ("key_id"),
    CONSTRAINT "user_encryption_keys_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("user_id") ON DELETE CASCADE,
    CONSTRAINT "user_encryption_keys_user_id_unique" UNIQUE ("user_id")
);

ALTER TABLE "public"."user_encryption_keys" OWNER TO "postgres";

COMMENT ON TABLE "public"."user_encryption_keys" IS 'Stores user public keys for end-to-end message encryption.';

CREATE INDEX IF NOT EXISTS "idx_user_encryption_keys_user_id" ON "public"."user_encryption_keys" ("user_id");

-- Function to update conversation timestamp on new message
CREATE OR REPLACE FUNCTION "public"."update_conversation_on_message"()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE "public"."conversations"
    SET 
        "last_message_at" = NEW."created_at",
        "last_message_preview" = LEFT(NEW."content", 100),
        "updated_at" = NOW()
    WHERE "conversation_id" = NEW."conversation_id";
    
    -- Update unread count for recipient
    IF (SELECT "participant_1" FROM "public"."conversations" WHERE "conversation_id" = NEW."conversation_id") = NEW."sender_id" THEN
        UPDATE "public"."conversations"
        SET "participant_2_unread_count" = "participant_2_unread_count" + 1
        WHERE "conversation_id" = NEW."conversation_id";
    ELSE
        UPDATE "public"."conversations"
        SET "participant_1_unread_count" = "participant_1_unread_count" + 1
        WHERE "conversation_id" = NEW."conversation_id";
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update conversation on new message
DROP TRIGGER IF EXISTS "trigger_update_conversation_on_message" ON "public"."messages";
CREATE TRIGGER "trigger_update_conversation_on_message"
    AFTER INSERT ON "public"."messages"
    FOR EACH ROW
    EXECUTE FUNCTION "public"."update_conversation_on_message"();

-- Enable Row Level Security
ALTER TABLE "public"."conversations" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."messages" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."user_encryption_keys" ENABLE ROW LEVEL SECURITY;

-- RLS Policies for conversations
CREATE POLICY "Users can view their own conversations" ON "public"."conversations"
    FOR SELECT USING (
        auth.uid() = participant_1 OR auth.uid() = participant_2
    );

CREATE POLICY "Users can insert conversations they are part of" ON "public"."conversations"
    FOR INSERT WITH CHECK (
        auth.uid() = participant_1 OR auth.uid() = participant_2
    );

CREATE POLICY "Users can update their own conversations" ON "public"."conversations"
    FOR UPDATE USING (
        auth.uid() = participant_1 OR auth.uid() = participant_2
    );

-- RLS Policies for messages
CREATE POLICY "Users can view messages in their conversations" ON "public"."messages"
    FOR SELECT USING (
        conversation_id IN (
            SELECT conversation_id FROM "public"."conversations"
            WHERE participant_1 = auth.uid() OR participant_2 = auth.uid()
        )
    );

CREATE POLICY "Users can insert messages in their conversations" ON "public"."messages"
    FOR INSERT WITH CHECK (
        sender_id = auth.uid() AND
        conversation_id IN (
            SELECT conversation_id FROM "public"."conversations"
            WHERE participant_1 = auth.uid() OR participant_2 = auth.uid()
        )
    );

CREATE POLICY "Users can update their own messages" ON "public"."messages"
    FOR UPDATE USING (
        sender_id = auth.uid()
    );

-- RLS Policies for encryption keys
CREATE POLICY "Users can view any public key" ON "public"."user_encryption_keys"
    FOR SELECT USING (true);

CREATE POLICY "Users can manage their own keys" ON "public"."user_encryption_keys"
    FOR ALL USING (auth.uid() = user_id);
