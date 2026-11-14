"""
Manifest MCP Server - Professional MCP server exposing Manifest platform functionality.

This server provides tools for AI agents to interact with the Manifest platform,
enabling automated startup ideation, document generation, and investment management.
"""

import argparse
import logging
import os
import sys

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:

    class FastMCP:  # type: ignore[override]
        """Minimal fallback used when the optional MCP dependency is unavailable."""

        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def tool(self):
            def decorator(func):
                return func

            return decorator

        def resource(self, _uri: str):
            def decorator(func):
                return func

            return decorator

        def run(self, *args, **kwargs):
            raise RuntimeError("The 'mcp' package is required to run the Manifest MCP server.")


from .client import ManifestClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("manifest-mcp")

mcp = FastMCP(
    "manifest",
    instructions="""
    Manifest MCP Server - Transform ideas into investor-ready startups.
    
    This server provides tools to:
    - Create and manage startup ideas
    - Generate AI-powered business documents (Business Model Canvas, Pitch Decks, PRDs, Patents)
    - Explore the ideas marketplace and discover opportunities
    - Manage investments and track portfolios
    - Interact socially with other founders (follow, upvote)
    
    Authentication: Set MANIFEST_API_TOKEN environment variable for authenticated operations.
    Internal quality loop: Set MANIFEST_AGENT_LOOP_SECRET for website, survey, and production-signal automation.
    API Endpoint: Set MANIFEST_API_URL environment variable (default: http://localhost:8000).
    Compatibility: This MCP server targets a running Manifest API deployment and mirrors the contracts documented in docs/API.md.
    """,
)


def get_client() -> ManifestClient:
    """Get a configured Manifest API client."""
    base_url = os.environ.get("MANIFEST_API_URL", "http://localhost:8000")
    auth_token = os.environ.get("MANIFEST_API_TOKEN")
    api_key = os.environ.get("MANIFEST_API_KEY")
    internal_secret = os.environ.get("MANIFEST_AGENT_LOOP_SECRET") or os.environ.get(
        "AGENT_LOOP_SECRET"
    )
    return ManifestClient(
        base_url=base_url,
        auth_token=auth_token,
        api_key=api_key,
        internal_secret=internal_secret,
    )


@mcp.tool()
async def list_ideas() -> str:
    """
    List all ideas owned by the current user.

    Returns a list of ideas with their ID, title, description, and creation date.
    Use this to see what ideas exist before performing other operations.
    """
    async with get_client() as client:
        ideas = await client.get_ideas()

        if not ideas:
            return "No ideas found. Create your first idea using create_idea."

        result = f"Found {len(ideas)} idea(s):\n\n"
        for idea in ideas:
            result += f"- **{idea.get('title', 'Untitled')}**\n"
            result += f"  ID: {idea.get('ideaId')}\n"
            if idea.get("description"):
                desc = (
                    idea["description"][:200] + "..."
                    if len(idea.get("description", "")) > 200
                    else idea.get("description", "")
                )
                result += f"  Description: {desc}\n"
            result += f"  Created: {idea.get('createdAt', 'Unknown')}\n\n"

        return result


@mcp.tool()
async def get_idea(idea_id: str) -> str:
    """
    Get detailed information about a specific idea.

    Args:
        idea_id: The unique identifier of the idea to retrieve.

    Returns comprehensive details including title, description, and any generated
    documents (Business Model Canvas, Pitch Deck, PRD, Patent).
    """
    async with get_client() as client:
        idea = await client.get_idea(idea_id)

        if not idea:
            return f"Idea with ID '{idea_id}' not found."

        result = f"# {idea.get('title', 'Untitled')}\n\n"
        result += f"**ID:** {idea.get('ideaId')}\n"
        result += f"**Created:** {idea.get('createdAt', 'Unknown')}\n\n"

        if idea.get("description"):
            result += f"## Description\n{idea['description']}\n\n"

        if idea.get("businessModelCanvas"):
            result += f"## Business Model Canvas\n{idea['businessModelCanvas']}\n\n"

        if idea.get("pitchDeck"):
            result += f"## Pitch Deck\n{idea['pitchDeck'][:500]}...\n\n"

        if idea.get("productRequirementsDocument"):
            result += f"## Product Requirements Document\n{idea['productRequirementsDocument'][:500]}...\n\n"

        if idea.get("provisionalPatent"):
            result += f"## Provisional Patent Draft\n{idea['provisionalPatent'][:500]}...\n\n"

        return result


