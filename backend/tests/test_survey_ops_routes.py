"""Route tests for internal survey insights and GitHub sync endpoints."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import fastapi_app
import app.routes.survey_ops_routes as survey_ops_routes
from app.services.survey_ops_service import SurveyOpsConfigurationError


def test_survey_summary_route_returns_service_payload():
    client = TestClient(fastapi_app)

    with patch.object(
        survey_ops_routes.survey_ops_service,
        "get_summary",
        return_value={"window_days": 90, "total_responses": 9, "top_action_themes": []},
    ), patch.dict("os.environ", {"MANIFEST_AGENT_LOOP_SECRET": "loop-secret"}):
        response = client.post(
            "/api/internal/survey-ops/summary",
            json={"window_days": 90, "include_issue_candidates": False},
            headers={"X-Manifest-Agent-Key": "loop-secret"},
        )

    assert response.status_code == 200
    assert response.json()["total_responses"] == 9


def test_survey_issue_sync_route_surfaces_configuration_errors():
    client = TestClient(fastapi_app)

    with patch.object(
        survey_ops_routes.survey_ops_service,
        "sync_issues",
        new=AsyncMock(side_effect=SurveyOpsConfigurationError("GitHub token missing")),
    ), patch.dict("os.environ", {"MANIFEST_AGENT_LOOP_SECRET": "loop-secret"}):
        response = client.post(
            "/api/internal/survey-ops/sync-issues",
            json={"dry_run": False},
            headers={"X-Manifest-Agent-Key": "loop-secret"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "GitHub token missing"


def test_survey_routes_reject_invalid_agent_key():
    client = TestClient(fastapi_app)

    with patch.dict("os.environ", {"MANIFEST_AGENT_LOOP_SECRET": "loop-secret"}):
        response = client.post(
            "/api/internal/survey-ops/summary",
            json={"window_days": 90},
            headers={"X-Manifest-Agent-Key": "wrong-secret"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid agent loop key"
