"""Survey analytics and GitHub triage helpers for Manifest research loops."""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from app.services.github_issue_service import (
    GitHubIssueConfigurationError,
    GitHubIssueDraft,
    GitHubIssueService,
)
from app.utils.logger import logger

OPEN_TEXT_FIELDS = {
    "research": ["friction", "job_success", "clarity", "investor_gap"],
    "product_feedback": [
        "progress_note",
        "confusing",
        "reels_feedback",
        "collab_blocker",
        "top_fix",
    ],
}

TOP_N = 5


@dataclass(frozen=True)
class SurveyThemeRule:
    key: str
    label: str
    keywords: Sequence[str]
    category: str
    issue_title: str
    suggested_fix: str
    labels: Sequence[str]


THEME_RULES: Sequence[SurveyThemeRule] = (
    SurveyThemeRule(
        key="research-credibility",
        label="Research credibility",
        keywords=(
            "citation",
            "citations",
            "source",
            "sources",
            "credible",
            "proof",
            "evidence",
            "validation",
        ),
        category="feature",
        issue_title="Add citations and source tracing to Manifest research outputs",
        suggested_fix="Show source links, citations, and claim provenance directly inside market research and comparable outputs.",
        labels=("survey-feedback", "research", "theme:trust", "theme:research"),
    ),
    SurveyThemeRule(
        key="onboarding-clarity",
        label="Onboarding clarity",
        keywords=(
            "onboarding",
            "first session",
            "first-time",
            "signup",
            "sign up",
            "start",
            "tutorial",
            "where do i",
            "confusing",
            "navigation",
        ),
        category="ux",
        issue_title="Clarify the first-session path from idea capture to a meaningful output",
        suggested_fix="Tighten onboarding copy and the first-run flow so users know the next best action without hunting through the workspace.",
        labels=("survey-feedback", "theme:onboarding", "theme:marketability"),
    ),
    SurveyThemeRule(
        key="document-quality",
        label="Document quality",
        keywords=(
            "document",
            "deck",
            "pitch deck",
            "prd",
            "patent",
            "canvas",
            "draft",
            "accuracy",
            "accurate",
            "wrong",
            "halluc",
        ),
        category="feature",
        issue_title="Improve the quality and accuracy of Manifest-generated startup artifacts",
        suggested_fix="Raise document quality with stronger prompts, clearer structure, and higher-confidence defaults for decks, PRDs, canvases, and legal drafts.",
        labels=("survey-feedback", "product-feedback", "theme:documents", "theme:feasibility"),
    ),
    SurveyThemeRule(
        key="shareability",
        label="Shareability and publishing",
        keywords=(
            "share",
            "publish",
            "investor",
            "send",
            "export",
            "one-pager",
            "one pager",
            "ready",
        ),
        category="ux",
        issue_title="Help founders reach a shareable outcome faster",
        suggested_fix="Prioritize polished, exportable outputs and clearer publish/share affordances earlier in the workflow.",
        labels=("survey-feedback", "theme:marketability", "theme:feasibility"),
    ),
    SurveyThemeRule(
        key="collaboration",
        label="Collaboration and messaging",
        keywords=(
            "collab",
            "collaborat",
            "invite",
            "message",
            "messaging",
            "cofounder",
            "advisor",
            "mentor",
        ),
        category="feature",
        issue_title="Reduce friction in collaboration and founder messaging",
        suggested_fix="Make inviting collaborators, messaging around ideas, and shared review flows more obvious and easier to complete.",
        labels=("survey-feedback", "theme:collaboration"),
    ),
    SurveyThemeRule(
        key="discovery",
        label="Discovery and Pitch Reels",
        keywords=("reel", "reels", "feed", "discover", "discovery", "shorts"),
        category="ux",
        issue_title="Increase the usefulness of discovery and Pitch Reels for idea evaluation",
        suggested_fix="Improve feed relevance, context, and transitions from discovery into a founder workspace or supporting artifacts.",
        labels=("survey-feedback", "theme:discovery", "theme:marketability"),
    ),
    SurveyThemeRule(
        key="performance",
        label="Performance and reliability",
        keywords=("slow", "speed", "lag", "loading", "load", "freeze", "crash", "bug", "error"),
        category="performance",
        issue_title="Improve survey-reported performance and reliability pain points",
        suggested_fix="Prioritize the most common slow, laggy, and error-prone flows called out in survey feedback.",
        labels=("survey-feedback", "theme:performance", "bug"),
    ),
    SurveyThemeRule(
        key="market-research",
        label="Market research and validation",
        keywords=(
            "market research",
            "market",
            "compare",
            "comparable",
            "comparables",
            "competitor",
            "competitors",
            "novelty",
            "validation",
        ),
        category="feature",
        issue_title="Strengthen market validation and comparable discovery in the first-run experience",
        suggested_fix="Surface market research, comparable analysis, and novelty checks earlier so founders can validate an idea before investing more time.",
        labels=("survey-feedback", "research", "theme:research", "theme:marketability"),
    ),
)

