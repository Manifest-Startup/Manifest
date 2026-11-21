# 0017. Voice with your own agent feels instant, and you can talk over it

- Status: Accepted (2026-11-20). Builds on [0014](0014-voice-is-fast-dictates-and-relays.md) (bridge, relay) and [0013](0013-voice-runs-on-pipecat.md) (Pipecat).
- Code: `frontend/src/features/voice/useLocalAgentVoiceSession.ts`, `localAgent.ts` (`isBargeIn`, `pickVoice`), `VoiceSetup.tsx`, `frontend/public/voice.sh`; `mcp_server/src/manifest_cli/bridge.py` (`_TurnLink`), `agents.py` (`interrupt`, `CLAUDE_VOICE_MODEL`, `detect_agent`), `local_voice.py` (`enough_memory`)

## Context

With no OpenAI key, the bridge ran a local Pipecat voice (Whisper + Kokoro) next to Claude Code. On an 8 GB M1 the models were swapped out between turns: Kokoro took 3–6 s to start a sentence, longer than Pipecat's 3 s stop timeout, so each reply ended as "completed with no audio". The app treated that non-fatal error as fatal and turned the orb red. Whisper took about 2 s per turn and often heard nothing. You couldn't interrupt the browser path, and setting it up took several commands.

## Decision

- **Browser speech by default, local models only with room.** The bridge runs Whisper + Kokoro only with about 16 GB of RAM or more (or `--voice <kokoro voice>`). Otherwise the browser hears (streaming recognition) and speaks (its voice starts in 4–190 ms; `say` took 3.5–4.7 s under swap).
- **A fast brain.** Claude Code answers voice on Haiku (warm first word: median 1.7 s vs 2.3 s for the default model) unless `--model` says otherwise. Codex runs with low reasoning effort. `--agent auto` (the default) picks Claude Code, else Codex.
- **Send on the pause.** The question goes when the words stop changing for 0.7 s, or 0.35 s after a final result. There's no spoken greeting.
- **Talk over it.** The mic stays open while it speaks. Words that mostly repeat what it is saying are its own echo and are ignored. "Stop"/"wait", or two words of something else, cancel speech at once and hang up the turn. The bridge sees the hang-up at once and sends Claude Code an `interrupt` control request, so the same warm process takes the next question about 1 s later. Tapping the orb or pressing Space also stops it.
- **Only fatal errors end a session.** Pipecat errors with `fatal: false` are logged, not shown, and Kokoro's stop timeout is 12 s.
- **Set up in one step.** The voice panel shows one command (`curl -fsSL https://manifeststartup.com/voice.sh | sh`): it installs the CLI from the public repo with uv and the login item, and the panel connects by itself when the bridge answers. "Add an OpenAI key" is the other choice.

## Consequences

- Measured on the real stack (8 GB M1 under heavy swap, scripted mic): last word → voice 2.0–2.9 s (was 5–7 s when it worked). Talking over a long answer → new answer in 2.7 s. Claude's own first token, 1–1.5 s warm, is now most of the wait. ChatGPT-level (~0.5 s) needs a speech-to-speech model (OpenAI Realtime, on the person's key), with the agent as a tool. That isn't built yet.
- Chrome's recognition sends audio to Google's speech service; Safari uses Apple's. The browser voice is less natural than Kokoro.
- The echo filter is a heuristic: with loud speakers, a person repeating the voice's own words won't interrupt it (tap or Space still does). Headphones avoid echo entirely.
