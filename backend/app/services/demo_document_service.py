import html
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

STOP_WORDS = {
    "a",
    "about",
    "after",
    "all",
    "also",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "between",
    "both",
    "build",
    "business",
    "can",
    "could",
    "create",
    "creates",
    "creating",
    "customers",
    "for",
    "from",
    "get",
    "has",
    "have",
    "helps",
    "ideas",
    "into",
    "its",
    "more",
    "need",
    "our",
    "platform",
    "product",
    "service",
    "startup",
    "that",
    "the",
    "their",
    "them",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "use",
    "users",
    "using",
    "with",
    "would",
}


DOMAIN_PROFILES = [
    {
        "name": "Education and Talent",
        "keywords": {
            "student",
            "students",
            "mentor",
            "mentors",
            "teacher",
            "teachers",
            "learning",
            "course",
            "school",
            "university",
            "career",
            "talent",
        },
        "partners": [
            "universities, bootcamps, and cohort operators",
            "subject-matter experts who can act as mentors",
            "employers that want warm, job-ready talent pipelines",
        ],
        "channels": [
            "campus ambassadors and cohort partnerships",
            "content aimed at students and career switchers",
            "referral loops between mentors and successful learners",
        ],
        "resources": [
            "mentor supply quality controls",
            "curriculum and matching data",
            "trust, ratings, and session analytics",
        ],
        "costs": [
            "mentor acquisition and support",
            "matching and communication infrastructure",
            "community management and learner success",
        ],
        "revenue": "Paid mentorship subscriptions, cohort fees, and employer sponsorship packages.",
    },
    {
        "name": "Healthcare and Wellness",
        "keywords": {
            "health",
            "healthcare",
            "patient",
            "patients",
            "clinic",
            "clinical",
            "medical",
            "wellness",
            "therapy",
            "therapist",
            "doctor",
        },
        "partners": [
            "providers, clinics, and care networks",
            "compliance, privacy, and claims partners",
            "device or data integrations needed for care delivery",
        ],
        "channels": [
            "provider-led distribution and pilots",
            "condition-specific communities and associations",
            "partnerships with employers or insurers",
        ],
        "resources": [
            "compliance and audit trails",
            "care workflow templates",
            "outcome reporting and patient engagement data",
        ],
        "costs": [
            "clinical and compliance oversight",
            "secure infrastructure and integrations",
            "customer success for provider deployments",
        ],
        "revenue": "Per-seat or per-clinic subscriptions with optional implementation and reporting fees.",
    },
    {
        "name": "Fintech and Operations",
        "keywords": {
            "finance",
            "fintech",
            "payment",
            "payments",
            "invoice",
            "bank",
            "cash",
            "budget",
            "equity",
            "cap",
            "table",
            "accounting",
            "bookkeeping",
        },
        "partners": [
            "banking, payment, and accounting integrations",
            "compliance and risk partners",
            "channel partners serving SMB operators",
        ],
        "channels": [
            "direct outbound to finance-heavy SMBs",
            "partner channels with accountants and operators",
            "SEO around painful back-office workflows",
        ],
        "resources": [
            "financial workflow automation",
            "data accuracy and reconciliation logic",
            "compliance-ready reporting",
        ],
        "costs": [
            "payment and data infrastructure",
            "risk controls and support",
            "integration maintenance",
        ],
        "revenue": "SaaS subscriptions paired with transaction, reconciliation, or premium workflow fees.",
    },
    {
        "name": "Commerce and Marketplaces",
        "keywords": {
            "marketplace",
            "seller",
            "sellers",
            "buyer",
            "buyers",
            "ecommerce",
            "e-commerce",
            "retail",
            "shop",
            "shopping",
            "fulfillment",
            "inventory",
        },
        "partners": [
            "supply-side anchors and early sellers",
            "payments, logistics, and trust providers",
            "communities that aggregate buyers or inventory",
        ],
        "channels": [
            "supply-first niche community outreach",
            "performance marketing once liquidity improves",
            "partner referrals from ecosystem tools",
        ],
        "resources": [
            "liquidity in the first niche",
            "trust, dispute handling, and onboarding",
            "pricing and matching data",
        ],
        "costs": [
            "seller success and onboarding",
            "payments and marketplace operations",
            "growth spend to reach both sides of the market",
        ],
        "revenue": "Take-rate revenue, subscriptions for power sellers, and premium workflow tools.",
    },
    {
        "name": "Developer Tools and AI Automation",
        "keywords": {
            "developer",
            "developers",
            "engineer",
            "engineering",
            "api",
            "apis",
            "sdk",
            "code",
            "coding",
            "graphql",
            "automation",
            "agent",
            "agents",
            "workflow",
            "workflows",
            "ai",
            "llm",
            "software",
        },
        "partners": [
            "cloud, model, and API providers",
            "systems integrators and implementation partners",
            "design partners inside product and engineering teams",
        ],
        "channels": [
            "developer content, demos, and open-source credibility",
            "founder-led outbound to product and engineering leaders",
            "integration marketplaces and partner ecosystems",
        ],
        "resources": [
            "fast iteration velocity",
            "reliable integrations and observability",
            "domain workflows encoded into the product",
        ],
        "costs": [
            "inference or compute costs",
            "platform engineering and reliability",
            "customer onboarding and solution engineering",
        ],
        "revenue": "Usage-based pricing with team subscriptions and enterprise support tiers.",
    },
    {
        "name": "B2B Workflow SaaS",
        "keywords": {
            "team",
            "teams",
            "company",
            "companies",
            "sales",
            "marketing",
            "recruiting",
            "compliance",
            "legal",
            "operations",
            "procurement",
            "dashboard",
            "analytics",
        },
        "partners": [
            "consultants and agencies already serving the workflow",
            "integration partners around the existing stack",
            "trade associations and communities with concentrated users",
        ],
        "channels": [
            "founder-led outbound into a tight ICP",
            "case-study content around time saved",
            "partner referrals from adjacent service firms",
        ],
        "resources": [
            "tight ICP knowledge",
            "workflow templates and playbooks",
            "integration and reporting infrastructure",
        ],
        "costs": [
            "product development and support",
            "implementation and onboarding",
            "targeted sales and customer education",
        ],
        "revenue": "Seat-based SaaS subscriptions with premium implementation and admin tooling.",
    },
]


