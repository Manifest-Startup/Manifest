# Manifest master spec: what exists, what's partial, what's next

Status of the "conversational intelligence, autonomous execution, communication orchestration and living knowledge" spec (pasted 2026-11-22) against the actual code. Verified by reading the code, not the docs. Update this file when a row changes; decisions go in `docs/adr/`.

Last verified: 2026-11-22, `main` at `34b01bb` plus the goals slice (ADR 0020).

## Architecture as built

```
voice (Pipecat, bot.py) ─┐                         ┌─ Open Media (/v1/connected, webhooks)
/mcp Worker + plugin ────┼─► /graphql (Strawberry) ─┼─ Supabase Postgres (ideas, vault_files, goals…)
manifest CLI ────────────┤   default-deny auth,     ├─ OpenAI (each person's own key, ADR 0018)
web app (React) ─────────┘   RBAC FIELD_PERMISSIONS └─ GitHub, Apollo, Gmail compose links
                               │
                    services/<domain> ── workers/generation_worker (in-process, SKIP LOCKED,
                                         + goal sweep every 60 s)
```

Every GraphQL field becomes a CLI command, an MCP tool, a plugin tool and a voice tool through one generated catalog (ADR 0004). New capability = new GraphQL field.

## Requirement map

| Spec area | Status | Where / what's missing |
|---|---|---|
| Voice pipeline, streaming STT/TTS, interruptions | Implemented | `services/voice/live/bot.py` (Pipecat, OpenAI realtime STT + TTS, server VAD). Providers switch only among OpenAI-compatible endpoints (`VOICE_*` env). |
| Conversation modes / intent classification | Partial | Voice prompt rules separate exploring from committing. No classifier and no stored `UserIntent`. |
| Goals as durable entities | **Implemented (slice)** | `goals` table, `services/goals/engine.py`, ADR 0020. |
| Projects | Implemented | Ideas are the project entity (`ideas`, collaborators, versions). Goals can point at an idea. |
| Task decomposition with statuses, deps, verification, risk | **Implemented (slice)** | `goal_tasks` with the spec's statuses, `depends_on`, tier, verification, retries. Plans come from agents or templates; no server-side LLM planner. |
| Durable workflows: retries, waits, checkpoints, resume | **Partial (slice)** | Idempotent `advance` with CAS, bounded retries, crash recovery, webhook and sweep resume. Scheduled triggers and timeouts only for reply waits. |
| Human approval as a workflow state | **Implemented (slice)** | `approval_requests`: scope hash checked at run time, expiry, deny cascades. No standing authorizations yet. |
| Risk tiers 0–3 | **Implemented (slice)** | Declared per capability in `services/goals/capabilities.py`, enforced in `policy.py`. |
| Tool registry with risk/idempotency metadata | Partial | Generated catalog (`readOnly`/`destructive` by name regex) plus `goalCapabilities` (tiers) for goal steps. |
| Service discovery and evaluation engine | Missing | No `ServiceEvaluation` records. ADRs and this file are the manual equivalent. |
| Integration lifecycle states | Partial | `integrations` table has no status column. `connections.py` returns transient states. No health checks except Open Media reconnect. |
| Secrets | Implemented | BYOK keys encrypted (`token_crypto`, `tenant_keys`); Infisical for dev; keys never in chat (catalog exclusions). |
| Open Media messaging, inbox, webhooks | Implemented | `services/integrations/open_media/`. Webhooks now also wake waiting goals. |
| Open Media drafts / delivery status | Missing | Not in Open Media's API. Prepared messages live in the goal step. Needs an open-media change. |
| Outbound only with authorization | **Partial** | Goal sends need an exact-scope approval. `sendMessage` / `replyInInbox` are still ungated (destructive=false); they're direct person-initiated tools. |
| Inbound processing (requests, commitments) | Partial | Replies to a goal's message are recorded as `external_claim` facts. No extraction of requests or commitments from the general inbox. |
| Meeting coordination | Missing | No calendar integration. |
| Knowledge graph, idea concepts | Implemented | `services/ideas/knowledge_graph.py`: derived on read, cited passages, no confidence. |
| Knowledge facts with provenance, confidence, corrections | **Implemented (slice)** | `knowledge_facts` + `services/goals/knowledge.py`. Entity resolution is by normalised handle only. |
| Event model | **Partial (slice)** | `goal_events` (deduped) for goals. No app-wide outbox or bus. |
| Prompt-injection defences | Partial | `<untrusted>` fencing in discovery and goal replies, injection heuristic + event. Inbox and message text reach the voice model unfenced. |
| Project timeline and progress reports | **Implemented (slice)** | `goal.timeline`, `goal.report` (completed / in progress / waiting / needs you / next), `report.spoken`. No web UI. |
| Privacy: erasure | Implemented | `compliance/tenant_purge.py` now includes the five goal tables. Export of goal data: missing. |
| Observability | Partial | JSON logs with OpenTelemetry field names. No traces or metrics pipeline. |

## Security baseline (2026-11-22)

- **CSRF.** `manifest_csrf_token` is set but never compared server-side. Current protection: SameSite=Lax cookies, the CORS allowlist and JSON-only GraphQL. Plan: validate the double-submit header for cookie-authenticated mutations. Low risk today, open item.
- **Ungated sends.** `sendMessage` and `replyInInbox` run without confirmation through any agent holding the person's token. Plan: mark them destructive in the catalog, or route agent-initiated sends through goal approvals.
- **Model-side confirm.** `confirm: true` is a tool-wrapper convention. For goals the server checks an approval record and scope hash; elsewhere it doesn't.
- **Unfenced tool results.** Voice gets inbox text unfenced. Plan: fence `my_inbox` / `inbox_conversation` bodies with `wrap_untrusted`.

## Backlog (in order: risk, then value)

1. Apply migration `20261122120000_goals_tasks_approvals.sql` in production and deploy the goals slice (owner approval).
2. Gate agent-initiated `sendMessage` / `replyInInbox` (destructive in the catalog), and fence inbox text for voice.
3. Server-side CSRF check for cookie-authenticated mutations.
4. Standing authorizations: scoped, expiring, revocable grants (for example "follow-ups to people I've already approved, up to 3 a week") checked in `policy.is_authorized`.
5. A Goals panel in the web app (approvals inbox, timeline). Voice, MCP and the CLI already have it.
6. Open Media drafts API and delivery status (open-media repo), then show goal drafts in Open Media's composer.
7. Inbound extraction: requests, requirements and commitments from replies, as `inferred` facts the person confirms.
8. Calendar capability (CalDAV / Google Calendar) for `meeting.propose` / `meeting.schedule` steps.
9. Data export of goals and facts in the data-subject access request flow; retention policy for `goal_events`.
10. Integration status and health checks (`integrations.status`, last verified).
