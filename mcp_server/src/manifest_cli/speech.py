"""Manifest's natural voice on this Mac: Kokoro (`af_heart`) on the Apple GPU, through the bridge.

The browser hears (fast, no local models) and the person's agent answers; this module turns
each sentence of the answer into speech. On Apple silicon, Kokoro on MLX takes about 0.5 s
for a sentence (3–5× faster than real time on an 8 GB M1), so the voice sounds natural
without the wait. The CPU (ONNX) build ran at about real time there. The app plays the
audio itself and falls back to the browser's voice if this isn't available.

    POST /speak       {"text": "One sentence."} → raw 16-bit mono PCM at 24 kHz
    POST /speak/warm  pages the model back in while the person is still talking

Extra: ``pip install 'manifest-mcp[natural-voice]'`` (mlx-audio + misaki; Apple silicon).
"""

from __future__ import annotations

import asyncio
import platform
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


class Voice:
    """Kokoro on MLX, loaded once in the background; one sentence at a time."""

    def __init__(self, voice: str = DEFAULT_VOICE) -> None:
        self.voice = voice
        self.ready = False
        self.problem: str | None = None
        self._model: Any = None
        self._lock = threading.Lock()  # MLX runs one synthesis at a time

    def load(self) -> None:
        """Download (first time, ~330 MB) and load the model, then speak once to warm it."""
        try:
            from mlx_audio.tts.utils import load_model

            self._model = load_model(MODEL)  # type: ignore[arg-type]  # a Hugging Face repo id
            self._pcm("Hi.")
            self.ready = True
        except Exception as exc:  # the app keeps the browser's voice
            self.problem = f"{type(exc).__name__}: {exc}"

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
