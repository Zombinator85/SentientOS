"""End-to-end controlled resource learning through the canonical evidence owners."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime as _datetime, timezone
from pathlib import Path
from types import MethodType

import pytest

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.developmental_model_replacement_experiment import ObjectivePredictionTask
from sentientos.governed_local_model_invocation import (
    GovernedLocalModelInvoker, validate_receipt,
)
from sentientos.governed_local_model_resource_allocation import (
    GovernedLocalModelResourceBounds, GovernedLocalModelResourcePolicy,
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
from sentientos.world_state_board import WorldStateBoardBuilder
from scripts.stage_resident_objective_intervention import stage_request
from tests.local_model_serving_fixture import FixturePatch, setup as serving_setup
from tests.test_production_chat_resource_provisioning_bundle_producer import inputs
from tests.test_resident_developmental_cognition import CONFIG_SCHEMA, owner, snapshot
from sentientos.resident_developmental_cognition import _task_family_history_examples

pytestmark = pytest.mark.no_legacy_skip


class SessionBoundGovernedFixture:
    """Attach a controlled session reference while retaining real governed receipts."""

    def __init__(self, invoker: GovernedLocalModelInvoker) -> None:
        self.invoker = invoker
        self.requests = []

    def build_request(self, **kwargs):
        linkage = dict(kwargs.pop("linkage", {}) or {})
        linkage["resident_cognitive_serving"] = {
            "session_id": "controlled-resource-session",
            "model_serving_admission_ref": "controlled-serving-admission",
            "activation_state_semantic_digest": "a" * 64,
            "session_receipt_id": "resident-serving-receipt-" + "b" * 24,
            "session_receipt_semantic_digest": "b" * 64,
        }
        request = self.invoker.build_request(linkage=linkage, **kwargs)
        self.requests.append(request)
        return request

    def invoke(self, request, **kwargs):
        return self.invoker.invoke(request, **kwargs)

    def verify_persisted_invocation_receipt(self, receipt_id, receipt_digest, **expected):
        path = self.invoker.runtime_root / "receipts" / (receipt_id + ".json")
        value = json.loads(path.read_text(encoding="utf-8"))
        valid, reasons = validate_receipt(value)
        assert valid, reasons
        assert value["receipt_id"] == receipt_id
        assert value["receipt_digest"] == receipt_digest
        request = value["request"]
        assert request["request_id"] == expected["expected_request_id"]
        assert request["request_digest"] == expected["expected_request_digest"]
        assert request["active_model_identity"] == expected["expected_active_model_identity"]
        assert request["linkage"]["resident_cognitive_serving"] == {
            "session_id": expected["expected_session_id"],
            **expected["expected_session_binding"],
            "session_receipt_id": expected["expected_session_receipt_id"],
            "session_receipt_semantic_digest": expected["expected_session_receipt_digest"],
        }
        return value


def _run_recovered_heldout(root: Path, staged_digest: str) -> dict:
    """Called by a separate interpreter with only durable owner roots."""
    from sentientos.resident_developmental_cognition import (
        load_objective_request, objective_task_for_request,
    )
    fixture_patch = FixturePatch()
    _, _, _, model, kernel, _ = serving_setup(fixture_patch, root / "model",
        installation_identity="production", state_root=root / "child-serving-state")
    artifact = root / "model" / "exact.gguf"
    config = ModelConfig([ModelCandidate(artifact, "llama_cpp", "catalog-model",
        {"gpu_layers": 0})], default_engine="llama_cpp", max_context_tokens=512,
        generation=GenerationConfig(max_new_tokens=8, temperature=0, top_p=1))
    authority = build_local_model_authority_map(config, allowed_roots=[root / "model"],
        observed_at="1970-01-01T00:00:00+00:00")
    def generate(self, prompt, **kwargs):
        self.calls += 1
        body = json.loads(prompt)
        if "objective_task" in body:
            examples = [item for packet in body["developmental_history"]
                for experience in packet.get("task_relevant_experience", ())
                for item in experience.get("examples", ())]
            probes = body["objective_task"]["probe_inputs"]
            if len(examples) >= 2:
                x1, y1 = examples[0]["probe_input"], examples[0]["observed_answer"]
                x2, y2 = examples[1]["probe_input"], examples[1]["observed_answer"]
                slope = (y2 - y1) // (x2 - x1)
                answers = [slope * (x - x1) + y1 for x in probes]
            else:
                answers = [0 for _ in probes]
            return json.dumps({"answers": answers}, sort_keys=True,
                separators=(",", ":"))
        return json.dumps({"interpretation": "bounded recovered fixture",
            "uncertainty": "medium"}, sort_keys=True)
    model.generate = MethodType(generate, model)
    invoker = SessionBoundGovernedFixture(GovernedLocalModelInvoker(
        model=model, authority_map=authority, kernel=kernel,
        runtime_root=root / "invocations"))
    cognition, _ = owner(root / "resident", comparison=True, invoker=invoker,
        allowed_source_kinds=("capability_registry", "embodiment", "resource_governor"),
        max_selected_facts=16)
    request = load_objective_request(root / "resident" / "state")
    assert request is not None and request["request_digest"] == staged_digest
    task = objective_task_for_request(request)
    result = cognition.run_objective_intervention_once(snapshot=snapshot(),
        tick_id=request["request_id"], objective_task=task,
        request_id=request["request_id"], request_digest=staged_digest)
    run = cognition.experiments.load_run(result.changed_cognition_measurement_id)
    prompts = {request.correlation_id.rsplit(":", 1)[-1]: json.loads(request.prompt)
        for request in invoker.requests
        if request.purpose == "resident_developmental_history_intervention_experiment"
        and request.prompt.lstrip().startswith("{")}
    return {"run": run, "prompts": prompts, "new_purposes": [request.purpose
        for request in invoker.requests], "new_calls": model.calls}


def test_governed_three_condition_resource_learning_survives_admission(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, suffix in (
            ("SENTIENTOS_GOVERNOR_ROOT", "governor"),
            ("SENTIENTOS_RUNTIME_STATE_ROOT", "runtime"),
            ("SENTIENTOS_FEDERATION_ROOT", "federation"),
            ("SENTIENTOS_REPO_ROOT", "repo"),
            ("PULSE_TRUST_EPOCH_ROOT", "trust")):
        monkeypatch.setenv(name, str(tmp_path / suffix))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(tmp_path / "trust" / "state.json"))
    installation, provisioning_inputs = inputs(tmp_path, calls=3)
    bounds = GovernedLocalModelResourceBounds(65536, 32768, 512, 30.0, 3)
    policy = GovernedLocalModelResourcePolicy.create(epoch=1,
        max_resource_specific_bounds=bounds, not_before="2026-09-21T08:00:00Z",
        valid_until="2026-09-21T09:15:00Z")
    provisioning_inputs["requested_bounds"] = bounds
    provisioning_inputs["resource_policy_artifact"] = (
        json.dumps(policy.to_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode()
    produce_production_chat_resource_provisioning_bundle(
        installation, "developmental-learning", **provisioning_inputs)
    nonce_values = iter(("developmental-present", "developmental-withheld",
        "developmental-restored"))
    resource_owner = load_production_chat_resource_context_owner(
        installation, "developmental-learning", clock=lambda: "2026-09-21T08:30:00Z",
        nonce_source=lambda: next(nonce_values))

    _, _, _, model, kernel, _ = serving_setup(monkeypatch, tmp_path / "model",
        installation_identity="production", state_root=tmp_path / "serving-state")
    artifact = tmp_path / "model" / "exact.gguf"
    config = ModelConfig([ModelCandidate(artifact, "llama_cpp", "catalog-model",
        {"gpu_layers": 0})], default_engine="llama_cpp", max_context_tokens=512,
        generation=GenerationConfig(max_new_tokens=8, temperature=0, top_p=1))
    authority = build_local_model_authority_map(config,
        allowed_roots=[tmp_path / "model"], observed_at="1970-01-01T00:00:00+00:00")
    def generate(self, prompt, **kwargs):
        self.calls += 1
        body = json.loads(prompt)
        if "objective_task" in body:
            probes = body["objective_task"]["probe_inputs"]
            has_history = bool(body["developmental_history"]) and self.calls == 2
            return json.dumps({"answers": [3 * x + 2 if has_history else 0
                for x in probes]}, sort_keys=True, separators=(",", ":"))
        return json.dumps({"interpretation": "input 1 produced 5; input 2 produced 8",
            "uncertainty": "medium"}, sort_keys=True)
    model.generate = MethodType(generate, model)
    import sentientos.governed_local_model_invocation as invocation_module
    class ControlledEventTime(_datetime):
        @classmethod
        def now(cls, tz=None):
            return _datetime(2026, 9, 21, 8, 30, tzinfo=tz or timezone.utc)
    monkeypatch.setattr(invocation_module, "datetime", ControlledEventTime)
    governed = GovernedLocalModelInvoker(model=model, authority_map=authority,
        kernel=kernel, runtime_root=tmp_path / "invocations")
    invoker = SessionBoundGovernedFixture(governed)
    root = tmp_path / "resident"
    cognition, _ = owner(root, comparison=True, invoker=invoker,
        allowed_source_kinds=("capability_registry", "embodiment", "resource_governor"),
        max_selected_facts=16)
    assert cognition.run_tick(snapshot=snapshot(), tick_id="resource-learning-seed").written_record_id
    cognition, _ = owner(root, comparison=True, invoker=invoker,
        allowed_source_kinds=("capability_registry", "embodiment", "resource_governor"),
        max_selected_facts=16, resource_context_owner=resource_owner)
    config_path = tmp_path / "objective-config.json"
    config_path.write_text(json.dumps({"schema": CONFIG_SCHEMA, "enabled": True,
        "history_root": str(root / "history"), "state_root": str(root / "state"),
        "allowed_source_kinds": ["capability_registry", "embodiment", "resource_governor"],
        "max_selected_facts": 16, "max_retrieved_records": 4,
        "comparison_enabled": True}), encoding="utf-8")
    task = ObjectivePredictionTask(3, 2, 7, (8, 9),
        task_family_id="integer_affine_prediction")
    _, staged, _ = stage_request(config_path=config_path,
        request_id="resource-learning-acquisition", task=task)
    result = cognition.run_objective_intervention_once(snapshot=snapshot(),
        tick_id="resource-learning-acquisition", objective_task=task,
        request_id="resource-learning-acquisition",
        request_digest=staged["request_digest"])
    run = cognition.experiments.load_run(result.changed_cognition_measurement_id)
    assert [row["condition_id"] for row in run["conditions"]] == [
        "history_present", "history_withheld", "history_restored"]
    assert resource_owner.allocator.ledger.remaining_calls(
        resource_owner.allocation.allocation_id) == 0
    source_records = cognition.experiments.world_state_records(
        run_refs=((run["run_id"], run["run_digest"]),))
    assert len(source_records) == 1
    assert source_records[0]["payload"]["independent_backend_observation"] is False
    assert source_records[0]["payload"]["execution_evidence_posture"] == (
        "all_owner_receipts_report_backend_entry")
    receipts = [json.loads((tmp_path / "invocations" / "receipts" /
        (condition["inference_receipt_id"] + ".json")).read_text(encoding="utf-8"))
        for condition in run["conditions"]]
    resource_records = resource_consumption_world_state_records(
        ledger=resource_owner.allocator.ledger, invocation_receipts=receipts)
    joined = resource_invocation_proposal_lineage_records(
        [*source_records, *resource_records])
    missing = resource_invocation_proposal_lineage_records(source_records)
    assert len(missing) == 3
    assert all(row["disposition"] == "degraded" and
        "resource_invocation_projection_missing_or_ambiguous" in
        row["payload"]["lineage_findings"] for row in missing)
    lineage = [row for row in joined if row["subject_kind"] ==
        "developmental_history_invocation_resource_lineage"]
    assert len(lineage) == 3
    assert all(row["disposition"] == "verified" for row in lineage)
    board = WorldStateBoardBuilder().build([*source_records, *lineage])
    cognition, _ = owner(root, comparison=True, invoker=invoker,
        allowed_source_kinds=("capability_registry", "embodiment", "resource_governor"),
        max_selected_facts=16)
    feedback = cognition.run_tick(snapshot=board, tick_id="resource-learning-feedback")
    admitted = cognition.writeback.store.get(feedback.written_record_id)
    assert len([fact for fact in admitted.candidate["selected_facts"]
        if fact["subject"]["subject_kind"] ==
        "developmental_history_invocation_resource_lineage"]) == 3
    examples = _task_family_history_examples(admitted.candidate,
        task_family_id="integer_affine_prediction")
    assert len(examples) == 1
    assert [row["resource_context"]["posture"] for row in
        examples[0]["condition_outcomes"]] == ["verified_ledger_receipt_values"] * 3
    assert examples[0]["resource_strategy_recommendation"]["posture"] == (
        "bounded_recommendation")
    recommendation = examples[0]["resource_strategy_recommendation"]
    assert recommendation["recommendation"]["condition_id"] == "history_present"
    assert recommendation["recommendation"]["correct_count"] == 3
    assert recommendation["recommendation"]["call_units_consumed"] == 2
    before_ledger = resource_owner.allocator.ledger.path.read_bytes()

    heldout = ObjectivePredictionTask(3, 2, 10, (11, 12),
        task_family_id="integer_affine_prediction", requires_task_family_history=True)
    _, heldout_request, _ = stage_request(config_path=config_path,
        request_id="resource-learning-heldout", task=heldout)
    child = subprocess.run([sys.executable, "-c",
        "import json,sys; from pathlib import Path; "
        "from tests.test_developmental_resource_learning_integration import _run_recovered_heldout; "
        "print(json.dumps(_run_recovered_heldout(Path(sys.argv[1]), sys.argv[2]), sort_keys=True))",
        str(tmp_path), heldout_request["request_digest"]],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    assert child.returncode == 0, child.stderr[-4000:]
    recovered = json.loads(child.stdout.strip().splitlines()[-1])
    present_prompt = recovered["prompts"]["history_present"]
    [historical] = [item for packet in present_prompt["developmental_history"]
        for item in packet.get("task_relevant_experience", ())]
    assert historical["source_run_id"] == run["run_id"]
    assert historical["source_run_digest"] == run["run_digest"]
    assert historical["resource_strategy_recommendation"]["recommendation_digest"] == (
        recommendation["recommendation_digest"])
    assert historical["resource_strategy_recommendation"]["recommendation"] == (
        recommendation["recommendation"])
    assert not recovered["prompts"]["history_withheld"]["developmental_history"]
    later_scores = {row["condition_id"]: row["score"] for row in
        recovered["run"]["objective_scores"]}
    assert later_scores["history_present"]["correct_count"] == 3
    assert later_scores["history_withheld"]["correct_count"] == 0
    assert later_scores["history_restored"]["correct_count"] == 3
    # Independently fixed criterion: the recommended treatment must clear the
    # held-out full-suite quality requirement; costs remain historical evidence.
    assert later_scores[recommendation["recommendation"]["condition_id"]][
        "correct_count"] >= 3
    assert recovered["new_calls"] == 3
    assert recovered["new_purposes"].count(
        "resident_developmental_history_intervention_experiment") == 4
    assert resource_owner.allocator.ledger.path.read_bytes() == before_ledger
    assert cognition.experiments.world_state_records(
        run_refs=((run["run_id"], run["run_digest"]),)) == source_records
    assert resource_owner.allocator.ledger.path.read_bytes() == before_ledger
