# Open Media (frontend)

Shared pieces for features that run on Open Media (Messages, Pitch Shorts).

- `useOpenMediaLink.ts` — `openMediaLink` status: is Open Media enabled here, is the account linked, where to connect.
- `OpenMediaConnectPrompt.tsx` — the one-tap "Connect Open Media" card.
- `useOpenMediaRealtime.ts` — live message updates through Open Media's Supabase Realtime (token from `openMediaRealtimeToken`); callers keep a 5-minute poll as fallback.

Naming: hooks `useX.ts`, components `PascalCase.tsx`, tests in `__tests__/`.

Notes for agents: never call Open Media from the browser except Realtime; everything else goes through Manifest GraphQL (`backend/app/services/integrations/open_media/`). Contract: `docs/OPEN_MEDIA_CONTRACT.md`.
