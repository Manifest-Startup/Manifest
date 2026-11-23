# Manifest master spec: what exists, what's partial, what's next

Status of the "conversational intelligence, autonomous execution, communication orchestration and living knowledge" spec (pasted 2026-11-22) against the actual code. Verified by reading the code, not the docs. Update this file when a row changes; decisions go in `docs/adr/`.

Last verified: 2026-11-22: goals slice live (PR #111, migration applied), plus the follow-ups below.

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
| One memory for every agent | **Implemented** | `Memory/` and `Conversations/` vault files, `services/memory/store.py`, `recall`/`remember` everywhere (voice, `/mcp`, CLI, plugin skills), Account → Memory, ADR 0021. |
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
| Outbound only with authorization | Implemented | Goal sends need an exact-scope approval checked by the server. Direct `sendMessage` / `replyInInbox` are confirm-first in voice, `/mcp` and the CLI (the web composer is the person typing). |
| Inbound processing (requests, commitments) | Partial | Replies to a goal's message are recorded as `external_claim` facts. No extraction of requests or commitments from the general inbox. |
| Meeting coordination | Missing | No calendar integration. |
| Knowledge graph, idea concepts | Implemented | `services/ideas/knowledge_graph.py`: derived on read, cited passages, no confidence. |
| Knowledge facts with provenance, confidence, corrections | **Implemented (slice)** | `knowledge_facts` + `services/goals/knowledge.py`. Entity resolution is by normalised handle only. |
| Event model | **Partial (slice)** | `goal_events` (deduped) for goals. No app-wide outbox or bus. |
| Prompt-injection defences | Partial | Fencing for discovery, goal replies and every voice tool result carrying other people's text (inbox, conversations, comments); injection heuristic + event. MCP agents get raw text (their own harness decides). |
| Project timeline and progress reports | **Implemented (slice)** | `goal.timeline`, `goal.report` (completed / in progress / waiting / needs you / next), `report.spoken`. Web: the Messages page lists goals with pending approvals (Send / Don't send) and status (`GoalsPanel.tsx`). The full timeline is in the API only. |
| Privacy: erasure | Implemented | `compliance/tenant_purge.py` now includes the five goal tables. Export of goal data: missing. |
| Observability | Partial | JSON logs with OpenTelemetry field names. No traces or metrics pipeline. |

## Security baseline (2026-11-22)

- **CSRF.** Fixed. `middleware/origin_check.py` refuses cookie-signed-in `POST /graphql` requests whose `Origin` (or `Referer`) isn't Manifest's own. Bearer clients are unaffected. The `manifest_csrf_token` double-submit header is still not required, because several app calls don't send it yet.
- **Sends.** Goal sends need a server-checked approval. Direct sends are confirm-first for agents. An agent that ignores the handshake and calls GraphQL directly with the person's token can still send; that is the person's own delegated access.
- **Model-side confirm.** Outside goals, `confirm: true` is still a tool-wrapper convention, not a server record.

## Backlog (in order: risk, then value)

1. First live outreach send, to a recipient the owner names.
2. Standing authorizations: scoped, expiring, revocable grants (for example "follow-ups to people I've already approved, up to 3 a week") checked in `policy.is_authorized`.
3. Goal timeline and facts in the web app (the approvals and status are on the Messages page).
4. Open Media drafts API and delivery status (open-media repo), then show goal drafts in Open Media's composer.
5. Inbound extraction: requests, requirements and commitments from replies, as `inferred` facts the person confirms.
6. Calendar capability (CalDAV / Google Calendar) for `meeting.propose` / `meeting.schedule` steps.
7. Data export of goals and facts in the data-subject access request flow; retention policy for `goal_events`.
8. Integration status and health checks (`integrations.status`, last verified).
9. Send the CSRF header from every app call, then require it as well as the Origin check.
