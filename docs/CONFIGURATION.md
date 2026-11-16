# Configuration

[`.env.example`](../.env.example) is the canonical list of environment variables, with defaults and comments. This page explains the groups that need more than a comment.

## Sessions and the Manifest CLI

Browser sessions last 7 days with a 24-hour idle timeout (`SESSION_IDLE_TIMEOUT_SECONDS`, at most `SESSION_CONCURRENCY_CAP` = 10 per person). Sessions minted for the `manifest` CLI ([ADR 0003](adr/0003-manifest-cli-browser-login.md), [CLI.md](CLI.md)) use their own limits; both are optional.

| Variable | Where | Default | Notes |
| --- | --- | --- | --- |
| `CLI_SESSION_TTL_DAYS` | backend | `30` | Lifetime of a CLI session; afterwards the person runs `manifest login` again. |
| `CLI_SESSION_IDLE_TIMEOUT_SECONDS` | backend | `1209600` (14 days) | A CLI session unused this long is revoked. |

The CLI reads `MANIFEST_API_URL`, `MANIFEST_API_TOKEN` and `MANIFEST_CONFIG` on the user's machine (not the server).

## Open Media (sign-in, Messages and Pitch Shorts)

Sign-in always uses Open Media ([ADR 0002](adr/0002-open-media-is-the-only-sign-in.md)); the defaults below work in production without setting anything. See [ADR 0001](adr/0001-open-media-for-messages-and-pitch-shorts.md) and [API.md § Environment variables (Open Media)](API.md#environment-variables-open-media).

| Variable | Where | Default | Notes |
| --- | --- | --- | --- |
| `OPEN_MEDIA_ENABLED` | backend | off | Off hides Messages and Pitch Shorts and never calls Veo. It does not affect sign-in. |
| `OPEN_MEDIA_API_BASE` | backend | `https://api.openmedia.site` | Local Open Media: the Worker URL from `npm run local`. |
| `OPEN_MEDIA_CLIENT_ID` | backend | `https://manifeststartup.com/oauth/open-media-client.json` | Must be the URL of the served client document (`frontend/public/oauth/`). |
| `OPEN_MEDIA_REDIRECT_URI` | backend | `https://manifeststartup.com/api/auth/open-media/callback` | Override only for a local stack; it must be in the document's `redirect_uris`. |
| `OPEN_MEDIA_WEBHOOK_SECRET` | backend (secret) | none | Same string as `APP_WEBHOOKS.manifest.secret` on the Open Media Worker. Without it the webhook answers 503. |

Stored Open Media tokens use the integration-token envelope keys (`MANIFEST_KEK_*`); there is no separate token key. The edge Worker needs no new variables: it serves `/oauth/*` as static assets and proxies `/api/*`.

Removed with ADR 0002 (November 2026), delete them from Render: `MFA_ENCRYPTION_KEY` (Manifest TOTP), `RESEND_API_KEY` and `RESEND_FROM_EMAIL` (only password-reset and guest-upgrade email used them), `REPL_ID` and `ISSUER_URL` (Replit sign-in), `DEMO_USER_PASSWORD`, `PASSWORD_RESET_SWEEP_INTERVAL_SEC` and `DISABLE_HIBP_CHECK`.

Also removed in November 2026: `PITCH_REEL_STORAGE_BUCKET`, `PITCH_REEL_STORAGE_PUBLIC_BASE_URL`, `PITCH_REEL_STORAGE_VIDEO_PREFIX`, `PITCH_REEL_STORAGE_HLS_PREFIX`, `PITCH_REEL_ENABLE_HLS`, `PITCH_REEL_FFMPEG_PATH` (videos are served by Open Media).
