# 0017. Voice with your own agent feels instant, and you can talk over it

- Status: Accepted (2026-11-20). Builds on [0014](0014-voice-is-fast-dictates-and-relays.md) (bridge, relay) and [0013](0013-voice-runs-on-pipecat.md) (Pipecat).
- Code: `frontend/src/features/voice/useLocalAgentVoiceSession.ts`, `localAgent.ts` (`isBargeIn`, `pickVoice`, `createBridgeSpeaker`, `speechPieces`), `mcp_server/src/manifest_cli/speech.py`, `VoiceSetup.tsx`, `frontend/public/voice.sh`; `mcp_server/src/manifest_cli/bridge.py` (`_TurnLink`), `agents.py` (`interrupt`, `CLAUDE_VOICE_MODEL`, `detect_agent`), `local_voice.py` (`enough_memory`)

## Context

With no OpenAI key, the bridge ran a local Pipecat voice (Whisper + Kokoro) next to Claude Code. On an 8 GB M1 the models were swapped out between turns: Kokoro took 3–6 s to start a sentence, longer than Pipecat's 3 s stop timeout, so each reply ended as "completed with no audio". The app treated that non-fatal error as fatal and turned the orb red. Whisper took about 2 s per turn and often heard nothing. You couldn't interrupt the browser path, and setting it up took several commands.

## Decision

- **The browser hears; Kokoro on the Apple GPU speaks.** Streaming recognition in the browser needs no local model. The answer is spoken in Kokoro's `af_heart` voice, made by the bridge on the Apple GPU (MLX, `speech.py`, `POST /speak`). It takes 0.4–0.8 s per sentence on an 8 GB M1, 3–5× faster than real time (the CPU/ONNX build ran at about real time). The app splits sentences at their pauses, requests every piece at once, plays them back to back through Web Audio, and wakes the model (`/speak/warm`) while the person is still talking. A piece that isn't ready 4 s after it's due, or a Mac without the voice (`manifest-mcp[natural-voice]`), uses the browser's voice. The full local Pipecat stack (Whisper + Kokoro) runs only without this voice and with about 16 GB of RAM or more.
- **A fast brain.** Claude Code answers voice on Haiku (warm first word: median 1.7 s vs 2.3 s for the default model) unless `--model` says otherwise. Codex runs with low reasoning effort. `--agent auto` (the default) picks Claude Code, else Codex.
- **Send on the pause.** The question goes when the words stop changing for 0.7 s, or 0.35 s after a final result. There's no spoken greeting.
- **Talk over it.** The mic stays open while it speaks. Words that mostly repeat what it is saying are its own echo and are ignored. "Stop"/"wait", or two words of something else, cancel speech at once and hang up the turn. The bridge sees the hang-up at once and sends Claude Code an `interrupt` control request, so the same warm process takes the next question about 1 s later. Tapping the orb or pressing Space also stops it.
- **Only fatal errors end a session.** Pipecat errors with `fatal: false` are logged, not shown, and Kokoro's stop timeout is 12 s.
- **Set up in one step.** The voice panel shows one command (`curl -fsSL https://manifeststartup.com/voice.sh | sh`): it installs the CLI from the public repo with uv and the login item, and the panel connects by itself when the bridge answers. "Add an OpenAI key" is the other choice.

## Consequences

- Measured on the real stack (8 GB M1 under heavy swap, scripted mic): last word → natural voice 2.8–4.5 s, or 2.0–2.9 s with the browser's voice (was 5–7 s when it worked, and failing). Talking over a long answer → new answer in 2.7 s. Claude's own first token, 1–1.5 s warm, is now most of the wait. ChatGPT-level (~0.5 s) needs a speech-to-speech model (OpenAI Realtime, on the person's key), with the agent as a tool. That isn't built yet.
- Chrome's recognition sends audio to Google's speech service; Safari uses Apple's. The voice model downloads once (about 330 MB, plus a small English text model).
- The echo filter is a heuristic: with loud speakers, a person repeating the voice's own words won't interrupt it (tap or Space still does). Headphones avoid echo entirely.
