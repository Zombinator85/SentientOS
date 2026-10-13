from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentientos.longitudinal_self_model import LongitudinalSelfModelError, LongitudinalSelfModelOwner
from sentientos.world_state_board import WorldStateBoardBuilder

pytestmark = pytest.mark.no_legacy_skip


NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def record(*, source: str = "runtime:a", subject: str = "sentientos", disposition: str = "serving",
           observed: str = "2026-09-25T11:59:00Z", model: str = "model-a", generation: str = "software-a",
           extra: dict[str, object] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "software_generation": generation,
        "cognitive_model_id": model,
        "developmental_history_boundary": "history-10",
    }
    payload.update(extra or {})
    return {
        "source_kind": "local_model_authority", "source_id": source,
        "schema_version": "test.v1", "subject_id": subject,
        "subject_kind": "persistent_causal_system", "stage": "observation",
        "disposition": disposition, "evidence_strength": "authenticated",
        "observed_at": observed, "payload": payload,
    }


def snapshot(*records: dict[str, object]):
    return WorldStateBoardBuilder(clock=lambda: NOW).build(records)


def test_exact_source_binding_and_identical_replay_are_idempotent(tmp_path: Path) -> None:
    source = snapshot(record())
    owner = LongitudinalSelfModelOwner(tmp_path)
    first = owner.reconcile(source, tick_id="tick-1")
    second = owner.reconcile(source, tick_id="tick-replay")
    assert second == first
    assert len(owner.history()) == 1
    assert all(claim.world_state_snapshot_digest == source.digest for claim in first.claims)
    assert {claim.source_evidence_ids for claim in first.claims} == {("runtime:a",)}
    assert not any(first.authority.values())


def test_stale_evidence_is_not_current_and_disappearance_is_withdrawal(tmp_path: Path) -> None:
    owner = LongitudinalSelfModelOwner(tmp_path)
    old = owner.reconcile(snapshot(record(observed="2026-09-10T00:00:00Z")), tick_id="tick-1")
    assert all(claim.status == "historical" and claim.freshness == "stale" for claim in old.claims)
    current = owner.reconcile(snapshot(record(source="runtime:b", subject="other")), tick_id="tick-2")
    withdrawn = [claim for claim in current.claims if claim.subject_id == "sentientos"]
    assert withdrawn and all(claim.status == "withdrawn" and claim.freshness == "stale" for claim in withdrawn)


def test_host_resource_snapshot_stays_historical_unknown_and_later_tick_bound(tmp_path: Path) -> None:
    observed_at = "2026-09-25T11:59:00Z"
    source = record(source="host_resource_runtime:snapshot", observed=observed_at,
        extra={"snapshot_id": "host-snapshot-a", "observed_at": observed_at,
            "cpu_utilization_percent": 37.5, "ram_utilization_percent": None,
            "gpu_utilization_percent": None, "disk_free_bytes": 123456,
            "authority": False, "effect_proven": False, "effect_claimed": False})
    source.update({"source_kind": "resource_governor", "subject_kind": "host_resource_snapshot"})
    world_state = snapshot(source)
    owner = LongitudinalSelfModelOwner(tmp_path)
    first = owner.reconcile(world_state, tick_id="tick-host-snapshot")
    claim = next(item for item in first.claims
        if item.predicate == "resource_governor.historical_host_snapshot")
    assert claim.status == "historical"
    assert claim.freshness == "unknown"
    assert claim.claim_category == "historical_interpretation"
    assert claim.source_evidence_ids == ("host_resource_runtime:snapshot",)
    assert claim.source_evidence_digests == (world_state.sources[0].digest,)
    assert claim.value["event_time"] == observed_at
    assert claim.value["event_time_posture"] == "source_payload_timestamp"
    assert claim.value["metrics"] == {"cpu_utilization_percent": 37.5,
        "disk_free_bytes": 123456}
    assert {"ram_utilization_percent", "gpu_utilization_percent"} <= set(claim.value["unknown_metrics"])
    assert claim.value["shared_host_use_attribution"] == "not_per_invocation"
    assert claim.value["current_truth"] is False and claim.value["authority"] is False

    restarted = LongitudinalSelfModelOwner(tmp_path)
    assert restarted.reconcile(world_state, tick_id="tick-host-replay") == first
    assert restarted.cognitive_projection(before_tick="tick-host-snapshot", max_claims=8,
        allowed_predicates=("resource_governor.historical_host_snapshot",)) is None
    later = restarted.cognitive_projection(before_tick="tick-host-next", max_claims=8,
        allowed_predicates=("resource_governor.historical_host_snapshot",))
    assert later is not None and later.source_tick == "tick-host-snapshot"
    retained = later.selected_claims[0]
    assert retained["claim_id"] == claim.claim_id
    assert retained["predicate"] == claim.predicate
    assert retained["value"]["event_time"] == observed_at
    assert retained["value"]["shared_host_use_attribution"] == "not_per_invocation"


