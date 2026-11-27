"""What a goal's step can do. Each capability declares its risk tier, inputs and how its result
is verified, and runs deterministic code: no model decides whether a step succeeded.

A step's input can reference an earlier step's result with ``"$steps.<key>"`` (the whole
result) or ``"$steps.<key>.<field>"``. A step only runs after the steps it depends on are
completed, so references always resolve.

Communication goes through Open Media (ADR 0001). A prepared message is held by its
``message.prepare`` / ``email.prepare`` step here, shown in the approval, and sent with Open
Media's idempotent send (the task id is the idempotency key, so a retry can never send twice).
Email goes from the person's own mailbox connected in Open Media (ADR 0026); the sent copy and
any reply land in their Messages.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from urllib.parse import quote

from app.security.ai_safety import looks_like_injection_attempt, wrap_untrusted
from app.services.goals import extraction, knowledge, store
from app.services.integrations.open_media import identity, mail, messaging, settings
from app.services.integrations.open_media.client import OpenMediaError, get_client, pick
from app.utils.logger import logger

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
    draft_id = _mirror_draft(ctx, handle, body)
    if draft_id:
        result["open_media_draft_id"] = draft_id
        how = "Draft saved in the plan and in your Open Media conversation"
    else:
        how = "Draft saved in the plan"
    return Outcome("completed", result, {"verified": True, "how": how})


def _mirror_draft(ctx: Context, handle: str, body: str) -> str | None:
    """Best effort: show the draft in an Open Media conversation the person already has with
    this person, so they see it where they read their messages. Never opens a conversation
    (the other person could see that) and never fails the step. The approval still covers
    the text held here; edits made in Open Media are not what gets sent."""
    try:
        conversation_id = messaging.existing_conversation_with(ctx.user_id, handle)
        if not conversation_id:
            return None
        draft = messaging.save_draft(ctx.user_id, conversation_id, body=body, ref=ctx.task["id"])
        return str(draft.get("id") or "") or None
    except Exception as exc:  # older Open Media without drafts, or a network hiccup
        logger.info(
            "goal draft not mirrored to Open Media",
            extra={"exception.type": type(exc).__name__, "goal_id": ctx.goal.get("id")},
        )
        return None


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
    draft_id = (data.get("draft") or {}).get("open_media_draft_id")
    if draft_id:
        try:  # the message is sent; its draft copy in Open Media is no longer needed
            messaging.discard_draft(ctx.user_id, str(draft_id))
        except Exception as exc:
            logger.info(
                "goal draft not discarded in Open Media",
                extra={"exception.type": type(exc).__name__, "goal_id": ctx.goal.get("id")},
            )
    return Outcome(
        "completed", result, {"verified": True, "how": "Message is in the Open Media conversation"}
    )


# --- email.prepare (tier 1) / email.send (tier 2): from the person's own mailbox ----------------


def _clean_evidence(raw: Any) -> list[dict[str, str]]:
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and str(item.get("text") or "").strip():
            out.append(
                {"text": str(item["text"]).strip()[:300], "url": str(item.get("url") or "")[:500]}
            )
    return out[:4]


def _prepare_email(ctx: Context, data: dict[str, Any]) -> Outcome:
    to = str(data.get("to") or "").strip()
    if not mail.is_email(to):
        raise StepInputError("Give the recipient's email address.")
    subject = " ".join(str(data.get("subject") or "").split())
    body = str(data.get("body") or "").strip()
    if not subject or not body:
        raise StepInputError("Write the subject and the email first.")
    if len(subject) > mail.MAX_SUBJECT_CHARS or len(body) > mail.MAX_BODY_CHARS:
        raise StepInputError("That email is too long to send.")
    result = {
        "channel": "email",
        "to": to,
        "to_name": str(data.get("to_name") or "")[:120] or None,
        "organization": str(data.get("organization") or "")[:160] or None,
        "subject": subject,
        "body": body,
        "purpose": str(data.get("purpose") or "")[:300],
        "why": str(data.get("why") or "")[:600],
        "evidence": _clean_evidence(data.get("evidence")),
        "follow_up": str(data.get("follow_up") or "")[:1500] or None,
        "compose_url": compose_link(to, subject, body),
    }
    if data.get("in_reply_to"):  # a follow-up, in the same thread as the first email
        result["in_reply_to"] = str(data["in_reply_to"])[:900]
        result["follow_up_of"] = str(data.get("follow_up_of") or "")[:80] or None
        result["follow_up_number"] = int(data.get("follow_up_number") or 1)
    # Say up front which mailbox it would go from, or that none can send yet (best effort).
    try:
        box = mail.sending_mailbox(ctx.user_id)
        result["from"] = box.get("email") if box else None
        result["mailbox_ready"] = bool(box)
    except Exception as exc:  # not linked yet, or Open Media is busy: decided at send time
        logger.info("mailbox lookup skipped", extra={"exception.type": type(exc).__name__})
    return Outcome("completed", result, {"verified": True, "how": "Draft saved in the plan"})


def compose_link(to: str, subject: str, body: str) -> str:
    """A pre-filled Gmail compose window, for people whose mailbox can't send from Open Media."""
    from urllib.parse import urlencode

    return "https://mail.google.com/mail/?" + urlencode(
        {"view": "cm", "fs": "1", "to": to, "su": subject, "body": body}
    )


