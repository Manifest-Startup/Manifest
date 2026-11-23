"""Rows for goals, their tasks, approvals, facts and events (Supabase-style query API).

Every write that changes a task's or approval's state is a compare-and-swap on the state it
read (``cas_update``), so two workers, a retry and a webhook can't both move the same step.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

GOALS = "goals"
TASKS = "goal_tasks"
APPROVALS = "approval_requests"
FACTS = "knowledge_facts"
EVENTS = "goal_events"
GRANTS = "standing_authorizations"

_TIME_FIELDS = (
    "created_at",
    "updated_at",
    "expires_at",
    "decided_at",
    "next_check_at",
    "source_at",
    "revoked_at",
)


def now() -> datetime:
    return datetime.now(UTC)


def iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()
    return str(value)


def parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _clean(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for key in ("id", "user_id", "goal_id", "task_id", "idea_id", "superseded_by"):
        if out.get(key) is not None:
            out[key] = str(out[key])
    for key in _TIME_FIELDS:
        if key in out:
            out[key] = iso(out[key])
    return out


def _rows(data: Any) -> list[dict[str, Any]]:
    if not data:
        return []
    items = data if isinstance(data, list) else [data]
    return [r for r in (_clean(i) for i in items) if r]


def insert(db: Any, table: str, row: dict[str, Any]) -> dict[str, Any]:
    stamp = now().isoformat()
    full = {"id": str(uuid.uuid4()), "created_at": stamp, **row}
    if table in (GOALS, TASKS):
        full.setdefault("updated_at", stamp)
    saved = _rows(db.table(table).insert(full).execute().data)
    return saved[0] if saved else _clean(full) or full


def select(db: Any, table: str, *, order: str | None = None, **equals: Any) -> list[dict[str, Any]]:
    query = db.table(table).select("*")
    for column, value in equals.items():
        query = query.eq(column, value)
    if order:
        query = query.order(order)
    return _rows(query.execute().data)


def one(db: Any, table: str, **equals: Any) -> dict[str, Any] | None:
    found = select(db, table, **equals)
    return found[0] if found else None


def cas_update(
    db: Any, table: str, row_id: str, expect: dict[str, Any], changes: dict[str, Any]
) -> dict[str, Any] | None:
    """Apply ``changes`` only while the row still has the ``expect`` values; None if it moved."""
    if table in (GOALS, TASKS):
        changes = {**changes, "updated_at": now().isoformat()}
    query = db.table(table).update(changes).eq("id", row_id)
    for column, value in expect.items():
        query = query.eq(column, value)
    saved = _rows(query.execute().data)
    return saved[0] if saved else None


def record_event(
    db: Any,
    user_id: str,
    goal_id: str | None,
    event_type: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    *,
    dedupe_key: str | None = None,
) -> dict[str, Any] | None:
    """Append one event to the goal's timeline. With ``dedupe_key`` an event is written once."""
    if dedupe_key and select(db, EVENTS, user_id=user_id, dedupe_key=dedupe_key):
        return None
    row = {
        "user_id": user_id,
        "goal_id": goal_id,
        "type": event_type,
        "summary": summary[:500],
        "payload": payload or {},
        "dedupe_key": dedupe_key,
    }
    try:
        return insert(db, EVENTS, row)
    except Exception:  # unique (user_id, dedupe_key): a concurrent writer recorded it first
        if dedupe_key:
            return None
        raise
