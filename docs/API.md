# Manifest API Reference

Last verified against code on **May 3, 2026**.

Primary source files:

- `backend/app/main.py`
- `backend/app/graphql/schema.py`
- `backend/app/routes/api_v1_routes.py`
- `backend/app/routes/api_keys_routes.py`
- `backend/app/routes/privacy_routes.py`
- `backend/app/routes/survey_ops_routes.py`
- `backend/app/routes/website_testing_routes.py`
- `backend/app/routes/ops_internal_routes.py`
- `backend/app/routes/voice_agent_routes.py`
- `backend/app/routes/dependencies.py`
- `backend/app/services/compliance/privacy_consent.py`

## API Surfaces

Manifest exposes multiple interfaces:

1. GraphQL (primary app API)
- Endpoint: `POST /graphql`
- Transport: JSON body with `query` and optional `variables`

2. Public REST API (API key based)
- Prefix: `/api/v1`
- Auth: `Authorization: Bearer manifest_sk_...`

3. API key management REST (session/JWT based)
- Prefix: `/api/keys`
- Auth: app session (`access_token` cookie or bearer JWT)

4. Voice agent REST (session/JWT based)
- Prefix: `/api/voice-agent`
- Auth: app session (`access_token` cookie or bearer JWT)

5. Contact route (currently inactive)
- Route exists in code (`backend/app/routes/customer_routes.py`) as `POST /api/contact`
- Current runtime status: router is not mounted in `backend/app/main.py`, so this endpoint is not active

6. Privacy preferences REST
- Prefix: `/api/privacy`
- Auth: optional; the same endpoints work for anonymous browsers and signed-in users

7. Manifest CLI sign-in
- Prefix: `/api/cli` (browser approval + token exchange, below)
- The `manifest` CLI ([CLI.md](CLI.md)) wraps every GraphQL operation and the user REST routes with `Authorization: Bearer <cli session>`

## Authentication

Two auth mechanisms are used in this codebase.

### Session/JWT auth

Used by GraphQL resolvers and most app REST routes.

Accepted token locations (`backend/app/auth/current_user.py`):

- `session_token` cookie
- `access_token` cookie
- `Authorization: Bearer <jwt>` header

Bearer tokens and cookies are interchangeable: GraphQL and every session REST route accept either (the cookie wins if both are sent). The Manifest CLI uses `Authorization: Bearer` with a CLI session (below).

Browsers get the session cookie only from **Continue with Open Media** (`/api/auth/open-media/*`, below; [ADR 0002](adr/0002-open-media-is-the-only-sign-in.md)). There is no password login, registration, password reset or Manifest MFA: passkeys, passwords and second factors live in Open Media. Scripts and agents use API keys.

If `DATABASE_URL` is not configured and `DEMO_MODE` is not explicitly set to false, demo mode auto-enables, and `GET /api/auth/open-media/start` signs in the demo user (`hello@manifeststartup.com`) without contacting Open Media.

Sensitive REST routes (API key create/rotate/revoke, DSAR erase/export) need a recent sign-in: if the session is older than 5 minutes they answer `401` with `X-Step-Up-Required: 1`, and the client sends the person through Continue with Open Media again.

### Sign in with Open Media (REST, browser navigation)

- `GET /api/auth/open-media/start?next=/ideas[&login_hint=email]` — no session needed. Sets a 10-minute signed, HttpOnly, SameSite=Lax cookie `manifest_om_signin` (path `/api/auth/open-media`) and redirects (303) to Open Media `/authorize` with `client_id=https://manifeststartup.com/oauth/open-media-client.json`, `scope=account`, PKCE `S256`, `login_hint` (the account email when a signed-in user reconnects) and a signed `state` holding the nonce, a safe `next` path, the guest user to merge (if a guest started it) and the signed-in user (if reconnecting). `next` must be a same-origin path; anything else becomes `/ideas`.
- `GET /api/auth/open-media/callback?code&state` — checks `state` against the cookie (once, within 10 minutes), exchanges the code at `/oauth/token`, reads `GET /v1/connected/me` (`id`, `handle`, `email`, `email_verified`, `has_profile`), then picks the Manifest user: the account already linked to that Open Media id; else the signed-in account that started a reconnect; else a non-guest account whose email equals the **verified** Open Media email (case-insensitive, auto-link); else a new full account. It stores the encrypted tokens in `integrations` (`service_id = open_media`), merges the browser's guest workspace into the account, sets the `session_token` cookie, resumes reels waiting in `needs_open_media`, and redirects (303) to `next` (with `?merged=N` when guest ideas moved). Failures redirect to `/login?error=<code>`: `cancelled`, `failed`, `invalid_state` (missing/mismatched cookie or tampered state), `expired`, `replayed`, `unverified_email`, `no_email` (nothing is created for either), `linked_elsewhere`, `account_disabled`.
- `POST /api/auth/logout` — revokes the current session and clears the auth cookies; returns `{"ok": true}`.

