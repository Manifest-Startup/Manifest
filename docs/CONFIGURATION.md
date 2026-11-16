# Configuration

[`.env.example`](../.env.example) is the canonical list of environment variables, with defaults and comments. This page explains the groups that need more than a comment.

## Open Media (Messages and Pitch Shorts)

See [ADR 0001](adr/0001-open-media-for-messages-and-pitch-shorts.md) and [API.md § Environment variables (Open Media)](API.md#environment-variables-open-media).

| Variable | Where | Default | Notes |
| --- | --- | --- | --- |
| `OPEN_MEDIA_ENABLED` | backend | off | Off hides Messages and Pitch Shorts and never calls Open Media or Veo. |
| `OPEN_MEDIA_API_BASE` | backend | `https://api.openmedia.site` | Local Open Media: the Worker URL from `npm run local`. |
| `OPEN_MEDIA_CLIENT_ID` | backend | `https://manifeststartup.com/oauth/open-media-client.json` | Must be the URL of the served client document (`frontend/public/oauth/`). |
| `OPEN_MEDIA_REDIRECT_URI` | backend | `https://manifeststartup.com/api/integrations/open-media/callback` | Override only for a local stack; it must be in the document's `redirect_uris`. |
| `OPEN_MEDIA_WEBHOOK_SECRET` | backend (secret) | none | Same string as `APP_WEBHOOKS.manifest.secret` on the Open Media Worker. Without it the webhook answers 503. |

Stored Open Media tokens use the integration-token envelope keys (`MANIFEST_KEK_*`); there is no separate token key. The edge Worker needs no new variables: it serves `/oauth/*` as static assets and proxies `/api/*`.

Removed in November 2026: `PITCH_REEL_STORAGE_BUCKET`, `PITCH_REEL_STORAGE_PUBLIC_BASE_URL`, `PITCH_REEL_STORAGE_VIDEO_PREFIX`, `PITCH_REEL_STORAGE_HLS_PREFIX`, `PITCH_REEL_ENABLE_HLS`, `PITCH_REEL_FFMPEG_PATH` (videos are served by Open Media).
