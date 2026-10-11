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
    contradictory = {**payload, "authority": False, "effect_proven": False,
        "software_generation": "other-generation"}
    fact.payload = contradictory
    assert owner._fact_selection_key(fact, "runtime_supervisor")[0] == 6



def test_current_software_generation_priority_requires_current_owner_scope() -> None:
    payload = {
        "currentness_posture": "owner_verified_process_and_source_at_observation",
        "process_identity_scope":
            "pid_startup_argv_executable_entrypoint_module_origin_and_environment",
        "software_generation_scope":
            "configured_manifest_and_clean_repository_state_at_observation",
        "loaded_code_identity_posture": "not_independently_attested",
        "software_generation": "generation-digest",
        "running_software_generation_observed": "generation-digest",
        "process_instance_id": "process-instance",
        "provenance_digest": "provenance-digest",
    }
    fact = SimpleNamespace(
        subject=SimpleNamespace(subject_kind="verified_current_running_software_generation"),
        disposition="observed", payload={**payload, "authority": False, "effect_proven": False},
        source=SimpleNamespace(source_id="runtime-source"),
        fact_id="fact-current", stage="observation",
        evidence_strength="owner_verified_current_process_and_clean_source",
        effect_claimed=False, effect_proven=False)
    owner = ResidentDevelopmentalCognitionOwner
    assert owner._fact_selection_key(fact, "runtime_supervisor")[0] == 0
    incomplete = dict(payload)
    incomplete.pop("loaded_code_identity_posture")
    fact.payload = incomplete
    assert owner._fact_selection_key(fact, "runtime_supervisor")[0] == 6


def test_launch_time_software_observation_is_not_current_running_priority() -> None:
    fact = SimpleNamespace(
        subject=SimpleNamespace(subject_kind="observed_running_software_generation"),
        disposition="observed", payload={"startup_timestamp": "2026-10-11T00:00:00Z"},
        source=SimpleNamespace(source_id="runtime-source"),
        fact_id="fact-launch", stage="observation", evidence_strength="resident_launch_provenance",
        effect_claimed=False, effect_proven=False)
    assert ResidentDevelopmentalCognitionOwner._fact_selection_key(
        fact, "runtime_supervisor")[0] == 6
