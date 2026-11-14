---
name: manifest-guest-session-guard
description: Guard guest-session TTL, merge, and gating logic. Use whenever an edit touches `backend/app/guest_session*`, `backend/app/services/guest*`, `frontend/src/features/guest*`, or any code that distinguishes guest from authenticated users. Requires updated tests and confirmation that the guest→authenticated merge path still preserves data.
---

# Manifest Guest Session Guard

Manifest exposes a "try-before-signup" surface where a guest gets a real `users` row with a
TTL. On signup, that row is merged into the authenticated account. Bugs in this path lose
founder ideas — the worst possible outcome for the product.

## When to apply

Apply this skill whenever Edit/Write/MultiEdit touches:

- `backend/app/guest_session*`
- `backend/app/services/guest*`
- `frontend/src/features/guest*`, or any component that branches on `isGuest`
- The TTL job, the merge job, or any GraphQL/REST endpoint that gates by guest status

## What to verify before approving the change

1. **TTL** — confirm the guest TTL is still respected. If TTL behaviour changed, surface
   the new value in the PR description.
2. **Merge path** — confirm guest→authenticated merge still:
   - copies all guest-owned ideas, drafts, follows, and AI artifacts
   - does not drop any rows on conflict
   - is idempotent if signup retries
3. **Gating** — every `isGuest`-gated mutation still rejects guests where the original code
   did. Specifically: messaging an investor on an unpublished idea, investing, and any
   payment-adjacent action.
4. **Tests** — there must be at least one test that exercises the merge path end-to-end on
   the changed surface. If none exists, write it.
5. **Frontend** — if a UI component now treats guests differently, confirm the empty state
   and CTA still nudge toward signup, not toward a dead screen.

## Why this matters

A guest losing their idea on signup is a silent retention killer. We do not detect this
in production until users complain on support. Local tests are the cheapest place to catch
it.
