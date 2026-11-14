"""Route tests for production signal ingest."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import fastapi_app
import app.routes.production_signal_routes as production_signal_routes


def test_production_signal_route_accepts_event():
    client = TestClient(fastapi_app)

    with patch.object(
        production_signal_routes.production_signal_service,
        "ingest",
        return_value={
            "accepted": True,
            "fingerprint": "x",
            "window_start": "2026-04-04T12:00:00+00:00",
            "event_count": 1,
            "github_issue_created": False,
            "github_eligible": False,
        },
    ), patch.dict("os.environ", {"MANIFEST_AGENT_LOOP_SECRET": "loop-secret"}):
        response = client.post(
            "/api/internal/production-signals/event",
            json={
                "event_name": "graphql_mutation_failed",
                "route": "/graphql",
                "severity": "error",
                "create_github_issue": False,
            },
            headers={"X-Manifest-Agent-Key": "loop-secret"},
        )

    assert response.status_code == 200
    assert response.json()["event_count"] == 1


def test_production_signal_route_async_path():
    client = TestClient(fastapi_app)

    with patch.object(
        production_signal_routes.production_signal_service,
        "ingest_and_maybe_open_github",
        new=AsyncMock(
            return_value={
                "github_issue_created": True,
                "github_issue_number": 12,
                "fingerprint": "fp",
                "window_start": "2026-04-04T12:00:00+00:00",
                "event_count": 5,
            }
        ),
    ), patch.dict("os.environ", {"MANIFEST_AGENT_LOOP_SECRET": "loop-secret"}):
        response = client.post(
            "/api/internal/production-signals/event",
            json={
                "event_name": "client_error_boundary",
                "severity": "error",
                "create_github_issue": True,
            },
            headers={"X-Manifest-Agent-Key": "loop-secret"},
        )

    assert response.status_code == 200
    assert response.json()["github_issue_number"] == 12