@dataclass(frozen=True)
class DemoDocumentBundle:
    similar_ideas: str
    business_model_canvas: str
    pitch_deck: str
    product_requirements_document: str
    provisional_patent: str


@dataclass(frozen=True)
class IdeaContext:
    description: str
    summary: str
    short_summary: str
    customer_segment: str
    domain_name: str
    keywords: tuple[str, ...]
    working_title: str
    problem_statement: str
    solution_statement: str
    differentiation: str
    revenue_model: str
    channels: tuple[str, ...]
    partners: tuple[str, ...]
    resources: tuple[str, ...]
    costs: tuple[str, ...]


def build_demo_documents(description: str) -> DemoDocumentBundle:
    context = _build_context(description)
    return DemoDocumentBundle(
        similar_ideas=_render_similar_ideas(context),
        business_model_canvas=_render_business_model_canvas(context),
        pitch_deck=_render_pitch_deck(context),
        product_requirements_document=_render_prd(context),
        provisional_patent=_render_provisional_patent(context),
    )


def _build_context(description: str) -> IdeaContext:
    clean_description = _normalize_text(description)
    sentences = _sentences(clean_description)
    summary = sentences[0] if sentences else clean_description
    summary = summary.rstrip(".") + "."
    short_summary = _limit_words(summary, 20)
    keyword_list = _extract_keywords(clean_description)
    domain = _pick_domain(keyword_list, clean_description)
    customer_segment = _infer_customer_segment(clean_description)
    working_title = _infer_working_title(keyword_list, domain["name"])
    problem_statement = _infer_problem_statement(clean_description, customer_segment)
    solution_statement = _infer_solution_statement(clean_description, customer_segment)
    differentiation = _infer_differentiation(clean_description, customer_segment)
    revenue_model = _infer_revenue_model(clean_description, domain["revenue"])

    return IdeaContext(
        description=clean_description,
        summary=summary,
        short_summary=short_summary,
        customer_segment=customer_segment,
        domain_name=domain["name"],
        keywords=tuple(keyword_list),
        working_title=working_title,
        problem_statement=problem_statement,
        solution_statement=solution_statement,
        differentiation=differentiation,
        revenue_model=revenue_model,
        channels=tuple(domain["channels"]),
        partners=tuple(domain["partners"]),
        resources=tuple(domain["resources"]),
        costs=tuple(domain["costs"]),
    )


