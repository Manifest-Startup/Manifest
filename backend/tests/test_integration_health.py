"""Connection health in the spec's lifecycle words; Open Media checked live, nothing leaked."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.db.database import InMemoryDatabaseClient
from app.services.integrations import health
from app.services.integrations.open_media.client import OpenMediaNotLinked, OpenMediaUnavailable

USER = "11111111-1111-1111-1111-111111111111"


class Client:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def connected(self, user_id, method, path, **kw):
        self.calls.append((method, path))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def linked(monkeypatch):
    monkeypatch.setattr(health.settings, "enabled", lambda: True)
    monkeypatch.setattr(
        health.identity, "link_status", lambda uid: {"linked": True, "handle": "me"}
    )


def _om(monkeypatch, result):
    client = Client(result)
    monkeypatch.setattr(health, "get_client", lambda: client)
    return client


def test_open_media_verified_by_a_live_read(monkeypatch, linked):
    client = _om(monkeypatch, {"handle": "me"})
    entry = health.open_media(USER)
    assert entry["state"] == "verified" and "@me" in entry["detail"]
    assert client.calls == [("GET", "")]


@pytest.mark.parametrize(
    ("result", "state"),
    [
        (OpenMediaNotLinked(reconnect=True), "authentication_required"),
        (OpenMediaUnavailable("down"), "degraded"),
    ],
)
def test_open_media_failures(monkeypatch, linked, result, state):
    _om(monkeypatch, result)
    assert health.open_media(USER)["state"] == state


def test_open_media_needs_reconnect_without_calling(monkeypatch):
    monkeypatch.setattr(health.settings, "enabled", lambda: True)
    monkeypatch.setattr(
        health.identity, "link_status", lambda uid: {"linked": True, "needs_reconnect": True}
    )
    client = _om(monkeypatch, {"handle": "me"})
    assert health.open_media(USER)["state"] == "authentication_required" and client.calls == []


def test_stored_connections_and_hidden_keys(monkeypatch, linked):
    _om(monkeypatch, {"handle": "me"})
    db = InMemoryDatabaseClient()
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    for row in (
        {"user_id": USER, "service_id": "github", "access_token_ciphertext": "x"},
        {
            "user_id": USER,
            "service_id": "gmail",
            "access_token_ciphertext": "x",
            "expires_at": past,
        },
        {
            "user_id": USER,
            "service_id": "notion",
            "access_token_ciphertext": "x",
            "expires_at": past,
            "refresh_token_ciphertext": "r",
        },
        {"user_id": USER, "service_id": "openai", "access_token_ciphertext": "sk"},
        {"user_id": "someone-else", "service_id": "slack", "access_token_ciphertext": "x"},
    ):
        db.table("integrations").insert(row).execute()
    states = {e["service"]: e["state"] for e in health.check(db, USER)}
    assert states == {
        "open_media": "verified",
        "github": "connected",
        "gmail": "authentication_required",
        "notion": "connected",
    }
    assert all(
        "ciphertext" not in str(e) and "sk" != e.get("detail") for e in health.check(db, USER)
    )
