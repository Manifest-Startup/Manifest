"""Tests for the website audit and GitHub issue sync service."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from app.services.website_issue_sync_service import (
    WebsiteIssueSyncConfigurationError,
    WebsiteIssueSyncService,
)


class FakeResponse:
    def __init__(self, *, status_code=200, text="", json_data=None, headers=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}
        self.content = text.encode("utf-8")

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.com")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("boom", request=request, response=response)


class FakeAsyncClient:
    def __init__(self, routes):
        self.routes = routes
        self.post_payloads = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None, params=None):
        key = ("GET", url)
        if key not in self.routes:
            raise AssertionError(f"Unexpected GET {url}")
        response = self.routes[key]
        return response(url, headers=headers, params=params) if callable(response) else response

    async def post(self, url, json=None, headers=None):
        self.post_payloads.append((url, json, headers))
        key = ("POST", url)
        if key not in self.routes:
            raise AssertionError(f"Unexpected POST {url}")
        response = self.routes[key]
        return response(url, json=json, headers=headers) if callable(response) else response


@pytest.fixture
def fake_router():
    router = MagicMock()
    router.is_available.return_value = True
    router.chat_json.return_value = {
        "issues": [
            {
                "title": "Improve no-JavaScript landing shell messaging",
                "category": "ux",
                "severity": "high",
                "page_url": "https://manifeststartup.com/",
                "summary": "The public landing shell still exposes a JavaScript dependency message before hydration, which creates onboarding friction and weakens crawler readability.",
                "suggested_fix": "Render meaningful server-delivered onboarding copy and a stronger fallback CTA before the SPA hydrates.",
                "evidence": ["Homepage excerpt contains the phrase 'enable JavaScript'."],
                "labels": ["onboarding"],
            }
        ]
    }
    return router


def _build_html(title: str, *, include_h1: bool = True, include_description: bool = True, body: str = "") -> str:
    description = '<meta name="description" content="Manifest description" />' if include_description else ""
    h1 = "<h1>Manifest</h1>" if include_h1 else ""
    return f"""
    <!doctype html>
    <html>
      <head>
        <title>{title}</title>
        {description}
        <link rel="canonical" href="https://manifeststartup.com/" />
      </head>
      <body>
        {h1}
        <main>{body}</main>
      </body>
    </html>
    """


@pytest.mark.asyncio
async def test_audit_website_creates_github_issues(monkeypatch, fake_router):
    homepage = _build_html(
        "Manifest",
        include_h1=False,
        body="You need to enable JavaScript to run this app. <a href='/signup'>Sign up</a>",
    )
    signup = _build_html("Manifest Signup", include_description=False, body="Create your account.")

    issue_counter = {"value": 0}

    def issue_create_response(url, json=None, headers=None):
        issue_counter["value"] += 1
        return FakeResponse(
            status_code=201,
            json_data={
                "number": issue_counter["value"],
                "html_url": f"https://github.com/Manifest-Startup/Manifest/issues/{issue_counter['value']}",
            },
            headers={"content-type": "application/json"},
        )

    fake_client = FakeAsyncClient(
        {
            ("GET", "https://manifeststartup.com/sitemap.xml"): FakeResponse(
                text="<urlset><url><loc>https://manifeststartup.com/</loc></url><url><loc>https://manifeststartup.com/signup</loc></url></urlset>",
                headers={"content-type": "application/xml"},
            ),
            ("GET", "https://manifeststartup.com"): FakeResponse(text=homepage),
            ("GET", "https://manifeststartup.com/"): FakeResponse(text=homepage),
            ("GET", "https://manifeststartup.com/signup"): FakeResponse(text=signup),
            ("GET", "https://api.github.com/repos/Manifest-Startup/Manifest/issues"): FakeResponse(
                headers={"content-type": "application/json"},
                json_data=[],
            ),
            ("GET", "https://api.github.com/repos/Manifest-Startup/Manifest/labels"): FakeResponse(
                headers={"content-type": "application/json"},
                json_data=[],
            ),
            ("POST", "https://api.github.com/repos/Manifest-Startup/Manifest/labels"): FakeResponse(
                status_code=201,
                headers={"content-type": "application/json"},
                json_data={"ok": True},
            ),
            ("POST", "https://api.github.com/repos/Manifest-Startup/Manifest/issues"): issue_create_response,
        }
    )

    monkeypatch.setattr("app.services.website_issue_sync_service.httpx.AsyncClient", lambda *args, **kwargs: fake_client)
    monkeypatch.setenv("MANIFEST_GITHUB_TOKEN", "ghs_test")

    service = WebsiteIssueSyncService(router=fake_router)
    result = await service.audit_website_and_sync_issues(
        "https://manifeststartup.com",
        max_pages=2,
        max_issues=1,
        create_github_issues=True,
        github_repo="Manifest-Startup/Manifest",
        extra_labels=["triage"],
    )

    assert result["pages_scanned"] == 2
    assert len(result["issue_candidates"]) == 1
    assert result["issue_candidates"][0]["title"] == "Improve no-JavaScript landing shell messaging"
    assert result["github"]["created_count"] == 1
    assert result["github"]["created_issues"][0]["number"] == 1
    issue_payloads = [payload for url, payload, _ in fake_client.post_payloads if url.endswith("/issues")]
    assert issue_payloads[0]["labels"] == ["website-audit", "ux", "priority:high", "onboarding", "triage"]


@pytest.mark.asyncio
async def test_audit_website_dry_run_skips_github_creation(monkeypatch):
    homepage = _build_html("Manifest", include_h1=False, body="You need to enable JavaScript to run this app.")
    fake_client = FakeAsyncClient(
        {
            ("GET", "https://manifeststartup.com/sitemap.xml"): FakeResponse(
                text="<urlset><url><loc>https://manifeststartup.com/</loc></url></urlset>",
                headers={"content-type": "application/xml"},
            ),
            ("GET", "https://manifeststartup.com"): FakeResponse(text=homepage),
            ("GET", "https://manifeststartup.com/"): FakeResponse(text=homepage),
        }
    )

    router = MagicMock()
    router.is_available.return_value = False

    monkeypatch.setattr("app.services.website_issue_sync_service.httpx.AsyncClient", lambda *args, **kwargs: fake_client)
    service = WebsiteIssueSyncService(router=router)

    result = await service.audit_website_and_sync_issues(
        "https://manifeststartup.com",
        max_pages=1,
        max_issues=2,
        create_github_issues=True,
        dry_run=True,
    )

    assert result["issue_candidates"]
    assert result["github"]["dry_run"] is True
    assert result["github"]["created_count"] == 0
    assert result["github"]["skipped_issues"][0]["reason"] == "dry_run"
    assert all(not url.endswith("/issues") for url, _, _ in fake_client.post_payloads)


@pytest.mark.asyncio
async def test_audit_website_requires_github_token_when_creating(monkeypatch):
    homepage = _build_html("Manifest", include_h1=False, body="You need to enable JavaScript to run this app.")
    fake_client = FakeAsyncClient(
        {
            ("GET", "https://manifeststartup.com/sitemap.xml"): FakeResponse(
                text="<urlset><url><loc>https://manifeststartup.com/</loc></url></urlset>",
                headers={"content-type": "application/xml"},
            ),
            ("GET", "https://manifeststartup.com"): FakeResponse(text=homepage),
            ("GET", "https://manifeststartup.com/"): FakeResponse(text=homepage),
        }
    )

    router = MagicMock()
    router.is_available.return_value = False

    monkeypatch.setattr("app.services.website_issue_sync_service.httpx.AsyncClient", lambda *args, **kwargs: fake_client)
    monkeypatch.delenv("MANIFEST_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    service = WebsiteIssueSyncService(router=router)

    with pytest.raises(WebsiteIssueSyncConfigurationError):
        await service.audit_website_and_sync_issues(
            "https://manifeststartup.com",
            max_pages=1,
            max_issues=1,
            create_github_issues=True,
            dry_run=False,
        )
