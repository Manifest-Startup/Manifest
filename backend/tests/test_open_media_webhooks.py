"""Open Media webhooks (signature, 5-minute window, dedupe)."""

from __future__ import annotations

import json
import time

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
            or {
                "conversation_id": "c1",
                "message_id": "m1",
                "actor_id": "om-a",
                "recipient_ids": ["om-b"],
                "context": {"app": "manifest"},
            },
        }
    ).encode()
    timestamp = str(int(ts if ts is not None else time.time()))
    return body, timestamp, webhooks.sign(secret, timestamp, body)


def test_valid_message_webhook_invalidates_unread_for_recipients_and_actor():
    cache.cache_set("open_media:unread:om-b", 4, 300)
    cache.cache_set("open_media:unread:om-a", 1, 300)
    cache.cache_set("open_media:unread:om-z", 9, 300)
    body, ts, sig = _delivery()
    assert webhooks.handle(body, event="message.created", timestamp=ts, signature=sig) == {
        "ok": True
    }
    assert cache.cache_get("open_media:unread:om-b") is None
    assert cache.cache_get("open_media:unread:om-a") is None
    assert cache.cache_get("open_media:unread:om-z") == 9


def test_post_webhook_invalidates_clip_stats():
    cache.cache_set("open_media:clips:public", [{"id": "p1"}], 60)
    body, ts, sig = _delivery(
        "post.liked", data={"post_id": "p1", "actor_id": "om-a", "recipient_ids": []}
    )
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
    assert webhooks.handle(body, event="x", timestamp=ts, signature=sig) == {
        "ok": True,
        "duplicate": True,
    }


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
def client():
    app = FastAPI()
    app.include_router(open_media_routes.router)
    return TestClient(app, follow_redirects=False)


def test_webhook_endpoint_verifies_and_dedupes(client):
    body, ts, sig = _delivery(delivery_id="route-1")
    headers = {
        "Content-Type": "application/json",
        "X-Open-Media-Event": "message.created",
        "X-Open-Media-Delivery": "route-1",
        "X-Open-Media-Timestamp": ts,
        "X-Open-Media-Signature": sig,
    }
    assert client.post("/api/webhooks/open-media", content=body, headers=headers).json() == {
        "ok": True
    }
    again = client.post("/api/webhooks/open-media", content=body, headers=headers)
    assert again.status_code == 200 and again.json()["duplicate"] is True
    bad = client.post(
        "/api/webhooks/open-media",
        content=body,
        headers={**headers, "X-Open-Media-Signature": "sha256=00"},
    )
    assert bad.status_code == 401


def test_signature_keys_on_the_utf8_secret_string_not_hex_decoded():
    import hashlib
    import hmac as std_hmac

    body, ts = b'{"id":"x"}', "1800000000"
    expected = std_hmac.new(
        SECRET.encode("utf-8"), f"{ts}.".encode() + body, hashlib.sha256
    ).hexdigest()
    assert webhooks.sign(SECRET, ts, body) == f"sha256={expected}"


def test_context_links_stay_on_manifeststartup_com(monkeypatch):
    from app.services.integrations.open_media import settings

    monkeypatch.setenv(
        "OPEN_MEDIA_REDIRECT_URI", "http://localhost:8000/api/auth/open-media/callback"
    )
    assert settings.clip_url("r1") == "https://manifeststartup.com/pitch-reels?clip=r1"
    monkeypatch.setenv(
        "OPEN_MEDIA_REDIRECT_URI",
        "https://staging.manifeststartup.com/api/auth/open-media/callback",
    )
    assert settings.app_origin() == "https://staging.manifeststartup.com"
