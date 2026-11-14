# Product vision — Manifest

Last updated **May 1, 2026**.

This document captures **what Manifest is for** and **how we want to build it**. For canonical AI agent guidance, see `docs/AI_AGENT_BASE_PROMPT.md`. For implementation topology, see `docs/ARCHITECTURE_REFERENCE.md` and root `AGENTS.md`.

## What Manifest is

Manifest is an AI-powered platform that helps people turn **raw ideas** into **investable, operational** startups: structured artifacts (e.g. business model canvas, research, financials, legal and IP-oriented outputs, technical scaffolding) while founders stay in control at a granular level.

**Audience**: People who think in ideas but struggle to commercialize them; **founders and investors** can coexist on the same platform (a user can be both).

## Problems we focus on

- The gap between **ideation and execution**
- Founder overwhelm (legal, compliance, documentation, iteration)
- Motivation, consistency, early validation, and access to capital
- **Premature spend** on incorporation and legal before the idea is ready

## How it works (high level)

- Users capture ideas as notes; AI continuously turns them into structured, linked artifacts.
- Artifacts **update in real time** as the idea changes.
- Outputs should be **auditable**, **versioned**, and **linked** across the workspace.

## Marketplace and social layer

- Ideas are **discoverable** (e.g. feed-oriented discovery).
- Users can follow, react, fund, invest in, or collaborate on ideas, with **clear separation** of investment, ownership, responsibility, and valuation where those concepts apply.
- Investors see analytics, traction signals, and AI-assisted due diligence style outputs.

## Business model (product intent)

- **No heavy upfront paywall** for core ideation.
- Users may choose subscription-style access to keep full equity, or alternate models aligned with the product (e.g. small equity-style participation) — exact mechanics are product/legal and must match live billing code when implemented.

## Design philosophy

- **IDE for startups**: one place where changes propagate.
- **Automation by default**, **manual override** where it matters.
- Minimize friction, bureaucracy, and cognitive load; **do not force incorporation** until it genuinely makes sense.

## Technical principles (directional)

- Portable architecture; schema and workflows live in **code and migrations**.
- Strong **auditability**, traceability, and versioning.
- AI handles **bottom-up** execution; humans retain **top-down** decisions.
- Optional future-facing layers (e.g. blockchain) are **not** requirements for current shipping code unless explicitly built.

## Cultural values

- Transparency over hype; quantification over vague storytelling; automation over busywork; **democratized access** to entrepreneurship.

## Principles for every change

When building features or changing code, optimize for:

1. **Extremely easy to use** — low friction from idea to progress.
2. **Extremely robust** — safe defaults, clear errors, testable behavior.
3. **Inexpensive to run and maintain** — simple operations, clear boundaries, proportional test and doc updates.

These three principles apply alongside the Cursor/project rules in `.cursor/rules/` and `docs/CONTRIBUTING_AGENTS.md`.
