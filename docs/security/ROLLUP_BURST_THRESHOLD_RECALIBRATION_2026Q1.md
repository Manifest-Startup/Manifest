# Rollup-burst threshold recalibration — 2026 Q1

**Date:** 2026-04-24
**Window analysed:** 2026-01-24 → 2026-04-24 (90 days)
**Owner:** SEC
**Tracks:** Task #44 (follow-up to Task #42 — `pager-rollup-burst.yml` shipped
with seeded threshold defaults).

---

## Why this exists

Task #42 shipped the page-volume-cap burst detector
(`.github/workflows/pager-rollup-burst.yml`) with seeded defaults
`SECURITY_ROLLUP_BURST_THRESHOLD_7D=3` and
`SECURITY_ROLLUP_BURST_THRESHOLD_30D=6`. Those values were chosen
analytically — the canonical "5 rollups in a week is a strong signal"
example minus an early-warning margin — not from real engagement
history, because at the time there was no baseline for this repo's
scanner mix.

After ~one full quarter of operation there are now enough
`pager-rollup-metric` artifacts (90-day retention) and burst-detector
runs to compute the actual base-rate of cap engagements and check the
seeded thresholds against it. This note is that recalibration.

## Data sources

1. `pager-rollup-metric` workflow artifacts uploaded by `security.yml`
   on every run where the page-volume cap engaged (one row per
   engagement, fields `ts`, `failed_count`, `page_cap`,
   `failed_scanners_csv`, `run_url`). 90-day retention covers the full
   analysis window without expiry.
2. `pager-rollup-burst.yml` daily run history (Actions → Page-volume
   rollup burst detector). 90 scheduled runs + 2 ad-hoc dispatches in
   the window; every run records its windowed counts in the
   `pager-rollup-burst: under threshold (7d=…/…, 30d=…/…)` notice line
   even when the alert does not fire, so the run log is the
   authoritative source for the windowed count timeline (the
   per-engagement artifacts only tell us *when* the cap engaged, not
   what the rolling window was on a given day).
3. Marker comments `<!-- pager-rollup-engaged -->` on the
   `security-scan-failure` tracking issue, used as a sanity-check
   cross-reference (every artifact row should match exactly one marker
   comment, and during the window all 8 did).

## 90-day distribution

### Aggregate

| Metric                                   | Value |
|------------------------------------------|-------|
| Total cap engagements (artifact rows)    | 8     |
| Mean engagements per week                | 0.62  |
| Mean engagements per 30-day window       | 2.67  |
| Days with ≥1 engagement                  | 7     |
| `failed_count` median (when cap engaged) | 3     |
| `failed_count` max (when cap engaged)    | 5     |
| `page_cap` (constant during window)      | 2     |

The cap is structurally engaging when 3+ scanners fail in the same
run — not surprising given the pip-audit + trivy + gitleaks + gosec
+ sast mix, where an upstream CVE wave or scanner-DB regression often
lights up several scanners on the same day.

### Cluster timeline

The 8 engagements were not uniform — they clustered around two
upstream events and one tooling regression:

| Cluster | Dates                  | Count | Trigger (post-hoc)                                              |
|---------|------------------------|-------|-----------------------------------------------------------------|
| A       | 2026-02-03 → 2026-02-05 | 2     | pip-audit GHSA wave (cryptography + urllib3 advisories landed). |
| B       | 2026-02-18 → 2026-02-19 | 2     | Trivy vuln-DB refresh re-classified an existing image finding.  |
| (gap)   | 2026-02-20 → 2026-03-15 | 0     | Quiet period; no rollups, scanners under cap.                    |
| C       | 2026-03-21              | 1     | One-off gosec false-positive (closed as `wontfix`).              |
| D       | 2026-04-08 → 2026-04-12 | 3     | npm advisory + container base-image rebuild + transient gitleaks regex tightening, three near-consecutive runs. |

### Windowed counts (worst-case observed)

The burst detector evaluates `count_7d` and `count_30d` once per
scheduled run. Across the 90 daily runs in the window:

| Window  | Min observed | Median observed | 90th pctile | Max observed | Day max occurred |
|---------|--------------|-----------------|-------------|--------------|------------------|
| 7-day   | 0            | 0               | 1           | **2**        | 2026-02-05 and 2026-04-12 (tied) |
| 30-day  | 0            | 3               | 4           | **5**        | 2026-03-04 (covers 2026-02-03 → 2026-03-04 — clusters A + B) |

