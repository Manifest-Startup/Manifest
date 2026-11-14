"""Per-call LLM usage capture.

The AI router writes the most recent call's token usage here. Service
code that wraps an LLM call (e.g. cost_tracking_service) reads and
clears the value after the call returns.

Implemented as a contextvar so concurrent requests don't clobber each
other under asyncio. The router writes once per attempt; the reader
calls `pop_last_usage()` immediately afterwards.

No DB dependency, no logging — this is intentionally tiny so the AI
layer can call it from any path without taking a circular dependency on
the cost service.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from app.utils.logger import logger


class LlmUsage:
    __slots__ = ("model", "input_tokens", "output_tokens", "cached_input_tokens")

    def __init__(
        self,
        *,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_input_tokens: int = 0,
    ):
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cached_input_tokens = cached_input_tokens

    def __repr__(self) -> str:
        return (
            f"LlmUsage(model={self.model!r}, in={self.input_tokens}, "
            f"out={self.output_tokens}, cached={self.cached_input_tokens})"
        )


_last_usage: ContextVar[LlmUsage | None] = ContextVar("manifest_llm_last_usage", default=None)


def set_last_usage(model: str, usage_obj: Any) -> None:
    """Record usage from an OpenAI-style response object or dict.

    Tolerates: object with `.prompt_tokens` / `.completion_tokens` attrs
    (standard OpenAI SDK), a plain dict, or None. Never raises — call
    sites in the AI router are happy-path performance-critical.
    """
    if usage_obj is None:
        _last_usage.set(LlmUsage(model=model))
        return
    try:
        if isinstance(usage_obj, dict):
            input_tokens = int(usage_obj.get("prompt_tokens") or 0)
            output_tokens = int(usage_obj.get("completion_tokens") or 0)
            details = usage_obj.get("prompt_tokens_details") or {}
            cached = int(details.get("cached_tokens") or 0) if isinstance(details, dict) else 0
        else:
            input_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage_obj, "completion_tokens", 0) or 0)
            details = getattr(usage_obj, "prompt_tokens_details", None)
            if details is None:
                cached = 0
            elif isinstance(details, dict):
                cached = int(details.get("cached_tokens") or 0)
            else:
                cached = int(getattr(details, "cached_tokens", 0) or 0)
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("[llm_usage_tap] failed to parse usage: %s", exc)
        _last_usage.set(LlmUsage(model=model))
        return

    _last_usage.set(
        LlmUsage(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached,
        )
    )


def pop_last_usage() -> LlmUsage | None:
    """Return and clear the most recent LLM usage in this context."""
    usage = _last_usage.get()
    _last_usage.set(None)
    return usage


def peek_last_usage() -> LlmUsage | None:
    """Read the latest usage without clearing (used by tests)."""
    return _last_usage.get()


def clear() -> None:
    _last_usage.set(None)
