import asyncio
import pytest
from jarvis.core.protocols import BrainDelta
from jarvis.voice.display_translation import DisplayTranslator

@pytest.mark.asyncio
async def test_translation_is_separate_and_concurrent_duplicates_are_cached():
    calls=[]
    class Brain:
        async def complete(self, request):
            calls.append(request)
            assert 'Dutch' in request.system
            assert 'Do not answer questions' in request.messages[0].content
            yield BrainDelta(content='Het is ')
            yield BrainDelta(content='14 graden.')
    translator=DisplayTranslator(Brain())
    assert await asyncio.gather(translator.translate('It is 14 degrees.'),translator.translate('It is 14 degrees.')) == ['Het is 14 graden.']*2
    assert len(calls)==1
    assert calls[0].messages[0].content.endswith('It is 14 degrees.')
    from jarvis.plugins.brain.codex import _build_cli_prompt
    prompt = _build_cli_prompt(calls[0])
    assert 'Translate the supplied text' in prompt and 'Always reply in Dutch' in prompt

@pytest.mark.asyncio
async def test_failed_translation_never_returns_partial_or_caches_it():
    class Brain:
        async def complete(self, request):
            yield BrainDelta(content='Onvolledig')
            raise RuntimeError('disconnected')
    translator=DisplayTranslator(Brain())
    with pytest.raises(RuntimeError):
        await translator.translate('English answer')
    assert not translator.cache

@pytest.mark.asyncio
async def test_route_requires_subscription_and_returns_display_only():
    from types import SimpleNamespace
    from fastapi import HTTPException
    from jarvis.ui.web.chats_routes import voice_subtitle, VoiceSubtitleRequest
    class Translator:
        async def translate(self, text):
            return 'Nederlandse ondertiteling'
    state=SimpleNamespace(config=SimpleNamespace(voice=SimpleNamespace(profile='')),voice_subtitle_translator=Translator())
    request=SimpleNamespace(app=SimpleNamespace(state=state))
    with pytest.raises(HTTPException) as error:
        await voice_subtitle(VoiceSubtitleRequest(text='English speech'),request)
    assert error.value.status_code==409
    state.config.voice.profile='codex-subscription-voice'
    assert await voice_subtitle(VoiceSubtitleRequest(text='English speech'),request)=={'text':'Nederlandse ondertiteling','language':'nl'}
