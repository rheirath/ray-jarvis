"""Subscription routing must exercise the real deferred desktop facade."""
import ast
from pathlib import Path
from types import SimpleNamespace
import pytest
from jarvis.brain.manager import BrainManager
from jarvis.core.capabilities import get_registry
from jarvis.core.capabilities_seed import seed_registry
from jarvis.core.protocols import BrainDelta
from jarvis.voice.subscription_profile import CodexSubscriptionVoiceBrain


def facade(brain):
    source = Path(__file__).resolve().parents[3] / 'jarvis/ui/desktop_app.py'
    tree = ast.parse(source.read_text())
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == '_DeferredVoiceBrain')
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), cls], type_ignores=[])
    namespace = {'brain_holder': {'brain': brain}}
    exec(compile(ast.fix_missing_locations(module), str(source), 'exec'), namespace)
    return namespace['_DeferredVoiceBrain']()


@pytest.mark.asyncio
async def test_reported_turn_and_followup_use_subscription_through_desktop():
    seed_registry(get_registry())
    class RealDetector:
        _turn_has_action_intent = BrainManager._turn_has_action_intent
    delegate = facade(RealDetector())
    async def forbidden(*args, **kwargs):
        pytest.fail('Desktop conversation reached the API-backed delegate')
        yield ''
    delegate.generate_stream = forbidden
    requests = []
    class Subscription:
        async def complete(self, request):
            requests.append(request)
            yield BrainDelta(content='Hello. I can hear you.')
    brain = CodexSubscriptionVoiceBrain(delegate, SimpleNamespace(brain=SimpleNamespace(reply_language='en')))
    brain._subscription = Subscription()
    for text in ["Hello, this isn't test.", 'Now.', 'now.']:
        assert await brain.generate(text) == 'Hello. I can hear you.'
    assert len(requests) == 3


def test_desktop_still_forwards_real_action_detection():
    seed_registry(get_registry())
    class RealDetector:
        _turn_has_action_intent = BrainManager._turn_has_action_intent
    assert facade(RealDetector())._turn_has_action_intent('Open Safari')
    assert facade(None)._turn_has_action_intent is None
