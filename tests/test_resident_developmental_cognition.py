from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Iterator, Mapping

import pytest
import scripts.doctor_resident_objective_experiment as readiness

from sentientos.codex_task_authority_admission import RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION
from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore, DevelopmentalHistoryInterventionError,
)
from sentientos.developmental_model_replacement_experiment import ObjectivePredictionTask
from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import AuthorityClass, ControlPlaneKernel, LifecyclePhase
from sentientos.host_collectors import HostCollectorResult
from sentientos.host_resource_runtime import (
    HostObservationCollectorSpec, HostResourceRuntimeCoordinator,
    build_observation_plan, world_state_records,
)
from sentientos.governed_local_model_invocation import (
    GovernedLocalModelInvoker, LocalModelInvocationBudget, LocalModelInvocationReceipt,
    FORBIDDEN_EFFECTS,
)
from sentientos.local_model_authority import build_local_model_authority_map
from sentientos.local_model_authority import digest_payload
from sentientos.resident_developmental_cognition import (
    CONFIG_SCHEMA, ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionError,
    ResidentDevelopmentalCognitionOwner, load_config, _bind_epistemic_context,
    load_objective_request, objective_task_for_request, stage_objective_request,
    stored_objective_request_disposition, stored_objective_request_record,
)
from sentientos.resident_developmental_writeback import (
    DevelopmentalWritebackError, ResidentDevelopmentalWritebackController,
)
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.resident_cognitive_model_serving import CONFIG_SCHEMA as SERVING_CONFIG_SCHEMA
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from sentientos.runtime_governor import reset_runtime_governor
from sentientos.federated_governance import reset_controller as reset_federated_governance
from sentientos.pulse_trust_epoch import reset_manager as reset_pulse_trust_epoch
from sentientos.trust_ledger import reset_trust_ledger
from sentientos.integrity_quarantine import QuarantineState, save_state
from sentientos.integrity_incident import build_incident, write_incident
from sentientos.world_state_board import WorldStateBoardBuilder
from sentientos.embodied_consequence import (
    WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V4, digest as embodied_digest,
)
from sentientosd import (
    RuntimeMaintenanceSurfaces,
    _attestation_snapshot_verification_world_state_record,
    _load_embodied_consequence_projection,
    _load_epistemic_state_owner,
)
from sentientos.persistent_epistemic_state import (PersistentEpistemicStateOwner,
    make_proposition, make_evidence_binding, make_cognitive_projection,
    MeaningBearingEpistemicCognitiveProjection)

pytestmark = pytest.mark.no_legacy_skip


def snapshot(value: int = 1):
    return WorldStateBoardBuilder().build([
        {"source_id":"source-b", "source_kind":"audit_trust", "subject_id":"b", "stage":"observation", "disposition":"recorded", "observed_at":"2026-01-01T00:00:00+00:00", "payload":{"value":9}},
        {"source_id":"source-a", "source_kind":"capability_registry", "subject_id":"a", "stage":"observation", "disposition":"recorded", "observed_at":"2026-01-01T00:00:00+00:00", "payload":{"value":value}},
        {"source_id":"source-c", "source_kind":"capability_registry", "subject_id":"c", "stage":"observation", "disposition":"recorded", "observed_at":"2026-01-01T00:00:00+00:00", "payload":{"value":3}},
    ])


