"""Input must remain closed until buffered speaker audio and its tail finish."""
from types import SimpleNamespace
import pytest
from jarvis.core.protocols import AudioChunk
from jarvis.speech.pipeline import SpeechPipeline


def pipeline(latency):
    p=SpeechPipeline.__new__(SpeechPipeline)
    p._player=SimpleNamespace(output_latency_s=latency)
    p._post_tts_listen_suppression_s=0.8
    p._input_suppressed_until_ns=0
    return p


def test_reported_speaker_latency_covers_percent_patient_tail(monkeypatch):
    monkeypatch.setattr('jarvis.speech.pipeline.time.time_ns',lambda: 10_000_000_000)
    p=pipeline(1.564)
    p._suppress_session_input_after_tts('response')
    assert p._input_suppressed_until_ns == 12_364_000_000
    # Even if processed later, queued mic frames carry their capture time.
    for captured in [10_800_000_000,11_564_000_000,12_000_000_000]:
        assert p._should_drop_session_input(AudioChunk(b'echo',16000,captured))
    assert not p._should_drop_session_input(AudioChunk(b'user',16000,12_400_000_000))


@pytest.mark.parametrize('latency',[None,'bad',float('nan'),float('inf'),-2,0])
def test_invalid_latency_preserves_fixed_tail(monkeypatch,latency):
    monkeypatch.setattr('jarvis.speech.pipeline.time.time_ns',lambda: 10_000_000_000)
    p=pipeline(latency);p._suppress_session_input_after_tts('response')
    assert p._input_suppressed_until_ns == 10_800_000_000


def test_new_shorter_guard_cannot_reopen_input_early(monkeypatch):
    monkeypatch.setattr('jarvis.speech.pipeline.time.time_ns',lambda: 10_000_000_000)
    p=pipeline(1.564);p._suppress_session_input_after_tts('response')
    p._player.output_latency_s=0
    p._suppress_session_input_after_tts('response')
    assert p._input_suppressed_until_ns == 12_364_000_000