def _normalize_text(description: str) -> str:
    raw = html.unescape(description or "")
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return (
        raw or "A software platform that solves a painful workflow for a focused customer segment."
    )


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _extract_keywords(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9-]+", text.lower())
    filtered = [word for word in words if len(word) > 3 and word not in STOP_WORDS]
    counts = Counter(filtered)
    if not counts:
        return ["workflow", "automation", "software"]
    return [word for word, _ in counts.most_common(6)]


def _pick_domain(keywords: Iterable[str], description: str) -> dict:
    keyword_set = set(keywords)
    description_set = set(re.findall(r"[a-zA-Z][a-zA-Z0-9-]+", description.lower()))

    def score(profile: dict) -> int:
        profile_words = profile["keywords"]
        return len(profile_words & keyword_set) * 3 + len(profile_words & description_set)

    return max(DOMAIN_PROFILES, key=score)


def _infer_customer_segment(description: str) -> str:
    rules = [
        (
            {"founder", "founders", "startup", "startups", "investor", "investors"},
            "founders and startup operators",
        ),
        (
            {"student", "students", "mentor", "mentors", "teacher", "teachers", "university"},
            "students, mentors, and academic programs",
        ),
        (
            {"patient", "patients", "doctor", "doctors", "clinic", "healthcare"},
            "patients and care teams",
        ),
        (
            {"developer", "developers", "engineer", "engineering", "product", "products"},
            "product and engineering teams",
        ),
        (
            {"seller", "sellers", "buyer", "buyers", "marketplace", "retail"},
            "buyers, sellers, and marketplace operators",
        ),
        (
            {"sales", "marketing", "ops", "operations", "recruiting", "legal"},
            "operators responsible for high-friction business workflows",
        ),
    ]
    words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9-]+", description.lower()))
    for triggers, segment in rules:
        if words & triggers:
            return segment
    return "time-constrained operators dealing with a fragmented workflow"


def _infer_working_title(keywords: list[str], domain_name: str) -> str:
    focus = " ".join(word.title() for word in keywords[:2]) or "Workflow Platform"
    return f"{focus} {domain_name.split()[0]} Platform"


def _infer_problem_statement(description: str, customer_segment: str) -> str:
    lowered = description.lower()
    if "connect" in lowered or "match" in lowered:
        return f"{customer_segment.capitalize()} still rely on manual discovery, scattered messaging, and weak trust signals to find the right counterpart."
    if "generate" in lowered or "document" in lowered or "draft" in lowered:
        return f"{customer_segment.capitalize()} lose momentum because critical execution documents are still assembled manually across spreadsheets, docs, and ad hoc expertise."
    if "marketplace" in lowered:
        return f"{customer_segment.capitalize()} face thin liquidity, poor onboarding, and limited trust, which makes the marketplace experience feel unreliable."
    return f"{customer_segment.capitalize()} currently solve the workflow with email, spreadsheets, and disconnected tools, creating delays, rework, and weak visibility."


def _infer_solution_statement(description: str, customer_segment: str) -> str:
    sentence = _limit_words(description, 28)
    return f"The product gives {customer_segment} a focused operating system for this workflow: {sentence}"


def _infer_differentiation(description: str, customer_segment: str) -> str:
    keywords = ", ".join(_extract_keywords(description)[:3])
    return (
        f"Instead of behaving like a generic toolkit, the product packages domain-specific workflows, structured recommendations, and measurable outcomes for {customer_segment}. "
        f"It becomes more useful as it learns from recurring patterns around {keywords}."
    )


