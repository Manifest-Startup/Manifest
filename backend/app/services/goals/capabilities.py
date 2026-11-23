"""What a goal's step can do. Each capability declares its risk tier, inputs and how its result
is verified, and runs deterministic code: no model decides whether a step succeeded.

A step's input can reference an earlier step's result with ``"$steps.<key>"`` (the whole
result) or ``"$steps.<key>.<field>"``. A step only runs after the steps it depends on are
completed, so references always resolve.

Communication goes through Open Media (ADR 0001). Open Media has no drafts API yet, so a
prepared message is held by its ``message.prepare`` step here, shown in the approval, and
sent with Open Media's idempotent send (``client_id`` = the task id, so a retry can never
send twice).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from urllib.parse import quote

from app.security.ai_safety import looks_like_injection_attempt, wrap_untrusted
from app.services.goals import extraction, knowledge, store
from app.services.integrations.open_media import identity, messaging, settings
from app.services.integrations.open_media.client import OpenMediaError, get_client, pick

REPLY_CHECK_EVERY = timedelta(minutes=15)
REPLY_WAIT_DEFAULT_DAYS = 7
MAX_REPLY_CHARS = 1500


@dataclass
class Context:
    db: Any
    user_id: str
    goal: dict[str, Any]
    task: dict[str, Any]
    steps: dict[str, dict[str, Any]]  # step_key -> task row


@dataclass
class Outcome:
    """``completed`` | ``waiting`` (check again later) | ``blocked`` (needs the person) | ``failed``."""

    status: str
    result: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    check_after: timedelta | None = None


@dataclass(frozen=True)
class Capability:
    name: str
    title: str
    tier: int
    description: str
    required: tuple[str, ...]
    run: Callable[[Context, dict[str, Any]], Outcome]
    # For tier 2+: what exactly the person approves, and how it is described to them.
    scope: Callable[[Context, dict[str, Any]], dict[str, Any]] | None = None
    describe: Callable[[Context, dict[str, Any]], dict[str, str]] | None = None


class StepInputError(ValueError):
    pass


def _handle(value: Any) -> str:
    text = str(value or "").strip().lstrip("@").lower()
    if not text or len(text) > 64 or any(c.isspace() for c in text):
        raise StepInputError("Give an Open Media handle, like @ana.")
    return text


def resolve_input(raw: dict[str, Any], steps: dict[str, dict[str, Any]]) -> dict[str, Any]:
    def resolve(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("$steps."):
            parts = value[len("$steps.") :].split(".")
            step = steps.get(parts[0])
            if step is None or step.get("status") != "completed":
                raise StepInputError(f"Step '{parts[0]}' hasn't finished.")
            current: Any = step.get("result") or {}
            for part in parts[1:]:
                current = current.get(part) if isinstance(current, dict) else None
            return current
        if isinstance(value, dict):
            return {k: resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve(v) for v in value]
        return value

    return {k: resolve(v) for k, v in (raw or {}).items()}


# --- contact.resolve (tier 0) -----------------------------------------------------------------


def _resolve_contact(ctx: Context, data: dict[str, Any]) -> Outcome:
    handle = _handle(data.get("handle"))
    try:
        body = get_client().public(f"/v1/profiles/{quote(handle, safe='')}")
    except OpenMediaError as exc:
        if exc.status == 404:
            return Outcome(
                "blocked",
                error=f"There's no one called @{handle} on Open Media. Check the handle.",
            )
        raise
    profile = body.get("data") if isinstance(body.get("data"), dict) else body
    found = str(pick(profile, "handle", default="")).lower()
    if found != handle:
        return Outcome("blocked", error=f"Open Media returned a different person for @{handle}.")
    result = {
        "handle": found,
        "display_name": pick(profile, "display_name", "displayName"),
        "om_user_id": str(pick(profile, "id", default="")) or None,
        "channel": "open_media",
    }
    knowledge.record(
        ctx.db,
        ctx.user_id,
        subject_type="person",
        subject_key=found,
        predicate="reachable_on",
        value="Open Media direct message",
        kind="verified",
        source_type="open_media_profile",
        source_ref=f"{settings.api_base()}/v1/profiles/{found}",
        extraction="api_lookup",
        goal_id=ctx.goal["id"],
    )
    return Outcome("completed", result, {"verified": True, "how": "Open Media profile exists"})


# --- message.prepare (tier 1) -----------------------------------------------------------------


def _prepare_message(ctx: Context, data: dict[str, Any]) -> Outcome:
    to = data.get("to")
    handle = _handle(to.get("handle") if isinstance(to, dict) else to)
    body = str(data.get("body") or "").strip()
    if not body:
        raise StepInputError("Write the message first.")
    if len(body) > messaging.MAX_BODY_CHARS:
        raise StepInputError(f"Messages can be up to {messaging.MAX_BODY_CHARS:,} characters.")
    result = {
        "to": handle,
        "body": body,
        "purpose": str(data.get("purpose") or "")[:300],
        "channel": "open_media",
    }
    return Outcome("completed", result, {"verified": True, "how": "Draft saved in the plan"})


# --- message.send (tier 2) --------------------------------------------------------------------


def _draft_of(data: dict[str, Any]) -> dict[str, Any]:
    draft = data.get("draft")
    if not isinstance(draft, dict) or not draft.get("body") or not draft.get("to"):
        raise StepInputError("message.send needs a prepared draft ($steps.<prepare step>).")
    return draft


def _send_scope(ctx: Context, data: dict[str, Any]) -> dict[str, Any]:
    draft = _draft_of(data)
    return {
        "action": "message.send",
        "channel": "open_media",
        "to": _handle(draft["to"]),
        "body": draft["body"],
        "idea_id": ctx.goal.get("idea_id"),
    }


def _send_describe(ctx: Context, data: dict[str, Any]) -> dict[str, str]:
    draft = _draft_of(data)
    preview = draft["body"] if len(draft["body"]) <= 160 else draft["body"][:157] + "…"
    return {
        "summary": f'Send @{draft["to"]} on Open Media: "{preview}"',
        "reason": f"Goal: {ctx.goal['title']}"
        + (f" ({draft['purpose']})" if draft.get("purpose") else ""),
        "consequences": f"@{draft['to']} gets this message from your Open Media account. "
        "It can't be unsent.",
    }


def _conversation_context(ctx: Context) -> dict[str, Any]:
    idea_id = ctx.goal.get("idea_id")
    if idea_id:
        return messaging.idea_context(str(idea_id), ctx.goal.get("title"))
    return {"app": settings.APP_TAG, "title": str(ctx.goal.get("title") or "")[:200]}


def _send_message(ctx: Context, data: dict[str, Any]) -> Outcome:
    scope = _send_scope(ctx, data)
    conversation = messaging.start_conversation(
        ctx.user_id, handle=scope["to"], context=_conversation_context(ctx)
    )
    conversation_id = conversation.get("id")
    if not conversation_id:
        return Outcome("failed", error="Open Media didn't open a conversation.")
    sent = messaging.send_message(
        ctx.user_id, conversation_id, body=scope["body"], client_id=ctx.task["id"]
    )
    message_id = sent.get("id")
    if not message_id:
        return Outcome("failed", error="Open Media didn't confirm the message.")
    # Verify against Open Media itself, not the send call's return value.
    recent = messaging.list_messages(ctx.user_id, conversation_id, limit=20)
    delivered = next((m for m in recent if m.get("id") == message_id), None)
    result = {
        "conversation_id": conversation_id,
        "message_id": message_id,
        "to": scope["to"],
        "sent_at": store.iso((delivered or sent).get("created_at")) or store.now().isoformat(),
        "sender_id": (delivered or sent).get("sender_id") or identity.om_user_id_for(ctx.user_id),
    }
    if delivered is None:
        return Outcome(
            "failed",
            result,
            {"verified": False, "how": "Message not found in the conversation after sending"},
            error="Open Media accepted the message but it isn't in the conversation yet.",
        )
    return Outcome(
        "completed", result, {"verified": True, "how": "Message is in the Open Media conversation"}
    )


# --- reply.await (tier 0, waits) --------------------------------------------------------------


def _await_reply(ctx: Context, data: dict[str, Any]) -> Outcome:
    sent = data.get("after")
    if not isinstance(sent, dict) or not sent.get("conversation_id"):
        raise StepInputError("reply.await needs the send step ($steps.<send step>).")
    conversation_id = sent["conversation_id"]
    me = sent.get("sender_id") or identity.om_user_id_for(ctx.user_id)
    sent_at = store.parse_time(sent.get("sent_at"))
    messages = messaging.list_messages(ctx.user_id, conversation_id, limit=50)
    replies = [
        m
        for m in messages
        if m.get("sender_id")
        and m.get("sender_id") != me
        and (sent_at is None or (store.parse_time(m.get("created_at")) or sent_at) > sent_at)
    ]
    waiting = {"conversation_id": conversation_id, "waiting_for": sent.get("to")}
    if not replies:
        days = int(data.get("days") or REPLY_WAIT_DEFAULT_DAYS)
        if sent_at and store.now() - sent_at > timedelta(days=days):
            return Outcome(
                "blocked",
                waiting,
                error=f"No reply from @{sent.get('to')} in {days} days. Follow up or close the goal.",
            )
        return Outcome("waiting", waiting, check_after=REPLY_CHECK_EVERY)
    reply = replies[0]
    text = str(reply.get("body") or "")[:MAX_REPLY_CHARS]
    suspicious = looks_like_injection_attempt(text)
    result = {
        **waiting,
        "reply_message_id": reply.get("id"),
        "from": sent.get("to"),
        "received_at": store.iso(reply.get("created_at")),
        # Their words are data. Agents get them fenced; nothing in them can run a step.
        "text_untrusted": text,
        "suspected_injection": suspicious,
    }
    if suspicious:
        store.record_event(
            ctx.db,
            ctx.user_id,
            ctx.goal["id"],
            "security.untrusted_instructions",
            f"A reply from @{sent.get('to')} contains instructions aimed at an assistant; "
            "they were treated as text.",
            {"message_id": reply.get("id")},
            dedupe_key=f"security.injection:{reply.get('id')}",
        )
    return Outcome(
        "completed", result, {"verified": True, "how": "Reply is in the Open Media conversation"}
    )


# --- knowledge.record (tier 1) ----------------------------------------------------------------


def _record_knowledge(ctx: Context, data: dict[str, Any]) -> Outcome:
    saved: list[str] = []
    reply = data.get("reply")
    if isinstance(reply, dict) and reply.get("reply_message_id"):
        fact = knowledge.record(
            ctx.db,
            ctx.user_id,
            subject_type="person",
            subject_key=str(reply.get("from") or "unknown"),
            predicate="replied",
            value=str(reply.get("text_untrusted") or ""),
            kind="external_claim",
            source_type="open_media_message",
            source_ref=f"open_media:message:{reply['reply_message_id']}",
            source_at=reply.get("received_at"),
            extraction="verbatim",
            goal_id=ctx.goal["id"],
        )
        saved.append(fact["id"])
        who = str(reply.get("from") or "unknown")
        # A reply that tries to instruct an assistant is kept verbatim but not mined: its
        # sentences never reach the spoken report.
        text = "" if reply.get("suspected_injection") else str(reply.get("text_untrusted") or "")
        findings = extraction.extract(text)
        for finding in findings:
            inferred = knowledge.record(
                ctx.db,
                ctx.user_id,
                subject_type="person",
                subject_key=who,
                predicate=finding.predicate,
                value=finding.quote,
                kind="inferred",
                source_type="open_media_message",
                source_ref=f"open_media:message:{reply['reply_message_id']}",
                source_at=reply.get("received_at"),
                extraction="rules:v1",
                goal_id=ctx.goal["id"],
            )
            saved.append(inferred["id"])
        if findings:
            store.record_event(
                ctx.db,
                ctx.user_id,
                ctx.goal["id"],
                "knowledge.extracted",
                f"From @{who}'s reply: "
                + "; ".join(f'{f.predicate} "{f.quote[:80]}"' for f in findings[:3])
                + " (unconfirmed)",
                {"facts": saved[-len(findings) :]},
                dedupe_key=f"knowledge.extracted:{reply['reply_message_id']}",
            )
    for item in data.get("facts") or []:
        if not isinstance(item, dict):
            continue
        kind = (
            item.get("kind") if item.get("kind") in ("stated_by_user", "inferred") else "inferred"
        )
        fact = knowledge.record(
            ctx.db,
            ctx.user_id,
            subject_type=str(item.get("subject_type") or "person"),
            subject_key=str(item.get("subject") or ""),
            predicate=str(item.get("predicate") or ""),
            value=str(item.get("value") or ""),
            kind=kind,
            source_type="goal_plan",
            source_ref=f"goal:{ctx.goal['id']}",
            extraction="explicit" if kind == "stated_by_user" else "agent",
            goal_id=ctx.goal["id"],
        )
        saved.append(fact["id"])
    if not saved:
        raise StepInputError("Nothing to record: pass reply ($steps.<await step>) or facts.")
    stored = [
        f for f in knowledge.for_goal(ctx.db, ctx.user_id, ctx.goal["id"]) if f["id"] in saved
    ]
    return Outcome(
        "completed",
        {"fact_ids": saved},
        {"verified": len(stored) == len(saved), "how": f"{len(stored)} fact(s) read back"},
    )


REGISTRY: dict[str, Capability] = {
    cap.name: cap
    for cap in (
        Capability(
            "contact.resolve",
            "Find the person",
            0,
            "Check that an Open Media handle belongs to a real person (input: handle).",
            ("handle",),
            _resolve_contact,
        ),
        Capability(
            "message.prepare",
            "Prepare the message",
            1,
            "Hold a message for review; nothing is sent (input: to, body, purpose).",
            ("to", "body"),
            _prepare_message,
        ),
        Capability(
            "message.send",
            "Send the message",
            2,
            "Send a prepared message on Open Media after the person approves exactly it "
            "(input: draft = $steps.<prepare>).",
            ("draft",),
            _send_message,
            scope=_send_scope,
            describe=_send_describe,
        ),
        Capability(
            "reply.await",
            "Wait for a reply",
            0,
            "Wait for the recipient to answer (input: after = $steps.<send>, days).",
            ("after",),
            _await_reply,
        ),
        Capability(
            "knowledge.record",
            "Remember what was learned",
            1,
            "Save the reply (input: reply = $steps.<await>) or facts as knowledge with sources.",
            (),
            _record_knowledge,
        ),
    )
}


def fenced_reply(result: dict[str, Any]) -> dict[str, Any]:
    """A step result safe to hand to a model: the other person's words are fenced."""
    if "text_untrusted" not in result:
        return result
    return {**result, "text_untrusted": wrap_untrusted(result["text_untrusted"], label="reply")}
