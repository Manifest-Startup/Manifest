# Incident Response Runbook

## Trigger event log

| Date | Event | Surfaces | Driving findings | Status |
|------|-------|----------|------------------|--------|
| 2026 (pre-program kickoff) | Spoofed email apparently sent from `manifeststartup.com`. Reported by the founder. Indicates SPF/DKIM/DMARC are absent, misconfigured, or in `p=none` so any third party can impersonate the domain. Blast radius unknown — depends on which recipients acted on the message. | Outbound email / domain authentication | SEC-069 (primary). Cross-link: SEC-009, SEC-015, SEC-018, SEC-048 (the credential-capture chain it enables — §5.8 of THREAT_MODEL.md). | Open — DMARC enforcement + log review pending |
| 2026-07-01 (scheduled, pending) | Quarterly scanner-failure pager drill (`security.yml::pager`) — first run of the cadence introduced by `.github/workflows/scanner-pager-drill.yml`. Drill procedure: §"Scanner-failure paging" → "Verify the wiring (drill)". Replace this row with the actual outcome (issue #, PD/Opsgenie incident URL, ack latency, auto-close confirmed) once executed. | Outbound paging webhook (PagerDuty / Opsgenie) | SEC follow-up to Task #37 (pager wiring). | Pending — drill reminder issue auto-files on 2026-07-01 |
| 2026-07-08 (scheduled, pending) | Quarterly governance-drift pager drill (`governance-verify.yml::pager`) — first run of the cadence introduced by `.github/workflows/governance-pager-drill.yml`. Drill procedure: §"Security-drift paging" → "Verify the wiring (drill)". Offset one week from the scanner-failure drill row above so a quarter-start outage of the shared paging webhook cannot silently consume both reminders. Replace this row with the actual outcome (issue #, PD/Opsgenie incident URL, ack latency, auto-close confirmed) once executed. | Outbound paging webhook (PagerDuty / Opsgenie) | SEC follow-up to Task #37 (pager wiring). | Pending — drill reminder issue auto-files on 2026-07-08 |
| 2026-07-15 (scheduled, pending) | Quarterly rollup-burst pager drill (`pager-rollup-burst.yml`) — first run of the cadence introduced by `.github/workflows/rollup-burst-drill.yml`. Drill procedure: §"Page-volume cap" → "Burst detector" → "Verify the wiring (drill)". Offset two weeks from the scanner-failure drill (1st) and one week from the governance-drift drill (8th) so a quarter-start outage of the shared paging webhook cannot silently consume all three reminders. Replace this row with the actual outcome (injection path used, issue #, PD/Opsgenie incident URL, ack latency, auto-close confirmed) once executed. | Outbound paging webhook (PagerDuty / Opsgenie) | SEC follow-up to Task #42 (burst detector). | Pending — drill reminder issue auto-files on 2026-07-15 |

When a new trigger event occurs, append a row above and link the SEC-### items it impacts. Do not delete rows; mark resolved in the Status column.

## Severity matrix

The audit pipeline tags every event with a `severity` value drawn from the
table below. Paging, escalation, and the SLAs in the next section are all
keyed off this column.

| Severity | Definition | Example events | Response SLA | Paging |
|----------|------------|----------------|--------------|--------|
| `info` | Routine telemetry. Stored, never paged. | `login_success`, `signup_success`, `webauthn_register_success` | None — analytics only | No |
| `low` | Single-actor noise that is suspicious only in aggregate. | `login_failed`, `session_ip_change`, `password_reset_requested` | Aggregated review next business day | No |
| `medium` | Deserves human review; may be benign. | `login_blocked_lockout`, `mfa_enabled`, `api_key_rotated`, `account_deletion_requested` | Acknowledge within 1 business day | Email / Slack |
| `high` | Strong signal of compromise or abuse. | `mfa_disabled`, `session_stolen_suspected`, `sso_oidc_id_token_rejected`, `role_changed`, `detection_brute_force`, `detection_impossible_travel`, `detection_mass_export`, `detection_priv_escalation` | Acknowledge within 30 minutes; mitigate within 4 hours | On-call page |
| `critical` | Probable active compromise or integrity break. | `detection_audit_chain_break`, mass account compromise, confirmed secret leak in production | Acknowledge within 15 minutes; declare incident immediately | On-call page + leadership notification |

## Regulatory notification timers

These clocks start the moment an incident is **confirmed** (i.e. severity is
escalated to "incident"), not at first detection. Document detection time
**and** confirmation time in the post-incident review so the auditor can see
both numbers.

| Regime | Trigger | Notification window | Owner | Notes |
|--------|---------|---------------------|-------|-------|
| GDPR Art. 33 | Personal data breach affecting EU/UK data subjects | **72 hours** to the lead supervisory authority | Privacy lead | Notify even if scope is unknown; supplement with detail later. |
| GDPR Art. 34 | Breach likely to result in high risk to data subjects | "Without undue delay" to affected users | Privacy lead | In practice ≤ 72 h from confirmation. |
| HIPAA Breach Notification Rule | Unsecured PHI affecting US residents | **60 days** to affected individuals; ≥ 500 individuals also requires HHS + media notification | Compliance lead | Track per-individual count. |
| CCPA / CPRA | Unauthorised access to personal information of California residents | "In the most expedient time possible and without unreasonable delay" | Privacy lead | Align with GDPR 72 h to keep one process. |
| US state breach laws | Per-state thresholds (typically 30–90 days) | State-specific | Compliance lead | Maintain a per-state matrix in the privacy program docs. |
| Customer DPA commitments | Contractually-defined notification SLA | Per-contract (typically 24–72 h) | Account owner + Compliance lead | Check the customer's signed DPA before each notification. |

## Trigger conditions

Use this runbook when any of the following occur:

- Suspected account takeover or credential abuse.
- Unexpected access to generated patent PDFs or private founder data.
- Elevated 401/403/429 rates suggesting abuse.
- Dependency audit failure for a critical vulnerability in production code.
- Data deletion/export failure affecting customer trust or privacy obligations.
- A report of email being received that purports to be from `@manifeststartup.com` but was not sent by us, or any DMARC aggregate report showing a high volume of unauthenticated mail using the domain.
- A `detection_*` event of severity `high` or above appears in `security_audit_events`.
- `audit_verifier.verify_chain` reports any break (treat as `critical` until proven otherwise — chain breaks indicate either a bug or active tampering).

## Initial response

1. Declare the incident and assign an incident commander.
2. Record the detection time, confirmation time, reporter, and suspected impact.
3. Preserve evidence:
   - `security_audit_events` rows for the affected user / IP / session window.
   - The JSONL audit stream files under `AUDIT_SINK_PATH` (off-host copy).
   - Application logs and CI runs.
   - Relevant DB rows (idea, document, session).
4. Contain the issue:
   - Revoke affected sessions or API keys.
   - Pause risky integrations if needed.
   - Disable vulnerable paths behind the edge or feature flags.
5. Open the regulatory timer matrix above and identify which clocks now apply.

## Investigation checklist

- Identify affected users, ideas, sessions, or API keys.
- Run `audit_verifier.verify_chain_window(since=<incident_start>)` and confirm
  the chain is intact across the incident window. A `detection_audit_chain_break`
  during the same window automatically escalates the incident to `critical`.
- Review recent security audit events for the affected user, filtering by
  severity ≥ `medium`:
  - `login_success`
  - `password_reset_requested` / `password_reset_completed`
  - `mfa_enabled` / `mfa_disabled`
  - `session_revoked` / `session_stolen_suspected`
  - `account_deletion_requested`
  - `role_changed`
  - any `detection_*` row
- Correlate with deployment timing, dependency updates, and infrastructure changes.
- Determine whether customer notification is required (consult the timer matrix).

## Communication

- Internal updates every 30 minutes during active mitigation.
- Customer communication should state:
  - What happened.
  - What data or features were affected.
  - What Manifest has done already.
  - What customers should do next, if anything.
- Regulator communication: prepare a single source-of-truth incident brief
  before notifying the first regulator so subsequent notifications stay
  consistent.

## Recovery

- Restore normal service only after the root cause is mitigated.
- Verify:
  - login/session flows work,
  - MFA still validates,
  - PDF authorization checks enforce ownership,
  - CI dependency audit gates are passing,
  - `audit_verifier.quick_self_check()` returns an intact chain for the last
    24 hours.

## Post-incident review

- Timeline (detection time → confirmation time → containment → recovery → notification).
- Root cause.
- Blast radius.
- Customer impact.
- Detection gaps.
- Preventive actions with owners and due dates.
- Confirmation that all regulatory timers were met (or, if missed, why and
  what changes prevent recurrence).

## Security-drift paging (`security-drift` label / `governance-verify`)

The `.github/workflows/governance-verify.yml` job runs daily at 07:00 UTC
and on `workflow_dispatch`. Any failing lint (tag-only `uses:`, Dockerfile
digest pin, required-check name lint, gate-flip schedule, gate
`continue-on-error` schedule, or — once blocking on `2026-08-02` — the
live ruleset diff) opens or updates a single GitHub issue labelled
`security-drift` **and** POSTs a paging event so the on-call rotation is
notified off-hours instead of relying on issue email subscriptions.

### Wiring the on-call pager

Pick one of the supported wirings and set the corresponding repo secrets
under **Settings → Secrets and variables → Actions**.

**PagerDuty Events API v2 (recommended for a real on-call rotation):**

1. In PagerDuty, create or pick the *Security On-Call* service. Under
   **Integrations**, add an **Events API v2** integration. Copy the
   *Integration Key* (a 32-char hex string).
2. Set the following repo secrets:
   - `SECURITY_PAGER_WEBHOOK = https://events.pagerduty.com/v2/enqueue`
   - `SECURITY_PAGER_ROUTING_KEY = <integration-key-from-step-1>`
3. The workflow will POST a `event_action: trigger` event with
   `dedup_key = governance-verify/security-drift/<owner>/<repo>`. PD
   collapses subsequent triggers with the same dedup key into the
   existing incident, matching our single-issue convention.
4. When a later run goes green, the workflow auto-closes the GitHub
   issue **and** POSTs `event_action: resolve` with the same
   `dedup_key`, clearing the PD incident.

**Opsgenie / Slack / generic webhook (alternative):**

1. In Opsgenie, create a *Custom JSON* integration on the security
   on-call team. Copy the integration's webhook URL (the URL itself
   embeds the API key — there is no separate routing key).
2. Set `SECURITY_PAGER_WEBHOOK = <opsgenie-webhook-url>` and leave
   `SECURITY_PAGER_ROUTING_KEY` unset.
3. The workflow POSTs the legacy generic shape
   `{title, run_url, tracking_issue, severity, source, dedup_key,
   event_action}`. Configure the Opsgenie integration to map
   `dedup_key → alias` so duplicates collapse and `event_action:
   resolve` (sent on green runs only when `SECURITY_PAGER_ROUTING_KEY`
   is set) closes the alert.

When **both** secrets are unset the step still files the GitHub issue
and emits a workflow `::warning::`. This is the bootstrap state — fine
for evidence, slow for response — and must not be the steady state once
an on-call rotation exists.

### Acknowledge a `security-drift` page

1. Open the linked GitHub Actions run (in the PD/Opsgenie payload as
   `links[].href` / `run_url`) and read the failing step's annotations.
   The job log is the authoritative source — the issue body only lists
   *likely* causes.
2. Open the linked `security-drift` tracking issue, assign yourself,
   and ack the page in PD/Opsgenie. SLA is **30 minutes** (high
   severity per the matrix above).
3. Identify which lint failed:
   - **Tag-only `uses:` / Dockerfile `FROM`** — a recent PR introduced
     an unpinned reference. Revert or repin (SEC-073).
   - **Required-check name lint** — a workflow/job was renamed without
     updating `BRANCH_PROTECTION.md` §1.2, or vice-versa. Re-align
     names (SEC-058/SEC-070).
   - **Gate-flip schedule lint** — a gate is >14d past its flip date.
     Either flip the gate (remove the matching `continue-on-error:
     true # remove to flip to blocking (SEC-###)` marker in
     `.github/workflows/security.yml`) or formally waive the row in
     `FINDINGS_BACKLOG.md` with a dated rationale.
   - **Live ruleset diff** — the live GitHub branch-protection ruleset
     drifted from `BRANCH_PROTECTION.md`. Either reapply the document
     in **Settings → Rules** or update the document if the divergence
     is intentional.

### Resolve a `security-drift` page

1. Land the fix on `main` (or, for a rollback, revert the offending
   commit).
2. Trigger a fresh `governance-verify` run via **Actions → Governance
   – branch-protection & gate-flip drift → Run workflow** instead of
   waiting for the 07:00 UTC schedule.
3. On green **on the default branch** (`main`), the workflow
   auto-closes the `security-drift` issue and (PD only) auto-resolves
   the incident. A green run from a feature branch deliberately does
   **not** auto-close — it only proves that branch is clean, not that
   the fix has landed. Confirm in PD/Opsgenie that the incident moved
   to *resolved* after the next default-branch run; if not, resolve it
   manually and file a follow-up to fix the resolve-event wiring.
4. If the resolve event needs to be sent manually (e.g. webhook
   transient failure logged as `::warning::Pager resolve POST
   failed`):
   ```sh
   curl -fsS -X POST https://events.pagerduty.com/v2/enqueue \
     -H 'Content-Type: application/json' \
     -d '{"routing_key":"<key>","event_action":"resolve",
          "dedup_key":"governance-verify/security-drift/<owner>/<repo>"}'
   ```

### Verify the wiring (drill)

After (re)wiring the secrets, prove end-to-end paging from a throwaway
branch — never on `main`:

1. On a branch, append a transient regression that the *required-check
   name lint* will catch (e.g. add `- \`bogus-check-that-doesnt-exist\``
   to `BRANCH_PROTECTION.md` §1.2).
2. Push the branch and run **Actions → Governance … → Run workflow**
   against it.
3. Verify within ~5 min:
   - A new `security-drift` issue is filed (or an existing one is
     commented on).
   - The on-call receives a real page.
4. Revert the branch, re-run the workflow against `main`, and confirm
   the issue auto-closes and the PD incident auto-resolves.
5. Record the drill date and outcome as a row in the *Trigger event
   log* above.

### Drill cadence

The drill above must be exercised **at least once per calendar
quarter** so a rotated webhook secret, a disabled Opsgenie
integration, or a `dedup_key` shape that no longer matches the
receiver's alias mapping is caught by us, not by the next real
branch-protection / gate-flip drift incident.

The cadence is automated by
`.github/workflows/governance-pager-drill.yml`, which fires at 13:00
UTC on the 8th of January, April, July, and October — one week
offset from the scanner-failure pager drill (which fires on the 1st
of the same months) so a quarter-start outage of the shared paging
webhook does not silently consume both reminders in the same
window. Each run opens (or re-comments on) a `security-drift-drill`
tracking issue containing the checklist mirror of the steps above.
The workflow only files the reminder — a human still has to execute
the drill on a throwaway branch and tick the boxes.

If a previous quarter's drill issue is still open when the next
reminder fires, the workflow comments on it with a `::warning::`
instead of opening a duplicate; treat that warning as a missed
drill and escalate to the security owner.

Ad-hoc drills (e.g. immediately after rotating
`SECURITY_PAGER_WEBHOOK` / `SECURITY_PAGER_ROUTING_KEY` or after
on-call handover) should be triggered via **Actions →
Governance-drift pager drill (quarterly) → Run workflow** with a
`reason` set, rather than waiting for the next scheduled tick.

## Scanner-failure paging (`security-scan-failure` label / `security.yml`)

The `.github/workflows/security.yml` workflow runs the daily
dependency / code / container scanners (`lockfile-drift`,
`secret-scan`, `python-sast`, `frontend-sast`, `python-sca`,
`frontend-sca`, `license-scan`, `container-scan`) at 06:00 UTC plus on
every push and PR. A trailing `pager` job (`needs:` every scanner)
inspects two signals per scanner job:

- **Job result** — `needs.<job>.result == 'failure'`. This catches
  already-blocking jobs (`lockfile-drift`, `secret-scan`) and any
  advisory gate that has since been flipped to blocking per the
  gate-flip schedule.
- **Advisory `findings` output** — every advisory scanner job exposes
  a `findings` job output that lists the names of any scanner steps
  whose `outcome == 'failure'` (i.e. real findings) but whose
  `continue-on-error: true` left the job result `success`. This is
  what makes the pager fire on a brand-new HIGH+ CVE in (for example)
  `pip-audit`, `npm audit`, or `trivy` *before* the gate-flip
  schedule moves them to blocking. Without it, an overnight CVE
  would only surface in the run log.

On the daily schedule, on `workflow_dispatch`, and on pushes to `main`
the pager opens or updates a single GitHub issue labelled
`security-scan-failure` **and** POSTs one paging event per failing
scanner so on-call learns about findings the same way they learn about
governance drift — not by waiting for the next PR's required check to
go red. The issue body lists the advisory step names per job (for
example: `python-sast (advisory findings: bandit,semgrep)`).

The wiring reuses the `SECURITY_PAGER_WEBHOOK` / `SECURITY_PAGER_ROUTING_KEY`
secrets configured for the `governance-verify` pager above — a single
on-call rotation handles both classes of page. Follow the same
"Wiring the on-call pager" instructions in §"Security-drift paging" to
provision the secrets; nothing additional is needed for scanner-failure
paging to start firing once those are set.

### How scanner pages differ from governance-drift pages

| Aspect           | `security-drift` (governance-verify.yml) | `security-scan-failure` (security.yml)                                                                                  |
|------------------|------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| Tracking issue   | one per drift episode                    | one per scanner-failure episode                                                                                        |
| `dedup_key`      | one per repo (`governance-verify/security-drift/<repo>`) | one **per scanner** (`security.yml/<scanner>/<repo>`) — independent CVE classes page independently                     |
| PagerDuty incidents | one                                   | up to one per failing scanner (so a pip-audit CVE and a trivy image CVE produce two incidents, ack/resolved separately), capped at `SECURITY_PAGER_MAX_PER_RUN` (default 2) per run — exceeding the cap collapses to a single `rollup` incident with per-scanner detail in `custom_details` (see "Page-volume cap" below) |
| Triage focus     | repo configuration drift                  | CVE / SAST finding triage against the named scanner                                                                    |
| Auto-resolve     | green run on `main`                      | green run on `main`; resolves are sent for **all** known scanner dedup keys (PD treats already-resolved keys as no-ops) |

### Page-volume cap

A bad upstream day can simultaneously trip multiple scanners for what
is effectively *one* event — e.g. a widely-used transitive dep ships a
HIGH+ CVE that fires `python-sca`, `frontend-sca` (incl. `osv-scanner`),
and `container-scan` at the same time. Without a cap, on-call would
take 4+ near-simultaneous pages for a single upstream cause, hit
PagerDuty per-service rate limits, and burn out the rotation.

The `pager` job therefore enforces a **per-run page cap**:

- The cap is read from the `SECURITY_PAGER_MAX_PER_RUN` repository
  variable (Settings → Secrets and variables → Actions → Variables).
  Default is **2** if unset. Must be a positive integer; a malformed
  value fails the `pager` job loudly rather than silently disabling
  paging.
- When the failing-scanner count is **at or below** the cap, the
  existing per-scanner pages fire as documented above — one PD
  incident per scanner, each with its own
  `security.yml/<scanner>/<repo>` `dedup_key` so ack/resolve stays
  granular.
- When the failing-scanner count **exceeds** the cap, the per-scanner
  pages are deliberately suppressed and a single rollup incident is
  fired instead with:
  - `dedup_key` = `security.yml/rollup/<repo>` (so multi-day bad
    upstream events collapse onto the same rolled-up incident across
    daily re-runs).
  - `payload.summary` = `Security scanner failure: <N> scanners (rollup)`.
  - `payload.component` = `rollup`.
  - `payload.custom_details.failed_scanners` = JSON array of
    `{scanner, advisory_findings}` so receivers render structured
    detail rather than a single concatenated string. The same list
    also appears as a CSV in `failed_scanners_csv` for receivers that
    only key on flat strings.
  - `payload.custom_details.failed_count` and `page_cap` so on-call
    can see at a glance how many scanners were collapsed and what
    threshold tripped the rollup.
  - The same `tracking_issue` link as the per-scanner shape — the
    GitHub issue body still lists every failed scanner with its
    advisory-step detail, so triage breadth is not lost.

The per-scanner `dedup_key`s are still meaningful: under the cap they
provide ack/resolve granularity (acking a `python-sca` page leaves a
concurrent `container-scan` page firing). Above the cap, the rollup
incident is the single ack/resolve handle for the whole episode and
on-call walks the failed-scanner list inside `custom_details` /
the tracking issue. Auto-resolve on a green run on `main` resolves
every known per-scanner `dedup_key` *and* the `rollup` `dedup_key`,
so a stuck rollup incident cannot outlive the fix.

To raise or lower the cap (e.g. temporarily set it to `1` during a
known-noisy upstream period, or to `8` to disable rollup entirely),
edit the `SECURITY_PAGER_MAX_PER_RUN` variable. No code change or
re-deploy is needed; the next `security.yml` run picks it up.

#### Reading the rollup signal

The cap engaging is a tuning signal — if it engages frequently, the
default of `2` is too low (real per-scanner regressions are getting
hidden behind the rollup); if it never engages, the default may be
high enough to defeat its purpose. Three sinks are emitted from the
`pager` job's rollup branch every time the cap engages, all carrying
`failed_count`, `page_cap`, and the failed-scanner list so the same
row reconciles across them:

1. **Workflow log filter** — the rollup branch emits a structured
   `::notice title=pager-rollup-engaged::failed_count=N page_cap=M
   scanners=<csv> run_url=<url>` annotation. In the Actions UI:
   **Actions → Security … → filter "pager-rollup-engaged"** to walk
   recent engagements; in any log-export sink, filter on the literal
   string `pager-rollup-engaged`.
2. **Artifact `pager-rollup-metric`** — a JSONL row is appended to
   `reports/pager-rollup-metric.jsonl` and uploaded as the
   `pager-rollup-metric` workflow artifact (90-day retention). To
   aggregate across a quarter:
   ```bash
   gh run list --workflow security.yml --limit 200 --json databaseId \
     --jq '.[].databaseId' | while read id; do
       gh run download "$id" -n pager-rollup-metric -D /tmp/m/"$id" \
         2>/dev/null || true
     done
   jq -s '. | length, (group_by(.failed_count) | map({n: .[0].failed_count, c: length}))' \
     /tmp/m/*/pager-rollup-metric.jsonl
   ```
   (The first number is total cap engagements over the window; the
   array shows the distribution by failed-scanner count.)
3. **Tracking-issue marker** — every engagement appends a comment to
   the `security-scan-failure` tracking issue beginning with the HTML
   marker `<!-- pager-rollup-engaged -->`. The whole history is
   greppable across both open and closed issues via:
   ```bash
   gh search issues 'label:security-scan-failure pager-rollup-engaged' \
     --state all --json number,title,url
   ```

Quarterly tuning cadence: the security owner reviews these three
signals during the quarterly verification pass (see
`FINDINGS_BACKLOG.md` §"Quarterly verification") and either keeps the
default `2`, raises/lowers it, or files a new finding if rollups are
demonstrably hiding regressions.

#### Burst detector

The three sinks above are passive — they only get read on the
quarterly cadence. Without an active alert, a sustained spike in cap
engagements (the canonical "five rollups in a week" example) silently
becomes the new normal because nobody is looking until the next
quarterly review. By then, real per-scanner regressions have been
hiding behind the rollup for up to 90 days.

`.github/workflows/pager-rollup-burst.yml` closes that detection gap.
It runs daily at 07:00 UTC (one hour after `security.yml`'s 06:00 UTC
re-scan, so today's `pager-rollup-metric` artifact is uploaded and
indexed before we count it) and:

1. Lists every `pager-rollup-metric` artifact on the repo via
   `GET /repos/.../actions/artifacts?name=pager-rollup-metric`,
   filters to non-expired artifacts created in the last ~31 days,
   downloads each via its `archive_download_url`, and concatenates
   the per-run JSONL rows into a single stream.
2. Counts rows whose `ts` field falls inside a rolling 7-day window
   and a rolling 30-day window.
3. If **either** count is at or above its threshold, opens (or
   appends a comment to) a single `pager-rollup-burst` tracking issue
   and pages via `SECURITY_PAGER_WEBHOOK` /
   `SECURITY_PAGER_ROUTING_KEY` with `dedup_key =
   pager-rollup-burst.yml/burst/<repo>` (so a multi-day burst
   collapses onto one PD incident).
4. When both counts fall back below threshold, the next scheduled
   run auto-closes the tracking issue and sends an
   `event_action:resolve` (PD treats already-resolved keys as no-ops,
   so this is safe to fire on every clean run).

Default thresholds (override via repo Variables — Settings → Secrets
and variables → Actions → Variables — without a code change).
Recalibrated **2026-04-24** against the first 90 days of real
`pager-rollup-metric` artifacts; see
[`ROLLUP_BURST_THRESHOLD_RECALIBRATION_2026Q1.md`](ROLLUP_BURST_THRESHOLD_RECALIBRATION_2026Q1.md)
for the distribution data and reasoning. Next recalibration scheduled
for the 2026-Q3 drill (2026-07-15).

| Window  | Variable                               | Default | Rationale                                                                                                                                                                                  |
|---------|----------------------------------------|---------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 7-day   | `SECURITY_ROLLUP_BURST_THRESHOLD_7D`   | `3`     | Held at `3` on 2026-04-24 recalibration: max observed 7-day count over 2026-Q1 was `2`, so `3` sits one event above the worst real burst — early-warning margin with zero false positives. |
| 30-day  | `SECURITY_ROLLUP_BURST_THRESHOLD_30D`  | `5`     | Lowered `6` → `5` on 2026-04-24 recalibration: worst observed 30-day count was `5` (Feb 2026 pip-audit + trivy compound) and the seeded `6` would have missed it; recall > precision here. |

A malformed Variable (non-integer, < 1) **fails the workflow loudly**
rather than silently disabling burst detection — the same posture
`security.yml` takes for `SECURITY_PAGER_MAX_PER_RUN`. A typo in the
Variable should not turn into "the burst alert quietly stops firing",
which is precisely the failure mode this detector exists to close.

To verify the wiring out-of-band, dispatch the workflow manually from
**Actions → Page-volume rollup burst detector → Run workflow** with
a `reason` (e.g. "threshold tuning"). The dispatch reason is recorded
on the tracking-issue body for audit.

When triaging a `pager-rollup-burst` page:

1. Open the linked tracking issue. The body contains the windowed
   counts, the per-run breakdown of last-7-day engagements (with run
   URLs), and a pointer back to this section.
2. Walk the listed runs and the longitudinal sinks above
   (`pager-rollup-metric` artifact, `pager-rollup-engaged` log
   filter, `security-scan-failure` tracking-issue marker comments)
   to decide whether the burst is (a) the page-volume cap being too
   tight, (b) a sustained upstream-CVE pattern, or (c) a transient
   noise spike.
3. Adjust `SECURITY_PAGER_MAX_PER_RUN` (raise to widen the cap),
   `SECURITY_ROLLUP_BURST_THRESHOLD_*` (raise if the burst threshold
   itself is mis-tuned), or file a new scanner-specific finding.
   Comment the decision on the issue and close it; the detector will
   re-open a fresh issue on the next burst.

##### Verify the wiring (drill)

After (re)wiring the secrets — or after editing
`SECURITY_ROLLUP_BURST_THRESHOLD_7D` /
`SECURITY_ROLLUP_BURST_THRESHOLD_30D` — prove end-to-end burst paging.
Pick **one** of the two synthetic-burst injection paths below per
drill (running both at once makes it harder to read which signal
tripped the detector):

1. **Throwaway-branch JSONL injection** (preferred — exercises the
   artifact-download + windowed-count code path end-to-end):
   - On a throwaway branch (never on `main`), append
     `SECURITY_ROLLUP_BURST_THRESHOLD_7D` synthetic rows to
     `reports/pager-rollup-metric.jsonl` with `ts` set to timestamps
     inside the rolling 7-day window. Each row must carry the same
     field shape `security.yml` writes (`ts`, `failed_count`,
     `page_cap`, `failed_scanners_csv`, `run_url`) so the burst-issue
     body renders cleanly. Mark each `run_url` with a `#drill`
     fragment so the synthetic rows are obvious in the rendered
     issue.
   - Push the branch and run **Actions → Security … → Run workflow**
     against it once so the synthetic rows are uploaded as a
     `pager-rollup-metric` artifact (the burst detector reads from
     artifacts, not the working tree).
   - Run **Actions → Page-volume rollup burst detector → Run
     workflow** against `main`. The detector reads repo-wide
     artifacts so the dispatch ref doesn't change the count, but the
     auto-resolve step is gated on `main`.
2. **Threshold-Variable knockdown** (faster — exercises the
   threshold-validation + paging code paths but not the artifact
   pipeline):
   - Note the current value of `SECURITY_ROLLUP_BURST_THRESHOLD_7D`
     (Settings → Secrets and variables → Actions → Variables) so it
     can be restored exactly.
   - Temporarily set `SECURITY_ROLLUP_BURST_THRESHOLD_7D=1` (or
     `SECURITY_ROLLUP_BURST_THRESHOLD_30D=1` if the 7-day count is
     currently `0`).
   - Run **Actions → Page-volume rollup burst detector → Run
     workflow** against `main` with a `reason` of "quarterly drill".

Verify within ~5 min:

- A new `pager-rollup-burst` issue is filed (or an existing one is
  commented on).
- On-call receives a real page whose `dedup_key` is
  `pager-rollup-burst.yml/burst/<owner>/<repo>` and whose `component`
  is `rollup-burst` — distinct from the per-scanner /
  `security.yml/rollup/<repo>` keys fired by `security.yml` itself.
  Receiver alias mapping must keep all three classes separate; a
  silent collapse here defeats the burst alert.

Roll back the synthetic burst, then confirm the next clean detector
run auto-closes the `pager-rollup-burst` issue and (PD only)
auto-resolves the matching incident:

- **JSONL-injection path:** delete the throwaway branch (the
  synthetic-row artifact ages out of the 30-day window on its own).
- **Threshold-knockdown path:** restore the noted-down value of the
  threshold Variable, then re-dispatch the burst detector.

Record the drill date, injection path used, issue # filed, PD /
Opsgenie incident URL, ack latency, and auto-close confirmation in
the *Trigger event log* at the top of this runbook (same log as the
scanner-failure and security-drift drills).

The drill above must be exercised **at least once per calendar
quarter** so a rotated webhook secret, a typo'd
`SECURITY_ROLLUP_BURST_THRESHOLD_*` Variable, or a `dedup_key` shape
that no longer matches the receiver's alias mapping is caught by us,
not by the next sustained-rollup incident — the exact failure mode
the burst alert exists to prevent for its own upstream.

The cadence is automated by
`.github/workflows/rollup-burst-drill.yml`, which fires at 13:00 UTC
on the 15th of January, April, July, and October (offset two weeks
from `scanner-pager-drill.yml` and one week from
`governance-pager-drill.yml`, so a quarter-start outage of the shared
paging webhook cannot silently consume all three reminders in the
same window). Each run opens (or re-comments on) a
`pager-rollup-burst-drill` tracking issue containing the checklist
mirror of the steps above. The workflow only files the reminder — a
human still has to execute the drill and tick the boxes.

If a previous quarter's drill issue is still open when the next
reminder fires, the workflow comments on it with a `::warning::`
instead of opening a duplicate; treat that warning as a missed drill
and escalate to the security owner.

Ad-hoc drills (e.g. immediately after rotating
`SECURITY_PAGER_WEBHOOK` / `SECURITY_PAGER_ROUTING_KEY`, after
editing a `SECURITY_ROLLUP_BURST_THRESHOLD_*` Variable, or after
on-call handover) should be triggered via **Actions → Rollup-burst
pager drill (quarterly) → Run workflow** with a `reason` set, rather
than waiting for the next scheduled tick.

### Acknowledge a `security-scan-failure` page

1. Open the linked GitHub Actions run (in the PD/Opsgenie payload as
   `links[].href` / `run_url`) and read the failed scanner step's
   annotations / SARIF. The `component` field on the PD payload (and
   the per-scanner `dedup_key`) tells you which scanner fired.
2. Open the linked `security-scan-failure` tracking issue (a single
   issue lists every failed scanner in the day's run), assign
   yourself, and ack the page in PD/Opsgenie. SLA is **30 minutes**
   (high severity per the matrix above) — same as `security-drift`.
3. Triage by scanner. The issue body lists per-scanner pointers; the
   short version:
   - **`lockfile-drift`** — re-run the install in the affected stack
     (`pip install -r backend/requirements.txt && pip check` /
     `npm ci` in `frontend/`) and commit the regenerated lockfile.
     Drift here invalidates every downstream scan (SEC-074).
   - **`secret-scan`** — gitleaks found a credential. Rotate
     immediately per `SECRET_ROTATION.md` *before* touching the
     commit (rotation is the actual mitigation; scrubbing history is
     defence in depth) (SEC-060).
   - **`python-sast` / `frontend-sast`** — a Bandit / Semgrep / ESLint
     HIGH+ finding. Open the SARIF in **Security → Code scanning** to
     read the rule and fix the call site, or — if the finding is a
     known false positive — baseline it with a dated rationale in the
     scanner's ignore file (SEC-061).
   - **`python-sca` / `frontend-sca`** — pip-audit / npm audit /
     osv-scanner reports a HIGH+ CVE in a pinned dependency. Bump and
     re-lock (lockfile-drift will refuse to merge a partial bump). If
     no fix is available upstream, file a dated waiver row in
     `FINDINGS_BACKLOG.md` and link it from the tracking issue
     (SEC-059).
   - **`license-scan`** — a transitive dep landed on the
     disallowed-license list (`GPL`/`LGPL`/`AGPL`/`SSPL`/`Commons-Clause`/`BUSL-1.1`).
     Replace the dep or get legal sign-off to update the allowlist in
     `RELEASE_PLAYBOOK.md` (SEC-059).
   - **`container-scan`** — Hadolint / Trivy flagged a HIGH+ image
     CVE (Trivy, `--severity CRITICAL,HIGH --ignore-unfixed`) or a
     Dockerfile lint regression (Hadolint). Bump the base-image
     digest in `backend/dockerfile` (or `frontend/dockerfile`) or fix
     the Dockerfile rule (SEC-062).

### Resolve a `security-scan-failure` page

1. Land the fix on `main` (dependency bump + regenerated lockfile,
   SAST suppression with rationale, base-image digest bump, etc).
2. Trigger a fresh `security.yml` run via **Actions → Security … →
   Run workflow** instead of waiting for the 06:00 UTC schedule.
3. On green **on the default branch** the `pager` job auto-closes the
   `security-scan-failure` issue and (PD only) auto-resolves every
   per-scanner incident. Confirm in PD/Opsgenie; if any incident is
   still firing, resolve it manually with the per-scanner dedup_key:
   ```sh
   curl -fsS -X POST https://events.pagerduty.com/v2/enqueue \
     -H 'Content-Type: application/json' \
     -d '{"routing_key":"<key>","event_action":"resolve",
          "dedup_key":"security.yml/<scanner>/<owner>/<repo>"}'
   ```
   where `<scanner>` is one of `lockfile-drift`, `secret-scan`,
   `python-sast`, `frontend-sast`, `python-sca`, `frontend-sca`,
   `license-scan`, `container-scan`, or `rollup` (the latter when the
   per-run page-volume cap collapsed the day's failures into a single
   rollup incident — see §"Page-volume cap" above).

### Verify the wiring (drill)

After (re)wiring the secrets, prove end-to-end scanner paging from a
throwaway branch — never on `main`:

1. On a branch, introduce a transient regression that any scanner
   will catch. Two recommended targets:
   - **Already-blocking path** — add a duplicate / conflicting dep
     to `backend/requirements.txt` so `pip check` exits non-zero,
     tripping the blocking `lockfile-drift` job. Validates the
     `needs.<job>.result == 'failure'` code path.
   - **Advisory-finding path** — pin a known-vulnerable old version
     of a Python dep (e.g. an old `requests` with a published CVE)
     in `backend/requirements.txt` to make `pip-audit` exit non-zero.
     The `python-sca` job stays green (advisory) but its `findings`
     output lists `pip-audit`, exercising the per-step paging path
     that fires before the gate-flip date.
   `secret-scan` is a poor drill target because it requires
   committing a real-looking secret.
2. Push the branch, then run **Actions → Security … → Run workflow**
   against it.
3. Verify within ~10 min:
   - A new `security-scan-failure` issue is filed (or an existing one
     is commented on) listing the failed scanner.
   - The on-call receives a real page whose `component` /
     `dedup_key` names the failed scanner.
4. Revert the branch, re-run the workflow against `main`, and confirm
   the issue auto-closes and the matching PD incident auto-resolves.
5. Record the drill date and outcome in the *Trigger event log*
   above (same log as the `security-drift` drill).

### Drill cadence

The drill above must be exercised **at least once per calendar
quarter** so a rotated webhook secret, a disabled Opsgenie
integration, or a per-scanner `dedup_key` shape that no longer
matches the receiver's alias mapping is caught by us, not by the
next real CVE.

The cadence is automated by
`.github/workflows/scanner-pager-drill.yml`, which fires at 13:00
UTC on the 1st of January, April, July, and October. Each run
opens (or re-comments on) a `security-scan-failure-drill`
tracking issue containing the checklist mirror of the steps
above. The workflow only files the reminder — a human still has
to execute the drill on a throwaway branch and tick the boxes.

If a previous quarter's drill issue is still open when the next
reminder fires, the workflow comments on it with a `::warning::`
instead of opening a duplicate; treat that warning as a missed
drill and escalate to the security owner.

Ad-hoc drills (e.g. immediately after rotating
`SECURITY_PAGER_WEBHOOK` / `SECURITY_PAGER_ROUTING_KEY` or after
on-call handover) should be triggered via **Actions →
Scanner-failure pager drill (quarterly) → Run workflow** with a
`reason` set, rather than waiting for the next scheduled tick.

## Tabletop drill cadence

A tabletop exercise must be run at least quarterly. The most recent drill
record lives at `docs/security/INCIDENT_TABLETOP_2026Q2.md`. After every
drill, file follow-ups for any gap exposed and link them in the runbook.