def _infer_revenue_model(description: str, default_revenue: str) -> str:
    lowered = description.lower()
    if "marketplace" in lowered or "transaction" in lowered:
        return "Take a fee on successful transactions and layer premium subscriptions on top for power users."
    if "api" in lowered or "developer" in lowered or "usage" in lowered:
        return "Charge on usage, with team plans for collaboration and enterprise support for larger deployments."
    if "consumer" in lowered or "creator" in lowered or "community" in lowered:
        return "Use freemium acquisition, then convert power users into premium subscriptions and paid concierge services."
    return default_revenue


def _limit_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(",.;:") + "..."


def _render_similar_ideas(context: IdeaContext) -> str:
    return "\n".join(
        [
            "# Similar Landscape",
            "## Comparable Companies",
            f"### Vertical workflow software for {context.customer_segment}",
            "- URL: https://www.g2.com/",
            f"- Summary: Category leaders package software around operational workflows for {context.customer_segment}.",
            "- Why Similar: They reduce manual coordination and replace fragmented tools with a dedicated operating surface.",
            "- Distinguishing Signal: Study how category leaders turn domain-specific workflows into repeatable product value.",
            "",
            "### Services-first operators in the same workflow",
            "- URL: https://www.clutch.co/",
            "- Summary: Agencies and consultants often solve the same problem through human-heavy delivery.",
            "- Why Similar: They prove demand and reveal which steps customers already pay to outsource.",
            "- Distinguishing Signal: Use them to identify which activities should remain high-touch in the first product release.",
            "",
            "### Horizontal collaboration and workflow suites",
            "- URL: https://www.atlassian.com/software/jira",
            "- Summary: Teams often patch together general-purpose software before buying a purpose-built workflow product.",
            "- Why Similar: These tools occupy budget and workflow real estate even when they do not solve the full job well.",
            "- Distinguishing Signal: Evaluate where a purpose-built product can deliver faster time-to-value than a configurable suite.",
            "",
            f"### Analytics and operating systems for {context.domain_name.lower()}",
            "- URL: https://www.gartner.com/",
            "- Summary: Analytics-heavy platforms often win by turning workflow activity into management visibility and decisions.",
            "- Why Similar: This concept also depends on structured outputs, measurable progress, and higher-confidence execution.",
            "- Distinguishing Signal: Strong products pair workflow automation with reporting that justifies continued usage.",
            "",
            "## Research Watchlist",
            "### Category demand and budget ownership",
            "- Suggested Sources: Gartner market guides, G2 category pages, buyer reviews, and analyst market maps.",
            "- Why It Matters: Budget ownership reveals whether the wedge belongs to operations, IT, finance, or a line-of-business team.",
            "- What To Validate: Confirm which team signs the budget and what incumbent spend can be displaced first.",
            "",
            "### Workflow bottlenecks that still require human review",
            "- Suggested Sources: customer interviews, expert communities, service providers, and operational playbooks.",
            "- Why It Matters: The human-in-the-loop boundary shapes the MVP, trust model, and pricing posture.",
            "- What To Validate: Identify which step can be automated now and which step still needs approval or expertise.",
            "",
            f"### Defensible data and process insights in {context.domain_name.lower()}",
            "- Suggested Sources: implementation case studies, integration docs, domain-specific publications, and internal usage telemetry.",
            "- Why It Matters: Durable products create proprietary context that improves recommendations and retention over time.",
            "- What To Validate: Determine which structured data exhaust becomes more valuable as customers keep using the workflow.",
        ]
    )


