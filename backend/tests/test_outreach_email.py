"""First customers, end to end: researched prospects → honest drafts → waiting in Messages →
the founder's yes → sent once from their own mailbox → their reply reported in their words.

Open Media is a fake; under test are the rules: drafts that read like spam or pretend to know
someone are refused, an address is a recipient only when it was really found, nothing is sent
without a yes for exactly that text, an edit needs a new yes, and a retry never sends twice."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from app.db.database import InMemoryDatabaseClient
from app.services.goals import capabilities, engine, policy, store
from app.services.ideas import customer_discovery as cd
from app.services.ideas import outreach
from app.services.integrations import discovery_connectors as connectors
from app.services.integrations.open_media.client import OpenMediaError, OpenMediaUnavailable

USER = "22222222-2222-2222-2222-222222222222"
IDEA = {"idea_id": "idea-9", "title": "Manifest", "description": "From an idea to a plan."}
BODY = (
    "Hi Priya, I read your post about juggling a spreadsheet, a deck and three docs while "
    "applying to accelerators. I'm Mihir, and I'm building a workspace that keeps those in one "
    "place. It's early and I'm not selling anything. How do you keep them in sync today? A "
    "one-line reply would help."
)


class FakeMail:
    """Open Media's mailbox routes: one sending mailbox, idempotent sends, stored mail."""

    def __init__(self) -> None:
        self.boxes = [
            {"id": "box-1", "email": "me@founder.test", "status": "connected", "can_send": True}
        ]
        self.sent: list[dict] = []
        self.rows: list[dict] = []
        self.syncs = 0
        self.fail: Exception | None = None

    def send(
        self, user_id, *, to, subject, text, idempotency_key, mailbox_id=None, in_reply_to=None
    ):
        if self.fail:
            error, self.fail = self.fail, None
            raise error
        if not any(b["can_send"] for b in self.boxes):
            raise OpenMediaError("None can send", status=409, code="no_mailbox")
        message_id = f"<om-{idempotency_key}@openmedia.site>"
        if any(r["messageId"] == message_id for r in self.rows):
            return {"mailbox_id": "box-1", "from": "me@founder.test", "replayed": True,
                    "message": {"sourceMessageId": message_id}}  # fmt: skip
        self.sent.append({"to": to, "subject": subject, "text": text, "key": idempotency_key,
                          "in_reply_to": in_reply_to})  # fmt: skip
        row = {"messageId": message_id, "from": "me@founder.test", "to": [to], "subject": subject,
               "text": text, "sentAt": store.now().isoformat(), "folder": "Sent"}  # fmt: skip
        self.rows.insert(0, row)
        return {
            "mailbox_id": "box-1",
            "from": "me@founder.test",
            "message": {**row, "sourceMessageId": message_id},
        }

    def stored(self, user_id, *, limit=200):
        return self.rows[:limit]

    def sync(self, user_id, mailbox_id):
        self.syncs += 1

    def reply(self, sender: str, text: str) -> None:
        self.rows.insert(0, {"messageId": f"<r{len(self.rows)}@x>", "from": f"Priya <{sender}>",
                             "subject": "Re: Question", "text": text, "folder": "INBOX",
                             "sentAt": (store.now() + timedelta(seconds=5)).isoformat()})  # fmt: skip


@pytest.fixture
def db():
    return InMemoryDatabaseClient()


@pytest.fixture
def mail(monkeypatch):
    fake = FakeMail()
    monkeypatch.setattr(capabilities.mail, "send", fake.send)
    monkeypatch.setattr(capabilities.mail, "stored", fake.stored)
    monkeypatch.setattr(capabilities.mail, "sync", fake.sync)
    monkeypatch.setattr(
        capabilities.mail,
        "sending_mailbox",
        lambda uid: next((b for b in fake.boxes if b["can_send"]), None),
    )
    return fake


def _email_goal(db, **kw):
    return engine.create_goal(
        db,
        USER,
        title=kw.pop("title", "Email Priya Shah"),
        idea_id="idea-9",
        steps=engine.email_outreach_plan(
            to=kw.pop("to", "priya@studio.test"),
            to_name="Priya Shah",
            subject=kw.pop("subject", "Question about your accelerator prep"),
            body=kw.pop("body", BODY),
            why="Posted about juggling application documents",
            evidence=[{"text": "Her post", "url": "https://example.org/post"}],
            **kw,
        ),
    )


