"""Local voice rejects invalid audio and isolates timed-out native calls."""
import asyncio
import threading

import numpy as np
import pytest

from jarvis.core.config import TTSConfig
from jarvis.plugins.tts import build_tts_from_config
from jarvis.plugins.tts.kokoro_local import KokoroLocalTTS


class Engine:
    def create(self, text, **kwargs):
        return np.array([-2., 0., 2.]), 24000


async def collect(provider, **kwargs):
    return [chunk async for chunk in provider.synthesize("Hello", **kwargs)]


@pytest.mark.asyncio
async def test_pcm_and_factory():
    provider = build_tts_from_config(TTSConfig(provider="kokoro-local", fallback="", voice_en="am_michael"))
    assert isinstance(provider, KokoroLocalTTS)
    from jarvis.core.protocols import TTSProvider
    assert isinstance(provider, TTSProvider)
    assert provider.list_voices("en-US") == ["am_michael"]
    assert provider.list_voices("nl") == []
    provider._engine_factory = Engine
    chunks = await collect(provider)
    assert chunks[0].sample_rate == 24000
    assert np.frombuffer(chunks[0].pcm, dtype="<i2").tolist() == [-32767, 0, 32767]


@pytest.mark.asyncio
async def test_unsupported_language_never_loads_engine():
    provider = KokoroLocalTTS(engine_factory=lambda: pytest.fail("Must not load"))
    with pytest.raises(ValueError, match="English only"):
        await collect(provider, language_code="nl-NL")


@pytest.mark.asyncio
async def test_invalid_audio_is_rejected():
    class Invalid(Engine):
        def create(self, text, **kwargs):
            return np.array([float("nan")]), 24000
    with pytest.raises(RuntimeError, match="invalid audio"):
        await collect(KokoroLocalTTS(engine_factory=Invalid))


@pytest.mark.asyncio
async def test_busy_engine_rejected_without_waiting():
    provider = KokoroLocalTTS(engine_factory=Engine)
    provider._state.lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="already synthesizing"):
            await collect(provider)
    finally:
        provider._state.lock.release()


@pytest.mark.asyncio
async def test_timeout_replaces_engine_while_old_call_remains_blocked():
    release = threading.Event()
    entered = threading.Event()
    class Slow(Engine):
        def create(self, text, **kwargs):
            entered.set()
            release.wait(2)
            return super().create(text, **kwargs)
    provider = KokoroLocalTTS(engine_factory=Slow, timeout_s=0.05)
    original = provider._state
    try:
        with pytest.raises(TimeoutError):
            await collect(provider)
        assert entered.is_set()
        assert provider._state is not original
        provider._engine_factory = Engine
        provider.timeout_s = 1
        assert len(await collect(provider)) == 1
    finally:
        release.set()


def test_warmup_reuses_engine_and_does_not_block_active_call():
    provider = KokoroLocalTTS(engine_factory=Engine)
    provider._ensure_client()
    engine = provider._state.engine
    provider._ensure_client()
    assert provider._state.engine is engine
    provider._state.lock.acquire()
    try:
        provider._ensure_client()
    finally:
        provider._state.lock.release()

@pytest.mark.asyncio
async def test_overlapping_sentences_are_serialized():
    import time
    class Measured(Engine):
        active = 0
        peak = 0
        def create(self, text, **kwargs):
            self.active += 1
            self.peak = max(self.peak, self.active)
            time.sleep(0.02)
            self.active -= 1
            return super().create(text, **kwargs)
    engine = Measured()
    provider = KokoroLocalTTS(engine_factory=lambda: engine)
    results = await asyncio.gather(collect(provider), collect(provider))
    assert all(len(result) == 1 for result in results)
    assert engine.peak == 1
