"""Tests for integration REST routes."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.dependencies import require_user_id
from app.routes.integration_routes import router as integration_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(integration_router)
    return TestClient(app)


class TestGitHubBootstrapRoute:
    def test_requires_auth(self, client):
        response = client.post(
            "/api/integrations/github/bootstrap",
            json={"idea_id": "idea-1", "repo_name": "my-repo"},
        )
        assert response.status_code in (401, 403)

    def test_success_returns_html_url(self, client):
        app = FastAPI()
        app.include_router(integration_router)

        async def _override():
            return "user-1"

        app.dependency_overrides[require_user_id] = _override
        tc = TestClient(app)

        with patch("app.routes.integration_routes.create_database_client") as mock_db_factory:
            mock_db_factory.return_value = object()
            with patch("app.routes.integration_routes.fetch_user_is_guest", return_value=False):
                with patch(
                    "app.routes.integration_routes.create_private_repo_for_idea",
                    return_value=("https://github.com/acme/r", None, None),
                ):
                    response = tc.post(
                        "/api/integrations/github/bootstrap",
                        json={"idea_id": "idea-1", "repo_name": "my-repo"},
                    )
        assert response.status_code == 200
        assert response.json() == {"html_url": "https://github.com/acme/r", "detail": None}

    def test_guest_returns_403(self, client):
        app = FastAPI()
        app.include_router(integration_router)

        async def _override():
            return "guest-1"

        app.dependency_overrides[require_user_id] = _override
        tc = TestClient(app)

        with patch("app.routes.integration_routes.create_database_client"):
            with patch("app.routes.integration_routes.fetch_user_is_guest", return_value=True):
                response = tc.post(
                    "/api/integrations/github/bootstrap",
                    json={"idea_id": "idea-1", "repo_name": "my-repo"},
                )
        assert response.status_code == 403