def _approve(db, view):
    pending = [a for a in view["approvals"] if a["status"] == "pending"]
    assert len(pending) == 1
    return engine.decide_approval(
        db,
        USER,
        pending[0]["id"],
        approve=True,
        scope_sha256=pending[0]["scope_sha256"],
        via="test",
    )


# ---- the writing rules ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("subject", "body", "problem"),
    [
        ("Hi [Name]", BODY, "placeholder"),
        ("Re: our chat", BODY, "reply or forward"),
        ("Question", "As we discussed, " + BODY, "past contact"),
        ("Question", "I hope this email finds you well. " + BODY, "sales email"),
        ("Question", "Revolutionary, game-changer tool. " + BODY, "sales email"),
        ("Question", "Hi, quick question?", "too short"),
        ("Question", " ".join(["word"] * 200), "too long"),
    ],
)
def test_spammy_or_dishonest_drafts_are_refused(subject, body, problem):
    problems, _notes = outreach.check(subject, body)
    assert any(problem in p for p in problems), problems


def test_a_good_draft_passes_and_gets_an_easy_out_and_a_name():
    problems, notes = outreach.check("Question about your accelerator prep", BODY)
    assert problems == [] and notes == []
    finished = outreach.finish(BODY, "Mihir Kavishwar")
    assert outreach.OPT_OUT in finished and finished.rstrip().endswith("Mihir Kavishwar")
    # An existing opt-out and signature are never doubled.
    assert outreach.finish(finished, "Mihir Kavishwar") == finished
    # The easy out goes above a sign-off that's already there.
    signed = outreach.finish(
        BODY + "\n\nMihir Kavishwar\nManifest, manifeststartup.com", "Mihir Kavishwar"
    )
    assert signed.endswith(f"{outreach.OPT_OUT}\n\nMihir Kavishwar\nManifest, manifeststartup.com")


# ---- email goals: approve, send once, hear back ---------------------------------------------


def test_nothing_is_sent_until_the_exact_email_is_approved_then_it_goes_once(db, mail):
    view = _email_goal(db)
    approval = next(a for a in view["approvals"] if a["status"] == "pending")
    assert approval["scope"]["to"] == "priya@studio.test"
    assert approval["scope"]["subject"] == "Question about your accelerator prep"
    assert approval["scope"]["body"] == BODY
    assert approval["summary"] == 'Email Priya Shah: "Question about your accelerator prep"'
    assert "your own mailbox" in approval["consequences"]
    assert mail.sent == []
    draft = next(t for t in view["tasks"] if t["step_key"] == "draft")["result"]
    assert draft["from"] == "me@founder.test" and draft["mailbox_ready"] is True

    view = _approve(db, view)
    assert len(mail.sent) == 1
    uuid.UUID(mail.sent[0]["key"])  # Open Media's /v1/me routes accept only a UUID
    send = next(t for t in view["tasks"] if t["step_key"] == "send")
    assert send["status"] == "completed" and send["verification"]["verified"] is True
    for _ in range(3):  # requests, sweeps and webhooks advance it again
        engine.advance(db, USER, view["goal"]["id"], force_check=True)
    assert len(mail.sent) == 1
    assert mail.syncs >= 1  # it fetched new mail to look for a reply
    assert "Wait for a reply from Priya Shah" in " ".join(
        engine.view(db, USER, view["goal"]["id"])["report"]["waiting"]
    )


def test_a_retry_after_a_network_error_never_sends_twice(db, mail):
    view = _email_goal(db)
    mail.fail = OpenMediaUnavailable("timeout")
    view = _approve(db, view)
    send = store.one(db, store.TASKS, goal_id=view["goal"]["id"], step_key="send")
    assert send["status"] == "ready" and mail.sent == []
    store.cas_update(db, store.TASKS, send["id"], {"status": "ready"}, {"next_check_at": None})
    engine.advance(db, USER, view["goal"]["id"])
    engine.advance(db, USER, view["goal"]["id"])
    assert len(mail.sent) == 1


