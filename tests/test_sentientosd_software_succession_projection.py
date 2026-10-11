from sentientosd import _software_generation_current_observation


def test_running_generation_requires_owner_revalidation_and_preserves_loaded_code_limit() -> None:
    provenance = {
        "represented_generation_digest": "generation-digest",
        "process_instance_id": "process-instance",
        "provenance_digest": "provenance-digest",
        "process_identity_scope": "pid_startup_argv_executable_entrypoint_module_origin_and_environment",
        "software_generation_scope": "configured_manifest_and_clean_repository_state_at_observation",
        "loaded_code_identity_posture": "not_independently_attested",
    }

    observed = _software_generation_current_observation(provenance)

    assert observed["running_software_generation_observed"] == "generation-digest"
    assert observed["running_software_process_instance_id"] == "process-instance"
    assert observed["running_software_observation_posture"] == (
        "process_identity_and_repository_revalidated_loaded_code_unattested")
    assert observed["running_software_loaded_code_identity_posture"] == "not_independently_attested"


def test_startup_baseline_or_malformed_provenance_cannot_be_projected_as_running() -> None:
    for provenance in (None, {"represented_generation_digest": "launch-baseline"}, {
            "represented_generation_digest": "generation-digest",
            "process_instance_id": "process-instance",
            "provenance_digest": "provenance-digest",
            "process_identity_scope": "process",
            "software_generation_scope": "source-bundle",
            "loaded_code_identity_posture": "independently_attested",
    }):
        observed = _software_generation_current_observation(provenance)
        assert observed["running_software_generation_observed"] is None
        assert observed["running_software_observation_posture"] == (
            "current_process_revalidation_unavailable")



def test_resident_transition_world_state_tail_preserves_omission_lineage() -> None:
    from sentientosd import (
        RESIDENT_TRANSITION_WORLD_STATE_ENTRY_LIMIT,
        _bounded_resident_transition_entries,
    )

    entries = tuple({"entry_digest": f"entry-{index}",
        "prior_digest": f"entry-{index - 1}" if index else "GENESIS"}
        for index in range(RESIDENT_TRANSITION_WORLD_STATE_ENTRY_LIMIT + 12))
    retained, omitted = _bounded_resident_transition_entries(entries)

    assert len(retained) == RESIDENT_TRANSITION_WORLD_STATE_ENTRY_LIMIT
    assert retained[0]["entry_digest"] == "entry-12"
    assert retained[-1]["entry_digest"] == f"entry-{len(entries) - 1}"
    assert omitted == {
        "journal_head_digest": f"entry-{len(entries) - 1}",
        "omitted_entry_count": 12,
        "last_omitted_entry_digest": "entry-11",
        "first_retained_prior_digest": "entry-11",
        "retained_entry_count": RESIDENT_TRANSITION_WORLD_STATE_ENTRY_LIMIT,
        "retained_tail_limit": RESIDENT_TRANSITION_WORLD_STATE_ENTRY_LIMIT,
    }



def test_resident_transition_projection_applies_the_declared_tail_to_the_full_journal() -> None:
    from types import SimpleNamespace

    from sentientosd import RESIDENT_TRANSITION_WORLD_STATE_ENTRY_LIMIT, RuntimeMaintenanceSurfaces

    count = RESIDENT_TRANSITION_WORLD_STATE_ENTRY_LIMIT + 22
    entries = tuple({
        "sequence": index + 1,
        "entry_digest": f"entry-{index}",
        "prior_digest": f"entry-{index - 1}" if index else "GENESIS",
        "phase": "a_quiesced", "status": "completed", "event_time": f"tick-{index}",
        "evidence": {},
    } for index in range(count))

    class Journal:
        def entries(self):
            return list(entries)

    protocol = SimpleNamespace(value={
        "transition_id": "transition-test", "protocol_digest": "protocol-digest",
        "predecessor_a": {"identity_digest": "model-a"},
        "successor_b": {"identity_digest": "model-b"},
        "initial_history_boundary": {"boundary_digest": "history-boundary"},
    })
    surfaces = object.__new__(RuntimeMaintenanceSurfaces)
    surfaces._resident_transition_runtime = None
    surfaces._resident_transition_custody = (protocol, Journal())
    surfaces._resident_transition_custody_error = None
    surfaces._resident_cognitive_invoker = SimpleNamespace(current_controller=None)
    surfaces._resident_software_transition_controller = None
    surfaces._resident_software_transition_config = None
    surfaces._resident_model_provenance_bindings = lambda _value: {}

    records = surfaces._resident_succession_world_state_records("2026-10-11T00:00:00Z")
    transitions = [record for record in records if record["subject_kind"] == "resident_model_transition"]
    retention = [record for record in records
        if record["subject_kind"] == "resident_model_transition_history_retention"]

    assert len(transitions) == RESIDENT_TRANSITION_WORLD_STATE_ENTRY_LIMIT
    assert transitions[0]["payload"]["journal_entry_digest"] == f"entry-{count - RESIDENT_TRANSITION_WORLD_STATE_ENTRY_LIMIT}"
    assert transitions[-1]["payload"]["journal_entry_digest"] == f"entry-{count - 1}"
    assert len(retention) == 1
    assert retention[0]["payload"]["omitted_entry_count"] == 22
    assert retention[0]["payload"]["last_omitted_entry_digest"] == f"entry-{count - RESIDENT_TRANSITION_WORLD_STATE_ENTRY_LIMIT - 1}"