TRUST_SIGNAL_ISSUES = {
    "Citations or links behind claims and research": (
        "Add citations and source tracing to Manifest research outputs",
        "feature",
        "Expose claim-level citations and direct links so founders can trust market research and comparable analyses.",
        "Show citations inline and make it obvious what evidence supports each generated claim.",
        ["survey-feedback", "research", "theme:trust", "theme:research"],
    ),
    "Editable assumptions and calculations": (
        "Make assumptions and calculations editable across generated startup analyses",
        "feature",
        "Respondents want to inspect and tune the assumptions behind Manifest outputs before relying on them.",
        "Expose editable assumptions for financial, market, and planning outputs with clear downstream propagation.",
        ["survey-feedback", "research", "theme:trust", "theme:feasibility"],
    ),
    "A clear explanation of what AI generated vs. what I provided": (
        "Clarify AI provenance across Manifest-generated outputs",
        "ux",
        "Users want a cleaner line between their inputs and what the AI inferred or generated.",
        "Label source-of-truth fields, AI-generated sections, and inferred assumptions throughout the workspace.",
        ["survey-feedback", "research", "theme:trust"],
    ),
}

FIRST_OUTPUT_ISSUES = {
    "A market / comparable research brief": (
        "Promote a market research brief as a first-session outcome",
        "feature",
        "Discovery respondents most often want early validation through market research and comparable analysis.",
        "Make a research brief a prominent first-run artifact and route users to it quickly after idea capture.",
        ["survey-feedback", "research", "theme:research", "theme:marketability"],
    ),
    "A one-page idea summary I could share": (
        "Make a shareable one-page summary the fastest path out of onboarding",
        "ux",
        "Respondents want proof of value through a concise artifact they can share immediately.",
        "Bias the first-run flow toward generating a polished one-page summary without extra setup.",
        ["survey-feedback", "research", "theme:onboarding", "theme:marketability"],
    ),
    "A pitch deck": (
        "Shorten the path from idea capture to a credible first pitch deck",
        "feature",
        "Pitch decks remain one of the highest-value outputs for early founder evaluation and sharing.",
        "Surface a deck-ready path earlier and make the first draft feel closer to investor-ready.",
        ["survey-feedback", "research", "theme:documents", "theme:marketability"],
    ),
}