def test_their_reply_is_reported_in_their_words_without_the_quoted_email(db, mail):
    view = _approve(db, _email_goal(db))
    mail.reply(
        "priya@studio.test",
        "Honestly I use Notion and it's a mess. Happy to chat Thursday.\n\nOn Mon, Mihir wrote:\n> Hi Priya",
    )
    view = engine.advance(db, USER, view["goal"]["id"], force_check=True)
    reply = next(t for t in view["tasks"] if t["step_key"] == "reply")
    assert reply["status"] == "completed"
    assert (
        "Notion" in reply["result"]["text_untrusted"]
        and "Hi Priya" not in reply["result"]["text_untrusted"]
    )
    assert (
        "UNTRUSTED_BEGIN" in reply["result"]["text_untrusted"]
    )  # fenced for any model that reads it
    replied = next(f for f in view["facts"] if f["predicate"] == "replied")
    assert replied["kind"] == "external_claim" and replied["source_ref"].startswith("email:")
    assert view["goal"]["status"] == "achieved"
    # The answered goal stays in Messages and in voice's list, with their words.
    assert [g["id"] for g in engine.list_goals(db, USER)] == [view["goal"]["id"]]


def test_without_a_sending_mailbox_it_waits_with_an_open_in_gmail_link(db, mail):
    mail.boxes[0]["can_send"] = False
    view = _email_goal(db)
    draft = next(t for t in view["tasks"] if t["step_key"] == "draft")["result"]
    assert draft["mailbox_ready"] is False  # the card can warn before Send
    view = _approve(db, view)
    send = next(t for t in view["tasks"] if t["step_key"] == "send")
    assert send["status"] == "blocked" and "Open in Gmail" in send["last_error"]
    assert send["result"]["compose_url"].startswith("https://mail.google.com/mail/?view=cm")
    assert mail.sent == []


def test_an_edit_needs_a_new_yes_and_the_old_one_no_longer_works(db, mail):
    view = _email_goal(db)
    old = next(a for a in view["approvals"] if a["status"] == "pending")
    view = engine.edit_draft(
        db, USER, view["goal"]["id"], body=BODY.replace("Hi Priya", "Hey Priya")
    )
    pending = [a for a in view["approvals"] if a["status"] == "pending"]
    assert len(pending) == 1 and pending[0]["id"] != old["id"]
    assert pending[0]["scope"]["body"].startswith("Hey Priya")
    with pytest.raises(policy.ApprovalError):
        engine.decide_approval(
            db, USER, old["id"], approve=True, scope_sha256=old["scope_sha256"], via="t"
        )
    _approve(db, view)
    assert mail.sent[0]["text"].startswith("Hey Priya")
    with pytest.raises(engine.GoalError, match="no unsent message"):
        engine.edit_draft(db, USER, view["goal"]["id"], body="Too late")


# ---- from discovery into Messages -----------------------------------------------------------


def _prospect(email=None, handle=None, contact_url="https://studio.test/contact"):
    entry = {
        "name": "Priya Shah",
        "kind": "person",
        "role": "Solo founder",
        "website": "https://studio.test",
        "why_fit": "Applying to accelerators with documents scattered across tools.",
        "need_evidence": [
            {"text": "Posted about juggling application docs", "url": "https://example.org/post"}
        ],
        "sources": ["https://example.org/post"],
        "scores": {"problem_relevance": 5, "profile_fit": 4, "need_evidence": 5, "purchasing": 2},
    }
    if email:
        entry["contact"] = {"method": "email on her site", "value": email, "source": contact_url}
    if handle:
        entry["contact"] = {"method": "Open Media", "value": handle}
    return entry


@pytest.fixture
def web(monkeypatch):
    pages = {"https://studio.test/contact": "Say hi: priya [at] studio [dot] test"}
    monkeypatch.setattr(
        connectors, "web_read", lambda url: {"url": url, "title": "", "text": pages.get(url, "")}
    )
    monkeypatch.setattr(connectors, "website_resolves", lambda url: True)
    return pages


def test_an_address_is_a_recipient_only_when_the_cited_page_shows_it(db, web, mail):
    work = {"prospects": [_prospect(email="priya@studio.test")]}
    state = cd.save_agent_work(db=db, user_id=USER, idea=IDEA, work=work)["state"]
    priya = state["prospects"][0]
    assert priya["kind"] == "person" and priya["decision_maker"]["name"] == "Priya Shah"
    assert priya["contact"]["verified"] is True and priya["contact"]["verified_by"] == "public page"

    invented = {"prospects": [_prospect(email="ceo@studio.test")]}
    state = cd.save_agent_work(db=db, user_id=USER, idea=IDEA, work=invented)["state"]
    assert state["prospects"][0]["contact"]["verified"] is False
    assert any("Couldn't find ceo@studio.test" in u for u in state["prospects"][0]["unverified"])
    # An agent can't just claim it was verified.
    claimed = _prospect(email="ceo@studio.test")
    claimed["contact"]["verified"] = True
    state = cd.save_agent_work(db=db, user_id=USER, idea=IDEA, work={"prospects": [claimed]})[
        "state"
    ]
    assert state["prospects"][0]["contact"]["verified"] is False