@mcp.tool()
async def create_idea(title: str, description: str | None = None) -> str:
    """
    Create a new startup idea.

    Args:
        title: A concise, memorable name for your startup idea.
        description: A detailed description of the idea, problem it solves, and target market.
                    The more detail provided, the better AI-generated documents will be.

    After creation, use generate_business_model to create a Business Model Canvas,
    or use generate_pitch_deck, generate_prd, or generate_patent for other documents.
    """
    async with get_client() as client:
        idea = await client.create_idea(title, description)

        result = f"Successfully created idea: **{idea.get('title')}**\n\n"
        result += f"**ID:** {idea.get('ideaId')}\n"
        result += f"**Created:** {idea.get('createdAt')}\n\n"

        if description:
            result += "Next steps:\n"
            result += "1. Use `generate_business_model` to create a Business Model Canvas\n"
            result += "2. Use `generate_pitch_deck` to create investor-ready slides\n"
            result += "3. Use `generate_prd` to create a Product Requirements Document\n"
        else:
            result += "Tip: Update the description using `update_idea` to enable better AI document generation.\n"

        return result


@mcp.tool()
async def update_idea(
    idea_id: str, title: str | None = None, description: str | None = None
) -> str:
    """
    Update an existing idea's title or description.

    Args:
        idea_id: The unique identifier of the idea to update.
        title: New title for the idea (optional).
        description: New description for the idea (optional).

    Updating the description will improve the quality of AI-generated documents.
    After updating, consider regenerating documents like the Business Model Canvas.
    """
    if not title and not description:
        return "Please provide at least a title or description to update."

    async with get_client() as client:
        idea = await client.update_idea(idea_id, title, description)

        result = f"Successfully updated idea: **{idea.get('title')}**\n\n"
        result += f"**ID:** {idea.get('ideaId')}\n"

        if description:
            result += "\nTip: Run `generate_business_model` to update your Business Model Canvas with the new description.\n"

        return result


@mcp.tool()
async def delete_idea(idea_id: str) -> str:
    """
    Permanently delete an idea.

    Args:
        idea_id: The unique identifier of the idea to delete.

    Warning: This action cannot be undone. All associated documents and
    investments will also be deleted.
    """
    async with get_client() as client:
        success = await client.delete_idea(idea_id)

        if success:
            return f"Successfully deleted idea with ID: {idea_id}"
        else:
            return f"Failed to delete idea with ID: {idea_id}. It may not exist or you may not have permission."


@mcp.tool()
async def generate_business_model(idea_id: str) -> str:
    """
    Generate a Business Model Canvas for an idea using AI.

    Args:
        idea_id: The unique identifier of the idea.

    Creates a comprehensive Business Model Canvas covering:
    - Value Propositions
    - Customer Segments
    - Channels
    - Customer Relationships
    - Revenue Streams
    - Key Resources
    - Key Activities
    - Key Partnerships
    - Cost Structure

    The quality depends on the idea's description - more detail yields better results.
    """
    async with get_client() as client:
        result = await client.run_background_tasks(idea_id)

        if result.get("businessModelCanvas"):
            return (
                f"Successfully generated Business Model Canvas:\n\n{result['businessModelCanvas']}"
            )
        else:
            return "Business Model Canvas generation started. Check back in a moment using `get_idea` to see the results."


@mcp.tool()
async def generate_pitch_deck(idea_id: str) -> str:
    """
    Generate an investor-ready pitch deck for an idea using AI.

    Args:
        idea_id: The unique identifier of the idea.

    Creates a professional pitch deck covering:
    - Problem & Solution
    - Market Opportunity
    - Business Model
    - Traction & Milestones
    - Team (if available)
    - Financial Projections
    - The Ask

    Best used after generating a Business Model Canvas for context.
    """
    async with get_client() as client:
        result = await client.generate_pitch_deck(idea_id)

        if result:
            return f"Successfully generated Pitch Deck:\n\n{result}"
        else:
            return "Pitch deck generation started. Check back using `get_idea` to see the results."


