"""Manifest's natural voice on this Mac: Kokoro (`af_heart`) on the Apple GPU, through the bridge.

The browser hears (fast, no local models) and the person's agent answers; this module turns
each sentence of the answer into speech. On Apple silicon, Kokoro on MLX takes about 0.5 s
for a sentence (3–5× faster than real time on an 8 GB M1), so the voice sounds natural
without the wait. The CPU (ONNX) build ran at about real time there. The app plays the
audio itself; the app never uses the browser's flat voice for answers (they show as text until this is available).

    POST /speak       {"text": "One sentence."} → raw 16-bit mono PCM at 24 kHz
    POST /speak/warm  pages the model back in while the person is still talking

Extra: ``pip install 'manifest-mcp[natural-voice]'`` (mlx-audio + misaki; Apple silicon).

With a Cartesia API key (``manifest bridge --cartesia-key``), answers are spoken by Cartesia
Sonic in the voice of Pipecat's own demos instead, with Kokoro as the fallback.
"""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
import threading
from typing import Any

SAMPLE_RATE = 24000
DEFAULT_VOICE = "af_heart"  # Kokoro's warmest English voice
MODEL = "prince-canuma/Kokoro-82M"
SPEED = 1.05
MAX_CHARS = 600  # one sentence or two; longer text is cut


def supported() -> str | None:
    """None when the natural voice can run here, else why not."""
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return "the natural voice needs a Mac with Apple silicon"
    try:
        import misaki  # noqa: F401
        import mlx_audio.tts.utils  # noqa: F401
    except BaseException:
        return "install it with: pip install 'manifest-mcp[natural-voice]'"
    return None


# Waits between attempts to load the voice (a download can fail; the network comes back).
RETRY_SECONDS = (30, 120, 600, 1800)


def text_model_problem() -> str | None:
    """Kokoro's English needs spaCy's small English model. misaki would download it on the
    fly and *exit the process* when that fails (it did in a uv tool install), so check first
    and never let it try: the model ships with the `natural-voice` extra."""
    try:
        import en_core_web_sm  # noqa: F401
    except BaseException:
        return (
            "the English text model is missing: run the setup again "
            "(curl -fsSL https://manifeststartup.com/voice.sh | sh)"
        )
    return None


