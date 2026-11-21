# Voice Agent API

Last verified against code on **November 19, 2026**.

Source files:

- `backend/app/routes/voice_agent_routes.py`
- `backend/app/services/voice/agent.py`
- `backend/app/services/voice/text_to_speech.py`
- `backend/app/services/voice/live/` + `backend/app/routes/voice_live_routes.py` (live Pipecat voice, the primary path)
- `frontend/src/features/voice/FloatingVoiceButton.tsx`
- `frontend/src/features/marketing/components/PitchPage.tsx` (home-page guest + voice entry)
- `frontend/src/features/voice/voiceAgentApi.ts`
- `frontend/src/features/voice/usePipecatVoiceSession.ts` (live Pipecat client)

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
- Speech generation defaults to `gpt-4o-mini-tts-2025-12-15`, the latest published GPT-4o mini TTS snapshot verified on 2026-09-12. `nova` remains the default voice. Delivery instructions are forwarded for the dated snapshot as well as the alias; legacy `tts-1` overrides still omit unsupported instructions. Sentence chunking and one-segment prefetch remain enabled. This upgrades the production streaming pipeline; it applies to the fallback pipeline.
- The frontend further reduces perceived latency by synthesizing a short opening segment first (see `FIRST_SPEECH_CHUNK_MAX`) so playback begins almost immediately, then uses larger segments for the rest of the reply to stay smooth.

## Latency architecture

Two backend-wide behaviours keep voice turns from slowing the rest of the platform down:

- **Threadpool handlers** — every blocking voice endpoint (`/start`, `/process`, `/qualify`, `/tts`, `/transcribe`) is a plain `def` FastAPI handler so its synchronous OpenAI/DB work runs in the threadpool instead of on the event loop. `backend/tests/test_voice_agent_routes.py` pins this; do not convert them back to `async def` without making the underlying I/O truly async.
- **Conversation-context cache** — the per-turn user/idea context load (2 DB round-trips before the first LLM token) is cached via `cache_service` (Redis when `REDIS_URL` is set, else in-process). `VOICE_CONTEXT_CACHE_TTL_SECONDS` controls the TTL (default `60`, `0` disables). The `updateIdea` GraphQL mutation invalidates the entry so edits are visible to the next turn immediately.

## Live voice (Pipecat) — the primary voice

Since 2026-11-19 Manifest's voice is a server-side [Pipecat](https://github.com/pipecat-ai/pipecat) pipeline (ADR 0013). It replaced the OpenAI Realtime (WebRTC speech-to-speech) path. ADR 0014 made it fast and added dictation and relay modes.

```
mic ─▶ WebSocket (RTVI over protobuf) ─▶ OpenAI Realtime transcription (server VAD, streaming)
    ─▶ LLM with Manifest's tools ─▶ OpenAI TTS (streamed) ─▶ WebSocket ─▶ speaker
```

- **Speed:** the backend's CPU is tiny (Render free, 0.1 vCPU), so no local inference runs: OpenAI's realtime transcription hears the person while they speak and ends the turn itself (`server_vad`), so the transcript is ready when they stop. The greeting is spoken without a model call; `GET /live/status` starts loading Pipecat in the background; the web app preloads its Pipecat chunk and caches the status for a minute when a voice control is hovered or focused.

- **Code:** `backend/app/routes/voice_live_routes.py` (route + auth), `backend/app/services/voice/live/bot.py` (pipeline, prompt, server messages), `backend/app/services/voice/live/tools.py` (tools).
- **Everything Manifest can do:** the agent uses the same generated catalog as `/mcp`, the agent plugin and the CLI (`tools.generated.json`, written by `scripts/generate_agent_tools.py`), and runs tools over the public GraphQL/REST API with the person's own session token, so backend permission checks apply unchanged. The model sees ~15 everyday tools plus `find_tools` (search all ~130) and `use_tool` (run any), `show_in_app` (navigate the web app) and `end_conversation`. Destructive tools return a preview first; the agent reads it back and needs a spoken yes before calling again with `confirm: true`.
- **Keys:** STT, LLM and TTS use the person's own OpenAI key (Account → AI settings). Nothing runs on a platform key.