class FakeInvoker:
    def __init__(self) -> None:
        self.requests = []
        self.lesson_statement = "When prior evidence conflicts, preserve its scope and uncertainty."
        self.lesson_scope = "historical evidence interpretation"
        self.lesson_dependency_override = None
        self.truncate_cognition_output = False
        self.modify_cognition_output_after_digest = False
        self.cross_cognition_request_identity = False
        self.no_cognition_lesson = False
        self.unavailable_cognition_output = False
        self.effective_generation_ceiling: int | None = None
        self.backend_completion_observation: dict[str, object] | None = None
        self.objective_mode = "derive_from_history"
        self.truncate_objective_output = False
        self.fail_objective_condition: str | None = None
        self.objective_plan_root: Path | None = None
        self.history_interpretation = "bounded history"

    def build_request(self, **kwargs):
        request = type("Request", (), {})()
        for key, value in kwargs.items(): setattr(request, key, value)
        request.prompt_digest = digest_payload({"prompt": kwargs["prompt"]})
        request.prompt_size = len(kwargs["prompt"].encode("utf-8"))
        request.model_id = "model-a"; request.model_artifact_digest = "sha256:model"
        request.authority_map_digest = "test-authority-map"; request.active_model_identity = {}
        budget = kwargs.get("budget") or LocalModelInvocationBudget()
        request.budget = budget
        request.lifecycle_phase = kwargs.get("lifecycle_phase", "runtime")
        request.structured_output_schema = (dict(kwargs["structured_output_schema"])
            if kwargs.get("structured_output_schema") is not None else None)
        semantic = {
            "purpose": kwargs["purpose"],
            "prompt_digest": digest_payload({"prompt": kwargs["prompt"]}),
            "prompt_size": len(kwargs["prompt"].encode("utf-8")),
            "model_id": "model-a", "authority_map_digest": "test-authority-map",
            "model_artifact_digest": "sha256:model", "active_model_identity": {},
            "caller": kwargs["caller"], "lifecycle_phase": request.lifecycle_phase,
            "correlation_id": kwargs["correlation_id"],
            "expected_output_format": kwargs.get("expected_output_format", "text"),
            "structured_output_schema": request.structured_output_schema,
            "budget": budget.to_dict(), "upstream_evidence": kwargs.get("upstream_evidence") or {},
            "linkage": kwargs.get("linkage") or {},
            "allowed_effects": {"local_model_inference": True},
            "forbidden_effects": dict(FORBIDDEN_EFFECTS),
        }
        request.request_digest = digest_payload(semantic); request.request_id = "lmreq-" + request.request_digest[:24]
        request.to_receipt_request_dict = lambda: {**semantic, "request_id":request.request_id,
            "request_digest":request.request_digest, "raw_prompt_stored":False,
            "ephemeral_prompt_handling":"raw prompt used only for immediate local backend call"}
        self.requests.append(request)
        return request

    def invoke(self, request, *, persist, include_output_in_receipt):
        if (request.purpose == "resident_developmental_history_intervention_experiment"
                and self.fail_objective_condition == request.linkage.get("condition_id")):
            raise RuntimeError("fixture_interrupted_before_condition_invocation")
        truncated = False
        original_output = None
        if request.purpose == "resident_developmental_interpretation":
            text = json.dumps({"interpretation":self.history_interpretation, "uncertainty":"medium"})
        elif (request.purpose == "resident_developmental_history_intervention_experiment"
                and "objective_task_plan_digest" in request.upstream_evidence):
            assert self.objective_plan_root is not None
            plans = list(self.objective_plan_root.glob("objective-task-plan-*.json"))
            matching = [json.loads(path.read_text(encoding="utf-8")) for path in plans
                if json.loads(path.read_text(encoding="utf-8")).get("plan_digest")
                    == request.upstream_evidence["objective_task_plan_digest"]]
            assert len(matching) == 1
            plan = matching[0]
            prompt = json.loads(request.prompt)
            assert prompt["objective_task"] == plan["task_descriptor"]
            assert "objective_task" not in prompt["current_evidence"]
            history = prompt["developmental_history"]
            descriptor = plan["task_descriptor"]
            suite = descriptor.get("probe_count", 1) > 1
            probes = descriptor.get("probe_inputs", [7])
            answers = [0 for _ in probes]
            if self.objective_mode == "derive_from_history":
                examples = []
                for packet in history:
                    text_value = packet.get("interpretation")
                    if isinstance(text_value, str):
                        import re
                        examples.extend((int(x), int(y)) for x, y in re.findall(
                            r"input (\d+) produced (\d+)", text_value))
                if len(examples) >= 2:
                    (x1, y1), (x2, y2) = examples[:2]
                    multiplier = (y2 - y1) // (x2 - x1)
                    offset = y1 - multiplier * x1
                    answers = [multiplier * probe + offset for probe in probes]
            elif self.objective_mode == "no_difference":
                answers = [23 for _ in probes]
            elif self.objective_mode == "degrade":
                answers = [0 for _ in probes] if history else [23 for _ in probes]
            elif self.objective_mode == "unstable":
                answers = ([0 for _ in probes] if request.linkage["condition_id"] == "history_restored"
                    else [23 if history else 0 for _ in probes])
            elif self.objective_mode == "malformed":
                answers = [0 for _ in probes]
            elif self.objective_mode == "substitute":
                answers = [23 if history else 0 for _ in probes]
            elif self.objective_mode == "partial":
                answers = ([23, 26, *([0] * max(0, len(probes) - 2))]
                    if history else [0 for _ in probes])
            response = {"answers": answers} if suite else {"answer": answers[0]}
            output = ("{\"answer\":23,\"answer\":0}" if self.objective_mode == "malformed"
                else json.dumps(response, sort_keys=True, separators=(",", ":")))
            original_output = output
            if self.truncate_objective_output:
                output = output[:max(1, len(output) // 2)]
                truncated = True
            if self.objective_mode == "unavailable":
                receipt_text = None
            else:
                receipt_text = output
            text = output
        elif request.expected_output_format == "json" and request.structured_output_schema:
            upstream = request.upstream_evidence
            consumed = (upstream.get("record_ids") or upstream.get("current_fact_ids")
                        or upstream.get("self_model_claim_ids") or
                        upstream.get("epistemic_consumed_packet_ids") or [])
            dependency = (self.lesson_dependency_override or consumed[0]) if consumed else "missing"
            lesson = None if self.no_cognition_lesson else {
                "statement": self.lesson_statement, "scope": self.lesson_scope,
                "applicability": "Only when the cited evidence and scope still match.",
                "uncertainty": "medium",
                "uncertainty_rationale": "The source is historical interpretation.",
                "evidence_dependencies": [dependency],
                "possible_contradiction_ids": [],
            }
            text = json.dumps({
                "conclusion": f"Conclusion supporting: {self.lesson_statement}",
                "lesson_candidate": lesson,
            }, sort_keys=True)
            original_output = text
            if self.truncate_cognition_output:
                text = text[:24]
                truncated = True
        else:
            text = "cognition-with-history" if request.linkage.get("history_present") else "cognition-withheld"
        if original_output is None:
            original_output = text
        if (self.modify_cognition_output_after_digest
                and request.purpose == "resident_developmental_retrieval_cognition"):
            text = text + " substituted"
        receipt_request = request.to_receipt_request_dict()
        if self.cross_cognition_request_identity and request.expected_output_format == "json":
            receipt_request["request_id"] = "lmreq-crossed"
        if not (request.purpose == "resident_developmental_history_intervention_experiment"
                and "objective_task_plan_digest" in request.upstream_evidence):
            receipt_text = None if (self.unavailable_cognition_output
                and request.purpose == "resident_developmental_retrieval_cognition") else text
        receipt_digest = digest_payload({"output":original_output})
        if (request.purpose == "resident_developmental_history_intervention_experiment"
                and "objective_task_plan_digest" in request.upstream_evidence
                and self.objective_mode == "substitute"):
            receipt_digest = digest_payload({"output": "different output"})
        completion = (self.backend_completion_observation
            if request.purpose == "resident_developmental_history_intervention_experiment"
            and "objective_task_plan_digest" in request.upstream_evidence else None)
        backend_truncated = isinstance(completion, dict) and completion.get("token_limit_reached") is True
        return LocalModelInvocationReceipt(request=receipt_request, status="admitted_completed",
            reason_codes=(("completed", "backend_token_limit_reached") if backend_truncated
                else ("completed",)), output_text=receipt_text, output_digest=receipt_digest,
            output_size_bytes=len(original_output.encode()), admission_decision_ref="local",
            purpose=request.purpose, latency_ms=1, output_truncated=truncated or backend_truncated, fallback_occurred=False,
            effects={"local_model_inference":True}, observed_at="2026-01-01T00:00:00+00:00",
            generation_config={"actual_generation_parameters":{
                "temperature":0,
                "max_new_tokens": (self.effective_generation_ceiling
                    if self.effective_generation_ceiling is not None
                    else request.budget.max_new_tokens)}} if request.purpose == "resident_developmental_history_intervention_experiment" else {},
            schema_version=("sentientos.local_model_invocation_receipt:v3"
                if completion is not None else "sentientos.local_model_invocation_receipt:v2"),
            backend_completion=completion)


class SessionBoundFakeInvoker(FakeInvoker):
    def __init__(self) -> None:
        super().__init__()
        self.session_id = "fixture-serving-session"
        self.session_binding = {
            "model_serving_admission_ref": "fixture-model-serving-admission",
            "activation_state_semantic_digest": "a" * 64,
            "session_receipt_id": "resident-serving-receipt-" + "b" * 24,
            "session_receipt_semantic_digest": "c" * 64,
        }
        self.receipts = {}
        self.verified_receipts = []

    def build_request(self, **kwargs):
        linkage = dict(kwargs.get("linkage") or {})
        linkage["resident_cognitive_serving"] = {
            "session_id": self.session_id,
            **{key: value for key, value in self.session_binding.items()
                if key in {"model_serving_admission_ref", "activation_state_semantic_digest"}},
            "session_receipt_id": self.session_binding["session_receipt_id"],
            "session_receipt_semantic_digest": self.session_binding["session_receipt_semantic_digest"]}
        kwargs["linkage"] = linkage
        return super().build_request(**kwargs)

    def invoke(self, request, **kwargs):
        receipt = super().invoke(request, **kwargs)
        self.receipts[receipt.receipt_id] = receipt
        return receipt

    def verify_persisted_invocation_receipt(self, receipt_id, receipt_digest, **expected):
        self.verified_receipts.append((receipt_id, receipt_digest, dict(expected)))
        receipt = self.receipts[receipt_id]
        assert receipt.receipt_digest == receipt_digest
        assert receipt.request["request_id"] == expected["expected_request_id"]
        assert receipt.request["request_digest"] == expected["expected_request_digest"]
        expected_serving = {
            "session_id": expected["expected_session_id"],
            **dict(expected["expected_session_binding"])}
        if expected.get("expected_session_receipt_id") is not None:
            expected_serving.update({"session_receipt_id": expected["expected_session_receipt_id"],
                "session_receipt_semantic_digest": expected["expected_session_receipt_digest"]})
        assert receipt.request["linkage"]["resident_cognitive_serving"] == expected_serving
        assert receipt.request["active_model_identity"] == expected["expected_active_model_identity"]
        return {"receipt_id": receipt.receipt_id, "receipt_digest": receipt.receipt_digest,
            "request": receipt.request, "status": receipt.status,
            "output_digest": receipt.output_digest, "output_truncated": receipt.output_truncated,
            "generation_config": dict(receipt.generation_config),
            "backend_completion": (dict(receipt.backend_completion)
                if receipt.backend_completion is not None else None),
            "observed_at": receipt.observed_at}


def test_session_bound_observation_recovery_reconciles_exact_invocation_receipt(tmp_path: Path) -> None:
    invoker = SessionBoundFakeInvoker()
    first, _ = owner(tmp_path, comparison=True, invoker=invoker)
    first.run_tick(snapshot=snapshot(), tick_id="session-tick-1")
    experiment_result = first.run_tick(snapshot=snapshot(), tick_id="session-tick-2")
    observations = first._recover_observation_ticks(include_records=True)
    assert observations
    assert all(row["serving_session_id"] == invoker.session_id for row in observations.values())
    expected_binding = {key: invoker.session_binding[key] for key in (
        "model_serving_admission_ref", "activation_state_semantic_digest")}
    assert all(row["serving_session_binding"] == expected_binding for row in observations.values())
    assert all(row["serving_session_receipt_id"] == invoker.session_binding["session_receipt_id"]
        and row["serving_session_receipt_digest"] == invoker.session_binding[
            "session_receipt_semantic_digest"] for row in observations.values())

    loaded = first.experiments.load_run(experiment_result.changed_cognition_measurement_id)
    assert loaded["validity"] == "valid_controlled_observation"
    projected = first.experiments.world_state_records(run_refs=((
        loaded["run_id"], loaded["run_digest"]),))
    assert len(projected) == 1
    assert projected[0]["observed_at"] == "2026-01-01T00:00:00+00:00"
    assert projected[0]["payload"]["event_time_posture"] == "all_condition_invocation_receipt_times_verified"
    assert projected == first.experiments.world_state_records(run_refs=((
        loaded["run_id"], loaded["run_digest"]),))
    from sentientos.developmental_history_intervention_experiment import _digest
    substituted = {key: value for key, value in loaded.items()
        if key not in {"run_id", "run_digest"}}
    for condition in substituted["conditions"]:
        semantic = {key: value for key, value in condition.items()
            if key not in {"observation_id", "observation_digest"}}
        semantic["generation_config"] = {**condition["generation_config"],
            "actual_generation_parameters": {"temperature": 0, "max_new_tokens": 1}}
        digest = _digest(semantic)
        condition.update(semantic, observation_id="devcog-" + digest[7:31],
            observation_digest=digest)
    substituted_id = first.experiments.persist_run(substituted)
    with pytest.raises(DevelopmentalHistoryInterventionError,
            match="run_artifact_generation_config_mismatch"):
        first.experiments.load_run(substituted_id)
    with pytest.raises(DevelopmentalHistoryInterventionError,
                       match="run_artifact_invocation_verifier_unavailable"):
        DevelopmentalExperimentStore(tmp_path / "state").load_run(
            experiment_result.changed_cognition_measurement_id)
    restarted, _ = owner(tmp_path, invoker=invoker)
    restarted.run_tick(snapshot=snapshot(), tick_id="session-tick-3")
    assert invoker.verified_receipts
    assert all(item[2]["expected_session_id"] == invoker.session_id
        for item in invoker.verified_receipts)


def test_completed_objective_run_is_read_only_projected_into_a_later_world_state_tick(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        request: pytest.FixtureRequest) -> None:
    from sentientos.resident_developmental_cognition import objective_request_payload

    class CompleteReceiptInvoker(SessionBoundFakeInvoker):
        def verify_persisted_invocation_receipt(self, receipt_id, receipt_digest, **expected):
            verified = dict(super().verify_persisted_invocation_receipt(
                receipt_id, receipt_digest, **expected))
            receipt = self.receipts[receipt_id]
            verified["effects"] = dict(receipt.effects)
            verified["fallback_occurred"] = receipt.fallback_occurred
            return verified

    fake = CompleteReceiptInvoker()
    fake.objective_mode = "derive_from_history"
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    task = ObjectivePredictionTask(3, 2, 7, (8, 9),
        task_family_id="integer_affine_prediction")
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    seed = cognition.run_tick(snapshot=snapshot(), tick_id="experience-seed")
    assert seed.written_record_id

    objective_request = objective_request_payload(request_id="later-transfer", task=task)
    stage_objective_request(cognition.config.state_root, request_id="later-transfer", task=task)
    trial = cognition.run_objective_intervention_once(snapshot=snapshot(),
        tick_id="objective-acquisition", objective_task=task,
        request_id="later-transfer", request_digest=objective_request["request_digest"])
    assert trial.status == "objective_intervention_completed"
    assert trial.changed_cognition_measurement_id is not None
    state_path = cognition.state_path
    before = state_path.read_bytes()
    refs = cognition.inspect_completed_objective_experiment_run_refs()
    assert state_path.read_bytes() == before
    assert refs == ((trial.changed_cognition_measurement_id,
        cognition.experiments.load_run(trial.changed_cognition_measurement_id)["run_digest"]),)

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_CONTROL_KERNEL_ROOT", str(tmp_path / "kernel"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(tmp_path / "pulse-trust"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(tmp_path / "pulse-trust" / "state.json"))
    reset_runtime_governor()
    reset_federated_governance()
    reset_pulse_trust_epoch()
    reset_trust_ledger()
    from sentientos.control_plane_kernel import reset_control_plane_kernel
    reset_control_plane_kernel()
    request.addfinalizer(reset_runtime_governor)
    request.addfinalizer(reset_federated_governance)
    request.addfinalizer(reset_pulse_trust_epoch)
    request.addfinalizer(reset_trust_ledger)
    request.addfinalizer(reset_control_plane_kernel)

    # Reconstruct the cognition owner before World-State consumes the completed
    # score. The durable invocation verifier remains explicitly supplied.
    recovered_cognition, _ = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    assert recovered_cognition.inspect_completed_objective_experiment_run_refs() == refs
    surfaces = RuntimeMaintenanceSurfaces(tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=recovered_cognition)
    surfaces.build_world_state_board(tick_id="2026-01-02T00:00:00+00:00")
    later_snapshot = surfaces.current_world_state_snapshot
    assert later_snapshot is not None
    run_source_id = "developmental-history-run:" + trial.changed_cognition_measurement_id
    run_fact = next(fact for fact in later_snapshot.facts if fact.source.source_id == run_source_id)
    assert run_fact.observed_at == "2026-01-01T00:00:00+00:00"
    assert run_fact.payload["current_truth"] is False
    assert run_fact.payload["learning_established"] is False
    assert run_fact.payload["objective_task_family"] == "integer_affine_prediction"
    assert len(run_fact.payload["acquisition_examples"]) == 3
    assert "multiplier" not in json.dumps(run_fact.payload)
    assert surfaces._feedback["surfaces"]["developmental_history_intervention_projection"][
        "automatic_completed_run_count"] == 1

    later = recovered_cognition.run_tick(snapshot=later_snapshot, tick_id="objective-outcome-consumed")
    assert run_fact.fact_id in later.selected_fact_ids
    assert later.written_record_id
    retained = recovered_cognition.writeback.store.get(later.written_record_id)
    assert any(fact["payload"].get("objective_task_family") == "integer_affine_prediction"
        for fact in retained.candidate["selected_facts"])

    # A second owner reconstruction at a later tick retrieves the admitted
    # consequence record; projection and retention do not replay the experiment.
    successor_cognition, _ = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    successor_surfaces = RuntimeMaintenanceSurfaces(tmp_path,
        runtime_state_root=tmp_path / "runtime", resident_developmental_owner=successor_cognition)
    successor_surfaces.build_world_state_board(tick_id="2026-01-02T00:00:02+00:00")
    successor_snapshot = successor_surfaces.current_world_state_snapshot
    assert successor_snapshot is not None
    successor = successor_cognition.run_tick(snapshot=successor_snapshot,
        tick_id="objective-outcome-retrieved")
    assert successor.changed_cognition_measurement_id
    recovered_run = successor_cognition.experiments.load_run(
        successor.changed_cognition_measurement_id)
    assert later.written_record_id in recovered_run["protocol"]["record_ids"]
    assert later.written_record_id in recovered_run["conditions"][0]["retrieved_record_ids"]
    assert later.written_record_id not in recovered_run["conditions"][1]["retrieved_record_ids"]
    assert later.written_record_id in recovered_run["conditions"][2]["retrieved_record_ids"]
    assert len([item for item in fake.requests
        if "objective_task_plan_digest" in item.upstream_evidence]) == 3

    pending = cognition.config.state_root / "pending_objective_intervention.json"
    substituted = json.loads(pending.read_text(encoding="utf-8"))
    substituted["task"]["offset"] += 1
    pending.write_text(json.dumps(substituted, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="objective_run_projection_verification_failed"):
        cognition.inspect_completed_objective_experiment_run_refs()


def test_interrupted_scored_family_run_recovers_into_later_world_state_without_replay(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        request: pytest.FixtureRequest) -> None:
    """All durable condition scores survive interruption before aggregate publication."""
    from scripts.stage_resident_objective_intervention import stage_request

    class CompleteReceiptInvoker(SessionBoundFakeInvoker):
        def invoke(self, request, **kwargs):
            receipt = super().invoke(request, **kwargs)
            relative = ("local-model/resident-cognitive-serving/inference/receipts/"
                + receipt.receipt_id + ".json")
            target = self.installation_handle.fixed_object(relative)
            self.installation_handle.ensure_directory(
                self.installation_handle.fixed_object(relative.rsplit("/", 1)[0]))
            self.installation_handle.durable_create(target,
                (json.dumps(receipt.to_dict(), sort_keys=True, indent=2) + "\n").encode())
            return receipt

        def verify_persisted_invocation_receipt(self, receipt_id, receipt_digest, **expected):
            return self.installation_reader.verify_persisted_invocation_receipt(
                receipt_id, receipt_digest, **expected)

    fake = CompleteReceiptInvoker()
    # Persist the fixture's invocation receipts under an explicit installation
    # identity. The restarted process below uses the production read-only
    # receipt verifier, not a test-local verifier that merely compares fields.
    from sentientos.resident_cognitive_model_serving import (
        WITNESS_SCHEMA, ResidentCognitiveInvocationReceiptReader, ServingSession,
        _resident_serving_session_receipt, resident_serving_session_receipt_reference,
    )
    from sentientos.local_runtime_provisioning import semantic_digest
    installation_identity = InstallationIdentity("interrupted-family-installation")
    installation_registry = InstallationStateRegistry._for_testing(
        tmp_path / "installation-custody")
    installation_handle = installation_registry.open(installation_identity, create=True)
    session_binding = {
        "installation_identity": installation_identity.value,
        "serving_operation_id": "interrupted-family-serving",
        "serving_config_digest": "d" * 64,
        "model_serving_admission_ref": "local",
        "activation_state_semantic_digest": "a" * 64,
        "observed_loaded_model_identity": {},
    }
    session = ServingSession("resident-serving-session-" + semantic_digest(session_binding)[:24],
        session_binding)
    session_receipt = _resident_serving_session_receipt(session.to_dict())
    session_reference = resident_serving_session_receipt_reference(session)
    fake.session_id = session.session_id
    fake.session_binding = {
        "model_serving_admission_ref": session_binding["model_serving_admission_ref"],
        "activation_state_semantic_digest": session_binding["activation_state_semantic_digest"],
        "session_receipt_id": session_reference["session_receipt_id"],
        "session_receipt_semantic_digest": session_reference["session_receipt_semantic_digest"],
    }

    def persist_installation_fixture(relative: str, value: Mapping[str, object]) -> None:
        target = installation_handle.fixed_object(relative)
        installation_handle.ensure_directory(
            installation_handle.fixed_object(relative.rsplit("/", 1)[0]))
        installation_handle.durable_create(target,
            (json.dumps(dict(value), sort_keys=True, separators=(",", ":")) + "\n").encode())

    persist_installation_fixture(
        "local-model/resident-cognitive-serving/receipts/"
        + session_receipt["receipt_id"] + ".json", session_receipt)
    witness = {"schema_version": WITNESS_SCHEMA, "session_id": session.session_id,
        "receipt_id": session_receipt["receipt_id"],
        "receipt_semantic_digest": session_receipt["receipt_semantic_digest"],
        "admission_decision_ref": session_binding["model_serving_admission_ref"],
        "authority_class": AuthorityClass.MODEL_SERVING.value, "inference_performed": False}
    witness["witness_semantic_digest"] = semantic_digest(witness)
    persist_installation_fixture("logs/privileges/" + session_receipt["receipt_id"] + ".json",
        witness)
    fake.installation_handle = installation_handle
    fake.installation_reader = ResidentCognitiveInvocationReceiptReader(
        installation_registry.open_read_only(installation_identity))
    fake.objective_mode = "derive_from_history"
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    seed = cognition.run_tick(snapshot=snapshot(), tick_id="interrupted-family-seed")
    assert seed.written_record_id
    config_path = tmp_path / "interrupted-family-config.json"
    config_path.write_text(json.dumps({"schema": CONFIG_SCHEMA, "enabled": True,
        "history_root": str(tmp_path / "history"), "state_root": str(tmp_path / "state"),
        "allowed_source_kinds": ["capability_registry", "embodiment"],
        "max_selected_facts": 16, "max_retrieved_records": 4,
        "comparison_enabled": True}), encoding="utf-8")
    task = ObjectivePredictionTask(3, 2, 16, (17, 18),
        task_family_id="integer_affine_prediction")
    stage_request(config_path=config_path, request_id="interrupted-family-run", task=task)
    staged = load_objective_request(tmp_path / "state")
    assert staged is not None

    def interrupt_after_all_scores(_payload):
        raise OSError("fixture interruption before aggregate run publication")

    monkeypatch.setattr(cognition.experiments, "persist_run", interrupt_after_all_scores)
    before = len(fake.requests)
    with pytest.raises(OSError, match="before aggregate run publication"):
        cognition.run_objective_intervention_once(snapshot=snapshot(),
            tick_id="interrupted-family-score-checkpoints",
            objective_task=objective_task_for_request(staged),
            request_id=staged["request_id"], request_digest=staged["request_digest"])
    issued_count = len(fake.requests)
    assert sum(1 for item in fake.requests[before:]
        if "objective_task_plan_digest" in item.upstream_evidence) == 3
    assert cognition.inspect_completed_objective_experiment_run_refs() == ()
    installation_files_before_recovery = {
        path.relative_to(installation_handle.root).as_posix(): path.read_bytes()
        for path in installation_handle.root.rglob("*") if path.is_file()}
    history_files_before_projection = {
        path.relative_to(tmp_path / "history").as_posix(): path.read_bytes()
        for path in (tmp_path / "history").rglob("*") if path.is_file()}
    child_code = r'''
import json, sys
from pathlib import Path
from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION)
from sentientos.resident_developmental_cognition import (
    ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionOwner)
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.resident_cognitive_model_serving import ResidentCognitiveInvocationReceiptReader
from sentientos.governed_local_model_invocation import digest_payload
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier

root, installation_root = Path(sys.argv[1]), Path(sys.argv[2])
identity = InstallationIdentity("interrupted-family-installation")
registry = InstallationStateRegistry._for_testing(installation_root)
reader = ResidentCognitiveInvocationReceiptReader(registry.open_read_only(identity))
ledger = AdmissionLedger(root / "state" / "runtime_admissions.json")
definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
def sequence(): return ledger.current_sequence()
writeback = ResidentDevelopmentalWritebackController(
    history_root=root / "history",
    admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger),
    current_sequence=sequence)
owner = ResidentDevelopmentalCognitionOwner(
    config=ResidentDevelopmentalCognitionConfig(root / "history", root / "state",
        ("capability_registry", "embodiment"), 16, 4, True),
    writeback=writeback,
    admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
    invoker=reader, current_sequence=sequence)
refs = owner.recovered_objective_experiment_run_refs()
projectable = owner.inspect_completed_objective_experiment_run_refs()
outcome = owner.verified_objective_measurement_for_request(
    request_id="interrupted-family-run",
    request_digest=json.loads((root / "state" / "pending_objective_intervention.json").read_text())[
        "request_digest"])
from sentientosd import RuntimeMaintenanceSurfaces
surfaces = RuntimeMaintenanceSurfaces(root, runtime_state_root=root / "runtime",
    resident_developmental_owner=owner)
surfaces.build_world_state_board(tick_id=sys.argv[3])
world = surfaces.current_world_state_snapshot
fact = next(row for row in world.facts
    if row.source.source_id == "developmental-history-run:" + refs[0][0])
print(json.dumps({"refs": refs, "projectable": projectable,
    "status": outcome["status"],
    "measurement_digest": outcome["measurement_digest"],
    "projected_source_id": fact.source.source_id,
    "projected_source_digest": fact.source.digest,
    "projected_fact_id": fact.fact_id,
    "projected_payload_digest": digest_payload({"payload": fact.payload}),
    "actual_nonsynthetic_inference_verified":
        outcome["actual_nonsynthetic_inference_verified"]}, sort_keys=True))
'''
    child = subprocess.run([sys.executable, "-c", child_code, str(tmp_path),
        str(tmp_path / "installation-custody"), "2026-01-02T00:00:01+00:00"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert child.returncode == 0, child.stderr[-4000:]
    child_result = json.loads(child.stdout.strip().splitlines()[-1])
    assert child_result["status"] == "verified_objective_measurement"
    assert child_result["actual_nonsynthetic_inference_verified"] is True
    assert len(child_result["refs"]) == 1 and child_result["projectable"] == child_result["refs"]
    assert child_result["projected_source_id"] == "developmental-history-run:" + child_result["refs"][0][0]
    assert child_result["projected_source_digest"]
    repeat_projection = subprocess.run([sys.executable, "-c", child_code, str(tmp_path),
        str(tmp_path / "installation-custody"), "2026-01-02T00:00:02+00:00"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=True)
    repeat_result = json.loads(repeat_projection.stdout.strip().splitlines()[-1])
    for field in ("refs", "measurement_digest", "projected_source_id",
            "projected_source_digest", "projected_fact_id", "projected_payload_digest"):
        assert repeat_result[field] == child_result[field]
    latest_world_state = tmp_path / "runtime" / "world_state_board" / "latest.json"
    assert latest_world_state.is_file()
    latest_projection = json.loads(latest_world_state.read_text(encoding="utf-8"))
    assert child_result["projected_source_id"] in json.dumps(latest_projection)
    assert history_files_before_projection == {
        path.relative_to(tmp_path / "history").as_posix(): path.read_bytes()
        for path in (tmp_path / "history").rglob("*") if path.is_file()}
    assert installation_files_before_recovery == {
        path.relative_to(installation_handle.root).as_posix(): path.read_bytes()
        for path in installation_handle.root.rglob("*") if path.is_file()}

    # Substituting a request digest in one persisted receipt keeps every
    # filename and journal identity fixed but must fail the canonical reader.
    score_request = next(item for item in fake.requests
        if "objective_task_plan_digest" in item.upstream_evidence)
    score_receipt = next(value for value in fake.receipts.values()
        if value.request["request_id"] == score_request.request_id)
    receipt_path = installation_handle.root / "local-model/resident-cognitive-serving/inference/receipts" / (
        score_receipt.receipt_id + ".json")
    substituted_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    original_score_receipt_bytes = receipt_path.read_bytes()
    substituted_receipt["request"]["request_digest"] = "substituted-request-digest"
    receipt_path.write_text(json.dumps(substituted_receipt, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    child_code_reject = child_code.replace(
        'refs = owner.recovered_objective_experiment_run_refs()',
        'try:\n    refs = owner.recovered_objective_experiment_run_refs()\n'
        'except Exception as exc:\n    print(json.dumps({"status": "rejected", "reason": str(exc)}))\n'
        '    raise SystemExit(0)')
    rejected = subprocess.run([sys.executable, "-c", child_code_reject, str(tmp_path),
        str(tmp_path / "installation-custody"), "2026-01-02T00:00:03+00:00"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, check=True)
    rejection = json.loads(rejected.stdout.strip().splitlines()[-1])
    assert rejection == {"status": "rejected",
        "reason": "cognition_invocation_receipt_reconciliation_failed"}
    assert len(fake.requests) == issued_count
    receipt_path.write_bytes(original_score_receipt_bytes)

    # The independent parent owner sees the run recovered by the child and
    # does not issue another inference or change its identity.
    restarted, _ = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    assert restarted.inspect_completed_objective_experiment_run_refs() == tuple(
        tuple(item) for item in child_result["refs"])
    recovered_refs = restarted.recovered_objective_experiment_run_refs()
    assert len(recovered_refs) == 1
    run_id, run_digest = recovered_refs[0]
    recovered_run = restarted.experiments.load_run(run_id)
    assert recovered_run["run_digest"] == run_digest
    assert len(recovered_run["objective_scores"]) == 3
    assert len(fake.requests) == issued_count
    assert restarted.inspect_completed_objective_experiment_run_refs() == (recovered_refs[0],)

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_CONTROL_KERNEL_ROOT", str(tmp_path / "kernel"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(tmp_path / "pulse-trust"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(tmp_path / "pulse-trust" / "state.json"))
    reset_runtime_governor(); reset_federated_governance(); reset_pulse_trust_epoch(); reset_trust_ledger()
    from sentientos.control_plane_kernel import reset_control_plane_kernel
    reset_control_plane_kernel()
    request.addfinalizer(reset_runtime_governor)
    request.addfinalizer(reset_federated_governance)
    request.addfinalizer(reset_pulse_trust_epoch)
    request.addfinalizer(reset_trust_ledger)
    request.addfinalizer(reset_control_plane_kernel)
    surfaces = RuntimeMaintenanceSurfaces(tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=restarted)
    surfaces.build_world_state_board(tick_id="2026-01-02T00:00:03+00:00")
    world = surfaces.current_world_state_snapshot
    assert world is not None
    fact = next(row for row in world.facts
        if row.source.source_id == "developmental-history-run:" + run_id)
    assert fact.payload["objective_task_family"] == "integer_affine_prediction"
    assert fact.payload["learning_established"] is False
    assert "multiplier" not in json.dumps(fact.payload)
    save_state = restarted._save_state
    def interrupt_after_admitted_feedback(state):
        if any(row.get("tick_id") == "interrupted-family-feedback-writeback"
                for row in state["completed_ticks"]):
            raise ResidentDevelopmentalCognitionError(
                "simulated_after_feedback_admission_before_checkpoint")
        save_state(state)
    restarted._save_state = interrupt_after_admitted_feedback
    captured_prior: dict[str, tuple[str, ...]] = {}
    build_prior_projection = restarted._prior_projection
    def capture_prior_projection(state, tick_id, **kwargs):
        projection = build_prior_projection(state, tick_id, **kwargs)
        if tick_id == "interrupted-family-feedback-writeback":
            captured_prior[tick_id] = projection.requested_record_ids
        return projection
    restarted._prior_projection = capture_prior_projection
    records_before_feedback = {record.record_id
        for record in restarted.writeback.store.records()}
    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="after_feedback_admission_before_checkpoint"):
        restarted.run_tick(snapshot=world,
            tick_id="interrupted-family-feedback-writeback")
    committed = [record for record in restarted.writeback.store.records()
        if record.record_id not in records_before_feedback]
    assert len(committed) == 1
    assert len(restarted.writeback.store.receipts()) == 2
    feedback_record = committed[0]
    assert feedback_record.record_id not in captured_prior["interrupted-family-feedback-writeback"]
    assert any(fact["payload"].get("objective_task_family") ==
        "integer_affine_prediction" for fact in feedback_record.candidate["selected_facts"])

    invocations_before_checkpoint_recovery = len(fake.requests)
    after_interruption, later_fake = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    recovered_state = after_interruption._state()
    assert len(fake.requests) == invocations_before_checkpoint_recovery
    recovered_tick = next(row for row in recovered_state["completed_ticks"]
        if row["tick_id"] == "interrupted-family-feedback-writeback")
    assert recovered_tick["record_id"] == feedback_record.record_id
    assert recovered_tick["receipt_id"]
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        after_interruption.run_tick(snapshot=world,
            tick_id="interrupted-family-feedback-writeback")
    assert len(after_interruption.writeback.store.records()) == 2
    assert len(after_interruption.writeback.store.receipts()) == 2
    later = after_interruption.run_tick(snapshot=snapshot(3),
        tick_id="interrupted-family-feedback-later-cognition")
    assert feedback_record.record_id in later.prior_record_ids
    later_request = next(item for item in reversed(later_fake.requests)
        if item.purpose == "resident_developmental_history_intervention_experiment"
        and item.linkage.get("history_present") is True)
    assert feedback_record.record_id in later_request.upstream_evidence["record_ids"]
    assert len([item for item in fake.requests
        if "objective_task_plan_digest" in item.upstream_evidence]) == 3


def test_task_family_example_flows_through_admitted_history_and_is_not_current_context(
        tmp_path: Path) -> None:
    """Fixture composition only: evaluator-backed examples reach later task history."""
    from scripts.stage_resident_objective_intervention import stage_request
    from sentientos.resident_developmental_cognition import objective_request_payload

    fake = SessionBoundFakeInvoker()
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    seeded = cognition.run_tick(snapshot=snapshot(), tick_id="family-acquisition-seed")
    assert seeded.written_record_id

    acquisition = ObjectivePredictionTask(3, 2, 7, (8, 9),
        task_family_id="integer_affine_prediction")
    stage_objective_request(tmp_path / "state", request_id="family-acquisition", task=acquisition)
    request = load_objective_request(tmp_path / "state")
    assert request is not None
    run_result = cognition.run_objective_intervention_once(snapshot=snapshot(),
        tick_id="family-acquisition-run", objective_task=acquisition,
        request_id="family-acquisition", request_digest=request["request_digest"])
    run = cognition.experiments.load_run(run_result.changed_cognition_measurement_id)
    from sentientos.developmental_history_intervention_experiment import _digest as experiment_digest
    from sentientos.developmental_model_replacement_experiment import (
        DevelopmentalModelReplacementError, _verify_objective_score,
    )
    original_score = run["objective_scores"][0]["score"]
    altered_score = dict(original_score)
    altered_results = [dict(item) for item in altered_score["probe_results"]]
    altered_results[0]["observed_answer"] += 1
    altered_score["probe_results"] = altered_results
    altered_score["score_digest"] = experiment_digest({key: value
        for key, value in altered_score.items() if key != "score_digest"})
    protocol = cognition.experiments.load_protocol(run["protocol"]["protocol_id"])
    plan = cognition.experiments.verify_objective_task_plan(protocol)
    with pytest.raises(DevelopmentalModelReplacementError,
            match="objective_score_binding_invalid"):
        _verify_objective_score(plan, altered_score, run["conditions"][0]["output_digest"])
    records = cognition.experiments.world_state_records(run_refs=((run["run_id"], run["run_digest"]),))
    evidence = records[0]["payload"]
    assert evidence["task_family_posture"] == "operator_declared_protocol_bound"
    assert evidence["objective_task_family"] == "integer_affine_prediction"
    assert evidence["acquisition_examples"] == [
        {"probe_input": 7, "observed_answer": 23, "evaluator_correct": True,
            "source_score_digest": evidence["objective_scores"][0]["score_digest"],
            "source_condition": "history_present"},
        {"probe_input": 8, "observed_answer": 26, "evaluator_correct": True,
            "source_score_digest": evidence["objective_scores"][0]["score_digest"],
            "source_condition": "history_present"},
        {"probe_input": 9, "observed_answer": 29, "evaluator_correct": True,
            "source_score_digest": evidence["objective_scores"][0]["score_digest"],
            "source_condition": "history_present"},
    ]
    assert "multiplier" not in json.dumps(evidence)

    from sentientos.world_state_board import WorldStateBoardBuilder
    world = WorldStateBoardBuilder().build(records)
    later = cognition.run_tick(snapshot=world, tick_id="family-acquisition-writeback")
    assert later.written_record_id
    admitted = cognition.writeback.store.get(later.written_record_id)
    assert any(fact["payload"].get("objective_task_family") == "integer_affine_prediction"
        for fact in admitted.candidate["selected_facts"])

    # A relevant example older than the prior 64-tick search window must not
    # be hidden by newer unrelated, otherwise valid developmental history.
    unrelated_owner, _ = owner(tmp_path, comparison=False, invoker=fake,
        allowed_source_kinds=("capability_registry",), max_selected_facts=4)
    for value in range(2, 68):
        unrelated = unrelated_owner.run_tick(snapshot=snapshot(value),
            tick_id=f"unrelated-history-{value}")
        assert unrelated.written_record_id

    config_path = tmp_path / "family-config.json"
    config_path.write_text(json.dumps({"schema": CONFIG_SCHEMA, "enabled": True,
        "history_root": str(tmp_path / "history"), "state_root": str(tmp_path / "state"),
        "allowed_source_kinds": ["capability_registry", "embodiment"],
        "max_selected_facts": 16, "max_retrieved_records": 4,
        "comparison_enabled": True}), encoding="utf-8")
    transfer = ObjectivePredictionTask(3, 2, 10, (11, 12),
        task_family_id="integer_affine_prediction", requires_task_family_history=True)
    unrelated = ObjectivePredictionTask(3, 2, 10, (11, 12),
        task_family_id="unrelated_prediction_family", requires_task_family_history=True)
    pending_path = tmp_path / "state" / "pending_objective_intervention.json"
    pending_before_denial = pending_path.read_bytes()
    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="checkpointed_history_relevant_experience_missing"):
        stage_request(config_path=config_path, request_id="unrelated-family-transfer",
            task=unrelated)
    assert pending_path.read_bytes() == pending_before_denial
    staged_path, _, matching_count = stage_request(config_path=config_path,
        request_id="family-transfer", task=transfer)
    assert staged_path.exists() and matching_count >= 1
    staged = load_objective_request(tmp_path / "state")
    assert staged is not None
    result = cognition.run_objective_intervention_once(snapshot=world,
        tick_id="family-transfer-run", objective_task=objective_task_for_request(staged),
        request_id=staged["request_id"], request_digest=staged["request_digest"])
    recovered = cognition.experiments.load_run(result.changed_cognition_measurement_id)
    family_record_ids = tuple(recovered["protocol"]["record_ids"])
    assert later.written_record_id in family_record_ids
    conditions = recovered["conditions"]
    present, withheld, restored = conditions
    family_fact = records[0]["payload"]
    source_fact = next(fact for fact in world.facts
        if fact.source.source_id == records[0]["source_id"])
    assert source_fact.fact_id not in present["current_fact_ids"]
    assert source_fact.fact_id not in withheld["current_fact_ids"]
    assert source_fact.fact_id not in restored["current_fact_ids"]
    assert later.written_record_id in present["retrieved_record_ids"]
    assert later.written_record_id not in withheld["retrieved_record_ids"]
    assert later.written_record_id in restored["retrieved_record_ids"]
    assert recovered["objective_evaluation"]["history_correct_probe_delta"] == 3
    assert recovered["objective_evaluation"]["restoration_correct_probe_delta"] == 0

    # The held-out score becomes a later World-State observation and ordinary
    # developmental record; a third, disjoint probe set can then consume both
    # admitted family records without receiving those answers as current facts.
    transfer_records = cognition.experiments.world_state_records(run_refs=((
        recovered["run_id"], recovered["run_digest"]),))
    assert len(transfer_records) == 1
    transfer_world = WorldStateBoardBuilder().build(transfer_records)
    feedback = cognition.run_tick(snapshot=transfer_world, tick_id="family-transfer-feedback")
    assert feedback.written_record_id
    feedback_record = cognition.writeback.store.get(feedback.written_record_id)
    assert any(fact["payload"].get("objective_task_family") == "integer_affine_prediction"
        for fact in feedback_record.candidate["selected_facts"])
    continued = ObjectivePredictionTask(3, 2, 13, (14, 15),
        task_family_id="integer_affine_prediction", requires_task_family_history=True)
    staged_path, _, matching_count = stage_request(config_path=config_path,
        request_id="family-continued-transfer", task=continued)
    assert staged_path.exists() and matching_count >= 2
    continued_request = load_objective_request(tmp_path / "state")
    assert continued_request is not None
    continued_result = cognition.run_objective_intervention_once(snapshot=transfer_world,
        tick_id="family-continued-transfer-run",
        objective_task=objective_task_for_request(continued_request),
        request_id=continued_request["request_id"],
        request_digest=continued_request["request_digest"])
    continued_run = cognition.experiments.load_run(
        continued_result.changed_cognition_measurement_id)
    assert later.written_record_id in continued_run["protocol"]["record_ids"]
    assert feedback.written_record_id in continued_run["protocol"]["record_ids"]
    continuation_source_ids = {fact.fact_id for fact in transfer_world.facts
        if fact.payload.get("objective_task_family") == "integer_affine_prediction"}
    assert continuation_source_ids
    assert all(not continuation_source_ids.intersection(condition["current_fact_ids"])
        for condition in continued_run["conditions"])
    assert continued_run["objective_evaluation"]["assessment"] == "preregistered_probe_suite_scored"
    progression = cognition.verified_objective_task_family_progression(request_refs=(
        ("family-acquisition", request["request_digest"]),
        ("family-transfer", staged["request_digest"]),
        ("family-continued-transfer", continued_request["request_digest"]),
    ))
    assert progression["status"] == "comparable_scored_episodes"
    assert progression["episode_count"] == 3
    assert [episode["task_family"]["probe_inputs"] for episode in progression["episodes"]] == [
        [7, 8, 9], [10, 11, 12], [13, 14, 15]]
    assert progression["same_model_generation_controls"] is True
    assert progression["distinct_task_instances"] is True
    assert progression["distinct_probe_sets"] is True
    assert progression["actual_nonsynthetic_inference_verified"] is False
    assert progression["learning_established"] is False


def test_incorrect_family_experience_remains_adverse_through_writeback_and_transfer(
        tmp_path: Path) -> None:
    """A family match is relevant evidence, not an implicit success claim."""
    fake = SessionBoundFakeInvoker()
    fake.objective_mode = "degrade"
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    assert cognition.run_tick(snapshot=snapshot(), tick_id="adverse-family-seed").written_record_id

    # The fixture endpoint is preregistered to answer incorrectly when history
    # is present and correctly when withheld. This is an instrument control,
    # not evidence of actual model learning or model performance.
    acquisition = ObjectivePredictionTask(0, 23, 6, (7, 8),
        task_family_id="integer_affine_prediction")
    stage_objective_request(tmp_path / "state", request_id="adverse-acquisition",
        task=acquisition)
    staged = load_objective_request(tmp_path / "state")
    assert staged is not None
    acquired = cognition.run_objective_intervention_once(snapshot=snapshot(),
        tick_id="adverse-family-acquisition", objective_task=acquisition,
        request_id=staged["request_id"], request_digest=staged["request_digest"])
    assert acquired.changed_cognition_measurement_id
    run = cognition.experiments.load_run(acquired.changed_cognition_measurement_id)
    assert run["objective_evaluation"]["history_correct_probe_delta"] == -3
    source_records = cognition.experiments.world_state_records(run_refs=((
        run["run_id"], run["run_digest"]),))
    assert len(source_records) == 1
    source_payload = source_records[0]["payload"]
    assert source_payload["current_truth"] is False
    assert source_payload["learning_established"] is False
    assert [item["evaluator_correct"] for item in source_payload["acquisition_examples"]] == [
        False, False, False]
    source_score_digest = source_payload["objective_scores"][0]["score_digest"]
    assert all(item["source_score_digest"] == source_score_digest
        for item in source_payload["acquisition_examples"])

    source_world = WorldStateBoardBuilder().build(source_records)
    retained_result = cognition.run_tick(snapshot=source_world,
        tick_id="adverse-family-source-writeback")
    assert retained_result.written_record_id
    retained = cognition.writeback.store.get(retained_result.written_record_id)
    retained_fact = next(fact for fact in retained.candidate["selected_facts"]
        if fact["payload"].get("objective_task_family") == "integer_affine_prediction")
    assert [item["evaluator_correct"] for item in retained_fact["payload"][
        "acquisition_examples"]] == [False, False, False]
    assert retained_fact["payload"]["objective_scores"][0]["score_digest"] == source_score_digest

    # Recent unrelated history cannot erase this independently admitted family
    # evidence. Staging discovers it via the ordinary checkpoint and receipt.
    later_task = ObjectivePredictionTask(0, 23, 9,
        (10,),
        task_family_id="integer_affine_prediction", requires_task_family_history=True)
    from scripts.stage_resident_objective_intervention import stage_request
    config_path = tmp_path / "adverse-family-config.json"
    config_path.write_text(json.dumps({"schema": CONFIG_SCHEMA, "enabled": True,
        "history_root": str(tmp_path / "history"), "state_root": str(tmp_path / "state"),
        "allowed_source_kinds": ["capability_registry", "embodiment"],
        "max_selected_facts": 16, "max_retrieved_records": 4,
        "comparison_enabled": True}), encoding="utf-8")
    staged_path, _, matching_count = stage_request(config_path=config_path,
        request_id="adverse-family-transfer", task=later_task)
    assert staged_path.exists() and matching_count >= 1
    later_request = load_objective_request(tmp_path / "state")
    assert later_request is not None
    later = cognition.run_objective_intervention_once(snapshot=source_world,
        tick_id="adverse-family-transfer-run", objective_task=objective_task_for_request(later_request),
        request_id=later_request["request_id"], request_digest=later_request["request_digest"])
    assert later.changed_cognition_measurement_id
    transfer = cognition.experiments.load_run(later.changed_cognition_measurement_id)
    assert transfer["objective_evaluation"]["history_correct_probe_delta"] == -2
    present, withheld, restored = transfer["conditions"]
    assert retained.record_id in present["retrieved_record_ids"]
    assert retained.record_id not in withheld["retrieved_record_ids"]
    assert retained.record_id in restored["retrieved_record_ids"]
    source_fact = next(fact for fact in source_world.facts
        if fact.source.source_id == source_records[0]["source_id"])
    assert all(source_fact.fact_id not in condition["current_fact_ids"]
        for condition in transfer["conditions"])
    assert all("objective_evaluation" not in json.dumps(condition["current_fact_ids"])
        for condition in transfer["conditions"])
    assert transfer["objective_evaluation"]["scope"] == (
        "same_model_task_correctness_not_general_learning_or_weight_change")


def test_admitted_resident_history_is_shared_with_predecessor_and_successor_models(
        tmp_path: Path) -> None:
    """Model-replacement controls receive the same ordinary admitted record."""
    from sentientos.developmental_model_replacement_experiment import (
        CognitiveModelIdentity, DevelopmentalModelReplacementExperiment, FrozenCausalContext,
    )

    cognition, _ = owner(tmp_path, comparison=False,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    source_snapshot = snapshot()
    acquired = cognition.run_tick(snapshot=source_snapshot, tick_id="succession-history-source")
    assert acquired.written_record_id
    record = cognition.writeback.store.get(acquired.written_record_id)
    projection = cognition._current_projection(source_snapshot)
    current_payload = projection.semantic_payload()
    history = cognition.writeback.retrieve((record.record_id,), limit=4)
    assert history.requested_record_ids == (record.record_id,)
    assert history.records[0]["record_digest"] == record.record_digest

    context = FrozenCausalContext.create(
        snapshot_id=projection.snapshot_id, snapshot_digest=projection.snapshot_digest,
        current_projection_id=projection.projection_id,
        current_projection_digest=projection.projection_digest,
        current_fact_ids=projection.fact_ids,
        projected_content_digest="sha256:" + digest_payload(current_payload),
        current_projection_payload=current_payload,
        history_record_ids=(record.record_id,), history_record_digests=(record.record_digest,),
        history_record_set_digest="sha256:" + digest_payload({
            "record_ids": [record.record_id], "record_digests": [record.record_digest]}),
        history_projection_payload=history.records,
        instruction_template=("Use current evidence with optional historical interpretation; "
            "history is not truth or authority."),
        instruction_template_digest="sha256:" + digest_payload({"instruction":
            "Use current evidence with optional historical interpretation; history is not truth or authority."}),
        inference_budget={"max_input_chars": 16000, "max_output_chars": 4000,
            "max_new_tokens": 512, "timeout_seconds": 30, "max_calls_per_correlation": 1},
        generation_posture={"temperature": 0, "hardware_determinism_claimed": False},
        repository_generation_identity="fixture-source-generation")

    def model_identity(name: str) -> CognitiveModelIdentity:
        artifact = f"fixture-artifact-{name}"
        content_digest = "sha256:" + digest_payload({"model": name})
        sidecar_digest = "sha256:" + digest_payload({"sidecar": name})
        configuration_digest = "sha256:" + digest_payload({"configuration": name})
        active = {"semantic_artifact_identity": artifact,
            "model_content_sha256": content_digest, "artifact_size_bytes": 10,
            "sidecar_metadata_digest": sidecar_digest,
            "configuration_digest": configuration_digest,
            "engine": "deterministic-test-runtime", "candidate_index": 0,
            "posture": "production", "fallback": False}
        return CognitiveModelIdentity.create(model_id=name,
            semantic_artifact_identity=artifact, model_content_sha256=content_digest,
            artifact_size_bytes=10, sidecar_metadata_digest=sidecar_digest,
            configuration_digest=configuration_digest,
            engine_runtime_family="deterministic-test-runtime", candidate_index=0,
            active_production=True, fallback=False,
            authority_record_id=f"fixture-authority-{name}",
            authority_record_digest="sha256:" + digest_payload({"authority": name}),
            active_model_identity=active,
            active_model_identity_digest="sha256:" + digest_payload(active))

    class Endpoint:
        def __init__(self, model: CognitiveModelIdentity) -> None:
            self.model = model
            self.calls = []

        def current_identity(self) -> CognitiveModelIdentity:
            return self.model

        def infer(self, **kwargs):
            self.calls.append(kwargs)
            prompt_digest = "sha256:" + digest_payload({"prompt": kwargs["prompt"]})
            number = len(self.calls)
            return {"status": "admitted_completed", "fallback_occurred": False,
                "request_id": f"fixture-request-{self.model.model_id}-{number}",
                "request_digest": "sha256:" + digest_payload({"request": self.model.model_id,
                    "number": number}),
                "inference_receipt_id": f"fixture-receipt-{self.model.model_id}-{number}",
                "inference_receipt_digest": "sha256:" + digest_payload({"receipt": self.model.model_id,
                    "number": number}), "output_digest": prompt_digest,
                "actual_generation_parameters": {"temperature": 0,
                    "max_new_tokens": kwargs["budget"]["max_new_tokens"]}}

    model_a, model_b = Endpoint(model_identity("predecessor")), Endpoint(model_identity("successor"))
    experiment = DevelopmentalModelReplacementExperiment(context=context,
        model_a=model_a, model_b=model_b, artifact_root=tmp_path / "replacement-experiment")
    result = experiment.run()
    assert result["validity"] == "valid_controlled_observation"
    assert experiment.context.history_record_ids == (record.record_id,)
    assert experiment.context.history_record_digests == (record.record_digest,)
    a_history = json.loads(model_a.calls[0]["prompt"])["developmental_history"]
    b_history = json.loads(model_b.calls[0]["prompt"])["developmental_history"]
    assert a_history[0]["record_id"] == b_history[0]["record_id"] == record.record_id
    assert a_history[0]["record_digest"] == b_history[0]["record_digest"] == record.record_digest
    assert json.loads(model_a.calls[1]["prompt"])["developmental_history"] == []
    assert json.loads(model_b.calls[1]["prompt"])["developmental_history"] == []
    assert json.loads(model_a.calls[2]["prompt"])["developmental_history"] == a_history
    assert all(item["history_record_ids"] == [record.record_id]
        for item in (result["observations"][0], result["observations"][2],
            result["observations"][4]))
    assert all(item["history_record_ids"] == []
        for item in (result["observations"][1], result["observations"][3]))
    assert record.current_truth is False and record.authority is False


def test_task_family_progression_is_receipt_bound_bounded_and_restart_read_only(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A fixture progression reports exact episodes and never claims learning."""
    from scripts.stage_resident_objective_intervention import stage_request

    fake = SessionBoundFakeInvoker()
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    acquisition = cognition.run_tick(snapshot=snapshot(), tick_id="progression-history-seed")
    assert acquisition.written_record_id
    config_path = tmp_path / "progression-config.json"
    config_path.write_text(json.dumps({"schema": CONFIG_SCHEMA, "enabled": True,
        "history_root": str(tmp_path / "history"), "state_root": str(tmp_path / "state"),
        "allowed_source_kinds": ["capability_registry", "embodiment"],
        "max_selected_facts": 16, "max_retrieved_records": 4,
        "comparison_enabled": True}), encoding="utf-8")
    requests: list[tuple[str, str]] = []
    for index, probes in enumerate(((7, 8, 9), (10, 11, 12)), start=1):
        task = ObjectivePredictionTask(3, 2, probes[0], probes[1:],
            task_family_id="integer_affine_prediction")
        request_id = f"progression-episode-{index}"
        stage_request(config_path=config_path, request_id=request_id, task=task)
        request = load_objective_request(tmp_path / "state")
        assert request is not None
        result = cognition.run_objective_intervention_once(snapshot=snapshot(),
            tick_id=f"progression-tick-{index}", objective_task=objective_task_for_request(request),
            request_id=request["request_id"], request_digest=request["request_digest"])
        assert result.changed_cognition_measurement_id
        requests.append((request_id, request["request_digest"]))

    checkpoint_before_report = cognition.state_path.read_bytes()
    progression = cognition.verified_objective_task_family_progression(
        request_refs=tuple(reversed(requests)))
    assert cognition.state_path.read_bytes() == checkpoint_before_report
    assert progression["status"] == "comparable_scored_episodes"
    assert progression["task_family_id"] == "integer_affine_prediction"
    assert progression["episode_count"] == 2
    assert [episode["tick_id"] for episode in progression["episodes"]] == [
        "progression-tick-1", "progression-tick-2"]
    assert progression["same_model_generation_controls"] is True
    assert progression["distinct_task_instances"] is True
    assert progression["distinct_probe_sets"] is True
    assert progression["actual_nonsynthetic_inference_verified"] is False
    assert progression["learning_established"] is False
    assert progression["performance_improvement_established"] is False
    assert all("multiplier" not in json.dumps(episode)
        for episode in progression["episodes"])
    before = len(fake.requests)
    restarted, _ = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    recovered = restarted.verified_objective_task_family_progression(request_refs=tuple(requests))
    assert recovered == progression
    assert len(fake.requests) == before
    # A changed effective generation ceiling must split the trajectory rather
    # than being averaged into a same-model progression claim.
    fake.effective_generation_ceiling = 128
    third_task = ObjectivePredictionTask(3, 2, 13, (14, 15),
        task_family_id="integer_affine_prediction")
    stage_request(config_path=config_path, request_id="progression-episode-3", task=third_task)
    third_request = load_objective_request(tmp_path / "state")
    assert third_request is not None
    third_result = restarted.run_objective_intervention_once(snapshot=snapshot(),
        tick_id="progression-tick-3", objective_task=objective_task_for_request(third_request),
        request_id=third_request["request_id"], request_digest=third_request["request_digest"])
    assert third_result.changed_cognition_measurement_id
    changed = restarted.verified_objective_task_family_progression(
        request_refs=(*requests, (third_request["request_id"], third_request["request_digest"])))
    assert changed["status"] == "descriptive_episodes_not_comparable"
    assert changed["same_model_generation_controls"] is False
    assert changed["actual_nonsynthetic_inference_verified"] is False
    assert changed["performance_improvement_established"] is False
    from scripts import inspect_resident_objective_result as objective_inspector
    from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
    serving_config = tmp_path / "progression-serving-config.json"
    serving_config.write_text(json.dumps({
        "schema_version": "sentientos.resident_cognitive_model_serving_config:v1",
        "enabled": True, "installation_identity": "progression-installation",
        "serving_operation_id": "progression-inspection", "expected_activation_state_digest": "d" * 64,
    }), encoding="utf-8")
    registry = InstallationStateRegistry._for_testing(tmp_path / "progression-installations")
    registry.open(InstallationIdentity("progression-installation"), create=True)
    monkeypatch.setattr(objective_inspector, "ResidentCognitiveInvocationReceiptReader",
        lambda _installation: fake)
    before_inspection = {path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*") if path.is_file()}
    inspected = objective_inspector.inspect_progression(cognition_config_path=config_path,
        serving_config_path=serving_config, request_refs=tuple(requests) + (
            (third_request["request_id"], third_request["request_digest"]),),
        installation_registry=registry)
    after_inspection = {path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*") if path.is_file()}
    assert inspected == {**changed, "model_invoked": False, "write_performed": False}
    assert after_inspection == before_inspection
    # Reconstruct the same report in a new interpreter from the durable
    # cognition/experiment custody plus serialized fixture-issued receipts.
    # This checks restart reading, not model behavior or production custody.
    receipt_path = tmp_path / "fixture-issued-invocation-receipts.json"
    receipt_path.write_text(json.dumps({receipt_id: receipt.to_dict()
        for receipt_id, receipt in fake.receipts.items()}, sort_keys=True), encoding="utf-8")
    child_code = r'''
import json, sys
from pathlib import Path
from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION)
from sentientos.resident_developmental_cognition import (
    ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionOwner)
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier

root, receipt_path = Path(sys.argv[1]), Path(sys.argv[2])
refs = json.loads(sys.argv[3])
receipts = json.loads(receipt_path.read_text(encoding="utf-8"))
class PersistedFixtureReceiptVerifier:
    def verify_persisted_invocation_receipt(self, receipt_id, receipt_digest, **expected):
        value = receipts[receipt_id]
        assert value["receipt_id"] == receipt_id and value["receipt_digest"] == receipt_digest
        request = value["request"]
        assert request["request_id"] == expected["expected_request_id"]
        assert request["request_digest"] == expected["expected_request_digest"]
        assert request["active_model_identity"] == expected["expected_active_model_identity"]
        serving = request["linkage"]["resident_cognitive_serving"]
        assert serving["session_id"] == expected["expected_session_id"]
        assert serving["activation_state_semantic_digest"] == expected[
            "expected_session_binding"]["activation_state_semantic_digest"]
        return {key: value[key] for key in ("receipt_id", "receipt_digest", "request",
            "status", "output_digest", "output_truncated", "generation_config",
            "backend_completion", "observed_at") if key in value}

ledger = AdmissionLedger(root / "state" / "runtime_admissions.json")
definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
def current_sequence():
    admissions, _ = ledger.load()
    return max((item.issued_sequence for item in admissions), default=1)
def next_sequence():
    admissions, revocations = ledger.load()
    return max([item.issued_sequence for item in admissions]
        + [item.sequence for item in revocations] + [0]) + 1
writeback = ResidentDevelopmentalWritebackController(
    history_root=root / "history",
    admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger),
    current_sequence=current_sequence)
owner = ResidentDevelopmentalCognitionOwner(
    config=ResidentDevelopmentalCognitionConfig(root / "history", root / "state",
        ("capability_registry", "embodiment"), 16, 4, True),
    writeback=writeback,
    admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
    invoker=PersistedFixtureReceiptVerifier(), current_sequence=next_sequence)
print(json.dumps(owner.verified_objective_task_family_progression(
    request_refs=tuple(tuple(item) for item in refs)), sort_keys=True))
'''
    child = subprocess.run([sys.executable, "-c", child_code, str(tmp_path), str(receipt_path),
        json.dumps(requests + [(third_request["request_id"], third_request["request_digest"])]),
        ], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=True)
    assert json.loads(child.stdout.strip().splitlines()[-1]) == changed
    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="objective_progression_episode_count_invalid"):
        restarted.verified_objective_task_family_progression(request_refs=tuple(requests) * 9)
    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="objective_progression_duplicate_request"):
        restarted.verified_objective_task_family_progression(request_refs=(requests[0], requests[0]))


@pytest.mark.parametrize("mode,delta,stable,assessment", [
    ("derive_from_history", 1, True, "single_preregistered_task_scored"),
    ("no_difference", 0, True, "single_preregistered_task_scored"),
    ("degrade", -1, True, "single_preregistered_task_scored"),
    ("unstable", 1, False, "single_preregistered_task_scored"),
    ("malformed", 0, True, "single_preregistered_task_scored"),
    ("unavailable", None, None, "unscoreable_missing_output"),
])
def test_same_model_history_intervention_uses_preregistered_objective_oracle(
        tmp_path: Path, mode: str, delta: int | None, stable: bool | None,
        assessment: str) -> None:
    fake = FakeInvoker()
    fake.objective_mode = mode
    fake.history_interpretation = (
        "Historical examples: input 1 produced 5; input 2 produced 8.")
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    task = ObjectivePredictionTask(multiplier=3, offset=2, probe_input=7)
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake, objective_task=task)
    first = cognition.run_tick(snapshot=snapshot(), tick_id="objective-history-seed")
    assert first.status == "completed" and first.written_record_id
    second = cognition.run_tick(snapshot=snapshot(), tick_id="objective-history-comparison")
    assert second.changed_cognition_measurement_id is not None
    run = cognition.experiments.load_run(second.changed_cognition_measurement_id)
    contamination = run["contamination_assessment"]
    assert contamination["status"] == "not_assessed"
    assert run["contamination_reasons"] is None
    assert contamination["objective_task_digest"] == task.public_descriptor()["task_digest"]
    assert contamination["current_projection_digest"] == run["protocol"]["current_projection_digest"]
    assert contamination["history_examples_absent_from_current_context"] is None
    assert contamination["oracle_answer_absent_from_current_context"] is None
    assert contamination["authority"] is False
    evaluation = run["objective_evaluation"]
    projected = cognition.experiments.world_state_records(run_refs=((run["run_id"], run["run_digest"]),))
    assert len(projected) == 1 and projected[0]["observed_at"] is None
    assert projected[0]["payload"]["event_time_posture"] == "historical_event_time_unverified_or_incomplete"
    assert projected[0]["payload"]["objective_evaluation"] == evaluation
    assert projected[0]["payload"]["current_truth"] is False
    assert projected[0]["payload"]["learning_established"] is False
    assert projected == cognition.experiments.world_state_records(
        run_refs=((run["run_id"], run["run_digest"]),))
    projection_board = WorldStateBoardBuilder(clock=lambda: datetime(2026, 10, 12,
        tzinfo=timezone.utc)).build(projected)
    projection_source = next(source for source in projection_board.sources
        if source.source_id == projected[0]["source_id"])
    assert projection_source.staleness == "undated"
    with pytest.raises(DevelopmentalHistoryInterventionError,
                       match="run_projection_digest_mismatch"):
        cognition.experiments.world_state_records(run_refs=((run["run_id"], "sha256:wrong"),))
    assert evaluation["history_accuracy_delta"] == delta
    assert evaluation["restoration_correctness_stable"] is stable
    assert evaluation["assessment"] == assessment
    assert [row["condition_id"] for row in run["objective_scores"]] == [
        "history_present", "history_withheld", "history_restored"]
    reopened_store = DevelopmentalExperimentStore(tmp_path / "state")
    assert reopened_store.load_run(run["run_id"])["objective_evaluation"] == evaluation
    corrupted = {key: value for key, value in run.items()
        if key not in {"run_id", "run_digest"}}
    corrupted["contamination_assessment"] = {**contamination,
        "current_projection_digest": "sha256:" + "0" * 64}
    corrupt_id = reopened_store.persist_run(corrupted)
    with pytest.raises(DevelopmentalHistoryInterventionError,
            match="run_artifact_control_invalid"):
        reopened_store.load_run(corrupt_id)
    if mode == "derive_from_history":
        assert [row["score"]["answer"] for row in run["objective_scores"]] == [23, 0, 23]
        requests = [request for request in fake.requests
            if request.purpose == "resident_developmental_history_intervention_experiment"
            and "objective_task_plan_digest" in request.upstream_evidence]
        assert len(requests) == 3
        assert len({request.request_digest for request in requests}) == 3
        assert [json.loads(request.prompt)["developmental_history"] != []
            for request in requests] == [True, False, True]
        child = subprocess.run([sys.executable, "-c", """
import json, sys
from pathlib import Path
from sentientos.developmental_history_intervention_experiment import DevelopmentalExperimentStore
store=DevelopmentalExperimentStore(Path(sys.argv[1]))
run=store.load_run(sys.argv[2])
print(json.dumps(run["objective_evaluation"], sort_keys=True))
""", str(tmp_path / "state"), run["run_id"]], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, check=True)
        assert json.loads(child.stdout.strip().splitlines()[-1]) == evaluation
    # A completed trial is never replayed, and independently re-opened custody
    # recomputes the oracle scores from the original receipt-bound outputs.
    replay_requests = len(fake.requests)
    restarted, _ = owner(tmp_path, comparison=True, invoker=fake, objective_task=task)
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        restarted.run_tick(snapshot=snapshot(), tick_id="objective-history-comparison")
    assert len(fake.requests) == replay_requests


def test_same_model_truncated_objective_output_recovers_as_unscoreable(tmp_path: Path) -> None:
    fake = SessionBoundFakeInvoker()
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    task = ObjectivePredictionTask(multiplier=3, offset=2, probe_input=7,
        additional_probe_inputs=(8, 9))
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake, objective_task=task)
    cognition.run_tick(snapshot=snapshot(), tick_id="truncated-objective-seed")
    fake.truncate_objective_output = True
    result = cognition.run_tick(snapshot=snapshot(), tick_id="truncated-objective-run")
    run = cognition.experiments.load_run(result.changed_cognition_measurement_id)
    assert run["objective_evaluation"]["assessment"] == "unscoreable_truncated_output"
    assert run["objective_evaluation"]["history_correct_probe_delta"] is None
    assert [row["score"]["status"] for row in run["objective_scores"]] == [
        "output_truncated", "output_truncated", "output_truncated"]
    assert all(row["score"]["correct_count"] is None for row in run["objective_scores"])
    restarted, _ = owner(tmp_path, comparison=True, invoker=fake, objective_task=task)
    assert restarted.experiments.load_run(run["run_id"])["objective_evaluation"] == run["objective_evaluation"]


def test_explicit_objective_request_runs_once_without_developmental_writeback(tmp_path: Path) -> None:
    fake = SessionBoundFakeInvoker()
    fake.effective_generation_ceiling = 128
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake)
    seeded = cognition.run_tick(snapshot=snapshot(), tick_id="one-shot-history-seed")
    assert seeded.written_record_id is not None
    prior_records = cognition.writeback.store.records()
    task = ObjectivePredictionTask(3, 2, 7, (8, 9))
    request_path = stage_objective_request(tmp_path / "state",
        request_id="operator-one-shot-001", task=task)
    request = load_objective_request(tmp_path / "state")
    assert request_path.exists() and request is not None
    assert objective_task_for_request(request).public_descriptor() == task.public_descriptor()
    assert request["task_descriptor"]["task_digest"] == task.public_descriptor()["task_digest"]

    result = cognition.run_objective_intervention_once(snapshot=snapshot(),
        tick_id="one-shot-objective-trial", objective_task=objective_task_for_request(request),
        request_id=request["request_id"], request_digest=request["request_digest"])
    assert result.status == "objective_intervention_completed"
    assert result.changed_cognition_measurement_id
    assert result.written_record_id is None and result.writeback_receipt_id is None
    assert result.canonical_explicit_user_retention_mutated is False
    assert cognition.writeback.store.records() == prior_records
    run = cognition.experiments.load_run(result.changed_cognition_measurement_id)
    assert run["objective_evaluation"]["assessment"] == "preregistered_probe_suite_scored"
    assert [item["condition_id"] for item in run["conditions"]] == [
        "history_present", "history_withheld", "history_restored"]
    objective_calls = [request for request in fake.requests
        if request.purpose == "resident_developmental_history_intervention_experiment"
        and "objective_task_plan_digest" in request.upstream_evidence]
    assert len(objective_calls) == 3
    assert all(request.upstream_evidence["objective_task_digest"] == task.public_descriptor()["task_digest"]
        for request in objective_calls)
    assert cognition.objective_request_disposition(request_id=request["request_id"],
        request_digest=request["request_digest"]) == "completed"
    report = cognition.verified_objective_measurement_summary(
        measurement_id=result.changed_cognition_measurement_id, request=request)
    assert report["status"] == "verified_objective_measurement"
    assert report["actual_nonsynthetic_inference_verified"] is False
    assert report["objective_evaluation"] == run["objective_evaluation"]
    assert [row["generation_budget"]["preregistered_max_new_tokens"]
        for row in report["conditions"]] == [512, 512, 512]
    assert [row["generation_budget"]["effective_max_new_tokens"]
        for row in report["conditions"]] == [128, 128, 128]
    assert all(row["generation_budget"]["posture"] == "effective_ceiling_reduced"
        for row in report["conditions"])
    assert all(row["generation_budget"]["backend_completion_reason_verified"] is False
        for row in report["conditions"])
    assert [row["condition_id"] for row in report["conditions"]] == [
        "history_present", "history_withheld", "history_restored"]
    assert all("output_text" not in row and "answer" not in row
        for row in report["conditions"])
    altered_request = dict(request); altered_request["request_id"] = "substituted-request"
    with pytest.raises(ResidentDevelopmentalCognitionError, match="objective_outcome_request_invalid"):
        cognition.verified_objective_measurement_summary(
            measurement_id=result.changed_cognition_measurement_id, request=altered_request)
    assert stored_objective_request_disposition(tmp_path / "state",
        request_id=request["request_id"], request_digest=request["request_digest"]) == "completed"
    second_task = ObjectivePredictionTask(3, 2, 8)
    old_bytes = request_path.read_bytes()
    stage_objective_request(tmp_path / "state", request_id="operator-one-shot-002",
        task=second_task)
    archive_name = hashlib.sha256(request["request_id"].encode()).hexdigest() + ".json"
    archived = tmp_path / "state" / "objective_intervention_request_archive" / archive_name
    assert archived.read_bytes() == old_bytes
    next_request = load_objective_request(tmp_path / "state")
    assert next_request is not None and next_request["request_id"] == "operator-one-shot-002"
    before = len(fake.requests)
    with pytest.raises(ResidentDevelopmentalCognitionError, match="objective_request_completed"):
        cognition.run_objective_intervention_once(snapshot=snapshot(),
            tick_id="one-shot-objective-replay", objective_task=task,
            request_id=request["request_id"], request_digest=request["request_digest"])
    assert len(fake.requests) == before


def test_backend_token_limit_receipt_prevents_a_parseable_objective_score(tmp_path: Path) -> None:
    fake = SessionBoundFakeInvoker()
    fake.backend_completion_observation = {
        "schema_version": "sentientos.llama_cpp_completion_observation:v1",
        "backend": "llama_cpp", "finish_reason": "length",
        "completion_tokens": 512, "prompt_tokens": 120, "token_limit_reached": True}
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake)
    assert cognition.run_tick(snapshot=snapshot(), tick_id="backend-limit-seed").written_record_id
    task = ObjectivePredictionTask(3, 2, 7, (8, 9))
    stage_objective_request(tmp_path / "state", request_id="backend-limit-objective", task=task)
    request = load_objective_request(tmp_path / "state")
    assert request is not None
    result = cognition.run_objective_intervention_once(snapshot=snapshot(),
        tick_id="backend-limit-objective-tick", objective_task=objective_task_for_request(request),
        request_id=request["request_id"], request_digest=request["request_digest"])
    run = cognition.experiments.load_run(result.changed_cognition_measurement_id)
    assert all(row["score"]["status"] == "output_truncated"
        for row in run["objective_scores"])
    assert run["objective_evaluation"]["assessment"] == "unscoreable_truncated_output"
    report = cognition.verified_objective_measurement_summary(
        measurement_id=result.changed_cognition_measurement_id, request=request)
    assert report["actual_nonsynthetic_inference_verified"] is False
    assert all(row["backend_completion"]["finish_reason"] == "length"
        and row["backend_completion"]["token_limit_reached"] is True
        and row["generation_budget"]["posture"] == "effective_ceiling_matches_preregistered_request"
        for row in report["conditions"])


def test_objective_request_digest_collision_and_no_history_are_terminal(tmp_path: Path) -> None:
    fake = FakeInvoker()
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake)
    task = ObjectivePredictionTask(3, 2, 7)
    payload = stage_objective_request(tmp_path / "state", request_id="no-history-request", task=task)
    request = load_objective_request(tmp_path / "state")
    assert request is not None and payload.exists()
    result = cognition.run_objective_intervention_once(snapshot=snapshot(),
        tick_id="no-history-terminal", objective_task=task,
        request_id=request["request_id"], request_digest=request["request_digest"])
    assert result.status == "objective_blocked_no_eligible_history"
    assert not fake.requests
    assert cognition.objective_request_disposition(request_id=request["request_id"],
        request_digest=request["request_digest"]) == "completed"
    assert cognition.objective_request_disposition(request_id=request["request_id"],
        request_digest="0" * 64) == "identity_conflict"


def test_interrupted_one_shot_request_is_not_replayed_after_restart(tmp_path: Path) -> None:
    fake = FakeInvoker()
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake)
    assert cognition.run_tick(snapshot=snapshot(), tick_id="interrupted-one-shot-seed").written_record_id
    task = ObjectivePredictionTask(3, 2, 7)
    stage_objective_request(tmp_path / "state", request_id="interrupted-one-shot", task=task)
    request = load_objective_request(tmp_path / "state")
    assert request is not None
    fake.fail_objective_condition = "history_present"
    with pytest.raises(RuntimeError, match="fixture_interrupted"):
        cognition.run_objective_intervention_once(snapshot=snapshot(),
            tick_id="interrupted-one-shot-tick", objective_task=task,
            request_id=request["request_id"], request_digest=request["request_digest"])
    calls_at_interruption = len(fake.requests)
    restarted, _ = owner(tmp_path, comparison=True, invoker=fake)
    assert restarted.objective_request_disposition(request_id=request["request_id"],
        request_digest=request["request_digest"]) == "interrupted"
    with pytest.raises(ResidentDevelopmentalCognitionError, match="objective_request_interrupted"):
        restarted.run_objective_intervention_once(snapshot=snapshot(),
            tick_id="interrupted-one-shot-replay", objective_task=task,
            request_id=request["request_id"], request_digest=request["request_digest"])
    assert len(fake.requests) == calls_at_interruption


def test_recovered_one_shot_score_is_returned_without_replaying_inference(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeInvoker()
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake)
    assert cognition.run_tick(snapshot=snapshot(), tick_id="recoverable-request-seed").written_record_id
    task = ObjectivePredictionTask(3, 2, 7, (8, 9))
    stage_objective_request(tmp_path / "state", request_id="recoverable-one-shot", task=task)
    request = load_objective_request(tmp_path / "state")
    assert request is not None
    real_persist_run = cognition.experiments.persist_run

    def interrupt_after_scores(payload):
        raise OSError("fixture interruption after objective scores")

    monkeypatch.setattr(cognition.experiments, "persist_run", interrupt_after_scores)
    with pytest.raises(OSError, match="after objective scores"):
        cognition.run_objective_intervention_once(snapshot=snapshot(),
            tick_id="recoverable-one-shot-tick", objective_task=task,
            request_id=request["request_id"], request_digest=request["request_digest"])
    calls_at_interruption = len(fake.requests)
    monkeypatch.setattr(cognition.experiments, "persist_run", real_persist_run)

    restarted, _ = owner(tmp_path, comparison=True, invoker=fake)
    outcome = restarted.verified_objective_measurement_for_request(
        request_id=request["request_id"], request_digest=request["request_digest"])

    assert outcome["status"] == "verified_objective_measurement"
    assert outcome["recovery_posture"] == "completed_run_loaded_without_inference_replay"
    assert outcome["actual_nonsynthetic_inference_verified"] is False
    assert outcome["objective_evaluation"]["assessment"] == "preregistered_probe_suite_scored"
    assert len(outcome["conditions"]) == 3
    assert len(fake.requests) == calls_at_interruption

    from scripts.inspect_resident_objective_result import inspect_result
    cognition_config = tmp_path / "cognition-config.json"
    cognition_config.write_text(json.dumps({"schema": CONFIG_SCHEMA, "enabled": True,
        "history_root": str(tmp_path / "history"), "state_root": str(tmp_path / "state"),
        "allowed_source_kinds": ["capability_registry"], "max_selected_facts": 1,
        "max_retrieved_records": 4, "comparison_enabled": True}), encoding="utf-8")
    serving_config = tmp_path / "serving-config.json"
    serving_config.write_text(json.dumps({"schema_version": "sentientos.resident_cognitive_model_serving_config:v1",
        "enabled": True, "installation_identity": "install-1", "serving_operation_id": "inspect-operation",
        "expected_activation_state_digest": "a" * 64}), encoding="utf-8")
    from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
    registry = InstallationStateRegistry._for_testing(tmp_path / "installation-state")
    registry.open(InstallationIdentity("install-1"), create=True)
    before = {path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*") if path.is_file()}
    inspected = inspect_result(cognition_config_path=cognition_config,
        serving_config_path=serving_config, request_id=request["request_id"],
        request_digest=request["request_digest"], installation_registry=registry)
    after = {path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*") if path.is_file()}
    assert inspected["status"] == "verified_objective_measurement"
    assert inspected["measurement_digest"] == outcome["measurement_digest"]
    assert inspected["recovery_posture"] == "completed_run_loaded_without_inference_replay"
    assert inspected["contamination_assessment"]["status"] == "not_assessed"
    assert inspected["contamination_assessment"]["objective_task_digest"] == task.public_descriptor()["task_digest"]
    assert inspected["actual_nonsynthetic_inference_verified"] is False
    assert after == before
    assert len(fake.requests) == calls_at_interruption


def test_read_only_objective_result_inspection_reconciles_existing_custody(tmp_path: Path) -> None:
    from scripts.inspect_resident_objective_result import inspect_result

    fake = FakeInvoker()
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake)
    assert cognition.run_tick(snapshot=snapshot(), tick_id="inspect-result-seed").written_record_id
    task = ObjectivePredictionTask(3, 2, 7, (8, 9))
    stage_objective_request(tmp_path / "state", request_id="inspect-result-request", task=task)
    request = load_objective_request(tmp_path / "state")
    assert request is not None
    result = cognition.run_objective_intervention_once(snapshot=snapshot(),
        tick_id="inspect-result-tick", objective_task=task,
        request_id=request["request_id"], request_digest=request["request_digest"])
    assert result.changed_cognition_measurement_id

    cognition_config = tmp_path / "cognition.json"
    cognition_config.write_text(json.dumps({"schema": CONFIG_SCHEMA, "enabled": True,
        "history_root": str(tmp_path / "history"), "state_root": str(tmp_path / "state"),
        "allowed_source_kinds": ["capability_registry"], "max_selected_facts": 1,
        "max_retrieved_records": 4, "comparison_enabled": True}), encoding="utf-8")
    serving_config = tmp_path / "serving.json"
    serving_config.write_text(json.dumps({"schema_version": "sentientos.resident_cognitive_model_serving_config:v1",
        "enabled": True, "installation_identity": "install-1", "serving_operation_id": "inspect-operation",
        "expected_activation_state_digest": "a" * 64}), encoding="utf-8")
    from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
    registry = InstallationStateRegistry._for_testing(tmp_path / "installation-state")
    registry.open(InstallationIdentity("install-1"), create=True)
    before = {path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*") if path.is_file()}

    lineage = stored_objective_request_record(tmp_path / "state",
        request_id=request["request_id"], request_digest=request["request_digest"])
    assert lineage["tick_id"] == "inspect-result-tick"
    report = inspect_result(cognition_config_path=cognition_config,
        serving_config_path=serving_config, request_id=request["request_id"],
        request_digest=request["request_digest"], installation_registry=registry)

    assert report["status"] == "verified_objective_measurement"
    assert report["tick_id"] == "inspect-result-tick"
    assert report["actual_nonsynthetic_inference_verified"] is False
    assert report["model_invoked"] is False and report["write_performed"] is False
    after = {path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before


def test_staged_objective_request_rejects_noncanonical_and_substituted_bytes(tmp_path: Path) -> None:
    task = ObjectivePredictionTask(3, 2, 7)
    stage_objective_request(tmp_path, request_id="fixed-task", task=task)
    with pytest.raises(ResidentDevelopmentalCognitionError, match="slot_occupied"):
        stage_objective_request(tmp_path, request_id="pending-task", task=task)
    with pytest.raises(ResidentDevelopmentalCognitionError, match="identity_conflict"):
        stage_objective_request(tmp_path, request_id="fixed-task",
            task=ObjectivePredictionTask(3, 9, 7))
    request_path = tmp_path / "pending_objective_intervention.json"
    request_path.write_text(request_path.read_text().replace('"offset": 2', '"offset": 9'),
        encoding="utf-8")
    with pytest.raises(ResidentDevelopmentalCognitionError, match="objective_request_invalid"):
        load_objective_request(tmp_path)


def test_same_model_probe_suite_partial_scores_reach_later_cognition(tmp_path: Path) -> None:
    fake = FakeInvoker()
    fake.objective_mode = "partial"
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    task = ObjectivePredictionTask(3, 2, 7, (8, 9, 10))
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake, objective_task=task)
    seeded = cognition.run_tick(snapshot=snapshot(), tick_id="probe-suite-seed")
    assert seeded.written_record_id
    measured = cognition.run_tick(snapshot=snapshot(), tick_id="probe-suite-measured")
    run = cognition.experiments.load_run(measured.changed_cognition_measurement_id)
    evaluation = run["objective_evaluation"]
    assert evaluation["assessment"] == "preregistered_probe_suite_scored"
    assert evaluation["history_accuracy_delta"] == 0
    assert evaluation["probe_count"] == 4
    assert evaluation["condition_correct_counts"] == [2, 0, 2]
    assert evaluation["history_correct_probe_delta"] == 2
    assert evaluation["restoration_correct_probe_delta"] == 0
    child = subprocess.run([sys.executable, "-c", """
import json, sys
from pathlib import Path
from sentientos.developmental_history_intervention_experiment import DevelopmentalExperimentStore
run=DevelopmentalExperimentStore(Path(sys.argv[1])).load_run(sys.argv[2])
print(json.dumps({"run_id":run["run_id"],"objective_evaluation":run["objective_evaluation"],
    "correct_counts":[item["score"]["correct_count"] for item in run["objective_scores"]]}, sort_keys=True))
""", str(tmp_path / "state"), run["run_id"]], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, check=True)
    child_value = json.loads(child.stdout.strip().splitlines()[-1])
    assert child_value["objective_evaluation"] == evaluation
    assert child_value["correct_counts"] == [2, 0, 2]
    records = cognition.experiments.world_state_records(
        run_refs=((run["run_id"], run["run_digest"]),))
    assert records[0]["payload"]["objective_evaluation"] == evaluation
    assert [item["correct_count"] for item in records[0]["payload"]["objective_scores"]] == [2, 0, 2]

    from sentientos.world_state_board import WorldStateBoardBuilder
    from tests.test_resident_developmental_cognition import owner as developmental_owner
    snapshot_value = WorldStateBoardBuilder().build(records)
    downstream_root = tmp_path / "later-cognition"
    downstream, _ = developmental_owner(downstream_root,
        allowed_source_kinds=("embodiment",), max_selected_facts=1)
    first = downstream.run_tick(snapshot=snapshot_value, tick_id="suite-history-tick-n")
    assert first.written_record_id
    retained = downstream.writeback.store.get(first.written_record_id).candidate[
        "selected_facts"][0]["payload"]
    assert retained["objective_evaluation"]["history_correct_probe_delta"] == 2
    assert [item["correct_count"] for item in retained["objective_scores"]] == [2, 0, 2]
    recovered, invoker = developmental_owner(downstream_root,
        allowed_source_kinds=("embodiment",), max_selected_facts=1)
    later = recovered.run_tick(snapshot=snapshot_value, tick_id="suite-history-tick-n-plus-one")
    assert first.written_record_id in later.prior_record_ids
    retrieval = next(request for request in invoker.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    assert first.written_record_id in retrieval.upstream_evidence["record_ids"]


def test_same_model_objective_score_recovery_rejects_rehashed_substitution(tmp_path: Path) -> None:
    fake = FakeInvoker()
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    task = ObjectivePredictionTask(multiplier=3, offset=2, probe_input=7)
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake, objective_task=task)
    cognition.run_tick(snapshot=snapshot(), tick_id="score-recovery-seed")
    result = cognition.run_tick(snapshot=snapshot(), tick_id="score-recovery-run")
    assert result.changed_cognition_measurement_id
    valid = cognition.experiments.load_run(result.changed_cognition_measurement_id)
    altered = dict(valid)
    altered.pop("run_id"); altered.pop("run_digest")
    altered["objective_scores"] = [dict(row) for row in valid["objective_scores"]]
    altered["objective_scores"][0] = dict(altered["objective_scores"][0])
    score = dict(altered["objective_scores"][0]["score"])
    score["answer"] = 22
    altered["objective_scores"][0]["score"] = score
    forged_id = cognition.experiments.persist_run(altered)
    with pytest.raises(DevelopmentalHistoryInterventionError,
                       match="objective_score_binding_invalid"):
        cognition.experiments.load_run(forged_id)


def test_history_intervention_run_reaches_world_state_and_later_cognition(tmp_path: Path) -> None:
    fake = FakeInvoker()
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    task = ObjectivePredictionTask(multiplier=3, offset=2, probe_input=7)
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake, objective_task=task)
    cognition.run_tick(snapshot=snapshot(), tick_id="world-projection-seed")
    result = cognition.run_tick(snapshot=snapshot(), tick_id="world-projection-run")
    run = cognition.experiments.load_run(result.changed_cognition_measurement_id)
    config = {"schema_version": WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V4,
        "enabled": True, "store_root": None, "experiment_result_ids": [],
        "consequence_chain_ids": [], "model_replacement_state_root": None,
        "model_replacement_runs": [], "proposal_review_log_path": None,
        "proposal_review_receipt_ids": [], "fulfillment_receipt_log_path": None,
        "fulfillment_receipt_ids": [], "developmental_history_intervention_runs":[
            {"run_id":run["run_id"],"run_digest":run["run_digest"]}]}
    config["config_digest"] = embodied_digest(config)
    config_path = tmp_path / "projection.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    loaded = _load_embodied_consequence_projection(str(config_path))
    assert loaded[11] == ((run["run_id"], run["run_digest"]),)
    assert loaded[12]["status"] == "verified"

    surfaces = RuntimeMaintenanceSurfaces(tmp_path, runtime_state_root=tmp_path / "maintenance",
        resident_developmental_owner=cognition,  # type: ignore[arg-type]
        developmental_history_intervention_run_refs=loaded[11])
    surfaces.build_world_state_board(tick_id="2026-10-12T00:00:00+00:00")
    world = surfaces.current_world_state_snapshot
    assert world is not None
    source = next(item for item in world.sources
        if item.source_id == "developmental-history-run:" + run["run_id"])
    fact = next(item for item in world.facts if item.source.source_id == source.source_id)
    assert source.staleness == "undated"
    assert fact.payload["objective_evaluation"]["history_accuracy_delta"] == 1
    assert fact.effect_claimed is False and fact.effect_proven is False
    minimal_snapshot = WorldStateBoardBuilder().build([
        cognition.experiments.world_state_records(
            run_refs=((run["run_id"], run["run_digest"]),))[0]])
    later, later_fake = owner(tmp_path / "later", allowed_source_kinds=("embodiment",))
    first = later.run_tick(snapshot=minimal_snapshot, tick_id="experiment-evidence-tick-n")
    assert first.written_record_id and fact.fact_id in first.selected_fact_ids
    restarted, restarted_fake = owner(tmp_path / "later", allowed_source_kinds=("embodiment",))
    second = restarted.run_tick(snapshot=minimal_snapshot, tick_id="experiment-evidence-tick-n-plus-one")
    assert first.written_record_id in second.prior_record_ids
    retrieval = next(request for request in restarted_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    assert first.written_record_id in retrieval.upstream_evidence["record_ids"]


def test_interrupted_same_model_trial_recovers_checkpointed_score_without_replay(tmp_path: Path) -> None:
    fake = FakeInvoker()
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    task = ObjectivePredictionTask(multiplier=3, offset=2, probe_input=7)
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake, objective_task=task)
    cognition.run_tick(snapshot=snapshot(), tick_id="interrupted-score-seed")
    fake.fail_objective_condition = "history_withheld"
    with pytest.raises(RuntimeError, match="fixture_interrupted_before_condition_invocation"):
        cognition.run_tick(snapshot=snapshot(), tick_id="interrupted-objective-trial")
    protocol_paths = list(fake.objective_plan_root.glob("devexp-protocol-*.json"))
    assert len(protocol_paths) == 1
    protocol = cognition.experiments.load_protocol(protocol_paths[0].stem)
    observations = cognition._recover_observation_ticks(include_records=True)
    condition = next(value for value in observations.values()
        if value.get("tick_id") == "interrupted-objective-trial")
    restarted_store = DevelopmentalExperimentStore(tmp_path / "state")
    recovered = restarted_store.load_objective_condition_score(protocol,
        condition_id="history_present", observation=condition)
    assert recovered["score"]["correct"] is True
    assert "output_text" not in recovered["score"]
    assert recovered["score"]["output_retention_posture"] == (
        "live_bytes_digest_verified_not_retained")
    assert recovered["score"]["output_digest"] == condition["output_digest"]
    condition_path = tmp_path / "state" / "cognition_observations" / (
        condition["observation_id"] + ".json")
    child = subprocess.run([sys.executable, "-c", """
import json, sys
from pathlib import Path
from sentientos.developmental_history_intervention_experiment import DevelopmentalExperimentStore
store=DevelopmentalExperimentStore(Path(sys.argv[1]))
protocol=store.load_protocol(sys.argv[2])
observation=json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
score=store.load_objective_condition_score(protocol, condition_id="history_present", observation=observation)
print(json.dumps(score["score"], sort_keys=True))
""", str(tmp_path / "state"), protocol.protocol_id, str(condition_path)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=True)
    assert json.loads(child.stdout.strip().splitlines()[-1]) == recovered["score"]
    with pytest.raises(DevelopmentalHistoryInterventionError,
                       match="objective_condition_score_missing"):
        restarted_store.load_objective_condition_score(protocol,
            condition_id="history_withheld", observation=condition)
    invocations = len(fake.requests)
    fake.fail_objective_condition = None
    restarted, _ = owner(tmp_path, comparison=True, invoker=fake, objective_task=task)
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        restarted.run_tick(snapshot=snapshot(), tick_id="interrupted-objective-trial")
    assert len(fake.requests) == invocations


def test_final_score_checkpoints_recover_run_after_precommit_interruption(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeInvoker()
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    task = ObjectivePredictionTask(multiplier=3, offset=2, probe_input=7)
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake, objective_task=task)
    seeded = cognition.run_tick(snapshot=snapshot(), tick_id="final-score-recovery-seed")
    assert seeded.written_record_id

    def interrupt_after_all_scores(_payload):
        raise OSError("fixture interruption after final score checkpoint")

    monkeypatch.setattr(cognition.experiments, "persist_run", interrupt_after_all_scores)
    with pytest.raises(OSError, match="final score checkpoint"):
        cognition.run_tick(snapshot=snapshot(), tick_id="final-score-recovery-trial")
    request_count = len(fake.requests)
    score_files = list((tmp_path / "state" / "developmental_experiments" / "protocols").glob(
        "objective-score-*.json"))
    assert len(score_files) == 3

    restarted, _ = owner(tmp_path, comparison=True, invoker=fake, objective_task=task)
    refs = restarted.recovered_objective_experiment_run_refs()
    assert len(refs) == 1
    assert restarted.inspect_completed_objective_experiment_run_refs() == ()
    run_id, run_digest = refs[0]
    run = restarted.experiments.load_run(run_id)
    assert run["run_digest"] == run_digest
    assert run["objective_evaluation"]["history_accuracy_delta"] == 1
    assert run["objective_evaluation"]["restoration_correctness_stable"] is True
    assert len(run["objective_scores"]) == 3
    projected = restarted.experiments.world_state_records(run_refs=refs)
    assert len(projected) == 1
    assert projected[0]["payload"]["objective_evaluation"] == run["objective_evaluation"]
    assert "output_text" not in json.dumps(projected)
    assert len(fake.requests) == request_count
    state = restarted._state()
    intent = next(row for row in state["incomplete_ticks"]
        if row.get("tick_id") == "final-score-recovery-trial")
    assert intent["status"] == "interrupted_recovered"
    assert intent["experiment_recovery_posture"] == (
        "complete_scored_run_recovered_without_inference_replay")
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        restarted.run_tick(snapshot=snapshot(), tick_id="final-score-recovery-trial")
    assert len(fake.requests) == request_count


def test_operator_staging_requires_read_only_checkpointed_admitted_history(tmp_path: Path) -> None:
    from scripts.stage_resident_objective_intervention import stage_request

    config_path = tmp_path / "resident-cognition.json"
    config_path.write_text(json.dumps({"schema": CONFIG_SCHEMA, "enabled": True,
        "history_root": str(tmp_path / "history"), "state_root": str(tmp_path / "state"),
        "allowed_source_kinds": ["capability_registry"], "max_selected_facts": 1,
        "max_retrieved_records": 4, "comparison_enabled": True}), encoding="utf-8")
    task = ObjectivePredictionTask(multiplier=3, offset=2, probe_input=7)
    request_path = tmp_path / "state" / "pending_objective_intervention.json"
    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="objective_intervention_requires_checkpointed_history"):
        stage_request(config_path=config_path, request_id="history-not-yet-committed", task=task)
    assert not request_path.exists()

    cognition, _ = owner(tmp_path, comparison=True)
    first = cognition.run_tick(snapshot=snapshot(), tick_id="stage-preflight-history-seed")
    assert first.written_record_id and first.writeback_receipt_id
    state_before = cognition.state_path.read_bytes()
    record_ids_before = tuple(sorted(path.name for path in cognition.writeback.store.records_root.glob("*.json")))
    receipt_ids_before = tuple(sorted(path.name for path in cognition.writeback.store.receipts_root.glob("*.json")))
    staged_path, payload, verified_count = stage_request(
        config_path=config_path, request_id="history-now-committed", task=task)
    assert staged_path == request_path and verified_count == 1
    assert payload["request_id"] == "history-now-committed"
    assert load_objective_request(tmp_path / "state")["request_digest"] == payload["request_digest"]
    assert cognition.state_path.read_bytes() == state_before
    assert tuple(sorted(path.name for path in cognition.writeback.store.records_root.glob("*.json"))) == record_ids_before
    assert tuple(sorted(path.name for path in cognition.writeback.store.receipts_root.glob("*.json"))) == receipt_ids_before

    malformed_root = tmp_path / "malformed"
    malformed_root.mkdir()
    malformed_config = tmp_path / "malformed-config.json"
    malformed_config.write_text(json.dumps({"schema": CONFIG_SCHEMA, "enabled": True,
        "history_root": str(malformed_root / "history"),
        "state_root": str(malformed_root / "state"),
        "allowed_source_kinds": ["capability_registry"], "max_selected_facts": 1,
        "max_retrieved_records": 4, "comparison_enabled": True}), encoding="utf-8")
    (malformed_root / "state").mkdir()
    (malformed_root / "state" / "composition_state.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="checkpointed_history_state_invalid"):
        stage_request(config_path=malformed_config,
            request_id="malformed-checkpoint", task=task)
    assert not (malformed_root / "state" / "pending_objective_intervention.json").exists()

    conflict_root = tmp_path / "receipt-conflict"
    conflict_config = tmp_path / "receipt-conflict-config.json"
    conflict_config.write_text(json.dumps({"schema": CONFIG_SCHEMA, "enabled": True,
        "history_root": str(conflict_root / "history"),
        "state_root": str(conflict_root / "state"),
        "allowed_source_kinds": ["capability_registry"], "max_selected_facts": 1,
        "max_retrieved_records": 4, "comparison_enabled": True}), encoding="utf-8")
    conflict_owner, _ = owner(conflict_root, comparison=True)
    assert conflict_owner.run_tick(snapshot=snapshot(),
        tick_id="receipt-conflict-seed").written_record_id
    state_path = conflict_owner.state_path
    valid_state = json.loads(state_path.read_text(encoding="utf-8"))
    state = json.loads(json.dumps(valid_state))
    semantic = dict(state)
    semantic.pop("state_digest")
    semantic["completed_ticks"][0]["receipt_id"] = "substituted-receipt"
    state["completed_ticks"] = semantic["completed_ticks"]
    state["state_digest"] = "sha256:" + digest_payload(semantic)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="checkpointed_history_reference_unverified"):
        stage_request(config_path=conflict_config,
            request_id="substituted-receipt", task=task)
    assert not (conflict_root / "state" / "pending_objective_intervention.json").exists()

    state = json.loads(json.dumps(valid_state))
    semantic = dict(state)
    semantic.pop("state_digest")
    semantic["completed_ticks"] = [dict(semantic["completed_ticks"][0])]
    semantic["completed_ticks"][0]["tick_id"] = "relabelled-tick"
    state["completed_ticks"] = semantic["completed_ticks"]
    state["state_digest"] = "sha256:" + digest_payload(semantic)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="checkpointed_history_tick_binding_invalid"):
        stage_request(config_path=conflict_config,
            request_id="relabelled-history", task=task)
    assert not (conflict_root / "state" / "pending_objective_intervention.json").exists()

def test_missing_final_score_keeps_interrupted_trial_unfinalized(tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeInvoker()
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    task = ObjectivePredictionTask(multiplier=3, offset=2, probe_input=7)
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake, objective_task=task)
    cognition.run_tick(snapshot=snapshot(), tick_id="missing-score-recovery-seed")
    persist_score = cognition.experiments.persist_objective_condition_score

    def interrupt_before_restored_score(protocol, plan, *, condition_id, observation, receipt):
        if condition_id == "history_restored":
            raise OSError("fixture interruption before final score checkpoint")
        return persist_score(protocol, plan, condition_id=condition_id,
            observation=observation, receipt=receipt)

    monkeypatch.setattr(cognition.experiments, "persist_objective_condition_score",
        interrupt_before_restored_score)
    with pytest.raises(OSError, match="final score checkpoint"):
        cognition.run_tick(snapshot=snapshot(), tick_id="missing-score-recovery-trial")
    request_count = len(fake.requests)
    protocols = list((tmp_path / "state" / "developmental_experiments" / "protocols").glob(
        "devexp-protocol-*.json"))
    assert len(protocols) == 1

    restarted, _ = owner(tmp_path, comparison=True, invoker=fake, objective_task=task)
    assert restarted.recovered_objective_experiment_run_refs() == ()
    incomplete = next(row for row in restarted._state()["incomplete_ticks"]
        if row.get("tick_id") == "missing-score-recovery-trial")
    assert incomplete["status"] == "interrupted_recovered"
    assert "recovered_experiment_run_id" not in incomplete
    assert len(fake.requests) == request_count
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        restarted.run_tick(snapshot=snapshot(), tick_id="missing-score-recovery-trial")
    assert len(fake.requests) == request_count


def owner(root: Path, *, comparison: bool = False, invoker: FakeInvoker | None = None,
          allowed_source_kinds: tuple[str, ...] = ("capability_registry",),
          max_selected_facts: int = 1, objective_task=None):
    ledger = AdmissionLedger(root / "state" / "runtime_admissions.json")
    definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
    def current():
        admissions, _ = ledger.load(); return max((a.issued_sequence for a in admissions), default=1)
    def next_sequence():
        admissions, revocations = ledger.load()
        return max([a.issued_sequence for a in admissions] + [r.sequence for r in revocations], default=0) + 1
    ctrl = ResidentDevelopmentalWritebackController(history_root=root / "history",
        admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger), current_sequence=current)
    fake = invoker or FakeInvoker()
    result = ResidentDevelopmentalCognitionOwner(config=ResidentDevelopmentalCognitionConfig(
        root / "history", root / "state", allowed_source_kinds, max_selected_facts, 4, comparison), writeback=ctrl,
        admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
        invoker=fake, current_sequence=next_sequence, objective_task=objective_task)
    return result, fake


def test_host_resource_owner_reaches_restart_safe_later_tick_cognition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest,
) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_CONTROL_KERNEL_ROOT", str(tmp_path / "kernel"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(tmp_path / "pulse-trust"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(tmp_path / "pulse-trust" / "state.json"))
    reset_runtime_governor()
    request.addfinalizer(reset_runtime_governor)
    with pytest.raises(TypeError, match="trusted_host_resource_runtime_required"):
        RuntimeMaintenanceSurfaces(tmp_path, host_resource_runtime=object())  # type: ignore[arg-type]

    observed_at = "2026-10-12T00:00:00+00:00"

    def disk_fixture(*, observed_at: str | None = None) -> HostCollectorResult:
        return HostCollectorResult("disk", "available", observed_at or "unknown",
            "bounded_test_fixture", values={"used_percent": 25.0, "free_bytes": 4096})

    coordinator = HostResourceRuntimeCoordinator(
        kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE,
            decisions_path=tmp_path / "resource-decisions.jsonl"),
        runtime_state_root=tmp_path / "host-resource-runtime",
        plan=build_observation_plan(specs=[HostObservationCollectorSpec(
            "disk", True, ("linux", "unknown"), 1, disk_fixture)]),
        clock=lambda: observed_at,
    )
    first_owner, first_fake = owner(tmp_path / "cognition",
        allowed_source_kinds=("resource_governor",), max_selected_facts=1)
    first_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "maintenance-runtime",
        resident_developmental_owner=first_owner,  # type: ignore[arg-type]
        host_resource_runtime=coordinator,
    )
    runtime_tick = "2026-10-12T00:00:01+00:00"
    observation = first_surfaces.run_host_resource_observation_runtime(tick_id=runtime_tick)
    assert observation["status"] in {"ok", "degraded"}
    assert observation["no_effect_authority"] is True
    assert observation["host_mutation_performed"] is False
    first_surfaces.build_world_state_board(tick_id=runtime_tick)
    world = first_surfaces.current_world_state_snapshot
    assert world is not None
    source = next(item for item in world.sources
        if item.source_id == "host_resource_runtime:snapshot")
    fact = next(item for item in world.facts
        if item.source.source_id == source.source_id)
    assert fact.source.digest == source.digest
    assert fact.payload["disk_free_bytes"] == 4096
    assert fact.payload["observed_at"] == observed_at
    assert fact.effect_claimed is False and fact.effect_proven is False

    evaluation = coordinator.run_cycle(
        correlation_id=f"{runtime_tick}:host_resource_observation_runtime")
    assert evaluation is not None
    snapshot_record = next(item for item in world_state_records(evaluation)
        if item["source_id"] == "host_resource_runtime:snapshot")
    cognition_snapshot = WorldStateBoardBuilder().build([snapshot_record])
    # Tick identifiers are opaque. Durable commit order, not wall-clock parsing,
    # determines which history is available to subsequent cognition.
    cognition_tick_one = "resource-cognition-z"
    cognition_tick_two = "resource-cognition-a"
    first = first_owner.run_tick(snapshot=cognition_snapshot, tick_id=cognition_tick_one)
    assert first.written_record_id
    assert fact.fact_id in first.selected_fact_ids
    assert first.prior_record_ids == () and first.same_tick_history_excluded
    initial_request = first_fake.requests[0]
    assert not initial_request.upstream_evidence.get("record_ids", [])
    first_record = first_owner.writeback.store.get(first.written_record_id)
    assert any(item["source_id"] == source.source_id
        and item["digest"] == source.digest
        for item in first_record.candidate["selected_sources"])

    later_owner, later_fake = owner(tmp_path / "cognition",
        allowed_source_kinds=("resource_governor",), max_selected_facts=1)
    later = later_owner.run_tick(snapshot=cognition_snapshot, tick_id=cognition_tick_two)
    assert later.status == "completed"
    assert first.written_record_id in later.prior_record_ids
    history_request = next(request for request in later_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    assert first.written_record_id in history_request.upstream_evidence["record_ids"]


def test_quarantine_custody_failure_reaches_configured_cognition_and_next_tick_history(
    tmp_path: Path,
) -> None:
    from sentientos.integrity_quarantine import QUARANTINE_PATH

    target = tmp_path / QUARANTINE_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"schema_version":1')
    narrative = tmp_path / "pulse" / "integrity_incidents.jsonl"
    narrative.parent.mkdir(parents=True)
    narrative.write_text('{"severity":"critical","triggers":["attack confirmed"]}\n')

    cognition, fake = owner(tmp_path / "cognition", allowed_source_kinds=("quarantine",))
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=cognition,  # type: ignore[arg-type]
    )
    tick = "2026-10-11T00:00:00+00:00"
    surfaces.build_world_state_board(tick_id=tick)
    snapshot_value = surfaces.current_world_state_snapshot
    assert snapshot_value is not None
    facts = [fact for fact in snapshot_value.facts
             if fact.source.kind == "quarantine"]
    assert len(facts) == 1
    fact = facts[0]
    assert fact.subject.subject_kind == "quarantine_custody_observation"
    assert fact.disposition == "custody_invalid"
    assert fact.observed_at == tick
    assert fact.source.staleness == "unknown"
    assert fact.payload["custody_error_code"] == "quarantine_json_invalid"
    assert fact.payload["quarantine_active"] is None
    assert fact.payload["attack_established"] is False
    assert fact.payload["hostile_activity_established"] is False

    first = surfaces.run_resident_developmental_cognition(tick_id=tick)
    record_id = first["written_record_id"]
    assert first["status"] == "completed" and record_id
    interpretation = next(request for request in fake.requests
        if request.purpose == "resident_developmental_interpretation")
    interpretation_input = json.loads(interpretation.prompt)
    selected = interpretation_input["selection"]["facts"]
    assert "Do not infer hostile activity, attack, intent, or cause" in interpretation_input["instruction"]
    assert len(selected) == 1
    selected_payload = selected[0]["payload"]
    assert selected_payload["custody_error_code"] == "quarantine_json_invalid"
    assert selected_payload["quarantine_active"] is None
    assert selected_payload["attack_established"] is False
    assert "attack confirmed" not in interpretation.prompt
    stored = cognition.writeback.store.get(record_id)
    assert stored.candidate["selected_facts"][0]["source"]["kind"] == "quarantine"

    restarted, later_fake = owner(tmp_path / "cognition", invoker=FakeInvoker(),
        allowed_source_kinds=("quarantine",))
    later_fake.no_cognition_lesson = True
    later_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=restarted,  # type: ignore[arg-type]
    )
    later_tick = "2026-10-11T00:00:01+00:00"
    later_surfaces.build_world_state_board(tick_id=later_tick)
    later = later_surfaces.run_resident_developmental_cognition(tick_id=later_tick)
    retrieval = next(request for request in later_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    assert retrieval.upstream_evidence["record_ids"] == [record_id]
    assert fact.fact_id in retrieval.upstream_evidence["current_fact_ids"]
    context = json.loads(retrieval.prompt)
    assert context["current_evidence"]["facts"][0]["payload"]["custody_error_code"] == "quarantine_json_invalid"
    assert later["status"] == "completed"


def test_quarantine_custody_context_can_yield_scoped_later_tick_lesson(tmp_path: Path) -> None:
    """A cognition conclusion stays an untrusted, evidence-bound history candidate."""
    from sentientos.integrity_quarantine import QUARANTINE_PATH

    target = tmp_path / QUARANTINE_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"schema_version":1')
    cognition, _first_fake = owner(
        tmp_path / "cognition", allowed_source_kinds=("quarantine",))
    first_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=cognition,  # type: ignore[arg-type]
    )
    first_tick = "2026-10-11T00:00:00+00:00"
    first_surfaces.build_world_state_board(tick_id=first_tick)
    first = first_surfaces.run_resident_developmental_cognition(tick_id=first_tick)
    assert first["status"] == "completed" and first["written_record_id"]

    # The lesson-producing request is the ordinary later history-conditioned
    # cognition call. Its proposal is scoped to interpreting this custody
    # failure, keeps uncertainty, and makes no claim about hostile activity.
    second_fake = FakeInvoker()
    second_fake.lesson_statement = (
        "A failed quarantine custody read leaves the stored protective posture unknown.")
    second_fake.lesson_scope = "quarantine custody observation interpretation"
    second = owner(tmp_path / "cognition", invoker=second_fake,
        allowed_source_kinds=("quarantine",))[0]
    second_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=second,  # type: ignore[arg-type]
    )
    second_tick = "2026-10-11T00:00:01+00:00"
    second_surfaces.build_world_state_board(tick_id=second_tick)
    second_snapshot = second_surfaces.current_world_state_snapshot
    assert second_snapshot is not None
    custody_fact = next(fact for fact in second_snapshot.facts
        if fact.subject.subject_kind == "quarantine_custody_observation")
    second_fake.lesson_dependency_override = custody_fact.fact_id
    result = second_surfaces.run_resident_developmental_cognition(tick_id=second_tick)
    lesson_record_id = result["written_record_id"]
    assert result["status"] == "completed" and lesson_record_id
    history_conditioned_request = next(request for request in second_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    assert "Treat the stored protective posture as unknown" in history_conditioned_request.prompt
    assert "do not turn it into a protective procedure, policy, or authority" in (
        history_conditioned_request.prompt)
    lesson_record = second.writeback.store.get(lesson_record_id)
    provenance = lesson_record.candidate["transformation_provenance"]
    lesson = provenance["lesson_candidate"]
    assert lesson["statement"] == second_fake.lesson_statement
    assert lesson["scope"] == second_fake.lesson_scope
    assert lesson["uncertainty"] == "medium"
    assert lesson["evidence_dependencies"] == [custody_fact.fact_id]
    assert lesson["possible_contradiction_ids"] == []
    assert provenance["candidate_posture"] == (
        "untrusted_candidate_not_truth_policy_authority_or_adopted_procedure")
    assert provenance["current_truth"] is False
    assert provenance["authority"] is False
    assert provenance["policy"] is False
    assert provenance["canonical_explicit_user_retention"] is False
    assert lesson_record.candidate["epistemic_status"] == (
        "untrusted_history_conditioned_cognition_candidate")

    # A fresh owner recovers the admitted record and makes it available to a
    # third-tick cognition request, still as historical context only.
    third_fake = FakeInvoker()
    third_fake.no_cognition_lesson = True
    third = owner(tmp_path / "cognition", invoker=third_fake,
        allowed_source_kinds=("quarantine",))[0]
    third_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=third,  # type: ignore[arg-type]
    )
    third_tick = "2026-10-11T00:00:02+00:00"
    third_surfaces.build_world_state_board(tick_id=third_tick)
    third_result = third_surfaces.run_resident_developmental_cognition(tick_id=third_tick)
    retrieval = next(request for request in third_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    assert lesson_record_id in retrieval.upstream_evidence["record_ids"]
    retrieval_context = json.loads(retrieval.prompt)
    assert second_fake.lesson_statement in json.dumps(retrieval_context, sort_keys=True)
    assert third_result["status"] == "completed"


def test_configured_snapshot_verifier_failure_reaches_scoped_cognition(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import hashlib
    from sentientos.attestation import canonical_json_bytes
    from sentientos.attestation_snapshot import (
        AttestationSnapshot, SIGNATURE_INDEX_PATH, emit_snapshot, maybe_sign_snapshot,
    )

    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY", "1")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_HMAC_SECRET", "fixture-only-secret")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_ENFORCE", "1")
    snapshot_payload = AttestationSnapshot(
        schema_version=1, ts="2099-01-01T00:00:00Z", policy_hash="fixture-policy",
        integrity_status_hash="fixture-integrity", latest_rollup_sig_hash=None,
        latest_strategic_sig_hash=None, latest_goal_graph_hash=None,
        latest_catalog_checkpoint_hash=None, doctrine_bundle_sha256=None,
        witness_summary={},
    )
    rel = emit_snapshot(tmp_path, snapshot_payload)
    maybe_sign_snapshot(tmp_path, snapshot_rel_path=rel,
        snapshot_payload=snapshot_payload.to_dict())
    positive_record = _attestation_snapshot_verification_world_state_record(
        tmp_path, observed_at="2026-10-11T00:00:00+00:00")
    assert positive_record is not None
    assert positive_record["payload"]["verification_result"] == "ok"
    assert positive_record["payload"]["verification_ok"] is True
    assert positive_record["payload"]["attack_established"] is False
    index = tmp_path / SIGNATURE_INDEX_PATH
    row = json.loads(index.read_text(encoding="utf-8").splitlines()[0])
    row["signature"] = "deliberately-invalid-test-signature"
    failed_record_digest = hashlib.sha256(canonical_json_bytes(row)).hexdigest()
    index.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")

    first_owner, _first_fake = owner(
        tmp_path / "cognition", allowed_source_kinds=("audit_trust",))
    first_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=first_owner,  # type: ignore[arg-type]
    )
    first_tick = "2026-10-11T00:00:00+00:00"
    first_surfaces.build_world_state_board(tick_id=first_tick)
    first_snapshot = first_surfaces.current_world_state_snapshot
    assert first_snapshot is not None
    failure_fact = next(fact for fact in first_snapshot.facts
        if fact.subject.subject_kind == "attestation_snapshot_verification_observation")
    assert failure_fact.source.kind == "audit_trust"
    assert failure_fact.disposition == "degraded"
    assert failure_fact.payload["verification_result"] == "fail"
    assert failure_fact.payload["verification_reason"] == "signature_invalid"
    assert failure_fact.payload["failed_signature_record_sha256"] == failed_record_digest
    assert failure_fact.payload["attack_established"] is False
    assert failure_fact.payload["compromise_established"] is False
    first = first_surfaces.run_resident_developmental_cognition(tick_id=first_tick)
    assert first["written_record_id"]
    interpretation = next(request for request in _first_fake.requests
        if request.purpose == "resident_developmental_interpretation")
    assert "not attack, hostile activity, intent, compromise, or cause" in interpretation.prompt

    second_fake = FakeInvoker()
    second_fake.lesson_statement = (
        "A failed signature check establishes a verifier result, while its cause remains unknown.")
    second_fake.lesson_scope = "attestation snapshot verification result interpretation"
    second_owner, _ = owner(tmp_path / "cognition", invoker=second_fake,
        allowed_source_kinds=("audit_trust",))
    second_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=second_owner,  # type: ignore[arg-type]
    )
    second_tick = "2026-10-11T00:00:01+00:00"
    second_surfaces.build_world_state_board(tick_id=second_tick)
    second_snapshot = second_surfaces.current_world_state_snapshot
    assert second_snapshot is not None
    current_failure = next(fact for fact in second_snapshot.facts
        if fact.subject.subject_kind == "attestation_snapshot_verification_observation")
    second_fake.lesson_dependency_override = current_failure.fact_id
    second = second_surfaces.run_resident_developmental_cognition(tick_id=second_tick)
    history_request = next(request for request in second_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    assert "cause remains unknown" in history_request.prompt
    assert "Do not infer attack, hostile activity, intent, compromise, or a defensive effect" in (
        history_request.prompt)
    history_context = json.loads(history_request.prompt)
    historical_packet = next(packet for packet in history_context["developmental_history"]
        if packet["record_id"] == first["written_record_id"])
    source_context = next(item for item in historical_packet["source_evidence_context"]
        if item["fact_id"] == failure_fact.fact_id)
    assert source_context["context"]["failed_signature_record_sha256"] == failed_record_digest
    assert source_context["context"]["event_meaning"] == failure_fact.payload["event_meaning"]
    assert source_context["observed_at"] == failure_fact.observed_at
    assert source_context["historical_only"] is True
    assert source_context["current_truth"] is False and source_context["authority"] is False
    lesson_record = second_owner.writeback.store.get(second["written_record_id"])
    assert lesson_record.candidate["epistemic_status"] == (
        "untrusted_history_conditioned_cognition_candidate")
    assert lesson_record.candidate["transformation_provenance"]["candidate_posture"] == (
        "untrusted_candidate_not_truth_policy_authority_or_adopted_procedure")
    assert lesson_record.candidate["transformation_provenance"]["lesson_candidate"][
        "evidence_dependencies"] == [current_failure.fact_id]


def test_integrity_controller_gate_results_reach_configured_cognition_as_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime-state"))
    reset_runtime_governor()
    monkeypatch.setenv("SENTIENTOS_INTEGRITY_CONTROLLER_OBSERVATION", "1")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY", "1")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_HMAC_SECRET", "fixture-only-secret")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_ENFORCE", "1")
    import hashlib
    from sentientos.attestation import canonical_json_bytes
    from sentientos.attestation_snapshot import (
        AttestationSnapshot, SIGNATURE_INDEX_PATH, emit_snapshot, maybe_sign_snapshot,
    )
    attestation = AttestationSnapshot(
        schema_version=1, ts="2099-01-01T00:00:00Z", policy_hash="fixture-policy",
        integrity_status_hash="fixture-integrity", latest_rollup_sig_hash=None,
        latest_strategic_sig_hash=None, latest_goal_graph_hash=None,
        latest_catalog_checkpoint_hash=None, doctrine_bundle_sha256=None,
        witness_summary={},
    )
    rel = emit_snapshot(tmp_path, attestation)
    maybe_sign_snapshot(tmp_path, snapshot_rel_path=rel, snapshot_payload=attestation.to_dict())
    index = tmp_path / SIGNATURE_INDEX_PATH
    row = json.loads(index.read_text(encoding="utf-8").splitlines()[0])
    row["signature"] = "invalid-controller-context-fixture"
    expected_failed_row_digest = hashlib.sha256(canonical_json_bytes(row)).hexdigest()
    index.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    cognition, fake = owner(
        tmp_path / "cognition", allowed_source_kinds=("audit_trust",))
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=cognition,  # type: ignore[arg-type]
    )
    tick = datetime.now(timezone.utc).isoformat()
    surfaces.build_world_state_board(tick_id=tick)
    current = surfaces.current_world_state_snapshot
    assert current is not None
    fact = next(item for item in current.facts
        if item.subject.subject_kind == "integrity_controller_observation")
    assert fact.source.kind == "audit_trust"
    assert fact.payload["observation_schema"] == "sentientos.integrity_controller_observation:v2"
    assert fact.payload["gate_results"]
    gate = next(item for item in fact.payload["gate_results"]
        if item["name"] == "attestation_snapshot_signatures")
    assert gate["status"] == "fail"
    assert gate["failed_record_sha256"] == expected_failed_row_digest
    result = surfaces.run_resident_developmental_cognition(tick_id=tick)
    assert result["written_record_id"]
    interpretation = next(request for request in fake.requests
        if request.purpose == "resident_developmental_interpretation")
    interpretation_input = json.loads(interpretation.prompt)
    controller_fact = next(item for item in interpretation_input["selection"]["facts"]
        if item.get("subject", {}).get("subject_kind") == "integrity_controller_observation")
    assert controller_fact["payload"]["gate_results"]
    assert expected_failed_row_digest in json.dumps(controller_fact["payload"]["gate_results"])
    instruction = interpretation_input["instruction"]
    assert "does not establish attack, cause, hostile intent, compromise, or a successful defense" in instruction
    assert "Skipped gates are gaps in coverage" in instruction

    later_tick = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    later_owner, later_fake = owner(tmp_path / "cognition",
        allowed_source_kinds=("audit_trust",))
    later_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=later_owner,  # type: ignore[arg-type]
    )
    later_surfaces.build_world_state_board(tick_id=later_tick)
    later_result = later_surfaces.run_resident_developmental_cognition(tick_id=later_tick)
    assert later_result["written_record_id"]
    retrieval = next(request for request in later_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    prior_packet = next(packet for packet in json.loads(retrieval.prompt)["developmental_history"]
        if packet["record_id"] == result["written_record_id"])
    source_context = next(item for item in prior_packet["source_evidence_context"]
        if item["subject_kind"] == "integrity_controller_observation")
    retained_gate = next(item for item in source_context["context"]["gates"]
        if item["name"] == "attestation_snapshot_signatures")
    assert retained_gate["failed_record_sha256"] == expected_failed_row_digest
    assert retained_gate["checked_at"] == gate["checked_at"]
    assert source_context["current_truth"] is False and source_context["authority"] is False
    assert source_context["attack_established"] is False
    assert source_context["hostile_activity_established"] is False
    reset_runtime_governor()


def test_unsigned_incident_narrative_is_not_attack_evidence_in_resident_cognition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime-state"))
    reset_runtime_governor()
    monkeypatch.setenv("SENTIENTOS_INTEGRITY_CONTROLLER_OBSERVATION", "1")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY", "0")
    tick = datetime.now(timezone.utc).isoformat()
    feed = tmp_path / "pulse" / "integrity_incidents.jsonl"
    feed.parent.mkdir(parents=True)
    feed.write_text(json.dumps({
        "schema_version": 1,
        "incident_id": "untrusted-narrative-only",
        "created_at": tick,
        "severity": "critical",
        "enforcement_mode": "enforce",
        "quarantine_activated": True,
        "triggers": ["attack confirmed: attacker-authored text"],
    }) + "\n", encoding="utf-8")

    cognition, fake = owner(
        tmp_path / "cognition", allowed_source_kinds=("audit_trust",))
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=cognition,  # type: ignore[arg-type]
    )
    surfaces.build_world_state_board(tick_id=tick)
    snapshot = surfaces.current_world_state_snapshot
    assert snapshot is not None
    fact = next(item for item in snapshot.facts
        if item.subject.subject_kind == "integrity_controller_observation")
    assert fact.payload["source_owner"] == "sentientos.integrity_controller.evaluate_integrity"
    assert fact.payload["attack_established"] is False
    assert fact.payload["hostile_activity_established"] is False
    assert fact.payload["independent_signature"] is False
    assert "pressure_summary" not in fact.payload
    assert "attack confirmed" not in json.dumps(fact.payload)

    result = surfaces.run_resident_developmental_cognition(tick_id=tick)
    assert result["written_record_id"]
    interpretation = next(request for request in fake.requests
        if request.purpose == "resident_developmental_interpretation")
    assert "attack confirmed" not in interpretation.prompt
    assert "does not establish attack, cause, hostile intent, compromise, or a successful defense" in (
        interpretation.prompt)

    later_tick = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    later_owner, later_fake = owner(tmp_path / "cognition",
        allowed_source_kinds=("audit_trust",))
    later_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=later_owner,  # type: ignore[arg-type]
    )
    later_surfaces.build_world_state_board(tick_id=later_tick)
    later_result = later_surfaces.run_resident_developmental_cognition(tick_id=later_tick)
    assert later_result["written_record_id"]
    retrieval = next(request for request in later_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    retrieval_context = json.loads(retrieval.prompt)
    prior_packet = next(packet for packet in retrieval_context["developmental_history"]
        if packet["record_id"] == result["written_record_id"])
    assert "attack confirmed" not in json.dumps(prior_packet)
    assert prior_packet["source_evidence_context"]
    assert all(item["context"]["event_meaning"] != "attack confirmed: attacker-authored text"
        for item in prior_packet["source_evidence_context"])
    assert all(item["authority"] is False and item["current_truth"] is False
        and item["attack_established"] is False
        for item in prior_packet["source_evidence_context"])
    reset_runtime_governor()


def test_later_valid_custody_evidence_can_narrow_an_earlier_failure_interpretation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime-state"))
    reset_runtime_governor()
    monkeypatch.setenv("SENTIENTOS_INTEGRITY_CONTROLLER_OBSERVATION", "1")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY", "0")
    quarantine_path = tmp_path / "glow" / "forge" / "quarantine.json"
    quarantine_path.parent.mkdir(parents=True)
    quarantine_path.write_bytes(b'{"schema_version":1')

    first_fake = FakeInvoker()
    first_owner, _ = owner(
        tmp_path / "cognition", invoker=first_fake,
        allowed_source_kinds=("audit_trust", "quarantine"), max_selected_facts=2)
    first_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=first_owner,  # type: ignore[arg-type]
    )
    first_tick = "2026-10-12T00:02:00+00:00"
    first_surfaces.build_world_state_board(tick_id=first_tick)
    first_result = first_surfaces.run_resident_developmental_cognition(tick_id=first_tick)
    assert first_result["written_record_id"]

    lesson_fake = FakeInvoker()
    lesson_fake.lesson_statement = (
        "A custody read failure leaves the stored protective posture unknown.")
    lesson_fake.lesson_scope = "quarantine custody read interpretation"
    lesson_owner, _ = owner(
        tmp_path / "cognition", invoker=lesson_fake,
        allowed_source_kinds=("audit_trust", "quarantine"), max_selected_facts=2)
    lesson_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=lesson_owner,  # type: ignore[arg-type]
    )
    lesson_tick = "2026-10-12T00:02:01+00:00"
    lesson_surfaces.build_world_state_board(tick_id=lesson_tick)
    lesson_snapshot = lesson_surfaces.current_world_state_snapshot
    assert lesson_snapshot is not None
    failure_fact = next(fact for fact in lesson_snapshot.facts
        if fact.subject.subject_kind == "integrity_controller_observation")
    lesson_fake.lesson_dependency_override = failure_fact.fact_id
    lesson_result = lesson_surfaces.run_resident_developmental_cognition(tick_id=lesson_tick)
    retrieval = next(request for request in lesson_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    retrieval_context = json.loads(retrieval.prompt)
    first_history = next(packet for packet in retrieval_context["developmental_history"]
        if packet["record_id"] == first_result["written_record_id"])
    quarantine_context = next(item for item in first_history["source_evidence_context"]
        if item["subject_kind"] == "quarantine_custody_observation")
    assert quarantine_context["context"]["custody_result"] == "invalid"
    assert quarantine_context["context"]["quarantine_active"] is None
    assert "could not be verified" in quarantine_context["context"]["event_meaning"]
    assert quarantine_context["event_time_posture"] == (
        "daemon_tick_point_observation_of_owner_read")
    assert quarantine_context["current_truth"] is False
    assert quarantine_context["authority"] is False
    prior_record_id = lesson_result["written_record_id"]
    assert prior_record_id
    prior = lesson_owner.writeback.store.get(prior_record_id)
    assert prior.candidate["transformation_provenance"]["lesson_candidate"][
        "statement"] == lesson_fake.lesson_statement

    # Model an external operator-preserved custody repair in this disposable
    # fixture. The real quarantine writer correctly refuses to overwrite the
    # malformed record; retain its exact bytes before publishing a valid state.
    preserved_corruption = tmp_path / "quarantine-invalid-evidence.bin"
    corrupt_bytes = quarantine_path.read_bytes()
    quarantine_path.replace(preserved_corruption)
    save_state(tmp_path, QuarantineState(
        active=False, allow_publish=True, allow_automerge=True,
        freeze_forge=False, allow_federation_sync=True,
    ))
    assert preserved_corruption.read_bytes() == corrupt_bytes
    revision_fake = FakeInvoker()
    revision_fake.lesson_statement = (
        "A later valid custody read narrows the present posture to inactive; the earlier read's cause remains unknown.")
    revision_fake.lesson_scope = "current valid quarantine custody observation"
    revision_owner, _ = owner(
        tmp_path / "cognition", invoker=revision_fake,
        allowed_source_kinds=("audit_trust", "quarantine"), max_selected_facts=2)
    revision_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=revision_owner,  # type: ignore[arg-type]
    )
    revision_tick = "2026-10-12T00:02:02+00:00"
    revision_surfaces.build_world_state_board(tick_id=revision_tick)
    current_snapshot = revision_surfaces.current_world_state_snapshot
    assert current_snapshot is not None
    current_fact = next(fact for fact in current_snapshot.facts
        if fact.subject.subject_kind == "integrity_controller_observation")
    current_gate = next(gate for gate in current_fact.payload["gate_results"]
        if gate["name"] == "quarantine_custody")
    assert current_gate["status"] == "ok"
    revision_fake.lesson_dependency_override = current_fact.fact_id

    result = revision_surfaces.run_resident_developmental_cognition(tick_id=revision_tick)
    assert result["written_record_id"]
    retrieval = next(request for request in revision_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    assert prior_record_id in retrieval.upstream_evidence["record_ids"]
    assert current_fact.fact_id in retrieval.upstream_evidence["current_fact_ids"]
    assert lesson_fake.lesson_statement in retrieval.prompt
    candidate = revision_owner.writeback.store.get(result["written_record_id"])
    assert candidate.candidate["epistemic_status"] == (
        "untrusted_history_conditioned_cognition_candidate")
    assert candidate.candidate["transformation_provenance"]["lesson_candidate"][
        "evidence_dependencies"] == [current_fact.fact_id]
    assert candidate.candidate["transformation_provenance"]["lesson_candidate"][
        "statement"] == revision_fake.lesson_statement
    assert candidate.candidate["transformation_provenance"]["authority"] is False
    reset_runtime_governor()


def test_integrity_controller_gate_context_becomes_scoped_later_tick_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime-state"))
    reset_runtime_governor()


    monkeypatch.setenv("SENTIENTOS_INTEGRITY_CONTROLLER_OBSERVATION", "1")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY", "0")
    quarantine_path = tmp_path / "glow/forge/quarantine.json"
    quarantine_path.parent.mkdir(parents=True)
    quarantine_path.write_bytes(b'{"schema_version":1')

    first_owner, first_fake = owner(
        tmp_path / "cognition", allowed_source_kinds=("audit_trust",))
    first_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=first_owner,  # type: ignore[arg-type]
    )
    first_tick = "2026-10-12T00:01:00+00:00"
    first_surfaces.build_world_state_board(tick_id=first_tick)
    first_snapshot = first_surfaces.current_world_state_snapshot
    assert first_snapshot is not None
    first_fact = next(item for item in first_snapshot.facts
        if item.subject.subject_kind == "integrity_controller_observation")
    first_custody_gate = next(gate for gate in first_fact.payload["gate_results"]
        if gate["name"] == "quarantine_custody")
    assert first_custody_gate["status"] == "fail"
    assert first_fact.payload["attack_established"] is False
    first_result = first_surfaces.run_resident_developmental_cognition(tick_id=first_tick)
    assert first_result["written_record_id"]
    first_interpretation = next(request for request in first_fake.requests
        if request.purpose == "resident_developmental_interpretation")
    assert "a warning or failure does not establish attack, cause, hostile intent, compromise" in (
        first_interpretation.prompt)

    second_fake = FakeInvoker()
    second_fake.lesson_statement = (
        "A quarantine-custody gate failure is a bounded verifier result; its cause remains unknown.")
    second_fake.lesson_scope = "integrity controller quarantine-custody verifier result"
    second_owner, _ = owner(tmp_path / "cognition", invoker=second_fake,
        allowed_source_kinds=("audit_trust",))
    second_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=second_owner,  # type: ignore[arg-type]
    )
    second_tick = "2026-10-12T00:01:01+00:00"
    second_surfaces.build_world_state_board(tick_id=second_tick)
    second_snapshot = second_surfaces.current_world_state_snapshot
    assert second_snapshot is not None
    current_fact = next(item for item in second_snapshot.facts
        if item.subject.subject_kind == "integrity_controller_observation")
    second_fake.lesson_dependency_override = current_fact.fact_id
    second_result = second_surfaces.run_resident_developmental_cognition(tick_id=second_tick)
    history_request = next(request for request in second_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    assert "does not establish attack, cause, hostile intent, compromise, or a successful defense" in (
        history_request.prompt)
    assert "Skipped gates are gaps in coverage" in history_request.prompt
    lesson = second_owner.writeback.store.get(second_result["written_record_id"])
    assert lesson.candidate["epistemic_status"] == (
        "untrusted_history_conditioned_cognition_candidate")
    assert lesson.candidate["transformation_provenance"]["candidate_posture"] == (
        "untrusted_candidate_not_truth_policy_authority_or_adopted_procedure")
    assert lesson.candidate["transformation_provenance"]["lesson_candidate"][
        "evidence_dependencies"] == [current_fact.fact_id]
    assert lesson.candidate["transformation_provenance"]["authority"] is False
    assert lesson.candidate["transformation_provenance"]["policy"] is False
    reset_runtime_governor()


def test_quarantine_incident_restart_custody_reaches_later_cognition_as_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime-state"))
    reset_runtime_governor()
    event_at = "2026-10-11T23:59:00+00:00"
    incident = build_incident(
        triggers=["verified_integrity_mismatch"], enforcement_mode="enforce",
        severity="warning", created_at=event_at,
        context={"attacker-authored-fixture": "ATTACKER_NARRATIVE_FIXTURE"},
        suggested_actions=["UNTRUSTED_ACTION_FIXTURE"],
    )
    write_incident(tmp_path, incident, quarantine_activated=True)
    save_state(tmp_path, QuarantineState(
        active=True, activated_at=event_at, activated_by="auto",
        last_incident_id=incident.incident_id, freeze_forge=True,
        allow_automerge=False, allow_publish=False,
        allow_federation_sync=False, notes=[],
    ))

    first_owner, first_fake = owner(
        tmp_path / "cognition", allowed_source_kinds=("quarantine",),
        max_selected_facts=2)
    first_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=first_owner,  # type: ignore[arg-type]
    )
    first_tick = "2026-10-12T00:00:00+00:00"
    first_surfaces.build_world_state_board(tick_id=first_tick)
    first_snapshot = first_surfaces.current_world_state_snapshot
    assert first_snapshot is not None
    fact = next(item for item in first_snapshot.facts
        if item.subject.subject_kind == "quarantine_incident_custody_observation")
    assert fact.payload["reconciliation_status"] == "complete_local_custody"
    assert fact.payload["incident_activated_at"] == event_at
    assert fact.observed_at == first_tick
    assert fact.payload["feed_is_authenticated"] is False
    first_result = first_surfaces.run_resident_developmental_cognition(tick_id=first_tick)
    first_record = first_owner.writeback.store.get(first_result["written_record_id"])
    assert fact.fact_id in first_record.candidate["selected_fact_ids"]
    retained_context = first_record.candidate["selected_facts"]
    retained_incident = next(item for item in retained_context
        if item["fact_id"] == fact.fact_id)
    assert retained_incident["payload"]["reconciliation_status"] == "complete_local_custody"
    assert "ATTACKER_NARRATIVE_FIXTURE" not in first_fake.requests[0].prompt
    # A later source read may disagree or become incomplete. It cannot rewrite
    # the exact earlier observation retained with the developmental record.
    (tmp_path / "pulse/integrity_incidents.jsonl").write_text(
        '{"schema_version":1,"incident_id":"substituted"}\n', encoding="utf-8")
    current_request = next(request for request in first_fake.requests
        if request.purpose == "resident_developmental_interpretation")
    assert "local artifact and feed custody" in current_request.prompt
    assert incident.incident_id in current_request.prompt
    assert event_at in current_request.prompt
    assert "ATTACKER_NARRATIVE_FIXTURE" not in current_request.prompt
    assert "UNTRUSTED_ACTION_FIXTURE" not in current_request.prompt

    second_fake = FakeInvoker()
    second_owner, _ = owner(tmp_path / "cognition", invoker=second_fake,
        allowed_source_kinds=("quarantine",), max_selected_facts=2)
    second_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=second_owner,  # type: ignore[arg-type]
    )
    second_tick = "2026-10-12T00:00:01+00:00"
    second_surfaces.build_world_state_board(tick_id=second_tick)
    second_snapshot = second_surfaces.current_world_state_snapshot
    assert second_snapshot is not None
    current_incident = next(item for item in second_snapshot.facts
        if item.subject.subject_kind == "quarantine_incident_custody_observation")
    assert current_incident.payload["reconciliation_status"] == "conflict"
    second_result = second_surfaces.run_resident_developmental_cognition(tick_id=second_tick)
    history_request = next(request for request in second_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    assert incident.incident_id in history_request.prompt
    assert event_at in history_request.prompt
    assert "feed is unauthenticated" in history_request.prompt
    assert "does not establish attack" in history_request.prompt
    assert "ATTACKER_NARRATIVE_FIXTURE" not in history_request.prompt
    assert "UNTRUSTED_ACTION_FIXTURE" not in history_request.prompt
    history_packet = json.loads(history_request.prompt)
    prior_packets = history_packet["developmental_history"]
    source_contexts = [context for packet in prior_packets
        for context in packet.get("source_evidence_context", [])]
    historical_incident = next(context for context in source_contexts
        if context.get("fact_id") == fact.fact_id)
    assert historical_incident["context"]["reconciliation_status"] == "complete_local_custody"
    assert historical_incident["context"]["incident_activated_at"] == event_at
    assert history_request.upstream_evidence["record_ids"]
    assert first_result["written_record_id"] in history_request.upstream_evidence["record_ids"]
    assert second_result["written_record_id"]
    assert second_owner.writeback.store.get(second_result["written_record_id"])
    reset_runtime_governor()

@pytest.mark.parametrize(("active", "expected"), [(False, False), (True, True)])
def test_valid_quarantine_state_projection_preserves_actual_posture(
    tmp_path: Path, active: bool, expected: bool,
) -> None:
    save_state(tmp_path, QuarantineState(active=active, allow_publish=not active,
        allow_automerge=not active, freeze_forge=active, allow_federation_sync=not active))
    surfaces = RuntimeMaintenanceSurfaces(tmp_path, runtime_state_root=tmp_path / "runtime")
    surfaces.build_world_state_board(tick_id="2026-10-11T00:00:00+00:00")
    snapshot_value = surfaces.current_world_state_snapshot
    assert snapshot_value is not None
    facts = [fact for fact in snapshot_value.facts if fact.source.kind == "quarantine"]
    custody_fact = next(fact for fact in facts
        if fact.subject.subject_kind == "quarantine_custody_observation")
    assert custody_fact.disposition == "recorded"
    assert custody_fact.payload["custody_result"] == "valid_v1"
    assert custody_fact.payload["quarantine_active"] is expected
    assert custody_fact.payload["attack_established"] is False
    incident_facts = [fact for fact in facts
        if fact.subject.subject_kind == "quarantine_incident_custody_observation"]
    assert len(incident_facts) == (1 if active else 0)
    if active:
        assert incident_facts[0].payload["reconciliation_status"] == "incomplete_identity"


def epistemic_projection(root: Path):
    epistemic = PersistentEpistemicStateOwner(root, allowed_namespaces=["embodiment"])
    proposition = make_proposition(namespace="embodiment", subject="body:g1", predicate="healthy",
        object_value=True, polarity="positive", qualifiers={}, temporal_scope={"kind":"prior"},
        context_scope={}, proposition_class="descriptive")
    epistemic.register_proposition(proposition)
    state, _ = epistemic.commit_update(proposition_id=proposition.proposition_id,
        expected_predecessor_digest=None, stance="unknown", reason="initialization",
        active_binding_ids=[], correlation_id="prior", tick=1,
        recorded_at="2026-01-01T00:00:00Z")
    projection = epistemic.cognitive_projection(max_states=1)
    assert projection is not None
    return projection, proposition, state


def test_meaning_bearing_epistemic_packets_reach_actual_inference_request(tmp_path: Path):
    epistemic = PersistentEpistemicStateOwner(tmp_path / "epistemic",
        allowed_namespaces=["embodiment"])
    propositions = [make_proposition(namespace="embodiment", subject="sensor:g9",
        predicate="reports_temperature", object_value={"celsius": 20}, polarity="positive",
        qualifiers={"sensor": "exact-a"}, temporal_scope={"window": window},
        context_scope={"room": room}, proposition_class="descriptive",
        statement="canonical temperature proposition")
        for window, room in (("morning", "lab-a"), ("evening", "lab-b"))]
    for index, proposition_value in enumerate(propositions):
        epistemic.register_proposition(proposition_value)
        support = make_evidence_binding(proposition_id=proposition_value.proposition_id,
            source_artifact_id=f"support-{index}", source_digest="sha256:" + str(index + 1) * 64,
            source_schema="sentientos.test_sensor:v1", source_class="fixture",
            observation_time="2026-01-01T00:00:00Z", evidence_relation="supports",
            dependency_kind="independently_sourced_observation", dependency_group=f"group-{index}",
            upstream_binding_ids=(), freshness="current", reliability_posture="verified")
        contradiction = make_evidence_binding(proposition_id=proposition_value.proposition_id,
            source_artifact_id=f"contradiction-{index}", source_digest="sha256:" + str(index + 3) * 64,
            source_schema="sentientos.test_sensor:v1", source_class="fixture",
            observation_time="2025-01-01T00:00:00Z", evidence_relation="contradicts",
            dependency_kind="unknown_dependency", dependency_group=None,
            upstream_binding_ids=(), freshness="stale", reliability_posture="unverified")
        epistemic.bind_evidence(support)
        epistemic.bind_evidence(contradiction)
        state, _ = epistemic.commit_update(proposition_id=proposition_value.proposition_id,
            expected_predecessor_digest=None, stance="contested", reason="initialization",
            active_binding_ids=[support.binding_id, contradiction.binding_id],
            added_binding_ids=[support.binding_id, contradiction.binding_id],
            correlation_id=f"contested-{index}", tick=1,
            recorded_at="2026-01-01T00:00:00Z", confidence={"uncertainty": "high"})
        if index == 1:
            current_contradiction = make_evidence_binding(
                proposition_id=proposition_value.proposition_id,
                source_artifact_id="contradiction-current",
                source_digest="sha256:" + "5" * 64,
                source_schema="sentientos.test_sensor:v1", source_class="fixture",
                observation_time="2026-01-02T00:00:00Z", evidence_relation="contradicts",
                dependency_kind="unknown_dependency", dependency_group=None,
                upstream_binding_ids=(), freshness="current", reliability_posture="unverified")
            epistemic.bind_evidence(current_contradiction)
            changed_state, _ = epistemic.commit_update(proposition_id=proposition_value.proposition_id,
                expected_predecessor_digest=state.state_digest, stance="contested",
                reason="evidence_withdrawal", active_binding_ids=[support.binding_id,
                    current_contradiction.binding_id], added_binding_ids=[current_contradiction.binding_id],
                removed_binding_ids=[contradiction.binding_id], correlation_id="withdraw-stale",
                tick=2, recorded_at="2026-01-02T00:00:00Z")
            epistemic.commit_update(proposition_id=proposition_value.proposition_id,
                expected_predecessor_digest=changed_state.state_digest, stance="contested",
                reason="update_rule_correction", active_binding_ids=[support.binding_id,
                    current_contradiction.binding_id], update_rule_id="fixture-rule:v2",
                correlation_id="after-withdrawal", tick=3,
                recorded_at="2026-01-03T00:00:00Z")
    projection = epistemic.cognitive_projection(max_states=2, current_tick=4)
    assert isinstance(projection, MeaningBearingEpistemicCognitiveProjection)
    composition, fake = owner(tmp_path / "cognition")
    result = composition.run_tick(snapshot=snapshot(), tick_id="tick-2",
        prior_epistemic_state=projection)
    request = next(item for item in fake.requests
        if item.purpose == "resident_developmental_retrieval_cognition")
    consumed = json.loads(request.prompt)["prior_epistemic_state"]
    packets = consumed["semantic_packets"]
    # The full two-packet projection exceeds the fixed input budget. Selection
    # delivers the complete packet with recent withdrawal/contradiction first
    # and binds the other packet as omitted rather than silently truncating it.
    assert len(packets) == 1
    assert packets[0]["state"]["stance"] == "contested"
    assert packets[0]["proposition"]["temporal_scope"]["window"] == "evening"
    assert packets[0]["proposition"]["context_scope"]["room"] == "lab-b"
    assert request.upstream_evidence["epistemic_owner_packet_count"] == 2
    assert len(request.upstream_evidence["epistemic_omitted_packets"]) == 1
    assert request.upstream_evidence["epistemic_omitted_packets"][0]["packet_id"] != packets[0]["packet_id"]
    withdrawn = next(packet for packet in packets if packet["removed_evidence_history"])
    assert withdrawn["removed_evidence_history"][0]["freshness"] == "stale"
    assert withdrawn["evidence_posture"]["dependency_unresolved"] is True
    assert withdrawn["contradicting_evidence"]
    upstream = request.upstream_evidence
    assert upstream["epistemic_consumed_packet_ids"] == [p["packet_id"] for p in packets]
    assert upstream["epistemic_consumed_packet_digests"] == [p["packet_digest"] for p in packets]
    assert upstream["epistemic_prompt_digest"] == "sha256:" + request.prompt_digest
    observation_id = result.cognition_observation_ids[0]
    recovered, _ = owner(tmp_path / "cognition")
    observation = recovered.verified_cognition_observation(observation_id)
    assert observation["epistemic_consumed_packet_ids"] == upstream["epistemic_consumed_packet_ids"]
    assert observation["epistemic_consumed_content_digest"] == upstream["epistemic_consumed_content_digest"]


def test_legacy_identifier_projection_is_valid_but_not_delivered_as_meaning(tmp_path: Path):
    semantic, proposition_value, state = epistemic_projection(tmp_path / "epistemic")
    legacy = make_cognitive_projection([state], source_tick=1, current_tick=2)
    composition, fake = owner(tmp_path / "cognition")
    composition.run_tick(snapshot=snapshot(), tick_id="tick-2", prior_epistemic_state=legacy)
    request = next(item for item in fake.requests
        if item.purpose == "resident_developmental_retrieval_cognition")
    prior = json.loads(request.prompt)["prior_epistemic_state"]
    assert prior["semantic_status"] == "canonical_definition_unavailable"
    assert prior["semantic_packets"] == []
    assert proposition_value.predicate not in request.prompt
    assert request.upstream_evidence["epistemic_state_ids"] == [state.state_id]


def test_semantic_packets_are_whole_and_omissions_are_bound_under_input_budget(tmp_path: Path):
    epistemic = PersistentEpistemicStateOwner(tmp_path, allowed_namespaces=["embodiment"])
    for index in range(2):
        proposition_value = make_proposition(namespace="embodiment", subject=f"sensor:{index}",
            predicate="long_scoped_measurement", object_value={"value": index}, polarity="positive",
            qualifiers={"canonical_qualifier": "q" * 4500},
            temporal_scope={"window": f"exact-window-{index}"},
            context_scope={"facility": f"facility-{index}"}, proposition_class="descriptive",
            statement="complete statement " + ("s" * 4500))
        epistemic.register_proposition(proposition_value)
        epistemic.commit_update(proposition_id=proposition_value.proposition_id,
            expected_predecessor_digest=None, stance="unknown", reason="initialization",
            active_binding_ids=[], correlation_id=f"long-{index}", tick=index + 1,
            recorded_at="2026-01-01T00:00:00Z")
    projection = epistemic.cognitive_projection(max_states=2, current_tick=3)
    context, metadata, prompt = _bind_epistemic_context(
        context={"instruction": "prior positions are not truth"}, projection=projection)
    assert len(prompt) <= 16_000
    prior = context["prior_epistemic_state"]
    assert len(prior["semantic_packets"]) == 1
    assert len(metadata["epistemic_omitted_packets"]) == 1
    delivered = prior["semantic_packets"][0]
    assert delivered["proposition"]["qualifiers"]["canonical_qualifier"] == "q" * 4500
    assert delivered["proposition"]["context_scope"]["facility"] in {"facility-0", "facility-1"}
    assert prior["omitted_packets_digest"] == metadata["epistemic_omitted_packets_digest"]


def self_model_projection(root: Path):
    from sentientos.longitudinal_self_model import LongitudinalSelfModelOwner
    from tests.test_longitudinal_self_model import record, snapshot as self_model_snapshot

    self_model = LongitudinalSelfModelOwner(root)
    self_model.reconcile(self_model_snapshot(record()), tick_id="tick-1")
    projection = self_model.cognitive_projection(before_tick="tick-2", max_claims=2,
        allowed_predicates=("software_generation", "cognitive_model_identity"))
    assert projection is not None
    return projection


def test_epistemic_only_prior_context_causes_real_owner_cognition(tmp_path: Path) -> None:
    projection, proposition, state = epistemic_projection(tmp_path / "epistemic")
    composition, fake = owner(tmp_path / "cognition")

    result = composition.run_tick(snapshot=snapshot(), tick_id="tick-2",
                                  prior_epistemic_state=projection)

    cognition = [request for request in fake.requests
                 if request.purpose == "resident_developmental_retrieval_cognition"]
    assert len(cognition) == 1
    assert result.cognition_observation_ids
    request = cognition[0]
    assert request.upstream_evidence["record_ids"] == []
    assert request.upstream_evidence["self_model_projection_present"] is False
    assert request.upstream_evidence["epistemic_projection_id"] == projection.projection_id
    assert request.upstream_evidence["epistemic_projection_digest"] == projection.projection_digest
    assert request.upstream_evidence["epistemic_proposition_ids"] == [proposition.proposition_id]
    assert request.upstream_evidence["epistemic_state_ids"] == [state.state_id]
    assert request.upstream_evidence["epistemic_state_digests"] == [state.state_digest]
    assert request.upstream_evidence["epistemic_generations"] == [state.generation]
    assert request.upstream_evidence["epistemic_evidence_set_digests"] == [state.evidence_set_digest]
    observation = json.loads((composition.observations_root /
                              f"{result.cognition_observation_ids[0]}.json").read_text())
    assert observation["epistemic_projection_present"] is True
    assert observation["epistemic_projection_id"] == projection.projection_id
    assert observation["epistemic_projection_digest"] == projection.projection_digest
    assert observation["epistemic_proposition_ids"] == [proposition.proposition_id]
    assert observation["epistemic_state_ids"] == [state.state_id]
    assert observation["epistemic_state_digests"] == [state.state_digest]
    assert observation["epistemic_generations"] == [state.generation]
    assert observation["epistemic_evidence_set_digests"] == [state.evidence_set_digest]
    assert observation["developmental_projection_present"] is False
    assert observation["self_model_projection_present"] is False
    assert observation["authority"] is False


def test_self_model_and_epistemic_context_run_one_ordinary_condition(tmp_path: Path) -> None:
    epistemic, _, _ = epistemic_projection(tmp_path / "epistemic")
    self_model = self_model_projection(tmp_path / "self-model")
    composition, fake = owner(tmp_path / "cognition", comparison=True)

    result = composition.run_tick(snapshot=snapshot(), tick_id="tick-2",
        prior_self_model=self_model, prior_epistemic_state=epistemic)

    cognition = [request for request in fake.requests
                 if request.purpose == "resident_developmental_retrieval_cognition"]
    assert len(cognition) == 1
    assert cognition[0].upstream_evidence["record_ids"] == []
    assert cognition[0].upstream_evidence["self_model_projection_id"] == self_model.projection_id
    assert cognition[0].upstream_evidence["epistemic_projection_id"] == epistemic.projection_id
    assert result.changed_cognition_measurement_id is None
    assert not list(composition.experiments.protocols.glob("*.json"))
    assert not list(composition.experiments.runs.glob("*.json"))


def test_all_four_substrates_reach_ordinary_cognition_when_comparison_disabled(tmp_path: Path) -> None:
    first, _ = owner(tmp_path / "cognition")
    written = first.run_tick(snapshot=snapshot(), tick_id="tick-1").written_record_id
    epistemic, _, _ = epistemic_projection(tmp_path / "epistemic")
    self_model = self_model_projection(tmp_path / "self-model")
    restarted, fake = owner(tmp_path / "cognition")

    result = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-2",
        prior_self_model=self_model, prior_epistemic_state=epistemic)

    cognition = [request for request in fake.requests
                 if request.purpose == "resident_developmental_retrieval_cognition"]
    assert len(cognition) == 1
    assert cognition[0].upstream_evidence["current_fact_ids"]
    assert cognition[0].upstream_evidence["record_ids"] == [written]
    assert cognition[0].upstream_evidence["self_model_projection_id"] == self_model.projection_id
    assert cognition[0].upstream_evidence["epistemic_projection_id"] == epistemic.projection_id
    assert result.changed_cognition_measurement_id is None


def test_history_comparison_keeps_self_model_and_epistemic_bindings_constant(tmp_path: Path) -> None:
    first, _ = owner(tmp_path / "cognition")
    acquired = first.run_tick(snapshot=snapshot(), tick_id="tick-1")
    source_record = first.writeback.store.get(acquired.written_record_id)
    epistemic, _, _ = epistemic_projection(tmp_path / "epistemic")
    self_model = self_model_projection(tmp_path / "self-model")
    restarted, fake = owner(tmp_path / "cognition", comparison=True)

    result = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-2",
        prior_self_model=self_model, prior_epistemic_state=epistemic)

    cognition = [request for request in fake.requests
                 if request.purpose == "resident_developmental_history_intervention_experiment"
                 and "history_present" in request.linkage]
    assert [request.linkage["history_present"] for request in cognition] == [True, False, True]
    assert {request.upstream_evidence["self_model_projection_digest"] for request in cognition} == {
        self_model.projection_digest}
    assert {request.upstream_evidence["epistemic_projection_digest"] for request in cognition} == {
        epistemic.projection_digest}
    selections = [request.upstream_evidence["developmental_history_selection"]
        for request in cognition]
    assert all(selection["schema_version"] == "sentientos.developmental_history_selection:v1"
        for selection in selections)
    assert all(selection["selection_digest"] == "sha256:" + digest_payload({
        key: value for key, value in selection.items() if key != "selection_digest"})
        for selection in selections)
    assert selections[0]["selected_records"] == [{"record_id": source_record.record_id,
        "record_digest": source_record.record_digest}]
    assert selections[1]["treatment"] == "withheld"
    assert selections[1]["selected_records"] == []
    assert selections[1]["omitted_records"] == [{"record_id": source_record.record_id,
        "record_digest": source_record.record_digest}]
    assert source_record.record_id not in cognition[1].prompt
    durable = [json.loads(path.read_text(encoding="utf-8"))
        for path in restarted.observations_root.glob("*.json")]
    by_request = {row["request_id"]: row for row in durable}
    assert all(by_request[request.request_id]["schema_version"].endswith(":v6")
        and by_request[request.request_id]["developmental_history_selection"]
            == request.upstream_evidence["developmental_history_selection"]
        for request in cognition)
    assert result.changed_cognition_measurement_id is not None


def test_tick_n_admitted_developmental_writeback_is_durable_and_bounded(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    result = composition.run_tick(snapshot=snapshot(), tick_id="tick-n")
    assert result.status == "completed" and result.written_record_id and result.writeback_receipt_id
    assert len(result.selected_fact_ids) == 1
    selected = next(f for f in snapshot().facts if f.fact_id == result.selected_fact_ids[0])
    assert selected.source.kind == "capability_registry"
    assert not result.prior_record_ids and result.same_tick_history_excluded
    assert [r.purpose for r in fake.requests] == ["resident_developmental_interpretation"]
    assert composition.writeback.store.get(result.written_record_id).current_truth is False
    assert composition.writeback.store.get_receipt(result.writeback_receipt_id).storage_verified
    inspected = composition.writeback.inspect_completed_records()
    assert [(record.record_id, receipt.receipt_id) for record, receipt in inspected] == [
        (result.written_record_id, result.writeback_receipt_id)]


def test_read_only_recovery_inspection_never_repairs_missing_writeback_receipt(
        tmp_path: Path) -> None:
    composition, _ = owner(tmp_path)
    result = composition.run_tick(snapshot=snapshot(), tick_id="inspection-receipt-gap")
    receipt_path = (composition.writeback.store.receipts_root
        / f"{result.writeback_receipt_id}.json")
    original = receipt_path.read_bytes()
    receipt_path.unlink()

    with pytest.raises(DevelopmentalWritebackError,
            match="durable_writeback_receipt_missing"):
        composition.writeback.inspect_completed_records()

    assert not receipt_path.exists()
    assert composition.writeback.store.get(result.written_record_id).record_digest
    assert original


def test_readiness_accepts_history_after_actual_owner_admission_recovery_check(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "resident"
    composition, _ = owner(root, comparison=True)
    written = composition.run_tick(snapshot=snapshot(), tick_id="preflight-history")

    config_path = tmp_path / "cognition.json"
    config_path.write_text(json.dumps({
        "schema": CONFIG_SCHEMA,
        "enabled": True,
        "history_root": str(root / "history"),
        "state_root": str(root / "state"),
        "allowed_source_kinds": ["capability_registry"],
        "max_selected_facts": 1,
        "max_retrieved_records": 4,
        "comparison_enabled": True,
    }))
    models = tmp_path / "models"
    models.mkdir()
    model_path = models / "selected.gguf"
    model_path.write_bytes(b"fixture artifact; never loaded")
    serving_path = tmp_path / "serving.json"
    identity = InstallationIdentity("install-readiness")
    registry = InstallationStateRegistry._for_testing(tmp_path / "install-state")
    registry.state_root_for(identity).mkdir(parents=True)
    serving_path.write_text(json.dumps({
        "schema_version": SERVING_CONFIG_SCHEMA,
        "enabled": True,
        "installation_identity": identity.value,
        "serving_operation_id": "readiness-fixture",
        "expected_activation_state_digest": "a" * 64,
    }))
    monkeypatch.setattr(readiness, "inspect_artifact", lambda *args, **kwargs: {
        "artifact_size_bytes": 123, "model_content_sha256": "a" * 64,
        "semantic_artifact_identity": "sha256:" + "b" * 64,
        "configuration_digest": "sha256:" + "c" * 64,
        "llama_cpp_dependency_available": True,
    })

    report = readiness.inspect_readiness(config_path, model_path, models,
        serving_config_path=serving_path, installation_registry=registry)

    assert written.written_record_id
    assert report["status"] == "ready_for_operator_review"
    assert report["findings"]["developmental_history"]["status"] == "eligible_history_present"
    assert report["findings"]["developmental_history"]["admission_validation"] == "verified_read_only"
    assert report["findings"]["developmental_history"]["runtime_recovery_validation"] == \
        "verified_read_only_no_repair"
    assert report["findings"]["resident_configuration"]["configured_history_root"] == \
        str(root / "history")
    assert report["findings"]["resident_configuration"]["configured_state_root"] == \
        str(root / "state")
    assert report["findings"]["serving_installation"]["installation_state_root"] == \
        str(registry.state_root_for(identity))
    assert any("Confirm the running daemon uses these exact cognition and serving configurations"
        in action
        for action in report["next_operator_actions"])
    assert report["findings"]["resident_configuration"]["running_daemon_binding"] == \
        "not_observed_explicit_config_paths_only"
    assert "resident_cognition_and_serving_config_same_process_lifetime_not_observed" in \
        report["unobserved_runtime_gates"]
    assert report["trial_execution_ready"] is False


def test_restart_recovers_writeback_committed_before_composition_checkpoint(tmp_path: Path) -> None:
    interrupted, _fake = owner(tmp_path)
    save_state = interrupted._save_state

    def interrupt_final_checkpoint(state):
        if state["completed_ticks"]:
            raise ResidentDevelopmentalCognitionError("simulated_after_writeback_before_checkpoint")
        save_state(state)

    interrupted._save_state = interrupt_final_checkpoint
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="simulated_after_writeback_before_checkpoint"):
        interrupted.run_tick(snapshot=snapshot(), tick_id="tick-interrupted")

    durable_records = interrupted.writeback.store.records()
    assert len(durable_records) == 1
    durable_receipts = interrupted.writeback.store.receipts()
    assert len(durable_receipts) == 1

    restarted, fake = owner(tmp_path)
    recovered = restarted._state()
    checkpoint = next(row for row in recovered["completed_ticks"]
                      if row["tick_id"] == "tick-interrupted")
    assert checkpoint["record_id"] == durable_records[0].record_id
    assert checkpoint["receipt_id"] == durable_receipts[0].receipt_id
    assert not any(row.get("tick_id") == "tick-interrupted"
                   for row in recovered["incomplete_ticks"])
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        restarted.run_tick(snapshot=snapshot(), tick_id="tick-interrupted")

    later = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-following")
    assert later.prior_record_ids == (durable_records[0].record_id,)
    assert any(request.purpose == "resident_developmental_retrieval_cognition"
               for request in fake.requests)


def test_same_tick_record_is_prohibited_from_retrieval(tmp_path: Path) -> None:
    composition, _ = owner(tmp_path)
    first = composition.run_tick(snapshot=snapshot(), tick_id="tick-n")
    assert first.written_record_id not in first.prior_record_ids
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        composition.run_tick(snapshot=snapshot(), tick_id="tick-n")


def test_restart_tick_n_plus_one_retrieves_prior_history_for_cognition(tmp_path: Path) -> None:
    first, _ = owner(tmp_path)
    written = first.run_tick(snapshot=snapshot(), tick_id="tick-n").written_record_id
    restarted, fake = owner(tmp_path)
    later = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-n-plus-one")
    assert later.prior_record_ids == (written,)
    assert len(later.cognition_observation_ids) == 1
    cognition = [r for r in fake.requests if r.purpose == "resident_developmental_retrieval_cognition"]
    assert cognition[0].upstream_evidence["record_ids"] == [written]
    observation = json.loads(next(restarted.observations_root.glob("*.json")).read_text())
    assert observation["historical_context_only"] and not observation["authority"]
    assert not observation["canonical_explicit_user_retention"]


def test_controlled_with_record_and_withheld_comparison_is_opt_in_and_difference_only(tmp_path: Path) -> None:
    first, _ = owner(tmp_path); first.run_tick(snapshot=snapshot(), tick_id="tick-n")
    restarted, fake = owner(tmp_path, comparison=True)
    later = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-n-plus-one")
    cognition = [r for r in fake.requests if r.purpose == "resident_developmental_history_intervention_experiment" and "history_present" in r.linkage]
    assert [r.linkage["history_present"] for r in cognition] == [True, False, True]
    assert cognition[0].upstream_evidence["snapshot_digest"] == cognition[1].upstream_evidence["snapshot_digest"]
    assert later.changed_cognition_measurement_id
    measured = json.loads((restarted.experiments.runs / f"{later.changed_cognition_measurement_id}.json").read_text())
    assert measured["summary"]["present_vs_withheld_difference_observed"] is True
    assert measured["summary"]["classification"] == "history_presence_associated_stable_difference"


def test_repeated_current_evidence_does_not_reinterpret_after_history_changes(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    composition.run_tick(snapshot=snapshot(), tick_id="tick-2")
    later = composition.run_tick(snapshot=snapshot(), tick_id="tick-3")
    assert later.written_record_id is not None
    record = composition.writeback.store.get(later.written_record_id)
    assert record.candidate["transformation_provenance"]["kind"] == "history_conditioned_cognition_conclusion:v1"
    assert len([r for r in fake.requests if r.purpose == "resident_developmental_interpretation"]) == 1
    assert len([r for r in fake.requests if r.purpose == "resident_developmental_retrieval_cognition"]) == 2


def test_missing_or_crossed_admission_prevents_history_mutation(tmp_path: Path) -> None:
    composition, _ = owner(tmp_path)
    composition.admission_authority = type("Missing", (), {"issue": lambda *a, **k: None})()
    with pytest.raises((AttributeError, ValueError)):
        composition.run_tick(snapshot=snapshot(), tick_id="tick-missing")
    assert not list((tmp_path / "history" / "records").glob("*.json"))


def test_configuration_is_exact_and_malformed_configuration_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    valid = {"schema":CONFIG_SCHEMA, "enabled":False, "history_root":str(tmp_path / "history"),
             "state_root":str(tmp_path / "state"), "allowed_source_kinds":["capability_registry"],
             "max_selected_facts":1, "max_retrieved_records":2, "comparison_enabled":False}
    path.write_text(json.dumps(valid)); assert load_config(path).enabled is False
    path.write_text(json.dumps({**valid, "personality":"helpful"}))
    with pytest.raises(ResidentDevelopmentalCognitionError, match="shape_invalid"): load_config(path)


def test_sentientosd_preserves_exact_snapshot_and_absent_config_is_inert(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SENTIENTOS_RESIDENT_DEVELOPMENTAL_COGNITION_CONFIG", raising=False)
    surfaces = RuntimeMaintenanceSurfaces(tmp_path, runtime_state_root=tmp_path / "runtime")
    feedback = surfaces.build_world_state_board(tick_id="2026-01-01T00:00:00+00:00")
    exact = surfaces.current_world_state_snapshot
    assert exact is not None and exact.snapshot_id == feedback["snapshot_id"]
    assert surfaces.run_resident_developmental_cognition(tick_id="2026-01-01T00:00:00+00:00")["status"] == "disabled"

    class Spy:
        seen = None
        def run_tick(self, *, snapshot, tick_id, **_kwargs):
            self.seen = snapshot
            return type("Result", (), {"__dataclass_fields__": {}, "status":"completed"})()
    spy = Spy()
    injected = RuntimeMaintenanceSurfaces(tmp_path, runtime_state_root=tmp_path / "runtime-2",
                                          resident_developmental_owner=spy)  # type: ignore[arg-type]
    injected.build_world_state_board(tick_id="2026-01-02T00:00:00+00:00")
    # The injected owner receives object identity, not a JSON reconstruction.
    try:
        injected.run_resident_developmental_cognition(tick_id="2026-01-02T00:00:00+00:00")
    except TypeError:
        pass
    assert spy.seen is injected.current_world_state_snapshot


def test_sentientosd_consumes_staged_objective_once_without_recurring_owner_config(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        isolated_governed_runtime_roots: None) -> None:
    monkeypatch.delenv("SENTIENTOS_RESIDENT_DEVELOPMENTAL_COGNITION_CONFIG", raising=False)
    fake = FakeInvoker()
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    fake.objective_plan_root = tmp_path / "cognition" / "state" / "developmental_experiments" / "protocols"
    cognition, _ = owner(tmp_path / "cognition", comparison=True, invoker=fake)
    seeded = cognition.run_tick(snapshot=snapshot(), tick_id="daemon-objective-history-seed")
    assert seeded.written_record_id
    request = stage_objective_request(tmp_path / "cognition" / "state",
        request_id="daemon-objective-once", task=ObjectivePredictionTask(3, 2, 7))
    surfaces = RuntimeMaintenanceSurfaces(tmp_path,
        runtime_state_root=tmp_path / "runtime-objective",
        resident_developmental_owner=cognition)  # type: ignore[arg-type]
    tick = "2026-10-13T00:00:00+00:00"
    surfaces.build_world_state_board(tick_id=tick)
    result = surfaces.run_resident_developmental_cognition(tick_id=tick)
    assert result["status"] == "objective_intervention_completed"
    assert result["objective_request_status"] == "objective_intervention_completed"
    assert result["written_record_id"] is None
    assert result["canonical_explicit_user_retention_mutated"] is False
    assert result["objective_measurement_summary"]["status"] == "verified_objective_measurement"
    assert result["objective_measurement_summary"]["actual_nonsynthetic_inference_verified"] is False
    assert len(result["objective_measurement_summary"]["conditions"]) == 3
    assert request.exists()
    trial_requests = [item for item in fake.requests
        if item.purpose == "resident_developmental_history_intervention_experiment"
        and "objective_task_plan_digest" in item.upstream_evidence]
    assert len(trial_requests) == 3

    # The staged file remains as custody evidence. Its durable request identity
    # prevents another trial, while ordinary cognition may continue next tick.
    next_tick = "2026-10-13T00:00:01+00:00"
    surfaces.build_world_state_board(tick_id=next_tick)
    later = surfaces.run_resident_developmental_cognition(tick_id=next_tick)
    assert later["objective_request_status"] == "completed"
    assert later["objective_measurement_summary"]["status"] == "verified_objective_measurement"
    assert later["objective_measurement_summary"]["actual_nonsynthetic_inference_verified"] is False
    assert len([item for item in fake.requests
        if item.purpose == "resident_developmental_history_intervention_experiment"
        and "objective_task_plan_digest" in item.upstream_evidence]) == 3


def test_sentientosd_composes_explicit_prior_epistemic_projection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SENTIENTOS_EPISTEMIC_STATE_CONFIG", raising=False)
    epistemic=PersistentEpistemicStateOwner(tmp_path/"epistemic",allowed_namespaces=["embodiment"])
    p=make_proposition(namespace="embodiment",subject="body:g1",predicate="healthy",
        object_value=True,polarity="positive",qualifiers={},temporal_scope={"kind":"prior"},
        context_scope={},proposition_class="descriptive")
    epistemic.register_proposition(p)
    epistemic.commit_update(proposition_id=p.proposition_id,expected_predecessor_digest=None,
        stance="unknown",reason="initialization",active_binding_ids=[],correlation_id="prior",tick=1,
        recorded_at="2026-01-01T00:00:00Z")
    class Spy:
        seen = None
        def run_tick(self, **kwargs):
            self.seen = kwargs
            return type("Result", (), {"__dataclass_fields__": {}, "status":"completed"})()
    spy=Spy()
    surfaces=RuntimeMaintenanceSurfaces(tmp_path,runtime_state_root=tmp_path/"runtime-epistemic",
        resident_developmental_owner=spy,epistemic_state_owner=epistemic,
        epistemic_state_config={"status":"configured","max_cognitive_projection_count":1,
                                "cognitive_consumption_enabled":True})  # type: ignore[arg-type]
    tick="2026-01-03T00:00:00+00:00"
    surfaces.build_world_state_board(tick_id=tick)
    feedback=surfaces.run_resident_developmental_cognition(tick_id=tick)
    projection=spy.seen["prior_epistemic_state"]
    assert projection.proposition_ids == (p.proposition_id,)
    assert feedback["epistemic_composition"]["status"] == "composed"
    assert feedback["epistemic_composition"]["authority"] is False


def test_epistemic_runtime_configuration_is_explicit_exact_and_independently_disabled(tmp_path: Path) -> None:
    assert _load_epistemic_state_owner(None) == (None, {"status":"disabled", "cognitive_consumption_enabled":False})
    path=tmp_path/"epistemic-config.json"
    payload={"schema":"sentientos.epistemic_runtime_config:v1","custody_root":str(tmp_path/"custody"),
        "allowed_proposition_namespaces":["embodiment"],"max_cognitive_projection_count":2,
        "cognitive_consumption_enabled":False}
    path.write_text(json.dumps(payload))
    configured, status=_load_epistemic_state_owner(str(path))
    assert configured is not None and status == {"status":"configured","max_cognitive_projection_count":2,
                                                  "cognitive_consumption_enabled":False}
    path.write_text(json.dumps({**payload,"ambient_discovery":True}))
    with pytest.raises(ValueError,match="configuration_invalid"):
        _load_epistemic_state_owner(str(path))



def test_recovered_history_order_uses_intent_not_wall_clock() -> None:
    from types import SimpleNamespace

    first = SimpleNamespace(
        created_at="2026-02-02T00:00:00+00:00",
        correlation_id="tick-first:resident-developmental-writeback",
        record_id="record-first")
    second = SimpleNamespace(
        created_at="2026-01-01T00:00:00+00:00",
        correlation_id="tick-second:resident-developmental-writeback",
        record_id="record-second")
    order = {"tick-first": 0, "tick-second": 1}
    first_key = ResidentDevelopmentalCognitionOwner._recovered_record_order(
        first, completed_order={}, recovery_intent_order=order)
    second_key = ResidentDevelopmentalCognitionOwner._recovered_record_order(
        second, completed_order={}, recovery_intent_order=order)
    assert first_key < second_key


def test_developmental_roots_resolve_aliases_and_exclude_canonical_memory(tmp_path: Path) -> None:
    import os

    from sentientos.canonical_memory import sentientos_memory_dir
    from sentientos.resident_developmental_cognition import _validate_root_separation

    if os.name == "posix":
        history = tmp_path / "history"
        history.mkdir()
        alias = tmp_path / "history-alias"
        alias.symlink_to(history, target_is_directory=True)
        with pytest.raises(ResidentDevelopmentalCognitionError,
                           match="configuration_roots_must_be_separate"):
            _validate_root_separation(history, alias, memory_root=tmp_path / "memory")

    memory = sentientos_memory_dir()
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="configuration_root_overlaps_canonical_memory"):
        _validate_root_separation(memory / "developmental-history", tmp_path / "state",
                                  memory_root=memory)

    # Reject the opposite nesting direction too: a developmental owner must
    # not claim a parent directory that also contains canonical user memory.
    memory_child = tmp_path / "owner-root" / "user-memory"
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="configuration_root_overlaps_canonical_memory"):
        _validate_root_separation(tmp_path / "owner-root", tmp_path / "other-state",
                                  memory_root=memory_child)


def test_cognition_checkpoint_round_trips_through_private_descriptor_custody(tmp_path: Path) -> None:
    import os
    import stat

    if os.name != "posix":
        pytest.skip("cognition checkpoint publication requires POSIX custody")
    cognition, _ = owner(tmp_path)
    state = cognition._state()
    cognition._save_state(state)

    metadata = cognition.state_path.stat()
    root_metadata = cognition.state_path.parent.stat()
    assert stat.S_ISREG(metadata.st_mode)
    assert metadata.st_uid == os.geteuid()
    assert metadata.st_mode & 0o077 == 0
    assert root_metadata.st_uid == os.geteuid()
    assert root_metadata.st_mode & 0o022 == 0
    assert cognition._state() == state


def test_cognition_checkpoint_rejects_replaced_symlink_root(tmp_path: Path) -> None:
    import os

    if os.name != "posix":
        pytest.skip("no-follow checkpoint publication requires POSIX")
    from sentientos.resident_developmental_cognition import _replace_cognition_state

    target = tmp_path / "external"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="composition_state_publication_failed"):
        _replace_cognition_state(alias / "composition_state.json", {"state": "bounded"})
    assert list(target.iterdir()) == []


def test_concurrent_developmental_ticks_cannot_replay_one_tick(tmp_path: Path) -> None:
    import os
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    if os.name != "posix":
        pytest.skip("POSIX cognition tick lock is required")
    first, _ = owner(tmp_path)
    second, _ = owner(tmp_path)
    tick_snapshot = WorldStateBoardBuilder().build([])
    barrier = Barrier(2)

    def run(owner_instance):
        barrier.wait()
        return owner_instance.run_tick(snapshot=tick_snapshot, tick_id="one-shared-tick")

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(run, first)
        right = pool.submit(run, second)
        results = []
        for future in (left, right):
            try:
                results.append(future.result())
            except ResidentDevelopmentalCognitionError as exc:
                results.append(str(exc))

    assert sum(getattr(result, "status", None) == "completed" for result in results) == 1
    assert results.count("tick_already_completed") == 1


def test_actual_history_conditioned_conclusion_is_the_retained_candidate(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path / "one")
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")

    assert result.written_record_id and result.writeback_receipt_id
    record = composition.writeback.store.get(result.written_record_id)
    candidate = record.candidate
    provenance = candidate["transformation_provenance"]
    assert provenance["kind"] == "history_conditioned_cognition_conclusion:v1"
    assert candidate["interpretation"] == fake.lesson_statement
    assert provenance["lesson_candidate"]["scope"] == fake.lesson_scope
    assert provenance["source_output_digest"] == candidate["output_digest"]
    assert digest_payload({"output": provenance["source_output_text"]}) == candidate["output_digest"]
    assert provenance["observation_id"] in result.cognition_observation_ids
    assert provenance["consumed_context"]["retrieved_record_ids"] == list(result.prior_record_ids)
    assert candidate["inference_receipt_id"] != ""
    # The candidate reuses the cognition call. Only the first tick's existing
    # current-evidence interpretation call occurred; no lesson-only call was added.
    assert [request.purpose for request in fake.requests] == [
        "resident_developmental_interpretation",
        "resident_developmental_retrieval_cognition",
    ]


def test_distinct_actual_conclusions_produce_distinct_bound_candidates(tmp_path: Path) -> None:
    records = []
    for label in ("lesson-alpha", "lesson-beta"):
        root = tmp_path / label
        composition, fake = owner(root)
        composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
        fake.lesson_statement = label
        result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
        records.append(composition.writeback.store.get(result.written_record_id))
    left, right = (record.candidate for record in records)
    assert left["interpretation"] == "lesson-alpha"
    assert right["interpretation"] == "lesson-beta"
    assert left["candidate_id"] != right["candidate_id"]
    assert left["candidate_digest"] != right["candidate_digest"]
    assert left["transformation_provenance"]["source_output_text"] != right["transformation_provenance"]["source_output_text"]


def test_retained_cognition_lesson_reaches_later_tick_after_restart(tmp_path: Path) -> None:
    first, fake = owner(tmp_path)
    first.run_tick(snapshot=snapshot(), tick_id="tick-1")
    fake.lesson_statement = "Later reasoning should revisit the bounded cited condition."
    retained = first.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = first.writeback.store.get(retained.written_record_id)
    restarted, later_fake = owner(tmp_path)
    later = restarted.run_tick(snapshot=snapshot(3), tick_id="tick-3")
    assert record.record_id in later.prior_record_ids
    prompt = json.loads(next(
        request.prompt for request in later_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition"))
    history_packet = next(item for item in prompt["developmental_history"]
        if item["record_id"] == record.record_id)
    assert {"record_id": record.record_id,
        "record_digest": record.record_digest} in prompt[
            "developmental_history_selection"]["selected_records"]
    assert history_packet["interpretation"] == record.candidate["interpretation"]
    lesson = record.candidate["transformation_provenance"]["lesson_candidate"]
    assert history_packet["scope"] == lesson["scope"]
    assert history_packet["applicability"] == lesson["applicability"]
    assert history_packet["current_truth"] is False
    assert "source_output_text" not in json.dumps(prompt)
    assert "Later reasoning should revisit the bounded cited condition." in json.dumps(prompt)
    assert "authority" not in record.candidate and "current_truth" not in record.candidate
    assert record.epistemic_posture == "historical_interpretation_not_current_truth"


def test_unconsumed_evidence_citation_does_not_become_a_cognition_candidate(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    fake.lesson_dependency_override = "fabricated-source-id"
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = composition.writeback.store.get(result.written_record_id)
    assert record.candidate["transformation_provenance"]["kind"] != "history_conditioned_cognition_conclusion:v1"
    assert any(request.purpose == "resident_developmental_interpretation" for request in fake.requests)


def test_truncated_cognition_output_never_manufactures_retained_lesson(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    fake.truncate_cognition_output = True
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = composition.writeback.store.get(result.written_record_id)
    assert record.candidate["transformation_provenance"]["kind"] != "history_conditioned_cognition_conclusion:v1"


def test_recovered_candidate_requires_its_exact_durable_cognition_observation(tmp_path: Path) -> None:
    composition, _fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    candidate = composition.writeback.store.get(result.written_record_id).candidate
    observation_path = composition.observations_root / f"{candidate['transformation_provenance']['observation_id']}.json"
    observation = json.loads(observation_path.read_text())
    observation["output_digest"] = "sha256:" + "0" * 64
    observation_path.write_text(json.dumps(observation, indent=2, sort_keys=True) + "\\n")
    restarted, _ = owner(tmp_path)
    with pytest.raises(ResidentDevelopmentalCognitionError, match="cognition_observation"):
        restarted._state()


def test_pre_v6_observation_recovery_preserves_historical_digest_shape(tmp_path: Path) -> None:
    composition, _fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    path = next(composition.observations_root.glob("*.json"))
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["schema_version"] == "sentientos.resident_cognition_observation:v6"
    value.pop("observation_id")
    value.pop("observation_digest")
    value.pop("developmental_history_selection")
    value["schema_version"] = "sentientos.resident_cognition_observation:v5"
    digest = "sha256:" + digest_payload(value)
    observation_id = "devcog-" + digest[7:31]
    value["observation_id"] = observation_id
    value["observation_digest"] = digest
    migrated_path = path.with_name(observation_id + ".json")
    migrated_path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    path.unlink()

    restarted, _ = owner(tmp_path)
    recovered = restarted._recover_observation_ticks(include_records=True)
    assert recovered[observation_id]["schema_version"] == \
        "sentientos.resident_cognition_observation:v5"
    assert "developmental_history_selection" not in recovered[observation_id]


def test_v6_history_selection_recovery_reconciles_the_invocation_receipt(tmp_path: Path) -> None:
    invoker = SessionBoundFakeInvoker()
    composition, _ = owner(tmp_path, comparison=True, invoker=invoker)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    path = next(composition.observations_root.glob("*.json"))
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["schema_version"] == "sentientos.resident_cognition_observation:v6"
    value.pop("observation_id")
    value.pop("observation_digest")
    selection = value["developmental_history_selection"]
    selection["retrieval_policy_id"] = "task_family_relevant_then_recency_fill:v1"
    selection_semantic = {key: item for key, item in selection.items()
        if key != "selection_digest"}
    selection["selection_digest"] = "sha256:" + digest_payload(selection_semantic)
    digest = "sha256:" + digest_payload(value)
    observation_id = "devcog-" + digest[7:31]
    value["observation_id"] = observation_id
    value["observation_digest"] = digest
    substituted_path = path.with_name(observation_id + ".json")
    substituted_path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    path.unlink()

    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="cognition_history_selection_invocation_binding_mismatch"):
        composition._recover_observation_ticks(include_records=True)


def test_experimental_history_arms_do_not_retain_cognition_lessons(tmp_path: Path) -> None:
    first, _ = owner(tmp_path)
    first.run_tick(snapshot=snapshot(), tick_id="tick-1")
    experimental, fake = owner(tmp_path, comparison=True)
    experimental.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    experiment_calls = [request for request in fake.requests
        if request.purpose == "resident_developmental_history_intervention_experiment"
        and "history_present" in request.linkage]
    assert len(experiment_calls) == 3
    assert all(request.expected_output_format == "text" for request in experiment_calls)
    assert all(request.to_receipt_request_dict().get("structured_output_schema") is None
        for request in experiment_calls)
    records = experimental.writeback.store.records()
    assert all(record.candidate["transformation_provenance"].get("kind")
        != "history_conditioned_cognition_conclusion:v1" for record in records)


def test_cognition_lesson_writeback_is_later_tick_only_and_recovery_is_idempotent(tmp_path: Path) -> None:
    first, _fake = owner(tmp_path)
    first.run_tick(snapshot=snapshot(), tick_id="tick-1")
    result = first.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = first.writeback.store.get(result.written_record_id)
    assert record.record_id not in result.prior_record_ids
    restarted, fake = owner(tmp_path)
    recovered = restarted._state()
    assert any(row["tick_id"] == "tick-2" and row["record_id"] == record.record_id
        for row in recovered["completed_ticks"])
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        restarted.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    later = restarted.run_tick(snapshot=snapshot(3), tick_id="tick-3")
    assert record.record_id in later.prior_record_ids
    assert any(request.purpose == "resident_developmental_retrieval_cognition"
        for request in fake.requests)


def test_modified_output_and_crossed_request_identity_are_rejected(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path / "modified")
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    fake.modify_cognition_output_after_digest = True
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = composition.writeback.store.get(result.written_record_id)
    assert record.candidate["transformation_provenance"]["kind"] != "history_conditioned_cognition_conclusion:v1"

    crossed, crossed_fake = owner(tmp_path / "crossed")
    crossed.run_tick(snapshot=snapshot(), tick_id="tick-1")
    crossed_fake.cross_cognition_request_identity = True
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="cognition_epistemic_receipt_binding_mismatch"):
        crossed.run_tick(snapshot=snapshot(2), tick_id="tick-2")


def test_out_of_scope_length_and_substituted_evidence_are_not_retained(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    fake.lesson_scope = "x" * 401
    fake.lesson_dependency_override = "different-unconsumed-evidence"
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = composition.writeback.store.get(result.written_record_id)
    assert record.candidate["transformation_provenance"]["kind"] != "history_conditioned_cognition_conclusion:v1"


def test_interruption_after_cognition_observation_does_not_reinfer_or_fabricate_candidate(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")

    def interrupt_candidate(*_args, **_kwargs):
        raise RuntimeError("interrupted_before_candidate_commit")

    composition.writeback.candidate_from_history_conditioned_cognition = interrupt_candidate
    with pytest.raises(RuntimeError, match="interrupted_before_candidate_commit"):
        composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    assert len(list(composition.observations_root.glob("*.json"))) == 1

    restarted, restarted_fake = owner(tmp_path)
    recovered = restarted._state()
    interrupted = next(row for row in recovered["incomplete_ticks"] if row["tick_id"] == "tick-2")
    assert interrupted["status"] == "interrupted_recovered"
    assert not restarted_fake.requests
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        restarted.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    assert not restarted_fake.requests


def test_candidate_record_committed_before_checkpoint_recovers_once(tmp_path: Path) -> None:
    composition, _fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    save_state = composition._save_state

    def interrupt_final_checkpoint(state):
        if (state["completed_ticks"]
                and state["completed_ticks"][-1]["tick_id"] == "tick-2"):
            raise ResidentDevelopmentalCognitionError("simulated_after_candidate_before_checkpoint")
        save_state(state)

    composition._save_state = interrupt_final_checkpoint
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="simulated_after_candidate_before_checkpoint"):
        composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")

    durable = composition.writeback.store.records()
    assert len(durable) == 2
    candidate_record = next(record for record in durable
        if record.candidate["transformation_provenance"].get("kind")
        == "history_conditioned_cognition_conclusion:v1")
    restarted, fake = owner(tmp_path)
    recovered = restarted._state()
    assert any(row["record_id"] == candidate_record.record_id
        and row["tick_id"] == "tick-2" for row in recovered["completed_ticks"])
    later = restarted.run_tick(snapshot=snapshot(3), tick_id="tick-3")
    assert candidate_record.record_id in later.prior_record_ids
    assert any(request.purpose == "resident_developmental_retrieval_cognition"
        for request in fake.requests)


def test_null_lesson_packet_is_not_automatically_retained(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    fake.no_cognition_lesson = True
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = composition.writeback.store.get(result.written_record_id)
    assert record.candidate["transformation_provenance"].get("kind") != "history_conditioned_cognition_conclusion:v1"
    assert any(request.purpose == "resident_developmental_interpretation"
        for request in fake.requests)


class HermeticCognitionBackend:
    """Local deterministic model substitute used behind the real governed invoker."""

    def __init__(self, statement: str = "Preserve the cited historical condition.") -> None:
        self.statement = statement
        self.calls: list[str] = []
        self.no_lesson = False

    def generate(self, prompt: str, **kwargs) -> str:
        self.calls.append(prompt)
        schema = kwargs.get("structured_output_schema")
        required = set(schema.get("required", ())) if isinstance(schema, dict) else set()
        if required == {"interpretation", "uncertainty"}:
            return json.dumps({"interpretation": "bounded current evidence",
                               "uncertainty": "medium"})
        context = json.loads(prompt)
        history = context.get("developmental_history", [])
        evidence_ids = [str(item["record_id"]) for item in history
                        if isinstance(item, dict) and isinstance(item.get("record_id"), str)]
        current = context.get("current_evidence", {})
        evidence_ids.extend(str(item["fact_id"]) for item in current.get("facts", [])
                            if isinstance(item, dict) and isinstance(item.get("fact_id"), str))
        return json.dumps({
            "conclusion": "I conclude: " + self.statement,
            "lesson_candidate": None if self.no_lesson else {
                "statement": self.statement,
                "scope": "the cited historical context",
                "applicability": "only while the cited conditions remain applicable",
                "uncertainty": "medium",
                "uncertainty_rationale": "the source is an interpretation of retained evidence",
                "evidence_dependencies": evidence_ids[:1],
                "possible_contradiction_ids": [],
            },
        }, sort_keys=True)


def governed_owner(root: Path, *, backend: HermeticCognitionBackend, comparison: bool = False):
    root.mkdir(parents=True, exist_ok=True)
    model_path = root / "fixture.gguf"
    model_path.write_bytes(b"hermetic local backend fixture")
    model_config = ModelConfig(
        candidates=[ModelCandidate(path=model_path, engine="llama_cpp", name="fixture")],
        generation=GenerationConfig(max_new_tokens=512),
    )
    authority_map = build_local_model_authority_map(model_config, allowed_roots=[root])
    invoker = GovernedLocalModelInvoker(
        model=backend, authority_map=authority_map,
        kernel=ControlPlaneKernel(phase=LifecyclePhase.RUNTIME,
            decisions_path=root / "control-plane-decisions.jsonl"),
        runtime_root=root / "invocation-custody",
    )
    ledger = AdmissionLedger(root / "state" / "admissions.json")
    definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}

    def current_sequence():
        admissions, revocations = ledger.load()
        return max([item.issued_sequence for item in admissions]
                   + [item.sequence for item in revocations], default=1)

    def next_sequence():
        return current_sequence() + 1

    writeback = ResidentDevelopmentalWritebackController(
        history_root=root / "history",
        admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger),
        current_sequence=current_sequence,
    )
    owner_value = ResidentDevelopmentalCognitionOwner(
        config=ResidentDevelopmentalCognitionConfig(
            root / "history", root / "state", ("capability_registry",), 1, 4, comparison),
        writeback=writeback,
        admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
        invoker=invoker,
        current_sequence=next_sequence,
    )
    return owner_value, invoker


@pytest.fixture
def isolated_governed_runtime_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Keep real local-invocation admission custody inside each hermetic test."""
    roots = {
        "SENTIENTOS_GOVERNOR_ROOT": tmp_path / "governor",
        "SENTIENTOS_FEDERATION_ROOT": tmp_path / "federation",
        "SENTIENTOS_CONTROL_KERNEL_ROOT": tmp_path / "kernel",
        "PULSE_TRUST_EPOCH_ROOT": tmp_path / "pulse-trust",
    }
    for name, path in roots.items():
        monkeypatch.setenv(name, str(path))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(roots["PULSE_TRUST_EPOCH_ROOT"] / "state.json"))
    def reset_governance_owners() -> None:
        reset_runtime_governor()
        reset_federated_governance()
        reset_pulse_trust_epoch()
        reset_trust_ledger()

    reset_governance_owners()
    yield
    reset_governance_owners()


def test_real_governed_invocation_output_is_retained_without_a_lesson_only_call(
    tmp_path: Path, isolated_governed_runtime_roots: None,
) -> None:
    backend = HermeticCognitionBackend("keep the observation's original scope")
    composition, invoker = governed_owner(tmp_path, backend=backend)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")

    record = composition.writeback.store.get(result.written_record_id)
    candidate = record.candidate
    provenance = candidate["transformation_provenance"]
    assert provenance["kind"] == "history_conditioned_cognition_conclusion:v1"
    assert candidate["interpretation"] == backend.statement
    assert candidate["model_id"] == provenance["source_request"]["model_id"]
    assert candidate["request_digest"] == provenance["source_request"]["request_digest"]
    assert provenance["source_output_text"].startswith('{"conclusion":')
    assert digest_payload({"output": provenance["source_output_text"]}) == candidate["output_digest"]
    # Tick one uses the existing interpretation request; tick two uses one
    # history-conditioned call whose exact output becomes the candidate.
    assert len(backend.calls) == 2
    assert result.cognition_observation_ids == (provenance["observation_id"],)


def test_real_invoker_retains_distinct_lessons_and_later_tick_reads_them(
    tmp_path: Path, isolated_governed_runtime_roots: None,
) -> None:
    backend = HermeticCognitionBackend("lesson A")
    composition, _invoker = governed_owner(tmp_path, backend=backend)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    first = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    first_record = composition.writeback.store.get(first.written_record_id)
    assert first_record.candidate["interpretation"] == "lesson A"

    backend.statement = "lesson B"
    restarted, _ = governed_owner(tmp_path, backend=backend)
    second = restarted.run_tick(snapshot=snapshot(3), tick_id="tick-3")
    second_record = restarted.writeback.store.get(second.written_record_id)
    assert second_record.candidate["interpretation"] == "lesson B"
    assert first_record.candidate["candidate_id"] != second_record.candidate["candidate_id"]
    assert first_record.record_id in second.prior_record_ids

    later_backend = HermeticCognitionBackend("later conclusion")
    later_owner, _ = governed_owner(tmp_path, backend=later_backend)
    later = later_owner.run_tick(snapshot=snapshot(4), tick_id="tick-4")
    assert second_record.record_id in later.prior_record_ids
    assert any(second_record.record_id in prompt for prompt in later_backend.calls)


def test_real_invoker_null_candidate_does_not_turn_the_conclusion_into_a_lesson(
    tmp_path: Path, isolated_governed_runtime_roots: None,
) -> None:
    backend = HermeticCognitionBackend("conclusion with no scoped lesson")
    backend.no_lesson = True
    composition, _ = governed_owner(tmp_path, backend=backend)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = composition.writeback.store.get(result.written_record_id)
    assert record.candidate["transformation_provenance"].get("kind") != "history_conditioned_cognition_conclusion:v1"
    assert len(backend.calls) == 3


def test_missing_output_text_and_substituted_scope_never_create_a_candidate(tmp_path: Path) -> None:
    missing, missing_fake = owner(tmp_path / "missing")
    missing.run_tick(snapshot=snapshot(), tick_id="tick-1")
    missing_fake.unavailable_cognition_output = True
    missing_result = missing.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    missing_record = missing.writeback.store.get(missing_result.written_record_id)
    assert missing_record.candidate["transformation_provenance"].get("kind") != "history_conditioned_cognition_conclusion:v1"

    scoped, _ = owner(tmp_path / "scope")
    scoped.run_tick(snapshot=snapshot(), tick_id="tick-1")
    original = scoped.writeback.candidate_from_history_conditioned_cognition

    def substitute_scope(selection, receipt, **kwargs):
        altered = dict(kwargs["lesson_payload"])
        altered_lesson = dict(altered["lesson_candidate"])
        altered_lesson["scope"] = "substituted scope"
        altered["lesson_candidate"] = altered_lesson
        kwargs["lesson_payload"] = altered
        return original(selection, receipt, **kwargs)

    scoped.writeback.candidate_from_history_conditioned_cognition = substitute_scope
    with pytest.raises(DevelopmentalWritebackError, match="cognition_lesson_output_invalid"):
        scoped.run_tick(snapshot=snapshot(2), tick_id="tick-2")


def test_compounded_integrity_failure_retains_unknown_pressure_through_later_cognition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime-state"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(tmp_path / "trust"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(tmp_path / "trust/state.json"))
    monkeypatch.setenv("SENTIENTOS_INTEGRITY_CONTROLLER_OBSERVATION", "1")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY", "0")
    reset_runtime_governor()

    from sentientos.integrity_quarantine import QUARANTINE_PATH
    quarantine = tmp_path / QUARANTINE_PATH
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    quarantine.write_text("{malformed protective state", encoding="utf-8")
    feed = tmp_path / "pulse/integrity_incidents.jsonl"
    feed.parent.mkdir(parents=True, exist_ok=True)
    feed.write_text("{malformed pressure feed", encoding="utf-8")

    cognition, fake = owner(
        tmp_path / "cognition", allowed_source_kinds=("audit_trust",),
    )
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=cognition,  # type: ignore[arg-type]
    )
    tick = "2026-10-12T00:00:00+00:00"
    surfaces.build_world_state_board(tick_id=tick)
    snapshot_value = surfaces.current_world_state_snapshot
    assert snapshot_value is not None
    fact = next(item for item in snapshot_value.facts
        if item.subject.subject_kind == "integrity_controller_observation")
    assert fact.payload["controller_posture"] == "fail"
    assert fact.payload["failed_gate_count"] >= 2
    assert "pressure_summary" not in fact.payload
    current_gates = {row["name"]: row for row in fact.payload["gate_results"]}
    assert current_gates["quarantine_custody"]["status"] == "fail"
    assert current_gates["integrity_pressure_input"]["status"] == "fail"

    first = surfaces.run_resident_developmental_cognition(tick_id=tick)
    assert first["written_record_id"]
    interpretation = next(request for request in fake.requests
        if request.purpose == "resident_developmental_interpretation")
    selected = json.loads(interpretation.prompt)["selection"]["facts"]
    current_fact = next(item for item in selected
        if item.get("subject", {}).get("subject_kind") == "integrity_controller_observation")
    assert {row["name"] for row in current_fact["payload"]["gate_results"]} >= {
        "quarantine_custody", "integrity_pressure_input",
    }
    assert "pressure_summary" not in json.dumps(current_fact["payload"])

    later_owner, later_fake = owner(
        tmp_path / "cognition", allowed_source_kinds=("audit_trust",),
    )
    later_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=later_owner,  # type: ignore[arg-type]
    )
    later_tick = "2026-10-12T00:00:01+00:00"
    later_surfaces.build_world_state_board(tick_id=later_tick)
    second = later_surfaces.run_resident_developmental_cognition(tick_id=later_tick)
    assert second["written_record_id"]
    retrieval = next(request for request in later_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    packets = json.loads(retrieval.prompt)["developmental_history"]
    prior = next(packet for packet in packets if packet["record_id"] == first["written_record_id"])
    historical = next(item for item in prior["source_evidence_context"]
        if item["subject_kind"] == "integrity_controller_observation")
    history_gates = {row["name"]: row for row in historical["context"]["gates"]}
    assert history_gates["quarantine_custody"]["status"] == "fail"
    assert history_gates["integrity_pressure_input"]["status"] == "fail"
    assert historical["historical_only"] is True
    assert historical["current_truth"] is False
    assert historical["authority"] is False
    assert historical["attack_established"] is False
    reset_runtime_governor()
