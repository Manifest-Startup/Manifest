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
- `backend/app/services/privacy_consent_service.py`

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

## Authentication

Two auth mechanisms are used in this codebase.

### Session/JWT auth

Used by GraphQL resolvers and most app REST routes.

Accepted token locations (`backend/app/utils/auth_utils.py`):

- `session_token` cookie
- `access_token` cookie
- `Authorization: Bearer <jwt>` header

If `DATABASE_URL` is not configured and `DEMO_MODE` is not explicitly set to false, demo mode auto-enables.

Default demo credentials:

- `hello@manifeststartup.com`
- `manifest`

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

Messaging and collaboration:

- `myConversations(limit, offset)`
- `conversationMessages(conversationId, limit, beforeId)`
- `unreadMessageCount`
- `ideaOwner(ideaId)` — includes `isPublished` and `canMessage` (non-owners may message only when the idea is published)
- `userPublicKey(userId)`

Pitch reels:

- `pitchReelsFeed(limit)` — returns **published** rows from `pitch_reels` only, excluding the three fixed legacy sample IDs (AquaChain, DormGrader, OneCard OS) before applying the limit; legitimate user reels with the same titles are retained; each item includes `videoUrl`, `videoStatus` (`ready` | `pending` | `processing` | `failed`), `ideaId` when the reel is linked to an idea (used with `createInvestment` in the Pitch Reels UI), and metadata
- `pitchReelComments(reelId, limit)`
- Related mutations: `togglePitchReelLike`, `togglePitchReelSave`, `recordPitchReelShare`, `createPitchReelComment`

Publishing an idea (`togglePublishIdea`) sets `ideas.is_published`, upserts a linked `pitch_reels` row when turning **on**, unpublishes that reel when turning **off**, and (when `GOOGLE_API_KEY` is set) starts a background Gemini/Veo job to create the pitch video.
- `ideaCollaborators(ideaId)`
- `mySharedIdeas`
- `myCollaborationInvitations`
- `ideaVersions(ideaId)`
- `checkIdeaAccess(ideaId)`

### Mutation operations

Core auth/account:

- `loginUser(email, password)`
- `signupUser(email, password)`
- `logoutUser`
- `updateAccount(input)`

Try-before-signup (guest) sessions:

- `startGuestSession` — no prior auth; creates a `users` row with `is_guest=true`, sets the same `access_token` cookie as email login, and returns a **one-time** `mergeSecret` (store client-side until signup). **Disabled when `DEMO_MODE` is on** (overlaps demo identity).
- `mergeGuestWorkspace(guestUserId, mergeSecret)` — authenticated; verifies the guest row and secret, moves `ideas` (and related workspace rows such as pitch decks, PRDs, patents, pitch reels creator, collaborators, versions where present) to the current user, then clears the merge secret and guest flag on the old row.
- `profile` includes `isGuest` for UI gating. The merge secret is **not** exposed on `profile`.
- **Rate limit:** `startGuestSession` is limited per client IP in-process (see `guest_workspace_service`).
- **Retention:** Guests get `guest_expires_at` (default 30 days from creation at insert). Stale rows may be deleted by a scheduled cleanup job in production; until then, data remains on the server for that guest id.

Guest accounts cannot use mutations that require a full account (enforced server-side), including: `togglePublishIdea`, founder messaging (`startConversation`, `sendMessage`, `markConversationRead`, `setEncryptionKey`), investing mutations, social follow mutations, and `inviteCollaborator`.

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
- `continueIdeaQualification(sessionId, userMessage)` — advances the session by one turn. Calls the LLM to extract structured fields from the latest reply and either asks the next best question or completes the session with a 0–100 score + explanation. Completes automatically after 8 turns. Each LLM-calling turn logs one `agent_cost_events` row via the `llm_usage_tap`. See `backend/app/services/idea_qualification_service.py` and the prompt at `backend/app/prompts/idea_qualification.mcp.json`. Permission: `ideas.write`.

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

