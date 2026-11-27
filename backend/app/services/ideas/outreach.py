"""Customer-discovery messages that people are glad to get, and how they reach Messages.

The rules come from the evidence on founder-led outreach (docs/CUSTOMER_OUTREACH.md):
short (40–90 words), plain words, one true and specific reason for writing to this person,
honest about who is writing and that it is early and not a pitch, one low-pressure question,
an easy way to say no, at most two follow-ups. ``check`` enforces what code can check; the
writing prompt and the agent skill carry the rest.

A prepared message becomes a goal (ADR 0020): it waits in Messages for the founder's yes
(on screen or by voice), is sent from their own mailbox or Open Media account, and any reply
comes back to the goal, where Manifest reports it in the person's own words.
"""

from __future__ import annotations

import re
from typing import Any

from app.utils.logger import logger

MIN_WORDS = 25
TARGET_WORDS = (40, 90)
MAX_WORDS = 150
MAX_SUBJECT_WORDS = 8
MIN_FOLLOW_UP_WORDS = 8
MAX_FOLLOW_UP_WORDS = 70
FOLLOW_UP_DAYS = 5

RULES = """How to write it (each rule is from the outreach evidence; follow all of them):
- 40 to 90 words; short sentences and plain words a 12-year-old would follow; plain text, no \
links unless they asked, no images, no emoji, at most one exclamation mark.
- Subject: 2 to 6 plain words about their world ("Question about your onboarding"). Never \
"Re:", "Fwd:", a question, a number or a pitch.
- First line: the one specific, true reason you're writing to this person, taken from the \
evidence (their post, their job listing, their product page), with no flattery. Never "I hope \
this finds you well" or "I came across your profile".
- Say who is writing and what they're exploring in one honest sentence, and that it's early \
and not a sales pitch. Never claim a relationship, past contact, a mutual connection, traction, \
customers or features that aren't in the evidence.
- One question about how they handle the problem today (their past and present, not whether \
they'd buy). Offer a short call only as an option ("a one-line reply is plenty").
- End with an easy out ("If this isn't relevant, just say so and I won't follow up.") and the \
sender's first name.
- Never: urgency, discounts, "quick call", "touch base", "circle back", "game-changer", \
"revolutionary", "cutting-edge", "synergy", "leverage", "free", "guarantee", ALL CAPS, or \
anything personal that isn't about their work.
- A follow-up (for a week later, same thread) is 1 to 3 sentences, adds something new or a \
sharper question, and offers to stop. Never "just bumping this"."""

OPT_OUT = "If this isn't relevant to you, just say so and I won't follow up."

_PLACEHOLDER = re.compile(
    r"\[[^\]\n]{1,40}\]|\{\{|\}\}|<(?:name|company|first ?name)>|lorem ipsum", re.I
)
_FAKE_FAMILIARITY = re.compile(
    r"\b(as (we|I) (discussed|mentioned)|following up on our|great (to meet|meeting) you|"
    r"you might remember|our (last|recent) (call|chat|conversation)|per our conversation|"
    r"thanks for (taking|your) (the )?(call|time) (earlier|yesterday|last))\b",
    re.I,
)
_SALESY = [
    "hope this email finds you well",
    "hope this finds you well",
    "hope you're doing well",
    "hope you are doing well",
    "i came across your profile",
    "quick call",
    "touch base",
    "circle back",
    "circling back",
    "just bumping",
    "game-changer",
    "game changer",
    "revolutionary",
    "cutting-edge",
    "cutting edge",
    "synergy",
    "best-in-class",
    "world-class",
    "limited time",
    "act now",
    "don't miss",
    "guarantee",
    "100% free",
    "risk-free",
    "10x",
]
_OPT_OUT_HINT = re.compile(
    r"(won'?t (follow up|write|email|reach out|bother)|not (relevant|a fit|for you)|"
    r"no worries if not|just say so|ignore this|stop (writing|emailing))",
    re.I,
)


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9'’-]+", text or ""))


