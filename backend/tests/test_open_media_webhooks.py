"""Open Media webhooks (signature, 5-minute window, dedupe) and the linking routes."""

from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from app.routes import open_media_routes
from app.services.integrations.open_media import webhooks
from app.services.shared import cache
from fastapi import FastAPI
from fastapi.testclient import TestClient

SECRET = "a" * 64


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("OPEN_MEDIA_ENABLED", "true")
    monkeypatch.setenv("OPEN_MEDIA_WEBHOOK_SECRET", SECRET)
    cache._reset_for_tests()
    yield
    cache._reset_for_tests()


def _delivery(event="message.created", *, delivery_id="d-1", data=None, ts=None, secret=SECRET):
    body = json.dumps(
        {
            "id": delivery_id,
            "type": event,
            "created_at": "2026-11-15T00:00:00Z",
            "data": data
            or {"conversation_id": "c1", "message_id": "m1", "actor_id": "om-a", "recipient_ids": ["om-b"], "context": {"app": "manifest"}},
        }
    ).encode()
    timestamp = str(int(ts if ts is not None else time.time()))
    return body, timestamp, webhooks.sign(secret, timestamp, body)


def test_valid_message_webhook_invalidates_unread_for_recipients_and_actor():
    cache.cache_set("open_media:unread:om-b", 4, 300)
    cache.cache_set("open_media:unread:om-a", 1, 300)
    cache.cache_set("open_media:unread:om-z", 9, 300)
    body, ts, sig = _delivery()
    assert webhooks.handle(body, event="message.created", timestamp=ts, signature=sig) == {"ok": True}
    assert cache.cache_get("open_media:unread:om-b") is None
    assert cache.cache_get("open_media:unread:om-a") is None
    assert cache.cache_get("open_media:unread:om-z") == 9


def test_post_webhook_invalidates_clip_stats():
    cache.cache_set("open_media:clips:public", [{"id": "p1"}], 60)
    body, ts, sig = _delivery("post.liked", data={"post_id": "p1", "actor_id": "om-a", "recipient_ids": []})
    webhooks.handle(body, event="post.liked", timestamp=ts, signature=sig)
    assert cache.cache_get("open_media:clips:public") is None


def test_bad_signature_is_rejected():
    body, ts, _ = _delivery()
    with pytest.raises(webhooks.WebhookRejected, match="Bad signature"):
        webhooks.handle(body, event="x", timestamp=ts, signature="sha256=" + "0" * 64)
    _, _, other_sig = _delivery(secret="b" * 64)
    with pytest.raises(webhooks.WebhookRejected):
        webhooks.handle(body, event="x", timestamp=ts, signature=other_sig)


def test_body_tampering_breaks_the_signature():
    body, ts, sig = _delivery()
    with pytest.raises(webhooks.WebhookRejected):
        webhooks.handle(body.replace(b"om-b", b"om-x"), event="x", timestamp=ts, signature=sig)


@pytest.mark.parametrize("age", [301, -301, 3600])
def test_deliveries_outside_five_minutes_are_rejected(age):
    now = 1_800_000_000
    body, ts, sig = _delivery(ts=now - age)
    with pytest.raises(webhooks.WebhookRejected, match="Stale"):
        webhooks.handle(body, event="x", timestamp=ts, signature=sig, now=now)


def test_delivery_inside_the_window_is_accepted():
    now = 1_800_000_000
    body, ts, sig = _delivery(ts=now - 299)
    assert webhooks.handle(body, event="x", timestamp=ts, signature=sig, now=now)["ok"] is True


def test_duplicate_delivery_is_acknowledged_once():
    body, ts, sig = _delivery(delivery_id="dup")
    assert webhooks.handle(body, event="x", timestamp=ts, signature=sig) == {"ok": True}
    assert webhooks.handle(body, event="x", timestamp=ts, signature=sig) == {"ok": True, "duplicate": True}


