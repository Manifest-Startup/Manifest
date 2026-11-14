# Manifest surveys — discovery vs product experience

The product ships two **separate** in-app flows. They answer different decisions and use different question types (aligned with common practice: **discovery / JTBD** vs **satisfaction, effort, and feature feedback**).

| Track | Route | Who | `survey_type` in DB | Purpose |
|-------|--------|-----|---------------------|---------|
| **A — Discovery & positioning** | `/research` | Public (often pre-signup) | `research` | Who visitors are, jobs-to-be-done, alternatives, messaging clarity, signup intent. **Not** product quality ratings. |
| **B — Product experience** | `/feedback/survey` | Signed-in users | `product_feedback` | Outcomes, ease, feature usage, AI output quality, NPS, priorities. **Not** website positioning for cold traffic. |

**Why two surveys:** Discovery questions bias badly if the respondent has not used the product; product questions bias badly if you mix them with “what should our homepage say?” Combining them confuses respondents and muddies analysis. The UI and marketing copy now **name the split** at the landing section, hero link, first screen of each flow, and thank-you states.

## Design principles behind the questions

- Prefer **behavior, blockers, and desired outcomes** over abstract opinions where possible.
- Keep most steps **single-choice** so the data is easier to segment and prioritize.
- Use open text sparingly and make it **optional + short** to reduce drop-off.
- Branch on **founder/operator vs investor/advisor** context instead of forcing one generic flow.
- For the signed-in survey, include one explicit **product-market-fit pull** question ("How would you feel if you could no longer use Manifest?") in addition to standard product UX questions.

Optional PostHog events (when configured): `survey_completed`, `survey_cta_clicked`, `survey_prompt_shown`, `survey_prompt_dismissed` with `track: "a" | "b"` and `surface` (e.g. `landing_hero`, `landing_section`, `research_page`, `feedback_page`, `account`, `ios_account`, `modal`).

## Operationalization

Survey responses are no longer "write-only."

- Storage: Postgres `survey_responses`
- Signed-in aggregate view: GraphQL `surveyInsights(windowDays)` used by the Account settings insights panel
- Internal ops routes:
  - `POST /api/internal/survey-ops/summary`
  - `POST /api/internal/survey-ops/sync-issues`
- Scheduled workflow: `.github/workflows/survey-feedback.yml`
- CLI: `backend/scripts/run_survey_issue_sync.py`

Repeated trust, onboarding, document-quality, collaboration, discovery, and performance signals can now become GitHub-ready issue candidates automatically through the shared survey ops service.

---

## Track A — Discovery & positioning (`/research`)

**Goal:** Segment audience (founder vs investor-side), understand current workflows and tools, surface the biggest "idea to reality" bottlenecks, test positioning and trust, measure signup intent, optional research call.  
**Length:** ~5–7 minutes (varies by role; investors skip founder workflow block).

### A1. Welcome

**Eyebrow:** Discovery & positioning  
**Title:** Help us understand what you need — before you judge the product  
**Body:** Clarify that this is **market and customer discovery** (not product-quality). Manifest overview + time estimate + data use.

### A2. Role (single choice)

Which best describes you?

- Founder (building a company)
- Aspiring founder
- Investor
- Advisor or mentor
- Student
- Other (short text branch)

**Branching:** **Investor** or **Advisor or mentor** → investor lens block after familiarity; skip **stage** and skip **tools + friction** (founder-centric).

### A3. Stage (single choice)

What stage best fits you?

- Idea only / exploring
- Pre-seed
- Seed or later
- Not applicable / prefer not to say

**Branching:** Only if role is Founder, Aspiring founder, or Student.

### A4. Primary goal today (single choice)

What brought you to Manifest today?

- Validate whether an idea is worth pursuing
- Turn an idea into investor- or team-ready artifacts
- Compare an idea against the market or similar companies
- Find startups to invest in, advise, or follow
- Browse discovery / pitch-style content
- General curiosity
- Other (short text)

### A5. AI familiarity (single choice)

