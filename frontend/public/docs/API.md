# Manifest API Reference

Last verified against code on **April 18, 2026**.

Primary source files:

- `backend/app/main.py`
- `backend/app/graphql/schema.py`
- `backend/app/routes/api_v1_routes.py`
- `backend/app/routes/api_keys_routes.py`
- `backend/app/routes/privacy_routes.py`
- `backend/app/routes/survey_ops_routes.py`
- `backend/app/routes/website_testing_routes.py`
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

### Query operations

Core:

- `me`
- `profile`
- `account`
- `ideas`
- `idea(ideaId)`

Documents:

- `pitchDeck(ideaId)`
- `productRequirementsDocument(ideaId)`
- `provisionalPatent(ideaId)`
- `findSimilarIdeas(ideaDescription)`

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

Pitch reels (immersive feed):

- `pitchReelsFeed(limit)` — returns reels with `videoUrl`, `videoStatus` (`ready` | `pending` | `processing` | `failed`), `ideaId` when the reel is linked to an idea (used with `createInvestment` in the Pitch Reels UI), and metadata
- `pitchReelComments(reelId, limit)`
- Related mutations: `togglePitchReelLike`, `togglePitchReelSave`, `recordPitchReelShare`, `createPitchReelComment`

Publishing an idea (`togglePublishIdea`) sets `ideas.is_published`, upserts a linked `pitch_reels` row when turning **on**, unpublishes that reel when turning **off**, and (when `GOOGLE_API_KEY` is set) starts a background Gemini/Veo job to replace the placeholder video file.
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
- `runBackgroundTasks(ideaId, description)`
- `generatePitchDeck(ideaId, description)`
- `generateProductRequirementsDocument(ideaId, description)`
- `generateProvisionalPatent(ideaId, description)`

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

`GET /api/voice-agent/capabilities` returns the deterministic app-control command catalog that backs the current Manifest Voice UI, including navigation, idea management, workspace layout, search, and pitch-reel controls.

`POST /api/voice-agent/start` may return an empty `response.message` so clients can open the microphone immediately without playing a spoken greeting.

`POST /api/voice-agent/process-stream` returns `text/event-stream` for the live spoken reply. Clients receive `delta` events while the assistant is still generating the answer, then a final `structured` event with the same payload shape as `POST /api/voice-agent/process` so the workspace note and qualification state stay consistent.

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

## Environment variables (pitch reels / video)

- `GOOGLE_API_KEY` — when set, publishing an idea triggers a background Gemini (Veo) video job for its pitch reel; when unset, the reel stays on a placeholder clip and is still listed in `pitchReelsFeed`.
- `GEMINI_VIDEO_MODEL` — optional model id (default `veo-3.1-generate-preview`).
- `PITCH_REEL_VIDEO_MODE` — `thread` (default) runs generation in a background thread after `togglePublishIdea` returns; `disabled` skips scheduling (use on serverless hosts where daemon threads are unreliable). Listing and `pitchReelsFeed` still work with the placeholder video.

### Production checklist (`togglePublishIdea` / `pitchReelsFeed`)

1. **Deploy the backend** that includes the `pitchReelsFeed` resolver calling `PitchReelService.list_feed` with `viewer_id` (wrong kwargs cause GraphQL errors and the web app falls back to demo clips only).
2. **Apply Supabase migrations** on the production project, including `pitch_reels` columns `video_status`, `video_generation_error`, and the partial unique index on `idea_id` (see `supabase/migrations/`).
3. **Frontend** — `REACT_APP_API_URL` (and related `REACT_APP_SUPABASE_*`) must target the same production API and Supabase project.
4. **`GOOGLE_API_KEY`** — optional in production; without it, reels use a built-in placeholder video but still appear in the feed.
5. **Background worker** — video generation uses an in-process **daemon thread**. On platforms that freeze or recycle the process immediately after each request, prefer `PITCH_REEL_VIDEO_MODE=disabled` or run a long-lived API worker; do not rely on the thread finishing on ephemeral serverless instances.
6. **Generated video files** — by default, successful jobs write MP4s under `generated/pdfs/pitch-reels/` on the API host. Ephemeral disks lose these files after deploy; static/CDN frontends may not serve that path. For durable URLs, plan object storage (e.g. Supabase Storage) and public URLs—see `pitch_reels/video_worker.py`.

## Minimal GraphQL Example

```bash
curl -X POST http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"mutation($email:String!,$password:String!){ loginUser(email:$email,password:$password){ userId email token }}","variables":{"email":"hello@manifeststartup.com","password":"manifest"}}'
```

## Known Caveats (Current Code)

- `updateIdea` rejects empty title/description updates and only accepts description with meaningful text after HTML stripping.
- `runBackgroundTasks` is fire-and-forget (threaded) and returns immediately.
- `POST /api/contact` is defined in code but currently not mounted in `main.py`.
- `/api/v1/ideas/{idea_id}/generate` performs generation inline and can be slow for large prompts; failures are returned per document in the `documents` payload.
- `/api/internal/website-testing/sync-issues` is internal-only and requires `MANIFEST_AGENT_LOOP_SECRET` (or `AGENT_LOOP_SECRET`) plus backend GitHub configuration (`MANIFEST_GITHUB_TOKEN` or `GITHUB_TOKEN`) before it can create issues.
- `/api/internal/production-signals/event` uses the same agent key; GitHub issue creation is opt-in per request and shares the same GitHub token requirements.
- Pitch reel **Gemini video** jobs are threaded and write to local `generated/` by default; see **Production checklist** under Environment variables.
