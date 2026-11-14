# Survey Feedback Ops

Last verified against code on **May 1, 2026**.

Manifest now treats survey feedback as an internal operating loop, not just stored form submissions.

## What Exists

- Storage: `survey_responses` table in Postgres
- Signed-in aggregate view: GraphQL `surveyInsights(windowDays)`
- Internal REST routes:
  - `POST /api/internal/survey-ops/summary`
  - `POST /api/internal/survey-ops/sync-issues`
- Shared backend service: `backend/app/services/operations/survey_ops.py`
- Shared GitHub helper: `backend/app/services/integrations/github_issues.py`
- CLI entrypoint: `backend/scripts/run_survey_issue_sync.py`
- GitHub Actions workflow: `.github/workflows/survey-feedback.yml`
- MCP tools:
  - `summarize_survey_feedback`
  - `create_survey_feedback_github_issues`

## Signals In The Summary

The summary focuses on two decisions:

1. Marketability
- `research_signup_intent_avg`
- `research_follow_up_rate`
- top roles (`top_research_roles`)
- top value props
- top improvement themes (`top_research_barriers` prefers `better_means`, else legacy `biggest_barrier`)
- primary goals / first outputs (`top_research_first_outputs` prefers `goal`, else legacy `first_output`)
- familiarity / trust preferences (`top_research_trust_signals` prefers `familiarity`, else legacy `trust_signal`)

2. Product pull / feasibility
- `product_pmf_very_disappointed_pct` (when the PMF question exists)
- `product_nps_score`
- `product_progress_avg`
- `product_deliverable_avg` (falls back to `satisfaction` average when legacy deliverable score is absent)
- `product_satisfaction_avg`, `product_ease_avg`, `product_satisfaction_topbox_pct`
- `product_ai_quality_avg`
- top benefits
- top tasks
- recurring open-text themes

GraphQL `surveyInsights` exposes the same aggregates for the signed-in insights panel.

## GitHub Issue Generation

`operations/survey_ops.py` converts repeated survey signals into GitHub-ready issue candidates when:

- a trust signal repeats enough times
- a desired first output keeps showing up
- open-text feedback clusters around recurring themes such as research credibility, onboarding clarity, collaboration, performance, or shareability

The sync path de-duplicates against existing open GitHub issues and reuses the shared label bootstrapping logic from `integrations/github_issues.py`.

## UI Surface

The current product surface is a lightweight insights panel inside Account settings:

- Desktop: `frontend/src/features/account/components/AccountPage.tsx`
- iOS shell: `frontend/src/features/ios/pages/IOSAccountPage.tsx`
- Shared panel: `frontend/src/features/feedback/SurveyInsightsPanel.tsx`

This panel is intentionally read-only and low-friction. It shows the aggregate health of Manifest without adding another noisy control surface.

## Operational Notes

- Internal REST routes require `X-Manifest-Agent-Key: <MANIFEST_AGENT_LOOP_SECRET>`.
- Direct GitHub issue creation requires `MANIFEST_GITHUB_TOKEN` or `GITHUB_TOKEN`.
- Repo selection falls back to `MANIFEST_GITHUB_REPO`, then `GITHUB_REPOSITORY`, then `Manifest-Startup/Manifest`.
- The workflow path requires a real `DATABASE_URL` because survey responses live in Postgres.
