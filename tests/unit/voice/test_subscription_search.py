import json
from types import SimpleNamespace
import pytest
from jarvis.voice.subscription_search import wants_search, search_answer, SubscriptionSearch
from jarvis.voice.subscription_profile import CodexSubscriptionVoiceBrain
from jarvis.core.protocols import ToolResult, BrainDelta

@pytest.mark.parametrize('text,expected', [('Wat is de uitslag van Feyenoord tegen AZ?',True),('Zoek op internet naar het laatste nieuws',True),('Read my email',False),('Zoek in mijn notities',False),('Hallo goedenavond',False),('Hoe laat is het?',False)])
def test_search_scope(text,expected):
    assert wants_search(text)==expected

def test_requires_search_event_and_source():
    answer=json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'Answer https://example.org/source'}})
    with pytest.raises(ValueError):search_answer(answer)
    search=json.dumps({'type':'item.completed','item':{'type':'web_search'}})
    assert 'example.org' in search_answer(search+'\n'+answer)
    with pytest.raises(ValueError):search_answer(search+'\n'+answer.replace('https://',''))

@pytest.mark.asyncio
async def test_voice_search_summarizes_once_after_executor():
    calls=[]
    class Executor:
        async def execute(self,tool,args,**kwargs):
            assert isinstance(tool,SubscriptionSearch)
            calls.append(args)
            return ToolResult(True,{'answer':'Verified answer https://example.org'})
    brain=CodexSubscriptionVoiceBrain(SimpleNamespace(_tool_executor_ref=Executor()),SimpleNamespace())
    class Summary:
        async def complete(self,request):
            assert 'English' in request.system
            assert 'State the answer once' in request.system
            yield BrainDelta(content='Verified English answer.')
    brain._subscription=Summary()
    chunks=[part async for part in brain.generate_stream('Wat is de uitslag van Feyenoord tegen AZ?')]
    assert chunks==['Verified English answer.']
    result=''.join(chunks)
    assert 'Verified' in result and len(calls)==1

@pytest.mark.asyncio
async def test_invalid_login_never_spawns(monkeypatch):
    import jarvis.codex_app_server as transport
    import jarvis.voice.subscription_search as search
    monkeypatch.setattr(transport,'_read_codex_capability',lambda _:SimpleNamespace(available=False,chatgpt_authenticated=False))
    async def forbidden(*args,**kwargs):
        pytest.fail('An invalid subscription must not start a process')
    monkeypatch.setattr(search.asyncio,'create_subprocess_exec',forbidden)
    result=await SubscriptionSearch(SimpleNamespace()).execute({'query':'news'},None)
    assert not result.success

def test_unexpected_tool_and_failed_search_rejected():
    for item in [{'type':'turn.failed'}, {'type':'item.completed','item':{'type':'command_execution'}}]:
        with pytest.raises(ValueError):search_answer(json.dumps(item))


def test_only_last_search_answer_is_spoken():
    events=[{'type':'item.completed','item':{'type':'web_search'}},
            {'type':'item.completed','item':{'type':'agent_message','text':'Checking. Repeated result.'}},
            {'type':'item.completed','item':{'type':'agent_message','text':'Final result https://example.org'}}]
    assert search_answer('\n'.join(json.dumps(e) for e in events))=='Final result https://example.org'
