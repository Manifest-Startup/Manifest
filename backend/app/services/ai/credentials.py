"""Which OpenAI key an AI call should use (bring-your-own-key).

Resolution order for the current request or job:

1. a key pinned explicitly with :func:`use_openai_key` (background jobs);
2. the signed-in user's own key (looked up lazily, only when an AI call
   happens, then cached on the request);
3. the platform key ``OPENAI_API_KEY`` if the operator set one (local dev);
4. none: AI features raise :class:`MissingOpenAIKeyError`, whose message is
   shown to the user.

``AIRequestContextMiddleware`` binds each HTTP request so step 2 works from
anywhere in the call stack, including ``asyncio.to_thread`` workers.
"""

from __future__ import annotations

import contextvars
import os
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any

from app.utils.logger import logger

MISSING_KEY_MESSAGE = (
    "Add your OpenAI API key in Account → AI settings to use AI features. "
    "Manifest uses your own key, so you only pay OpenAI for what you generate."
)

_pinned_key: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "manifest_openai_key", default=None
)
_request: contextvars.ContextVar[Any] = contextvars.ContextVar("manifest_ai_request", default=None)
_UNSET = object()


class MissingOpenAIKeyError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(MISSING_KEY_MESSAGE)


def platform_key() -> str | None:
    return (os.getenv("OPENAI_API_KEY") or "").strip() or None


def _user_key_for_request(request: Any) -> str | None:
    cached = getattr(request.state, "openai_key", _UNSET)
    if cached is not _UNSET:
        return cached if isinstance(cached, str) else None
    key = None
    try:
        from app.services.ai.user_keys import load_user_key
        from app.utils.auth_utils import get_current_user_id_optional

        user_id = get_current_user_id_optional(request)
        if user_id:
            key = load_user_key(str(user_id))
    except Exception as exc:  # never break the request because the key lookup failed
        logger.warning("[byok] user key lookup failed: %s", type(exc).__name__)
    request.state.openai_key = key
    return key


def current_openai_key() -> str | None:
    pinned = _pinned_key.get()
    if pinned:
        return pinned
    request = _request.get()
    if request is not None:
        key = _user_key_for_request(request)
        if key:
            return key
    return platform_key()


def require_openai_key() -> str:
    key = current_openai_key()
    if not key:
        raise MissingOpenAIKeyError()
    return key


@contextmanager
def use_openai_key(key: str | None) -> Generator[None, None, None]:
    """Pin ``key`` for AI calls made inside the block (e.g. a background job)."""
    token = _pinned_key.set(key)
    try:
        yield
    finally:
        _pinned_key.reset(token)


def start_thread_with_current_key(target: Callable[..., Any], *args: Any) -> threading.Thread:
    """Start a daemon thread that keeps using the caller's OpenAI key.

    Plain threads do not inherit context variables, and the request may be
    finished by the time the thread runs, so the key is resolved now.
    """
    key = current_openai_key()

    def run() -> None:
        with use_openai_key(key):
            target(*args)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


class AIRequestContextMiddleware:
    """Pure ASGI middleware: make the current request visible to the AI layer."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        from starlette.requests import Request

        token = _request.set(Request(scope, receive))
        try:
            await self.app(scope, receive, send)
        finally:
            _request.reset(token)