```bash
# Start a sign-in (prints the Open Media authorize URL and the nonce cookie)
curl -si "http://localhost:8000/api/auth/open-media/start?next=/ideas" | grep -i -E "^(location|set-cookie):"
```

### Manifest CLI sign-in (REST, browser + CLI)

Loopback redirect + PKCE ([ADR 0003](adr/0003-manifest-cli-browser-login.md), `backend/app/routes/cli_auth_routes.py`). `manifest login` does all of this for you.

- `GET /api/cli/authorize?redirect_uri=http://127.0.0.1:<port>/callback&state=<8-256 url-safe chars>&code_challenge=<S256>&code_challenge_method=S256` — browser navigation. `redirect_uri` must be `http://127.0.0.1:<port>/callback` or `http://localhost:<port>/callback`; invalid parameters get a 400 page (never a redirect). No session, a guest session, or a CLI token → `303 /login?next=/api/cli/authorize?…` (Continue with Open Media, then back). A session whose sign-in (`auth_iat`) is older than 5 minutes → `303 /api/auth/open-media/start?next=<this URL>&reauth=1` for a fresh sign-in; with `reauth=1` already set and still stale, a 401 page (no loop). Otherwise a `no-store`, non-frameable page "Allow Manifest CLI on this computer?"; **Allow** (`&confirm=<session-bound HMAC>`) redirects `303` to `redirect_uri?code=<one-time code>&state=<state>`, **Cancel** (`&deny=1`) to `redirect_uri?error=access_denied&state=<state>`. The code expires after 2 minutes and works once.
- `POST /api/cli/token` — JSON `{"code", "code_verifier", "redirect_uri", "hostname"}`. Checks the code, PKCE verifier and redirect URI; refuses guests (`403 access_denied`) and codes whose approving browser session has been signed out. Returns `{"access_token", "token_type": "Bearer", "expires_at", "label": "Manifest CLI · <hostname>", "user": {"user_id", "email"}}`: a revocable session JWT (`kind: "cli"`, 30 days, 14-day idle timeout, `CLI_SESSION_TTL_DAYS` / `CLI_SESSION_IDLE_TIMEOUT_SECONDS`). Errors are `400 {"error": "invalid_request" | "invalid_grant", "error_description"}`. No refresh token: sign in again when it expires.
- Revoke with `POST /api/auth/logout` and the bearer token (what `manifest logout` does), from Account → Security → Active sessions (`mySessions` returns `kind: "cli"` with the label in `userAgent`), or with `revokeAccountSession` / `revokeOtherAccountSessions`.

```bash
manifest login --base-url http://localhost:8000 && manifest whoami
curl -s -X POST http://localhost:8000/graphql -H "Authorization: Bearer $(jq -r .token ~/.config/manifest/cli.json)" \
  -H "Content-Type: application/json" -d '{"query":"{ mySessions { kind userAgent current } }"}'
```

### API key auth

Used by `/api/v1/*`.

Header format:

```http
Authorization: Bearer manifest_sk_xxx
```

## GraphQL: Main Domains

The schema is implemented in `backend/app/graphql/schema.py`.

### AI keys (bring your own key)

Every AI feature runs on the signed-in customer's own OpenAI API key.

- `aiKeyStatus` → `{ configured, source, last4 }`, where `source` is `user`, `platform` (an operator `OPENAI_API_KEY` fallback, used for local development only) or `none`.
- `saveOpenaiApiKey(apiKey)` checks the key with OpenAI, encrypts it with the user's tenant data key and stores it (`integrations.service_id = 'openai'`, ciphertext only). Malformed or rejected keys return a readable error.
- `removeOpenaiApiKey` deletes the stored key.
- An AI request made without a key fails with a message that starts with "Add your OpenAI API key". The web app turns that message into a banner linking to `/account#ai-key`.

### Query operations

Core:

- `me`
- `profile`
- `account`
- `mySessions` — the caller's sessions (`sessionId`, `current`, timestamps, `requestIp`, `userAgent`, `kind`). `kind` is `browser` or `cli`; a CLI session's `userAgent` is its label, `Manifest CLI · <hostname>`.
- `ideas(first: Int = 100, after: String)` — lightweight `IdeaSummary` rows for the workspace sidebar; ordered by `created_at` DESC; capped at 200 per page. `after` is an opaque cursor from the previous page (base64 JSON of `{created_at, idea_id}`). List queries read denormalized `generated_asset_count` / `has_description` columns and **do not** load multi-MB document blobs.
- `idea(ideaId)`

Documents:

- `pitchDeck(ideaId)`
- `productRequirementsDocument(ideaId)`
- `provisionalPatent(ideaId)`
- `findSimilarIdeas(ideaDescription)`

Idea qualification (pre-build conversational agent):