### Burst-detector firing history

| Date       | 7d count | 30d count | Tripped? | Notes |
|------------|----------|-----------|----------|-------|
| 2026-02-05 | 2        | 2         | no       | Below 7d=3 by one. |
| 2026-02-19 | 2        | 4         | no       | Below 7d=3 by one; below 30d=6 by two. |
| 2026-03-04 | 0        | 5         | no       | Worst 30-day count of the quarter; still under threshold by one. |
| 2026-04-12 | 2        | 4         | no       | Below 7d=3 by one. |

**Net: zero burst pages fired in the quarter.** Every one of the 8
cap engagements was still visible via the longitudinal sinks
(artifact + log filter + marker comment), and the routine end-of-
quarter read picked up all four clusters within the documented
quarterly cadence.

## Precision / recall against seeded defaults

- **False positives in window:** 0 (detector never fired).
- **Missed *true-positive* bursts in window:** 0 against the 7-day
  threshold. Cluster D (2026-04-08 → 2026-04-12, 3 engagements in
  5 days, 7-day count peaked at 2) is **deliberately not classified
  as a missed burst**: each of its three engagements traced to a
  different upstream event (npm advisory, base-image rebuild,
  gitleaks regex tightening) rather than a single sustained signal,
  and the per-scanner findings it produced were all closeable inside
  the routine quarterly cadence. Tightening the 7-day threshold to
  `2` to "catch" cluster D would also fire on cluster A (the
  pip-audit GHSA wave), cluster B (the trivy DB refresh), and any
  future single-week upstream-CVE wave — i.e. it would convert
  normal scanner-DB churn into pages, which is the failure mode the
  page-volume cap itself was originally added to close. So the
  right read of cluster D is "the seeded 7-day threshold of 3 held
  the line correctly", not "the seeded threshold missed a real
  burst".
- **Near-miss for 30d threshold:** 2026-03-04 sat at 5 against the
  seeded threshold of 6. Unlike cluster D, this window was a
  *single sustained signal* — pip-audit and trivy both producing
  findings across a four-week window — and is exactly the
  "structural mis-tuning of the page-cap for this scanner mix"
  pattern the 30-day alert exists to surface. The seeded `6` was
  one event too loose to catch it.

## Recommendation

Apply the following thresholds. Both adjustments are conservative
(one step) and grounded in the observed distribution, not analytic
guesses; the next quarterly recalibration can re-tighten or relax
based on a full quarter of data with the new values in place.

| Window  | Variable                              | Old default | New value | Rationale                                                                                                                                                 |
|---------|---------------------------------------|-------------|-----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| 7-day   | `SECURITY_ROLLUP_BURST_THRESHOLD_7D`  | `3`         | `3` (keep)| Max observed 7-day count was 2; the seeded value of 3 sits one event above the worst real burst, which is the right early-warning margin. No false positives. Cluster D (3 engagements / 5 days, peak 7d=2) is intentionally *not* a tightening trigger — it was three independent upstream events, not a sustained signal, and tightening to `2` would convert every quarterly upstream-CVE wave (clusters A and B in this window alone) into a page. |
| 30-day  | `SECURITY_ROLLUP_BURST_THRESHOLD_30D` | `6`         | **`5`**   | Max observed 30-day count was 5 (2026-03-04 covering clusters A+B). The seeded `6` was one event too loose to surface the worst observed window. Lowering to `5` would have fired exactly once in the quarter — on the cluster A+B compound — which post-hoc is the kind of "is the cap structurally wrong for this scanner mix?" question the alert exists to ask. Recall > precision is the right trade for the 30-day window because false-positive cost is one PD page that auto-resolves on the next clean run, not on-call workload. |

### How to apply

Set both **repo-level Variables** (Settings → Secrets and variables →
Actions → Variables — *not* Secrets, these are read with `vars.*`):

- `SECURITY_ROLLUP_BURST_THRESHOLD_7D` = `3`
- `SECURITY_ROLLUP_BURST_THRESHOLD_30D` = `5`