# Matches ResearchSurveyPage GOAL_OPTIONS (discovery survey).
GOAL_ISSUES = {
    "Validate whether an idea is worth pursuing": (
        "Double down on idea validation in the first session",
        "feature",
        "Discovery respondents often want to know if an idea is worth pursuing before investing more time.",
        "Surface validation loops (comparables, novelty, structured canvases) immediately after idea capture.",
        ["survey-feedback", "research", "theme:research", "theme:marketability"],
    ),
    "Turn an idea into investor- or team-ready artifacts": (
        "Shorten the path from idea capture to investor- or team-ready artifacts",
        "feature",
        "Many visitors want polished outputs they can share with investors or collaborators.",
        "Prioritize deck, one-pager, and export flows with minimal setup.",
        ["survey-feedback", "research", "theme:documents", "theme:marketability"],
    ),
    "Compare an idea against the market or similar companies": (
        "Make market and comparable research the hero of early sessions",
        "feature",
        "Respondents want to benchmark ideas against the market and similar companies.",
        "Put market research and comparables one click away from the first idea capture.",
        ["survey-feedback", "research", "theme:research", "theme:marketability"],
    ),
    "Find startups to invest in, advise, or follow": (
        "Improve investor-side discovery and evaluation workflows",
        "ux",
        "Investor-side respondents want to find and evaluate startups on-platform.",
        "Strengthen discovery, reels, and profiles so investors can triage without friction.",
        ["survey-feedback", "research", "theme:discovery", "theme:marketability"],
    ),
    "Browse discovery / pitch-style content": (
        "Make discovery and pitch-style feeds more compelling",
        "ux",
        "Visitors want to browse ideas like a feed before committing.",
        "Improve feed relevance, context cards, and handoff into a workspace.",
        ["survey-feedback", "research", "theme:discovery", "theme:marketability"],
    ),
    "General curiosity": (
        "Reduce friction for curious first-time visitors",
        "ux",
        "A segment is exploring without a concrete task—help them reach one meaningful artifact fast.",
        "Offer a single obvious next step and a lightweight win in under five minutes.",
        ["survey-feedback", "research", "theme:onboarding", "theme:marketability"],
    ),
}

# Subset of ResearchSurveyPage BETTER_MEANS_OPTIONS → recurring product themes.
BETTER_MEANS_ISSUES = {
    "Trust — I understand what the AI did and can verify it": (
        "Make AI provenance and verifiability obvious in generated outputs",
        "ux",
        "Discovery respondents want to understand and verify what the AI produced.",
        "Label AI vs user content, add citations, and expose editable assumptions.",
        ["survey-feedback", "research", "theme:trust", "theme:research"],
    ),
    "Speed — from rough idea to credible artifacts faster": (
        "Cut time from rough idea to a credible first artifact",
        "ux",
        "Users want speed from idea to something they can use or share.",
        "Remove redundant steps and default to the fastest high-value output path.",
        ["survey-feedback", "research", "theme:onboarding", "theme:marketability"],
    ),
    "Quality — stronger first drafts I can ship or share": (
        "Raise first-draft quality for shareable startup artifacts",
        "feature",
        "Respondents want stronger first drafts they can ship without heavy rework.",
        "Improve prompts, structure, and defaults for decks, briefs, and summaries.",
        ["survey-feedback", "research", "theme:documents", "theme:feasibility"],
    ),
    "Collaboration — easier to loop in co-founders or advisors": (
        "Reduce friction when looping in co-founders or advisors",
        "feature",
        "Discovery users want collaboration baked into the workflow.",
        "Surface invites, shared review, and messaging around ideas earlier.",
        ["survey-feedback", "research", "theme:collaboration"],
    ),
    "Discovery — finding or comparing ideas and founders": (
        "Improve discovery for comparing ideas and founders",
        "ux",
        "Users want to find and compare ideas and founders on-platform.",
        "Improve search, reels context, and transitions from browsing into a workspace.",
        ["survey-feedback", "research", "theme:discovery", "theme:marketability"],
    ),
}

FAMILIARITY_ISSUES = {
    "Limited — I mostly use traditional docs, slides, or spreadsheets": (
        "Onboard users who are newer to AI-native startup workflows",
        "ux",
        "A meaningful segment is still anchored in traditional docs and needs a gentler bridge into AI-assisted work.",
        "Use plainer language, progressive disclosure, and familiar document metaphors in the first session.",
        ["survey-feedback", "research", "theme:onboarding", "theme:trust"],
    ),
    "New — I am exploring what AI can do for startups": (
        "Help first-time AI users reach a concrete win quickly",
        "ux",
        "Explorers need a short path to a tangible artifact so the product clicks.",
        "Offer a guided first outcome with clear before/after and minimal jargon.",
        ["survey-feedback", "research", "theme:onboarding", "theme:marketability"],
    ),
}


