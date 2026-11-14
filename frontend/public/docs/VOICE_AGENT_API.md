# Voice Agent API

Last verified against code on **May 31, 2026**.

Source files:

- `backend/app/routes/voice_agent_routes.py`
- `backend/app/services/voice/agent.py`
- `backend/app/services/voice/text_to_speech.py`
- `backend/app/services/voice/realtime.py` (Realtime / speech-to-speech)
- `frontend/src/features/voice/FloatingVoiceButton.tsx`
- `frontend/src/features/marketing/components/PitchPage.tsx` (home-page guest + voice entry)
- `frontend/src/features/voice/voiceAgentApi.ts`
- `frontend/src/features/voice/realtimeVoiceClient.ts`, `realtimeEvents.ts`, `useRealtimeVoiceSession.ts` (Realtime / speech-to-speech)

## Base Path

`/api/voice-agent`

## Authentication

Endpoints call `get_current_user_id` (session/JWT auth).

Accepted auth:

- `access_token` cookie, or
- `Authorization: Bearer <jwt>` header

Frontend voice client reads token from `localStorage.access_token` (with fallback to `localStorage.sb-access-token` for backward compatibility).

## Endpoints

### `GET /api/voice-agent/capabilities`

Returns the deterministic app-control command catalog available to authenticated Manifest Voice sessions.

Response:

```json
{
  "summary": "Manifest Voice can navigate the app, create and manage ideas, control the workspace layout, search Manifest, and run pitch-reel actions by voice.",
  "commands": [
    {
      "id": "ideas-manage",
      "category": "ideas",
      "title": "Manage the current idea",
      "description": "Rename, publish, unpublish, share, open history, or delete the current idea.",
      "examples": ["Rename this idea to Startup OS", "Publish this idea"]
    }
  ]
}
```

### `POST /api/voice-agent/start`

Start a new conversation context.

Optional JSON body fields:

- `idea_id` (string, optional) — when set, loads that idea’s note into grounding context.
- `onboarding_mode` (boolean, default `false`) — when `true`, the first assistant `message` includes a short spoken orientation for **guest tryouts / home-page voice** (what Manifest does, guest limits, invitation to describe an idea). The `messages` array includes an extra system line with the same grounding hints used on later turns.

Response shape:

```json
{
  "conversation_id": "uuid",
  "response": {
    "message": "...",
    "is_qualified": false,
    "summary": null,
    "suggested_title": null
  },
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

### `POST /api/voice-agent/process`

Process one user message.

Request:

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "user_message": "I want to build ...",
  "idea_id": null,
  "onboarding_mode": false
}
```

When `onboarding_mode` is `true`, model grounding includes the same guest/home orientation hints as `/start` so answers stay consistent for try-before-signup users.

Response:

```json
{
  "response": {
    "message": "...",
    "is_qualified": false,
    "summary": null,
    "suggested_title": null
  },
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

Notes:

- Uses `AIRouter.chat_json` with OpenAI-backed JSON response format.
- Qualification is signaled by `response.is_qualified = true`.

### `POST /api/voice-agent/process-stream`

Stream the spoken reply before the structured voice-note payload is ready.

Request:

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "user_message": "I want to build ...",
  "idea_id": "optional-idea-id"
}
```

Response:

- Content type: `text/event-stream`
- Event sequence:
  - `event: delta` with `{"text":"..."}` while the spoken reply is streaming
  - `event: structured` with the same payload shape as `POST /process`
  - `event: done` with `{"ok":true}` when the turn is complete
  - `event: error` with `{"error":"..."}` if the stream fails after headers are sent

Notes:

- This is the preferred hot path for low-latency voice mode because the frontend can start TTS sentence-by-sentence while later text is still arriving.
- `POST /api/voice-agent/process` remains available as the non-streaming fallback and compatibility path.

### `POST /api/voice-agent/qualify`

Extract a structured idea from conversation.

Request:

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

Response:

```json
{
  "title": "...",
  "description": "<p>...</p>",
  "summary": "..."
}
```

### `POST /api/voice-agent/tts`

Convert text to speech.

Request:

```json
{
  "text": "Hello"
}
```

Response:

```json
{
  "audio_base64": "...",
  "success": true,
  "fallback_to_browser": false
}
```

If TTS is unavailable/fails, API returns:

- `success: false`
- `fallback_to_browser: true`
- `audio_base64: null`

Notes:

- `voice`, `model`, and `instructions` are optional request fields.
- Backend defaults are controlled centrally via `VOICE_AGENT_TTS_*` env vars so every client can share the same OpenAI voice configuration.
- Speech generation defaults to `gpt-4o-mini-tts-2025-12-15`, the latest published GPT-4o mini TTS snapshot verified on 2026-09-12. `nova` remains the default voice. Delivery instructions are forwarded for the dated snapshot as well as the alias; legacy `tts-1` overrides still omit unsupported instructions. Sentence chunking and one-segment prefetch remain enabled. This upgrades the production streaming pipeline; it does not enable the separately gated Realtime or GPT-Live APIs.
- The frontend further reduces perceived latency by synthesizing a short opening segment first (see `FIRST_SPEECH_CHUNK_MAX`) so playback begins almost immediately, then uses larger segments for the rest of the reply to stay smooth.

## Latency architecture

Two backend-wide behaviours keep voice turns from slowing the rest of the platform down:

- **Threadpool handlers** — every blocking voice endpoint (`/start`, `/process`, `/qualify`, `/tts`, `/transcribe`, `/realtime/session`, `/realtime/status`) is a plain `def` FastAPI handler so its synchronous OpenAI/DB work runs in the threadpool instead of on the event loop. `backend/tests/test_voice_agent_routes.py` pins this; do not convert them back to `async def` without making the underlying I/O truly async.
- **Conversation-context cache** — the per-turn user/idea context load (2 DB round-trips before the first LLM token) is cached via `cache_service` (Redis when `REDIS_URL` is set, else in-process). `VOICE_CONTEXT_CACHE_TTL_SECONDS` controls the TTL (default `60`, `0` disables). The `updateIdea` GraphQL mutation invalidates the entry so edits are visible to the next turn immediately.

### `GET /api/voice-agent/realtime/status`

Cheap capability probe used by the client to decide which voice pipeline to mount. **Does not mint a token.**

Response:

```json
{ "enabled": true }
```

`enabled` is `true` only when `VOICE_REALTIME_ENABLED` is set **and** `OPENAI_API_KEY` is configured **and** (the caller is not a guest, or `VOICE_REALTIME_ALLOW_GUESTS` is set).

### `POST /api/voice-agent/realtime/session`

Mint a short-lived **ephemeral client secret** for the OpenAI Realtime (speech-to-speech) API. The browser uses this secret to open a WebRTC connection **directly to OpenAI** for near-instant, barge-in-native conversation; the platform `OPENAI_API_KEY` is never exposed to the client.

Optional JSON body fields: `idea_id`, `onboarding_mode`, `landing_onboarding` (used to ground the session instructions, mirroring `/start`).

Response (enabled):

```json
{
  "enabled": true,
  "client_secret": "ek_...",
  "expires_at": 1730000000,
  "model": "gpt-4o-realtime-preview",
  "voice": "shimmer",
  "base_url": "https://api.openai.com/v1/realtime"
}
```

When the feature is off (or the key is missing) the route returns `{ "enabled": false }` and the client transparently falls back to the streaming `process-stream` pipeline. A genuine mint failure returns HTTP `502`.

Notes:

- **Cost + safety:** Realtime audio is materially more expensive than the streaming TTS pipeline, so it is **off by default** (`VOICE_REALTIME_ENABLED=false`). Guests are refused unless `VOICE_REALTIME_ALLOW_GUESTS=true`. Tune the model/voice with `VOICE_REALTIME_MODEL` / `VOICE_REALTIME_VOICE` (Realtime exposes a different voice set than TTS — there is no `nova`; `shimmer` is the warm female default).
- **Persona + grounding:** the session `instructions` reuse the shared `BASE_VOICE_AGENT_PROMPT` plus spoken guidance and the same founder/idea grounding as the streaming path (`backend/app/services/voice/realtime.py`).
- **Durable note:** the live speech-to-speech turn stays off the hot path; the structured voice note is synthesized once when the session ends (or the founder opens the workspace) by replaying the transcript through `POST /process`, then persisted via GraphQL — so persistence behaves like the streaming pipeline without paying its latency on every turn.
- **Frontend:** `frontend/src/features/voice/realtimeVoiceClient.ts` (WebRTC), `realtimeEvents.ts` (pure transcript reducer), `useRealtimeVoiceSession.ts` (session hook, same API shape as `useVoiceIdeaSession`), wired in `VoiceAgent.tsx` behind the status probe with full fallback.

## Frontend Flow

`FloatingVoiceButton` and `VoiceAgent` components use this sequence:

1. `capabilities` for the deterministic app-control catalog
2. `start`
3. repeat `process-stream` for startup-strategy turns that are not handled as built-in app commands
4. `qualify` when a conversation should be synthesized into an idea note
5. persist idea changes via GraphQL mutations

When `VOICE_REALTIME_ENABLED` is on, `VoiceAgent` instead probes `realtime/status`, mints a session via `realtime/session`, and runs the conversation over WebRTC speech-to-speech (steps 2–3 collapse into one live session); persistence (steps 4–5) still runs on session end.

## Error Behavior

- Route handlers return HTTP 500 with `detail` for unhandled exceptions.
- `tts` endpoint is defensive and often returns `success: false` instead of hard failing.


## Compact voice surface (September 2026)

The workspace assistant opens in a nonmodal 380px panel with a bounded height, leaving the note usable. Minimize preserves the audio element and keeps status, pause/resume and end visible. Closing or Escape ends the session; pause stops recognition, playback and capture while retaining the conversation. Session details are optional. No orb, glow, decorative audio analysis, or full-screen overlay is used. Landing onboarding uses the same themed card and still requires a start action before microphone capture.

Design research: [Siri on Mac](https://support.apple.com/guide/mac-help/how-to-use-siri-mchl6b029310/mac) keeps requests in a corner; [ChatGPT Voice](https://help.openai.com/en/articles/20001274) integrates readable conversation with explicit microphone and exit controls. Manifest applies these patterns to its own compact workspace theme.

Model selection: [OpenAI TTS guide](https://developers.openai.com/api/docs/guides/text-to-speech) and [published snapshots](https://developers.openai.com/api/docs/models/gpt-4o-mini-tts) support the current production architecture. [GPT-Live 1](https://developers.openai.com/api/docs/models/gpt-live-1) is the newer full-duplex conversation family, but requires a distinct session/delegation integration, rather than a TTS model substitution. We retain the app-command and per-turn idea-save path. Do not describe this release as a GPT-Live migration.
