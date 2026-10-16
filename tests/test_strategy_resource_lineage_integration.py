from __future__ import annotations

import json
from pathlib import Path
from types import MethodType
from datetime import datetime as _datetime, timezone

import pytest

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.embodied_consequence import (
    ConsequenceStore,
    GovernedStrategyCognitionBackend,
    make_strategy_proposal,
    run_strategy_experiment,
    strategy_prompt_schema_digest,
)
from sentientos.governed_local_model_invocation import (
    GovernedLocalModelInvoker,
    LocalModelInvocationBudget,
)
from sentientos.governed_local_model_resource_allocation import (
    GovernedLocalModelResourceBounds,
    GovernedLocalModelResourcePolicy,
)
from sentientos.host_resource_runtime import (
    resource_consumption_world_state_records,
    resource_invocation_proposal_lineage_records,
)
from sentientos.local_model_authority import build_local_model_authority_map
from sentientos.world_state_board import record_digest
from sentientos.production_chat_resource_provisioning import load_production_chat_resource_context_owner
from sentientos.production_chat_resource_provisioning_bundle_producer import (
    produce_production_chat_resource_provisioning_bundle,
)
from tests.local_model_serving_fixture import FixturePatch, setup as serving_setup
from tests.test_embodied_consequence import TX, chain
from tests.test_production_chat_resource_provisioning_bundle_producer import inputs

pytestmark = pytest.mark.no_legacy_skip


def _history_record(attribution: dict[str, object]) -> dict[str, object]:
    fact = {
        "fact_id": "fact:causal",
        "source": {
            "source_id": attribution["attribution_id"],
            "digest": attribution["attribution_digest"],
            "schema_version": attribution["schema_version"],
            "kind": "embodiment",
        },
        "subject": {"subject_id": "body-a", "subject_kind": "embodied_consequence_attribution"},
        "payload": attribution,
    }
    record: dict[str, object] = {
        "candidate": {
            "epistemic_posture": "historical_interpretation_not_current_truth",
            "selected_fact_ids": [fact["fact_id"]],
            "selected_facts": [fact],
        },
        "created_at": TX,
        "current_truth": False,
        "authority": False,
        "policy": False,
    }
    from sentientos.embodied_consequence import digest

    record["record_digest"] = digest(record)
    record["record_id"] = "devrec-" + str(record["record_digest"])[7:31]
    return record


