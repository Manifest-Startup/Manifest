# 0015. Shared notes highlight statements that contradict each other

- Status: Accepted (2026-11-19). Builds on [0008](0008-shared-notes-are-edited-live-together.md) (live notes) and [0010](0010-sources-are-highlighted-in-the-note.md) (decorations, never edits).
- Code: `frontend/src/features/ideas/knowledge/contradictions.ts`, `frontend/src/features/common-ui/TextArea.tsx`, `.manifest-contradiction` in `frontend/src/index.css`

## Context

When several people write one idea note, they disagree: one writes that a cold room holds 400 crates, another that it holds 250; one that farmers rent it, another that they buy it. In running prose those collisions are easy to miss.

## Decision

- **Detect locally, without a model.** Two sentences are compared only when they are about the same thing (two or more shared content words). They contradict when they give the same unit different numbers (`400 crates` / `250 crates`, `$5` / `$8`, `10%` / `20%`), when one denies the other (`needs grid power` / `does not need grid power`), or when they use opposite words (rent/buy, monthly/yearly, B2B/B2C, free/paid; word forms match, so "rented" counts as "rent"). It runs as people type, costs nothing, works offline and needs no OpenAI key.
- **Show it gently.** Both sentences get a soft lilac wash with a dotted underline; hovering one shows a small card: what it disagrees with and why ("400 crates vs 250 crates"). Decorations only: the shared document is never changed.
- **Shared notes only**, where people write together; the switch follows the live session, so it turns on when a note becomes shared.

## Consequences

- Heuristic: it misses contradictions that need understanding ("we target hospitals" / "our customers are farmers") and can flag a plan as a disagreement. Pairs that are usually a plan ("free" first month vs a "fee") are left out on purpose. An AI check could add depth later, on the person's own key.
- It does not know who wrote each sentence (live notes don't keep authorship), so it also flags one person contradicting themselves.
