"""GraphQL types and mappers for the survey and the contact form."""

from datetime import datetime
from typing import Any

import strawberry


@strawberry.type
class ContactForm:
    first_name: str
    last_name: str
    email: str
    message: str


@strawberry.type
class SurveyDistributionItem:
    label: str
    count: int
    percentage: float | None = None


@strawberry.type
class SurveyThemeSummary:
    theme: str
    count: int


@strawberry.type
class SurveyInsights:
    generated_at: str
    window_days: int
    total_responses: int
    research_responses: int
    product_feedback_responses: int
    research_signup_intent_avg: float | None = None
    research_follow_up_rate: float | None = None
    product_pmf_very_disappointed_pct: float | None = None
    product_nps_score: int | None = None
    product_progress_avg: float | None = None
    product_deliverable_avg: float | None = None
    product_satisfaction_avg: float | None = None
    product_ease_avg: float | None = None
    product_satisfaction_topbox_pct: float | None = None
    product_ai_quality_avg: float | None = None
    top_research_roles: list[SurveyDistributionItem]
    top_research_value_props: list[SurveyDistributionItem]
    top_research_barriers: list[SurveyDistributionItem]
    top_research_first_outputs: list[SurveyDistributionItem]
    top_research_trust_signals: list[SurveyDistributionItem]
    top_product_benefits: list[SurveyDistributionItem]
    top_product_tasks: list[SurveyDistributionItem]
    top_action_themes: list[SurveyThemeSummary]


@strawberry.input
class ContactFormInput:
    first_name: str
    last_name: str
    email: str
    message: str


@strawberry.input
class SubmitSurveyInput:
    """In-app survey payload; answers_json is a JSON object of question keys to values."""

    survey_type: str
    answers_json: str
    contact_email: str | None = None


def _build_survey_distribution_items(items: list[dict[str, Any]]) -> list[SurveyDistributionItem]:
    distribution_items: list[SurveyDistributionItem] = []
    for item in items or []:
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        distribution_items.append(
            SurveyDistributionItem(
                label=label,
                count=int(item.get("count") or 0),
                percentage=(
                    float(item["percentage"]) if item.get("percentage") is not None else None
                ),
            )
        )
    return distribution_items


def _build_survey_theme_summaries(items: list[dict[str, Any]]) -> list[SurveyThemeSummary]:
    theme_items: list[SurveyThemeSummary] = []
    for item in items or []:
        theme = str(item.get("theme") or "").strip()
        if not theme:
            continue
        theme_items.append(
            SurveyThemeSummary(
                theme=theme,
                count=int(item.get("count") or 0),
            )
        )
    return theme_items


def _build_survey_insights(summary: dict[str, Any]) -> SurveyInsights:
    return SurveyInsights(
        generated_at=str(summary.get("generated_at") or datetime.utcnow().isoformat()),
        window_days=int(summary.get("window_days") or 90),
        total_responses=int(summary.get("total_responses") or 0),
        research_responses=int(summary.get("research_responses") or 0),
        product_feedback_responses=int(summary.get("product_feedback_responses") or 0),
        research_signup_intent_avg=(
            float(summary["research_signup_intent_avg"])
            if summary.get("research_signup_intent_avg") is not None
            else None
        ),
        research_follow_up_rate=(
            float(summary["research_follow_up_rate"])
            if summary.get("research_follow_up_rate") is not None
            else None
        ),
        product_pmf_very_disappointed_pct=(
            float(summary["product_pmf_very_disappointed_pct"])
            if summary.get("product_pmf_very_disappointed_pct") is not None
            else None
        ),
        product_nps_score=(
            int(summary["product_nps_score"])
            if summary.get("product_nps_score") is not None
            else None
        ),
        product_progress_avg=(
            float(summary["product_progress_avg"])
            if summary.get("product_progress_avg") is not None
            else None
        ),
        product_deliverable_avg=(
            float(summary["product_deliverable_avg"])
            if summary.get("product_deliverable_avg") is not None
            else None
        ),
        product_satisfaction_avg=(
            float(summary["product_satisfaction_avg"])
            if summary.get("product_satisfaction_avg") is not None
            else None
        ),
        product_ease_avg=(
            float(summary["product_ease_avg"])
            if summary.get("product_ease_avg") is not None
            else None
        ),
        product_satisfaction_topbox_pct=(
            float(summary["product_satisfaction_topbox_pct"])
            if summary.get("product_satisfaction_topbox_pct") is not None
            else None
        ),
        product_ai_quality_avg=(
            float(summary["product_ai_quality_avg"])
            if summary.get("product_ai_quality_avg") is not None
            else None
        ),
        top_research_roles=_build_survey_distribution_items(
            summary.get("top_research_roles") or []
        ),
        top_research_value_props=_build_survey_distribution_items(
            summary.get("top_research_value_props") or []
        ),
        top_research_barriers=_build_survey_distribution_items(
            summary.get("top_research_barriers") or []
        ),
        top_research_first_outputs=_build_survey_distribution_items(
            summary.get("top_research_first_outputs") or []
        ),
        top_research_trust_signals=_build_survey_distribution_items(
            summary.get("top_research_trust_signals") or []
        ),
        top_product_benefits=_build_survey_distribution_items(
            summary.get("top_product_benefits") or []
        ),
        top_product_tasks=_build_survey_distribution_items(summary.get("top_product_tasks") or []),
        top_action_themes=_build_survey_theme_summaries(summary.get("top_action_themes") or []),
    )
