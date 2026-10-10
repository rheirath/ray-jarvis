from __future__ import annotations

from types import SimpleNamespace

import pytest

from jarvis.core.protocols import BrainDelta
from jarvis.speech.pipeline import PipelineState, SpeechPipeline
from jarvis.voice.subscription_profile import (
    CODEX_SUBSCRIPTION_VOICE_PROFILE,
    CodexSubscriptionVoiceBrain,
    configured_voice_profile,
    subscription_voice_capability,
)


def _config(*, profile: str = "", realtime_provider: str = "") -> SimpleNamespace:
    realtime = SimpleNamespace(provider=realtime_provider) if realtime_provider else None
    return SimpleNamespace(
        voice=SimpleNamespace(profile=profile, mode="realtime"),
        brain=SimpleNamespace(reply_language="auto", realtime=realtime),
    )


def test_only_explicit_profile_selects_the_classic_subscription_composition() -> None:
    assert (
        configured_voice_profile(profile := _config(profile=CODEX_SUBSCRIPTION_VOICE_PROFILE))
        == CODEX_SUBSCRIPTION_VOICE_PROFILE
    )
    assert profile.voice.mode == "realtime"
    assert configured_voice_profile(
        _config(realtime_provider="codex-subscription-realtime")
    ) == ""
    assert configured_voice_profile(_config()) == ""


def test_realtime_provider_pin_does_not_change_the_selected_engine() -> None:
    pipeline = SpeechPipeline.__new__(SpeechPipeline)
    pipeline._config = _config(realtime_provider="codex-subscription-realtime")

    assert pipeline._configured_voice_mode() == "realtime"


def test_profile_can_be_applied_and_removed_without_process_restart() -> None:
    delegate = object()
    config = _config()
    pipeline = SpeechPipeline.__new__(SpeechPipeline)
    pipeline._config = config
    pipeline._base_brain = delegate
    pipeline._brain = delegate
    pipeline._state = PipelineState.IDLE

    assert pipeline.apply_voice_profile(CODEX_SUBSCRIPTION_VOICE_PROFILE) is False
    assert isinstance(pipeline._brain, CodexSubscriptionVoiceBrain)
    assert config.voice.mode == "pipeline"

    assert pipeline.apply_voice_profile("") is False
    assert pipeline._brain is delegate


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
def test_capability_uses_the_same_composed_path_on_every_desktop_os(
    platform: str,
) -> None:
    config = _config(profile=CODEX_SUBSCRIPTION_VOICE_PROFILE)
    config.stt = SimpleNamespace(provider="nemotron-local")
    config.tts = SimpleNamespace(provider="piper-local")

    capability = subscription_voice_capability(
        config,
        account_ready=True,
        runtime_attached=True,
        display_present=True,
        platform=platform,
    )

    assert capability.available is True
    assert capability.reason == "ready"


def test_capability_reports_headless_audio_as_unavailable() -> None:
    config = _config(profile=CODEX_SUBSCRIPTION_VOICE_PROFILE)
    config.stt = SimpleNamespace(provider="nemotron-local")
    config.tts = SimpleNamespace(provider="piper-local")

    capability = subscription_voice_capability(
        config,
        account_ready=True,
        runtime_attached=True,
        display_present=False,
        platform="linux",
    )

    assert capability.available is False
    assert capability.reason == "headless_audio_unavailable"


@pytest.mark.asyncio
async def test_conversation_turns_stream_through_subscription_with_history() -> None:
    requests = []

    class Subscription:
        async def complete(self, request):
            requests.append(request)
            yield BrainDelta(content="Hello.")
            yield BrainDelta(finish_reason="stop")

    class Delegate:
        @staticmethod
        def _turn_has_action_intent(_text: str) -> bool:
            return False

        async def generate_stream(self, *_args, **_kwargs):
            pytest.fail("conversational turns must not use the router brain")
            yield ""

    brain = CodexSubscriptionVoiceBrain(Delegate(), _config())
    brain._subscription = Subscription()

    first = [chunk async for chunk in brain.generate_stream("Share a short joke.")]
    second = [chunk async for chunk in brain.generate_stream("Tell me something amusing.")]

    assert first == ["Hello."]
    assert second == ["Hello."]
    assert [message.role for message in requests[1].messages] == [
        "user",
        "assistant",
        "user",
    ]
    assert "REPLY LANGUAGE" in str(requests[0].system)