def _render_business_model_canvas(context: IdeaContext) -> str:
    return "\n".join(
        [
            "# Key Partners",
            *(f"- {item}" for item in context.partners),
            "# Key Activities",
            f"- Translate {context.customer_segment} workflows into repeatable product experiences.",
            "- Ship integrations, analytics, and onboarding paths that reduce setup friction.",
            "- Maintain a tight feedback loop with design partners and early power users.",
            "# Key Resources",
            *(f"- {item}" for item in context.resources),
            f"- Workflow data, templates, and proprietary insights tied to {context.domain_name.lower()}.",
            "# Value Propositions",
            f"- {context.solution_statement}",
            f"- {context.problem_statement}",
            f"- {context.differentiation}",
            "# Customer Relationships",
            "- High-touch onboarding for the first cohort of customers.",
            "- Product-led guidance, templates, and alerts that keep customers active.",
            "- Quarterly business reviews focused on measurable operational outcomes.",
            "# Channels",
            *(f"- {item}" for item in context.channels),
            "# Customer Segments",
            f"- Primary: {context.customer_segment}.",
            "- Secondary: managers, advisors, or operators who need visibility into results.",
            "- Tertiary: ecosystem partners who benefit from cleaner execution and reporting.",
            "# Cost Structure",
            *(f"- {item}" for item in context.costs),
            "- Founder-led sales and customer success until repeatability is proven.",
            "# Revenue Streams",
            f"- {context.revenue_model}",
            "- Optional implementation, premium templates, and higher-tier reporting features.",
        ]
    )


def _render_pitch_deck(context: IdeaContext) -> str:
    return "\n".join(
        [
            "# Slide 1: Company Purpose",
            f"{context.working_title} gives {context.customer_segment} a focused system for a painful workflow that is still handled manually or across fragmented tools.",
            f"- Working concept: {context.working_title}",
            f"- One-line pitch: {context.short_summary}",
            f"- Initial wedge: {context.customer_segment}.",
            f"- Business model: {context.revenue_model}",
            "",
            "# Slide 2: Problem",
            f"{context.problem_statement}",
            "- Existing alternatives are fragmented, manual, or too horizontal to solve the workflow end-to-end.",
            "- The pain repeats frequently enough that speed, accuracy, and visibility matter.",
            "- Customers often rely on email, spreadsheets, or service providers to bridge the gap.",
            "",
            "# Slide 3: Solution",
            f"{context.solution_statement}",
            "- The first release should remove the highest-friction step and make the next action obvious.",
            "- Structured outputs and workflow history create compounding product value over time.",
            "- The product should feel operationally useful on day one, not aspirational.",
            "",
            "# Slide 4: Why Now",
            "The market is ready when workflow complexity is rising, users expect software to do more of the work, and incumbents still leave teams stitching systems together.",
            "- AI-assisted execution lowers the cost of shipping workflow-specific automation.",
            "- Buyers increasingly expect measurable ROI and faster time-to-value from software.",
            "- Integration-heavy categories create room for focused products with better user experience.",
            "",
            "# Slide 5: Market Opportunity",
            f"{context.customer_segment.capitalize()} is the initial wedge inside the broader {context.domain_name.lower()} category.",
            f"- Category focus: {context.domain_name}.",
            "- Land with one painful workflow, then expand into adjacent planning, collaboration, and reporting needs.",
            "- The expansion path should increase account value without losing focus on the original pain point.",
            "",
            "# Slide 6: Product and User Experience",
            "The product should feel like an operating surface, not a generic workspace.",
            "- Capture the user's intent quickly and translate it into a structured output.",
            "- Keep editing, collaboration, and next-step execution in the same workflow.",
            "- Build visible confidence through templates, recommendations, and auditability.",
            "",
            "# Slide 7: Business Model",
            f"{context.revenue_model}",
            "- Land with a focused use case, then expand ARPU through automation, integrations, and admin capabilities.",
            "- Premium service, onboarding, or reporting can increase value in early accounts.",
            "",
            "# Slide 8: Go-to-Market",
            "Distribution should start narrow, founder-led, and tied to a clear ICP before broadening.",
            *(f"- {item.capitalize()}." for item in context.channels),
            "",
            "# Slide 9: Competition and Moat",
            f"{context.differentiation}",
            "- Better workflow data creates better recommendations, templates, and benchmark insights.",
            "- The moat strengthens if the product becomes the system of record for execution decisions.",
            "",
            "# Slide 10: Proof Points and Early Traction",
            "The earliest proof should show that customers use the workflow repeatedly and trust the generated output enough to act on it.",
            "- Target 5 to 10 design partners in a tight ICP.",
            "- Measure time saved, workflow completion, and rate of output reuse or sharing.",
            "- Use qualitative case studies until hard revenue or retention data is available.",
            "",
            "# Slide 11: Execution Roadmap",
            "Execution should deepen the wedge before expanding the surface area.",
            "- Secure design partners and map the workflow in detail.",
            "- Ship the narrow MVP quickly and instrument activation and retention.",
            "- Expand into adjacent workflows only after the first loop is sticky and measurable.",
            "",
            "# Slide 12: Team and Ask",
            "The team should bias toward product execution, domain fluency, and tight customer feedback loops.",
            "- Build the first team around product, engineering, and customer insight.",
            "- Use the next funding or hiring milestone to deepen the wedge, not broaden it prematurely.",
            "- Present the ask in terms of what proof points the next 12 to 18 months will unlock.",
        ]
    )


