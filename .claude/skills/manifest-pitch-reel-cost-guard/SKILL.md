---
name: manifest-pitch-reel-cost-guard
description: Block changes that grow LLM or video-generation cost without a cache or feature flag. Use when an edit touches the AI Layer (`backend/app/services/ai_*`, `backend/app/prompts/`, anything calling OpenAI / Gemini / Veo / Perplexity) or the pitch-reel generator. Refuses to ship without a cache_control marker, a model downgrade where appropriate, or a feature flag that can be turned off in production.
---

# Manifest Pitch Reel & AI Cost Guard

Manifest's third non-negotiable principle is *inexpensive to run and maintain*. The AI
Layer (and especially the pitch-reel video generator using Gemini / Veo) is the largest
spend in the system. Any change that adds an LLM call without thought is a regression.

## When to apply

Apply this skill on any Edit/Write/MultiEdit that:

- adds, removes, or modifies a call to `openai.*`, `google.generativeai.*`, `veo`, or
  `perplexity*`
- edits files under `backend/app/services/ai_*` or `backend/app/prompts/`
- changes the pitch-reel generator, the BMC generator, the legal-doc generator, or the
  market-research generator

## What to verify before approving the change

1. **Prompt caching** — every prompt that is reused across calls must use Anthropic's
   `cache_control` (or the equivalent for OpenAI / Gemini). If the change adds a new
   prompt, it must declare a cache strategy. Run `/claude-api` to validate.
2. **Model choice** — the model must match the task: cheapest model that meets the
   quality bar. Don't use Opus for classification, don't use Haiku for legal drafting.
3. **Caching layer** — outputs that are deterministic for a given idea revision must be
   cached in Postgres or a hash-keyed cache, not regenerated on every render.
4. **Feature flag** — if the change adds a new expensive call (e.g. Veo video generation),
   it must be gated by an env-var feature flag so production can disable it without code
   changes.
5. **Cost test** — for new AI surfaces, add a smoke test that asserts the call count and
   token budget per request stays within an expected range.

## Why this matters

A single uncached prompt in a hot path can 10× monthly spend. The product principle isn't
optional — it's the difference between Manifest being viable for early founders and being
priced like enterprise software.