class Voice:
    """Kokoro on MLX, loaded in the background; one sentence at a time.

    Loading never takes the bridge down and never fails silently: every problem (even one
    that calls `exit`) is kept in `problem`, reported to `log`, and retried with backoff.
    """

    def __init__(self, voice: str = DEFAULT_VOICE, log: Any = None) -> None:
        self.voice = voice
        self.ready = False
        self.loading = False
        self.problem: str | None = None
        self.seconds_per_sentence: float | None = None
        self._model: Any = None
        self._lock = threading.Lock()  # MLX runs one synthesis at a time
        self._log = log or (lambda _line: None)

    @property
    def status(self) -> str:
        """ "ready", "loading", or what's wrong (for /health and the log)."""
        if self.ready:
            return "ready"
        return self.problem or "loading"

    def load(self) -> bool:
        """Download (first time, ~330 MB) and load the model, then speak once to warm it."""
        import time

        self.loading = True
        try:
            missing = text_model_problem()
            if missing:
                raise RuntimeError(missing)
            from mlx_audio.tts.utils import load_model

            self._model = load_model(MODEL)  # type: ignore[arg-type]  # a Hugging Face repo id
            if not self._pcm("Hi."):  # the first sentence also compiles the GPU kernels
                raise RuntimeError("the voice made no sound")
            started = time.monotonic()
            self._pcm("Hi, I'm here.")
            self.seconds_per_sentence = round(time.monotonic() - started, 2)
            self.ready, self.problem = True, None
            self._log(
                f"Natural voice ready: Kokoro {self.voice} ({self.seconds_per_sentence} s a sentence)."
            )
        except BaseException as exc:  # noqa: BLE001  (misaki can raise SystemExit)
            self.ready = False
            self.problem = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            self._log(
                f"Natural voice unavailable ({self.problem}); retrying. Answers show as text until it loads."
            )
        finally:
            self.loading = False
        return self.ready

    def load_forever(self) -> None:
        """Load, and if that fails, try again later (for the bridge's background thread)."""
        import time

        for wait in (0, *RETRY_SECONDS):
            time.sleep(wait)
            if self.load():
                return
            if self.problem and "text model is missing" in self.problem:
                return  # only a reinstall fixes this; it is reported in /health

    def _pcm(self, text: str) -> bytes:
        import numpy as np

        chunks: list[bytes] = []
        with self._lock:
            for result in self._model.generate(
                text=text, voice=self.voice, speed=SPEED, lang_code=self.voice[0]
            ):
                audio = np.asarray(result.audio, dtype=np.float32).reshape(-1)
                chunks.append((np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes())
        return b"".join(chunks)

    async def speak(self, text: str) -> bytes:
        text = " ".join(text.split())[:MAX_CHARS]
        if not (self.ready and text):
            return b""
        return await asyncio.to_thread(self._pcm, text)

    def warm(self) -> None:
        """Synthesize a word in the background so a swapped-out model is back in memory by
        the time the answer arrives (the person is still talking)."""
        if self.ready and not self._lock.locked():
            threading.Thread(target=self._pcm, args=("Okay.",), daemon=True).start()


# ---- Cartesia (the voice of Pipecat's own demos) ------------------------------------------

CARTESIA_URL = "https://api.cartesia.ai/tts/bytes"
CARTESIA_VERSION = "2026-08-14"
CARTESIA_MODEL = "sonic-3.6"
# The default voice of Pipecat's quickstart bot (docs.pipecat.ai/getting-started/quickstart).
PIPECAT_VOICE = "86e30c1d-714b-4074-a1f2-1cb6b552fb49"
KEYCHAIN_SERVICE = "manifest-cartesia"


def cartesia_key() -> str | None:
    """The person's Cartesia API key: CARTESIA_API_KEY, else the macOS Keychain."""
    key = os.environ.get("CARTESIA_API_KEY", "").strip()
    if key:
        return key
    if platform.system() != "Darwin":
        return None
    found = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
        capture_output=True,
        text=True,
    )
    if found.returncode != 0:
        return None
    return found.stdout.strip() or None


def save_cartesia_key(key: str) -> bool:
    """Keep the key in the login Keychain. It goes through `security -i` on stdin, so it never
    appears in a process list."""
    key = key.strip().replace('"', "")
    line = f'add-generic-password -U -s {KEYCHAIN_SERVICE} -a manifest -w "{key}"\n'
    done = subprocess.run(["security", "-i"], input=line, capture_output=True, text=True)
    return done.returncode == 0 and "error" not in (done.stdout + done.stderr).lower()


class CartesiaVoice:
    """Cartesia Sonic in the voice from Pipecat's demos (cloud; the answer's text is sent to
    Cartesia). About 0.1–0.3 s per sentence. If a request fails, `fallback` speaks it."""

    def __init__(self, key: str, voice: str = PIPECAT_VOICE, fallback: Voice | None = None):
        self.key, self.voice_id, self.fallback = key, voice, fallback
        self.voice = "cartesia"
        self.ready = True
        self.problem: str | None = None
        self.status = "ready"
        self._client: Any = None

    def _http(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(http2=False, timeout=8.0)  # keeps the connection warm
        return self._client

    def body(self, text: str) -> dict[str, Any]:
        return {
            "model_id": CARTESIA_MODEL,
            "transcript": text,
            "voice": {"id": self.voice_id},
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": SAMPLE_RATE,
            },
            "language": "en",
            "generation_config": {"speed": 1.0},
        }

    async def speak(self, text: str) -> bytes:
        text = " ".join(text.split())[:MAX_CHARS]
        if not text:
            return b""
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Cartesia-Version": CARTESIA_VERSION,
            "Content-Type": "application/json",
        }
        try:
            response = await self._http().post(CARTESIA_URL, headers=headers, json=self.body(text))
            if response.status_code == 200 and response.content:
                self.problem = None
                return response.content
            self.problem = f"Cartesia {response.status_code}: {response.text[:200]}"
        except Exception as exc:  # network: the fallback speaks
            self.problem = f"Cartesia: {type(exc).__name__}"
        return await self.fallback.speak(text) if self.fallback else b""

    def warm(self) -> None:
        if self.fallback:
            self.fallback.warm()
