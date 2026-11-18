---
name: manifest-documents
description: "Generate and read Manifest's startup documents: Business Model Canvas, pitch deck, product requirements document (PRD) and provisional patent draft, plus partner discovery. Use when a person wants a plan, deck, PRD, patent draft or BMC for an idea, or wants to know whether generation finished."
---

# Startup documents

The goal is to get the founder from idea to execution, so every idea should end up with real, specific documents. There are two writers:

- **Manifest, on the person's own OpenAI key** (Account → AI settings). Use it when `ai_key_status` shows `configured: true`.
- **You, the agent they are talking to.** When there is no key, do not stop and do not settle for Manifest's generic template text: write the documents yourself and save them. No key is needed for this.

## Choose the writer
1. Read the idea with `idea`; thin input gives thin documents, so ask one or two sharp questions if the description is vague.
2. `ai_key_status`. If configured, use **Generate with Manifest** below (check `my_cost_preflight` first and mention large costs).
3. If not configured, or the person asks you to write it, use **Write it yourself**.
4. If documents already exist and look like generic templates (phrases like "time-constrained operators dealing with a fragmented workflow"), they were made without a key: offer to rewrite them.

## Write it yourself (no key needed)
1. `document_guide` with the document type (`business_model_canvas`, `pitch_deck`, `product_requirements_document`, `provisional_patent`, `similar_ideas`). It returns Manifest's own system prompt and structure: follow them exactly so the result fits the app.
2. Write the document in Markdown, specific to this idea: its customer, numbers, risks. Research with web search when you can (competitors, market size, prior art) and cite sources; never invent companies, figures or patents.
3. If the idea already has a version of that document, snapshot first with `create_idea_version`.
4. Save it with `save_idea_document` (ideaId, documentType, content). For the canvas you can also save single sections with `save_bmc_section` when the person refines one.
5. Order that works: `similar_ideas` → `business_model_canvas` → `pitch_deck` → `product_requirements_document` → `provisional_patent` (only if there's something novel to protect; it's a draft for a patent attorney).
6. Tell the person what you wrote and what to check, then update their local vault (manifest-vault skill) if they keep one.

## Generate with Manifest
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
