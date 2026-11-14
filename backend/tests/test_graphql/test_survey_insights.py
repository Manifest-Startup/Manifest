from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.graphql.schema import Query
from app.auth.current_user import generate_demo_token


@pytest.mark.asyncio
async def test_survey_insights_requires_auth_and_maps_summary_payload():
    token = generate_demo_token("user-123", "hello@example.com")
    request = MagicMock()
    request.cookies.get.return_value = None
    request.headers.get.return_value = f"Bearer {token}"
    info = SimpleNamespace(context={"request": request, "db": MagicMock()})

    with patch(
        "app.graphql.schema.survey_ops_service.get_summary",
        return_value={
            "generated_at": "2026-04-05T12:00:00Z",
            "window_days": 30,
            "total_responses": 12,
            "research_responses": 7,
            "product_feedback_responses": 5,
            "research_signup_intent_avg": 4.2,
            "research_follow_up_rate": 40.0,
            "product_pmf_very_disappointed_pct": 20.0,
            "product_nps_score": 10,
            "product_progress_avg": 3.6,
            "product_deliverable_avg": 3.8,
            "product_satisfaction_avg": 3.9,
            "product_ease_avg": 3.4,
            "product_satisfaction_topbox_pct": 55.0,
            "product_ai_quality_avg": 4.1,
            "top_research_roles": [{"label": "Founder (building a company)", "count": 4, "percentage": 57.1}],
            "top_research_value_props": [{"label": "One workspace instead of a pile of tools", "count": 3, "percentage": 42.9}],
            "top_research_barriers": [],
            "top_research_first_outputs": [],
            "top_research_trust_signals": [],
            "top_product_benefits": [],
            "top_product_tasks": [],
            "top_action_themes": [{"theme": "Onboarding clarity", "count": 2}],
        },
    ) as get_summary:
        result = await Query().survey_insights(info, window_days=30)

    get_summary.assert_called_once_with(info.context["db"], window_days=30)
    assert result.window_days == 30
    assert result.total_responses == 12
    assert result.top_research_value_props[0].label == "One workspace instead of a pile of tools"
    assert result.top_action_themes[0].theme == "Onboarding clarity"
