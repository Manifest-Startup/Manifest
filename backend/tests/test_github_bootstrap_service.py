"""Unit tests for GitHub bootstrap helpers."""

from unittest.mock import MagicMock, patch

from app.services.integrations.github_bootstrap import _plain_text_from_html, _validate_repo_name, create_private_repo_for_idea


def test_plain_text_from_html_strips_tags():
    assert _plain_text_from_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_validate_repo_name():
    assert _validate_repo_name("my-app_1")
    assert not _validate_repo_name("bad name")
    assert not _validate_repo_name("")


def test_create_private_repo_for_idea_validation():
    db = MagicMock()
    url, detail, code = create_private_repo_for_idea(db, "u", "i", "bad repo!")
    assert url is None
    assert detail
    assert code == "validation"


def test_create_private_repo_missing_token():
    db = MagicMock()
    t = MagicMock()
    ch = MagicMock()
    db.table.return_value = t
    t.select.return_value = ch
    ch.eq.return_value = ch
    ch.limit.return_value = ch
    ch.execute.return_value = MagicMock(data=[])

    url, detail, code = create_private_repo_for_idea(db, "u", "idea-1", "repo-name")
    assert url is None
    assert "Connect GitHub" in (detail or "")
    assert code == "github_auth"


@patch("app.services.integrations.github_bootstrap.httpx.Client")
def test_create_private_repo_success(mock_client_cls):
    db = MagicMock()

    def _table(name):
        t = MagicMock()
        ch = MagicMock()
        t.select.return_value = ch
        ch.eq.return_value = ch
        ch.limit.return_value = ch
        ch.single.return_value = ch
        if name == "integrations":
            ch.execute.return_value = MagicMock(data=[{"access_token": "ghp_secret"}])
        elif name == "ideas":
            ch.execute.return_value = MagicMock(
                data={"idea_id": "idea-1", "title": "T", "description": "<p>Hi</p>"}
            )
        return t

    db.table.side_effect = _table

    mock_http = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_http

    create_resp = MagicMock()
    create_resp.status_code = 201
    create_resp.json.return_value = {"html_url": "https://github.com/me/r", "full_name": "me/r"}

    readme_resp = MagicMock()
    readme_resp.status_code = 201

    mock_http.post.return_value = create_resp
    mock_http.put.return_value = readme_resp

    url, detail, code = create_private_repo_for_idea(db, "user-1", "idea-1", "r")
    assert url == "https://github.com/me/r"
    assert detail is None
    assert code is None
