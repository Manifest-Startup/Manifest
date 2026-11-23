"""CSRF: cookie-signed-in GraphQL writes are accepted only from Manifest's own origins."""

from __future__ import annotations

import pytest
from app.middleware.origin_check import OriginCheckMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client() -> TestClient:
    app = FastAPI()

    @app.post("/graphql")
    async def graphql():
        return {"data": {"ok": True}}

    @app.post("/sso/saml/acs")
    async def acs():
        return {"ok": True}

    app.add_middleware(OriginCheckMiddleware, allowed_origins=["https://manifeststartup.com"])
    return TestClient(app, base_url="https://manifest-backend.test")


COOKIE = {"cookie": "session_token=abc; manifest_csrf_token=x"}


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({**COOKIE, "origin": "https://evil.example"}, 403),
        ({**COOKIE, "origin": "null"}, 403),
        ({**COOKIE, "referer": "https://evil.example/page"}, 403),
        ({**COOKIE, "origin": "https://manifeststartup.com"}, 200),
        ({**COOKIE, "referer": "https://manifeststartup.com/ideas/1"}, 200),
        # Behind the edge Worker: the public host arrives as x-forwarded-host.
        (
            {
                **COOKIE,
                "origin": "https://staging.manifest.test",
                "x-forwarded-host": "staging.manifest.test",
            },
            200,
        ),
        ({**COOKIE}, 200),  # no browser origin: not a CSRF vector
        ({"origin": "https://evil.example"}, 200),  # no session cookie to ride on
        ({**COOKIE, "origin": "https://evil.example", "authorization": "Bearer t"}, 200),
    ],
)
def test_graphql_writes(headers, status):
    response = _client().post("/graphql", json={"query": "{ ok }"}, headers=headers)
    assert response.status_code == status
    if status == 403:
        assert "didn't come from Manifest" in response.json()["errors"][0]["message"]


def test_other_paths_and_reads_are_untouched():
    client = _client()
    evil = {**COOKIE, "origin": "https://idp.example"}
    assert client.post("/sso/saml/acs", headers=evil).status_code == 200
    assert client.get("/graphql", headers=evil).status_code in (200, 405)
