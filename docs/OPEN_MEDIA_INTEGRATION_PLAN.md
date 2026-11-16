# Open Media integration plan: Messages and Pitch Shorts

Status: proposal for review (2026-11-15). No code changed yet.

## Decisions

| Question | Decision |
| --- | --- |
| Identity | Users link an Open Media account once with "Sign in with Open Media" (OAuth 2.1). Manifest keeps its own login. |
| Shorts reach | Pitch shorts are Open Media clips tagged `manifest`. They show in Manifest `/pitch-reels` and in Open Media's public clips feed. Cross-posting to other networks comes later. |
| Existing data | Fresh start. The Manifest database has no real DMs or reels, so nothing is migrated and the old tables and code are removed. |
| Fallback | No duplicate built-in version. If `OPEN_MEDIA_ENABLED` is off (for example on a self-hosted copy without Open Media), Messages and Pitch Shorts are hidden. Idea pages and investing still work. |

## Who owns what

- **Open Media owns:** conversations, messages, reactions, read receipts, video files, clip posts, likes, comments, follows.
- **Manifest owns:** ideas, canvas, research, documents, investments, AI video generation (Veo), and pointers to Open Media records.

Manifest never copies Open Media content into its own tables. It stores only these IDs:
- `open_media_links` (`user_id`, `om_user_id`, `om_handle`, encrypted refresh token, scopes, `linked_at`)
- `pitch_reels.om_post_id`
- an optional `idea_conversations` cache (`idea_id`, `om_conversation_id`) used for the "Message founder" lookup

## Architecture

```
Manifest frontend ──GraphQL──> Manifest backend ──> services/integrations/open_media/  (one adapter)
      │                                                    │  uses packages/python (open-media SDK)
      │ Supabase Realtime (OM token, read-only)            ▼
      └──────────────────────────────────────────> Open Media Worker  api.openmedia.site
                                                           │  outbound webhooks
Manifest backend  <── POST /api/webhooks/open-media ───────┘  (HMAC-signed)
```

- **One adapter, one boundary.** The module `backend/app/services/integrations/open_media/` holds:
  - `client.py`: an HTTP client that refreshes tokens and retries
  - `messaging.py`, `clips.py`, `identity.py`
  - `webhooks.py`: signature checks and event dispatch

  No other Manifest code calls Open Media directly.
- **GraphQL stays stable for the frontend.** The existing `myConversations`, `sendMessage`, `pitchReelsFeed`, `togglePitchReelLike` and related fields keep their shapes but resolve through the adapter. The UI changes stay small.
- **Pinned SDK.** Manifest depends on a pinned `open-media` Python package version. A contract test runs the adapter against Open Media's `/v1/openapi.json`, so an Open Media API change breaks CI instead of breaking production.

## Changes in Open Media (do first; each is a small ADR plus PR)

1. **OAuth on REST.** Accept "Sign in with Open Media" access tokens on `/v1/me/*`, not just `/account/mcp`. Add Manifest as a registered client with scopes `messages`, `posts`, `media` and a redirect URI `https://manifeststartup.com/oauth/open-media/callback`.
2. **Video upload through the API.**
   - Add `POST /v1/me/media/videos`, which returns a signed upload URL for the `post-videos` bucket.
   - Let `POST /v1/me/posts` accept a `video` object, passing the existing `p_video` to `open_media_create_post`.
   - Add the matching SDK, Python and MCP tool changes.
3. **App context on records.**
   - Add an optional `context` jsonb on `conversations` and `posts`, for example `{app: "manifest", idea_id, url}`.
   - Add a `source_app` field and filters `?app=manifest` on `/v1/feed?kind=clips` and `/v1/posts`.
   - Open Media shows a "From Manifest" chip that links back to the idea.
4. **Outbound webhooks.**
   - Per-client subscriptions for `message.created`, `conversation.read`, `post.liked`, `post.commented` and `post.deleted`.
   - Requests are HMAC-signed and retried with backoff from a Worker queue or cron.
   - Payloads carry IDs and context only, never message bodies.
5. **Later, not in the first release:**
   - server-side cross-posting
   - transcoding and HLS (Cloudflare Stream)
   - message attachments
   - push notifications

