"""Local English Kokoro speech with isolated, recoverable native engines."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import threading
import time
from typing import Any

from jarvis.core.protocols import AudioChunk


@dataclass
class _EngineState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    engine: Any = None


class KokoroLocalTTS:
    name = "kokoro-local"
    supports_streaming = False
    runs_on_device = True
    last_voice: str | None = None
    last_voice_provider: str | None = None

    def __init__(self, *, model_dir: str | Path | None = None,
                 voice: str = "am_michael", speed: float = 1.0,
                 timeout_s: float = 45.0, engine_factory: Any = None) -> None:
        self.model_dir = Path(model_dir or Path.home() / ".jarvis/models/kokoro")
        self.voice = voice
        self.speed = float(speed)
        if not 0.5 <= self.speed <= 2.0:
            raise ValueError("Kokoro speed must be between 0.5 and 2.0")
        self.timeout_s = timeout_s
        self._engine_factory = engine_factory
        self._state = _EngineState()

    def _load_engine(self):
        if self._engine_factory is not None:
            return self._engine_factory()
        from kokoro_onnx import Kokoro
        from kokoro_onnx.config import EspeakConfig

        model = self.model_dir / "kokoro-v1.0.onnx"
        voices = self.model_dir / "voices-v1.0.bin"
        data = self.model_dir / "espeak-ng-data"
        if not model.is_file() or not voices.is_file() or not data.is_dir():
            raise RuntimeError("Install the Kokoro model, voices and eSpeak data locally first")
        return Kokoro(str(model), str(voices), espeak_config=EspeakConfig(data_path=str(data)))

    def _ensure_client(self) -> None:
        """Warm the local engine using the same nonblocking ownership lock."""
        state = self._state
        if not state.lock.acquire(blocking=False):
            return  # An active synthesis already owns initialization.
        try:
            if state.engine is None:
                state.engine = self._load_engine()
        finally:
            state.lock.release()

    def list_voices(self, language: str | None = None) -> list[str]:
        if language and language.lower().split("-")[0].split("_")[0] != "en":
            return []
        return ["am_michael"]

    def recover(self) -> None:
        # A timed-out native call may still be running. Its engine and lock
        # stay with that call; a future request gets a fresh instance.
        self._state = _EngineState()

    def _render(self, state: _EngineState, text: str, voice: str, language: str):
        import numpy as np

        if not state.lock.acquire(blocking=False):
            raise RuntimeError("Kokoro is already synthesizing speech")
        try:
            if state.engine is None:
                state.engine = self._load_engine()
            samples, rate = state.engine.create(text, voice=voice, speed=self.speed, lang=language)
            samples = np.asarray(samples)
            if samples.ndim != 1 or not samples.size or not np.isfinite(samples).all() or rate <= 0:
                raise RuntimeError("Kokoro produced invalid audio")
            pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
            return AudioChunk(pcm=pcm, sample_rate=int(rate), timestamp_ns=time.monotonic_ns())
        finally:
            state.lock.release()

    async def synthesize(self, text: str, voice: str | None = None,
                         language_code: str | None = None):
        if not text.strip():
            return
        language = (language_code or "en-US").lower().replace("_", "-")
        if language not in {"en", "en-us", "en-gb"}:
            raise ValueError("This Kokoro integration currently supports English only")
        selected_voice = voice or self.voice
        if not selected_voice.startswith(("af_", "am_", "bf_", "bm_")):
            raise ValueError("Select an English Kokoro voice")
        language = "en-gb" if selected_voice.startswith(("bf_", "bm_")) else "en-us"
        state = self._state
        try:
            chunk = await asyncio.wait_for(
                asyncio.to_thread(self._render, state, text, selected_voice, language),
                timeout=self.timeout_s,
            )
        except (TimeoutError, asyncio.CancelledError):
            if self._state is state:
                self.recover()
            raise
        self.last_voice = selected_voice
        self.last_voice_provider = self.name
        yield chunk