def test_drafts_land_in_messages_waiting_for_a_yes_and_updates_replace_them(db, web, mail):
    work = {
        "prospects": [_prospect(email="priya@studio.test")],
        "sender_name": "Mihir Kavishwar",
        "outreach": [
            {
                "prospect_name": "Priya Shah",
                "subject": "Question about your accelerator prep",
                "body": BODY,
            }
        ],
    }
    result = cd.save_agent_work(db=db, user_id=USER, idea=IDEA, work=work)
    assert any("waiting in Messages for your OK" in x for x in result["limitations"])
    draft = result["state"]["outreach"][0]
    assert draft and draft["goal_id"] and draft["body"].rstrip().endswith("Mihir Kavishwar")
    goals = engine.list_goals(db, USER)
    assert [g["title"] for g in goals] == ["Email Priya Shah"]
    assert mail.sent == []

    # The agent rewrites it: the waiting message is replaced, not duplicated.
    work["outreach"][0]["body"] = BODY.replace(
        "A one-line reply would help.", "Even one line helps."
    )
    result = cd.save_agent_work(db=db, user_id=USER, idea=IDEA, work=work)
    assert len(engine.list_goals(db, USER)) == 1
    view = engine.view(db, USER, goals[0]["id"])
    pending = [a for a in view["approvals"] if a["status"] == "pending"]
    assert len(pending) == 1 and "Even one line helps." in pending[0]["scope"]["body"]
    assert "waiting in Messages" in cd.render_markdown(result["state"])


def test_spammy_agent_drafts_are_sent_back_with_what_to_fix(db, web, mail):
    work = {
        "prospects": [_prospect(email="priya@studio.test")],
        "outreach": [
            {
                "prospect_name": "Priya Shah",
                "subject": "Re: quick call",
                "body": "I hope this email finds you well! Quick call?",
            }
        ],  # fmt: skip
    }
    result = cd.save_agent_work(db=db, user_id=USER, idea=IDEA, work=work)
    assert result["state"]["outreach"] == []
    assert any("rewrite it" in x and "sales email" in x for x in result["limitations"])
    assert engine.list_goals(db, USER) == []


def test_open_media_handles_are_checked_and_become_direct_messages(db, web, mail, monkeypatch):
    class Public:
        def public(self, path, params=None):
            if path.endswith("/priya"):
                return {"data": {"handle": "priya", "id": "om-priya"}}
            raise OpenMediaError("Not found", status=404)

    from app.services.integrations.open_media import client

    monkeypatch.setattr(client, "get_client", lambda: Public())
    monkeypatch.setattr(capabilities, "get_client", lambda: Public())
    monkeypatch.setattr(capabilities.messaging, "existing_conversation_with", lambda uid, h: None)
    work = {
        "prospects": [_prospect(handle="@Priya")],
        "outreach": [{"prospect_name": "Priya Shah", "subject": "", "body": BODY}],
    }
    result = cd.save_agent_work(db=db, user_id=USER, idea=IDEA, work=work)
    draft = result["state"]["outreach"][0]
    assert draft["channel"] == "open_media" and draft["to"] == "priya"
    goal = engine.list_goals(db, USER)[0]
    assert goal["title"] == "Message Priya Shah"
    pending = engine.pending_approvals(db, USER)
    assert pending and pending[0]["scope"]["action"] == "message.send"


def test_voice_hears_each_waiting_message_not_the_plan():
    from app.services.voice.live import tools

    goal = {
        "id": "g1", "title": "Email Priya Shah", "status": "active",
        "steps": [{"key": "draft", "result": {"body": "x" * 5000}}] * 6,
        "timeline": [{"summary": "y" * 3000}], "facts": [],
        "report": {"spoken": "Needs you: Approve or decline: Email Priya Shah."},
        "approvals": [{"id": "a1", "summary": "Email Priya", "consequences": "c", "scopeSha256": "h",
                       "status": "pending"}, {"id": "a0", "status": "superseded"}],
        "draft": {"to": "priya@studio.test", "body": BODY, "composeUrl": "https://x", "reply": None},
    }  # fmt: skip
    spoken = tools.SPEECH_SHAPES["goals"]([goal] * 8)
    assert len(spoken) == 8 and "steps" not in spoken[0]
    assert spoken[0]["draft"]["body"] == BODY and "composeUrl" not in spoken[0]["draft"]
    assert spoken[0]["approvals"] == [
        {"id": "a1", "summary": "Email Priya", "consequences": "c", "scopeSha256": "h"}
    ]
    assert tools._clip(spoken) == spoken  # eight messages fit whole in one answer


