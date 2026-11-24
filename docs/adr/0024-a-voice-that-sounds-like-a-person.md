# 0024. A voice that sounds like a person, and reads tone on the device

- Status: accepted
- Date: 2026-11-23
- Issue: #131

## Context

People found Manifest voice clear but stiff (#131). We reviewed published practice from OpenAI's Realtime prompting guide, ElevenLabs' agent prompting guide, Sierra's voice engineering posts, Sesame's "voice presence" research, Google conversation design and Alexa's one-breath test. The same rules keep coming up:

- warm and confident, never fawning
- react specifically to what was said
- remember earlier details and ask at most one real follow-up
- honest pushback instead of empty praise
- match the person's energy
- vary the wording
- keep a turn to one breath
- say aloud only what can be read aloud
- check when something sounds misheard

The person also asked that voice notice *how* things are said.

We measured the local agent path (Claude Code haiku, 3 founder questions, 2 rounds per arm, alternating order). The old system prompt alone produced 150–240 spoken words per answer. Adding persona text to the system prompt made it worse (median 397 words with markdown), because Claude Code's own coding instructions outweigh an appended prompt.

## Decision

1. **One persona everywhere.** It covers the rules above and lives in `VOICE_PERSONA` (local agents, `manifest_cli/agents.py`), the live voice `SYSTEM_PROMPT` (`backend/app/services/voice/live/bot.py`) and the strategist base prompt. The live TTS gets an expressive style (`TTS_STYLE`): warm, a smile on light moments, softer for hard news, natural pauses.
2. **A one-line hint with every turn** (`VOICE_TURN_HINT`, about 20 tokens): one to three short spoken sentences, no markdown. Measured against main, same method:
   - first spoken sentence: median 4.0 s → 2.4 s
   - whole answer: 6.3 s → 3.1 s
   - length: 180 → 72 words
   - markdown in no answers in either arm

   The persona itself costs about 140 tokens once per call.
3. **Markdown is never read aloud.** `speakable()` strips bold, headings, bullets, code and links before the bridge or the local Pipecat voice speaks.
4. **Tone of voice, opt-in, on the device** (`frontend/src/features/voice/voiceProsody.ts`):
   - **Off by default.** A switch in the voice panel says what it does and that no audio leaves the device.
   - **How it measures:** while the person talks, the browser computes loudness (RMS), pitch (our own YIN on audio decimated to 12 kHz, about 0.07 ms per 50 ms frame) and pace (recognized words per voiced second).
   - **Relative only:** each turn is compared with this person's own baseline in this conversation, after two turns. There is no population norm.
   - **What it outputs:** only arousal (calm ↔ energized), the dimension prosody carries best, using the W3C EmotionML 1.0 PAD vocabulary (`toEmotionML`). It produces a label (energized, calm, subdued) and up to three fixed phrases ("faster than usual"), with confidence capped at 0.8. It never names an emotion.
   - **What's sent:** a "steady" turn sends nothing. The bridge accepts only known labels and phrases (`describe_tone`), so a page can't inject text. It passes one short line to the agent: "a rough hint for your energy and pace, not a fact; don't mention it."
   - **What's kept:** nothing. No audio, features or cues are stored.
5. **No emotion classifier.** The open models are non-commercial (audeering, autrainer), research-licensed (openSMILE), trained on commercially restricted data (SpeechBrain IEMOCAP), carry a custom license (emotion2vec, FunASR model license) or are GPL (Parselmouth, pitchfinder). Even the best reach only about 36% macro-F1 on natural speech (Odyssey 2024). Prosody cues need no weights and no network.

## Consequences

- Answers are shorter and start sooner. A person who wants depth says so, and the persona allows longer answers when asked.
- Tone reading stays close to the AI Act's "readily apparent expression" carve-out (Recital 18). It is not for workplace or education monitoring (Art. 5(1)(f)). The switch is the disclosure Art. 50(3) asks for. Review again before any server-side or categorical emotion feature.
- The live (OpenAI key) path gets the new persona and voice style, but not tone reading yet. Its mic lives inside Pipecat's transport.