def test_missing_headers_or_secret_are_rejected(monkeypatch):
    body, ts, sig = _delivery()
    with pytest.raises(webhooks.WebhookRejected, match="Missing"):
        webhooks.handle(body, event="x", timestamp=None, signature=sig)
    monkeypatch.setenv("OPEN_MEDIA_WEBHOOK_SECRET", "")
    with pytest.raises(webhooks.WebhookRejected) as exc:
        webhooks.handle(body, event="x", timestamp=ts, signature=sig)
    assert exc.value.status == 503


# -- routes ---------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(open_media_routes.router)
    state = {"user": "u1", "guest": False}
    monkeypatch.setattr(open_media_routes, "get_current_user_id_optional", lambda request: state["user"])
    monkeypatch.setattr(open_media_routes, "fetch_user_is_guest", lambda db, uid: state["guest"])
    monkeypatch.setattr(open_media_routes, "create_database_client", lambda: None)
    test_client = TestClient(app, follow_redirects=False)
    test_client.state = state
    return test_client


def test_webhook_endpoint_verifies_and_dedupes(client):
    body, ts, sig = _delivery(delivery_id="route-1")
    headers = {
        "Content-Type": "application/json",
        "X-Open-Media-Event": "message.created",
        "X-Open-Media-Delivery": "route-1",
        "X-Open-Media-Timestamp": ts,
        "X-Open-Media-Signature": sig,
    }
    assert client.post("/api/webhooks/open-media", content=body, headers=headers).json() == {"ok": True}
    again = client.post("/api/webhooks/open-media", content=body, headers=headers)
    assert again.status_code == 200 and again.json()["duplicate"] is True
    bad = client.post("/api/webhooks/open-media", content=body, headers={**headers, "X-Open-Media-Signature": "sha256=00"})
    assert bad.status_code == 401


def test_connect_redirects_full_accounts_to_open_media_authorize(client, monkeypatch):
    monkeypatch.setenv("OPEN_MEDIA_API_BASE", "https://om.test")
    response = client.get("/api/integrations/open-media/connect")
    assert response.status_code == 303
    location = urlsplit(response.headers["location"])
    assert (location.netloc, location.path) == ("om.test", "/authorize")
    assert parse_qs(location.query)["code_challenge_method"] == ["S256"]


def test_connect_requires_login_and_a_full_account(client):
    client.state["user"] = None
    assert client.get("/api/integrations/open-media/connect").headers["location"] == "/login"
    client.state.update(user="u1", guest=True)
    location = client.get("/api/integrations/open-media/connect").headers["location"]
    assert location == "/account?open_media=full_account_required#open-media"


def test_connect_is_hidden_when_open_media_is_off(client, monkeypatch):
    monkeypatch.setenv("OPEN_MEDIA_ENABLED", "0")
    location = client.get("/api/integrations/open-media/connect").headers["location"]
    assert location == "/account?open_media=disabled#open-media"


def test_callback_links_then_resumes_waiting_reels(client, monkeypatch):
    linked = []
    resumed = []
    monkeypatch.setattr(
        open_media_routes.identity, "complete_link", lambda uid, code, state: linked.append((uid, code, state))
    )
    import app.services.pitch_reels.video_worker as worker

    monkeypatch.setattr(worker, "resume_reels_waiting_for_open_media", lambda uid: resumed.append(uid))
    response = client.get("/api/integrations/open-media/callback?code=c&state=s")
    assert response.headers["location"] == "/account?open_media=linked#open-media"
    assert linked == [("u1", "c", "s")] and resumed == ["u1"]


def test_callback_reports_denied_and_bad_state(client, monkeypatch):
    denied = client.get("/api/integrations/open-media/callback?error=access_denied")
    assert denied.headers["location"] == "/account?open_media=cancelled#open-media"

    def fail(uid, code, state):
        raise open_media_routes.identity.OpenMediaLinkError("bad")

    monkeypatch.setattr(open_media_routes.identity, "complete_link", fail)
    bad = client.get("/api/integrations/open-media/callback?code=c&state=s")
    assert bad.headers["location"] == "/account?open_media=error#open-media"