How familiar are you with AI tools for startup or knowledge work?

- Very familiar — I use AI tools regularly for work
- Somewhat — I have tried them a few times
- Limited — I mostly use traditional docs, slides, or spreadsheets
- New — I am exploring what AI can do for startups
- Prefer not to say

### A6a. Investor lens — evaluation focus (single choice)

When you first evaluate an early-stage opportunity, what do you weight most?

- Team, narrative, and founder fit
- Market size, timing, and dynamics
- Traction, metrics, or milestones
- Product, demo, or technical proof
- Financial model and unit economics
- It depends — I do not have a single default

### A6b. Investor lens — dealflow (single choice)

Where do most of the companies you evaluate come from?

- Warm introductions from my network
- Events, pitch days, or accelerators
- Platforms, databases, or deal-flow tools
- Social feeds or short-form content (e.g. pitch-style reels)
- Inbound applications or cold outreach
- Other / mixed sources

### A6c. Investor lens — materials gap (optional paragraph)

What is usually missing or weak in first-pass founder materials?

### A7. Current tools (multi-select) — non-investor only

How do you capture and develop startup ideas today?

- Google Docs / Word
- Notion or similar wiki
- ChatGPT / other AI chat
- Spreadsheets / Airtable
- Slides / Canva
- Whiteboard / FigJam / Miro
- Mostly in my head
- Other (short text field)

### A8. Friction (optional paragraph) — non-investor only

What is the biggest friction in how you develop or capture ideas today?

### A9. Biggest blocker (single choice) — non-investor only

What most often blocks you from turning an idea into something real?

- Knowing whether the idea is actually worth pursuing
- Turning rough thinking into a clear story or plan
- Doing market research or finding comparable companies
- Scoping the product or roadmap
- Legal, incorporation, or admin overhead
- Finding co-founders, collaborators, or advisors
- Getting customer or investor interest
- Keeping momentum and following through consistently
- Other / mixed blockers

### A10. First output (single choice) — non-investor only

If Manifest proved itself in the first session, what should it help create first?

- A one-page idea summary
- A market / comparable research brief
- A business model canvas
- A pitch deck
- A PRD or roadmap
- Legal starter documents or a formation checklist
- A financial model or assumptions sheet
- A shareable founder page for collaborators or investors

### A11. Job success (optional paragraph)

If a tool like Manifest worked perfectly for you, what would be true a month from now?

### A12. Value prop (single choice)

On the website today, which promise matters most to you?

- AI turns a rough idea into structured startup documents
- Market / comparable research that sharpens or validates the idea
- Investor- or share-ready outputs without starting from scratch
- Collaboration with co-founders or contributors
- Discovery, pitch reels, or the startup social layer
- One workspace instead of a pile of tools
- Not sure yet

### A13. Trust signal (single choice)

What would make Manifest feel credible enough to rely on?

- Citations or links behind claims and research
- Editable assumptions and calculations
- A clear explanation of what AI generated vs. what the user provided
- Outputs that already look polished enough to share
- Proof that real founders or investors use it successfully
- A visible history of changes, collaborators, or iteration
- Not sure yet

### A14. Clarity / trust (optional paragraph)

What felt unclear, overstated, or hard to believe about Manifest?

### A15. Improvement vector (single choice)

Thinking about your workflow, where would “meaningfully better” show up first?

- Speed — from rough idea to credible artifacts faster
- Structure — less blank-page friction; clearer sections
- Quality — stronger first drafts I can ship or share
- Trust — I understand what the AI did and can verify it
- Collaboration — easier to loop in co-founders or advisors
- Discovery — finding or comparing ideas and founders
- Momentum — easier to keep moving instead of stalling out
- Consolidation — fewer tools to juggle
- Not sure yet

### A16. Signup intent (Likert 1–5)

**Founder-side title:** How likely are you to create a free account this week?  
**Investor-side title:** How likely are you to create a free account this week to browse ideas, reels, or founder workspaces?

### A17. Research call (Y/N + conditional email)