class SurveyOpsConfigurationError(RuntimeError):
    """Raised when internal survey automation is missing required configuration."""


class SurveyOpsService:
    """Summarize survey responses and turn recurring signals into GitHub-ready actions."""

    def __init__(
        self,
        *,
        github_issue_service: GitHubIssueService | None = None,
        github_api_base: str = "https://api.github.com",
    ):
        self.github_api_base = github_api_base.rstrip("/")
        self.github_issue_service = github_issue_service or GitHubIssueService(
            github_api_base=self.github_api_base
        )

    def get_summary(
        self,
        db,
        *,
        window_days: int = 90,
        include_issue_candidates: bool = False,
        max_issues: int = 6,
        min_theme_count: int = 2,
    ) -> dict[str, Any]:
        safe_window_days = max(7, min(int(window_days or 90), 365))
        rows = self._fetch_rows(db, safe_window_days)
        summary = self._build_summary(rows, safe_window_days)
        if include_issue_candidates:
            summary["issue_candidates"] = [
                self._serialize_issue_candidate(candidate)
                for candidate in self._build_issue_candidates(
                    summary,
                    max_issues=max_issues,
                    min_theme_count=min_theme_count,
                )
            ]
        return summary

    async def sync_issues(
        self,
        db,
        *,
        window_days: int = 90,
        max_issues: int = 6,
        min_theme_count: int = 2,
        create_github_issues: bool = True,
        dry_run: bool = False,
        github_repo: str | None = None,
        extra_labels: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        summary = self.get_summary(
            db,
            window_days=window_days,
            include_issue_candidates=True,
            max_issues=max_issues,
            min_theme_count=min_theme_count,
        )
        repo = (
            github_repo
            or os.getenv("MANIFEST_GITHUB_REPO")
            or os.getenv("GITHUB_REPOSITORY")
            or "Manifest-Startup/Manifest"
        )
        issue_candidates = summary.get("issue_candidates", [])
        extra_labels_list = [label for label in (extra_labels or []) if label]

        github_summary = {
            "repo": repo,
            "create_requested": bool(create_github_issues),
            "dry_run": bool(dry_run),
            "created_count": 0,
            "skipped_existing_count": 0,
            "created_issues": [],
            "skipped_issues": [],
        }

        if issue_candidates and create_github_issues:
            if dry_run:
                github_summary["skipped_issues"] = [
                    {"title": candidate["title"], "reason": "dry_run"}
                    for candidate in issue_candidates
                ]
            else:
                issue_drafts = [
                    GitHubIssueDraft(
                        title=candidate["title"],
                        body=self._build_issue_body(candidate, summary=summary),
                        labels=candidate["labels"],
                    )
                    for candidate in issue_candidates
                ]
                try:
                    async with httpx.AsyncClient(
                        timeout=20.0,
                        headers={"User-Agent": "ManifestSurveyOps/1.0"},
                    ) as client:
                        github_summary = await self.github_issue_service.create_issues(
                            client,
                            repo=repo,
                            issue_drafts=issue_drafts,
                            extra_labels=extra_labels_list,
                        )
                except GitHubIssueConfigurationError as exc:
                    raise SurveyOpsConfigurationError(str(exc)) from exc

        return {
            "summary": summary,
            "issue_candidates": issue_candidates,
            "github": github_summary,
        }

    def _fetch_rows(self, db, window_days: int) -> list[dict[str, Any]]:
        since = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        response = (
            db.table("survey_responses")
            .select("*")
            .gte("created_at", since)
            .order("created_at", desc=True)
            .execute()
        )
        rows = response.data or []
        normalized_rows = []
        for row in rows:
            answers = row.get("answers") or {}
            if isinstance(answers, str):
                try:
                    answers = json.loads(answers)
                except json.JSONDecodeError:
                    logger.warning(
                        "[SurveyOps] Failed to parse answers JSON for response %s",
                        row.get("response_id"),
                    )
                    answers = {}

            normalized_rows.append(
                {
                    **row,
                    "answers": answers if isinstance(answers, dict) else {},
                    "survey_type": (row.get("survey_type") or "").strip(),
                }
            )
        return normalized_rows

    def _build_summary(self, rows: list[dict[str, Any]], window_days: int) -> dict[str, Any]:
        research_rows = [row for row in rows if row.get("survey_type") == "research"]
        product_rows = [row for row in rows if row.get("survey_type") == "product_feedback"]

        top_action_themes = self._summarize_open_text_themes(rows)

        product_satisfaction_avg = self._average_numeric(product_rows, "satisfaction")
        product_ease_avg = self._average_numeric(product_rows, "ease_score")
        product_deliverable_avg = self._average_numeric(product_rows, "deliverable_score")
        if product_deliverable_avg is None and product_satisfaction_avg is not None:
            product_deliverable_avg = product_satisfaction_avg

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_days": window_days,
            "total_responses": len(rows),
            "research_responses": len(research_rows),
            "product_feedback_responses": len(product_rows),
            "research_signup_intent_avg": self._average_numeric(research_rows, "signup_intent"),
            "research_follow_up_rate": self._yes_rate(research_rows, "wants_call", target="yes"),
            "product_pmf_very_disappointed_pct": self._choice_rate(
                product_rows, "pmf_disappointment", target="Very disappointed"
            ),
            "product_nps_score": self._nps_score(product_rows),
            "product_progress_avg": self._average_numeric(product_rows, "progress_score"),
            "product_deliverable_avg": product_deliverable_avg,
            "product_satisfaction_avg": product_satisfaction_avg,
            "product_ease_avg": product_ease_avg,
            "product_satisfaction_topbox_pct": self._topbox_pct(
                product_rows, "satisfaction", min_score=4
            ),
            "product_ai_quality_avg": self._average_numeric(product_rows, "ai_quality"),
            "top_research_roles": self._distribution(research_rows, "role"),
            "top_research_value_props": self._distribution(research_rows, "value_prop"),
            "top_research_barriers": self._distribution_prefer_field(
                research_rows, "better_means", "biggest_barrier"
            ),
            "top_research_first_outputs": self._distribution_prefer_field(
                research_rows, "goal", "first_output"
            ),
            "top_research_trust_signals": self._distribution_prefer_field(
                research_rows, "familiarity", "trust_signal"
            ),
            "top_product_benefits": self._distribution(product_rows, "main_benefit"),
            "top_product_tasks": self._distribution(product_rows, "primary_task"),
            "top_action_themes": top_action_themes,
        }

    def _distribution(self, rows: list[dict[str, Any]], field_name: str) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        answered = 0
        for row in rows:
            value = row["answers"].get(field_name)
            if isinstance(value, list):
                items = [str(item).strip() for item in value if str(item).strip()]
                if items:
                    answered += 1
                for item in items:
                    counts[item] += 1
            else:
                normalized = str(value).strip() if value is not None else ""
                if normalized:
                    counts[normalized] += 1
                    answered += 1

        if not counts:
            return []

        base = max(answered, 1)
        return [
            {
                "label": label,
                "count": count,
                "percentage": round((count / base) * 100, 1),
            }
            for label, count in counts.most_common(TOP_N)
        ]

    def _summarize_open_text_themes(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        theme_counts: Counter[str] = Counter()
        theme_labels: dict[str, str] = {}
        for row in rows:
            survey_type = row.get("survey_type") or ""
            for field_name in OPEN_TEXT_FIELDS.get(survey_type, []):
                value = row["answers"].get(field_name)
                text = " ".join(str(value).split()).strip().lower() if value else ""
                if not text:
                    continue
                matched = False
                for rule in THEME_RULES:
                    if any(keyword in text for keyword in rule.keywords):
                        theme_counts[rule.key] += 1
                        theme_labels[rule.key] = rule.label
                        matched = True
                if not matched and len(text.split()) >= 4:
                    theme_counts["other"] += 1
                    theme_labels["other"] = "Other recurring friction"

        return [
            {"theme": theme_labels[key], "count": count}
            for key, count in theme_counts.most_common(TOP_N)
        ]

    def _has_nonempty_answer(self, rows: list[dict[str, Any]], field_name: str) -> bool:
        for row in rows:
            value = row["answers"].get(field_name)
            if value is None or value == "":
                continue
            if isinstance(value, list):
                if any(str(item).strip() for item in value):
                    return True
            elif str(value).strip():
                return True
        return False

    def _distribution_prefer_field(
        self,
        rows: list[dict[str, Any]],
        primary_field: str,
        fallback_field: str,
    ) -> list[dict[str, Any]]:
        if self._has_nonempty_answer(rows, primary_field):
            return self._distribution(rows, primary_field)
        return self._distribution(rows, fallback_field)

    def _topbox_pct(
        self, rows: list[dict[str, Any]], field_name: str, *, min_score: int
    ) -> float | None:
        scores: list[float] = []
        for row in rows:
            raw = row["answers"].get(field_name)
            if raw is None or raw == "":
                continue
            try:
                scores.append(float(raw))
            except (TypeError, ValueError):
                continue
        if not scores:
            return None
        top = sum(1 for s in scores if s >= min_score)
        return round((top / len(scores)) * 100, 1)

    def _build_issue_candidates(
        self,
        summary: dict[str, Any],
        *,
        max_issues: int,
        min_theme_count: int,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []

        candidates.extend(
            self._build_open_text_issue_candidates(summary, min_theme_count=min_theme_count)
        )
        candidates.extend(
            self._build_better_means_candidates(summary, min_theme_count=min_theme_count)
        )
        candidates.extend(
            self._build_trust_signal_candidates(summary, min_theme_count=min_theme_count)
        )
        candidates.extend(
            self._build_first_output_candidates(summary, min_theme_count=min_theme_count)
        )

        low_pmf_candidate = self._build_low_pmf_candidate(summary)
        if low_pmf_candidate:
            candidates.append(low_pmf_candidate)

        candidates = self._dedupe_candidates(candidates)
        candidates.sort(
            key=lambda candidate: (
                self._severity_rank(candidate["severity"]),
                -candidate["signal_count"],
                candidate["title"],
            )
        )
        return candidates[:max_issues]

    def _build_open_text_issue_candidates(
        self, summary: dict[str, Any], *, min_theme_count: int
    ) -> list[dict[str, Any]]:
        theme_lookup = {
            theme["theme"]: theme["count"] for theme in summary.get("top_action_themes", [])
        }
        candidates = []
        for rule in THEME_RULES:
            count = theme_lookup.get(rule.label, 0)
            if count < min_theme_count:
                continue
            candidates.append(
                {
                    "title": rule.issue_title,
                    "category": rule.category,
                    "severity": "high" if count >= max(5, min_theme_count + 2) else "medium",
                    "summary": f"Survey respondents repeatedly surfaced {rule.label.lower()} as a point of friction or a missing capability.",
                    "suggested_fix": rule.suggested_fix,
                    "evidence": [
                        f"{rule.label} appeared in {count} open-text survey responses.",
                        "Signal compiled from recurring themes in research and product-feedback free text fields.",
                    ],
                    "labels": list(rule.labels),
                    "signal_count": count,
                }
            )
        return candidates

    def _build_better_means_candidates(
        self, summary: dict[str, Any], *, min_theme_count: int
    ) -> list[dict[str, Any]]:
        candidates = []
        for item in summary.get("top_research_barriers", [])[:2]:
            mapping = BETTER_MEANS_ISSUES.get(item["label"])
            if not mapping or item["count"] < min_theme_count:
                continue
            title, category, issue_summary, suggested_fix, labels = mapping
            candidates.append(
                {
                    "title": title,
                    "category": category,
                    "severity": "high" if item["percentage"] >= 30 else "medium",
                    "summary": issue_summary,
                    "suggested_fix": suggested_fix,
                    "evidence": [
                        f"'{item['label']}' was selected by {item['count']} research respondents ({item['percentage']}%).",
                    ],
                    "labels": labels,
                    "signal_count": item["count"],
                }
            )
        return candidates

    def _build_trust_signal_candidates(
        self, summary: dict[str, Any], *, min_theme_count: int
    ) -> list[dict[str, Any]]:
        candidates = []
        for item in summary.get("top_research_trust_signals", [])[:2]:
            mapping = TRUST_SIGNAL_ISSUES.get(item["label"]) or FAMILIARITY_ISSUES.get(
                item["label"]
            )
            if not mapping or item["count"] < min_theme_count:
                continue
            title, category, issue_summary, suggested_fix, labels = mapping
            candidates.append(
                {
                    "title": title,
                    "category": category,
                    "severity": "high" if item["percentage"] >= 35 else "medium",
                    "summary": issue_summary,
                    "suggested_fix": suggested_fix,
                    "evidence": [
                        f"'{item['label']}' was selected by {item['count']} research respondents ({item['percentage']}%).",
                    ],
                    "labels": labels,
                    "signal_count": item["count"],
                }
            )
        return candidates

    def _build_first_output_candidates(
        self, summary: dict[str, Any], *, min_theme_count: int
    ) -> list[dict[str, Any]]:
        candidates = []
        for item in summary.get("top_research_first_outputs", [])[:2]:
            mapping = GOAL_ISSUES.get(item["label"]) or FIRST_OUTPUT_ISSUES.get(item["label"])
            if not mapping or item["count"] < min_theme_count:
                continue
            title, category, issue_summary, suggested_fix, labels = mapping
            candidates.append(
                {
                    "title": title,
                    "category": category,
                    "severity": "medium",
                    "summary": issue_summary,
                    "suggested_fix": suggested_fix,
                    "evidence": [
                        f"'{item['label']}' was the top primary goal or desired first output for {item['count']} research respondents ({item['percentage']}%).",
                    ],
                    "labels": labels,
                    "signal_count": item["count"],
                }
            )
        return candidates

    def _build_low_pmf_candidate(self, summary: dict[str, Any]) -> dict[str, Any] | None:
        product_count = summary.get("product_feedback_responses") or 0
        if product_count < 5:
            return None

        very_disappointed_pct = summary.get("product_pmf_very_disappointed_pct")
        deliverable_avg = summary.get("product_deliverable_avg")
        satisfaction_avg = summary.get("product_satisfaction_avg")

        if very_disappointed_pct is not None:
            if very_disappointed_pct >= 40 and (deliverable_avg or 0) >= 3.5:
                return None
            severity = "high" if very_disappointed_pct < 25 else "medium"
            evidence = [
                f"Only {very_disappointed_pct}% of product-feedback respondents said they would be 'Very disappointed' without Manifest.",
            ]
            if deliverable_avg is not None:
                evidence.append(
                    f"Average shareability/satisfaction score is {deliverable_avg} / 5."
                )
            return {
                "title": "Strengthen first-session value before scaling acquisition",
                "category": "ux",
                "severity": severity,
                "summary": "Product pull is still weak enough that Manifest should focus on helping users reach obvious value quickly before leaning harder on growth.",
                "suggested_fix": "Simplify the first-run path, bias it toward a clear high-value output, and cut any steps that delay visible progress.",
                "evidence": evidence,
                "labels": [
                    "survey-feedback",
                    "product-feedback",
                    "theme:onboarding",
                    "theme:feasibility",
                ],
                "signal_count": product_count,
            }

        if satisfaction_avg is None:
            return None
        if satisfaction_avg >= 3.5:
            return None

        severity = "high" if satisfaction_avg < 2.5 else "medium"
        evidence = [
            f"Average product satisfaction (1–5) is {satisfaction_avg} across {product_count} product-feedback responses.",
        ]
        topbox = summary.get("product_satisfaction_topbox_pct")
        if topbox is not None:
            evidence.append(f"{topbox}% rated satisfaction 4 or 5 (top box).")

        return {
            "title": "Strengthen first-session value before scaling acquisition",
            "category": "ux",
            "severity": severity,
            "summary": "Satisfaction scores suggest product-market fit is not yet strong; prioritize clearer value in the first session.",
            "suggested_fix": "Simplify the first-run path, bias it toward a clear high-value output, and cut any steps that delay visible progress.",
            "evidence": evidence,
            "labels": [
                "survey-feedback",
                "product-feedback",
                "theme:onboarding",
                "theme:feasibility",
            ],
            "signal_count": product_count,
        }

    def _dedupe_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen = set()
        for candidate in candidates:
            key = " ".join(candidate["title"].lower().split())
            if key in seen:
                continue
            deduped.append(candidate)
            seen.add(key)
        return deduped

    def _average_numeric(self, rows: list[dict[str, Any]], field_name: str) -> float | None:
        values = []
        for row in rows:
            value = row["answers"].get(field_name)
            if value is None or value == "":
                continue
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                continue
        if not values:
            return None
        return round(sum(values) / len(values), 2)

    def _yes_rate(
        self, rows: list[dict[str, Any]], field_name: str, *, target: str
    ) -> float | None:
        answered = 0
        matches = 0
        for row in rows:
            value = row["answers"].get(field_name)
            if value is None or value == "":
                continue
            answered += 1
            if str(value).strip().lower() == target.lower():
                matches += 1
        if not answered:
            return None
        return round((matches / answered) * 100, 1)

    def _choice_rate(
        self, rows: list[dict[str, Any]], field_name: str, *, target: str
    ) -> float | None:
        answered = 0
        matches = 0
        for row in rows:
            value = row["answers"].get(field_name)
            if value is None or value == "":
                continue
            answered += 1
            if str(value).strip() == target:
                matches += 1
        if not answered:
            return None
        return round((matches / answered) * 100, 1)

    def _nps_score(self, rows: list[dict[str, Any]]) -> int | None:
        scores = []
        for row in rows:
            raw = row["answers"].get("nps")
            if raw is None or raw == "":
                continue
            try:
                scores.append(int(raw))
            except (TypeError, ValueError):
                continue
        if not scores:
            return None
        promoters = sum(1 for score in scores if score >= 9)
        detractors = sum(1 for score in scores if score <= 6)
        total = len(scores)
        return int(round(((promoters / total) - (detractors / total)) * 100))

    def _severity_rank(self, severity: str) -> int:
        return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get((severity or "").lower(), 99)

    def _build_issue_body(self, candidate: dict[str, Any], *, summary: dict[str, Any]) -> str:
        evidence_lines = (
            "\n".join(f"- {item}" for item in candidate.get("evidence", []))
            or "- No additional evidence captured."
        )
        return (
            f"## Summary\n{candidate['summary']}\n\n"
            "## Why It Matters\n"
            "- This issue was generated from recurring Manifest survey signals.\n"
            f"- Window: last {summary['window_days']} days\n"
            f"- Total responses reviewed: {summary['total_responses']}\n\n"
            f"## Evidence\n{evidence_lines}\n\n"
            f"## Suggested Fix\n{candidate['suggested_fix']}\n\n"
            "## Survey Snapshot\n"
            f"- Research responses: {summary['research_responses']}\n"
            f"- Product feedback responses: {summary['product_feedback_responses']}\n"
            f"- Signal count: {candidate['signal_count']}\n"
            f"- Generated at: {summary['generated_at']}\n"
            "- Generated by: Manifest survey feedback loop\n"
        )

    def _serialize_issue_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": candidate["title"],
            "category": candidate["category"],
            "severity": candidate["severity"],
            "summary": candidate["summary"],
            "suggested_fix": candidate["suggested_fix"],
            "evidence": list(candidate["evidence"]),
            "labels": list(candidate["labels"]),
            "signal_count": candidate["signal_count"],
        }


survey_ops_service = SurveyOpsService()