@pytest.mark.parametrize("subject_kind", [
    "developmental_model_replacement_experiment",
    "developmental_history_intervention_experiment",
])
def test_developmental_experiment_lifecycle_is_historical_not_current_state(
    tmp_path: Path, subject_kind: str,
) -> None:
    source_record = {
        "source_kind": "embodiment", "source_id": f"experiment:{subject_kind}",
        "schema_version": "sentientos.developmental_experiment:v1",
        "subject_id": f"run:{subject_kind}", "subject_kind": subject_kind,
        "stage": "observation", "disposition": "history_presence_associated_stable_difference",
        "evidence_strength": "digest_bound_experimental_record",
        "observed_at": "2026-09-25T11:59:00Z",
        "payload": {"classification": "history_presence_associated_stable_difference",
            "current_truth": False, "authority": False, "learning_established": False},
        "effect_claimed": False, "effect_proven": False,
    }
    owner = LongitudinalSelfModelOwner(tmp_path)
    world_state = snapshot(source_record)
    tick_id = f"tick:{subject_kind}"
    result = owner.reconcile(world_state, tick_id=tick_id)
    lifecycle = next(claim for claim in result.claims
        if claim.predicate == "lifecycle.observation.disposition")
    assert lifecycle.claim_category == "historical_interpretation"
    assert lifecycle.status == "historical"
    assert lifecycle.current_truth is False
    assert lifecycle.value == "history_presence_associated_stable_difference"
    assert owner.cognitive_projection(before_tick=tick_id, max_claims=4,
        allowed_predicates=("lifecycle.observation.disposition",)) is None

    # Restarted later cognition receives the historical category, source
    # observation time, uncertainty, and non-authority qualifiers intact.
    later = LongitudinalSelfModelOwner(tmp_path).cognitive_projection(
        before_tick=f"{tick_id}:next", max_claims=4,
        allowed_predicates=("lifecycle.observation.disposition",))
    assert later is not None and later.source_tick == tick_id
    projected = later.selected_claims[0]
    assert projected["claim_category"] == "historical_interpretation"
    assert projected["status"] == "historical"
    assert projected["freshness"] == "unknown"
    assert projected["temporal_scope"] == "historical_and_current"
    assert projected["lifecycle_stage"] == "observation"
    assert projected["source_observed_at"] == ["2026-09-25T11:59:00Z"]
    assert projected["source_observed_at_count"] == 1
    assert projected["source_observed_at_posture"] == "complete"
    assert projected["current_truth"] is False and projected["interpretation"] is True
    assert projected["authority"] and not any(projected["authority"].values())


def test_contradictory_evidence_is_preserved_without_latest_wins(tmp_path: Path) -> None:
    result = LongitudinalSelfModelOwner(tmp_path).reconcile(
        snapshot(record(source="runtime:a", model="model-a"), record(source="runtime:b", model="model-b")),
        tick_id="tick-1",
    )
    model_claims = [claim for claim in result.claims if claim.predicate == "cognitive_model_identity"]
    assert {claim.value for claim in model_claims} == {"model-a", "model-b"}
    assert all(claim.status == "contradicted" and claim.contradiction_state == "contradicted" for claim in model_claims)