- `startConversation(otherUserId, ideaId)` — if `ideaId` is set, non-owners require the idea to be **published**
- `sendMessage(conversationId, content, messageType, metadata)`
- `markConversationRead(conversationId)`
- `setEncryptionKey(publicKey)`
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

- `GET /api/keys/clients`
- `POST /api/keys/clients`
- `POST /api/keys/keys`
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

`GET /api/voice-agent/capabilities` returns the deterministic app-control command catalog that backs the current Manifest Voice UI, including navigation (including messages), idea management, document generation phrases (pitch deck, PRD, patent, background tasks), integrations/GitHub bootstrap phrases, workspace layout, search, pitch-reel controls, and **guest account claim** phrases (`claim my account`, `send upgrade link to …`).

### `/api/integrations` (session/JWT)

- `POST /api/integrations/github/bootstrap` — JSON body `{ "idea_id": "<uuid>", "repo_name": "<github-repo-slug>" }`. Requires a **full** account (not guest). Uses the user’s stored GitHub integration token (`integrations.service_id = github`) to create a **private** repository and seed `README.md` from the idea title and note. Returns `{ "html_url": "..." }` on success; `400` if GitHub is not connected, `404` if the idea is missing or not owned by the caller. Pair with voice phrasing that ends in `confirm bootstrap` so repos are not created accidentally.

`POST /api/voice-agent/start` accepts optional `onboarding_mode: true` for guest sessions so the first turn can include a short spoken orientation; otherwise `response.message` may be empty so clients can open the microphone immediately without playing a greeting.

**GraphQL (guest upgrade):** authenticated guests may call `requestGuestAccountUpgradeEmail(email)` (rate-limited; generic success message). Completing the flow is `completeGuestAccountUpgrade(token, password)` (public mutation) after the user opens the emailed link (`/auth?guest_upgrade_token=…`).

`POST /api/voice-agent/process-stream` returns `text/event-stream` for the live spoken reply. Clients receive `delta` events while the assistant is still generating the answer, then a final `structured` event with the same payload shape as `POST /api/voice-agent/process` so the workspace note and qualification state stay consistent.

**Web client:** choosing voice-first entry from the marketing page sets `localStorage` key `manifest_voice_mode` to `full`. While that value is `full`, the desktop/web client auto-opens the voice overlay once per browser tab when you land on `/ideas` (tracked with sessionStorage key `manifest_voice_full_auto_opened`). Use the in-session **Workspace** control to switch back to `standard` (traditional workspace on next visit), or clear `manifest_voice_mode` manually.

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

## Environment variables (pitch reels / video)

- `GOOGLE_API_KEY` — when set, publishing an idea triggers a background Gemini (Veo) video job for its pitch reel; when unset, the reel is still listed in `pitchReelsFeed` with an empty `videoUrl` until a real video exists.
- `GEMINI_VIDEO_MODEL` — optional model id (default `veo-3.1-generate-preview`).
- `PITCH_REEL_VIDEO_MODE` — `thread` (default) runs generation in a background thread after `togglePublishIdea` returns; `disabled` skips scheduling (use on serverless hosts where daemon threads are unreliable). Listing and `pitchReelsFeed` still work without video. The client shows the idea summary and a quiet unavailable-video state; it never substitutes a tutorial clip.

### Production checklist (`togglePublishIdea` / `pitchReelsFeed`)

1. **Deploy the backend** that includes the `pitchReelsFeed` resolver calling `PitchReelService.list_feed` with `viewer_id` (wrong kwargs cause GraphQL errors and a retry state in the web app).
2. **Apply Supabase migrations** on the production project, including `pitch_reels` columns `video_status`, `video_generation_error`, and the partial unique index on `idea_id` (see `supabase/migrations/`).
3. **Frontend** — `REACT_APP_API_URL` (and related `REACT_APP_SUPABASE_*`) must target the same production API and Supabase project.
4. **`GOOGLE_API_KEY`** — optional in production; without it, reels use a built-in placeholder video but still appear in the feed.
5. **Background worker** — video generation uses an in-process **daemon thread**. On platforms that freeze or recycle the process immediately after each request, prefer `PITCH_REEL_VIDEO_MODE=disabled` or run a long-lived API worker; do not rely on the thread finishing on ephemeral serverless instances.
6. **Generated video files** — by default, successful jobs write MP4s under `generated/pdfs/pitch-reels/` on the API host. Ephemeral disks lose these files after deploy; static/CDN frontends may not serve that path. For durable URLs, plan object storage (e.g. Supabase Storage) and public URLs—see `pitch_reel_video_worker.py`.