### No OpenAI key: the browser and your own agent

When live voice isn't available (no key on the account, or a vault without signing in), the web app doesn't stop at "add a key":

- **Voice button:** if `manifest bridge` runs on this computer (`http://127.0.0.1:47821`, probed only in this case), the browser listens (`SpeechRecognition`) and speaks (`speechSynthesis`), and each turn goes to the person's Claude Code or Codex (`frontend/src/features/voice/localAgent.ts`, `useLocalAgentVoiceSession.ts`). The question goes out when the person pauses, and the mic stays open while it speaks. Talking over it (its own echo is ignored), tapping the orb or pressing Space stops the voice, and the bridge interrupts the agent ([ADR 0017](adr/0017-voice-feels-instant.md)). Otherwise the panel shows a one-step setup (`curl -fsSL https://manifeststartup.com/voice.sh | sh`) that connects by itself, or the option to add an OpenAI key.
- **Note dictation:** falls back to the browser's speech recognition.

### `GET /api/voice-agent/live/status`

Cheap probe; never returns a credential.

```json
{ "available": true, "reason": null, "message": null, "transport": "websocket", "protocol": "rtvi" }
```

`reason` is `no_api_key` (with `message`) when the person has no OpenAI key, or `unavailable` when the server lacks Pipecat.

### `WS /api/voice-agent/live`

One conversation. Query parameters (optional, grounding only): `path`, `idea_id`, `idea_title`, and `mode`:

| `mode` | What runs on the server | Used by |
|---|---|---|
| `agent` (default) | transcription → Manifest's agent with every tool → speech | web app voice, `manifest voice` |
| `relay` | transcription and speech only; the client's own agent answers each turn | `manifest voice --agent claude\|codex\|"<cmd>"` |
| `dictate` | transcription only, streamed word by word; no model, no speech | the note's voice orb |

- **Relay:** the server sends `manifest.turn` `{id, text}` (server-message) when the person finishes a turn; the client answers with `manifest.say` `{text}` client-messages (one per sentence, spoken in order) and may send `manifest.hush` to stop speech. The server never runs a model or tools in relay mode.
- **Dictate:** RTVI `user-transcription` events: `final: false` carries the next piece (a delta to append), `final: true` the whole sentence once the person pauses. Sessions end after 2 idle minutes.