def test_generation_and_model_transition_preserves_historical_claims(tmp_path: Path) -> None:
    owner = LongitudinalSelfModelOwner(tmp_path)
    first = owner.reconcile(snapshot(record(model="model-a", generation="software-a")), tick_id="tick-a")
    second = owner.reconcile(snapshot(record(source="runtime:b", model="model-b", generation="software-b")), tick_id="tick-b")
    assert owner.reconstruct(1) == first
    assert owner.reconstruct(2) == second
    old = [claim for claim in second.claims if claim.value in {"model-a", "software-a"}]
    new = [claim for claim in second.claims if claim.value in {"model-b", "software-b"}]
    assert old and all(claim.status == "historical" and claim.superseded_by for claim in old)
    assert new and all(claim.status == "current" and claim.supersedes for claim in new)


def test_source_digest_mismatch_fails_closed_without_write(tmp_path: Path) -> None:
    bad = snapshot({**record(), "digest": "not-the-content-digest"})
    owner = LongitudinalSelfModelOwner(tmp_path)
    with pytest.raises(LongitudinalSelfModelError, match="provenance"):
        owner.reconcile(bad, tick_id="tick-1")
    assert owner.history() == ()


def test_malformed_snapshot_identity_fails_closed(tmp_path: Path) -> None:
    good = snapshot(record())
    owner = LongitudinalSelfModelOwner(tmp_path)
    with pytest.raises(LongitudinalSelfModelError, match="invalid_world_state_snapshot"):
        owner.reconcile(replace(good, digest="tampered"), tick_id="tick-1")
    assert owner.history() == ()


def test_authority_and_model_authored_claim_smuggling_is_rejected(tmp_path: Path) -> None:
    owner = LongitudinalSelfModelOwner(tmp_path)
    for payload in ({"authority": True}, {"permission": True}, {"model_authored_claim": "I improved"}):
        with pytest.raises(LongitudinalSelfModelError, match="smuggling"):
            owner.reconcile(snapshot(record(extra=payload)), tick_id="tick-1")
    assert owner.history() == ()


