"""
Optional Gemini / Veo video generation for pitch reels.
Requires GOOGLE_API_KEY and the google-genai package.

Concurrency: a module-level semaphore serialises all Veo API calls so that
only one video generation job runs at a time per server process.  This avoids
simultaneous requests hitting the 10 RPM preview-model quota.

Retry: transient 429 RATE_LIMIT errors are retried with exponential backoff
(max 3 attempts, 15 s / 30 s / 60 s waits).  Billing errors ("credits
depleted") are NOT retried — they will fail immediately with a clear log.
"""

from __future__ import annotations

import os
import random
import threading
import time
from pathlib import Path

from app.utils.logger import logger

# ── Serialisation ────────────────────────────────────────────────────────────
# Allow only one Veo generation at a time.  The API allows 10 concurrent
# requests for preview models, but keeping concurrency at 1 is safest for a
# low-traffic app and prevents burst 429s when multiple ideas are published
# within seconds of each other.
_VEO_SEMAPHORE = threading.Semaphore(1)

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 15.0  # seconds
_RETRY_MAX_DELAY = 60.0  # seconds


def _is_billing_error(exc_str: str) -> bool:
    """Return True if the error is a billing/quota-exhausted error (not retriable)."""
    billing_phrases = [
        "prepayment credits are depleted",
        "credits are depleted",
        "billing",
        "payment",
    ]
    return any(phrase in exc_str.lower() for phrase in billing_phrases)


def _is_rate_limit_error(exc_str: str) -> bool:
    """Return True if the 429 is a transient rate-limit (retriable)."""
    return "429" in exc_str or "resource_exhausted" in exc_str.lower()


def _build_pitch_prompt(idea_title: str, idea_description: str) -> str:
    title = (idea_title or "").strip() or "A startup idea"
    body = (idea_description or "").strip()
    if body:
        return (
            f"Cinematic vertical 9:16 startup pitch teaser for: {title}. "
            f"Professional, modern, no on-screen text. Concept: {body[:1200]}"
        )
    return (
        f"Cinematic vertical 9:16 abstract professional tech visuals suggesting innovation "
        f"for a startup called: {title}. No readable text."
    )


def _attempt_generate(client: object, model: str, prompt: str) -> object | None:
    """
    Call generate_videos once.  Returns the operation object on success,
    raises on any error (caller handles retry vs abort).
    """
    return client.models.generate_videos(model=model, prompt=prompt)  # type: ignore[attr-defined]


def generate_pitch_video_to_path(  # noqa: C901
    idea_title: str,
    idea_description: str,
    output_path: Path,
    *,
    timeout_seconds: int = 600,
    poll_interval_seconds: float = 8.0,
) -> bool:
    """
    Generate a short video file using the Gemini API (Veo) when configured.
    Returns True if output_path was written successfully.

    Uses the module-level semaphore so only one generation runs at a time.
    Retries up to _MAX_RETRIES times on transient 429 rate-limit errors.
    """
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        logger.warning("[GeminiVideo] GOOGLE_API_KEY not set; skipping video generation.")
        return False

    model = os.getenv("GEMINI_VIDEO_MODEL", "veo-3.1-generate-preview").strip()

    try:
        from google import genai  # type: ignore[import-untyped]
    except ImportError:
        logger.error("[GeminiVideo] google-genai is not installed.")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = _build_pitch_prompt(idea_title, idea_description)

    try:
        client = genai.Client(api_key=api_key)
    except Exception as exc:
        logger.error("[GeminiVideo] Failed to create client: %s", exc)
        return False

    logger.info("[GeminiVideo] Waiting for semaphore (model=%s)…", model)
    with _VEO_SEMAPHORE:
        logger.info("[GeminiVideo] Semaphore acquired — starting Veo request (model=%s)", model)
        operation = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                operation = _attempt_generate(client, model, prompt)
                break
            except Exception as exc:
                exc_str = str(exc)
                if _is_billing_error(exc_str):
                    logger.error(
                        "[GeminiVideo] Billing error — credits exhausted. Add funds at "
                        "https://ai.studio/projects. Error: %s",
                        exc_str,
                    )
                    return False
                if _is_rate_limit_error(exc_str) and attempt < _MAX_RETRIES:
                    delay = min(_RETRY_BASE_DELAY * (2 ** (attempt - 1)), _RETRY_MAX_DELAY)
                    jitter = random.uniform(0, delay * 0.2)
                    wait = delay + jitter
                    logger.warning(
                        "[GeminiVideo] 429 rate-limit on attempt %d/%d — retrying in %.1f s. Error: %s",
                        attempt,
                        _MAX_RETRIES,
                        wait,
                        exc_str[:200],
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "[GeminiVideo] generate_videos failed (attempt %d/%d): %s",
                        attempt,
                        _MAX_RETRIES,
                        exc_str,
                    )
                    return False

        if operation is None:
            logger.error("[GeminiVideo] All %d attempts failed.", _MAX_RETRIES)
            return False

        deadline = time.monotonic() + timeout_seconds
        try:
            while not operation.done:
                if time.monotonic() > deadline:
                    logger.error("[GeminiVideo] Timed out after %s seconds", timeout_seconds)
                    return False
                time.sleep(poll_interval_seconds)
                try:
                    operation = client.operations.get(operation)
                except Exception as exc:
                    logger.error("[GeminiVideo] operations.get failed: %s", exc)
                    return False
        except AttributeError:
            logger.error(
                "[GeminiVideo] Operation object missing expected API; check google-genai version."
            )
            return False

    try:
        response = operation.response
        generated = response.generated_videos[0]
        video_file = generated.video
        client.files.download(file=video_file)
        if hasattr(video_file, "save"):
            video_file.save(str(output_path))
        else:
            logger.error("[GeminiVideo] Unexpected video payload type from API.")
            return False
    except Exception as exc:
        logger.error("[GeminiVideo] Failed to save generated video: %s", exc)
        return False

    if not output_path.is_file() or output_path.stat().st_size < 32:
        logger.error("[GeminiVideo] Output file missing or too small.")
        return False

    logger.info(
        "[GeminiVideo] Wrote video to %s (%d bytes)", output_path, output_path.stat().st_size
    )
    return True
