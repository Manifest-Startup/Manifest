"""Route tests for website issue sync endpoints."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import fastapi_app
import app.routes.website_testing_routes as website_testing_routes
from app.services.operations.website_issue_sync import WebsiteIssueSyncConfigurationError


def test_sync_website_issues_route_returns_service_payload():
    client = TestClient(fastapi_app)

    with patch.object(
        website_testing_routes.website_issue_sync_service,
        "audit_website_and_sync_issues",
        new=AsyncMock(
            return_value={
                "target_url": "https://manifeststartup.com",
                "repo": "Manifest-Startup/Manifest",
                "pages_scanned": 1,
                "issue_candidates": [],
                "github": {"created_count": 0, "skipped_existing_count": 0},
            }
        ),
    ), patch.dict("os.environ", {"MANIFEST_AGENT_LOOP_SECRET": "loop-secret"}):
            response = client.post(
                "/api/internal/website-testing/sync-issues",
                json={"target_url": "https://manifeststartup.com", "dry_run": True},
                headers={"X-Manifest-Agent-Key": "loop-secret"},
            )

    assert response.status_code == 200
    assert response.json()["repo"] == "Manifest-Startup/Manifest"


def test_sync_website_issues_route_surfaces_configuration_errors():
    client = TestClient(fastapi_app)

    with patch.object(
        website_testing_routes.website_issue_sync_service,
        "audit_website_and_sync_issues",
        new=AsyncMock(side_effect=WebsiteIssueSyncConfigurationError("GitHub token missing")),
    ), patch.dict("os.environ", {"MANIFEST_AGENT_LOOP_SECRET": "loop-secret"}):
            response = client.post(
                "/api/internal/website-testing/sync-issues",
                json={"target_url": "https://manifeststartup.com"},
                headers={"X-Manifest-Agent-Key": "loop-secret"},
            )

    assert response.status_code == 503
    assert response.json()["detail"] == "GitHub token missing"


def test_sync_website_issues_route_rejects_invalid_agent_key():
    client = TestClient(fastapi_app)

    with patch.dict("os.environ", {"MANIFEST_AGENT_LOOP_SECRET": "loop-secret"}):
        response = client.post(
            "/api/internal/website-testing/sync-issues",
            json={"target_url": "https://manifeststartup.com", "dry_run": True},
            headers={"X-Manifest-Agent-Key": "wrong-secret"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid agent loop key"