def test_atomic_interruption_leaves_no_partial_reconciliation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = LongitudinalSelfModelOwner(tmp_path)
    def interrupted(*args: object, **kwargs: object) -> None:
        raise OSError("interrupted")
    monkeypatch.setattr(owner, "_publish_entry", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        owner.reconcile(snapshot(record()), tick_id="tick-1")
    assert owner.history() == ()


def test_restart_reconstruction_detects_tamper_and_retains_superseded_history(tmp_path: Path) -> None:
    owner = LongitudinalSelfModelOwner(tmp_path)
    owner.reconcile(snapshot(record()), tick_id="tick-a")
    owner.reconcile(snapshot(record(source="runtime:b", model="model-b")), tick_id="tick-b")
    restarted = LongitudinalSelfModelOwner(tmp_path)
    assert restarted.reconstruct(1) is not None
    assert any(claim.value == "model-a" for claim in restarted.reconstruct(2).claims)  # type: ignore[union-attr]
    path = sorted((tmp_path / "reconciliations").glob("*.json"))[0]
    raw = json.loads(path.read_text()); raw["tick_id"] = "tampered"
    path.write_text(json.dumps(raw, sort_keys=True, indent=2) + "\n")
    with pytest.raises(LongitudinalSelfModelError, match="digest_mismatch"):
        restarted.history()



def test_qualified_software_generation_scope_survives_longitudinal_writeback(
    tmp_path: Path,
) -> None:
    qualified = record(source="runtime:software", extra={
        "process_role": "maintenance_daemon",
        "process_identity_scope": "launch_provenance_bound_process_instance",
        "software_generation_scope": "configured_manifest_and_clean_repository_state",
        "loaded_code_identity_posture": "not_independently_attested",
    })
    result = LongitudinalSelfModelOwner(tmp_path).reconcile(
        snapshot(qualified), tick_id="tick-qualified-software")
    values = {(claim.predicate, claim.value) for claim in result.claims}
    assert ("process_role", "maintenance_daemon") in values
    assert ("software_generation_scope",
            "configured_manifest_and_clean_repository_state") in values
    assert ("loaded_code_identity_posture", "not_independently_attested") in values



def test_chat_runtime_history_binds_source_scope_and_loaded_code_limit(tmp_path: Path) -> None:
    observation = {
        "observation_semantic_digest": "a" * 64,
        "runtime_supervisor_generation": "runtime-generation-1",
        "observed_at": "2026-09-25T11:59:00Z",
        "runtime_status": "running_observed",
        "configured_serving_receipt_posture": "not_observed",
        "configured_serving_operation_id": "serve-op-1",
        "serving_receipt": None,
        "handoff_id": "handoff-1",
        "handoff_digest": "b" * 64,
        "process_instance_id": "process-1",
        "software_generation_digest": "sha256:" + "c" * 64,
        "source_generation_scope": "sentientos_and_scripts_python_sources",
    }
    source = record(source="runtime:chat-process", extra={
        "chat_process_runtime_observation": observation,
        "linked_invocation_receipts": [],
        "software_generation_scope": observation["source_generation_scope"],
        "loaded_code_identity_posture": "not_independently_attested",
        "process_identity_scope":
            "installation_bound_launcher_handoff_checked_at_recorded_observation",
    })
    source["source_kind"] = "runtime_supervisor"
    source["subject_kind"] = "chat_process_runtime_generation_observation"
    result = LongitudinalSelfModelOwner(tmp_path).reconcile(
        snapshot(source), tick_id="tick-chat-runtime")
    lineage = next(claim for claim in result.claims
        if claim.predicate == "chat_process_runtime.historical_generation_observation")
    assert lineage.value["software_generation_scope"] == (
        "sentientos_and_scripts_python_sources")
    assert lineage.value["loaded_code_identity_posture"] == "not_independently_attested"
    assert lineage.value["process_identity_scope"] == (
        "installation_bound_launcher_handoff_checked_at_recorded_observation")



def test_chat_recovery_history_retains_loaded_code_scope_posture(tmp_path: Path) -> None:
    transition = {
        "request_id": "recovery-request-1",
        "attempt_phase_digest": "a" * 64,
        "phase_evidence_posture":
            "canonical_installation_custody_and_digest_chain_checked_not_independently_signed",
        "predecessor_chat_process_handoff": {
            "handoff_id": "predecessor-handoff",
            "handoff_digest": "b" * 64,
            "software_generation_digest": "sha256:" + "c" * 64,
            "source_generation_scope": "sentientos_and_scripts_python_sources",
        },
        "successor_chat_process_handoff": {
            "handoff_id": "successor-handoff",
            "handoff_digest": "d" * 64,
            "software_generation_digest": "sha256:" + "e" * 64,
            "source_generation_scope": "sentientos_and_scripts_python_sources",
        },
    }
    source = record(source="runtime:recovery", extra={
        "chat_process_recovery_transition": transition,
        "loaded_code_identity_posture": "not_independently_attested",
        "process_identity_scope":
            "installation_bound_handoff_and_digest_chained_recovery_receipts",
        "source_generation_evidence_scope":
            "source_bundle_handoff_identity_not_loaded_code_attestation",
    })
    source["source_kind"] = "runtime_supervisor"
    source["subject_kind"] = "chat_process_recovery_transition"
    result = LongitudinalSelfModelOwner(tmp_path).reconcile(
        snapshot(source), tick_id="tick-chat-recovery")
    lineage = next(claim for claim in result.claims
        if claim.predicate == "chat_process_recovery.historical_phase_lineage")
    assert lineage.value["loaded_code_identity_posture"] == "not_independently_attested"
    assert lineage.value["process_identity_scope"] == (
        "installation_bound_handoff_and_digest_chained_recovery_receipts")
    assert lineage.value["predecessor_chat_process_handoff"]["source_generation_scope"] == (
        "sentientos_and_scripts_python_sources")



def test_running_software_observation_is_grouped_with_source_scope(tmp_path: Path) -> None:
    observed = "2026-09-25T11:59:00Z"
    source = record(source="runtime:software-current", observed=observed, extra={
        "running_software_generation_observed": "sha256:" + "a" * 64,
        "software_generation": "sha256:" + "a" * 64,
        "process_instance_id": "sha256:" + "b" * 64,
        "provenance_digest": "sha256:" + "c" * 64,
        "repository_commit": "commit-sha",
        "repository_tree": "tree-sha",
        "startup_timestamp": "2026-09-25T11:00:00Z",
        "process_role": "maintenance_daemon",
        "process_identity_scope":
            "pid_startup_argv_executable_entrypoint_module_origin_and_environment",
        "software_generation_scope":
            "configured_manifest_and_clean_repository_state_at_observation",
        "loaded_code_identity_posture": "not_independently_attested",
        "currentness_posture": "owner_verified_process_and_source_at_observation",
        "event_time_posture": "owner_point_observation_time",
        "authority": False,
        "effect_proven": False,
    })
    source.update({"source_kind": "runtime_supervisor",
        "subject_kind": "verified_current_running_software_generation",
        "disposition": "observed",
        "evidence_strength": "owner_verified_current_process_and_clean_source"})
    source["effect_claimed"] = False
    result = LongitudinalSelfModelOwner(tmp_path).reconcile(
        snapshot(source), tick_id="tick-current-software")
    claim = next(item for item in result.claims
        if item.predicate == "software_generation.current_process_observation")
    assert claim.value["observed_at"] == observed
    assert claim.value["process_identity_scope"] == (
        "pid_startup_argv_executable_entrypoint_module_origin_and_environment")
    assert claim.value["loaded_code_identity_posture"] == "not_independently_attested"
    assert claim.current_truth is False
    assert claim.source_evidence_ids == ("runtime:software-current",)
    restarted = LongitudinalSelfModelOwner(tmp_path)
    assert restarted.cognitive_projection(before_tick="tick-current-software",
        max_claims=8, allowed_predicates=("software_generation.current_process_observation",)) is None
    later = restarted.cognitive_projection(before_tick="tick-next", max_claims=8,
        allowed_predicates=("software_generation.current_process_observation",))
    assert later is not None and later.source_tick == "tick-current-software"
    assert later.selected_claims[0]["value"]["observed_at"] == observed
    assert later.selected_claims[0]["value"]["loaded_code_identity_posture"] == (
        "not_independently_attested")


def test_launch_software_observation_is_historical_interpretation(tmp_path: Path) -> None:
    source = record(source="runtime:software-launch", observed=NOW.isoformat(), extra={
        "running_software_generation_observed": "sha256:" + "a" * 64,
        "startup_timestamp": NOW.isoformat(),
        "process_role": "maintenance_daemon",
    })
    source.update({"source_kind": "runtime_supervisor",
        "subject_kind": "observed_running_software_generation"})
    result = LongitudinalSelfModelOwner(tmp_path).reconcile(
        snapshot(source), tick_id="tick-software-launch")
    lifecycle = next(item for item in result.claims
        if item.predicate == "lifecycle.observation.disposition")
    assert lifecycle.claim_category == "historical_interpretation"



def test_conflicting_running_and_represented_generation_is_not_grouped(tmp_path: Path) -> None:
    source = record(source="runtime:software-conflict", extra={
        "running_software_generation_observed": "sha256:" + "a" * 64,
        "software_generation": "sha256:" + "b" * 64,
        "process_instance_id": "sha256:" + "c" * 64,
        "provenance_digest": "sha256:" + "d" * 64,
        "repository_commit": "commit-sha", "repository_tree": "tree-sha",
        "startup_timestamp": "2026-09-25T11:00:00Z",
        "process_identity_scope":
            "pid_startup_argv_executable_entrypoint_module_origin_and_environment",
        "software_generation_scope":
            "configured_manifest_and_clean_repository_state_at_observation",
        "loaded_code_identity_posture": "not_independently_attested",
        "currentness_posture": "owner_verified_process_and_source_at_observation",
        "event_time_posture": "owner_point_observation_time",
        "authority": False, "effect_proven": False})
    source.update({"source_kind": "runtime_supervisor",
        "subject_kind": "verified_current_running_software_generation",
        "evidence_strength": "owner_verified_current_process_and_clean_source"})
    result = LongitudinalSelfModelOwner(tmp_path).reconcile(
        snapshot(source), tick_id="tick-software-conflict")
    assert not any(item.predicate == "software_generation.current_process_observation"
        for item in result.claims)



def test_running_model_claim_carries_activation_predecessor_through_restart(tmp_path: Path) -> None:
    observed = "2026-09-25T11:59:00Z"
    source = record(source="runtime:model-session", observed=observed, extra={
        "running_model_identity_observed": {"model_id": "model-b", "artifact_id": "artifact-b"},
        "serving_session_id": "session-b",
        "activation_state_digest": "sha256:" + "a" * 64,
        "activation_receipt_id": "activation-b",
        "activation_receipt_semantic_digest": "sha256:" + "b" * 64,
        "activation_predecessor_state_digest": "sha256:" + "c" * 64,
        "activation_predecessor_posture": "verified_predecessor_state",
        "activation_generation": 8,
        "activation_history_digest": "sha256:" + "d" * 64,
        "activation_history_posture": "verified_selection_history_digest",
        "transition_id": "transition-b",
        "event_time_posture": "serving_session_observation_time_not_model_load_time",
        "model_development_provenance": {"posture": "identity_binding_verified",
            "provenance_manifest_digest": "sha256:" + "e" * 64},
        "authority": False, "effect_proven": False,
    })
    source.update({"source_kind": "runtime_supervisor",
        "subject_kind": "observed_running_model",
        "disposition": "observed",
        "evidence_strength": "serving_session_observation"})
    source["effect_claimed"] = False
    result = LongitudinalSelfModelOwner(tmp_path).reconcile(
        snapshot(source), tick_id="tick-model-session")
    claim = next(item for item in result.claims
        if item.predicate == "running_model_identity_observed")
    assert claim.value["model_id"] == "model-b"
    assert claim.value["activation_predecessor_state_digest"] == "sha256:" + "c" * 64
    assert claim.value["activation_predecessor_posture"] == "verified_predecessor_state"
    assert claim.value["observed_at"] == observed
    assert claim.value["model_development_provenance"]["posture"] == "identity_binding_verified"
    assert claim.current_truth is False

    restarted = LongitudinalSelfModelOwner(tmp_path)
    later = restarted.cognitive_projection(before_tick="tick-next", max_claims=8,
        allowed_predicates=("running_model_identity_observed",))
    assert later is not None
    retained = next(item for item in later.selected_claims
        if item["predicate"] == "running_model_identity_observed")
    assert retained["value"]["activation_predecessor_state_digest"] == "sha256:" + "c" * 64
    assert retained["value"]["activation_predecessor_posture"] == "verified_predecessor_state"
    assert retained["value"]["observed_at"] == observed



def test_transition_activation_predecessor_fields_remain_lineage_claims(tmp_path: Path) -> None:
    source = record(source="transition:activation", subject="transition-a", extra={
        "transition_id": "transition-a",
        "transition_phase": "b_activation_committed",
        "activation_state_digest": "sha256:" + "a" * 64,
        "activation_receipt_id": "activation-receipt-b",
        "activation_receipt_digest": "sha256:" + "b" * 64,
        "activation_predecessor_state_digest": "sha256:" + "c" * 64,
        "activation_predecessor_posture": "verified_predecessor_state",
        "activation_history_digest": "sha256:" + "d" * 64,
        "model_load_posture": "not_loaded_by_activation",
    })
    source.update({"source_kind": "runtime_supervisor",
        "subject_kind": "resident_model_transition",
        "evidence_strength": "digest_valid_transition_journal_entry"})
    result = LongitudinalSelfModelOwner(tmp_path).reconcile(
        snapshot(source), tick_id="tick-activation-lineage")
    predecessor = next(claim for claim in result.claims
        if claim.predicate == "activation_predecessor_state_digest")
    posture = next(claim for claim in result.claims
        if claim.predicate == "activation_predecessor_posture")
    assert predecessor.value == "sha256:" + "c" * 64
    assert posture.value == "verified_predecessor_state"
    assert predecessor.claim_category == posture.claim_category == "lineage"
    assert predecessor.current_truth is False and posture.current_truth is False


def test_software_transition_retention_is_historical_interpretation(tmp_path: Path) -> None:
    source = record(source="software-transition:retention", subject="transition-retention",
        observed=None, extra={"omitted_event_count": 12,
            "journal_head_digest": "head",
            "event_time_posture": "journal_retention_is_not_a_transition_event"})
    source.update({"source_kind": "runtime_supervisor",
        "subject_kind": "software_generation_transition_history_retention",
        "disposition": "bounded_tail"})
    result = LongitudinalSelfModelOwner(tmp_path).reconcile(
        snapshot(source), tick_id="tick-transition-retention")
    lifecycle = next(claim for claim in result.claims
        if claim.predicate == "lifecycle.observation.disposition")
    assert lifecycle.value == "bounded_tail"
    assert lifecycle.claim_category == "historical_interpretation"
    assert lifecycle.current_truth is False


def test_longitudinal_self_model_rejects_canonical_memory_root(tmp_path: Path) -> None:
    from sentientos.canonical_memory import sentientos_memory_dir

    with pytest.raises(LongitudinalSelfModelError,
                       match="self_model_root_overlaps_canonical_memory"):
        LongitudinalSelfModelOwner(sentientos_memory_dir())


def test_longitudinal_self_model_rejects_storage_inside_canonical_memory() -> None:
    from sentientos.canonical_memory import sentientos_memory_dir

    with pytest.raises(LongitudinalSelfModelError,
                       match="self_model_root_overlaps_canonical_memory"):
        LongitudinalSelfModelOwner(sentientos_memory_dir() / "retained-user-content")


def test_concurrent_self_model_writers_preserve_generation_predecessors(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(2)
    first_owner = LongitudinalSelfModelOwner(tmp_path / "self-model")
    second_owner = LongitudinalSelfModelOwner(tmp_path / "self-model")

    def reconcile(owner: LongitudinalSelfModelOwner, source_id: str):
        barrier.wait()
        return owner.reconcile(snapshot(record(source=source_id)), tick_id=f"tick-{source_id}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(reconcile, first_owner, "runtime:parallel-a")
        second = pool.submit(reconcile, second_owner, "runtime:parallel-b")
        first.result()
        second.result()

    history = first_owner.history()
    assert len(history) == 2
    assert [item.generation for item in history] == [1, 2]
    assert history[1].previous_reconciliation_id == history[0].reconciliation_id
    assert len({item.snapshot_id for item in history}) == 2


def test_parent_lifecycle_lineage_is_retained_as_non_authoritative_history(tmp_path: Path) -> None:
    lineage = {
        "parent_process_instance_id": "sha256:" + "a" * 64,
        "resident_config_digest": "sha256:" + "b" * 64,
        "child_spec_digest": "sha256:" + "c" * 64,
        "launch_receipt_digest": "sha256:" + "d" * 64,
        "generation_digest": "generation-proposed",
        "generation_posture": "launch_provenance_not_live_runtime_attestation",
        "current_truth": False, "authority": False, "effect_proven": False,
    }
    source = record(source="resident-parent:fixture", subject="parent-instance",
        extra={"parent_lifecycle_lineage": lineage})
    source["source_kind"] = "runtime_supervisor"
    source["subject_kind"] = "resident_parent_lifecycle_history"
    world = snapshot(source)
    result = LongitudinalSelfModelOwner(tmp_path / "self-model").reconcile(
        world, tick_id="tick-parent-lifecycle")
    claim = next(item for item in result.claims
        if item.predicate == "resident_parent_lifecycle_lineage")
    assert claim.value == lineage
    assert claim.claim_category == "historical_interpretation"
    assert claim.current_truth is False
    assert claim.status == "historical"
    assert claim.freshness == "unknown"
    assert claim.authority == {
        "decision_authority": False, "admission_authority": False,
        "execution_authority": False, "adoption_authority": False,
        "policy_authority": False, "goal_authority": False,
        "source_mutation_authority": False, "model_authorship_authority": False,
    }