def test_a_follow_up_threads_under_the_first_email_waits_for_a_yes_and_stops_at_two(db, mail):
    view = _approve(
        db,
        _email_goal(
            db,
            follow_up="Quick thought: is it finding people or knowing what to ask that's harder?",
        ),
    )
    goal_id = view["goal"]["id"]
    with pytest.raises(engine.GoalError, match="few days"):
        engine.follow_up(db, USER, goal_id)  # too soon
    send = store.one(db, store.TASKS, goal_id=goal_id, step_key="send")
    old = (store.now() - timedelta(days=4)).isoformat()
    store.cas_update(db, store.TASKS, send["id"], {"status": "completed"},
                     {"result": {**send["result"], "sent_at": old}})  # fmt: skip
    follow = engine.follow_up(db, USER, goal_id)
    pending = [a for a in follow["approvals"] if a["status"] == "pending"]
    assert follow["goal"]["title"] == "Follow up with Priya Shah"
    assert pending[0]["scope"]["subject"] == "Re: Question about your accelerator prep"
    assert pending[0]["scope"]["in_reply_to"].startswith("<om-")
    assert (
        "is it finding people" in pending[0]["scope"]["body"]
        and outreach.OPT_OUT in pending[0]["scope"]["body"]
    )
    assert len(mail.sent) == 1  # nothing sent until the yes
    assert engine.view(db, USER, goal_id)["goal"]["status"] == "cancelled"
    with pytest.raises(engine.GoalError, match="already followed up"):
        engine.follow_up(db, USER, goal_id)
    _approve(db, follow)
    assert len(mail.sent) == 2 and mail.sent[1]["subject"].startswith("Re: ")
    assert mail.sent[1]["in_reply_to"] == mail.rows[-1]["messageId"]  # threads under the first
    # Only the follow-up shows now, and a "bumping this" note is refused.
    assert [g["title"] for g in engine.list_goals(db, USER)] == ["Follow up with Priya Shah"]
    send2 = store.one(db, store.TASKS, goal_id=follow["goal"]["id"], step_key="send")
    store.cas_update(db, store.TASKS, send2["id"], {"status": "completed"},
                     {"result": {**send2["result"], "sent_at": old}})  # fmt: skip
    with pytest.raises(engine.GoalError, match="something new"):
        engine.follow_up(db, USER, follow["goal"]["id"], body="Just bumping this.")


def test_follow_up_status_says_why_not(db, mail):
    view = _email_goal(db)
    tasks = engine.view(db, USER, view["goal"]["id"])["tasks"]
    assert engine.follow_up_status(tasks) == {
        "allowed": False,
        "reason": "It hasn't been sent yet.",
    }


def test_the_real_mail_adapter_sends_a_uuid_key_and_threads(monkeypatch):
    """What goes over the wire to Open Media (its /v1/me routes refuse a non-UUID key)."""
    from app.services.integrations.open_media import mail as real_mail

    calls = []

    class Client:
        def connected(self, user_id, method, path, **kw):
            calls.append((method, path, kw))
            return {"message": {"sourceMessageId": "<x@y>"}}

    monkeypatch.setattr(real_mail, "get_client", lambda: Client())
    key = str(uuid.uuid4())
    real_mail.send(
        USER, to="a@b.co", subject="Hi", text="Hello", idempotency_key=key, in_reply_to="<x@y>"
    )
    method, path, kw = calls[0]
    assert (method, path) == ("POST", "/email") and kw["headers"] == {"Idempotency-Key": key}
    assert kw["json"]["in_reply_to"] == "<x@y>" and kw["idempotent"] is True
    with pytest.raises(ValueError, match="UUID"):
        real_mail.send(
            USER, to="a@b.co", subject="Hi", text="Hello", idempotency_key="manifest-goal-1"
        )