- `ideaQualificationSession(sessionId)` — returns the in-progress or completed session (transcript, extracted fields, next question, score). Returns `null` if the session is not owned by the caller.
- `myIdeaQualificationSessions` — list view of the caller's own sessions, newest first (id, status, turnCount, qualificationScore, timestamps).

Cost tracking + billing dashboard:

- `myCostDashboard` — single-call payload powering `/account/billing`: current month's spend with by-agent + by-model breakdowns, remaining USD against the cap, % of cap, warning level (`ok` / `elevated` / `critical` / `over`), 20 most-recent agent runs, base subscription + estimated total. Permission: `account.read`. See `docs/COST_TRACKING.md`.
- `myAgentRuns(limit: Int)` — recent `agent_runs` rows for the caller (default 20, max 100). Permission: `account.read`.

Integrations:

- `integrations`
- `integration(serviceId)`

Social and investing:

- `publicIdeasFeed(limit, offset)`
- `userFollowers(userId)`
- `userFollowing(userId)`
- `userSocialStats(userId)`
- `ideaInvestments(ideaId)`
- `ideaCapTable(ideaId)`
- `myPortfolio`
- `calculateSweatEquity(hours, hourlyRate, totalValuation)`
- `surveyInsights(windowDays)` — aggregate discovery + product-feedback signals used by the Account settings insight panel
- `privacyStatus` — retention and deletion status used by the Account privacy panel; optional analytics and outreach preferences are saved through `/api/privacy/consent`

