"""Cancelled native opens retain their callback owner until explicit close."""
import asyncio
import threading
import pytest
from jarvis.audio.capture import MicrophoneCapture

@pytest.mark.asyncio
async def test_cancelled_open_closes_late_native_stream():
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    calls = []
    class Stream:
        def abort(self):
            calls.append('abort')
        def close(self):
            calls.append('close')
            closed.set()
    def opener():
        entered.set()
        release.wait(2)
        return Stream()
    capture = MicrophoneCapture.__new__(MicrophoneCapture)
    task = asyncio.create_task(capture._owned_native_open(opener))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        assert await asyncio.to_thread(closed.wait, 1)
        assert calls == ['abort', 'close']
    finally:
        release.set()

@pytest.mark.asyncio
async def test_successful_open_transfers_ownership_to_caller():
    capture = MicrophoneCapture.__new__(MicrophoneCapture)
    stream = object()
    assert await capture._owned_native_open(lambda: stream) is stream