def _email_draft(data: dict[str, Any]) -> dict[str, Any]:
    draft = data.get("draft")
    if not isinstance(draft, dict) or draft.get("channel") != "email" or not draft.get("to"):
        raise StepInputError("email.send needs a prepared email ($steps.<prepare step>).")
    return draft


def _email_scope(ctx: Context, data: dict[str, Any]) -> dict[str, Any]:
    draft = _email_draft(data)
    return {
        "action": "email.send",
        "channel": "email",
        "to": draft["to"].lower(),
        "to_name": draft.get("to_name"),
        "subject": draft["subject"],
        "body": draft["body"],
        "idea_id": ctx.goal.get("idea_id"),
        # Only follow-ups carry it, so first emails keep the scope (and approvals) they had.
        **({"in_reply_to": draft["in_reply_to"]} if draft.get("in_reply_to") else {}),
    }


def _email_describe(ctx: Context, data: dict[str, Any]) -> dict[str, str]:
    draft = _email_draft(data)
    who = draft.get("to_name") or draft["to"]
    at = f" at {draft['organization']}" if draft.get("organization") else ""
    verb = "Follow up with" if draft.get("in_reply_to") else "Email"
    return {
        "summary": f'{verb} {who}{at}: "{draft["subject"]}"',
        "reason": draft.get("why") or f"Goal: {ctx.goal['title']}",
        "consequences": f"{who} gets this email from your own mailbox, and their reply comes "
        "to your Messages. It can't be unsent.",
    }


