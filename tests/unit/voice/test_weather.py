from types import SimpleNamespace
import pytest
from jarvis.core.protocols import ToolResult
from jarvis.voice import weather
from jarvis.voice.subscription_profile import CodexSubscriptionVoiceBrain

@pytest.mark.parametrize('text,expected', [
 ('here. Okay, what is the weather today in Rotterdam?', {'city':'Rotterdam','day':'today'}),
 ('What is the weather in New York tomorrow?', {'city':'New York','day':'tomorrow'}),
 ('What is the weather tomorrow in London?', {'city':'London','day':'tomorrow'}),
 ('What will the weather be tomorrow in Rotterdam?', {'city':'Rotterdam','day':'tomorrow'}),
 ('How will the weather be in Rotterdam tomorrow?', {'city':'Rotterdam','day':'tomorrow'}),
 ('What will the weather be like tomorrow in Rotterdam?', {'city':'Rotterdam','day':'tomorrow'}),
 ('What will the weather be in Rotterdam next week?', None),
 ('What is the weather in Rotterdam next week?', None),
 ('Send the weather to Ray', None), ('What is the weather at home?', None),
])
def test_request_scope(text,expected):
    assert weather.weather_request(text) == expected

@pytest.mark.asyncio
async def test_forecast_uses_location_date_and_units(monkeypatch):
    calls=[]
    async def get(url,params):
        calls.append((url,params))
        if 'geocoding' in url:
            return {'results':[{'name':'Rotterdam','country':'Netherlands','latitude':51.9,'longitude':4.5}]}
        return {'daily':{'time':['2026-10-09','2026-10-10'],'temperature_2m_min':[10,11],'temperature_2m_max':[16,17],'precipitation_probability_max':[20,30]}}
    monkeypatch.setattr(weather,'_json',get)
    r=await weather.DailyWeather().execute({'city':'Rotterdam','day':'today'},None)
    assert r.success and r.output['date']=='2026-10-09'
    assert 'Netherlands' in r.output['answer'] and 'Celsius' in r.output['answer']
    assert calls[1][1]['timezone']=='auto'

@pytest.mark.asyncio
async def test_bad_measurements_fail_honestly(monkeypatch):
    async def get(*args):
        return {'results':[{'latitude':float('nan'),'longitude':4}]}
    monkeypatch.setattr(weather,'_json',get)
    assert not (await weather.DailyWeather().execute({'city':'Rotterdam','day':'today'},None)).success

@pytest.mark.asyncio
@pytest.mark.parametrize('question,day', [
    ('What is the weather today in Rotterdam?', 'today'),
    ('What will the weather be tomorrow in Rotterdam?', 'tomorrow'),
])
async def test_weather_uses_executor_and_neither_model(question, day):
    calls=[]
    class Executor:
        async def execute(self,tool,args,**kwargs):
            calls.append((tool.name,args))
            return ToolResult(True,{'answer':'Source-backed weather answer.'})
    class Delegate:
        _tool_executor_ref=Executor()
        async def generate_stream(self,*a,**kw):
            pytest.fail('No API model should be used')
            yield ''
    brain=CodexSubscriptionVoiceBrain(Delegate(),SimpleNamespace())
    assert await brain.generate(question)=='Source-backed weather answer.'
    assert calls==[('daily_weather',{'city':'Rotterdam','day':day})]

@pytest.mark.asyncio
async def test_missing_executor_does_not_request_api_key():
    answer=await weather.answer_weather(object(),{'city':'Rotterdam','day':'today'},'weather')
    assert 'not ready' in answer and 'API' not in answer

@pytest.mark.asyncio
async def test_dutch_weather_clarification_and_cancellation():
    calls=[]
    class Executor:
        async def execute(self, tool, args, **kwargs):
            calls.append(args)
            return ToolResult(True, {'answer':'Verified forecast.'})
    brain=CodexSubscriptionVoiceBrain(SimpleNamespace(_tool_executor_ref=Executor()), SimpleNamespace())
    assert 'Which city' in await brain.generate('Wat is het weer morgen?')
    assert await brain.generate('Rotterdam.') == 'Verified forecast.'
    assert calls == [{'city':'Rotterdam','day':'tomorrow'}]
    assert brain._pending_weather_day is None
    assert weather.weather_city_reply('Nee bedankt') is None
    assert weather.weather_city_reply('Hoe laat is het?') is None

@pytest.mark.parametrize('text,day', [('Wat is het weer vandaag in Rotterdam?', 'today'), ('Hoe wordt het weer in Rotterdam morgen?', 'tomorrow')])
def test_dutch_daily_weather(text,day):
    assert weather.weather_request(text)=={'city':'Rotterdam','day':day}
