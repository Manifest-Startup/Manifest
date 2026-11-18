"""Public, agent-readable site content.

One source of truth for the text that AI agents and no-JavaScript crawlers
read about Manifest:

* the server-rendered SPA shell for marketing and trust pages
  (``spa_prerender_shell``),
* the Markdown twins (``/index.md``, ``/about.md`` …) and
  ``Accept: text/markdown`` negotiation,
* the agent guide (``/agents.md``) and ``/pricing.md``.

Keep every statement here true for the running product. Do not describe
endpoints, integrations, or company details that do not exist; the
discovery documents built from this module are read by machines that
will act on them.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

SITE_ORIGIN = "https://manifeststartup.com"
GITHUB_ORG_URL = "https://github.com/Manifest-Startup"

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PUBLIC_DOC_DIRS = (
    _REPO_ROOT / "frontend" / "build" / "docs",
    _REPO_ROOT / "frontend" / "public" / "docs",
)


@dataclass(frozen=True)
class AgentPage:
    """A public page with a Markdown body (the body starts with ``# <h1>``)."""

    path: str
    title: str
    description: str
    markdown: str
    canonical_path: str | None = None

    @property
    def h1(self) -> str:
        first = self.markdown.lstrip().splitlines()[0]
        return first.lstrip("#").strip()

    @property
    def body_markdown(self) -> str:
        """Markdown without the leading ``# <h1>`` line."""
        lines = self.markdown.lstrip().splitlines()
        return "\n".join(lines[1:]).strip()

    @property
    def markdown_path(self) -> str:
        return markdown_twin_path(self.path)


def markdown_twin_path(path: str) -> str:
    return "/index.md" if path == "/" else f"{path}.md"


def _read_public_doc(filename: str) -> str | None:
    for directory in _PUBLIC_DOC_DIRS:
        candidate = directory / filename
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    return None


# --------------------------------------------------------------------------
# Page copy
# --------------------------------------------------------------------------

_DEVELOPER_LINKS = f"""\
- [API reference](/docs/api): authentication, endpoints, errors and examples for the public REST API.
- [OpenAPI specification](/openapi.json): machine-readable description of `/api/v1`.
- [Agent guide](/agents.md): when an AI agent should use Manifest and how to call it.
- [llms.txt](/llms.txt): index of the pages agents should read.
- [Pricing and API limits](/pricing.md)
- [Manifest on GitHub]({GITHUB_ORG_URL})"""

_COMPANY_LINKS = """\
- [About Manifest](/about)
- [Contact](/contact)
- [Privacy policy](/privacy)
- [Terms of service](/legal/terms)"""

_DEMO_NOTICE = (
    "Manifest is in development. The public site is a demo preview: it is not yet "
    "operational and should not be used for real business decisions."
)

_HOME_MARKDOWN = f"""\
# Turn your idea into a plan.

Manifest is one simple workspace for strategy, research and startup documents. It is an
AI-powered workspace that helps founders turn raw startup ideas into structured,
investor-ready artifacts: describe an idea in your own words and Manifest drafts the
documents a new company needs, keeps them linked to the idea, and lets you refine them as
the idea changes. You stay in control of every generated draft.

**Demo only.** {_DEMO_NOTICE}

## What Manifest is built to do

- Generate a business model canvas, a pitch deck (downloadable as an editable PowerPoint
  file), a product requirements document and a provisional patent draft from one idea.
- Keep versions of your idea and its documents, and collaborate with people you invite.
- Publish an idea to Pitch Reels, a feed of short founder pitch clips, and message other
  founders about published ideas.
- Let you explore the demo as a guest before you sign up. When you create an account, the
  guest workspace moves into it.

## Get started

- [Sign in or create an account](/auth), or [read the user guide](/docs/guide).

## For developers and AI agents

{_DEVELOPER_LINKS}

## Company

{_COMPANY_LINKS}
"""

_ABOUT_MARKDOWN = f"""\
# About Manifest

Manifest is an ideas-to-reality platform for founders. Most startup ideas stall between a
note on a phone and a company that can raise money: the founder has to write a business
model, a pitch deck, product requirements, and early legal and intellectual-property
paperwork before anyone will take the idea seriously. Manifest uses AI to draft that work
from the founder's own description of the idea, so the founder can spend their time on
judgment rather than formatting.

## What Manifest does

- Turns a raw idea, typed or spoken, into linked startup artifacts: a business model
  canvas, a pitch deck, a product requirements document and a provisional patent draft.
- Keeps those artifacts tied to the idea, versioned and editable, so they stay consistent
  as the idea changes.
- Gives founders a place to publish ideas, share short pitch reels, and talk with other
  founders and investors on the same platform.

## How we build it

Manifest follows three product principles: it should be extremely easy to use, extremely
robust, and inexpensive to run. AI drafts the bottom-up work; the founder keeps top-down
control and decides what is published. Generated documents are drafts to review, not legal,
financial or investment advice.

{_DEMO_NOTICE}

## Contact

- General questions: [hello@manifeststartup.com](mailto:hello@manifeststartup.com)
- Code and engineering: [Manifest on GitHub]({GITHUB_ORG_URL})

## More

{_COMPANY_LINKS}
"""

_CONTACT_MARKDOWN = f"""\
# Contact Manifest

Contact Manifest by email for product and general questions.

## General questions, partnerships and press

Email [hello@manifeststartup.com](mailto:hello@manifeststartup.com) for product and general
questions.

## Account and privacy requests

Signed-in users can manage their account data from the account page. See our
[privacy policy](/privacy) for information about data handling.

## Security vulnerabilities

For security reports, use the contact details published in our
[security.txt](/.well-known/security.txt), when available.

## Developers

The public REST API is documented in the [API reference](/docs/api) and the
[OpenAPI specification](/openapi.json). AI agents should start with the
[agent guide](/agents.md).

## More

{_COMPANY_LINKS}
"""

_DOCS_MARKDOWN = f"""\
# Manifest documentation

Guides for founders using the Manifest workspace and references for developers and AI agents
that integrate with it.

## For founders

- [User guide](/docs/guide): create an idea, generate documents, collaborate and publish.
- [Privacy policy](/privacy) and [terms of service](/legal/terms).

## For developers and AI agents

{_DEVELOPER_LINKS}
"""

_API_DOCS_MARKDOWN = """\
# Manifest API

The Manifest REST API lets you create and manage startup ideas and generate documents for
them (business model canvas, pitch deck, product requirements document and provisional
patent draft) from your own code or from an AI agent. The machine-readable description is
the [OpenAPI specification](/openapi.json).

## Authentication

Every `/api/v1` request (except `GET /api/v1/`) needs an API key in the `Authorization`
header:

```http
Authorization: Bearer manifest_sk_...
```

Signed-in users create API keys from their Manifest account (API access settings), which
uses the session-authenticated key management endpoints under `/api/keys`. Keys carry
scopes: `ideas.read` to read ideas and `ideas.write` to create, update, delete and generate
(the coarse `read` and `write` scopes cover all `*.read` and `*.write` permissions). New
keys default to `read`.

## Endpoints

- `GET /api/v1/` - API name, version and status (no key needed).
- `GET /api/v1/ideas` - list your ideas.
- `POST /api/v1/ideas` - create an idea from a `title` and optional `description`.
- `GET /api/v1/ideas/{idea_id}` - get one idea.
- `PATCH /api/v1/ideas/{idea_id}` - update the title or description.
- `DELETE /api/v1/ideas/{idea_id}` - delete an idea.
- `POST /api/v1/ideas/{idea_id}/generate` - generate documents; `document_types` is any of
  `business_model_canvas`, `pitch_deck`, `prd`, `patent`. The call is synchronous and can
  take a while because it runs AI generation.
- `GET /api/v1/usage` - usage statistics for your API client.

## Quickstart

```bash
curl -s https://manifeststartup.com/api/v1/ideas \\
  -H "Authorization: Bearer $MANIFEST_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"title": "Solar-powered cold storage for small farms"}'
```

## Errors and limits

Errors return JSON shaped as `{"detail": {"error": {"message", "type", "code"}}}` with
status 401 (missing or invalid key), 403 (missing scope or not your idea), 404 (unknown
idea), 429 (rate or monthly limit reached) or 500. Rate and monthly limits depend on your
API tier; see [pricing and API limits](/pricing.md).

## More

- [Agent guide](/agents.md)
- [API catalog](/.well-known/api-catalog) (RFC 9727)
- [Contact](/contact) for higher limits or integration questions.
"""


def _policy_page(path: str, filename: str, title: str, description: str, canonical: str):
    text = _read_public_doc(filename)
    if text is None:
        text = (
            f"# {title}\n\nThe full document is available at "
            f"[{SITE_ORIGIN}{canonical}]({canonical})."
        )
    return AgentPage(
        path=path,
        title=title,
        description=description,
        markdown=text.strip() + "\n",
        canonical_path=canonical,
    )


_PRIVACY_DESCRIPTION = (
    "How Manifest collects, uses, shares and stores personal information, and the privacy "
    "choices and rights available to you."
)
_TERMS_DESCRIPTION = "The terms that govern use of the Manifest website, apps and API."


def _build_pages() -> dict[str, AgentPage]:
    home = AgentPage(
        path="/",
        title="Manifest — Turn your idea into a plan",
        description=(
            "Manifest is an AI workspace that turns raw startup ideas into a business model "
            "canvas, pitch deck, product requirements and provisional patent drafts."
        ),
        markdown=_HOME_MARKDOWN,
    )
    api_docs = AgentPage(
        path="/docs/api",
        title="Manifest API reference",
        description=(
            "Authentication, endpoints, errors and limits for the Manifest public REST API, "
            "with a quickstart and an OpenAPI specification."
        ),
        markdown=_API_DOCS_MARKDOWN,
    )
    pages = [
        home,
        AgentPage(
            path="/about",
            title="About Manifest",
            description="What Manifest is, what it does for founders and how to reach us.",
            markdown=_ABOUT_MARKDOWN,
        ),
        AgentPage(
            path="/contact",
            title="Contact Manifest",
            description="How to reach Manifest for questions, privacy requests and security.",
            markdown=_CONTACT_MARKDOWN,
        ),
        AgentPage(
            path="/docs",
            title="Manifest documentation",
            description="User guide, API reference and agent resources for Manifest.",
            markdown=_DOCS_MARKDOWN,
        ),
        api_docs,
        AgentPage(
            path="/developers",
            title=api_docs.title,
            description=api_docs.description,
            markdown=_API_DOCS_MARKDOWN,
            canonical_path="/docs/api",
        ),
        _policy_page(
            "/privacy",
            "PRIVACY_POLICY.md",
            "Manifest Privacy Policy",
            _PRIVACY_DESCRIPTION,
            "/legal/privacy",
        ),
        _policy_page(
            "/legal/privacy",
            "PRIVACY_POLICY.md",
            "Manifest Privacy Policy",
            _PRIVACY_DESCRIPTION,
            "/legal/privacy",
        ),
        _policy_page(
            "/legal/terms",
            "TERMS_OF_SERVICE.md",
            "Manifest Terms of Service",
            _TERMS_DESCRIPTION,
            "/legal/terms",
        ),
    ]
    return {page.path: page for page in pages}


AGENT_PAGES: dict[str, AgentPage] = _build_pages()
MARKDOWN_TWINS: dict[str, AgentPage] = {page.markdown_path: page for page in AGENT_PAGES.values()}


def get_agent_page(path: str) -> AgentPage | None:
    return AGENT_PAGES.get(path)


# --------------------------------------------------------------------------
# Standalone Markdown documents
# --------------------------------------------------------------------------


def pricing_markdown() -> str:
    from app.services.identity.api_keys import BillingTier

    limits = BillingTier.LIMITS

    def _monthly(tier: str) -> str:
        value = limits[tier]["requests_per_month"]
        return "Unlimited" if value < 0 else f"{value:,}"

    def _rpm(tier: str) -> str:
        return f"{limits[tier]['rate_limit_per_minute']:,}"

    rows = [
        ("Free", "$0", BillingTier.FREE),
        ("Starter", "$29", BillingTier.STARTER),
        ("Pro", "$99", BillingTier.PRO),
        ("Enterprise", "Custom", BillingTier.ENTERPRISE),
    ]
    table = "\n".join(
        f"| {name} | {price} | {_monthly(tier)} | {_rpm(tier)} |" for name, price, tier in rows
    )
    return f"""\
# Manifest pricing

{_DEMO_NOTICE} The web workspace demo can be explored without an account through a guest
session. API access is organised in tiers; the tiers below are the API tiers and limits the
platform is configured with (also returned by `GET /api/keys/tiers`). Contact us before
relying on them.

## API tiers

| Tier | Listed price (USD) | Requests per month | Requests per minute |
| --- | --- | --- | --- |
{table}

- The table describes configured usage limits only. It does not represent a billing
  commitment or guarantee that a tier can currently be purchased.

Requests over a tier's per-minute or monthly limit receive HTTP 429 with error code
`rate_limit_exceeded` or `monthly_limit_exceeded`.

## Questions

See the [API reference](/docs/api) for how to authenticate.
"""


AGENTS_MARKDOWN = f"""\
# Manifest agent guide

Manifest ({SITE_ORIGIN}) turns a founder's raw startup idea into structured, investor-ready
documents. This file tells AI agents when Manifest is the right tool and how to call it.

**Status:** {_DEMO_NOTICE} Tell users this before relying on Manifest's output.

## When to use Manifest

Use Manifest when a user wants to:

- turn a startup or product idea into a business model canvas, a pitch deck, a product
  requirements document (PRD) or a provisional patent draft;
- keep a set of startup ideas and their generated documents in one place that the user can
  open and edit in the Manifest web app;
- create, list, update or delete those ideas programmatically on behalf of a user who has a
  Manifest account and an API key.

## When not to use Manifest

- For legal, tax, financial or investment advice. Manifest's documents are AI drafts for the
  founder to review, not advice, and Manifest does not file patents or incorporate companies.
- For general web search, market data lookups or company research unrelated to an idea the
  user is building in Manifest.
- Without the user's consent: every tool acts as the signed-in person, on their own data.

## How to call Manifest

**Best: the MCP server with OAuth.** Connect `{SITE_ORIGIN}/mcp` (Streamable HTTP). The first
call answers 401 with OAuth discovery; the person signs in with Open Media and clicks Allow, and
you get every Manifest feature as a tool (ideas, qualification, documents, pitch shorts,
messages, investments, collaborators, account and privacy). Destructive tools need
`confirm: true` after the person agrees. Install it as a plugin for Claude Code, Codex, Cursor,
VS Code, Gemini CLI or Antigravity from `https://github.com/Manifest-Startup/Manifest`
(`agent-plugin/`), or add the URL as a custom connector in Claude or ChatGPT.

**Scripts: the REST API with an API key.** Never ask for a key in chat; the user creates one
while signed in and gives it to your secure credential store.

1. Send `Authorization: Bearer <key>` (`manifest_sk_...`) to the REST API at `{SITE_ORIGIN}/api/v1`.
   Keys default to the `read` scope; creating ideas or generating documents needs
   `ideas.write` (or `write`).
2. Typical flow: `POST /api/v1/ideas` with a `title` and `description`, then
   `POST /api/v1/ideas/{{idea_id}}/generate` with `document_types` (any of
   `business_model_canvas`, `pitch_deck`, `prd`, `patent`), then `GET /api/v1/ideas/{{idea_id}}`
   and read the `has_*` flags. Generation is synchronous and can take a while; do not retry
   while a request is still running.
3. Send the user to `{SITE_ORIGIN}/ideas` to read and edit the generated documents.

Errors come back as JSON `{{"detail": {{"error": {{"message", "type", "code"}}}}}}`. On HTTP 429,
back off and retry later; limits depend on the user's API tier.

## Machine-readable resources

- [OpenAPI specification](/openapi.json)
- [Manifest MCP server](https://manifeststartup.com/mcp) (Streamable HTTP; OAuth sign-in, or a Manifest API key for the small REST toolset)
- [MCP server card](https://manifeststartup.com/.well-known/mcp/server-card.json)
- [API catalog](/.well-known/api-catalog) (RFC 9727)
- [Agentic resource catalog](/.well-known/ard.json)
- [API reference](/docs/api)
- [Pricing and API limits](/pricing.md)
- [llms.txt](/llms.txt)
- Every public page also has a Markdown version: append `.md` (the homepage is
  [/index.md](/index.md)) or send `Accept: text/markdown`.

## Contact

General questions: [hello@manifeststartup.com](mailto:hello@manifeststartup.com).
"""


def not_found_markdown(path: str) -> str:
    safe_path = path.replace("`", "")
    return f"""\
# Page not found

There is no page at `{safe_path}` on manifeststartup.com. It may have moved, or the address
may be mistyped.

Try one of these instead:

- [Home](/)
- [Documentation](/docs)
- [API reference](/docs/api)
- [Agent guide](/agents.md)
- [llms.txt](/llms.txt)
- [Sitemap](/sitemap.xml)
"""


# --------------------------------------------------------------------------
# Minimal Markdown → HTML for server-rendered shells
# --------------------------------------------------------------------------

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def _inline(text: str) -> str:
    """Render inline code, bold and links. Input is raw Markdown text."""
    placeholders: list[str] = []

    def _stash(rendered: str) -> str:
        placeholders.append(rendered)
        return f"\x00{len(placeholders) - 1}\x00"

    text = _CODE_RE.sub(lambda m: _stash(f"<code>{html.escape(m.group(1))}</code>"), text)
    escaped = html.escape(text, quote=False)
    escaped = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    escaped = _LINK_RE.sub(
        lambda m: f'<a href="{html.escape(html.unescape(m.group(2)), quote=True)}">{m.group(1)}</a>',
        escaped,
    )
    return re.sub(r"\x00(\d+)\x00", lambda m: placeholders[int(m.group(1))], escaped)


def markdown_to_html(markdown: str) -> str:  # noqa: C901 - small line-oriented state machine
    """Render the restricted Markdown used in this module (and the public policy docs).

    Supports ATX headings, paragraphs, ``-``/``*``/numbered lists (with
    continuation lines), fenced code blocks, inline code, bold and links.
    Tables are rendered as preformatted text.
    """

    out: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    list_tag: str | None = None
    code: list[str] | None = None
    table: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_tag
        if list_items and list_tag:
            items = "".join(f"<li>{_inline(item)}</li>" for item in list_items)
            out.append(f"<{list_tag}>{items}</{list_tag}>")
        list_items.clear()
        list_tag = None

    def flush_table() -> None:
        if table:
            out.append(f"<pre>{html.escape(chr(10).join(table))}</pre>")
            table.clear()

    def flush_all() -> None:
        flush_paragraph()
        flush_list()
        flush_table()

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if code is not None:
            if line.strip().startswith("```"):
                out.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
                code = None
            else:
                code.append(raw)
            continue
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_all()
            code = []
            continue
        if not stripped:
            flush_all()
            continue
        if stripped.startswith("|"):
            flush_paragraph()
            flush_list()
            table.append(stripped)
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush_all()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            continue
        bullet = re.match(r"^[-*]\s+(.*)$", stripped)
        numbered = re.match(r"^\d+\.\s+(.*)$", stripped)
        if bullet or numbered:
            flush_paragraph()
            flush_table()
            tag = "ul" if bullet else "ol"
            if list_tag and list_tag != tag:
                flush_list()
            list_tag = tag
            list_items.append((bullet or numbered).group(1))  # type: ignore[union-attr]
            continue
        if list_items and raw.startswith((" ", "\t")):
            list_items[-1] = f"{list_items[-1]} {stripped}"
            continue
        flush_list()
        flush_table()
        paragraph.append(stripped)

    if code is not None:
        out.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
    flush_all()
    return "".join(out)
