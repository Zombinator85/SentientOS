from __future__ import annotations

import pytest

pytestmark = pytest.mark.no_legacy_skip



import types
import sys

sys.modules.setdefault("notification", types.SimpleNamespace(send=lambda *a, **k: None))

from sentientos.embodiment_proposals import build_embodied_proposal_record, append_embodied_proposal, list_recent_embodied_proposals
import mic_bridge, feedback, screen_awareness, vision_tracker, multimodal_tracker


def test_builder_shape_and_deterministic_id():
    rec1 = build_embodied_proposal_record(source_module="mic_bridge", gate_mode="proposal_only", blocked_effect_type="memory_write", ingress_receipt={"ingress_id":"i1"}, created_at=1.0)
    rec2 = build_embodied_proposal_record(source_module="mic_bridge", gate_mode="proposal_only", blocked_effect_type="memory_write", ingress_receipt={"ingress_id":"i1"}, created_at=2.0)
    assert rec1["proposal_id"] == rec2["proposal_id"]
    assert rec1["review_status"] == "pending_review"
    assert rec1["decision_power"] == "none"
    assert rec1["does_not_write_memory"] is True


def test_append_and_list(tmp_path):
    p = tmp_path / "p.jsonl"
    rec = build_embodied_proposal_record(source_module="feedback", gate_mode="proposal_only", blocked_effect_type="feedback_action", ingress_receipt={"ingress_id":"i2"})
    append_embodied_proposal(rec, path=p)
    out = list_recent_embodied_proposals(path=p, limit=5)
    assert out[-1]["proposal_id"] == rec["proposal_id"]


def test_all_five_modules_emit_proposals_when_blocked(monkeypatch, tmp_path):
    proposals = []
    recorder = lambda r: proposals.append(r) or r

    monkeypatch.setattr(mic_bridge, "append_memory", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no memory write")))
    monkeypatch.setattr(mic_bridge.eu, "detect", lambda path: ({"joy": 0.1}, {}))
    monkeypatch.setattr(mic_bridge.eu, "text_sentiment", lambda text: {"joy": 0.2})
    monkeypatch.setattr(mic_bridge.eu, "fuse", lambda a, b: {"joy": 0.3})
    class DummyRec:
        def record(self, source): return object()
        def recognize_google(self, audio): return "remember this"
    class DummyAudioFile:
        def __init__(self, path): self.path = path
        def __enter__(self): return object()
        def __exit__(self, *args): return False
    class SR: Recognizer = DummyRec; AudioFile = DummyAudioFile
    monkeypatch.setattr(mic_bridge, "sr", SR)
    mic_bridge.recognize_from_file("x.wav", ingress_gate_mode="proposal_only", embodiment_proposal_recorder=recorder)

    mgr = feedback.FeedbackManager(embodiment_proposal_recorder=recorder)
    mgr.add_rule(feedback.FeedbackRule(emotion="joy", threshold=0.1, action="x"))
    mgr.register_action("x", lambda *a: (_ for _ in ()).throw(AssertionError("no action")))
    monkeypatch.setattr(mgr, "request_feedback", lambda *a, **k: None)
    monkeypatch.setattr(feedback, "EMBODIMENT_INGRESS_GATE_MODE", "proposal_only")
    mgr.process(1, {"joy": 0.9})

    s = screen_awareness.ScreenAwareness(log_path=tmp_path / "screen.jsonl")
    s._log_snapshot(screen_awareness.ScreenSnapshot(timestamp=1.0, text="hi"), ingress_gate_mode="proposal_only", embodiment_proposal_recorder=recorder)
    v = vision_tracker.FaceEmotionTracker(camera_index=None, output_file=str(tmp_path / "vision.jsonl"))
    v.log_result({"timestamp":1.0, "faces":[]}, ingress_gate_mode="proposal_only", embodiment_proposal_recorder=recorder)
    mm = multimodal_tracker.MultiModalEmotionTracker(enable_vision=False, enable_voice=False, enable_scene=False, enable_screen=False, output_dir=str(tmp_path))
    mm._log(0, {"timestamp":1.0, "vision":{}, "voice":{}}, ingress_gate_mode="proposal_only", embodiment_proposal_recorder=recorder)

    kinds = {p["proposal_kind"] for p in proposals}
    assert "memory_ingress_candidate" in kinds
    assert "feedback_action_candidate" in kinds
    assert "screen_retention_candidate" in kinds
    assert "vision_retention_candidate" in kinds
    assert "multimodal_retention_candidate" in kinds