- **Auth:** browsers use the session cookie and must connect from a Manifest origin (same host, `FRONTEND_ORIGINS`, `APP_BASE_URL`; localhost outside production) to stop cross-site WebSocket hijacking. The CLI and agents send `Authorization: Bearer <session token>` (no Origin needed).
- **Close codes:** `4401` sign in · `4402` no OpenAI key · `4403` origin not allowed · `4503` voice not installed.
- **Protocol:** [RTVI](https://docs.pipecat.ai/client/introduction) 2.3 frames serialized with Pipecat's `ProtobufFrameSerializer`; input audio 16 kHz mono PCM, output 24 kHz. Any Pipecat client works (`@pipecat-ai/client-js` + `@pipecat-ai/websocket-transport` in the web app; `manifest voice` in the CLI).
- **Server messages** (RTVI `server-message`, `data.type`): `manifest.tool` `{phase: started|finished, id, name, label, ok?, summary?}` · `manifest.navigate` `{path}` · `manifest.changed` `{tool}` (refresh views) · `manifest.end`.
- **Client messages** (RTVI `client-message`): `manifest.context` `{path, idea_id?, idea_title?}` when the person moves around the app. Typed input uses RTVI `send-text`.
- **Limits:** 30-minute session, 5 minutes idle.

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `VOICE_LLM_MODEL` | `gpt-4.1-mini` | Conversation + tool-calling model (fast first token) |
| `VOICE_STT_MODEL` | `gpt-transcribe` | Streaming speech to text with server turn detection (all modes) |
| `VOICE_TURN_SILENCE_MS` | `500` | Pause that ends a turn (200–3000); shorter answers sooner |
| `VOICE_STT_URL` | from `VOICE_OPENAI_BASE_URL` (`ws…/realtime`) | Realtime transcription WebSocket |
| `VOICE_TTS_MODEL` / `VOICE_TTS_VOICE` | `gpt-4o-mini-tts` / `coral` | Text to speech |
| `VOICE_OPENAI_BASE_URL` | OpenAI | Any OpenAI-compatible API for all three (self-hosted, a gateway) |
| `VOICE_LLM_BASE_URL` | `VOICE_OPENAI_BASE_URL` | A different OpenAI-compatible endpoint for the LLM only |
| `VOICE_API_ORIGIN` | `http://127.0.0.1:$PORT` | Where tools call Manifest's API. Set it to the backend's URL when voice runs as its own service |

Pipecat swaps providers per stage (Deepgram, ElevenLabs, Cartesia, Anthropic, Gemini and more); only `bot.py` constructs services, so a new provider is a local change there plus a key.

### Deployment

Voice runs inside the backend by default (≈70 MB extra when a session starts; fits Render free). To isolate it, deploy the same image again as `manifest-voice` with `VOICE_API_ORIGIN` pointing at the backend, and set the Worker's `VOICE_ORIGIN` var: the Worker then routes `/api/voice-agent/live*` there (`deploy/cloudflare/src/edge.mjs` `originFor`). WebSocket upgrades already pass through the Worker.

### Testing

`backend/tests/test_voice_live.py` covers tools, confirmation, auth and origin gating. For a full audio run without an OpenAI key, point `VOICE_OPENAI_BASE_URL` at an OpenAI-compatible stub and stream a WAV over the socket (any Pipecat client, or `manifest voice --text`).

## Frontend Flow

Fallback (REST) pipeline, used only when live voice is unavailable:

1. `capabilities` for the deterministic app-control catalog
2. `start`
3. repeat `process-stream` for startup-strategy turns that are not handled as built-in app commands
4. `qualify` when a conversation should be synthesized into an idea note
5. persist idea changes via GraphQL mutations

When `live/status` reports `available`, the web app runs the live Pipecat conversation instead (above); this REST sequence remains the fallback when live voice is unavailable.

## Error Behavior

- Route handlers return HTTP 500 with `detail` for unhandled exceptions.
- `tts` endpoint is defensive and often returns `success: false` instead of hard failing.


## Compact voice surface (September 2026)

The workspace assistant opens in a nonmodal 380px panel with a bounded height, leaving the note usable. Minimize preserves the audio element and keeps status, pause/resume and end visible. Closing or Escape ends the session; pause stops recognition, playback and capture while retaining the conversation. Session details are optional. No orb, glow, decorative audio analysis, or full-screen overlay is used. Landing onboarding uses the same themed card and still requires a start action before microphone capture.

Design research: [Siri on Mac](https://support.apple.com/guide/mac-help/how-to-use-siri-mchl6b029310/mac) keeps requests in a corner; [ChatGPT Voice](https://help.openai.com/en/articles/20001274) integrates readable conversation with explicit microphone and exit controls. Manifest applies these patterns to its own compact workspace theme.

Model selection: [OpenAI TTS guide](https://developers.openai.com/api/docs/guides/text-to-speech) and [published snapshots](https://developers.openai.com/api/docs/models/gpt-4o-mini-tts) support the current production architecture. [GPT-Live 1](https://developers.openai.com/api/docs/models/gpt-live-1) is the newer full-duplex conversation family, but requires a distinct session/delegation integration, rather than a TTS model substitution. We retain the app-command and per-turn idea-save path. Do not describe this release as a GPT-Live migration.
