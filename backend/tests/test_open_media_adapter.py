"""Open Media adapter: client retries/refresh, linking, messaging and clips (httpx.MockTransport)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from app.services.integrations.open_media import clips, identity, messaging, store
from app.services.integrations.open_media import client as om_client
from app.services.integrations.open_media.client import (
    OpenMediaClient,
    OpenMediaDisabled,
    OpenMediaNotLinked,
    OpenMediaUnavailable,
)
from app.services.integrations.open_media.store import OpenMediaLink
from app.services.shared import cache


class FakeStore:
    """In-memory replacement for the encrypted ``integrations`` row."""

    def __init__(self):
        self.links: dict[str, OpenMediaLink] = {}

    def add(self, user_id="u1", *, access="at-1", expires_in=3600, refresh="rt-1", om_id="om-1"):
        self.links[user_id] = OpenMediaLink(
            user_id=user_id,
            om_user_id=om_id,
            handle=f"handle-{user_id}",
            access_token=access,
            refresh_token=refresh,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            metadata={"om_user_id": om_id, "handle": f"handle-{user_id}"},
        )

    def load_link(self, user_id):
        return self.links.get(user_id)

    def link_metadata(self, user_id):
        link = self.links.get(user_id)
        return dict(link.metadata) if link else None

    def update_tokens(self, user_id, *, access_token, refresh_token, expires_in):
        link = self.links[user_id]
        link.access_token = access_token
        link.refresh_token = refresh_token or link.refresh_token
        link.expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in or 3600))

    def mark_needs_reconnect(self, user_id):
        link = self.links[user_id]
        link.refresh_token = None
        link.metadata["needs_reconnect"] = True

    def save_link(self, user_id, **kw):
        self.links[user_id] = OpenMediaLink(
            user_id=user_id,
            om_user_id=kw["om_user_id"],
            handle=kw["handle"],
            access_token=kw["access_token"],
            refresh_token=kw["refresh_token"],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            metadata={"om_user_id": kw["om_user_id"], "handle": kw["handle"]},
        )
        return self.links[user_id].metadata


class Router:
    """Records requests and answers from a queue of (method, path) -> responses."""

    def __init__(self):
        self.routes: dict[tuple[str, str], list] = {}
        self.calls: list[httpx.Request] = []

    def on(self, method, path, *responses):
        self.routes.setdefault((method, path), []).extend(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        queue = self.routes.get((request.method, request.url.path))
        if not queue:
            return httpx.Response(404, json={"error": "not_found"})
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        status, body = item
        return httpx.Response(status, json=body)


@pytest.fixture
def om(monkeypatch):
    monkeypatch.setenv("OPEN_MEDIA_ENABLED", "true")
    monkeypatch.setenv("OPEN_MEDIA_API_BASE", "https://om.test")
    fake = FakeStore()
    for name in (
        "load_link",
        "link_metadata",
        "update_tokens",
        "mark_needs_reconnect",
        "save_link",
    ):
        monkeypatch.setattr(store, name, getattr(fake, name))
    router = Router()
    sleeps: list[float] = []
    om_client.set_client(
        OpenMediaClient(transport=httpx.MockTransport(router), sleep=sleeps.append)
    )
    cache._reset_for_tests()
    yield {"store": fake, "router": router, "sleeps": sleeps}
    om_client.set_client(None)
    cache._reset_for_tests()


def _auth(request):
    return request.headers.get("authorization")


# -- client ---------------------------------------------------------------


def test_connected_calls_use_the_stored_access_token(om):
    om["store"].add()
    om["router"].on("GET", "/v1/connected/me/conversations", (200, {"conversations": []}))
    assert messaging.list_conversations("u1") == []
    request = om["router"].calls[0]
    assert _auth(request) == "Bearer at-1"
    assert request.url.params["app"] == "manifest"


def test_expired_access_token_is_refreshed_and_rotation_is_saved(om):
    om["store"].add(expires_in=10)  # inside the 60 s refresh margin
    om["router"].on(
        "POST",
        "/oauth/token",
        (200, {"access_token": "at-2", "refresh_token": "rt-2", "expires_in": 3600}),
    )
    om["router"].on("GET", "/v1/connected/me/conversations", (200, {"conversations": []}))
    messaging.list_conversations("u1")

    token_request = om["router"].calls[0]
    form = parse_qs(token_request.content.decode())
    assert form["grant_type"] == ["refresh_token"]
    assert form["refresh_token"] == ["rt-1"]
    assert form["client_id"] == ["https://manifeststartup.com/oauth/open-media-client.json"]
    assert _auth(om["router"].calls[1]) == "Bearer at-2"
    assert om["store"].links["u1"].refresh_token == "rt-2"


def test_a_401_refreshes_once_and_retries(om):
    om["store"].add()
    om["router"].on(
        "GET",
        "/v1/connected/me/conversations",
        (401, {"error": "invalid_token"}),
        (200, {"conversations": []}),
    )
    om["router"].on("POST", "/oauth/token", (200, {"access_token": "at-2", "expires_in": 3600}))
    messaging.list_conversations("u1")
    assert [c.url.path for c in om["router"].calls] == [
        "/v1/connected/me/conversations",
        "/oauth/token",
        "/v1/connected/me/conversations",
    ]
    assert _auth(om["router"].calls[2]) == "Bearer at-2"


def test_rejected_refresh_marks_link_for_reconnect(om):
    om["store"].add(expires_in=0)
    om["router"].on("POST", "/oauth/token", (400, {"error": "invalid_grant"}))
    with pytest.raises(OpenMediaNotLinked) as exc:
        messaging.list_conversations("u1")
    assert exc.value.reconnect is True
    assert "Reconnect" in str(exc.value)
    assert om["store"].links["u1"].metadata["needs_reconnect"] is True
    with pytest.raises(OpenMediaNotLinked):
        messaging.list_conversations("u1")
    assert len(om["router"].calls) == 1  # no second refresh attempt


def test_unlinked_user_gets_a_clear_error(om):
    with pytest.raises(OpenMediaNotLinked, match="Connect your Open Media account"):
        messaging.list_conversations("nobody")
    assert om["router"].calls == []


def test_disabled_open_media_never_calls_out(om, monkeypatch):
    monkeypatch.setenv("OPEN_MEDIA_ENABLED", "false")
    om["store"].add()
    with pytest.raises(OpenMediaDisabled):
        messaging.list_conversations("u1")
    assert om["router"].calls == []


def test_gets_retry_on_503_with_backoff(om):
    om["store"].add()
    om["router"].on(
        "GET",
        "/v1/connected/me/conversations",
        (503, {"error": "busy"}),
        (502, {"error": "busy"}),
        (200, {"conversations": []}),
    )
    messaging.list_conversations("u1")
    assert len(om["router"].calls) == 3
    assert om["sleeps"] == [0.3, 0.6]


def test_gives_up_after_three_attempts_with_a_friendly_error(om):
    om["store"].add()
    om["router"].on("GET", "/v1/connected/me/conversations", (503, {"error": "busy"}))
    with pytest.raises(OpenMediaUnavailable, match="unavailable"):
        messaging.list_conversations("u1")
    assert len(om["router"].calls) == 3


def test_non_idempotent_upload_is_not_retried_after_a_read_timeout(om):
    om["store"].add()
    om["router"].on("POST", "/v1/connected/me/media/videos", httpx.ReadTimeout("slow"))
    with pytest.raises(OpenMediaUnavailable):
        clips.upload_video("u1", b"video-bytes")
    assert len(om["router"].calls) == 1


def test_connect_errors_are_retried_even_for_posts(om):
    om["store"].add()
    om["router"].on(
        "POST",
        "/v1/connected/me/media/videos",
        httpx.ConnectError("refused"),
        (201, {"video": {"path": "u/1.mp4"}}),
    )
    assert clips.upload_video("u1", b"video-bytes", duration_ms=8000) == {"path": "u/1.mp4"}
    upload = om["router"].calls[-1]
    assert upload.headers["content-type"] == "video/mp4"
    assert upload.headers["content-length"] == str(len(b"video-bytes"))
    assert dict(upload.url.params) == {"duration_ms": "8000"}
    assert upload.content == b"video-bytes"


def test_4xx_errors_surface_open_media_description(om):
    om["store"].add()
    om["router"].on(
        "POST",
        "/v1/connected/me/conversations",
        (404, {"error": "not_found", "error_description": "No one has that handle."}),
    )
    with pytest.raises(om_client.OpenMediaError, match="No one has that handle"):
        messaging.start_conversation("u1", handle="ghost")


# -- identity (the stored link; signing in is covered in test_open_media_sign_in.py) --


def test_link_status_reports_the_link_even_when_features_are_off(om, monkeypatch):
    assert identity.link_status("u1") == {"enabled": True, "linked": False}
    om["store"].add()
    status = identity.link_status("u1")
    assert status["linked"] is True and status["handle"] == "handle-u1"
    assert "access_token" not in json.dumps(status)
    monkeypatch.setenv("OPEN_MEDIA_ENABLED", "")
    status = identity.link_status("u1")
    assert status["enabled"] is False and status["handle"] == "handle-u1"


def test_handle_for_user_hides_links_that_need_reconnect(om):
    om["store"].add("founder")
    assert identity.handle_for_user("founder") == "handle-founder"
    om["store"].links["founder"].metadata["needs_reconnect"] = True
    assert identity.handle_for_user("founder") is None
    assert identity.handle_for_user("") is None


# -- messaging ------------------------------------------------------------


def test_conversations_are_normalised_with_the_other_member(om):
    om["store"].add(om_id="om-me")
    om["router"].on(
        "GET",
        "/v1/connected/me/conversations",
        (
            200,
            {
                "conversations": [
                    {
                        "id": "c1",
                        "kind": "direct",
                        "context": {"app": "manifest", "idea_id": "i1", "title": "Tidy"},
                        "members": [
                            {"id": "om-me", "handle": "me"},
                            {
                                "id": "om-ada",
                                "handle": "ada",
                                "displayName": "Ada L",
                                "avatarUrl": "a.png",
                            },
                        ],
                        "lastMessage": {
                            "id": "m1",
                            "body": "hi",
                            "senderId": "om-ada",
                            "createdAt": "2026-11-01T00:00:00Z",
                        },
                        "unread_count": 2,
                    }
                ]
            },
        ),
    )
    [conv] = messaging.list_conversations("u1")
    assert conv["other"] == {
        "id": "om-ada",
        "handle": "ada",
        "display_name": "Ada L",
        "avatar_url": "a.png",
    }
    assert conv["context"]["idea_id"] == "i1"
    assert conv["last_message"]["body"] == "hi"
    assert conv["unread_count"] == 2


def test_send_message_carries_an_idempotency_key_and_is_retried_safely(om):
    om["store"].add()
    om["router"].on(
        "POST",
        "/v1/connected/me/conversations/c1/messages",
        (503, {"error": "busy"}),
        (201, {"message": {"id": "m9", "body": "hello", "sender_id": "om-1"}}),
    )
    msg = messaging.send_message("u1", "c1", body="  hello  ", client_id="k-1")
    assert msg["id"] == "m9"
    first, second = om["router"].calls
    assert first.headers["idempotency-key"] == second.headers["idempotency-key"] == "k-1"
    assert json.loads(second.content) == {"body": "hello", "client_id": "k-1"}


def test_empty_message_is_rejected_locally(om):
    om["store"].add()
    with pytest.raises(ValueError):
        messaging.send_message("u1", "c1", body="   ")
    assert om["router"].calls == []


def test_unread_count_is_cached_until_invalidated(om):
    om["store"].add(om_id="om-1")
    om["router"].on(
        "GET",
        "/v1/connected/me/conversations",
        (200, {"conversations": [{"id": "a", "unread_count": 2}, {"id": "b", "unread_count": 1}]}),
    )
    assert messaging.unread_count("u1") == 3
    assert messaging.unread_count("u1") == 3
    assert len(om["router"].calls) == 1
    messaging.invalidate_unread(["om-1"])
    messaging.unread_count("u1")
    assert len(om["router"].calls) == 2


def test_unread_count_is_zero_without_a_link(om):
    assert messaging.unread_count("u1") == 0


def test_mark_read_drops_the_cached_unread_count(om):
    om["store"].add(om_id="om-1")
    cache.cache_set("open_media:unread:om-1", 5, 300)
    om["router"].on("POST", "/v1/connected/me/conversations/c1/read", (200, {}))
    assert messaging.mark_read("u1", "c1") is True
    assert cache.cache_get("open_media:unread:om-1") is None


def test_start_conversation_sends_idea_context(om):
    om["store"].add()
    om["router"].on(
        "POST",
        "/v1/connected/me/conversations",
        (201, {"conversation": {"id": "c1", "members": []}}),
    )
    context = messaging.idea_context("idea-1", "Tidy")
    messaging.start_conversation("u1", handle="ada", context=context)
    sent = json.loads(om["router"].calls[0].content)
    assert sent == {
        "handle": "ada",
        "context": {
            "app": "manifest",
            "idea_id": "idea-1",
            "url": "https://manifeststartup.com/ideas/idea-1",
            "title": "Tidy",
        },
    }


def test_realtime_token_shape(om):
    om["store"].add(om_id="om-1")
    om["router"].on(
        "POST",
        "/v1/connected/me/realtime-token",
        (
            200,
            {
                "supabase_url": "https://x.supabase.co",
                "anon_key": "anon",
                "access_token": "jwt",
                "expires_at": "soon",
            },
        ),
    )
    token = messaging.realtime_token("u1")
    assert token == {
        "supabase_url": "https://x.supabase.co",
        "anon_key": "anon",
        "access_token": "jwt",
        "expires_at": "soon",
        "om_user_id": "om-1",
    }


# -- clips ----------------------------------------------------------------

POST = {
    "id": "p1",
    "body": "Tidy",
    "created_at": "2026-11-01T00:00:00Z",
    "author": {"id": "om-f", "handle": "founder", "display_name": "F", "avatar_url": None},
    "video": {"url": "https://cdn/p1.mp4", "poster_url": None},
    "context": {"app": "manifest", "idea_id": "i1"},
    "counts": {"likes": 4, "comments": 2, "reshares": 1},
}


def test_public_feed_is_used_for_unlinked_viewers_and_cached(om):
    om["router"].on(
        "GET",
        "/v1/feed",
        (
            200,
            {
                "data": [{**POST, "createdAt": "ignored-extra"}],
                "app": "manifest",
                "kind": "clips",
                "nextCursor": None,
            },
        ),
    )
    [post] = clips.feed("viewer")
    assert post["video_url"] == "https://cdn/p1.mp4"
    assert (post["like_count"], post["comment_count"], post["reshare_count"]) == (4, 2, 1)
    assert post["viewer_liked"] is False
    request = om["router"].calls[0]
    assert dict(request.url.params) == {"kind": "clips", "app": "manifest", "limit": "50"}
    assert _auth(request) is None
    clips.feed(None)
    assert len(om["router"].calls) == 1
    clips.invalidate_clip_stats(["p1"])
    clips.feed(None)
    assert len(om["router"].calls) == 2


def test_linked_viewer_feed_includes_viewer_liked(om):
    om["store"].add("viewer")
    om["router"].on(
        "GET", "/v1/connected/me/feed", (200, {"posts": [{**POST, "viewer": {"liked": True}}]})
    )
    [post] = clips.feed("viewer")
    assert post["viewer_liked"] is True
    assert _auth(om["router"].calls[0]) == "Bearer at-1"


def test_like_uses_post_and_falls_back_to_put_on_405(om):
    om["store"].add()
    om["router"].on(
        "POST", "/v1/connected/me/posts/p1/like", (405, {"error": "method_not_allowed"})
    )
    om["router"].on("PUT", "/v1/connected/me/posts/p1/like", (200, {"likes": 5, "liked": True}))
    assert clips.set_like("u1", "p1", True)["like_count"] == 5
    om["router"].on("DELETE", "/v1/connected/me/posts/p1/like", (200, {"likes": 4}))
    assert clips.set_like("u1", "p1", False)["like_count"] == 4


def test_create_post_sends_video_context_and_idempotency_key(om):
    om["store"].add()
    om["router"].on("POST", "/v1/connected/me/posts", (201, {"post": {"id": "p7"}}))
    post = clips.create_post(
        "u1",
        body="Tidy",
        video={"path": "v"},
        context={"app": "manifest", "idea_id": "i1"},
        client_id="k",
    )
    assert post["id"] == "p7"
    sent = om["router"].calls[0]
    assert json.loads(sent.content) == {
        "body": "Tidy",
        "context": {"app": "manifest", "idea_id": "i1"},
        "client_id": "k",
        "video": {"path": "v"},
    }
    assert sent.headers["idempotency-key"] == "k"


def test_delete_post_treats_404_as_done(om):
    om["store"].add()
    om["router"].on("DELETE", "/v1/connected/me/posts/gone", (404, {"error": "not_found"}))
    clips.delete_post("u1", "gone")


def test_comments_are_public_and_tolerate_camel_case(om):
    om["router"].on(
        "GET",
        "/v1/posts/p1/comments",
        (
            200,
            {
                "postId": "p1",
                "comments": [
                    {
                        "id": "c1",
                        "body": "nice",
                        "createdAt": "t",
                        "author": {"id": "om-a", "handle": "a"},
                    }
                ],
            },
        ),
    )
    [comment] = clips.comments("p1")
    assert comment == {
        "id": "c1",
        "post_id": "p1",
        "body": "nice",
        "created_at": "t",
        "author": {"id": "om-a", "handle": "a", "display_name": "a", "avatar_url": None},
    }


def test_oversized_video_is_rejected_before_upload(om):
    om["store"].add()
    with pytest.raises(ValueError, match="100 MB"):
        clips.upload_video("u1", b"x" * (clips.MAX_VIDEO_BYTES + 1))
    assert om["router"].calls == []


def test_public_errors_use_the_nested_error_shape(om):
    om["router"].on(
        "GET",
        "/v1/posts/p1/comments",
        (404, {"error": {"code": "not_found", "message": "No such post."}}),
    )
    with pytest.raises(om_client.OpenMediaError, match="No such post") as exc:
        clips.comments("p1")
    assert exc.value.code == "not_found" and exc.value.status == 404


def test_create_post_reads_a_top_level_post(om):
    om["store"].add()
    om["router"].on("POST", "/v1/connected/me/posts", (201, {"id": "p8", "body": "Tidy"}))
    post = clips.create_post(
        "u1", body="Tidy", video=None, context={"app": "manifest"}, client_id="k"
    )
    assert post["id"] == "p8"


def test_send_message_reads_the_final_response_container(om):
    om["store"].add()
    om["router"].on(
        "POST",
        "/v1/connected/me/conversations/c1/messages",
        (
            201,
            {
                "sent": True,
                "conversationId": "c1",
                "message": {"id": "m1", "body": "hi", "sender_id": "om-1"},
            },
        ),
    )
    assert messaging.send_message("u1", "c1", body="hi")["id"] == "m1"


def test_start_conversation_reads_the_final_response_container(om):
    om["store"].add(om_id="om-me")
    om["router"].on(
        "POST",
        "/v1/connected/me/conversations",
        (
            201,
            {
                "id": "c1",
                "with": "ada",
                "conversation": {"id": "c1", "members": [{"id": "om-ada", "handle": "ada"}]},
            },
        ),
    )
    conv = messaging.start_conversation("u1", handle="ada")
    assert conv["id"] == "c1" and conv["other"]["handle"] == "ada"


# -- email (read-only) -----------------------------------------------------


def test_email_is_read_live_and_grouped_into_threads(om):
    from app.services.integrations.open_media import email as om_email

    om["store"].add()
    om["router"].on(
        "GET",
        "/v1/connected/me/email",
        (
            200,
            {
                "data": [
                    {
                        "mailboxId": "mb1",
                        "account": "me@x.com",
                        "folder": "INBOX",
                        "from": '"Ada L" <ada@x.com>',
                        "to": ["me@x.com"],
                        "subject": "Re: Seed round",
                        "text": "Sounds  good\n see you",
                        "sentAt": "2026-11-03T00:00:00Z",
                        "messageId": "<m2@x>",
                        "inReplyTo": "<m1@x>",
                    },
                    {
                        "mailboxId": "mb1",
                        "account": "me@x.com",
                        "folder": "INBOX",
                        "from": "bob@y.com",
                        "to": ["me@x.com"],
                        "subject": "Lunch?",
                        "text": "tomorrow",
                        "sentAt": "2026-11-02T00:00:00Z",
                        "messageId": "<m3@y>",
                    },
                    {
                        "mailboxId": "mb1",
                        "account": "me@x.com",
                        "folder": "Sent",
                        "from": "me@x.com",
                        "to": ["ada@x.com"],
                        "subject": "Seed round (different subject)",
                        "text": "Want to talk?",
                        "sentAt": "2026-11-01T00:00:00Z",
                        "messageId": "<m1@x>",
                    },
                ],
                "note": "Imported email is not end-to-end encrypted.",
            },
        ),
    )
    threads = om_email.list_threads("u1", limit=9999)
    request = om["router"].calls[0]
    assert _auth(request) == "Bearer at-1"
    assert request.url.params["limit"] == "500"
    assert [t["subject"] for t in threads] == ["Seed round (different subject)", "Lunch?"]
    seed = threads[0]
    assert [m["message_id"] for m in seed["messages"]] == ["<m1@x>", "<m2@x>"]
    assert seed["participants"] == ["Ada L", "me@x.com"]
    assert seed["preview"] == "Sounds good see you"
    assert seed["id"] != threads[1]["id"]


def test_email_threads_by_subject_without_reply_headers():
    from app.services.integrations.open_media import email as om_email

    def mail(i, subject, mailbox="mb1"):
        return om_email._email(
            {"mailboxId": mailbox, "from": "a@x", "subject": subject, "messageId": f"<{i}>",
             "sentAt": f"2026-11-0{i}T00:00:00Z"}
        )

    threads = om_email.group_threads(
        [mail(1, "Hello"), mail(2, "RE: Fwd: hello"), mail(3, "Hello", "mb2"), mail(4, ""), mail(5, "")]
    )
    sizes = sorted(len(t["messages"]) for t in threads)
    assert sizes == [1, 1, 1, 2]
    assert all(t["subject"] for t in threads)


def test_email_reply_loop_does_not_recurse():
    from app.services.integrations.open_media import email as om_email

    a = om_email._email({"messageId": "<a>", "inReplyTo": "<b>", "subject": "x"})
    b = om_email._email({"messageId": "<b>", "inReplyTo": "<a>", "subject": "y"})
    assert len(om_email.group_threads([a, b])) == 1


def test_sender_name_and_web_origin(monkeypatch):
    from app.services.integrations.open_media import email as om_email
    from app.services.integrations.open_media import settings

    assert om_email.sender_name('"Ada L" <ada@x.com>') == "Ada L"
    assert om_email.sender_name("<ada@x.com>") == "ada@x.com"
    assert om_email.sender_name("") == "Unknown sender"
    monkeypatch.delenv("OPEN_MEDIA_API_BASE", raising=False)
    assert settings.web_origin() == "https://openmedia.site"
