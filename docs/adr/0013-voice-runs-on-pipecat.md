# 0013. Voice runs on Pipecat, with every Manifest tool

- Status: Accepted (2026-11-19). Replaces the OpenAI Realtime voice path; builds on [0004](0004-agents-get-everything-through-one-plugin.md).
- Code: `backend/app/routes/voice_live_routes.py`, `backend/app/services/voice/live/`, `frontend/src/features/voice/`, `mcp_server/src/manifest_cli/voice.py`, `deploy/cloudflare/src/edge.mjs` (`originFor`)
- Docs: [`VOICE_AGENT_API.md`](../VOICE_AGENT_API.md) · [`CLI.md`](../CLI.md#voice)

## Context

Voice is meant to become the main way people use Manifest, but it could only talk about one idea and run a few hard-coded app commands. The opt-in fast path sent the browser straight to OpenAI's Realtime API over WebRTC: one vendor and one model, a different tool surface from the plugin and CLI, and no way to use it from a terminal. Hosting is Render free behind a Cloudflare Worker: HTTP and WebSockets only, no inbound UDP, 512 MB.

## Decision

- **Pipecat on the server.** One pipeline per conversation: Silero VAD with Pipecat's smart-turn model → OpenAI streaming STT → an LLM with tools → OpenAI TTS, built with Pipecat's `PipelineWorker`. Pipecat is open source (BSD-2), swaps providers per stage, and gives interruption handling and turn detection we would otherwise hand-build. We chose STT → LLM → TTS over speech-to-speech so we control the tool set, the context and the per-turn cost.
- **WebSocket + RTVI.** Pipecat's `FastAPIWebsocketTransport` with protobuf frames and its open RTVI client protocol. It passes through the existing Worker, unlike WebRTC (UDP/TURN) or a hosted room service (another vendor). Browsers authenticate with the session cookie plus an Origin check; the CLI with a Bearer token.
- **The plugin's tools, not a voice-only set.** The agent loads the catalog `scripts/generate_agent_tools.py` generates for `/mcp` and the plugin, and calls the public API with the person's own token, so voice can do anything the plugin and CLI can, under the same permissions. ~15 everyday tools are always offered; `find_tools` / `use_tool` reach the rest without sending ~130 schemas per spoken turn. Destructive tools keep the confirm handshake: preview, spoken yes, then `confirm: true`.
- **Bring your own key** for every stage, like the rest of Manifest. `VOICE_*_MODEL` and an OpenAI-compatible `VOICE_OPENAI_BASE_URL` / `VOICE_LLM_BASE_URL` choose models and endpoints.
- **In-process by default, separable.** The pipeline runs in the backend (Pipecat loads lazily; ~70 MB more during a session). Setting the Worker's `VOICE_ORIGIN` sends `/api/voice-agent/live*` to a second deployment of the same image with `VOICE_API_ORIGIN` set.
- **One client protocol everywhere.** The web app uses `@pipecat-ai/client-js` with the WebSocket transport; `manifest voice` is a small audio bridge (websockets + sounddevice), half-duplex by default because laptop speakers feed the mic.

## Consequences

- Removed: `services/voice/realtime.py`, `/api/voice-agent/realtime/*`, the WebRTC client, and `VOICE_REALTIME_*` settings. The REST streaming pipeline stays only as a fallback when live voice is unavailable.
- A new GraphQL field reaches voice the same way it reaches agents: regenerate the tools.
- In-process voice shares the event loop with sync resolvers; heavy traffic should move voice to its own service (`VOICE_ORIGIN`).
- Each turn costs the person's own STT + LLM + TTS usage; sessions stop after 30 minutes or 5 idle minutes.