def _problems(subject: str, body: str, count: int, follow_up: bool = False) -> list[str]:
    problems = []
    text = f"{subject}\n{body}"
    if _PLACEHOLDER.search(text):
        problems.append("It still has a placeholder like [Name]; fill it in.")
    if not follow_up and re.match(r"\s*(re|fwd?|fw)\s*:", subject or "", re.I):
        problems.append("The subject pretends to be a reply or forward.")
    if not follow_up and _FAKE_FAMILIARITY.search(text):
        problems.append("It implies past contact that didn't happen.")
    if follow_up:  # 1 to 3 sentences, never a bare "bumping this"
        if count < MIN_FOLLOW_UP_WORDS:
            problems.append(f"Say something new in the follow-up ({count} words).")
        if count > MAX_FOLLOW_UP_WORDS:
            problems.append(f"Keep the follow-up short ({count} words).")
    elif count < MIN_WORDS:
        problems.append(f"It's too short to make sense ({count} words).")
    if not follow_up and count > MAX_WORDS:
        problems.append(f"It's too long ({count} words); keep it under {TARGET_WORDS[1]}.")
    salesy = [p for p in _SALESY if p in text.lower()]
    if salesy:
        problems.append(f"It sounds like a sales email ({', '.join(salesy[:3])}).")
    return problems


def _notes(subject: str, body: str, count: int) -> list[str]:
    notes = []
    if re.search(r"\b[A-Z]{5,}\b", body) and not re.search(r"\b(API|SaaS|CRM|HIPAA|GDPR)\b", body):
        notes.append("Avoid all-caps words.")
    if count > TARGET_WORDS[1]:
        notes.append(f"{count} words; under {TARGET_WORDS[1]} reads better.")
    if words(subject) > MAX_SUBJECT_WORDS:
        notes.append("Shorten the subject to a few plain words.")
    if body.count("?") > 2:
        notes.append("Ask one question, not several.")
    if len(re.findall(r"https?://", body)) > 1:
        notes.append("Drop the extra links; plain text gets more replies.")
    if body.count("!") > 1:
        notes.append("Fewer exclamation marks.")
    return notes


def message_words(body: str) -> int:
    """Words in the message itself: not the easy-out line or a short sign-off."""
    lines = [ln for ln in body.strip().splitlines() if not _OPT_OUT_HINT.search(ln)]
    while lines and (not lines[-1].strip() or words(lines[-1]) <= 5):
        lines.pop()
    return words("\n".join(lines))


def check(subject: str, body: str, *, follow_up: bool = False) -> tuple[list[str], list[str]]:
    """(problems that make it unsendable, notes for the founder)."""
    count = message_words(body)
    return _problems(subject, body, count, follow_up), _notes(subject, body, count)


def finish(body: str, sender_name: str | None) -> str:
    """Add what every message needs and is easy to forget: an easy way to say no (above any
    sign-off), and who it's from. Never rewrites what was written."""
    lines = body.strip().splitlines()
    first = (sender_name or "").split()[0].lower() if sender_name else ""
    # A sign-off: the last short lines, starting at the one with their name.
    sign_at = len(lines)
    if first:
        for i in range(len(lines) - 1, max(len(lines) - 4, -1), -1):
            if first in lines[i].lower() and words(lines[i]) <= 5:
                sign_at = i
                break
    text_part = "\n".join(lines[:sign_at]).rstrip()
    sign_off = "\n".join(lines[sign_at:]).strip()
    if not _OPT_OUT_HINT.search(text_part):
        text_part = f"{text_part}\n\n{OPT_OUT}"
    if not sign_off and sender_name:
        sign_off = sender_name
    return f"{text_part}\n\n{sign_off}".strip() if sign_off else text_part


def sender_name(db: Any, user_id: str) -> str | None:
    try:
        rows = (
            db.table("users")
            .select("first_name, last_name, username")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
            .data
            or []
        )
    except Exception as exc:  # a missing name never stops drafting
        logger.info("sender name unavailable", extra={"exception.type": type(exc).__name__})
        return None
    row = rows[0] if rows else {}
    name = " ".join(p for p in (row.get("first_name"), row.get("last_name")) if p).strip()
    return name or (row.get("username") or None)


# ---- into Messages -------------------------------------------------------------------------


