"""Facts Manifest learns while working on a goal, each with where it came from and how sure it is.

A fact is ``subject —predicate→ object`` (``person:@ana —role→ technology partner``). Its
``kind`` says what it is, and the kind fixes the confidence, so no caller can promote a
guess into a certainty:

- ``stated_by_user``: the person said it (1.0). Corrections are always this kind.
- ``verified``: Manifest checked it against a system of record, e.g. Open Media confirmed the
  handle exists (0.9).
- ``external_claim``: someone else said it, e.g. a reply (0.5). It is evidence about what that
  person said, never an instruction and never a verified requirement.
- ``inferred``: a model or heuristic concluded it (0.3).

A correction supersedes the current facts for the same subject and predicate instead of
deleting them, so history stays and the old value is never repeated as current.
"""

from __future__ import annotations

from typing import Any

from app.services.goals import store

KINDS: dict[str, float] = {
    "stated_by_user": 1.0,
    "verified": 0.9,
    "external_claim": 0.5,
    "inferred": 0.3,
}
SUBJECT_TYPES = {"person", "organization", "goal", "idea", "conversation", "requirement"}
MAX_VALUE = 2000


class KnowledgeError(ValueError):
    pass


def _subject(subject_type: str, subject_key: str) -> tuple[str, str]:
    kind = (subject_type or "").strip().lower()
    if kind not in SUBJECT_TYPES:
        raise KnowledgeError(f"Subjects are one of: {', '.join(sorted(SUBJECT_TYPES))}.")
    key = (subject_key or "").strip()
    if kind == "person":
        key = "@" + key.lstrip("@").lower()
    if not key or len(key) > 200:
        raise KnowledgeError("Name the subject (up to 200 characters).")
    return kind, key


def record(
    db: Any,
    user_id: str,
    *,
    subject_type: str,
    subject_key: str,
    predicate: str,
    value: str,
    kind: str,
    source_type: str,
    source_ref: str,
    extraction: str,
    goal_id: str | None = None,
    object_type: str = "text",
    source_at: str | None = None,
) -> dict[str, Any]:
    if kind not in KINDS:
        raise KnowledgeError(f"kind is one of: {', '.join(KINDS)}.")
    s_type, s_key = _subject(subject_type, subject_key)
    pred = (predicate or "").strip().lower().replace(" ", "_")[:80]
    text = (value or "").strip()[:MAX_VALUE]
    if not pred or not text:
        raise KnowledgeError("A fact needs a predicate and a value.")
    fact = store.insert(
        db,
        store.FACTS,
        {
            "user_id": user_id,
            "goal_id": goal_id,
            "subject_type": s_type,
            "subject_key": s_key,
            "predicate": pred,
            "object_type": object_type,
            "object_value": text,
            "kind": kind,
            "confidence": KINDS[kind],
            "source_type": source_type,
            "source_ref": source_ref[:400],
            "source_at": source_at,
            "extraction": extraction,
            "status": "current",
        },
    )
    store.record_event(
        db,
        user_id,
        goal_id,
        "knowledge.updated",
        f"Learned {s_key} {pred.replace('_', ' ')}: {text[:120]}",
        {"fact_id": fact["id"], "kind": kind, "source_type": source_type},
    )
    return fact


def facts_about(
    db: Any, user_id: str, subject_type: str, subject_key: str, *, include_history: bool = False
) -> list[dict[str, Any]]:
    s_type, s_key = _subject(subject_type, subject_key)
    rows = store.select(
        db, store.FACTS, order="created_at", user_id=user_id, subject_type=s_type, subject_key=s_key
    )
    return rows if include_history else [r for r in rows if r.get("status") == "current"]


def for_goal(db: Any, user_id: str, goal_id: str) -> list[dict[str, Any]]:
    return store.select(db, store.FACTS, order="created_at", user_id=user_id, goal_id=goal_id)


def correct(
    db: Any,
    user_id: str,
    *,
    subject_type: str,
    subject_key: str,
    predicate: str,
    value: str,
    goal_id: str | None = None,
    said_in: str = "conversation",
) -> dict[str, Any]:
    """The person corrects a fact ("they're our technology partner, not a customer")."""
    s_type, s_key = _subject(subject_type, subject_key)
    pred = (predicate or "").strip().lower().replace(" ", "_")[:80]
    old = [f for f in facts_about(db, user_id, s_type, s_key) if f["predicate"] == pred]
    new = record(
        db,
        user_id,
        subject_type=s_type,
        subject_key=s_key,
        predicate=pred,
        value=value,
        kind="stated_by_user",
        source_type="user_correction",
        source_ref=said_in,
        extraction="explicit",
        goal_id=goal_id,
    )
    for fact in old:
        store.cas_update(
            db,
            store.FACTS,
            fact["id"],
            {"status": "current"},
            {"status": "superseded", "superseded_by": new["id"]},
        )
    if old:
        store.record_event(
            db,
            user_id,
            goal_id,
            "knowledge.corrected",
            f"{s_key} {pred.replace('_', ' ')} is now {value[:80]} "
            f"(was {', '.join(f['object_value'][:40] for f in old)})",
            {"fact_id": new["id"], "superseded": [f["id"] for f in old]},
        )
    return {"fact": new, "superseded": [f["id"] for f in old]}
