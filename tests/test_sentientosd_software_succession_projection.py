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
