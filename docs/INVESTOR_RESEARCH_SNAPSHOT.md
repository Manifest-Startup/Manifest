# Investor-facing research snapshot (anonymized)

Use this as a **methodology and narrative checklist** when sharing discovery survey learnings with stakeholders. Do **not** commit raw `survey_responses` exports, emails, or identifiable quotes to public repositories.

## What to include

1. **Context**: who was invited, channels, date range, sample size (n), incentives if any.
2. **Aggregates only**: role mix, top value props, improvement themes (`better_means`), primary goals, product satisfaction / NPS bands, recurring theme tags.
3. **So what**: 3–5 bullets mapping learnings to the next build or GTM bets.

## Data sources (Manifest)

- **In-app**: GraphQL `surveyInsights(windowDays)` (Account → Survey insights panel).
- **Internal API**: `POST /api/internal/survey-ops/summary` with `X-Manifest-Agent-Key`.
- **CLI JSON**: from repo root, with `DATABASE_URL` set:

```bash
cd backend && PYTHONPATH=. python scripts/export_survey_investor_snapshot.py > /path/to/private/snapshot.json
```

Optional: `SNAPSHOT_WINDOW_DAYS=90` (default).

The script prints **structured aggregates** only (same family as `survey_ops_service.get_summary` without issue candidates). Build slides or a one-pager in a **private** doc or PDF; keep the JSON out of public GitHub.

## Field alignment

Discovery surveys store answers under keys such as `goal`, `better_means`, `familiarity`, `value_prop`, and product feedback under `satisfaction`, `ease_score`, `progress_score`, `nps`. The backend summary prefers these keys when present and falls back to legacy keys for older rows.
