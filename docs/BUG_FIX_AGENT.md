# Bug-Fix Agent (v1 — diagnose-only)

Closes the production-test feedback loop one step further. When the
Playwright pipeline files a labeled GitHub issue
(`automated-test, production, severity:*`), this agent:

1. Spins up in a separate, scoped GitHub Actions workflow.
2. Reads the issue body + the suspected files from the local checkout.
3. Asks an LLM for a STRUCTURED root-cause diagnosis (not a patch).
4. Posts the diagnosis as a comment on the issue.
5. Records the attempt in `bug_fix_attempts` so the admin dashboard
   sees what the agent did and how much it cost.

**v1 is intentionally comment-only.** The agent never opens a PR,
never creates a branch, never writes code. v2 graduates it to draft
PRs — the schema and runner are pre-wired for that path.

This is Phase 3a of the agentic-automation roadmap.

## Architecture

```
GitHub issue labeled `automated-test`
        │
        ▼  (GHA `issues.labeled` trigger)
.github/workflows/bug-fix-agent.yml
        │  checks out repo, installs minimal Python deps
        ▼
backend/scripts/run_bugfix_agent.py
   ┌────────────┐   ┌─────────┐   ┌───────────────┐
   │ GitHub API │   │ OpenAI  │   │ Manifest      │
   │ (read +    │   │ (LLM)   │   │ backend       │
   │  comment)  │   │ JSON    │   │ /api/internal/│
   │            │   │ output  │   │ bug-fix/      │
   │            │   │         │   │ attempts      │
   └────────────┘   └─────────┘   └───────────────┘
                                          │
                                          ▼
                            backend/app/services/operations/bug_fix.py
                                          │
                                          ▼
                            Postgres: bug_fix_attempts
```

The runner is intentionally **stand-alone** (no FastAPI imports). The
backend is the source of truth for persistence.

## What's in (Phase 3a)

- `bug_fix_attempts` table
  ([`migration`](../supabase/migrations/20260522210000_bug_fix_attempts.sql)).
- [`backend/app/services/operations/bug_fix.py`](../backend/app/services/operations/bug_fix.py)
  with `record_attempt`, `list_recent_attempts`, `get_attempt_stats`.
- Internal route
  [`POST /api/internal/bug-fix/attempts`](../backend/app/routes/bug_fix_routes.py)
  + `GET /recent` + `GET /stats`. Same `X-Manifest-Agent-Key` auth.
- Stand-alone runner
  [`backend/scripts/run_bugfix_agent.py`](../backend/scripts/run_bugfix_agent.py).
- GitHub Actions workflow
  [`bug-fix-agent.yml`](../.github/workflows/bug-fix-agent.yml).

## Output format

The agent emits one of two GitHub comments — see the production-tested
diagnose / decline templates in `render_diagnosis_comment` and
`render_decline_comment`.

## Safety boundary

- **No write access to code.** Workflow has `contents: read`, not
  `contents: write`. v2 will add `pull-requests: write` only.
- **No direct push to main.**
- **No data exfiltration beyond the issue body.** The LLM prompt
  includes only the issue body + at most 4 file excerpts (capped at
  12KB each).
- **Bounded cost per attempt.** `max_tokens=1500`,
  `temperature=0.2`, response forced to `json_object`.
- **One attempt per label fire** via concurrency key per issue.

## Configuration

| Env / Var | Where | Purpose |
|---|---|---|
| `secrets.OPENAI_API_KEY` | GitHub secret | LLM call. |
| `secrets.MANIFEST_AGENT_LOOP_SECRET` | GitHub secret | Backend `X-Manifest-Agent-Key`. |
| `secrets.GITHUB_TOKEN` | provided by workflow | Read issue + post comment. |
| `vars.MANIFEST_INTERNAL_API_URL` | GitHub repo var | Base URL of the deployed backend. |
| `vars.BUGFIX_AGENT_MODEL` | GitHub repo var (optional) | Defaults to `gpt-4o-mini`. |

## Tests

[`backend/tests/test_bug_fix_service.py`](../backend/tests/test_bug_fix_service.py)
covers: validation, JSONB coercion, issue + action filtering, stats
roll-up. The runner script (`run_bugfix_agent.py`) is the integration
boundary to GitHub + OpenAI; a fixture-based test lands once the
agent has run against real issues.
