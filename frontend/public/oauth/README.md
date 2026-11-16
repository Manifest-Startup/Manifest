# OAuth client documents

Public OAuth client metadata served at `https://manifeststartup.com/oauth/*` as static assets.

- `open-media-client.json` — Manifest's Client ID Metadata Document for "Continue with Open Media", Manifest's only sign-in (`/api/auth/open-media/callback`). Its URL is the `client_id` (`OPEN_MEDIA_CLIENT_ID`). Keep `redirect_uris` in sync with `OPEN_MEDIA_REDIRECT_URI` / `backend/app/services/integrations/open_media/settings.py`. Contract: `docs/OPEN_MEDIA_CONTRACT.md`.

Notes for agents: these files are public. Never put secrets here.