@mcp.tool()
async def generate_prd(idea_id: str) -> str:
    """
    Generate a Product Requirements Document (PRD) for an idea using AI.

    Args:
        idea_id: The unique identifier of the idea.

    Creates a comprehensive PRD covering:
    - Product Overview & Vision
    - User Personas
    - User Stories & Use Cases
    - Functional Requirements
    - Non-Functional Requirements
    - Technical Architecture
    - MVP Scope
    - Success Metrics

    Useful for technical planning and communicating with developers.
    """
    async with get_client() as client:
        result = await client.generate_prd(idea_id)

        if result:
            return f"Successfully generated Product Requirements Document:\n\n{result}"
        else:
            return "PRD generation started. Check back using `get_idea` to see the results."


@mcp.tool()
async def generate_patent(idea_id: str) -> str:
    """
    Generate a provisional patent draft for an idea using AI.

    Args:
        idea_id: The unique identifier of the idea.

    Creates a draft provisional patent application covering:
    - Title & Abstract
    - Technical Field
    - Background & Prior Art
    - Detailed Description
    - Claims
    - Drawings Description

    Note: This is a draft for review. Consult a patent attorney before filing.
    """
    async with get_client() as client:
        result = await client.generate_patent(idea_id)

        if result:
            return f"Successfully generated Provisional Patent Draft:\n\n{result}"
        else:
            return (
                "Patent draft generation started. Check back using `get_idea` to see the results."
            )


@mcp.tool()
async def discover_ideas(limit: int = 10, offset: int = 0) -> str:
    """
    Browse the public ideas marketplace to discover interesting startups.

    Args:
        limit: Maximum number of ideas to return (default: 10, max: 50).
        offset: Number of ideas to skip for pagination (default: 0).

    Returns publicly shared ideas with upvote counts and author information.
    Use this to find ideas to invest in or collaborate on.
    """
    limit = min(limit, 50)

    async with get_client() as client:
        ideas = await client.get_public_feed(limit, offset)

        if not ideas:
            return "No public ideas found in the marketplace."

        result = f"Discovered {len(ideas)} idea(s) in the marketplace:\n\n"
        for idea in ideas:
            result += f"### {idea.get('title', 'Untitled')}\n"
            result += f"**ID:** {idea.get('ideaId')}\n"
            result += f"**Upvotes:** {idea.get('upvoteCount', 0)} {'(You upvoted)' if idea.get('isUpvoted') else ''}\n"
            if idea.get("author"):
                result += f"**Author:** {idea['author'].get('fullName', 'Anonymous')}\n"
            if idea.get("description"):
                desc = (
                    idea["description"][:150] + "..."
                    if len(idea.get("description", "")) > 150
                    else idea.get("description", "")
                )
                result += f"**Description:** {desc}\n"
            result += "\n"

        return result


@mcp.tool()
async def upvote_idea(idea_id: str) -> str:
    """
    Upvote an idea to show support.

    Args:
        idea_id: The unique identifier of the idea to upvote.

    Upvoting helps surface the best ideas in the marketplace and
    signals interest to founders.
    """
    async with get_client() as client:
        result = await client.upvote_idea(idea_id)

        if result.get("success"):
            return f"Successfully upvoted idea. Total upvotes: {result.get('upvoteCount', 0)}"
        else:
            return "Failed to upvote idea. You may have already upvoted it."


@mcp.tool()
async def toggle_upvote(idea_id: str) -> str:
    """
    Toggle your upvote on an idea (upvote if not upvoted, remove if already upvoted).

    Args:
        idea_id: The unique identifier of the idea.
    """
    async with get_client() as client:
        result = await client.toggle_upvote(idea_id)

        if result.get("success"):
            status = "upvoted" if result.get("isUpvoted") else "removed upvote from"
            return f"Successfully {status} idea. Total upvotes: {result.get('upvoteCount', 0)}"
        else:
            return "Failed to toggle upvote."


@mcp.tool()
async def follow_user(user_id: str) -> str:
    """
    Follow a user to see their ideas in your feed.

    Args:
        user_id: The unique identifier of the user to follow.

    Following founders helps you stay updated on their new ideas and progress.
    """
    async with get_client() as client:
        result = await client.follow_user(user_id)

        if result.get("success"):
            return "Successfully followed user. You are now following them."
        else:
            return "Failed to follow user. You may already be following them."


@mcp.tool()
async def unfollow_user(user_id: str) -> str:
    """
    Unfollow a user.

    Args:
        user_id: The unique identifier of the user to unfollow.
    """
    async with get_client() as client:
        result = await client.unfollow_user(user_id)

        if result.get("success"):
            return "Successfully unfollowed user."
        else:
            return "Failed to unfollow user."


