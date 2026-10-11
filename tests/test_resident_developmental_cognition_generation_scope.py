from __future__ import annotations

from types import SimpleNamespace

from sentientos.resident_developmental_cognition import ResidentDevelopmentalCognitionOwner


def _fact(payload):
    return SimpleNamespace(
        subject=SimpleNamespace(subject_kind="chat_process_software_generation_invocation"),
        disposition="recorded",
        payload=payload,
        source=SimpleNamespace(source_id="chat-invocation"),
        fact_id="fact-1",
    )


def test_chat_process_generation_priority_requires_scope_qualification() -> None:
    payload = {
        "attribution_posture": "invocation_receipt_and_historical_chat_handoff_verified",
        "chat_process_handoff": {
            "source_generation_scope": "sentientos_and_scripts_python_sources",
        },
        "software_generation_scope": "sentientos_and_scripts_python_sources",
        "loaded_code_identity_posture": "not_independently_attested",
        "invocation_receipt_digest": "a" * 64,
    }
    assert ResidentDevelopmentalCognitionOwner._fact_selection_key(
        _fact(payload), "resource_governor")[0] == 3
    incomplete = dict(payload)
    incomplete.pop("loaded_code_identity_posture")
    assert ResidentDevelopmentalCognitionOwner._fact_selection_key(
        _fact(incomplete), "resource_governor")[0] == 6


def test_chat_recovery_priority_requires_loaded_code_scope_qualification() -> None:
    transition = {
        "phase_evidence_posture":
            "canonical_installation_custody_and_digest_chain_checked_not_independently_signed",
        "effect_authority": False,
        "inference_performed": False,
    }
    payload = {
        "chat_process_recovery_transition": transition,
        "loaded_code_identity_posture": "not_independently_attested",
        "process_identity_scope":
            "installation_bound_handoff_and_digest_chained_recovery_receipts",
        "source_generation_evidence_scope":
            "source_bundle_handoff_identity_not_loaded_code_attestation",
    }
    fact = SimpleNamespace(
        subject=SimpleNamespace(subject_kind="chat_process_recovery_transition"),
        disposition="recorded", payload=payload,
        source=SimpleNamespace(source_id="chat-recovery"),
        fact_id="fact-2")
    owner = ResidentDevelopmentalCognitionOwner
    assert owner._fact_selection_key(fact, "runtime_supervisor")[0] == 4
    incomplete = dict(payload)
    incomplete.pop("loaded_code_identity_posture")
    fact.payload = incomplete
    assert owner._fact_selection_key(fact, "runtime_supervisor")[0] == 6