def _render_prd(context: IdeaContext) -> str:
    return "\n".join(
        [
            "# Product Requirements Document",
            "## Document Control",
            "| Field | Value |",
            "| --- | --- |",
            "| Status | Draft |",
            "| Owner | Product / Founder |",
            f"| Primary User | {context.customer_segment.capitalize()} |",
            "| Release Target | TBD - validate with first design partners |",
            "| Last Updated | Generated by Manifest |",
            "",
            "## Executive Summary",
            context.solution_statement,
            "",
            "## Problem Statement",
            context.problem_statement,
            "",
            "## Goals",
            "- Reduce the time required to complete the core workflow from hours or days to minutes.",
            "- Replace fragmented communication and handoffs with a single operating surface.",
            "- Produce outputs that are immediately useful for execution, not just brainstorming.",
            "",
            "## Non-Goals",
            "- Do not support every adjacent workflow in the first release.",
            "- Do not optimize for highly customized enterprise deployments before the core loop is validated.",
            "- Do not replace expert review where trust or compliance still requires a human in the loop.",
            "",
            "## Users and Jobs To Be Done",
            f"- Primary users: {context.customer_segment}.",
            "- Secondary users: decision-makers who want visibility into progress, quality, and ROI.",
            "- Core job: move from an ambiguous request to a usable, execution-ready output with less manual effort.",
            "",
            "## User Stories",
            f"- As a {context.customer_segment}, I want to submit a messy workflow request, so that the product can turn it into a structured output I can use immediately.",
            "- As a collaborator, I want to review and edit generated outputs, so that the final artifact reflects team input before execution.",
            "- As a decision-maker, I want visibility into progress and next steps, so that I can judge whether the workflow is moving forward effectively.",
            "",
            "## Scope",
            "- Capture the core workflow input in a guided form or editor.",
            "- Generate the first meaningful output automatically and persist it.",
            "- Allow edits, version history, and basic collaboration on the output.",
            "- Surface next-step recommendations tied to the user's stated goal.",
            "",
            "## Functional Requirements",
            "1. The system must persist user inputs and generated artifacts reliably.",
            "2. The system must make generated outputs editable without losing structure.",
            "3. The system must support asynchronous generation so long-running tasks do not block the interface.",
            "4. The system should provide collaboration and sharing primitives for team-based workflows.",
            "5. The system should preserve enough document structure for downstream export, review, or approval flows.",
            "",
            "## Non-Functional Requirements",
            "1. Responses should feel fast enough for iterative editing, with clear status feedback.",
            "2. Generated artifacts must be structured, readable, and reusable across downstream workflows.",
            "3. The product should log failures and degrade gracefully when external generation services are unavailable.",
            "4. Sensitive user content must be stored and transmitted with appropriate access controls.",
            "",
            "## UX Principles",
            "- Favor clarity over novelty; generated outputs should read like working business documents.",
            "- Keep the next step obvious after every generation flow.",
            "- Reduce formatting friction so users can focus on meaning, not cleanup.",
            "",
            "## Technical Considerations",
            "- Use asynchronous document generation and polling or subscriptions for long-running work.",
            "- Store generated artifacts in formats that can be reused across web, mobile, and future export flows.",
            "- Preserve enough metadata to support analytics, history, and future document templates.",
            "",
            "## Analytics and Success Metrics",
            "- Activation: percentage of new users who create and save a usable artifact in the first session.",
            "- Retention: weekly return rate of users managing an active workflow.",
            "- Outcome quality: percent of generated outputs that require only light editing before use.",
            "",
            "## Risks and Open Questions",
            "- Which narrow user segment has the most urgent pain and willingness to pay right now?",
            "- What output quality threshold is required before the product becomes part of the workflow?",
            "- Where should human review stay in the loop versus full automation?",
            "",
            "## Launch and Rollout",
            "- Phase 1: validate the narrow wedge with design partners and a manual concierge layer.",
            "- Phase 2: automate the heaviest repeated steps and instrument activation and retention.",
            "- Phase 3: expand into adjacent workflows once the initial loop is sticky and measurable.",
        ]
    )