def _send_email(ctx: Context, data: dict[str, Any]) -> Outcome:
    scope = _email_scope(ctx, data)
    try:
        sent = mail.send(
            ctx.user_id,
            to=scope["to"],
            subject=scope["subject"],
            text=scope["body"],
            # Open Media takes a UUID; the step's own id is one, and a retry reuses it.
            idempotency_key=str(ctx.task["id"]),
            in_reply_to=scope.get("in_reply_to"),
        )
    except OpenMediaError as exc:
        if exc.status == 409 or exc.code == "no_mailbox":
            draft = _email_draft(data)
            return Outcome(
                "blocked",
                {"compose_url": draft.get("compose_url")},
                error="Your email isn't connected for sending yet. Connect your mailbox in Open "
                "Media (Settings, Email & connections), then retry; or send it yourself with "
                "Open in Gmail.",
            )
        raise
    message = sent.get("message") if isinstance(sent.get("message"), dict) else {}
    message_id = message.get("sourceMessageId")
    if not message_id:
        return Outcome("failed", error="Open Media didn't confirm the email.")
    result = {
        "channel": "email",
        "to": scope["to"],
        "to_name": scope.get("to_name"),
        "subject": scope["subject"],
        "message_id": message_id,
        "mailbox_id": sent.get("mailbox_id"),
        "from": sent.get("from"),
        "sent_at": store.iso(message.get("sentAt")) or store.now().isoformat(),
    }
    # Verify against the stored mail, not only the send call's answer.
    try:
        found = any(r.get("messageId") == message_id for r in mail.stored(ctx.user_id, limit=50))
    except OpenMediaError:
        found = False
    verified = found or bool(sent.get("replayed"))
    knowledge.record(
        ctx.db,
        ctx.user_id,
        subject_type="person",
        subject_key=scope["to"],
        predicate="contacted",
        value=f'Email "{scope["subject"]}"',
        kind="verified",
        source_type="email",
        source_ref=f"email:{message_id}",
        extraction="api_send",
        goal_id=ctx.goal["id"],
    )
    return Outcome(
        "completed",
        result,
        {
            "verified": verified,
            "how": "Your mail server accepted it (Manifest watches for a bounce)"
            if verified
            else "Your mail server accepted it",
        },
    )


def _address(value: Any) -> str:
    text = str(value or "").lower()
    found = re.search(r"[^\s<>\"']+@[^\s<>\"']+", text)
    return found.group(0) if found else text.strip()


def _await_email_reply(ctx: Context, sent: dict[str, Any], days: int) -> Outcome:
    to = sent["to"].lower()
    sent_at = store.parse_time(sent.get("sent_at"))
    waiting = {"channel": "email", "waiting_for": sent.get("to_name") or to, "to": to}
    if sent.get("mailbox_id"):
        try:  # fetch new mail now; Open Media only syncs while its app is open
            mail.sync(ctx.user_id, str(sent["mailbox_id"]))
        except OpenMediaError as exc:
            logger.info("mailbox sync skipped", extra={"http.status_code": exc.status})
    rows = mail.stored(ctx.user_id, limit=200)
    bounce = _bounce_for(rows, to, sent.get("message_id"), sent_at)
    if bounce is not None:
        who = sent.get("to_name") or to
        return Outcome(
            "blocked",
            {**waiting, "bounced": True, "bounce_reason": bounce},
            {"verified": True, "how": "A delivery-failure notice came back"},
            error=f"Your email to {who} didn't arrive: it was rejected before delivery ({bounce}). "
            "Nothing more will be sent to this address; find another way to reach them.",
        )
    replies = [
        r
        for r in rows
        if _address(r.get("from")) == to
        and (sent_at is None or (store.parse_time(r.get("sentAt")) or sent_at) > sent_at)
    ]
    if not replies:
        if sent_at and store.now() - sent_at > timedelta(days=days):
            who = sent.get("to_name") or to
            return Outcome(
                "blocked",
                waiting,
                error=f"No reply from {who} in {days} days. Send the follow-up, or close this.",
            )
        return Outcome("waiting", waiting, check_after=REPLY_CHECK_EVERY)
    replies.sort(key=lambda r: str(r.get("sentAt") or ""))
    reply = replies[0]
    text = _reply_text(str(reply.get("text") or ""))[:MAX_REPLY_CHARS]
    suspicious = looks_like_injection_attempt(text)
    result = {
        **waiting,
        "reply_message_id": reply.get("messageId"),
        "from": sent.get("to_name") or to,
        "subject": str(reply.get("subject") or "")[:200],
        "received_at": store.iso(reply.get("sentAt")),
        "text_untrusted": text,
        "suspected_injection": suspicious,
    }
    if suspicious:
        store.record_event(
            ctx.db,
            ctx.user_id,
            ctx.goal["id"],
            "security.untrusted_instructions",
            f"A reply from {to} contains instructions aimed at an assistant; they were treated "
            "as text.",
            {"message_id": reply.get("messageId")},
            dedupe_key=f"security.injection:{reply.get('messageId')}",
        )
    return Outcome("completed", result, {"verified": True, "how": "Reply is in your mail"})