Open to a 20-minute video call? Yes → email.

### A18. Consent (checkboxes)

- Required: agree to use responses to improve the product.
- Optional: contact for follow-up research or early access.

### A19. Thank you

Reinforce that **product experience feedback** is a separate survey after using the workspace (Account / prompts).

---

## Track B — Product experience (`/feedback/survey`)

**Goal:** Measure **experienced** outcomes, effort, feature use, AI usefulness, closeness to a shareable result, product pull, conditional reels/collab depth, NPS, open priorities.  
**Length:** ~6–9 minutes; reels detail is **skipped** when outputs already include Pitch Reels or publishing.

### B1. Welcome

**Eyebrow:** Product experience  
**Title:** Help us improve what you actually use in Manifest  
**Body:** Explicit contrast with `/research` discovery survey; both can be taken but serve different decisions.

### B2. Session depth (single choice)

How much time have you spent in Manifest so far?

- First real session
- 2–5 working sessions
- 6–15 working sessions
- More than 15 sessions

### B3. Primary task (single choice)

What were you mainly trying to accomplish in your latest visits?

- Generate or refine documents (deck, PRD, canvas, patent, etc.)
- Capture or structure my idea in the editor
- Browse Pitch Reels or published ideas
- Message someone or collaborate on an idea
- Publish or share an idea externally
- Mostly exploring — no single goal yet

### B4. Progress outcome (Likert 1–5 + optional line)

Has Manifest helped you make progress on an idea or project? Optional: “What changed?” one line.

### B5. Main benefit (single choice)

What is the biggest benefit you are getting from Manifest today?

- It gives shape to rough ideas faster
- It creates drafts instead of starting from a blank page
- It helps with market research, comparables, or adjacent ideas
- It makes sharing with collaborators or investors easier
- It helps discover ideas, founders, or opportunities
- It gives momentum or confidence to keep moving
- I am not getting enough value yet

### B6. Outputs used (multi-select)

Same capability list as implemented in the app (editor, deck, PRD, patent, canvas, similar ideas, publishing/reels, messaging, collaboration, voice, API, none).

### B7. AI quality (Likert 1–5 or N/A)

How useful were AI-generated documents as a starting point? If no doc generation yet → N/A path.

### B8. Shareability / actionability (Likert 1–5)

How close did Manifest get to something the user would actually share, publish, or act on?

### B9. Task ease (Likert 1–5)

How easy was it to accomplish what you came here to do? (CES-style effort.)

### B10. Product pull (single choice)

If you could no longer use Manifest, how would you feel?

- Very disappointed
- Somewhat disappointed
- Not disappointed
- I have not used it enough yet

### B11. Usability (two optional short text)

Easiest part; most confusing part.

### B12. Pitch Reels

- If usage includes **Pitch Reels feed** or **Publishing an idea / pitch reel** → go straight to reels helpful + open feedback.
- Else → Y/N “Aside from what you selected, have you used Pitch Reels?” then conditional detail.

### B13. Collaboration & messaging

Did you try inviting others or messaging? If no, optional blocker text.

### B14. NPS (0–10)

### B15. Top priority (paragraph)

One thing to build or fix first to help the user move an idea forward (optional to submit empty).

### B16. Thank you

Acknowledge dual participation if they also took discovery survey.

---

## Branching summary (implementation checklist)

| Condition | Action |
|-----------|--------|
| Track A: Investor / Advisor | Skip stage; skip tools + friction; show investor focus, dealflow, optional gap |
| Track A: Other roles | Show stage (if applicable), tools, friction, biggest blocker, first output |
| Track B: Outputs include reels or publishing | Skip “have you used reels?” gate; show reels detail |
| Track B: No doc generation | N/A on AI quality |

---

## Privacy note (paste into form intros)

We use responses to improve Manifest. Do not submit passwords or confidential third-party data. Respect the product-level privacy choice stored through `/api/privacy/consent`, and keep survey-specific consent copy aligned with the broader tracking and outreach settings.