def _goal_title(draft: dict[str, Any]) -> str:
    who = draft.get("to_name") or draft.get("prospect_name") or draft.get("to")
    org = draft.get("prospect_name")
    at = f" at {org}" if org and org != who else ""
    verb = "Message" if draft.get("channel") == "open_media" else "Email"
    return f"{verb} {who}{at}"


def _plan(draft: dict[str, Any], prospect: dict[str, Any], idea: dict[str, Any]) -> list[dict]:
    from app.services.goals import engine

    purpose = f"Customer discovery for {idea.get('title') or 'your idea'}"
    if draft.get("channel") == "open_media":
        return engine.outreach_plan(
            draft["to"], draft["body"], purpose=purpose, wait_days=FOLLOW_UP_DAYS
        )
    evidence = [e for e in prospect.get("need_evidence") or [] if e.get("url")][:3]
    return engine.email_outreach_plan(
        to=draft["to"],
        to_name=draft.get("to_name"),
        organization=prospect.get("name") if prospect.get("kind") != "person" else None,
        subject=draft["subject"],
        body=draft["body"],
        why=prospect.get("why_fit") or "",
        evidence=evidence,
        follow_up=draft.get("follow_up"),
        purpose=purpose,
        wait_days=FOLLOW_UP_DAYS,
    )


def queue(
    db: Any,
    user_id: str,
    idea: dict[str, Any],
    state: dict[str, Any],
    prospect_ids: set[str] | None = None,
) -> dict[str, list[str]]:
    """Put prepared messages in Messages, each waiting for the founder's yes. Nothing is sent.
    A message already waiting is updated if its text changed; one already sent is left alone."""
    from app.services.goals import engine

    prospects = {p["id"]: p for p in state.get("prospects") or []}
    out: dict[str, list[str]] = {"queued": [], "updated": [], "needs_recipient": [], "sent": []}
    for draft in state.get("outreach") or []:
        if prospect_ids is not None and draft["prospect_id"] not in prospect_ids:
            continue
        name = draft.get("to_name") or draft["prospect_name"]
        if not draft.get("to"):
            out["needs_recipient"].append(draft["prospect_name"])
            continue
        prospect = prospects.get(draft["prospect_id"]) or {"name": draft["prospect_name"]}
        try:
            goal = engine.create_goal(
                db,
                user_id,
                title=_goal_title(draft),
                steps=_plan(draft, prospect, idea),
                desired_outcome=f"Hear from {name} how they handle this today.",
                success_criteria=[f"{name} replies"],
                idea_id=idea.get("idea_id"),
                source={
                    "kind": "customer_discovery",
                    "prospect_id": draft["prospect_id"],
                    "via": draft.get("origin") or "agent",
                },
            )
        except engine.GoalError as exc:
            out["needs_recipient"].append(f"{draft['prospect_name']} ({exc})")
            continue
        goal_id = goal["goal"]["id"]
        draft["goal_id"] = goal_id
        if goal.get("existing"):
            if _waiting_text(goal) not in (None, draft["body"]):
                try:
                    engine.edit_draft(
                        db, user_id, goal_id, body=draft["body"], subject=draft.get("subject")
                    )
                    out["updated"].append(name)
                except engine.GoalError:
                    out["sent"].append(name)
            elif _waiting_text(goal) is None:
                out["sent"].append(name)
        else:
            out["queued"].append(name)
    return out


def _waiting_text(goal: dict[str, Any]) -> str | None:
    """The body of the message this goal still holds for approval, if any."""
    for approval in goal.get("approvals") or []:
        if approval.get("status") == "pending":
            return (approval.get("scope") or {}).get("body")
    return None


def queued_summary(result: dict[str, list[str]]) -> list[str]:
    lines = []
    if result["queued"] or result["updated"]:
        n = len(result["queued"]) + len(result["updated"])
        lines.append(
            f"{n} message{'s' if n != 1 else ''} waiting in Messages for your OK; nothing is "
            "sent until you say yes."
        )
    if result["needs_recipient"]:
        lines.append(
            "No verified address yet for "
            + ", ".join(result["needs_recipient"])
            + "; give me their email (or Open Media handle) and I'll put those in Messages too."
        )
    if result["sent"]:
        lines.append(f"Already sent, left as is: {', '.join(result['sent'])}.")
    return lines
