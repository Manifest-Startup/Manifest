# 0001. Open Media for Messages and Pitch Shorts

- Status: Accepted (2026-11-15); the "Manifest keeps its own login" part is superseded by [0002](0002-open-media-is-the-only-sign-in.md)
- Plan: [OPEN_MEDIA_INTEGRATION_PLAN.md](../OPEN_MEDIA_INTEGRATION_PLAN.md) · Contract: [OPEN_MEDIA_CONTRACT.md](../OPEN_MEDIA_CONTRACT.md)

## Context

Manifest had its own direct messages and pitch reel social features. Both were thin: messages were polled every 15–120 s and the advertised end-to-end encryption stored plaintext; pitch reel likes, saves, follows and comments lived only in the browser's localStorage; videos were stored as `BYTEA` in Postgres or a Supabase bucket and served from an unauthenticated route. Open Media, a sister product, already does messaging, read receipts, video clips, likes and comments well, with Realtime and moderation.

## Decision

- Users link an Open Media account once ("Sign in with Open Media", OAuth 2.1 + PKCE, public client identified by a Client ID Metadata Document at `/oauth/open-media-client.json`). Manifest keeps its own login.
- Open Media owns conversations, messages, video files, clip posts, likes, comments and reshares. Manifest stores pointers only: the link in `integrations` (`service_id = open_media`, refresh/access tokens envelope-encrypted like BYOK keys, plus `om_user_id` and `handle`) and `pitch_reels.om_post_id`.
- One adapter, `backend/app/services/integrations/open_media/`, is the only code that calls Open Media. GraphQL fields keep their shapes where sensible and resolve through it.
- Pitch shorts are Open Media clips tagged `context.app = "manifest"`; they also appear in Open Media's public clips feed. Veo runs only for founders who linked Open Media, at most once per idea per 30 days.
- Saves are dropped: Open Media has no save concept and Manifest never showed a saved list. Creator follows on reels use Manifest's existing follow graph (the contract has no follow state on clips).
- Fresh start: no data is migrated. Guarded migrations drop the old tables and refuse to run if they hold real rows.
- Off switch: without `OPEN_MEDIA_ENABLED`, Messages and Pitch Shorts are hidden. There is no duplicate built-in fallback.
- Live updates come from Open Media Supabase Realtime with a short-lived per-user token; signed, IDs-only webhooks invalidate cached unread counts and clip stats.

## Consequences

- Founders who have not linked Open Media cannot be messaged or have a reel video; the UI says so and their reels wait in `needs_open_media`.
- An Open Media outage disables messages and reel interactions (with clear errors) but not ideas or investing; the feed falls back to pitch copy.
- Re-publishing within 30 days of a generated video does not regenerate it (cost guard); unpublishing deletes the clip.
- Breaking GraphQL changes: `setEncryptionKey`, `userPublicKey`, `togglePitchReelSave`, `recordPitchReelShare` and several fields are removed; `togglePitchReelLike` takes `liked`; conversation ids are Open Media ids.
- Webhook dedupe and caches are in-process unless `REDIS_URL` is set; with several instances, short TTLs bound staleness.
- Later: server-side cross-posting, transcoding/HLS, message attachments, push notifications, and moving Veo to the async job queue.