Open Media (messages and pitch shorts run on the user's linked [Open Media](https://openmedia.site) account; see [ADR 0001](adr/0001-open-media-for-messages-and-pitch-shorts.md) and [OPEN_MEDIA_CONTRACT.md](OPEN_MEDIA_CONTRACT.md)):

- `openMediaLink` → `{ enabled, linked, needsReconnect, handle, displayName, avatarUrl, connectUrl }`. `linked`/`handle` describe the Open Media account this user signs in with. `enabled: false` means this server runs without Messages and Pitch Shorts (`OPEN_MEDIA_ENABLED` off). `connectUrl` is `/api/auth/open-media/start` (signing in again renews an expired link). Never returns tokens.
- `openMediaRealtimeToken` → `{ supabaseUrl, anonKey, accessToken, expiresAt, omUserId }` — the user's short-lived Open Media Supabase token so the browser can subscribe to Realtime `postgres_changes` on `messages` (RLS-limited). Requires a linked account.

Messaging (Open Media; conversation, message and `otherUserId` ids are Open Media ids):

- `myConversations(limit, offset, allApps = false)` — conversations tagged `context.app = "manifest"`; `allApps: true` lists every Open Media conversation. Each item: `conversationId, otherUserId, otherUserName, otherUserHandle, otherUserAvatar, ideaId, ideaTitle, lastMessageAt, lastMessagePreview, unreadCount`.
- `conversationMessages(conversationId, limit, beforeId)` → `{ messageId, conversationId, senderId, content, createdAt, isMine }`, oldest first
- `unreadMessageCount` — unread messages in Manifest conversations; cached per user for 5 minutes and refreshed by webhooks. Returns `0` when Open Media is off, unlinked or unreachable.
- `ideaOwner(ideaId)` — includes `isPublished`, `openMediaHandle` (null until the founder links Open Media) and `canMessage` (true only for non-owners of a published idea whose founder has linked Open Media)

Without a linked account these fields fail with "Connect your Open Media account in Account settings to use this." (or "…expired. Reconnect it…").

```graphql
query { myConversations(limit: 20) { conversationId otherUserHandle ideaTitle unreadCount } }
```

Pitch reels (clips are Open Media posts with `context.app = "manifest"`):

- `pitchReelsFeed(limit)` — published Manifest reels joined with their Open Media clips: video `videoUrl`/`posterUrl` and `stats { likeCount commentCount shareCount }` (share = Open Media reshares) come from Open Media; `viewerState { liked reshared }` uses the viewer's token when linked, otherwise the public feed. Reels whose clip is not posted yet follow, with `videoStatus` `pending` | `processing` | `failed` | `needs_open_media` (the founder has not linked Open Media). Empty when Open Media is off. Excludes the three legacy sample IDs.
- `pitchReelComments(reelId, limit)` — public Open Media comments on the clip (`authorId` is an Open Media id; `authorHandle` added)
- Mutations (linked account required): `togglePitchReelLike(reelId, liked: Boolean!)`, `resharePitchReel(reelId, reshared: Boolean!)` (repost on the viewer's Open Media profile), `createPitchReelComment(reelId, body)`. There is no save: Open Media has no save concept.
- Creator follow on reels uses Manifest's own `toggleFollow(followedId)`.

```graphql
mutation { togglePitchReelLike(reelId: "<reel-uuid>", liked: true) { liked likeCount } }
```

Publishing an idea (`togglePublishIdea`) sets `ideas.is_published` and upserts a linked `pitch_reels` row when turning **on**. When Open Media is enabled and the founder has linked it, a background Veo job generates the video, uploads it as the founder (`/v1/connected/me/media/videos`) and posts the clip with `context { app: "manifest", idea_id, title, url: "https://manifeststartup.com/pitch-reels?clip=<reelId>" }`; the post id is saved in `pitch_reels.om_post_id`. A founder who has not linked waits in `needs_open_media`; linking resumes the job. Turning publishing **off** hides the reel and deletes the Open Media post.

**Removed (November 2026):** `userPublicKey`, `setEncryptionKey`, `togglePitchReelSave`, `recordPitchReelShare`, `Message.isEncrypted` / `messageType` / `isRead`, `IdeaOwner.email`, `stats.saveCount` and `viewerState.saved`. The old encryption was not real end-to-end encryption.
- `ideaCollaborators(ideaId)`
- `mySharedIdeas`
- `myCollaborationInvitations`
- `ideaVersions(ideaId)`
- `checkIdeaAccess(ideaId)`

### Mutation operations

Core auth/account (signing in is REST, above):

- `logoutUser`
- `updateAccount(input)`
- `revokeAccountSession(sessionId)`, `revokeOtherAccountSessions`
- `requestAccountDeletion(confirmEmail)` — the account email confirms it; the `password` and `mfaCode` arguments were removed

Removed in ADR 0002: `loginUser`, `signupUser`, `requestPasswordReset`, `resetPassword`, `requestGuestAccountUpgradeEmail`, `completeGuestAccountUpgrade`, `mergeGuestWorkspace`, `beginTotpSetup`, `enableTotp`, `disableTotp`, `regenerateRecoveryCodes`, `mfaStatus`, `disconnectOpenMedia` and `PrivacyStatus.passwordResetRetentionMinutes`.

Try-before-signup (guest) sessions:

- `startGuestSession` — no prior auth; creates a `users` row with `is_guest=true`, sets the session cookie, and returns `mergeSecret` (kept for compatibility; clients no longer need it). **Disabled when `DEMO_MODE` is on** (overlaps demo identity).
- Upgrading: the guest follows **Continue with Open Media** from the same browser. The callback merges the guest workspace server-side (the guest's session cookie proves ownership): it moves `ideas` and related workspace rows (pitch decks, PRDs, patents, pitch reels creator, collaborators, versions where present) to the signed-in account and clears the guest flag. A retried callback merges nothing twice.
- `profile` includes `isGuest` for UI gating. The merge secret is **not** exposed on `profile`.
- **Rate limit:** `startGuestSession` is limited per client IP in-process (see `guest_workspace_service`).
- **Retention:** Guests get `guest_expires_at` (default 30 days from creation at insert). Stale rows may be deleted by a scheduled cleanup job in production; until then, data remains on the server for that guest id.

Guest accounts cannot use mutations that require a full account (enforced server-side), including: `togglePublishIdea`, founder messaging (`startConversation`, `sendMessage`, `markConversationRead`), investing mutations, social follow mutations, and `inviteCollaborator`.

Ideas and generation:

- `createIdea(title, description)`
- `updateIdea(ideaId, title, description)`
- `deleteIdea(ideaId)`
- `togglePublishIdea(ideaId)` — also syncs `pitch_reels` for the idea and may enqueue Gemini video generation (see env vars below)
- `runBackgroundTasks(ideaId, description)` — legacy fire-and-forget (threaded).
- `enqueueBackgroundTasks(ideaId, documentTypes, idempotencyKey)` → `{ jobId, status }` — durable, restart-safe alternative. Enqueues a `generation_jobs` row that the dedicated generation worker drains (`FOR UPDATE SKIP LOCKED`); returns immediately with a job id. Poll `generationJob(jobId)` for status, and deduplicated per `idempotencyKey` (a retried request joins the in-flight job). Permission: `ideas.write`.
- `generationJob(jobId)` (query) → `{ id, status, documentTypes, ideaId, errorMessage, createdAt, updatedAt }` — status of an async job; only the owner can read it. Permission: `ideas.read`.
- `generatePitchDeck(ideaId, description)`
- `generateProductRequirementsDocument(ideaId, description)`
- `generateProvisionalPatent(ideaId, description)`

Idea qualification:

- `startIdeaQualification(initialIdeaText)` — opens a new multi-turn qualification session, seeds the opening question, returns the `IdeaQualificationSession`. Also opens an `agent_runs` row linked to the session so cost can be tracked. Permission: `ideas.write`.
- `continueIdeaQualification(sessionId, userMessage)` — advances the session by one turn. Calls the LLM to extract structured fields from the latest reply and either asks the next best question or completes the session with a 0–100 score + explanation. Completes automatically after 8 turns. Each LLM-calling turn logs one `agent_cost_events` row via the `llm_usage_tap`. See `backend/app/services/ai/idea_qualification.py` and the prompt at `backend/app/prompts/idea_qualification.mcp.json`. Permission: `ideas.write`.

Billing (variable-cost cap):

- `setVariableCostCap(monthlyCapUsd: Float, paused: Boolean)` — update the caller's monthly variable-cost cap and/or paused flag. The cap is clamped to `[0, MANIFEST_USER_CAP_MAX_USD]` (default 5000). Currently a soft warning surface; enforcement gating lands in a follow-up — see `docs/COST_TRACKING.md`. Permission: `account.write`.

Import/export:

- `exportIdeas(format)`
- `importIdeas(fileContent, fileFormat, filename)`

Integrations/social/investing:

- `connectIntegration(input)`
- `disconnectIntegration(serviceId)`
- `followUser(followedId)`
- `unfollowUser(followedId)`
- `toggleFollow(followedId)`
- `upvoteIdea(ideaId)`
- `removeVote(ideaId)`
- `toggleUpvote(ideaId)`
- `createInvestment(input)`
- `addInvestmentContribution(input)`
- `updateInvestmentStatus(investmentId, status)`

Messaging/collaboration:

- `startConversation(otherUserId, ideaId)` — opens (or reuses) an Open Media conversation with the founder's linked Open Media handle. `otherUserId` is the founder's **Manifest** user id; with `ideaId` the idea must be **published**, owned by that founder, and the conversation is tagged `context { app, idea_id, title, url }`. Fails with "This founder hasn't connected Open Media yet…" when they have not linked.
- `sendMessage(conversationId, content, clientId)` — `clientId` (optional) is passed to Open Media as the idempotency key so a retried send lands once
- `markConversationRead(conversationId)`
- `disconnectOpenMedia` — forgets the link and its tokens (Open Media content stays on Open Media); returns the new `openMediaLink` status
- `inviteCollaborator(input)`
- `respondToInvitation(ideaId, accept)`
- `updateCollaboratorRole(ideaId, targetUserId, newRole)`
- `removeCollaborator(ideaId, targetUserId)`
- `createIdeaVersion(ideaId, changeSummary)`
- `restoreIdeaVersion(ideaId, versionId)`

## REST Endpoints

### `/api/v1` (API key)

- `GET /api/v1/` info
- `GET /api/v1/ideas`
- `POST /api/v1/ideas`
- `GET /api/v1/ideas/{idea_id}`
- `PATCH /api/v1/ideas/{idea_id}`
- `DELETE /api/v1/ideas/{idea_id}`
- `POST /api/v1/ideas/{idea_id}/generate`
- `GET /api/v1/usage`

### `/api/privacy` (browser privacy preferences)

- `GET /api/privacy/consent`
- `POST /api/privacy/consent`

`GET /api/privacy/consent` behavior:

- Returns the effective privacy choice for the current browser or authenticated user
- Uses a first-party consent cookie, plus the latest server-side audit row when one exists
- Response fields:
  - `hasStoredPreference`
  - `necessaryEnabled` (always `true`)
  - `analyticsEnabled`
  - `communicationsEnabled`
  - `doNotSellOrShare`
  - `policyVersion`
  - `consentUpdatedAt`
  - `source`

`POST /api/privacy/consent` request body:

```json
{
  "analytics_enabled": true,
  "communications_enabled": false,
  "do_not_sell_or_share": false,
  "source": "banner_accept_all"
}
```

`POST /api/privacy/consent` behavior:

- Persists the latest optional-data choice with a timestamp and policy version
- Sets the `manifest_privacy_consent` cookie used by the frontend and backend middleware
- Sets or clears the analytics-scoped `visitor_id` cookie based on consent
- Writes an audit row to `privacy_consents` when `DATABASE_URL` is configured

### `/api/internal/website-testing` (internal agent loop)

- `POST /api/internal/website-testing/sync-issues`

### `/api/internal/survey-ops` (internal agent loop)

- `POST /api/internal/survey-ops/summary`
- `POST /api/internal/survey-ops/sync-issues`

### `/api/internal/production-signals` (internal agent loop)

- `POST /api/internal/production-signals/event` — deduped production anomaly ingest; optional GitHub issue when thresholds are met (see `docs/PRODUCTION_SIGNALS_OPS.md`).

These internal routes are not a customer-facing product API.

Auth:

- `X-Manifest-Agent-Key: <MANIFEST_AGENT_LOOP_SECRET>`

`POST /api/internal/survey-ops/summary` behavior:

- Reads `survey_responses` from Postgres for a rolling window
- Returns aggregate marketability and product-pull metrics
- Can optionally include GitHub-ready issue candidates derived from repeated survey themes

`POST /api/internal/survey-ops/sync-issues` behavior:

- Builds recurring issue candidates from survey signals
- Can create GitHub issues directly when `create_github_issues=true` and backend GitHub credentials are configured
- Supports `dry_run=true` to return candidates without writing to GitHub

`POST /api/internal/production-signals/event` behavior:

- Increments a per-fingerprint counter inside a rolling time window (`PRODUCTION_SIGNAL_WINDOW_SECONDS`, default 15 minutes)
- Opens at most one GitHub issue per fingerprint per window when `create_github_issue=true`, the count meets `PRODUCTION_SIGNAL_THRESHOLD`, and severity / event allowlist rules match (see `docs/PRODUCTION_SIGNALS_OPS.md`)

This route is for Manifest's internal self-improvement loop, not a customer-facing product API.

Auth:

- `X-Manifest-Agent-Key: <MANIFEST_AGENT_LOOP_SECRET>`

`GET /api/internal/ops/snapshot` behavior:

- Returns JSON suitable for monitoring: sync DB connection pool snapshot (`db_pool`: `pooled_connections_checked_out`, min/max pool size flags), async pool snapshot (`async_db_pool`: `async_db_enabled`, `pool_open`, pool stats when `ASYNC_DB=true`), GraphQL and DB slow thresholds from environment, and a placeholder `background_job_queue` block until a queue is implemented.
- Uses the same `X-Manifest-Agent-Key` header as other internal agent-loop routes.
- See `docs/OBSERVABILITY_AND_SLO.md`.

`POST /api/internal/website-testing/sync-issues` behavior:

- Audits a bounded set of public pages from the provided target URL
- Skips `/api/*` and `/graphql` paths
- Generates GitHub-ready issue candidates from heuristics plus AI synthesis when available
- Can create GitHub issues directly when `create_github_issues=true` and backend GitHub credentials are configured
- Supports `dry_run=true` to return candidates without writing to GitHub

`POST /api/v1/ideas/{idea_id}/generate` behavior:

- Accepts `document_types` from: `business_model_canvas`, `pitch_deck`, `prd`, `patent`
- Runs generation synchronously and returns per-document statuses in `documents`
- Uses `ManifestManager` + service classes under `backend/app/services/`

### `/api/keys` (session/JWT)

CLI: `manifest keys clients | create-client | delete-client | create | rotate | revoke | tiers | usage`.

- `GET /api/keys/clients`
- `POST /api/keys/clients`
- `POST /api/keys/keys`
- `POST /api/keys/keys/rotate`
- `DELETE /api/keys/keys/{key_id}`
- `DELETE /api/keys/clients/{client_id}`
- `GET /api/keys/usage`
- `GET /api/keys/tiers`

### `/api/voice-agent` (session/JWT)

- `GET /api/voice-agent/capabilities`
- `POST /api/voice-agent/start`
- `POST /api/voice-agent/process`
- `POST /api/voice-agent/process-stream`
- `POST /api/voice-agent/qualify`
- `POST /api/voice-agent/tts`
- `POST /api/voice-agent/transcribe`

`GET /api/voice-agent/capabilities` returns the deterministic app-control command catalog that backs the current Manifest Voice UI, including navigation (including messages), idea management, document generation phrases (pitch deck, PRD, patent, background tasks), integrations/GitHub bootstrap phrases, workspace layout, search, pitch-reel controls, and **guest account claim** phrases (`claim my account`, which opens sign-in).

### `/api/integrations` (session/JWT)

- `POST /api/integrations/github/bootstrap` — JSON body `{ "idea_id": "<uuid>", "repo_name": "<github-repo-slug>" }`. Requires a **full** account (not guest). Uses the user’s stored GitHub integration token (`integrations.service_id = github`) to create a **private** repository and seed `README.md` from the idea title and note. Returns `{ "html_url": "..." }` on success; `400` if GitHub is not connected, `404` if the idea is missing or not owned by the caller. Pair with voice phrasing that ends in `confirm bootstrap` so repos are not created accidentally.

`POST /api/voice-agent/start` accepts optional `onboarding_mode: true` for guest sessions so the first turn can include a short spoken orientation; otherwise `response.message` may be empty so clients can open the microphone immediately without playing a greeting.

`POST /api/voice-agent/process-stream` returns `text/event-stream` for the live spoken reply. Clients receive `delta` events while the assistant is still generating the answer, then a final `structured` event with the same payload shape as `POST /api/voice-agent/process` so the workspace note and qualification state stay consistent.

**Web client:** choosing voice-first entry from the marketing page sets `localStorage` key `manifest_voice_mode` to `full`. While that value is `full`, the desktop/web client auto-opens the voice overlay once per browser tab when you land on `/ideas` (tracked with sessionStorage key `manifest_voice_full_auto_opened`). Use the in-session **Workspace** control to switch back to `standard` (traditional workspace on next visit), or clear `manifest_voice_mode` manually.

### `/api/webhooks/open-media`

Linking an Open Media account is part of signing in (`/api/auth/open-media/*`, above); `/api/integrations/open-media/connect` and `/callback` were removed.

- `POST /api/webhooks/open-media` — called by Open Media. Headers `X-Open-Media-Event`, `X-Open-Media-Delivery`, `X-Open-Media-Timestamp`, `X-Open-Media-Signature: sha256=<hex HMAC-SHA256(OPEN_MEDIA_WEBHOOK_SECRET, timestamp + "." + raw_body)>`. Rejects bad signatures (401) and timestamps more than 5 minutes off; dedupes on the body `id`; `503` when no secret is configured. Bodies carry ids only; `message.created` / `conversation.read` drop cached unread counts, `post.liked` / `post.commented` / `post.deleted` drop cached clip stats. Returns `{"ok": true}` (plus `"duplicate": true` for repeats).

```bash
body='{"id":"d-1","type":"message.created","data":{"recipient_ids":["<om-user-id>"]}}'
ts=$(date +%s)
sig="sha256=$(printf '%s.%s' "$ts" "$body" | openssl dgst -sha256 -hmac "$OPEN_MEDIA_WEBHOOK_SECRET" -hex | awk '{print $2}')"
curl -X POST http://localhost:8000/api/webhooks/open-media -H "Content-Type: application/json" \
  -H "X-Open-Media-Event: message.created" -H "X-Open-Media-Timestamp: $ts" -H "X-Open-Media-Signature: $sig" -d "$body"
```

**Removed:** `GET /api/pitch-reels/{reel_id}/video` (unauthenticated video bytes from the database). Videos are served by Open Media.

### Other

- `GET /ping`
- `GET /api/docs` (serves `docs/public/api/index.html`)

## Internal Feedback Loop Workflows

- Website audit workflow: `.github/workflows/website-testing.yml`
- Survey feedback workflow: `.github/workflows/survey-feedback.yml`
- Website CLI: `backend/scripts/run_website_issue_sync.py`
- Survey CLI: `backend/scripts/run_survey_issue_sync.py`
- Anonymized survey JSON for stakeholders: `backend/scripts/export_survey_investor_snapshot.py` (private output only; see `docs/INVESTOR_RESEARCH_SNAPSHOT.md`)

### GitHub Projects v2 (optional)

After each successful REST issue create, the backend may attach the issue to a Project v2 board and set **Start** / **End** date fields when configured:

- `MANIFEST_GITHUB_PROJECT_NODE_ID`
- `MANIFEST_GITHUB_PROJECT_START_FIELD_ID` / `MANIFEST_GITHUB_PROJECT_END_FIELD_ID` (Project v2 field node ids)
- `MANIFEST_GITHUB_PROJECT_ROADMAP_DAYS` (default `7`)

Requires a token with **Issues** and **Projects** write access.

## Environment variables (database — async pool, Stage #2)

- `ASYNC_DB` — set to `true` / `1` / `yes` to open a `psycopg` 3.x `AsyncConnectionPool` at FastAPI startup (default **off**). Existing sync `psycopg2` `DatabaseClient.table(...).execute()` calls are unchanged until individual resolvers opt into async helpers in later migration stages.
- `ASYNC_DB_POOL_MIN` / `ASYNC_DB_POOL_MAX` — async pool size bounds (fallback to `DB_POOL_MIN_CONNECTIONS` / `DB_POOL_MAX_CONNECTIONS`).
- `GET /ping` includes an `async_db` block when `ASYNC_DB=true` (`enabled`, `pool_open`, `ping_ok` after `SELECT 1`).

## Environment variables (Open Media)

- `OPEN_MEDIA_ENABLED` — `true` turns on Messages and Pitch Shorts. Off (default) hides both and never calls Veo; ideas and investing keep working. Signing in always uses Open Media, whatever this flag says.
- `OPEN_MEDIA_API_BASE` — default `https://api.openmedia.site` (local: the Worker URL `npm run local` prints in Open Media).
- `OPEN_MEDIA_CLIENT_ID` — default `https://manifeststartup.com/oauth/open-media-client.json` (must match the served document).
- `OPEN_MEDIA_REDIRECT_URI` — optional; default `https://manifeststartup.com/api/auth/open-media/callback`. Only for a local Open Media stack; it must be listed in the client document.
- `OPEN_MEDIA_WEBHOOK_SECRET` — secret; the same hex value as `APP_WEBHOOKS.manifest.secret` on the Open Media Worker.

Stored tokens are encrypted with the existing integration-token envelope keys (`MANIFEST_KEK_*`), so no separate token key is needed.

## Environment variables (pitch reels / video)

- `GOOGLE_API_KEY` — when set (and Open Media is enabled and the founder has linked it), publishing an idea runs one background Gemini (Veo) job for its reel. Cost guard: Veo never runs for an unlinked founder, at most one successful generation per idea per 30 days (`pitch_reels.video_generated_at`), and a failed upload keeps the MP4 on local disk so the retry re-uploads it without calling Veo. When unset, the reel is listed without video (`failed`).
- `GEMINI_VIDEO_MODEL` — optional model id (default `veo-3.1-generate-preview`).
- `PITCH_REEL_VIDEO_MODE` — `thread` (default) runs generation in a background thread after `togglePublishIdea` returns; `disabled` skips scheduling (use on serverless hosts where daemon threads are unreliable). Listing and `pitchReelsFeed` still work without video. The client shows the idea summary and a quiet unavailable-video state; it never substitutes a tutorial clip.

### Production checklist (`togglePublishIdea` / `pitchReelsFeed`)

1. **Apply Supabase migrations** `20261115120000_pitch_reels_open_media.sql` (adds `om_post_id`, `video_generated_at`; drops `video_data` only if empty) and the guarded drops `20261115120100_drop_manifest_messaging.sql` and `20261115120200_drop_pitch_reel_social_tables.sql` (they refuse to drop tables with real rows).
2. **Set the Open Media env vars** above on the backend and `APP_WEBHOOKS` on the Open Media Worker.
3. **`GOOGLE_API_KEY`** — optional; without it reels appear without video.
4. **Background worker** — video generation uses an in-process **daemon thread**. On platforms that freeze or recycle the process immediately after each request, prefer `PITCH_REEL_VIDEO_MODE=disabled` or run a long-lived API worker.
5. **Video files** — the MP4 is written to `generated/pdfs/pitch-reels/` only until it is uploaded to Open Media, then deleted. Open Media serves the video.

## Minimal GraphQL Example

```bash
# Demo mode: get a session cookie, then query GraphQL with it
curl -s -c cookies.txt -o /dev/null "http://localhost:8000/api/auth/open-media/start"
curl -s -b cookies.txt -X POST http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"{ profile { userId email isGuest } }"}'
```

## Known Caveats (Current Code)

- `updateIdea` rejects empty title/description updates and only accepts description with meaningful text after HTML stripping.
- `runBackgroundTasks` is fire-and-forget (threaded) and returns immediately; work is lost on process restart. Prefer `enqueueBackgroundTasks` (durable queue + `generationJob` status) once the generation worker is deployed.
- `POST /api/contact` is defined in code but currently not mounted in `main.py`.
- `/api/v1/ideas/{idea_id}/generate` performs generation inline and can be slow for large prompts; failures are returned per document in the `documents` payload.
- `/api/internal/website-testing/sync-issues` is internal-only and requires `MANIFEST_AGENT_LOOP_SECRET` (or `AGENT_LOOP_SECRET`) plus backend GitHub configuration (`MANIFEST_GITHUB_TOKEN` or `GITHUB_TOKEN`) before it can create issues.
- `/api/internal/production-signals/event` uses the same agent key; GitHub issue creation is opt-in per request and shares the same GitHub token requirements.
- Pitch reel **Gemini video** jobs are threaded; see **Production checklist** under Environment variables.
- Open Media webhook dedupe and the unread/clip-stat caches use `app.services.shared.cache` (in-process unless `REDIS_URL` is set), so with several instances a webhook only clears the instance that received it; the short TTLs (5 minutes unread, 60 seconds clips) bound staleness.

### Pitch Reels feed and loading (September 2026)

The feed uses the shared workspace navigation and theme. Video and pitch details are shown side by side on desktop and stacked on phones. Scroll, arrow keys, or Previous/Next move through reels. Only the active reel has a video source; inactive reels do not download media. The investment dialog is loaded on demand. Returning to the page can show cached reels while refreshing the feed.

`PitchReelService.list_feed` (November 2026) reads published reel rows off the event loop, fetches one page of Open Media clips (`/v1/connected/me/feed?kind=clips&app=manifest` for a linked viewer, else the public `/v1/feed`, cached 60 seconds) and joins them by `om_post_id`. Clip-backed reels follow Open Media's order; reels still waiting for a clip come after. If Open Media is down, the feed degrades to the waiting reels instead of failing. No generation calls occur on feed reads.

Feed subtitle, thesis, and description are plain-text previews capped at 640 characters plus an ellipsis. PostgreSQL also bounds these text columns in its projection, so full note transcripts do not travel in a feed response. Open the linked idea for full content.

Reels with a posted clip are shown before published ideas that are still waiting for one, so the feed opens on available content.

### Supporting document presentation

The canvas, cost worksheet, pitch deck, PRD and U.S. provisional draft use the conventional working formats described in [DOCUMENT_FORMATS.md](DOCUMENT_FORMATS.md). Existing GraphQL fields and Markdown section contracts are unchanged. Saved content receives the updated display without regeneration; prompt changes and the new specification PDF layout apply to subsequent generation. Cost estimates distinguish currency, cadence and assumptions. Existing saved PDFs remain unchanged. No additional AI calls are made on document views.

### Compact note controls

History and Share are icon-only controls with accessible labels and tooltips. The note toolbar no longer shows a Focus button or the collaborator-skills section, and note views no longer fetch the skills catalog. The Similar ideas panel uses its single main heading without the redundant subtitle. Existing keyboard/voice focus commands remain compatible; reopening either side panel exits focus mode. Stored skills fields and account APIs are unchanged.