_BOUNCE_SENDER = re.compile(r"mailer-daemon|postmaster|mail delivery", re.IGNORECASE)
_BOUNCE_SUBJECT = re.compile(
    r"undeliver|delivery (status notification|failure|has failed)|returned (mail|to sender)|"
    r"failure notice|could not be delivered|not delivered",
    re.IGNORECASE,
)
_BOUNCE_REASON = re.compile(
    r"\b[45]\d\d[ -][245]\.\d{1,3}\.\d{1,3}\b.{0,160}|\b55\d\b.{0,160}", re.S
)


def _bounce_for(
    rows: list[dict[str, Any]], to: str, message_id: str | None, sent_at: Any
) -> str | None:
    """A delivery-failure notice about this email: a message from the mail system, after the
    send, that names the recipient (or our Message-ID). Returns the server's reason, short."""
    for row in rows:
        when = store.parse_time(row.get("sentAt"))
        if sent_at and when and when < sent_at:
            continue
        sender, subject = str(row.get("from") or ""), str(row.get("subject") or "")
        if not (_BOUNCE_SENDER.search(sender) or _BOUNCE_SUBJECT.search(subject)):
            continue
        text = str(row.get("text") or "")
        if to not in text.lower() and not (message_id and message_id in text):
            continue
        found = _BOUNCE_REASON.search(text)
        reason = " ".join((found.group(0) if found else subject or "delivery failed").split())
        # Keep the server's code and reason; drop the boilerplate that follows it.
        reason = re.split(r";\s*(if you|please)|\s+Txn\b|\s+\(in reply to", reason, flags=re.I)[0]
        return reason.strip()[:200]
    return None


_QUOTE_START = re.compile(r"^(on .{4,200} wrote:|-{2,} ?original message|from: )", re.IGNORECASE)


def _reply_text(text: str) -> str:
    """Their new words only: stop at the quoted email below a reply."""
    kept = []
    for line in text.splitlines():
        if line.lstrip().startswith(">") or _QUOTE_START.match(line.strip()):
            break
        kept.append(line)
    return "\n".join(kept).strip() or text.strip()


# --- reply.await (tier 0, waits) --------------------------------------------------------------


def _await_reply(ctx: Context, data: dict[str, Any]) -> Outcome:
    sent = data.get("after")
    if isinstance(sent, dict) and sent.get("channel") == "email" and sent.get("to"):
        return _await_email_reply(ctx, sent, int(data.get("days") or REPLY_WAIT_DEFAULT_DAYS))
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
        email = reply.get("channel") == "email"
        source_type = "email" if email else "open_media_message"
        ref_prefix = "email" if email else "open_media:message"
        fact = knowledge.record(
            ctx.db,
            ctx.user_id,
            subject_type="person",
            subject_key=str(reply.get("from") or "unknown"),
            predicate="replied",
            value=str(reply.get("text_untrusted") or ""),
            kind="external_claim",
            source_type=source_type,
            source_ref=f"{ref_prefix}:{reply['reply_message_id']}",
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
                source_type=source_type,
                source_ref=f"{ref_prefix}:{reply['reply_message_id']}",
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
                f"From {who if '@' in who else '@' + who}'s reply: "
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
            "email.prepare",
            "Prepare the email",
            1,
            "Hold an email for review; nothing is sent (input: to, subject, body, to_name, "
            "organization, why, evidence, follow_up).",
            ("to", "subject", "body"),
            _prepare_email,
        ),
        Capability(
            "email.send",
            "Send the email",
            2,
            "Send a prepared email from the person's own mailbox after they approve exactly it "
            "(input: draft = $steps.<prepare>).",
            ("draft",),
            _send_email,
            scope=_email_scope,
            describe=_email_describe,
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