## Minimal GraphQL Example

```bash
curl -X POST http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"mutation($email:String!,$password:String!){ loginUser(email:$email,password:$password){ userId email token }}","variables":{"email":"hello@manifeststartup.com","password":"manifest"}}'
```

## Known Caveats (Current Code)

- `updateIdea` rejects empty title/description updates and only accepts description with meaningful text after HTML stripping.
- `runBackgroundTasks` is fire-and-forget (threaded) and returns immediately; work is lost on process restart. Prefer `enqueueBackgroundTasks` (durable queue + `generationJob` status) once the generation worker is deployed.
- `POST /api/contact` is defined in code but currently not mounted in `main.py`.
- `/api/v1/ideas/{idea_id}/generate` performs generation inline and can be slow for large prompts; failures are returned per document in the `documents` payload.
- `/api/internal/website-testing/sync-issues` is internal-only and requires `MANIFEST_AGENT_LOOP_SECRET` (or `AGENT_LOOP_SECRET`) plus backend GitHub configuration (`MANIFEST_GITHUB_TOKEN` or `GITHUB_TOKEN`) before it can create issues.
- `/api/internal/production-signals/event` uses the same agent key; GitHub issue creation is opt-in per request and shares the same GitHub token requirements.
- Pitch reel **Gemini video** jobs are threaded and write to local `generated/` by default; see **Production checklist** under Environment variables.

### Pitch Reels feed and loading (September 2026)

The feed uses the shared workspace navigation and theme. Video and pitch details are shown side by side on desktop and stacked on phones. Scroll, arrow keys, or Previous/Next move through reels. Only the active reel has a video source; inactive reels do not download media. The investment dialog is loaded on demand. Returning to the page can show cached reels while refreshing the feed.

On PostgreSQL, `PitchReelService.list_feed` runs one parameterized query through the existing connection pool, off the event loop. It aggregates social counts in SQL, preserves viewer-specific likes/saves/follows, and selects only a boolean for video availability, never video bytes. Sample IDs are filtered before the limit. Legacy tutorial/founder placeholder URLs become empty strings (or the actual stored video endpoint if available). No generation calls occur on feed reads, and existing sample records are retained outside the feed rather than deleting related data.

Feed subtitle, thesis, and description are plain-text previews capped at 640 characters plus an ellipsis. PostgreSQL also bounds these text columns in its projection, so full note transcripts do not travel in a feed response. Open the linked idea for full content.

Reels with an existing video are shown before published ideas that are still waiting for one, so the feed opens on available content. Within each group, featured rank and recency determine order.

### Supporting document presentation

The canvas, cost worksheet, pitch deck, PRD and U.S. provisional draft use the conventional working formats described in [DOCUMENT_FORMATS.md](DOCUMENT_FORMATS.md). Existing GraphQL fields and Markdown section contracts are unchanged. Saved content receives the updated display without regeneration; prompt changes and the new specification PDF layout apply to subsequent generation. Cost estimates distinguish currency, cadence and assumptions. Existing saved PDFs remain unchanged. No additional AI calls are made on document views.

### Compact note controls

History and Share are icon-only controls with accessible labels and tooltips. The note toolbar no longer shows a Focus button or the collaborator-skills section, and note views no longer fetch the skills catalog. The Similar ideas panel uses its single main heading without the redundant subtitle. Existing keyboard/voice focus commands remain compatible; reopening either side panel exits focus mode. Stored skills fields and account APIs are unchanged.
