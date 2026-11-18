---
name: manifest-documents
description: "Generate and read Manifest's startup documents: Business Model Canvas, pitch deck, product requirements document (PRD) and provisional patent draft, plus partner discovery. Use when a person wants a plan, deck, PRD, patent draft or BMC for an idea, or wants to know whether generation finished."
---

# Startup documents

All generation uses the person's own OpenAI key and counts toward their monthly AI cap.

## Before generating
1. `ai_key_status`: if no key is saved, stop and tell the person to add one in Account → AI settings.
2. `my_cost_preflight`: shows whether they're near their cap. Mention the cost when it's large.
3. Make sure the idea has a real description (`idea`); thin input gives thin documents.

## Generate
- Several documents at once, durably: `enqueue_background_tasks` (ideaId, documentTypes, optional idempotencyKey) returns a job; poll `generation_job` with its jobId every few seconds until it finishes, and tell the person it's running meanwhile.
- One document, waiting for it: `generate_pitch_deck`, `generate_product_requirements_document`, `generate_provisional_patent` (an optional `description` steers the result).
- Business Model Canvas: `bmc_sections` reads it; `regenerate_bmc_section` (one section by sectionName) or `regenerate_all_bmc_sections` rebuilds it.

## Read
- `pitch_deck`, `product_requirements_document`, `provisional_patent` read the latest version for an idea; `patents` lists every patent draft.
- Summarise first; offer the full text. A provisional patent is a draft for a patent attorney, not legal advice.

## Partners
- `run_partner_discovery` (owned ideas) finds potential partners; `partner_candidates` lists them; `approve_partner_candidate` approves one. Describe who they are and why before approving.

## Agent runs
- `my_agent_runs` shows recent AI runs with status, cost and duration, useful when something seems stuck.
- `available_skills` lists the skills Manifest's own agents can apply.