@mcp.tool()
async def get_portfolio() -> str:
    """
    Get your investment portfolio showing all ideas you've invested in.

    Returns a list of your investments with details on:
    - Investment type (cash or sweat equity)
    - Amount invested
    - Equity percentage owned
    - Investment status
    """
    async with get_client() as client:
        portfolio = await client.get_portfolio()

        if not portfolio:
            return "Your portfolio is empty. Use `invest_in_idea` to make your first investment."

        result = f"Your Portfolio ({len(portfolio)} investment(s)):\n\n"
        total_invested = 0.0

        for item in portfolio:
            result += f"### {item.get('ideaTitle', 'Unknown Idea')}\n"
            result += f"**Investment ID:** {item.get('investmentId')}\n"
            result += f"**Type:** {item.get('investmentType', 'Unknown')}\n"
            result += f"**Amount:** ${item.get('totalAmount', 0):,.2f}\n"
            result += f"**Equity:** {item.get('equityPercentage', 0):.2f}%\n"
            result += f"**Status:** {item.get('status', 'Unknown')}\n"
            result += f"**Date:** {item.get('createdAt', 'Unknown')}\n\n"
            total_invested += item.get("totalAmount", 0)

        result += f"---\n**Total Invested:** ${total_invested:,.2f}\n"

        return result


@mcp.tool()
async def invest_in_idea(
    idea_id: str, investment_type: str, amount: float, equity_percentage: float
) -> str:
    """
    Invest in a startup idea.

    Args:
        idea_id: The unique identifier of the idea to invest in.
        investment_type: Type of investment - "cash" for monetary investment,
                        "sweat_equity" for time/skill contribution.
        amount: Investment amount in USD (for cash) or equivalent value (for sweat equity).
        equity_percentage: Requested equity percentage for this investment.

    Creates an investment offer that the idea owner can accept or negotiate.
    """
    if investment_type not in ["cash", "sweat_equity"]:
        return "Invalid investment type. Use 'cash' or 'sweat_equity'."

    if amount <= 0:
        return "Investment amount must be positive."

    if equity_percentage <= 0 or equity_percentage > 100:
        return "Equity percentage must be between 0 and 100."

    async with get_client() as client:
        result = await client.create_investment(idea_id, investment_type, amount, equity_percentage)

        if result.get("investmentId"):
            return (
                f"Successfully created investment:\n\n"
                f"**Investment ID:** {result.get('investmentId')}\n"
                f"**Type:** {result.get('investmentType')}\n"
                f"**Amount:** ${result.get('amount', 0):,.2f}\n"
                f"**Equity:** {result.get('equityPercentage', 0):.2f}%\n"
                f"**Status:** {result.get('status', 'pending')}\n"
            )
        else:
            return "Failed to create investment. Please verify the idea ID and try again."


@mcp.tool()
async def get_cap_table(idea_id: str) -> str:
    """
    Get the capitalization table for an idea showing equity distribution.

    Args:
        idea_id: The unique identifier of the idea.

    Returns the equity breakdown among all investors and contributors.
    """
    async with get_client() as client:
        cap_table = await client.get_cap_table(idea_id)

        if not cap_table:
            return f"No cap table entries found for idea {idea_id}."

        result = f"Cap Table for Idea {idea_id}:\n\n"
        result += "| Holder | Equity % | Type |\n"
        result += "|--------|----------|------|\n"

        total_equity = 0.0
        for entry in cap_table:
            name = entry.get("userName", "Unknown")
            equity = entry.get("equityPercentage", 0)
            inv_type = entry.get("investmentType", "Unknown")
            result += f"| {name} | {equity:.2f}% | {inv_type} |\n"
            total_equity += equity

        result += f"\n**Total Allocated:** {total_equity:.2f}%\n"
        result += f"**Remaining:** {100 - total_equity:.2f}%\n"

        return result


@mcp.tool()
async def find_similar_ideas(description: str) -> str:
    """
    Find ideas similar to a given description for market research.

    Args:
        description: A description of the idea concept to search for.

    Useful for:
    - Competitive analysis
    - Validating idea novelty
    - Finding potential collaborators
    - Market research
    """
    async with get_client() as client:
        ideas = await client.find_similar_ideas(description)

        if not ideas:
            return "No similar ideas found. Your concept may be unique!"

        result = f"Found {len(ideas)} similar idea(s):\n\n"
        for idea in ideas:
            similarity = idea.get("similarity", 0)
            result += f"### {idea.get('title', 'Untitled')} ({similarity:.0%} similar)\n"
            result += f"**ID:** {idea.get('ideaId')}\n"
            if idea.get("description"):
                desc = (
                    idea["description"][:150] + "..."
                    if len(idea.get("description", "")) > 150
                    else idea.get("description", "")
                )
                result += f"**Description:** {desc}\n"
            result += "\n"

        return result


