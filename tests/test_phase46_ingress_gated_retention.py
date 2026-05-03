
from __future__ import annotations

import pytest

import json

import multimodal_tracker
import screen_awareness
import vision_tracker
pytestmark = pytest.mark.no_legacy_skip

from sentientos.embodiment_ingress import (
    build_retention_ingress_candidate,
    evaluate_embodiment_ingress,
    mark_legacy_direct_retention_preserved,
    should_allow_legacy_retention_write,
)


def test_screen_awareness_proposal_only_blocks_persistent_write(tmp_path):
    s = screen_awareness.ScreenAwareness(log_path=tmp_path / "screen.jsonl")
    snap = screen_awareness.ScreenSnapshot(timestamp=1.0, text="hello")
    rec = s._log_snapshot(snap, ingress_gate_mode="proposal_only")
    assert rec["retention_gate_mode"] == "proposal_only"
    assert not (tmp_path / "screen.jsonl").exists()


def test_screen_awareness_compatibility_legacy_preserves_write(tmp_path):
    s = screen_awareness.ScreenAwareness(log_path=tmp_path / "screen.jsonl")
    snap = screen_awareness.ScreenSnapshot(timestamp=1.0, text="hello")
    rec = s._log_snapshot(snap, ingress_gate_mode="compatibility_legacy")
    assert (tmp_path / "screen.jsonl").exists()
    assert rec["legacy_direct_effect_preserved"] is True


def test_vision_proposal_only_blocks_write(tmp_path):
    t = vision_tracker.FaceEmotionTracker(camera_index=None, output_file=str(tmp_path / "vision.jsonl"))
    rec = t.log_result({"timestamp": 1.0, "faces": []}, ingress_gate_mode="proposal_only")
    assert rec["retention_gate_mode"] == "proposal_only"
    assert rec["recommended_posture"] in {"biometric_sensitive_hold", "privacy_sensitive_hold", "no_ingress_needed", "incomplete_context_hold"}
    assert not (tmp_path / "vision.jsonl").exists()


def test_vision_compatibility_preserves_write(tmp_path):
    t = vision_tracker.FaceEmotionTracker(camera_index=None, output_file=str(tmp_path / "vision.jsonl"))
    rec = t.log_result({"timestamp": 1.0, "faces": [{"id": 1, "emotions": {"joy": 0.9}}]}, ingress_gate_mode="compatibility_legacy")
    assert (tmp_path / "vision.jsonl").exists()
    assert rec["legacy_direct_effect_preserved"] is True


def test_multimodal_proposal_only_blocks_person_and_environment_writes(tmp_path):
    mm = multimodal_tracker.MultiModalEmotionTracker(enable_vision=False, enable_voice=False, enable_scene=False, enable_screen=False, output_dir=str(tmp_path))
    rec1 = mm._log(0, {"timestamp": 1.0, "vision": {}, "voice": {}, "screen": {"text": "x"}}, ingress_gate_mode="proposal_only")
    rec2 = mm._log_environment({"timestamp": 1.0, "screen": {"text": "x"}}, ingress_gate_mode="proposal_only")
    assert rec1["retention_gate_mode"] == "proposal_only"
    assert rec2["retention_gate_mode"] == "proposal_only"
    assert not (tmp_path / "0.jsonl").exists()
    assert not (tmp_path / "environment.jsonl").exists()


def test_multimodal_compatibility_preserves_writes(tmp_path):
    mm = multimodal_tracker.MultiModalEmotionTracker(enable_vision=False, enable_voice=False, enable_scene=False, enable_screen=False, output_dir=str(tmp_path))
    rec1 = mm._log(1, {"timestamp": 1.0, "vision": {}, "voice": {}}, ingress_gate_mode="compatibility_legacy")
    rec2 = mm._log_environment({"timestamp": 1.0, "voice": {"joy": 0.1}}, ingress_gate_mode="compatibility_legacy")
    assert (tmp_path / "1.jsonl").exists()
    assert (tmp_path / "environment.jsonl").exists()
    assert rec1["legacy_direct_effect_preserved"] is True
    assert rec2["legacy_direct_effect_preserved"] is True


def test_ingress_retention_helpers_non_authoritative_contract():
    snap = {"snapshot_id": "x", "modalities_present": ["screen"]}
    rec = evaluate_embodiment_ingress(snap)
    cand = build_retention_ingress_candidate(snap, retention_surface="screen_ocr", source_refs=["screen"])
    marked = mark_legacy_direct_retention_preserved(rec, retention_surface="screen_ocr", mode="compatibility_legacy")
    assert should_allow_legacy_retention_write("proposal_only") is False
    assert should_allow_legacy_retention_write("compatibility_legacy") is True
    assert cand["decision_power"] == "none"
    assert rec["decision_power"] == "none"
    assert marked["legacy_direct_effect_preserved"] is True
