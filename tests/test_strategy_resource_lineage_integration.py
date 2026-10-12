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
    installation, provisioning_inputs = inputs(tmp_path, calls=3)
    bounds = GovernedLocalModelResourceBounds(8192, 8192, 32, 5.0, 3)
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
    nonce_values = iter(("strategy-attempt-1", "strategy-attempt-2", "strategy-attempt-3"))
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
    assert resource_owner.allocator.ledger.remaining_calls(resource_owner.allocation.allocation_id) == 0

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
    resource_owner.close()
    serving.close()
    fixture_patch.undo()
