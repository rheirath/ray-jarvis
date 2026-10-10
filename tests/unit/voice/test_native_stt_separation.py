"""Exercise the constructor's real provider-selection block without audio IO."""
import ast
from pathlib import Path
from types import SimpleNamespace
import logging
import pytest

@pytest.mark.parametrize('same_class',[True,False])
def test_final_provider_keeps_configured_instance(monkeypatch,same_class):
    from jarvis.plugins import stt
    class Native:
        pass
    wake=Native()
    final=Native() if same_class else object()
    monkeypatch.setattr(stt,'build_stt_from_config',lambda config:final)
    path=Path(__file__).resolve().parents[3]/'jarvis/speech/pipeline.py'
    tree=ast.parse(path.read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SpeechPipeline')
    init=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
    block=next(n for n in init.body if isinstance(n,ast.If) and any(isinstance(c,ast.ImportFrom) and c.module=='jarvis.plugins.stt' and any(a.name=='build_stt_from_config' for a in c.names) for c in ast.walk(n)))
    instance=SimpleNamespace(_stt=wake,_utterance_stt=wake)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[block],type_ignores=[])),str(path),'exec'),{'self':instance,'config':SimpleNamespace(stt=object()),'log':logging.getLogger(__name__)})
    assert instance._utterance_stt is final
    assert instance._stt is wake
    assert instance._utterance_stt is not instance._stt

@pytest.mark.parametrize('local,requested,expected',[(True,8,30),(False,8,8),(True,45,45)])
def test_local_timeout_budget(local,requested,expected):
    path=Path(__file__).resolve().parents[3]/'jarvis/speech/pipeline.py'
    tree=ast.parse(path.read_text())
    assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr=='_stt_final_timeout_s' for t in n.targets))
    instance=SimpleNamespace(_utterance_stt=SimpleNamespace(runs_on_device=local))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[assignment],type_ignores=[])),str(path),'exec'),{'self':instance,'stt_final_timeout_s':requested})
    assert instance._stt_final_timeout_s==expected
