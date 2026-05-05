from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from sentientos.context_hygiene.context_packet import PollutionRisk
from sentientos.context_hygiene.embodiment_context import build_embodiment_context_candidates, embodiment_artifact_is_context_eligible
from sentientos.context_hygiene.selector import build_context_packet_from_candidates


NOW = datetime.now(timezone.utc)


def _a(kind: str, **kwargs):
    base = {
        "ref_id": f"{kind}-1",
        "source_kind": kind,
        "packet_scope": "turn",
        "conversation_scope_id": "conv",
        "task_scope_id": "task",
        "content_summary": "sanitized summary",
        "provenance_refs": ["prov:1"],
        "sanitized_context_summary": True,
        "decision_power": "none",
        "non_authoritative": True,
        "proposal_status": "reviewable",
    }
    base.update(kwargs)
    return base


def test_phase63_embodiment_context_eligibility_bridge():
    blocked_kinds = ["raw_perception_event", "legacy_screen_artifact", "legacy_audio_artifact", "legacy_vision_artifact", "legacy_multimodal_artifact", "legacy_feedback_artifact"]
    for k in blocked_kinds:
        assert not embodiment_artifact_is_context_eligible(_a(k))

    assert not embodiment_artifact_is_context_eligible(_a("embodiment_snapshot", sanitized_context_summary=False))
    assert embodiment_artifact_is_context_eligible(_a("embodiment_snapshot"))
    assert not embodiment_artifact_is_context_eligible(_a("embodiment_ingress_receipt", sanitized_context_summary=False, context_eligible=False))
    assert embodiment_artifact_is_context_eligible(_a("embodiment_ingress_receipt", context_eligible=True, sanitized_context_summary=False))
    assert embodiment_artifact_is_context_eligible(_a("embodiment_proposal"))
    assert not embodiment_artifact_is_context_eligible(_a("embodiment_proposal", provenance_refs=[]))
    assert embodiment_artifact_is_context_eligible(_a("embodiment_proposal_diagnostic"))
    assert embodiment_artifact_is_context_eligible(_a("embodiment_review_receipt"))
    assert not embodiment_artifact_is_context_eligible(_a("embodiment_handoff_candidate", handoff_is_not_fulfillment=False))
    assert embodiment_artifact_is_context_eligible(_a("embodiment_handoff_candidate", handoff_is_not_fulfillment=True))
    assert not embodiment_artifact_is_context_eligible(_a("embodiment_governance_bridge_candidate", bridge_is_not_admission=False))
    assert embodiment_artifact_is_context_eligible(_a("embodiment_governance_bridge_candidate", bridge_is_not_admission=True))
    assert not embodiment_artifact_is_context_eligible(_a("embodiment_fulfillment_candidate", fulfillment_candidate_is_not_effect=False))
    assert embodiment_artifact_is_context_eligible(_a("embodiment_fulfillment_candidate", fulfillment_candidate_is_not_effect=True))
    assert not embodiment_artifact_is_context_eligible(_a("embodiment_fulfillment_receipt", fulfillment_receipt_is_not_effect=True, receipt_does_not_prove_side_effect=False))
    assert embodiment_artifact_is_context_eligible(_a("embodiment_fulfillment_receipt", fulfillment_receipt_is_not_effect=True, receipt_does_not_prove_side_effect=True))
    assert embodiment_artifact_is_context_eligible(_a("memory_ingress_validation", validation_is_not_memory_write=True))
    assert embodiment_artifact_is_context_eligible(_a("action_ingress_validation", validation_is_not_action_trigger=True))
    assert embodiment_artifact_is_context_eligible(_a("retention_ingress_validation", validation_is_not_retention_commit=True))
    assert not embodiment_artifact_is_context_eligible(_a("embodiment_snapshot", privacy_posture="biometric_or_emotion_sensitive"))
    assert embodiment_artifact_is_context_eligible(_a("embodiment_snapshot", privacy_posture="biometric_or_emotion_sensitive", allow_context_biometric_or_emotion=True))
    assert not embodiment_artifact_is_context_eligible(_a("embodiment_snapshot", privacy_posture="raw_retention_sensitive"))
    assert embodiment_artifact_is_context_eligible(_a("embodiment_snapshot", privacy_posture="raw_retention_sensitive", allow_context_raw_retention=True))
    assert not embodiment_artifact_is_context_eligible(_a("embodiment_snapshot", privacy_posture="privacy_sensitive"))
    assert embodiment_artifact_is_context_eligible(_a("embodiment_snapshot", privacy_posture="privacy_sensitive", allow_context_privacy_sensitive=True))
    assert not embodiment_artifact_is_context_eligible(_a("embodiment_snapshot", decision_power="admit"))
    assert not embodiment_artifact_is_context_eligible(_a("embodiment_snapshot", packet_scope=None))
    assert not embodiment_artifact_is_context_eligible(_a("unknown"))

    raw = _a("raw_perception_event")
    good = _a("embodiment_snapshot")
    diag = _a("embodiment_proposal_diagnostic")
    action_cap = _a("embodiment_snapshot", action_capable=True)
    cands = build_embodiment_context_candidates([raw, good, diag, action_cap])
    assert cands[2].ref_type == "diagnostic"
    assert cands[1].metadata["context_eligible"] is True

    pkt = build_context_packet_from_candidates(cands, "turn", "conv", "task", now=NOW)
    assert any(i.ref_id == good["ref_id"] for i in pkt.included_embodiment_refs)
    assert any(i.ref_id == diag["ref_id"] for i in pkt.included_diagnostic_refs)
    assert pkt.pollution_risk == PollutionRisk.BLOCKED
    assert any(r.ref_id == raw["ref_id"] for r in pkt.excluded_refs)
    assert any("excluded:" in r for r in pkt.exclusion_reasons)
    assert pkt.non_authoritative and pkt.decision_power == "none"

    original = _a("embodiment_snapshot")
    cloned = deepcopy(original)
    _ = build_embodiment_context_candidates([original])
    assert original == cloned

    import sentientos.context_hygiene.embodiment_context as mod

    txt = open(mod.__file__, encoding="utf-8").read()
    for forbidden in [
        "prompt_assembler",
        "memory_manager",
        "task_executor",
        "task_admission",
        "screen_awareness",
        "mic_bridge",
        "vision_tracker",
        "multimodal_tracker",
        "openai",
        "requests",
    ]:
        assert forbidden not in txt
