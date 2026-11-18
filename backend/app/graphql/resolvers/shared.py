"""Helpers shared by several GraphQL resolver modules."""

import os
import threading
from datetime import datetime
from typing import Any

import strawberry
from app.auth.current_user import get_current_user_id
from app.services.shared import cache as cache_service

_AI_CACHE_TTL_SECONDS = int(os.getenv("AI_INTERACTIVE_CACHE_TTL_SECONDS", "300"))


_ai_request_lock = threading.Lock()


def _cache_key(namespace: str, value: str) -> str:
    return f"{namespace}:{value.strip().lower()}"


def _get_ai_cache(namespace: str, value: str) -> Any:
    # Backed by Redis when REDIS_URL is set (shared across workers), else an
    # in-process TTL map — identical behaviour to before. See cache_service.
    return cache_service.cache_get(_cache_key(namespace, value))


def _set_ai_cache(namespace: str, value: str, result: Any) -> None:
    cache_service.cache_set(_cache_key(namespace, value), result, _AI_CACHE_TTL_SECONDS)


def _display_name(record: dict | None, default: str = "User") -> str:
    if not record:
        return default

    first_name = (record.get("first_name") or "").strip()
    last_name = (record.get("last_name") or "").strip()
    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        return full_name

    username = (record.get("username") or "").strip()
    if username:
        return username

    email = (record.get("email") or "").strip()
    if email:
        return email.split("@", 1)[0]

    return default


def _coerce_datetime(value: object | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return datetime.utcnow()
    return datetime.utcnow()


def _require_full_account(db, request) -> str:
    """Raise if the current user is a try-before-signup guest (blocked for social/invest/publish)."""
    from app.services.identity.guest_workspace import fetch_user_is_guest

    user_id = get_current_user_id(request)
    if fetch_user_is_guest(db, user_id):
        raise Exception("Create an account to use this feature.")
    return user_id


def _request_ip(info: strawberry.Info) -> str | None:
    request = info.context.get("request")
    client = getattr(request, "client", None) if request else None
    return getattr(client, "host", None) if client else None


def _user_agent(info: strawberry.Info) -> str | None:
    """Best-effort User-Agent extraction for the canonical audit row."""
    request = info.context.get("request")
    if not request:
        return None
    headers = getattr(request, "headers", None)
    if not headers:
        return None
    try:
        ua = headers.get("user-agent")
    except Exception:
        return None
    return (ua or "")[:500] or None
