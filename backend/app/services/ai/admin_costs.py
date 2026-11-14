"""Cross-user cost + agent-run analytics for the admin dashboard.

Read-only. Reuses the same tables the per-user dashboard already reads
(`agent_runs`, `agent_cost_events`, `production_test_runs`) and rolls
them up across all users.

Permission gate is enforced one level up at the GraphQL layer
(`admin.cost.read` in FIELD_PERMISSIONS). This module assumes the
caller has already passed that check — do NOT call from a public
context without re-gating.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import logger

# Conservative caps so an admin dashboard request can't accidentally
# scan the entire history.
DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 180
EVENT_SCAN_CAP = 50_000
RUN_SCAN_CAP = 5_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _coerce_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _day_key(dt: datetime) -> str:
    return dt.date().isoformat()


def _resolve_window_days(days: int | None) -> int:
    if days is None:
        return DEFAULT_WINDOW_DAYS
    try:
        d = int(days)
    except (TypeError, ValueError):
        return DEFAULT_WINDOW_DAYS
    return max(1, min(MAX_WINDOW_DAYS, d))


# ---------- public API ----------


def build_admin_cost_overview(*, db, window_days: int | None = None) -> dict[str, Any]:
    """One-shot payload for the admin /admin/cost dashboard."""
    days = _resolve_window_days(window_days)
    now = _now()
    window_start = now - timedelta(days=days)
    window_start_iso = _iso(window_start)

    events = _scan_cost_events(db=db, since_iso=window_start_iso)
    runs = _scan_agent_runs(db=db, since_iso=window_start_iso)
    failed_runs_count = sum(1 for r in runs if str(r.get("status")) == "failed")
    user_emails = _fetch_user_emails(db=db, user_ids=[str(r.get("user_id")) for r in runs])

    # Daily series.
    by_day: dict[str, dict[str, float]] = {}
    for e in events:
        dt = _coerce_dt(e.get("created_at"))
        if dt is None:
            continue
        key = _day_key(dt)
        slot = by_day.setdefault(
            key, {"date": key, "billable_usd": 0.0, "model_cost_usd": 0.0, "event_count": 0}
        )
        slot["billable_usd"] += float(e.get("billable_cost_usd") or 0)
        slot["model_cost_usd"] += float(e.get("model_cost_usd") or 0)
        slot["event_count"] += 1
    daily_series = sorted(by_day.values(), key=lambda r: r["date"])

    # Per-user, per-kind, per-model.
    by_user: dict[str, dict[str, Any]] = {}
    by_kind: dict[str, float] = {}
    by_model: dict[str, float] = {}
    total_billable = 0.0
    total_model = 0.0
    total_input = 0
    total_output = 0
    for e in events:
        billable = float(e.get("billable_cost_usd") or 0)
        total_billable += billable
        total_model += float(e.get("model_cost_usd") or 0)
        total_input += int(e.get("input_tokens") or 0)
        total_output += int(e.get("output_tokens") or 0)

        uid = str(e.get("user_id") or "unknown")
        user_slot = by_user.setdefault(
            uid,
            {
                "user_id": uid,
                "email": user_emails.get(uid),
                "billable_usd": 0.0,
                "event_count": 0,
            },
        )
        user_slot["billable_usd"] = round(user_slot["billable_usd"] + billable, 6)
        user_slot["event_count"] += 1

        kind = str(e.get("agent_kind") or "unknown")
        by_kind[kind] = round(by_kind.get(kind, 0.0) + billable, 6)
        model = str(e.get("model") or "unknown")
        by_model[model] = round(by_model.get(model, 0.0) + billable, 6)

    top_users = sorted(by_user.values(), key=lambda u: u["billable_usd"], reverse=True)[:20]

    # Expensive runs (single-run spend ≥ $1 OR top 10 by spend).
    runs_with_cost = [
        {
            "id": str(r.get("id")),
            "user_id": str(r.get("user_id")),
            "user_email": user_emails.get(str(r.get("user_id"))),
            "agent_kind": str(r.get("agent_kind") or "unknown"),
            "status": str(r.get("status") or "unknown"),
            "billable_usd": float(r.get("total_billable_cost_usd") or 0),
            "input_tokens": int(r.get("total_input_tokens") or 0),
            "output_tokens": int(r.get("total_output_tokens") or 0),
            "started_at": (_coerce_dt(r.get("started_at")) or now).isoformat(),
            "completed_at": (
                _coerce_dt(r.get("completed_at")).isoformat()
                if _coerce_dt(r.get("completed_at"))
                else None
            ),
        }
        for r in runs
    ]
    sorted_runs = sorted(runs_with_cost, key=lambda r: r["billable_usd"], reverse=True)
    expensive_runs = [r for r in sorted_runs if r["billable_usd"] >= 1.0]
    if len(expensive_runs) < 10:
        expensive_runs = sorted_runs[:10]

    # Burn rate: trailing-7-day average per day.
    seven_days_ago = now - timedelta(days=7)
    trailing_7d_billable = sum(
        float(e.get("billable_cost_usd") or 0)
        for e in events
        if (_coerce_dt(e.get("created_at")) or now) >= seven_days_ago
    )
    burn_rate_per_day = trailing_7d_billable / 7.0

    # Month projection.
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_to_date_billable = sum(
        float(e.get("billable_cost_usd") or 0)
        for e in events
        if (_coerce_dt(e.get("created_at")) or now) >= month_start
    )
    if now.month == 12:
        next_month = now.replace(
            year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    else:
        next_month = now.replace(
            month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    days_remaining = max(0, (next_month - now).days)
    projected_month_billable = month_to_date_billable + burn_rate_per_day * days_remaining

    return {
        "window_days": days,
        "window_start": window_start_iso,
        "generated_at": _iso(now),
        "totals": {
            "total_billable_usd": round(total_billable, 6),
            "total_model_cost_usd": round(total_model, 6),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_runs": len(runs),
            "failed_runs": failed_runs_count,
            "active_users": len(by_user),
        },
        "burn_rate_per_day_usd": round(burn_rate_per_day, 6),
        "month_to_date_billable_usd": round(month_to_date_billable, 6),
        "projected_month_billable_usd": round(projected_month_billable, 6),
        "daily_series": daily_series,
        "top_users": top_users,
        "by_agent_kind": [{"label": k, "billable_usd": round(v, 6)} for k, v in by_kind.items()],
        "by_model": [{"label": k, "billable_usd": round(v, 6)} for k, v in by_model.items()],
        "expensive_runs": expensive_runs[:20],
    }


def list_recent_runs_cross_user(
    *,
    db,
    limit: int = 50,
    agent_kind: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Recent agent_runs across ALL users, with optional filters."""
    limit = max(1, min(int(limit or 50), 500))
    query = db.table("agent_runs").select("*").order("started_at", desc=True).limit(limit)
    if agent_kind:
        query = query.eq("agent_kind", agent_kind)
    if status:
        query = query.eq("status", status)
    response = query.execute()
    rows = list(response.data or [])
    emails = _fetch_user_emails(db=db, user_ids=[str(r.get("user_id")) for r in rows])
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["user_email"] = emails.get(str(d.get("user_id")))
        out.append(d)
    return out


