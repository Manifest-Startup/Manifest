# Autopilot Playbook

This is the prompt context the autopilot loop carries into every run. The
weekly `autopilot-retro.yml` job rewrites this file from the run journal so the
loop gets better over time. Keep it concise and concrete — it is read by an
agent, not just humans.

> The main loop is forbidden from editing this file (it's on the denylist).
> Only the human-reviewed retro job may change it.

## What good work looks like here

- The **smallest** change that fully resolves the issue. Prefer one file.
- Tests proportionate to risk; update `docs/` when a public contract changes
  (GraphQL schema, REST route, MCP contract, env var, CLI).
- Conventional Commit subject derived from the issue (`fix:` for bug /
  `automated-test`, `feat:` otherwise).

## Issue types — current guidance

| Type | Signal | Approach |
| --- | --- | --- |
| `automated-test` (live-site / smoke) | Has a failing test + suspected files | Reproduce the assertion, fix the narrowest cause, keep the test green. |
| `bug` | Repro steps or stack trace | Fix root cause, add a regression test. |
| Docs / SEO / link issues | Low risk | Often a one-file change; still run lint. |
| `feature` / `enhancement` | May be large | Decline (`AUTOPILOT_DECLINE:`) if it can't fit the size cap; leave a note for a human to split it. |

## When to decline

Print a line starting with `AUTOPILOT_DECLINE:` and make no changes when:

- The fix needs a DB/schema migration or a change to a denylisted path.
- The issue is ambiguous or lacks enough signal to act safely.
- The smallest correct change exceeds the file/line size cap.

## Learnings (auto-maintained by the retro job)

_No runs recorded yet. The first weekly retro will populate this section with
which issue types succeed, which get guard-rejected, and recurring failure
causes._
