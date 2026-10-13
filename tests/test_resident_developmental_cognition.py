from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Iterator

import pytest

from sentientos.codex_task_authority_admission import RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION
from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore, DevelopmentalHistoryInterventionError,
)
from sentientos.developmental_model_replacement_experiment import ObjectivePredictionTask
from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import ControlPlaneKernel, LifecyclePhase
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
            assert len(plans) == 1
            plan = json.loads(plans[0].read_text(encoding="utf-8"))
            assert plan["plan_digest"] == request.upstream_evidence["objective_task_plan_digest"]
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
        return LocalModelInvocationReceipt(request=receipt_request, status="admitted_completed",
            reason_codes=("completed",), output_text=receipt_text, output_digest=receipt_digest,
            output_size_bytes=len(original_output.encode()), admission_decision_ref="local",
            purpose=request.purpose, latency_ms=1, output_truncated=truncated, fallback_occurred=False,
            effects={"local_model_inference":True}, observed_at="2026-01-01T00:00:00+00:00",
            generation_config={"actual_generation_parameters":{"temperature":0}} if request.purpose == "resident_developmental_history_intervention_experiment" else {})


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
    with pytest.raises(DevelopmentalHistoryInterventionError,
                       match="run_artifact_invocation_verifier_unavailable"):
        DevelopmentalExperimentStore(tmp_path / "state").load_run(
            experiment_result.changed_cognition_measurement_id)
    restarted, _ = owner(tmp_path, invoker=invoker)
    restarted.run_tick(snapshot=snapshot(), tick_id="session-tick-3")
    assert invoker.verified_receipts
    assert all(item[2]["expected_session_id"] == invoker.session_id
        for item in invoker.verified_receipts)


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
    fake = FakeInvoker()
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
    ledger = AdmissionLedger(root / "state" / "admissions.json")
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
    first.run_tick(snapshot=snapshot(), tick_id="tick-1")
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
