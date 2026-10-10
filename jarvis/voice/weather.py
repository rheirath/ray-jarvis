"""Key-free, read-only daily weather for explicit English voice questions.

Data and geocoding: https://open-meteo.com/en/docs (CC BY 4.0 attribution).
Only fixed public service hosts are contacted; no user-provided URL is used.
"""
from __future__ import annotations

from datetime import date
import math
import re

from jarvis.core.protocols import ToolResult

_QUESTION = re.compile(
    r"^(?:(?:here|okay|ok|hello|hey|jarvis)[\s,.!]*)*"
    r"(?:(?:what(?:'s| is)|how(?:'s| is)) (?:the )?weather"
    r"|(?:what|how) will (?:the )?weather be)(?: like)?"
    r"(?: (today|tomorrow))? in ([\w\s,'’.-]{2,80}?)"
    r"(?: (today|tomorrow))?[?.!]*$", re.IGNORECASE,
)


def weather_request(text: str) -> dict | None:
    match = _QUESTION.fullmatch(text.strip())
    if not match:
        return None
    before, city, after = match.groups()
    if re.search(r'\b(?:next|week|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', city, re.IGNORECASE):
        return None
    if before and after and before.lower() != after.lower():
        return None
    return {'city': city.strip(' .,!?'), 'day': (before or after or 'today').lower()}


async def _json(url: str, params: dict) -> dict:
    import httpx
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        async with client.stream('GET', url, params=params) as response:
            response.raise_for_status()
            payload = bytearray()
            async for chunk in response.aiter_bytes():
                payload.extend(chunk)
                if len(payload) > 262144:
                    raise ValueError('Weather response too large')
    import json
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError('Invalid weather response')
    return result


def _number(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Missing weather measurement')
    return float(value)


class DailyWeather:
    name = 'daily_weather'
    description = 'Read today or tomorrow forecast for an explicitly named city from Open-Meteo.'
    risk_tier = 'safe'
    schema = {'type': 'object', 'properties': {'city': {'type': 'string'}, 'day': {'enum': ['today', 'tomorrow']}}, 'required': ['city', 'day'], 'additionalProperties': False}

    async def execute(self, args, ctx) -> ToolResult:
        import httpx
        try:
            city = args['city']
            day = args['day']
            if not isinstance(city, str) or not 2 <= len(city) <= 80 or day not in {'today', 'tomorrow'}:
                raise ValueError('Invalid weather request')
            geo = await _json('https://geocoding-api.open-meteo.com/v1/search', {'name': city, 'count': 1, 'language': 'en', 'format': 'json'})
            places = geo.get('results') or []
            if not places:
                return ToolResult(True, {'answer': f'I could not locate {city}. Please give the city name more clearly.'})
            place = places[0]
            latitude, longitude = _number(place['latitude']), _number(place['longitude'])
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError('Invalid coordinates')
            data = await _json('https://api.open-meteo.com/v1/forecast', {
                'latitude': latitude, 'longitude': longitude, 'timezone': 'auto', 'forecast_days': 2,
                'daily': 'temperature_2m_max,temperature_2m_min,precipitation_probability_max',
                'temperature_unit': 'celsius',
            })
            daily = data['daily']; index = int(day == 'tomorrow')
            forecast_date = date.fromisoformat(daily['time'][index])
            low = _number(daily['temperature_2m_min'][index])
            high = _number(daily['temperature_2m_max'][index])
            rain = _number(daily['precipitation_probability_max'][index])
            if low > high or not 0 <= rain <= 100:
                raise ValueError('Invalid forecast range')
            label = ', '.join(str(place[k]) for k in ('name', 'admin1', 'country') if place.get(k))
            answer = (f'According to Open-Meteo, the forecast for {label} on {forecast_date.strftime("%B %d, %Y")} '
                      f'is a low of {low:g} and a high of {high:g} degrees Celsius, '
                      f'with a maximum precipitation chance of {rain:g} percent.')
            return ToolResult(True, {'answer': answer, 'source': 'https://open-meteo.com/', 'date': forecast_date.isoformat(), 'location': label})
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            return ToolResult(False, None, 'Live weather could not be retrieved. Please try again later.')


async def answer_weather(delegate, args: dict, utterance: str) -> str:
    from jarvis.core.capabilities import Capability, get_registry
    executor = getattr(delegate, '_tool_executor_ref', None)
    if executor is None:
        return 'The weather connection is not ready yet. Please try again shortly.'
    tool = DailyWeather()
    get_registry().register(Capability(id='local.daily-weather', source='local_action', verbs=('forecast',), objects=('weather',), description=tool.description, risk_tier='safe', requires_evidence=True))
    result = await executor.execute(tool, args, user_utterance=utterance, rationale='Explicit read-only weather question')
    if not result.success:
        return 'I could not retrieve live weather right now. Please try again later.'
    return str(result.output['answer'])