def build_production_test_health(*, db, hours: int = 24) -> dict[str, Any]:
    """Production-test pass/fail roll-up, wrapping production_test_service."""
    from app.services.operations import production_tests as pts

    return pts.get_failure_stats(db=db, hours=hours)


# ---------- internals ----------


def _scan_cost_events(*, db, since_iso: str) -> list[dict[str, Any]]:
    try:
        response = (
            db.table("agent_cost_events")
            .select("*")
            .gte("created_at", since_iso)
            .order("created_at", desc=True)
            .limit(EVENT_SCAN_CAP)
            .execute()
        )
        return list(response.data or [])
    except Exception as exc:
        logger.error("[admin_cost] cost_events scan failed: %s", exc)
        return []


def _scan_agent_runs(*, db, since_iso: str) -> list[dict[str, Any]]:
    try:
        response = (
            db.table("agent_runs")
            .select("*")
            .gte("started_at", since_iso)
            .order("started_at", desc=True)
            .limit(RUN_SCAN_CAP)
            .execute()
        )
        return list(response.data or [])
    except Exception as exc:
        logger.error("[admin_cost] agent_runs scan failed: %s", exc)
        return []


def _fetch_user_emails(*, db, user_ids: list[str]) -> dict[str, str | None]:
    """Look up email by user_id for display in admin tables."""
    unique = sorted({uid for uid in user_ids if uid and uid != "unknown"})
    if not unique:
        return {}
    try:
        response = db.table("users").select("user_id, email").in_("user_id", unique).execute()
        return {str(row.get("user_id")): row.get("email") for row in (response.data or [])}
    except Exception as exc:
        logger.debug("[admin_cost] user-email lookup failed (continuing): %s", exc)
        return {}