@pytest.mark.asyncio
async def test_subscription_failure_never_uses_provider_chain() -> None:
    delegated = []

    class Subscription:
        async def complete(self, _request):
            raise RuntimeError("subscription transport is busy")
            yield BrainDelta()  # pragma: no cover - preserves async-generator shape

    class Delegate:
        _last_turn_all_failed = False
        _last_turn_suppressed = False
        _last_turn_executed_action_tool = False

        @staticmethod
        def _turn_has_action_intent(_text: str) -> bool:
            return False

        async def generate_stream(self, text, **_kwargs):
            delegated.append(text)
            yield "Fallback answer."

    brain = CodexSubscriptionVoiceBrain(Delegate(), _config())
    brain._subscription = Subscription()

    with pytest.raises(RuntimeError, match="subscription transport is busy"):
        await brain.generate("Tell me a short joke.")
    assert delegated == []
    assert brain._last_turn_all_failed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [
    "I do this.", "Open Chrome now.", "Use the connected service for this request.",
    "Which plugins are installed?", "What is the latest news?", "Read my email.",
])
async def test_subscription_profile_never_enters_api_action_chain(text):
    requests = []
    class Delegate:
        def _turn_has_action_intent(self, text):
            return True
        async def generate_stream(self, *args, **kwargs):
            pytest.fail("Subscription profile must never enter the API chain")
            yield ""
    class Subscription:
        async def complete(self, request):
            requests.append(request)
            yield BrainDelta(content="Could you clarify what you mean?")
    brain = CodexSubscriptionVoiceBrain(Delegate(), _config())
    brain._subscription = Subscription()
    assert await brain.generate(text) == "Could you clarify what you mean?"
    assert requests[0].messages[-1].content == text
    assert "cannot execute actions" in requests[0].system
    assert "Do not ask for an API key" in requests[0].system
    assert not brain._last_turn_executed_action_tool


@pytest.mark.asyncio
async def test_spoken_salutation_stays_on_subscription_and_preserves_prompt():
    requests = []
    class Subscription:
        async def complete(self, request):
            requests.append(request)
            yield BrainDelta(content="Hello, Ray!")
    class Delegate:
        @staticmethod
        def _turn_has_action_intent(text):
            return False
        async def generate_stream(self, *args, **kwargs):
            pytest.fail("A salutation must not reach the API router")
            yield ""
    brain = CodexSubscriptionVoiceBrain(Delegate(), _config())
    brain._subscription = Subscription()
    text = "Hello, Jarvis. Say hello to Ray."
    assert await brain.generate(text) == "Hello, Ray!"
    assert requests[0].messages[-1].content == text
    assert await brain.generate("Say that again.") == "Hello, Ray!"


@pytest.mark.asyncio
async def test_salutation_preserves_local_state_request_without_api_fallback():
    requests = []
    class Delegate:
        async def generate_stream(self, text, **kwargs):
            pytest.fail("Local-state requests must not cross to a paid API")
            yield ""
    class Subscription:
        async def complete(self, request):
            requests.append(request)
            yield BrainDelta(content="I cannot inspect installed plugins in this voice mode.")
    brain = CodexSubscriptionVoiceBrain(Delegate(), _config())
    brain._subscription = Subscription()
    text = "Hello, Jarvis. Which plugins are installed?"
    await brain.generate(text)
    assert requests[0].messages[-1].content == text
    assert "do not invent results" in requests[0].system
