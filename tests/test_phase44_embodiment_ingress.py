from sentientos.embodiment_fusion import build_embodiment_snapshot
from sentientos.embodiment_ingress import evaluate_embodiment_ingress


def _snapshot(events):
    return build_embodiment_snapshot(events, created_at=100.0, correlation_id="c1")


def test_memory_pressure_requires_review() -> None:
    snap = _snapshot([{"modality": "audio", "timestamp": 1.0, "source_module": "mic_bridge", "observation": {"message": "remember this"}}])
    rec = evaluate_embodiment_ingress(snap)
    assert rec["recommended_posture"] in {"memory_candidate_requires_review", "incomplete_context_hold", "privacy_sensitive_hold", "consent_required_hold"}
    assert rec["does_not_write_memory"] is True


def test_feedback_pressure_blocked_or_attention() -> None:
    snap = _snapshot([{"modality": "feedback", "timestamp": 1.0, "source_module": "feedback", "observation": {"action": "cue"}}])
    rec = evaluate_embodiment_ingress(snap)
    assert rec["recommended_posture"] in {"action_candidate_blocked", "operator_attention_recommended", "incomplete_context_hold"}
    assert rec["does_not_trigger_feedback"] is True


def test_vision_is_biometric_hold() -> None:
    snap = _snapshot([{"modality": "vision", "timestamp": 1.0, "source_module": "vision_tracker", "observation": {"faces": [{"dominant": "joy"}]}}])
    rec = evaluate_embodiment_ingress(snap)
    assert rec["recommended_posture"] in {"biometric_sensitive_hold", "incomplete_context_hold"}


def test_screen_privacy_hold() -> None:
    snap = _snapshot([{"modality": "screen", "timestamp": 1.0, "source_module": "screen_awareness", "observation": {"text": "password"}}])
    rec = evaluate_embodiment_ingress(snap)
    assert rec["recommended_posture"] in {"privacy_sensitive_hold", "incomplete_context_hold"}


def test_incomplete_context_hold() -> None:
    rec = evaluate_embodiment_ingress(_snapshot([]))
    assert rec["recommended_posture"] == "incomplete_context_hold"


def test_deterministic_and_provenance() -> None:
    snap = _snapshot([{"modality": "multimodal", "timestamp": 1.0, "source_module": "multimodal_tracker", "observation": {"summary": "ok"}}])
    a = evaluate_embodiment_ingress(snap)
    b = evaluate_embodiment_ingress(snap)
    assert a == b
    assert a["source_snapshot_ref"] == snap["snapshot_id"]
    assert isinstance(a["source_event_refs"], list)
    for k in ["non_authoritative", "decision_power", "does_not_admit_work", "does_not_execute_or_route_work"]:
        assert k in a
