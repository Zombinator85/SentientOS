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
        stage="observation",
        observed_at="2026-10-12T00:00:00Z",
        evidence_strength="receipt_bound",
        effect_claimed=False,
        effect_proven=False,
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
        fact_id="fact-2", stage="observation", observed_at=None,
        evidence_strength="phase_chain_with_terminal_receipt",
        effect_claimed=False, effect_proven=False)
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
        fact_id="fact-current", stage="observation", observed_at="2026-10-11T12:00:00Z",
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



def test_running_model_priority_requires_observed_serving_session_lineage() -> None:
    payload = {
        "running_model_identity_observed": {"model_id": "model-a", "artifact_id": "artifact-a"},
        "serving_session_id": "session-a",
        "event_time_posture": "serving_session_observation_time_not_model_load_time",
        "authority": False,
        "effect_proven": False,
    }
    fact = SimpleNamespace(
        subject=SimpleNamespace(subject_kind="observed_running_model"),
        disposition="observed", payload=payload,
        source=SimpleNamespace(source_id="model-session"), fact_id="fact-model",
        stage="observation", observed_at="2026-10-11T12:00:00Z",
        evidence_strength="serving_session_observation", effect_claimed=False, effect_proven=False)
    owner = ResidentDevelopmentalCognitionOwner
    assert owner._fact_selection_key(fact, "runtime_supervisor")[0] == 0
    assert owner._fact_selection_key(fact, "local_model_authority")[0] == 6
    fact.payload = {**payload, "event_time_posture": "activation_receipt_only"}
    assert owner._fact_selection_key(fact, "runtime_supervisor")[0] == 6
    fact.payload = payload
    fact.observed_at = "tick-without-time"
    assert owner._fact_selection_key(fact, "runtime_supervisor")[0] == 6


def test_activation_identity_remains_distinct_from_running_model() -> None:
    fact = SimpleNamespace(
        subject=SimpleNamespace(subject_kind="resident_model_transition"),
        disposition="completed",
        payload={"activated_model_identity": {"model_id": "successor"},
            "model_load_posture": "not_loaded_by_activation"},
        source=SimpleNamespace(source_id="transition-record"), fact_id="fact-activation",
        stage="observation", evidence_strength="digest_valid_transition_journal_entry",
        effect_claimed=False, effect_proven=False)
    assert ResidentDevelopmentalCognitionOwner._fact_selection_key(
        fact, "runtime_supervisor")[0] == 1
