# 0014. Voice is fast, dictates into the note, and can be any agent's voice

- Status: Accepted (2026-11-19). Revises [0013](0013-voice-runs-on-pipecat.md).
- Code: `backend/app/services/voice/live/{bot,relay,dictation}.py`, `backend/app/routes/voice_live_routes.py` (`mode`), `frontend/src/features/voice/NoteDictationOrb.tsx`, `frontend/src/features/ideas/utils/noteDictation.ts`, `mcp_server/src/manifest_cli/agents.py`
- Docs: [`VOICE_AGENT_API.md`](../VOICE_AGENT_API.md) · [`CLI.md`](../CLI.md#voice)

## Context

Voice felt slow. Every turn ran Silero VAD continuously and Pipecat's local smart-turn model (ONNX, ~86 ms per turn on an M1 core) on a Render free instance (0.1 shared vCPU), then uploaded the finished utterance for batch transcription, then ran `gpt-4.1`; the greeting needed a model round trip before anything was heard, and the first session paid Pipecat's import. Separately, people wanted to speak a note rather than talk to the agent, the voice button sat in the screen corner far from the text, voice was hidden in vault mode (the installed Chrome app with a local folder), and people wanted the agents they already use (Claude Code, also inside VS Code; Codex) to be reachable by voice.

## Decision

- **No local inference.** One transcription service for every mode: OpenAI's realtime transcription (`gpt-transcribe`) with server-side turn detection. It streams while the person speaks and ends the turn itself, so the transcript is ready when they stop and the backend only moves audio. `VOICE_TURN_SILENCE_MS` (500) sets the pause.
- **Faster defaults:** `gpt-4.1-mini` for the conversation; a fixed spoken greeting; Pipecat imported in the background when the app asks `/live/status`; the web app preloads its Pipecat chunk and caches the status on hover/focus.
- **`mode=dictate`:** transcription only. The note's orb (beside the reading column; bottom right of the note on phones) writes the words at the cursor as they are heard, lighter until the sentence is final, and follows collaborators' edits. The corner pill steps aside on the note; a small button by the orb opens the agent.
- **`mode=relay`:** the server listens and speaks; the client's own agent answers (`manifest voice --agent claude|codex|<cmd>`). Claude Code runs as one long-lived `--input-format stream-json` process per conversation, started at connect, read-only by default. The server never runs a model or tools in relay mode, so the agent can do no more than it could in a terminal.
- **Vault mode keeps voice:** it runs through the account session; without one, the panel and orb say to sign in. Agent changes reach the folder through vault ↔ account sync (`manifest:vault-sync-now`).

- **No key needed with your own agent (follow-up, same day):** without a key (or account), the app's voice uses the browser's speech recognition and voice and sends turns to `manifest bridge` on 127.0.0.1 (origin-checked; Chrome's local-network preflight answered). Dictation falls back to browser recognition. Measured: Claude Code answers through the bridge in about 2.6 s.
- **Final transcripts end the turn at once (follow-up):** Pipecat passed OpenAI's `completed` transcript on unmarked, so its turn logic waited 0.5 s more on every turn. `build_stt` marks it final; measured locally, turn end → model request fell from 0.53–0.59 s to 0.01–0.05 s.

- **Like-for-like check (same day):** the old (`c3f0128`) and new pipelines, end to end (sound in → first sound out), against the same fake OpenAI with identical delays (model 0.4 s, speech 0.2 s; batch transcription 0.4 s after speech vs streaming 0.15 s after OpenAI's turn end), 5 runs each on an M1: last word → answer heard 1.38–1.79 s old vs 1.39–1.89 s new, i.e. **no change on a fast machine**; connect → greeting heard 5.2–8.0 s old vs 3.3–7.3 s new. The gain from removing local inference should show on the 0.1-vCPU production instance, which could not be reproduced locally (runs on throttled efficiency cores did not finish); a production timing with a real key is still open. The new pipeline waits for OpenAI's 500 ms silence (`VOICE_TURN_SILENCE_MS`), which is now the biggest fixed cost per turn.

## Consequences

- Removed from the voice path: Silero VAD, smart-turn and batch transcription. Echo handling relies on the browser's echo cancellation (the CLI still mutes the mic while speaking).
- Turn detection is OpenAI's; a different STT provider needs its own turn strategy in `build_stt`.
- Relay latency includes the agent: Claude Code's first answer comes ~3 s after a turn once warm, but its Stop hooks run before it accepts the next message.