def test_resource_linked_strategy_proposals_join_to_reconciled_ledger(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(tmp_path / "trust"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(tmp_path / "trust" / "state.json"))
    installation, provisioning_inputs = inputs(tmp_path, calls=4)
    bounds = GovernedLocalModelResourceBounds(8192, 8192, 32, 5.0, 4)
    policy = GovernedLocalModelResourcePolicy.create(
        epoch=1,
        max_resource_specific_bounds=bounds,
        not_before="2026-09-21T08:00:00Z",
        valid_until="2026-09-21T09:15:00Z",
    )
    provisioning_inputs["requested_bounds"] = bounds
    provisioning_inputs["resource_policy_artifact"] = (
        json.dumps(policy.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    produce_production_chat_resource_provisioning_bundle(
        installation, "strategy-lineage", **provisioning_inputs
    )
    nonce_values = iter(("strategy-attempt-1", "strategy-attempt-2", "strategy-attempt-3",
        "developmental-history-attempt"))
    resource_owner = load_production_chat_resource_context_owner(
        installation,
        "strategy-lineage",
        clock=lambda: "2026-09-21T08:30:00Z",
        nonce_source=lambda: next(nonce_values),
    )

    fixture_patch = FixturePatch()
    bridge, serving, _session, model, fixture_kernel, _current = serving_setup(
        fixture_patch,
        tmp_path / "model",
        installation_identity="production",
        state_root=tmp_path / "state",
        serving_operation_id="strategy-lineage-serving",
    )
    artifact = tmp_path / "model" / "exact.gguf"
    config = ModelConfig(
        [ModelCandidate(artifact, "llama_cpp", "catalog-model", {"gpu_layers": 0})],
        default_engine="llama_cpp",
        max_context_tokens=512,
        generation=GenerationConfig(max_new_tokens=8, temperature=0, top_p=1),
    )
    authority = build_local_model_authority_map(
        config,
        allowed_roots=[tmp_path / "model"],
        observed_at="1970-01-01T00:00:00+00:00",
    )
    model_id = authority.records[0].model_id
    budget = LocalModelInvocationBudget(8192, 8192, 32, 5.0, 1)
    invoker = GovernedLocalModelInvoker(
        model=model,
        authority_map=authority,
        # Narrow deterministic local-inference admission fixture; the governed
        # invoker, resource allocator/ledger, receipt verifier, and evidence
        # owners remain production implementations.
        kernel=fixture_kernel,
        runtime_root=tmp_path / "invocations",
    )
    situation = {"situation_binding": "resource-lineage-situation"}
    proposal = make_strategy_proposal(
        situation_binding=situation["situation_binding"],
        body_generation=2,
        relevant_consequence_ids=(),
        proposed_next_action_class="observe",
        requested_pose="wave",
        requested_expression="neutral",
        retry_prior_strategy=False,
        alter_body_or_rig=False,
        more_observation_required=True,
        distinguishes_renderer_and_observer=True,
        rationale="bounded controlled fixture proposal",
        uncertainty="high",
        factual_assertions=(),
    )
    output = json.dumps(
        {
            key: getattr(proposal, key)
            for key in (
                "situation_binding", "body_generation", "proposed_next_action_class",
                "requested_pose", "requested_expression", "retry_prior_strategy",
                "alter_body_or_rig", "more_observation_required",
                "distinguishes_renderer_and_observer", "rationale", "uncertainty",
                "relevant_consequence_ids", "factual_assertions",
            )
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    def generate(self, prompt, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        return output
    model.generate = MethodType(generate, model)
    import sentientos.governed_local_model_invocation as invocation_module
    class ControlledEventTime(_datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            return _datetime(2035, 1, 3, tzinfo=tz or timezone.utc)
    monkeypatch.setattr(invocation_module, "datetime", ControlledEventTime)
    backend = GovernedStrategyCognitionBackend(
        invoker=invoker,
        model_id=model_id,
        model_artifact_digest=authority.records[0].model_content_sha256,
        inference_budget=budget.to_dict(),
        caller="controlled-resource-lineage-fixture",
        resource_context_owner=resource_owner,
    )
    *_, attribution, _comparison = chain()
    record = _history_record(attribution)
    protocol = {
        "protocol_id": "resource-lineage-protocol",
        "snapshot_digest": "sha256:" + "a" * 64,
        "body_generation": 2,
        "model_id": model_id,
        "model_artifact_digest": authority.records[0].model_content_sha256,
        "inference_budget_digest": __import__("sentientos.embodied_consequence", fromlist=["digest"]).digest(budget.to_dict()),
        "prompt_schema_digest": strategy_prompt_schema_digest(),
        "renderer_situation_digest": __import__("sentientos.embodied_consequence", fromlist=["digest"]).digest(situation),
        "software_generation": "fixture-generation-not-runtime-attestation",
        "environment_fixture_digest": "sha256:" + "b" * 64,
    }
    store = ConsequenceStore(tmp_path / "strategy-evidence")
    result = run_strategy_experiment(
        protocol=protocol,
        history_record=record,
        situation=situation,
        backend=backend,
        consequence=attribution,
        store=store,
    )
    assert result["experiment_completion_posture"] == "completed", result
    assert model.calls == 3
    assert resource_owner.allocator.ledger.remaining_calls(resource_owner.allocation.allocation_id) == 1

    evidence_owner = ConsequenceStore(tmp_path / "strategy-evidence")
    experiment_records = evidence_owner.world_state_records(
        experiment_result_ids=(result["experiment_result_id"],)
    )
    review_records = evidence_owner.strategy_proposal_review_records(
        experiment_result_ids=(result["experiment_result_id"],)
    )
    assert len(review_records) == 3
    invocations = tuple(
        row["invocation_receipt"]
        for row in result["execution_evidence"]
        if isinstance(row.get("invocation_receipt"), dict)
    )
    assert len(invocations) == 3
    resource_records = resource_consumption_world_state_records(
        ledger=resource_owner.allocator.ledger,
        invocation_receipts=invocations,
    )
    joined = resource_invocation_proposal_lineage_records([*resource_records, *experiment_records])
    assert len(joined) == 3
    assert all(row["disposition"] == "verified" for row in joined)
    assert all(row["effect_proven"] is False and row["effect_claimed"] is False for row in joined)
    assert all(row["payload"]["shared_host_cpu_gpu_attribution"] == "unknown_without_independent_observation" for row in joined)
    assert {row["payload"]["principal_id"] for row in joined} == {resource_owner.principal.principal_id}

    incomplete = resource_invocation_proposal_lineage_records(experiment_records)
    assert len(incomplete) == 3
    assert all(row["disposition"] == "degraded" for row in incomplete)
    assert all("resource_invocation_projection_missing_or_ambiguous" in row["payload"]["lineage_findings"] for row in incomplete)

    # A further governed local call supplies genuine resource custody for the
    # developmental-history join. The surrounding run row is only a bounded
    # source-record fixture; this does not claim a real developmental episode.
    developmental_request = invoker.build_request(
        purpose="resident_developmental_history_intervention_experiment",
        prompt='{"condition":"history_present","task_family_id":"fixture-affine"}',
        caller="controlled-developmental-resource-join-fixture",
        correlation_id="fixture-developmental-resource-join",
        lifecycle_phase="runtime", expected_output_format="json", budget=budget,
        upstream_evidence={"fixture_scope": "resource-join-contract-only"},
        linkage={"experiment_condition": "history_present",
            "experiment_protocol_id": "fixture-protocol"})
    developmental_receipt = invoker.invoke(developmental_request, persist=True,
        include_output_in_receipt=False, resource_context=resource_owner.next_context())
    assert developmental_receipt.status == "admitted_completed"
    developmental_value = developmental_receipt.to_dict()
    condition = {
        "condition_id": "history_present", "observation_id": "fixture-observation",
        "observation_digest": "fixture-observation-digest",
        "output_digest": developmental_receipt.output_digest,
        "request_id": developmental_receipt.request["request_id"],
        "request_digest": developmental_receipt.request["request_digest"],
        "inference_receipt_id": developmental_receipt.receipt_id,
        "inference_receipt_digest": developmental_receipt.receipt_digest,
        "model_id": developmental_request.model_id,
        "model_artifact_digest": developmental_request.model_artifact_digest,
        "authority_map_digest": developmental_request.authority_map_digest,
        "active_model_identity": {}, "retrieved_record_ids": [],
        "retrieved_record_digests": [], "serving_session_id": None,
        "observed_at": developmental_receipt.observed_at,
        "resource_allocation_digest": developmental_receipt.resource_allocation_digest,
        "resource_attempt_id": developmental_receipt.resource_attempt_id,
        "resource_consumption_receipt_digests": list(
            developmental_receipt.resource_consumption_receipt_digests),
        "resource_linkage_digest": developmental_receipt.resource_linkage_digest,
    }
    developmental_payload = {
        "run_id": "fixture-developmental-resource-run",
        "run_digest": "fixture-run-digest",
        "protocol_id": "fixture-protocol", "protocol_digest": "fixture-protocol-digest",
        "history_record_ids": [], "history_record_digests": [],
        "model_id": developmental_request.model_id,
        "model_artifact_digest": developmental_request.model_artifact_digest,
        "active_model_identity": {}, "authority_map_digest": developmental_request.authority_map_digest,
        "conditions": [condition],
        "objective_task_descriptor": {"task_family_id": "fixture-affine", "probe_count": 2},
        "objective_scores": [{"condition_id": "history_present",
            "score_digest": "sha256:" + "a" * 64, "status": "correct",
            "correct": True, "correct_count": 2, "probe_count": 2}],
    }
    developmental_record = {"source_kind": "embodiment",
        "source_id": "fixture-developmental-run", "subject_id": "fixture-developmental-resource-run",
        "subject_kind": "developmental_history_intervention_experiment",
        "stage": "observation", "disposition": "fixture_only",
        "payload": developmental_payload}
    developmental_record["digest"] = record_digest(developmental_record)
    all_resource_records = resource_consumption_world_state_records(
        ledger=resource_owner.allocator.ledger,
        invocation_receipts=[*invocations, developmental_value])
    developmental_join = resource_invocation_proposal_lineage_records(
        [*all_resource_records, developmental_record])
    [history_lineage] = [row for row in developmental_join
        if row["subject_kind"] == "developmental_history_invocation_resource_lineage"]
    assert history_lineage["disposition"] == "verified", history_lineage["payload"]["lineage_findings"]
    assert history_lineage["payload"]["task_family_id"] == "fixture-affine"
    outcome = history_lineage["payload"]["task_outcome"]
    assert outcome == {"posture": "run_owner_score_bound_to_condition",
        "condition_id": "history_present",
        "inference_receipt_id": developmental_receipt.receipt_id,
        "inference_receipt_digest": developmental_receipt.receipt_digest,
        "output_digest": developmental_receipt.output_digest,
        "score_digest": "sha256:" + "a" * 64, "score_status": "correct",
        "correct": True, "correct_count": 2, "probe_count": 2,
        "oracle_answer_retained": False, "causal_effect_established": False}
    assert history_lineage["payload"]["resource_measurement_posture"] == "verified_ledger_receipt_values"
    measurement_rows = history_lineage["payload"]["resource_consumption_evidence"]
    assert len(measurement_rows) == 2
    assert all(row["measured_values"]["call_units_consumed"] == 1
        for row in measurement_rows)
    assert all(row["measurement_posture"]["token_count"] == "unknown"
        and row["measurement_posture"]["shared_host_cpu_gpu"]
            == "unknown_without_independent_observation" for row in measurement_rows)

    # The attributed source is consumable by the existing World-State and
    # developmental writeback owners; the interpreting model remains a test
    # fixture, and its lesson remains separately admitted historical context.
    from sentientos.world_state_board import WorldStateBoardBuilder
    from tests.test_resident_developmental_cognition import owner as cognition_owner
    from sentientos.resident_developmental_writeback import DevelopmentalWritebackError
    board = WorldStateBoardBuilder().build([history_lineage])
    cognition, fixture_model = cognition_owner(tmp_path / "cognition",
        allowed_source_kinds=("resource_governor",), max_selected_facts=16)
    substituted_outcome = json.loads(json.dumps(history_lineage))
    substituted_outcome["payload"]["task_outcome"]["inference_receipt_id"] = "substituted"
    substituted_outcome["digest"] = record_digest(substituted_outcome)
    substituted_board = WorldStateBoardBuilder().build([substituted_outcome])
    with pytest.raises(DevelopmentalWritebackError,
            match="resource_task_outcome_projection_binding_invalid"):
        cognition.writeback.select_evidence(substituted_board,
            fact_ids=tuple(fact.fact_id for fact in substituted_board.facts))
    cognition_result = cognition.run_tick(snapshot=board,
        tick_id="resource-lineage-developmental-interpretation")
    assert cognition_result.written_record_id
    admitted = cognition.writeback.store.get(cognition_result.written_record_id)
    assert any(fact["subject"]["subject_kind"]
            == "developmental_history_invocation_resource_lineage"
        and fact["payload"]["resource_measurement_posture"] == "verified_ledger_receipt_values"
        and fact["payload"]["task_outcome"]["score_digest"] == outcome["score_digest"]
        for fact in admitted.candidate["selected_facts"])
    admitted_lineage = next(fact for fact in admitted.candidate["selected_facts"]
        if fact["subject"]["subject_kind"]
            == "developmental_history_invocation_resource_lineage")
    retained_measurements = admitted_lineage["payload"]["resource_consumption_evidence"]
    assert len(retained_measurements) == len(measurement_rows)
    assert all(retained["receipt_id"] == observed["receipt_id"]
        and retained["receipt_digest"] == observed["receipt_digest"]
        and retained["measured_values"]["call_units_consumed"]
            == observed["measured_values"]["call_units_consumed"]
        and retained["measurement_posture"].get("token_count")
            == observed["measurement_posture"].get("token_count")
        for retained, observed in zip(retained_measurements, measurement_rows))
    assert all(row["receipt_digest"] in admitted_lineage["payload"]["resource_linkage"][
        "consumption_receipt_digests"] for row in admitted_lineage["payload"][
            "resource_consumption_evidence"])
    assert fixture_model.requests

    # A self-rehashed source record cannot turn an unknown score status into a
    # qualified outcome. Resource custody remains visible, while the outcome
    # is excluded from developmental interpretation.
    invalid_score = json.loads(json.dumps(developmental_record))
    invalid_score["payload"]["objective_scores"][0]["status"] = "scored"
    invalid_score["digest"] = record_digest(invalid_score)
    invalid_join = resource_invocation_proposal_lineage_records(
        [*all_resource_records, invalid_score])
    invalid_history = next(row for row in invalid_join
        if row["subject_kind"] == "developmental_history_invocation_resource_lineage")
    assert invalid_history["disposition"] == "degraded"
    assert "developmental_experiment_condition_score_invalid" in \
        invalid_history["payload"]["lineage_findings"]
    assert invalid_history["payload"]["task_outcome"] == {
        "posture": "score_binding_invalid"}

    incomplete_family_score = json.loads(json.dumps(developmental_record))
    incomplete_family_score["payload"]["objective_scores"][0]["correct_count"] = None
    incomplete_family_score["payload"]["objective_scores"][0]["probe_count"] = None
    incomplete_family_score["digest"] = record_digest(incomplete_family_score)
    incomplete_join = resource_invocation_proposal_lineage_records(
        [*all_resource_records, incomplete_family_score])
    incomplete_history = next(row for row in incomplete_join
        if row["subject_kind"] == "developmental_history_invocation_resource_lineage")
    assert incomplete_history["disposition"] == "degraded"
    assert "developmental_experiment_condition_score_invalid" in \
        incomplete_history["payload"]["lineage_findings"]
    assert incomplete_history["payload"]["task_outcome"] == {
        "posture": "score_binding_invalid"}

    substituted = json.loads(json.dumps(developmental_record))
    substituted["payload"]["conditions"][0]["resource_attempt_id"] = "substituted-attempt"
    substituted["digest"] = record_digest(substituted)
    degraded = resource_invocation_proposal_lineage_records(
        [*all_resource_records, substituted])
    degraded_history = next(row for row in degraded
        if row["subject_kind"] == "developmental_history_invocation_resource_lineage")
    assert degraded_history["disposition"] == "degraded"
    assert "resource_invocation_linkage_substitution" in degraded_history["payload"]["lineage_findings"]
    assert degraded_history["payload"]["resource_measurement_posture"] == \
        "unknown_unverified_or_missing_lineage"
    partial = json.loads(json.dumps(developmental_record))
    partial["payload"]["conditions"][0]["resource_linkage_digest"] = None
    partial["digest"] = record_digest(partial)
    incomplete_linkage = resource_invocation_proposal_lineage_records(
        [*all_resource_records, partial])
    partial_history = next(row for row in incomplete_linkage
        if row["subject_kind"] == "developmental_history_invocation_resource_lineage")
    assert partial_history["disposition"] == "degraded"
    assert "resource_invocation_linkage_substitution" in partial_history["payload"]["lineage_findings"]
    assert partial_history["payload"]["resource_consumption_evidence"] == []
    assert resource_owner.allocator.ledger.remaining_calls(resource_owner.allocation.allocation_id) == 0
    resource_owner.close()
    serving.close()
    fixture_patch.undo()
