"""Unit tests for creating a GitHub repository from an idea."""

import json
from unittest.mock import MagicMock

import httpx
from app.services.integrations import github_bootstrap
from app.services.integrations.github_api import GitHubClient
from app.services.integrations.github_bootstrap import (
    _plain_text_from_html,
    _validate_repo_name,
    create_private_repo_for_idea,
    idea_readme,
)


def _idea_db(idea):
    db = MagicMock()
    chain = MagicMock()
    db.table.return_value.select.return_value = chain
    chain.eq.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = MagicMock(data=idea)
    return db


def test_plain_text_from_html_strips_tags():
    assert _plain_text_from_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_validate_repo_name():
    assert _validate_repo_name("my-app_1")
    assert not _validate_repo_name("bad name")
    assert not _validate_repo_name("")


def test_create_private_repo_for_idea_validation():
    url, detail, code = create_private_repo_for_idea(MagicMock(), "u", "i", "bad repo!")
    assert url is None
    assert detail
    assert code == "validation"


def test_create_private_repo_missing_token(monkeypatch):
    monkeypatch.setattr(github_bootstrap, "load_github_token", lambda uid: None)
    url, detail, code = create_private_repo_for_idea(MagicMock(), "u", "idea-1", "repo-name")
    assert url is None
    assert "Connect GitHub" in (detail or "")
    assert code == "github_auth"


def test_idea_readme_needs_an_owned_idea():
    assert idea_readme(_idea_db(None), "u", "idea-1") is None
    readme = idea_readme(_idea_db({"title": "T", "description": "<p>Hi</p>"}), "u", "idea-1")
    assert readme == "# T\n\nHi\n"


def test_create_private_repo_success(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        if request.url.path == "/user/repos":
            return httpx.Response(
                201,
                json={
                    "html_url": "https://github.com/me/r",
                    "full_name": "me/r",
                    "name": "r",
                    "private": True,
                },
            )
        return httpx.Response(201, json={"content": {}, "commit": {"sha": "abc"}})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(github_bootstrap, "load_github_token", lambda uid: "ghp_" + "x" * 36)
    monkeypatch.setattr(
        github_bootstrap, "client_for", lambda uid: GitHubClient("t", transport=transport)
    )

    db = _idea_db({"idea_id": "idea-1", "title": "T", "description": "<p>Hi</p>"})
    url, detail, code = create_private_repo_for_idea(db, "user-1", "idea-1", "r")
    assert (url, detail, code) == ("https://github.com/me/r", None, None)
    assert calls[0][:2] == ("POST", "/user/repos")
    assert calls[0][2]["private"] is True and calls[0][2]["auto_init"] is False
    assert calls[1][:2] == ("PUT", "/repos/me/r/contents/README.md")