@mcp.tool()
async def audit_website_and_create_github_issues(
    target_url: str = "https://manifeststartup.com",
    max_pages: int = 6,
    max_issues: int = 6,
    dry_run: bool = False,
) -> str:
    """
    Crawl public website pages, turn findings into GitHub-ready issues, and optionally create them directly.

    Args:
        target_url: Public website to audit. Defaults to the production Manifest site.
        max_pages: Maximum number of same-origin public pages to crawl.
        max_issues: Maximum number of issue candidates to return or create.
        dry_run: When true, skip GitHub issue creation and return only the generated candidates.

    Notes:
    - Intended for Manifest's internal quality loop rather than a customer-facing product surface.
    - Requires `MANIFEST_AGENT_LOOP_SECRET` (or `AGENT_LOOP_SECRET`) for the
      `/api/internal/website-testing/sync-issues` endpoint.
    - The backend also needs `MANIFEST_GITHUB_TOKEN`/`GITHUB_TOKEN` and `MANIFEST_GITHUB_REPO`
      configured when `dry_run` is false.
    """
    async with get_client() as client:
        result = await client.sync_website_issues(
            target_url,
            max_pages=max_pages,
            max_issues=max_issues,
            create_github_issues=not dry_run,
            dry_run=dry_run,
        )

        candidates = result.get("issue_candidates", [])
        github = result.get("github", {})
        pages_scanned = result.get("pages_scanned", 0)

        lines = [
            f"Website audit completed for {result.get('target_url')}.",
            f"Pages scanned: {pages_scanned}",
            f"Issue candidates: {len(candidates)}",
        ]

        if dry_run:
            lines.append("GitHub issue creation: skipped (dry run)")
        else:
            lines.append(
                "GitHub issue creation: "
                f"{github.get('created_count', 0)} created, "
                f"{github.get('skipped_existing_count', 0)} skipped as existing"
            )

        if candidates:
            lines.append("")
            lines.append("Top issue candidates:")
            for candidate in candidates:
                lines.append(
                    f"- [{candidate.get('severity', 'medium').upper()}] "
                    f"{candidate.get('title')} "
                    f"({candidate.get('category', 'ux')})"
                )

        created_issues = github.get("created_issues", [])
        if created_issues:
            lines.append("")
            lines.append("Created GitHub issues:")
            for issue in created_issues:
                lines.append(f"- #{issue.get('number')} {issue.get('title')} - {issue.get('url')}")

        return "\n".join(lines)


@mcp.tool()
async def summarize_survey_feedback(
    window_days: int = 90,
    max_issues: int = 6,
    min_theme_count: int = 2,
) -> str:
    """
    Summarize Manifest's discovery and product-feedback survey signals.

    Args:
        window_days: Rolling number of days to analyze.
        max_issues: Maximum number of issue candidates to include in the summary.
        min_theme_count: Minimum recurring count before a theme is included as an issue candidate.

    Notes:
    - Intended for Manifest's internal marketability and product-pull loop.
    - Requires `MANIFEST_AGENT_LOOP_SECRET` (or `AGENT_LOOP_SECRET`) for the
      `/api/internal/survey-ops/summary` endpoint.
    """
    async with get_client() as client:
        summary = await client.get_survey_insights(
            window_days=window_days,
            include_issue_candidates=True,
            max_issues=max_issues,
            min_theme_count=min_theme_count,
        )

    lines = [
        f"Survey feedback summary for the last {summary.get('window_days', window_days)} days.",
        f"Total responses: {summary.get('total_responses', 0)}",
        f"Research responses: {summary.get('research_responses', 0)}",
        f"Product feedback responses: {summary.get('product_feedback_responses', 0)}",
        f"Signup intent: {summary.get('research_signup_intent_avg', 'n/a')}",
        f"Follow-up rate: {summary.get('research_follow_up_rate', 'n/a')}%",
        f"PMF 'Very disappointed': {summary.get('product_pmf_very_disappointed_pct', 'n/a')}%",
        f"NPS: {summary.get('product_nps_score', 'n/a')}",
        f"Satisfaction avg (1–5): {summary.get('product_satisfaction_avg', 'n/a')}",
        f"Satisfaction top box (4–5) %: {summary.get('product_satisfaction_topbox_pct', 'n/a')}",
    ]

    top_value_prop = (summary.get("top_research_value_props") or [{}])[0].get("label")
    top_barrier = (summary.get("top_research_barriers") or [{}])[0].get("label")
    top_benefit = (summary.get("top_product_benefits") or [{}])[0].get("label")
    if top_value_prop or top_barrier or top_benefit:
        lines.append("")
        lines.append("Top signals:")
        if top_value_prop:
            lines.append(f"- Strongest value prop: {top_value_prop}")
        if top_barrier:
            lines.append(f"- Biggest blocker: {top_barrier}")
        if top_benefit:
            lines.append(f"- Main product benefit: {top_benefit}")

    themes = summary.get("top_action_themes", [])
    if themes:
        lines.append("")
        lines.append("Recurring themes:")
        for theme in themes[:4]:
            lines.append(f"- {theme.get('theme')} ({theme.get('count')})")

    candidates = summary.get("issue_candidates", [])
    if candidates:
        lines.append("")
        lines.append("Issue candidates:")
        for candidate in candidates:
            lines.append(
                f"- [{candidate.get('severity', 'medium').upper()}] "
                f"{candidate.get('title')} ({candidate.get('category', 'feature')})"
            )

    return "\n".join(lines)


