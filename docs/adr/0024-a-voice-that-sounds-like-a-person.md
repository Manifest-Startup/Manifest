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

## Follow-up (same day)

- **Pi and Hume EVI.** Inflection's Pi was built to be short, curious and honest about being an AI. Hume EVI's guidance says not to end every reply with a question and to mirror the user's length. The persona now adds four rules: don't end every reply with a question; match their length as well as their energy; when words and tone disagree, take the gentler reading; never claim to feel or detect emotions, and say plainly you're an AI if asked. Rules that clash with "praise only what's earned", such as validating on every turn, were left out.
- **End to end on the real stack.** The deployed `voiceProsody.ts` ran in Chromium on recorded speech in place of the mic: three calm turns for the baseline, then an excited turn and a tired one.
  - **Tone reading:** the excited turn read as energized (arousal 0.94: louder, higher, more animated). The tired turn read as subdued (0.13: quieter, lower, flatter).
  - **Through to the agent:** the real cues went to the person's real bridge and Codex. The Codex session shows both cue lines in the prompt. Codex answered the excited turn with "That's a real milestone… What did they want to try first?". To the tired one it said "That's a rough turn, especially after the clinics said yes. We can leave it for now, or look at what the insurer objected to when you're ready."
  - **Low-confidence cues:** the third calm turn was misread as energized at confidence 0.22, against a baseline of only two turns. Cues below 0.3 are now dropped in the browser as well as the bridge.

- **Hume EVI's default prompt.** The official repo is gone; this is its `default_prompt.txt` from a mirror of Hume's examples. Its new rules are adopted: say numbers, dates and money aloud; when the person trails off, a quick "mm-hm, go on"; go with the likely meaning of an obvious mishearing and ask only when it matters; don't lecture. Two deliberate differences remain: Hume names emotions when they are intense and avoids calling itself an AI, while Manifest does neither.
- **Blind evaluation.** A simulated founder (Claude haiku) talked to each version for 5 turns in 2 scenarios, excited and discouraged. A judge (Claude sonnet) scored the unlabeled transcripts in both orders, 1–10.
  - **Pre-#135 vs #135/#137:** the new version was preferred 3 of 4 times. Human 5.8 → 7.0, attention 6.8 → 8.5, fit for speech 4.2 → 8.2, honesty 7.5 → 8.0, warmth 5.5 → 6.0. The one loss was "clinical": it never acknowledged a nervous founder.
  - **Fix:** acknowledge the situation (never a diagnosis of feelings) in a few words, once, and allow the odd real reaction ("oh, nice").
  - **Live vs this version:** this version was preferred 3 of 4 times. Warmth 5.5 → 6.8, energy match 5.8 → 7.0, honesty 7.2 → 8.2, attention 6.8 → 7.5, human 6.0 → 6.5. Its one loss came from repeating a quoted example word for word, so the example became "in a few human words of your own, once", as OpenAI's guide advises.
  - **Script:** `blind_eval.py` (session scratchpad).

## Consequences

- Answers are shorter and start sooner. A person who wants depth says so, and the persona allows longer answers when asked.
- Tone reading stays close to the AI Act's "readily apparent expression" carve-out (Recital 18). It is not for workplace or education monitoring (Art. 5(1)(f)). The switch is the disclosure Art. 50(3) asks for. Review again before any server-side or categorical emotion feature.
- The live (OpenAI key) path gets the new persona and voice style, but not tone reading yet. Its mic lives inside Pipecat's transport.