def _render_provisional_patent(context: IdeaContext) -> str:
    keywords = ", ".join(context.keywords[:3]) or "workflow automation"
    return "\n".join(
        [
            "# Title",
            f"System and method for orchestrating {keywords} workflows",
            "# Inventor / Applicant Details Needed Before Filing",
            "- Confirm legal inventor names, residence, and citizenship details.",
            "- Confirm applicant / assignee information, correspondence address, and entity status.",
            "- Review whether any public disclosure or prior filing affects the filing strategy.",
            "# Abstract",
            f"A computer-implemented system that receives structured and unstructured inputs from {context.customer_segment}, transforms those inputs into guided workflow artifacts, and coordinates the next recommended actions across a shared software interface. The system improves speed, consistency, and decision quality for {context.domain_name.lower()} use cases.",
            "# Description",
            "## Field of the Invention",
            f"The invention relates to software systems for {context.domain_name.lower()}, including systems that receive ambiguous user requests and transform them into structured workflow artifacts and recommended actions.",
            "",
            "## Background",
            context.problem_statement,
            "Conventional tools require users to manually coordinate documents, approvals, and follow-up actions across multiple systems, which creates delay, inconsistency, and poor visibility.",
            "",
            "## Summary",
            f"The disclosed system provides a workflow operating layer for {context.customer_segment}. It receives a goal, constraint set, or request; classifies the request; generates one or more structured artifacts; and recommends or triggers subsequent actions while preserving review and revision history.",
            "",
            "## Brief Description of the Drawings",
            "Figure 1 illustrates an end-to-end workflow from user input through artifact generation and next-step orchestration.",
            "Figure 2 illustrates a system architecture including user interface, generation engine, persistence layer, and external integrations.",
            "Figure 3 illustrates an example review interface with editable artifacts, status indicators, and recommended actions.",
            "",
            "## Detailed Description",
            "A user provides an initial description of a goal, constraint set, or workflow request. The platform normalizes the input, identifies the relevant workflow type, generates structured artifacts, and stores those artifacts for editing, collaboration, and execution. The system may further rank recommended next actions, monitor completion state, and adapt future outputs using prior workflow data. In preferred implementations, the system integrates external data sources, communication tools, or transactional systems so that users can move from planning to execution without leaving the product.",
            "",
            "## Filing Notes",
            "- This draft should be reviewed for enablement, novelty, and scope before filing.",
            "- Replace generalized business language with implementation details, examples, and architecture specifics where available.",
            "- Confirm whether additional embodiments or drawings are needed to support broader claim coverage.",
            "# Claims",
            "1. A computer-implemented method comprising receiving a workflow request, classifying the request, generating one or more structured workflow artifacts, and presenting the artifacts through an interactive interface.",
            "2. The method of claim 1, wherein the system stores revisions to the structured workflow artifacts and uses the revisions to improve later recommendations.",
            "3. The method of claim 1, wherein the system triggers downstream actions or integrations after user approval of a generated artifact.",
            "4. The method of claim 1, wherein the generated artifacts include planning documents, execution checklists, or collaboration-ready summaries tailored to a specific workflow.",
            "# Suggested Drawings",
            "Figure 1: End-to-end workflow from user input through artifact generation and next-step orchestration.",
            "Figure 2: System architecture showing user interface, generation engine, persistence layer, and external integrations.",
            "Figure 3: Example review screen with editable artifacts, status indicators, and recommended actions.",
        ]
    )
