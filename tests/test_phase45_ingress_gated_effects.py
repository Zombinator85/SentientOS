
from __future__ import annotations

import pytest

import sys
import types

sys.modules.setdefault("notification", types.SimpleNamespace(send=lambda *a, **k: None))
import feedback
import mic_bridge

pytestmark = pytest.mark.no_legacy_skip


def test_mic_bridge_proposal_only_blocks_memory_write(monkeypatch):
    calls = []
    monkeypatch.setattr(mic_bridge, "append_memory", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(mic_bridge.eu, "detect", lambda path: ({"joy": 0.1}, {}))
    monkeypatch.setattr(mic_bridge.eu, "text_sentiment", lambda text: {"joy": 0.2})
    monkeypatch.setattr(mic_bridge.eu, "fuse", lambda a, b: {"joy": 0.3})

    class DummyRec:
        def record(self, source):
            return object()
        def recognize_google(self, audio):
            return "remember this"

    class DummyAudioFile:
        def __init__(self, path):
            self.path = path
        def __enter__(self):
            return object()
        def __exit__(self, *args):
            return False

    class SR:
        Recognizer = DummyRec
        AudioFile = DummyAudioFile

    monkeypatch.setattr(mic_bridge, "sr", SR)
    out = mic_bridge.recognize_from_file("fake.wav", ingress_gate_mode="proposal_only")
    assert calls == []
    assert out["ingress_receipt"]["ingress_gate_mode"] == "proposal_only"


def test_mic_bridge_compatibility_legacy_preserves_memory_write(monkeypatch):
    calls = []
    monkeypatch.setattr(mic_bridge, "append_memory", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(mic_bridge.eu, "detect", lambda path: ({"joy": 0.1}, {}))
    monkeypatch.setattr(mic_bridge.eu, "text_sentiment", lambda text: {"joy": 0.2})
    monkeypatch.setattr(mic_bridge.eu, "fuse", lambda a, b: {"joy": 0.3})

    class DummyRec:
        def record(self, source):
            return object()
        def recognize_google(self, audio):
            return "remember this"

    class DummyAudioFile:
        def __init__(self, path):
            self.path = path
        def __enter__(self):
            return object()
        def __exit__(self, *args):
            return False

    class SR:
        Recognizer = DummyRec
        AudioFile = DummyAudioFile

    monkeypatch.setattr(mic_bridge, "sr", SR)
    out = mic_bridge.recognize_from_file("fake.wav", ingress_gate_mode="compatibility_legacy")
    assert len(calls) == 1
    assert out["ingress_receipt"]["legacy_direct_effect_preserved"] is True


def test_feedback_proposal_only_blocks_actions(monkeypatch):
    monkeypatch.setattr(feedback, "EMBODIMENT_INGRESS_GATE_MODE", "proposal_only")
    manager = feedback.FeedbackManager()
    rule = feedback.FeedbackRule(emotion="joy", threshold=0.1, action="x")
    manager.add_rule(rule)
    action_calls = []
    manager.register_action("x", lambda r, u, v: action_calls.append((r, u, v)))
    monkeypatch.setattr(manager, "request_feedback", lambda *a, **k: None)
    manager.process(1, {"joy": 0.9})
    assert action_calls == []
    assert manager.history[-1]["ingress_receipt"]["ingress_gate_mode"] == "proposal_only"


def test_feedback_compatibility_legacy_preserves_actions(monkeypatch):
    monkeypatch.setattr(feedback, "EMBODIMENT_INGRESS_GATE_MODE", "compatibility_legacy")
    manager = feedback.FeedbackManager()
    rule = feedback.FeedbackRule(emotion="joy", threshold=0.1, action="x")
    manager.add_rule(rule)
    action_calls = []
    manager.register_action("x", lambda r, u, v: action_calls.append((r, u, v)))
    monkeypatch.setattr(manager, "request_feedback", lambda *a, **k: None)
    manager.process(1, {"joy": 0.9})
    assert len(action_calls) == 1
    assert manager.history[-1]["ingress_receipt"]["legacy_direct_effect_preserved"] is True


def test_ingress_non_authoritative_contract():
    from sentientos.embodiment_fusion import build_embodiment_snapshot
    from sentientos.embodiment_ingress import evaluate_embodiment_ingress

    snap = build_embodiment_snapshot([])
    rec = evaluate_embodiment_ingress(snap)
    assert rec["decision_power"] == "none"
    assert rec["does_not_write_memory"] is True
    assert rec["does_not_trigger_feedback"] is True
