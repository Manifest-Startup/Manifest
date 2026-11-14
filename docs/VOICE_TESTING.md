# AI-Driven Voice-Platform Testing

A self-contained testing harness for Manifest's voice agent. Three
LLM agents per test:

1. **User Simulation Agent** — generates a single realistic voice
   utterance for a `(scenario, emotion)` pair, matching the way a
   real person would *actually speak* (filler words, hesitation,
   incomplete sentences allowed).
2. **Voice executor** — produces the response under test. v1
   default is a deterministic LLM stub; the real
   `VoiceAgentService.process_message` slot is reserved (see
   "Switching to the real voice agent" below).
3. **Evaluation Agent** — scores the response 1–5 across three
   dimensions, decides pass/fail, classifies failures, suggests a
   rewrite.

Each phase opens its own cost-tracked `agent_run`, so spending on the
testing harness lands on the admin's billing dashboard (the operator
who triggered the test bears the cost — none of this rolls up to end
users).

## MVP scope (per your own recommendation)

- **5 emotions**: `neutral`, `confused`, `frustrated`, `angry`,
  `happy`.
- **3 scenarios**: `support_request`, `product_question`,
  `complaint`.
- **3 scores** (each 1–5): `intent_understanding`,
  `emotional_awareness`, `helpfulness`.
- **Single-turn**: one user utterance, one assistant response.
- **Text-only**: no TTS, no STT, no acoustic-feature emotion
  recognition yet — the User Simulation Agent declares the emotion
  and the Evaluation Agent uses that as ground truth.
- **Pass-bar**: every score must be `>= 3`. The Evaluation Agent
  may return `pass_status=true`, but the service overrides to
  `false` whenever any single score is below 3.

## Schema

`voice_test_runs`
([migration](../supabase/migrations/20260524120000_voice_test_runs.sql))
— one row per end-to-end test. Combines:

- Test-case fields (from the simulator): `scenario`, `user_persona`,
  `user_emotion`, `user_goal`, `user_input`, `expected_behavior`,
  `success_criteria`, `failure_conditions`.
- Execution: `assistant_response`, `executor_kind` (`stub` or
  `voice_agent`).
- Evaluation: three scores, `overall_score`, `pass_status`,
  `detected_failures` (taxonomy), `root_cause_analysis`,
  `recommended_fixes`, `improved_response_example`.
- Provenance: three `agent_runs` FKs (`simulator_run_id`,
  `executor_run_id`, `evaluator_run_id`) + `triggered_by_user_id`.

## Failure taxonomy

Closed enum to keep dashboards aggregatable. v1 set:

- `incorrect_intent` — assistant misread what the user wanted.
- `tone_mismatch` — response tone doesn't match user emotion.
- `robotic_response` — sounds like form-letter / chatbot copy.
- `missed_emotion` — ignored user's emotional cue entirely.
- `hallucinated_policy` — invented a refund/escalation/tier policy.
- `over_apologizing` — apologizes more than once when not asked.
- `ignored_question` — answered something the user didn't ask.
- `no_next_step` — left the user without an actionable next move.
- `unsafe_advice` — could plausibly mislead or harm.
- `context_loss` — forgot what was said earlier in the turn.
- `other` — fallback; use sparingly.

## Prompts

- [`voice_user_simulator.mcp.json`](../backend/app/prompts/voice_user_simulator.mcp.json)
- [`voice_evaluator.mcp.json`](../backend/app/prompts/voice_evaluator.mcp.json)

Both use strict JSON output (`response_format=json_object` upstream
via `ai_layer_service.generate_structured_response`), `temperature`
calibrated per role (simulator higher for variety, evaluator lower
for consistency).

## GraphQL surface

All admin-gated.

| Operation | Permission |
|---|---|
| `adminVoiceTestRuns(limit, scenario?, emotion?, passOnly?)` | `admin.voice_testing.read` |
| `adminVoiceTestStats(hours)` | `admin.voice_testing.read` |
| `adminRunVoiceTestCase(scenario, emotion, persona?)` | `admin.voice_testing.write` |

Permissions live in
[`backend/app/security/permissions.py`](../backend/app/security/permissions.py)
under `ADMIN_PERMISSIONS` (granted to the `admin` role).

## Cost behavior

Each end-to-end test fires three cost-tracked agent_runs:

- `voice_test_simulator` — generates the test case.
- `voice_test_executor` — produces the response under test
  (`stub` in v1).
- `voice_test_evaluator` — scores the response.

The estimated per-run cost ladder (used by the cap-enforcement
guard when an admin runs many tests):

| agent_kind | est USD per run |
|---|---|
| `voice_test_simulator` | $0.002 |
| `voice_test_executor` | $0.003 |
| `voice_test_evaluator` | $0.004 |

So a typical end-to-end test costs around **$0.009 per run** at
`gpt-4o-mini` pricing. A 100-test batch ≈ $0.90.

## Switching to the real voice agent

The executor is a `Callable[[test_case, ai_layer], str]`. The default
is `stub_voice_executor` (self-contained LLM call, no DB writes). To
test the actual `VoiceAgentService.process_message` path, a
follow-up slice would:

1. Create a synthetic test user once (`voice-test-user` UUID), so
   real-user DB rows aren't polluted.
2. Write a `voice_agent_executor` callable that loads that user's
   context and calls `VoiceAgentService().process_message(...)`,
   returning the structured `response` field.
3. Pass `executor_kind="voice_agent"` and the callable through
   `run_test_case_end_to_end`.

The schema already differentiates by `executor_kind`, so dashboards
can split "stub" vs "real" runs.

## Tests

[`backend/tests/test_voice_testing_service.py`](../backend/tests/test_voice_testing_service.py)
covers:

- Simulator: scenario/emotion validation, AI-layer availability,
  happy path, defensive trim on empty user_input.
- Evaluator: score clamping (1–5), pass requires all scores ≥ 3,
  failure taxonomy filtering (drops unknown values), empty-response
  short-circuit (auto-fail without burning evaluator tokens).
- End-to-end: persists a single row linked to three agent_runs +
  three cost events, simulator failure raises and only the
  simulator run gets marked failed, executor failure still
  persists the row with `assistant_response=null` and the error in
  `metadata`.
- Read APIs: filters by scenario, emotion, pass_only; stats roll-up
  computes pass_rate + by-scenario + by-emotion + top failures.

16 tests, all passing in the full backend sweep.

## Roadmap (per the master prompt)

What's still in the original prompt but reserved for follow-up
slices:

- **Multi-turn**: conversation_messages-aware execution + an
  Evaluation Agent that scores `context_retention`,
  `recovery_from_ambiguity`, `escalation_handling`.
- **TTS/STT loop**: generate audio with the simulator's
  `tts_generation_instruction`, send the audio through the platform's
  STT, evaluate the transcribed → response pipeline. Adds an audio
  storage column and a transcription_run agent.
- **Emotion recognition from audio**: when TTS/STT lands, replace
  the declared emotion with an acoustic-feature classifier and
  include the detected vs. ground-truth comparison in the row.
- **Daily regression cron** + GitHub Actions workflow that runs N
  cases per scenario × emotion pair, posts a summary issue if pass
  rate drops vs. previous run.
- **Failure → suggested-prompt-change feedback loop**: every failed
  case produces a structured `suggested_prompt_change` payload that
  drives prompt-iteration PRs.
- **Frontend `/admin/voice-tests` panel**: pass-rate by emotion and
  scenario, recent failures with rewrite suggestions inline, "Run
  N tests" CTA.