## Changes in Manifest

### Phase 1: linking (after Open Media changes 1 and 3)
- Add the migration for the `open_media_links` table.
- Add a "Connect Open Media" card in Account settings, with the OAuth PKCE flow, callback route and unlink option.
- Add GraphQL `openMediaLink` (status, handle) and `disconnectOpenMedia`.
- Messages and Pitch Shorts show a one-tap connect prompt until the account is linked.

### Phase 2: messages
- Resolvers call `open_media.messaging`:
  - list conversations filtered to `context.app = manifest`, with a toggle to show all
  - send
  - mark read
  - unread count
- "Message founder" (`IdeaOwnerPanel`) calls `start_conversation` with the founder's Open Media handle and `context.idea_id`. If the founder hasn't linked an account, the button says so instead of failing.
- **Live updates:**
  - The frontend subscribes to Open Media Supabase Realtime with the user's short-lived token (a backend-issued `openMediaRealtimeToken`).
  - The 15/30/120 s polling stays only as a slow fallback (5 min).
  - Webhooks update the nav unread badge for users who aren't on the page.
- Remove the fake encryption fields (`is_encrypted`, `SET_ENCRYPTION_KEY`, `user_encryption_keys`) and the unused `MessageButton`.

### Phase 3: pitch shorts
- `video_worker.py`: after Veo produces the video, upload it through `POST /v1/me/media/videos` as the founder, then create the post with `context.idea_id`. Save `om_post_id`.
- The reel's `video_status` flow stays the same (pending → processing → ready/failed).
- Unpublishing an idea deletes or hides the Open Media post.
- `pitchReelsFeed` reads `/v1/feed?kind=clips&app=manifest` and joins Manifest idea data (thesis, raise, Invest button) by `context.idea_id`.
- **Likes, saves, comments, shares and follow** call Open Media through the adapter:
  - Delete `usePersistentShortsState` and `shortsStorage`, which are browser-only today.
  - Wire the existing unused GraphQL mutations.
- Remove from Manifest:
  - the `pitch_reel_likes`, `_saves`, `_comments` and `_share_events` tables
  - the `video_data` BYTEA and its startup DDL
  - the `pitch-reels` storage bucket code and the unauthenticated `/api/pitch-reels/{id}/video` route
- **Later:** move the Veo job from a daemon thread to the queue in `docs/ASYNC_JOB_QUEUE_DESIGN.md`.

### Phase 4: cleanup and docs
- Drop the Manifest `conversations` and `messages` tables (fresh start).
- Run the code graph `orphans`/`unused` checks.
- Update `docs/API.md`, `docs/ARCHITECTURE_REFERENCE.md` and `.env.example`.
- Write an ADR in each repo.

## Settings

- `OPEN_MEDIA_ENABLED`
- `OPEN_MEDIA_API_BASE` (default `https://api.openmedia.site`)
- `OPEN_MEDIA_CLIENT_ID`
- `OPEN_MEDIA_WEBHOOK_SECRET`
- `OPEN_MEDIA_TOKEN_KEY` (encrypts stored refresh tokens)

All are Worker or backend secrets and never committed.

## Testing

- **Adapter:** unit tests with recorded Open Media responses, plus a contract test against `openapi.json`.
- **Webhooks:** signature, replay and idempotency tests (`client_id` on sends is already idempotent in Open Media).
- **End to end:** Cypress `messaging_dm` and `social_pitch_shorts` against a local Open Media (`npm run local`) with two synthetic users.
- **Open Media:** `npm run check` and `npm run test:db` for each change, and cross-platform checks per its AGENTS.md (the "From Manifest" chip affects web, iOS and Android).

## Risks

- **Founders who haven't linked can't be messaged.** Show a clear state, and email them a "connect to receive messages" invite.
- **Open Media outage.** Messages and Shorts show a retry banner; ideas and investing are unaffected.
- **Video without transcoding.** Raw MP4 up to 100 MB from Open Media storage. Fine for 8 s Veo clips; plan for Cloudflare Stream later.
- **Moderation.** Hidden Open Media posts still have reachable video files (Open Media ADR 0009 follow-up). Fix this before the public launch.
