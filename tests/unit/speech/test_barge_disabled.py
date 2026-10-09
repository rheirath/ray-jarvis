from types import SimpleNamespace
import pytest
from jarvis.speech.pipeline import SpeechPipeline

@pytest.mark.asyncio
async def test_disabled_barge_monitor_never_initializes_audio():
    pipeline=SpeechPipeline.__new__(SpeechPipeline)
    pipeline._config=SimpleNamespace(voice=SimpleNamespace(barge_in_enabled=False))
    assert await pipeline._barge_monitor() is False
