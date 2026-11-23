# 0022. Standing approvals: the person can say "don't ask again" for a few people

- Status: Proposed (2026-11-23).
- Code: `backend/app/services/goals/policy.py` (`grant`, `revoke`, `grants`, `use_standing`), `engine._run`, `backend/app/graphql/resolvers/goals.py` (`standingAuthorizations`, `grantStandingAuthorization`, `revokeStandingAuthorization`); schema `supabase/migrations/20261123120000_standing_authorizations.sql`; web `frontend/src/features/messaging/components/GoalsPanel.tsx`; tests `backend/tests/test_goals.py`, `GoalsPanel.test.tsx`.

## Context

ADR 0020 made every tier 2 step (sending a message) wait for a yes to that exact message. For follow-ups with someone the person already works with, asking every time is the "unnecessary intervention" the master spec asks Manifest to remove. The risk: a broad standing permission is exactly what a prompt-injected or overeager agent would want.

## Decision

- **Narrow by construction.** A standing approval covers one action, today only `message.send`. It names 1–20 Open Media handles, has a weekly cap of 1–20 and lasts 1–90 days. It never covers tier 3 and never covers anyone who isn't named.
- **Only the person can grant one, in the app.** `grantStandingAuthorization` refuses any request that carries an `Authorization` header (CLI, MCP, voice, API keys). It needs the web session cookie, and the CSRF origin check makes that cookie usable only from Manifest's own origin. The tool is excluded from the agent catalog. An agent therefore can't give itself permission, whatever text it reads. Revoking works from anywhere.
- **Same audit trail as a one-off yes.** When a step runs under a standing approval, the engine writes an approved `approval_requests` row with the exact scope and hash, `decided_via = "standing:<id>"`, and an `approval.granted` event. The weekly cap counts those rows. When nothing matches (wrong person, over the cap, expired, revoked), the step asks as before.
- **In the web app.** The approval card offers an unticked "Don't ask again for @x (up to 3 a week, 30 days)". "Sends without asking" lists active grants with this week's use and a Stop button.

## Consequences

- Two goals running at the same moment can each pass the cap check, so a week can exceed the cap by one in a race. The weekly cap is a limit on volume, not a hard security boundary; the recipient list and the expiry are the boundary.
- Erasure deletes `standing_authorizations` with the other goal tables.
- Not yet: grants for other actions, per-goal grants, or a notification when a grant is used.