@mcp.tool()
async def create_survey_feedback_github_issues(
    window_days: int = 90,
    max_issues: int = 6,
    min_theme_count: int = 2,
    dry_run: bool = False,
) -> str:
    """
    Convert recurring survey signals into GitHub-ready issues and optionally create them.

    Args:
        window_days: Rolling number of days to analyze.
        max_issues: Maximum number of GitHub-ready issues to create.
        min_theme_count: Minimum recurring count before a theme becomes a candidate.
        dry_run: When true, skip GitHub writes and return only the generated candidates.

    Notes:
    - Requires `MANIFEST_AGENT_LOOP_SECRET` (or `AGENT_LOOP_SECRET`) for the
      `/api/internal/survey-ops/sync-issues` endpoint.
    - The backend also needs `MANIFEST_GITHUB_TOKEN`/`GITHUB_TOKEN` and `MANIFEST_GITHUB_REPO`
      configured when `dry_run` is false.
    """
    async with get_client() as client:
        result = await client.sync_survey_issues(
            window_days=window_days,
            max_issues=max_issues,
            min_theme_count=min_theme_count,
            create_github_issues=not dry_run,
            dry_run=dry_run,
        )

    candidates = result.get("issue_candidates", [])
    github = result.get("github", {})
    summary = result.get("summary", {})

    lines = [
        f"Survey issue sync analyzed {summary.get('total_responses', 0)} responses from the last {summary.get('window_days', window_days)} days.",
        f"Issue candidates: {len(candidates)}",
    ]

    if dry_run:
        lines.append("GitHub issue creation: skipped (dry run)")
    else:
        lines.append(
            "GitHub issue creation: "
            f"{github.get('created_count', 0)} created, "
            f"{github.get('skipped_existing_count', 0)} skipped as existing"
        )

    if candidates:
        lines.append("")
        lines.append("Top issue candidates:")
        for candidate in candidates:
            lines.append(
                f"- [{candidate.get('severity', 'medium').upper()}] "
                f"{candidate.get('title')} "
                f"({candidate.get('category', 'feature')})"
            )

    created_issues = github.get("created_issues", [])
    if created_issues:
        lines.append("")
        lines.append("Created GitHub issues:")
        for issue in created_issues:
            lines.append(f"- #{issue.get('number')} {issue.get('title')} - {issue.get('url')}")

    return "\n".join(lines)