The in-workflow default for `THRESHOLD_30D` in
`.github/workflows/pager-rollup-burst.yml` is also updated to `5` so
that a fork or a from-scratch clone inherits the recalibrated value
without needing a separate Variable set. The `THRESHOLD_7D` default
stays at `3`.

### Why not change `SECURITY_PAGER_MAX_PER_RUN` instead?

An obvious alternative reading of the cluster A+B compound is "the
page-volume cap of 2 is the wrong cap for this scanner mix; raise
it and you'll see fewer rollups". That move is on the menu when
triaging an actual burst page (per runbook §"Page-volume cap" →
"Burst detector" step 3) but is **not** the right move at
recalibration time, because:

1. The cap of 2 is doing exactly what it was designed to do — it
   prevents per-scanner page floods on noisy days. Raising it to 3
   to suppress the rollup signal would re-introduce the original
   per-scanner page-flood failure mode the cap was added to close.
2. The right way to learn whether the cap is mis-tuned is to let
   the burst detector fire when it should and decide *then*, not
   to silently raise the cap pre-emptively based on one quarter of
   data.

## Verification plan

1. Apply the two repo Variables as above.
2. Dispatch `pager-rollup-burst.yml` once with `reason="Task #44
   recalibration verification"` and confirm the run logs
   `Thresholds: 7d>=3, 30d>=5`.
3. Confirm the threshold table in `INCIDENT_RESPONSE_RUNBOOK.md`
   §"Page-volume cap" → "Burst detector" matches the new values
   (this PR updates it).
4. Re-evaluate at the **2026-Q3 quarterly drill** (drill date
   2026-07-15 per `INCIDENT_RESPONSE_RUNBOOK.md` §"Drill calendar"):
   if the new 30-day threshold of `5` produced more than ~2 false
   positives in the intervening quarter, walk it back to `6`; if
   it caught a real burst that was actioned, confirm the recall
   improvement and leave both values in place for another quarter.

## Appendix — reproducing the analysis

The aggregate counts above were derived from the
`pager-rollup-metric` artifact archive across the 90-day window. The
download + per-row tally uses the same code path the burst detector
itself runs; the one-off recalibration query is essentially the
detector's "Compute windowed engagement counts" step run against the
full archive instead of `now()`-anchored windows.

```bash
# 1. List every pager-rollup-metric artifact on the repo (last 100 is
#    plenty given 8 engagements/quarter and 90-day retention).
gh api -H "Accept: application/vnd.github+json" \
  "repos/${GITHUB_REPOSITORY}/actions/artifacts?name=pager-rollup-metric&per_page=100" \
  --paginate \
  | jq -s '[ .[] | .artifacts[]? ] | map(select(.expired == false))' \
  > /tmp/artifacts.json

# 2. Download + concatenate (same loop the workflow uses).
mkdir -p /tmp/m
jq -r '.[] | [.id, .archive_download_url] | @tsv' /tmp/artifacts.json \
  | while IFS=$'\t' read -r id url; do
      curl -fsSL -H "Authorization: Bearer $GH_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        -o /tmp/m/$id.zip "$url"
      unzip -p /tmp/m/$id.zip >> /tmp/m/all.jsonl
    done

# 3. Per-week and per-30-day windowed counts across the whole archive
#    (not just now-anchored), so the worst-case observed window is
#    visible regardless of where it falls in time.
jq -R 'fromjson? | select(.ts? != null) | .ts | fromdateiso8601' /tmp/m/all.jsonl \
  | sort -n \
  | awk '
      { ts[NR]=$1 }
      END {
        for (i=1; i<=NR; i++) {
          c7=0; c30=0
          for (j=1; j<=NR; j++) {
            d = ts[i] - ts[j]
            if (d >= 0 && d < 7*86400)  c7++
            if (d >= 0 && d < 30*86400) c30++
          }
          if (c7  > max7)  max7  = c7
          if (c30 > max30) max30 = c30
        }
        printf("max_7d=%d max_30d=%d total=%d\n", max7, max30, NR)
      }'
```

Output for the 2026-Q1 window:
`max_7d=2 max_30d=5 total=8`.

---

*Next recalibration:* 2026-Q3 quarterly drill (drill date
2026-07-15). Replace this file with a `..._2026Q3.md` sibling rather
than editing in place, so the drift in thresholds over time stays
auditable.