@mcp.tool()
async def emit_production_signal(
    event_name: str,
    route: str = "",
    severity: str = "error",
    error_code: str = "",
    sample: str = "",
    create_github_issue: bool = False,
) -> str:
    """
    Record a production anomaly signal with server-side deduping and optional GitHub issue creation.

    Args:
        event_name: Stable identifier (e.g. client_error_boundary, graphql_mutation_failed).
        route: Optional route or surface label for grouping.
        severity: One of info, warn, error, critical (info is counted but never opens issues).
        error_code: Optional short code for fingerprinting.
        sample: Optional redacted context; emails are stripped server-side.
        create_github_issue: When true and thresholds are met, open a deduped GitHub issue.

    Notes:
    - Requires `MANIFEST_AGENT_LOOP_SECRET` for `/api/internal/production-signals/event`.
    - GitHub writes additionally require `MANIFEST_GITHUB_TOKEN`/`GITHUB_TOKEN`.
    """
    async with get_client() as client:
        payload = await client.post_production_signal(
            event_name=event_name,
            route=route or None,
            severity=severity,
            error_code=error_code or None,
            sample=sample or None,
            create_github_issue=create_github_issue,
        )

    lines = [
        f"Fingerprint: {payload.get('fingerprint')}",
        f"Window start: {payload.get('window_start')}",
        f"Events in window: {payload.get('event_count')}",
        f"GitHub eligible: {payload.get('github_eligible')}",
        f"GitHub issue created: {payload.get('github_issue_created')}",
    ]
    if payload.get("github_issue_url"):
        lines.append(f"URL: {payload.get('github_issue_url')}")
    if payload.get("skipped_reason"):
        lines.append(f"Note: {payload.get('skipped_reason')}")
    if payload.get("github_error"):
        lines.append(f"GitHub error: {payload.get('github_error')}")
    return "\n".join(lines)


@mcp.resource("manifest://status")
def get_server_status() -> str:
    """Get Manifest MCP server status and configuration."""
    base_url = os.environ.get("MANIFEST_API_URL", "http://localhost:8000")
    has_token = bool(os.environ.get("MANIFEST_API_TOKEN"))
    has_internal_secret = bool(
        os.environ.get("MANIFEST_AGENT_LOOP_SECRET") or os.environ.get("AGENT_LOOP_SECRET")
    )

    return f"""
# Manifest MCP Server Status

**Version:** 1.0.0
**API Endpoint:** {base_url}
**Authenticated:** {'Yes' if has_token else 'No (set MANIFEST_API_TOKEN for authenticated operations)'}
**Internal Agent Loop Secret Configured:** {'Yes' if has_internal_secret else 'No (set MANIFEST_AGENT_LOOP_SECRET for internal automation routes)'}

## Available Tools

### Idea Management
- `list_ideas` - List all your ideas
- `get_idea` - Get detailed information about an idea
- `create_idea` - Create a new startup idea
- `update_idea` - Update an existing idea
- `delete_idea` - Delete an idea

### AI Document Generation
- `generate_business_model` - Generate Business Model Canvas
- `generate_pitch_deck` - Generate investor pitch deck
- `generate_prd` - Generate Product Requirements Document
- `generate_patent` - Generate provisional patent draft

### Marketplace & Discovery
- `discover_ideas` - Browse public ideas marketplace
- `find_similar_ideas` - Find similar ideas for research
- `upvote_idea` - Upvote an idea
- `toggle_upvote` - Toggle upvote on an idea

### Internal Quality Loop
- `audit_website_and_create_github_issues` - Audit Manifest pages and sync findings into GitHub Issues
- `summarize_survey_feedback` - Summarize discovery and product-feedback signals
- `create_survey_feedback_github_issues` - Turn recurring survey signals into GitHub Issues
- `emit_production_signal` - Ingest deduped production signals with optional GitHub issue creation

### Social
- `follow_user` - Follow a user
- `unfollow_user` - Unfollow a user

### Investments
- `get_portfolio` - View your investment portfolio
- `invest_in_idea` - Invest in an idea
- `get_cap_table` - View idea capitalization table

## Configuration

Set these environment variables:
- `MANIFEST_API_URL` - API endpoint (default: http://localhost:8000)
- `MANIFEST_API_TOKEN` - Authentication token for API access
- `MANIFEST_API_KEY` - Optional API key for `/api/v1` routes when a tool uses the public REST surface
- `MANIFEST_AGENT_LOOP_SECRET` - Shared secret for the internal website and survey feedback loops
"""


def create_server() -> FastMCP:
    """Create and return the Manifest MCP server instance."""
    return mcp


def main():
    """Run the Manifest MCP server."""
    parser = argparse.ArgumentParser(description="Manifest MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host", default="localhost", help="Host for SSE transport (default: localhost)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for SSE transport (default: 8080)"
    )

    args = parser.parse_args()

    logger.info(f"Starting Manifest MCP Server (transport: {args.transport})")

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
