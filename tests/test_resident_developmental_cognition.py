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
    _bind_history_and_epistemic_context,
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


@pytest.fixture(autouse=True)
def _isolate_shared_runtime_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep default daemon governance state inside each test's disposable root."""
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime-state"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))


def snapshot(value: int = 1):
    return WorldStateBoardBuilder().build([
        {"source_id":"source-b", "source_kind":"audit_trust", "subject_id":"b", "stage":"observation", "disposition":"recorded", "observed_at":"2026-01-01T00:00:00+00:00", "payload":{"value":9}},
        {"source_id":"source-a", "source_kind":"capability_registry", "subject_id":"a", "stage":"observation", "disposition":"recorded", "observed_at":"2026-01-01T00:00:00+00:00", "payload":{"value":value}},
        {"source_id":"source-c", "source_kind":"capability_registry", "subject_id":"c", "stage":"observation", "disposition":"recorded", "observed_at":"2026-01-01T00:00:00+00:00", "payload":{"value":3}},
    ])


class FakeInvoker:
    def __init__(self) -> None:
        self.requests = []
        self.active_model_identity: dict[str, str] = {}
        self.resource_contexts = []
        self.lesson_statement = "When prior evidence conflicts, preserve its scope and uncertainty."
        self.lesson_scope = "historical evidence interpretation"
        self.lesson_uncertainty = "medium"
        self.lesson_uncertainty_rationale = "Historical evidence may not generalize."
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

    def observed_current_model_identity(self):
        return dict(self.active_model_identity) if self.active_model_identity else None

    def build_request(self, **kwargs):
        request = type("Request", (), {})()
        for key, value in kwargs.items(): setattr(request, key, value)
        request.prompt_digest = digest_payload({"prompt": kwargs["prompt"]})
        request.prompt_size = len(kwargs["prompt"].encode("utf-8"))
        request.model_id = "model-a"; request.model_artifact_digest = "sha256:model"
        request.authority_map_digest = "test-authority-map"
        request.active_model_identity = dict(self.active_model_identity)
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
            "model_artifact_digest": "sha256:model",
            "active_model_identity": dict(self.active_model_identity),
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

    def invoke(self, request, *, persist, include_output_in_receipt,
            resource_context=None):
        if resource_context is not None:
            self.resource_contexts.append(resource_context)
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
            elif self.objective_mode in {"derive_from_admitted_family",
                    "derive_from_latest_admitted_family"}:
                examples = []
                for packet in history:
                    for experience in packet.get("task_relevant_experience", ()):
                        if (isinstance(experience, Mapping)
                                and experience.get("task_family_id") == descriptor.get("task_family_id")
                                and experience.get("event_scope") ==
                                    "scored_benchmark_outcome_not_external_environmental_event"):
                            examples.extend((int(item["probe_input"]), int(item["observed_answer"]))
                                for item in experience.get("examples", ())
                                if isinstance(item, Mapping)
                                and type(item.get("probe_input")) is int
                                and type(item.get("observed_answer")) is int)
                if len(examples) >= 2:
                    fitting_examples = (examples[-2:]
                        if self.objective_mode == "derive_from_latest_admitted_family"
                        else examples[:2])
                    (x1, y1), (x2, y2) = fitting_examples
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
                "uncertainty": self.lesson_uncertainty,
                "uncertainty_rationale": self.lesson_uncertainty_rationale,
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
        elif request.purpose == "resident_developmental_retrieval_cognition":
            text = json.dumps({"recommendation": self.lesson_statement,
                "uncertainty": self.lesson_uncertainty}, sort_keys=True)
            original_output = text
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
            "output_size_bytes": receipt.output_size_bytes,
            "generation_config": dict(receipt.generation_config),
            "backend_completion": (dict(receipt.backend_completion)
                if receipt.backend_completion is not None else None),
            "resource_allocation_digest": receipt.resource_allocation_digest,
            "resource_attempt_id": receipt.resource_attempt_id,
            "resource_consumption_receipt_digests": list(
                receipt.resource_consumption_receipt_digests),
            "resource_linkage_digest": receipt.resource_linkage_digest,
            "observed_at": receipt.observed_at}


class InstallationCustodyFakeInvoker(SessionBoundFakeInvoker):
    """Deterministic issuer whose receipts use the real installation custody reader."""

    installation_handle = None
    installation_reader = None

    def invoke(self, request, **kwargs):
        receipt = super().invoke(request, **kwargs)
        if self.installation_handle is None:
            raise AssertionError("fixture installation writer not configured")
        # Keep test-generated outputs truthful at the canonical receipt boundary:
        # valid durable custody does not turn a deterministic fake into inference.
        from dataclasses import replace
        simulated = replace(receipt, status="admitted_simulation",
            effects={**dict(receipt.effects), "local_model_inference": False})
        self.receipts.pop(receipt.receipt_id, None)
        self.receipts[simulated.receipt_id] = simulated
        receipt = simulated
        relative = ("local-model/resident-cognitive-serving/inference/receipts/"
            + receipt.receipt_id + ".json")
        target = self.installation_handle.fixed_object(relative)
        self.installation_handle.ensure_directory(
            self.installation_handle.fixed_object(relative.rsplit("/", 1)[0]))
        payload = (json.dumps(receipt.to_dict(), sort_keys=True, indent=2) + "\n").encode()
        self.installation_handle.durable_create(target, payload)
        return receipt

    def verify_persisted_invocation_receipt(self, receipt_id, receipt_digest, **expected):
        if self.installation_reader is None:
            raise AssertionError("fixture read-only installation receipt reader not configured")
        return self.installation_reader.verify_persisted_invocation_receipt(
            receipt_id, receipt_digest, **expected)


def _bind_fixture_installation_custody(root: Path,
        invoker: InstallationCustodyFakeInvoker, *, publish_session: bool = True) -> None:
    """Install synthetic serving witness and bind the fake issuer to real custody APIs."""
    from sentientos.resident_cognitive_model_serving import (
        WITNESS_SCHEMA, ResidentCognitiveInvocationReceiptReader, ServingSession,
        _resident_serving_session_receipt, resident_serving_session_receipt_reference,
    )
    from sentientos.local_runtime_provisioning import semantic_digest

    identity = InstallationIdentity("task-family-transfer-installation")
    registry = InstallationStateRegistry._for_testing(root / "installation-custody")
    handle = registry.open(identity, create=True)
    binding = {
        "installation_identity": identity.value,
        "serving_operation_id": "task-family-transfer-serving",
        "serving_config_digest": "d" * 64,
        "model_serving_admission_ref": "local",
        "activation_state_semantic_digest": "a" * 64,
        "observed_loaded_model_identity": dict(invoker.active_model_identity),
    }
    session = ServingSession("resident-serving-session-" + semantic_digest(binding)[:24], binding)
    session_receipt = _resident_serving_session_receipt(session.to_dict())
    reference = resident_serving_session_receipt_reference(session)

    def persist(relative: str, value: Mapping[str, object]) -> None:
        target = handle.fixed_object(relative)
        handle.ensure_directory(handle.fixed_object(relative.rsplit("/", 1)[0]))
        payload = (json.dumps(dict(value), sort_keys=True, separators=(",", ":")) + "\n").encode()
        if publish_session:
            handle.durable_create(target, payload)

    persist("local-model/resident-cognitive-serving/receipts/"
        + session_receipt["receipt_id"] + ".json", session_receipt)
    witness = {"schema_version": WITNESS_SCHEMA, "session_id": session.session_id,
        "receipt_id": session_receipt["receipt_id"],
        "receipt_semantic_digest": session_receipt["receipt_semantic_digest"],
        "admission_decision_ref": binding["model_serving_admission_ref"],
        "authority_class": AuthorityClass.MODEL_SERVING.value, "inference_performed": False}
    witness["witness_semantic_digest"] = semantic_digest(witness)
    persist("logs/privileges/" + session_receipt["receipt_id"] + ".json", witness)
    invoker.session_id = session.session_id
    invoker.session_binding = {
        "model_serving_admission_ref": binding["model_serving_admission_ref"],
        "activation_state_semantic_digest": binding["activation_state_semantic_digest"],
        **reference,
    }
    invoker.installation_handle = handle
    invoker.installation_reader = ResidentCognitiveInvocationReceiptReader(
        registry.open_read_only(identity))


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
    cognition, model = owner(tmp_path, comparison=True, invoker=fake,
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
    fake.active_model_identity = {"provider": "fixture", "model": "model-a"}
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
    history_score = evidence["objective_scores"][0]
    assert history_score["evaluator"] == "deterministic_exact_integer_suite_oracle_v2"
    assert history_score["task_digest"] == evidence["objective_task_descriptor"]["task_digest"]
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
    assert "offset" not in json.dumps(evidence)

    from sentientos.resident_developmental_writeback import (
        DevelopmentalWritebackError, _developmental_history_interpretation_projection,
    )
    projection_fact = {"fact_id": "fixture-history-fact",
        "subject": {"subject_id": records[0]["subject_id"],
            "subject_kind": records[0]["subject_kind"]}}
    projection_source = {"source_id": records[0]["source_id"],
        "digest": records[0]["digest"]}
    for field, replacement in (("task_digest", "sha256:substituted"),
            ("evaluator", "substituted_evaluator")):
        substituted = json.loads(json.dumps(evidence))
        substituted["objective_scores"][0][field] = replacement
        with pytest.raises(DevelopmentalWritebackError,
                match="developmental_history_task_score_lineage_invalid"):
            _developmental_history_interpretation_projection(
                projection_fact, substituted, projection_source)
    substituted_examples = json.loads(json.dumps(evidence))
    substituted_examples["acquisition_examples"][0]["observed_answer"] += 1
    with pytest.raises(DevelopmentalWritebackError,
            match="developmental_history_task_example_binding_invalid"):
        _developmental_history_interpretation_projection(
            projection_fact, substituted_examples, projection_source)
    with pytest.raises(DevelopmentalWritebackError,
            match="developmental_history_source_identity_invalid"):
        _developmental_history_interpretation_projection(projection_fact, evidence,
            {**projection_source, "source_id": "substituted-completed-run"})
    substituted_subject = {**projection_fact,
        "subject": {**projection_fact["subject"], "subject_id": "another-run"}}
    with pytest.raises(DevelopmentalWritebackError,
            match="developmental_history_source_identity_invalid"):
        _developmental_history_interpretation_projection(
            substituted_subject, evidence, projection_source)

    for invocation_request in fake.requests:
        if invocation_request.purpose != \
                "resident_developmental_history_intervention_experiment":
            continue
        assert '"multiplier"' not in invocation_request.prompt
        assert '"offset"' not in invocation_request.prompt
        assert "objective_evaluation" not in invocation_request.prompt

    from sentientos.world_state_board import WorldStateBoardBuilder
    world = WorldStateBoardBuilder().build(records)
    later = cognition.run_tick(snapshot=world, tick_id="family-acquisition-writeback")
    assert later.written_record_id
    admitted = cognition.writeback.store.get(later.written_record_id)
    assert any(fact["payload"].get("objective_task_family") == "integer_affine_prediction"
        for fact in admitted.candidate["selected_facts"])

    # The same admitted family experience can be frozen into the existing A/B
    # replacement context through its real history owner, then reconstructed
    # read-only after restart without carrying it into current evidence.
    from dataclasses import asdict
    from tests.test_developmental_model_replacement_experiment import (
        FakeEndpoint as ReplacementFixtureEndpoint,
        context as replacement_context,
        identity as replacement_identity,
    )
    from sentientos.developmental_model_replacement_experiment import (
        DevelopmentalModelReplacementExperiment, FrozenCausalContext,
    )
    context_fields = asdict(replacement_context())
    for field in ("context_id", "context_digest", "history_record_ids",
            "history_record_digests", "history_record_set_digest",
            "history_projection_payload"):
        context_fields.pop(field)
    succession_context = FrozenCausalContext.create_from_admitted_history(
        writeback=cognition.writeback, history_record_ids=(later.written_record_id,),
        **context_fields)
    assert succession_context.history_record_ids == (later.written_record_id,)
    record_facts = succession_context.history_projection_payload[0]["candidate"][
        "selected_facts"]
    family_history_fact = next(fact for fact in record_facts
        if fact["payload"].get("objective_task_family") == "integer_affine_prediction")
    family_history_score = family_history_fact["payload"]["objective_scores"][0]
    assert family_history_score["evaluator"] == \
        "deterministic_exact_integer_suite_oracle_v2"
    replacement_a = ReplacementFixtureEndpoint(replacement_identity("family-a"))
    replacement_b = ReplacementFixtureEndpoint(replacement_identity("family-b"))
    replacement_root = tmp_path / "family-model-replacement"
    replacement = DevelopmentalModelReplacementExperiment(
        context=succession_context, model_a=replacement_a, model_b=replacement_b,
        artifact_root=replacement_root)
    replacement_run = replacement.run(trial_id="family-history-succession")
    history_prompts = [replacement_a.calls[0]["prompt"],
        replacement_b.calls[0]["prompt"], replacement_a.calls[2]["prompt"]]
    for prompt in history_prompts:
        body = json.loads(prompt)
        assert family_history_fact in body["developmental_history"][0]["candidate"][
            "selected_facts"]
        assert body["current_evidence"] == succession_context.current_projection_payload
    assert json.loads(replacement_a.calls[1]["prompt"])["developmental_history"] == []
    assert json.loads(replacement_b.calls[1]["prompt"])["developmental_history"] == []
    call_counts = (len(replacement_a.calls), len(replacement_b.calls))
    child = subprocess.run([sys.executable, "-c", """
import json, sys
from pathlib import Path
from sentientos.developmental_model_replacement_experiment import ModelReplacementArtifactStore
store = ModelReplacementArtifactStore(Path(sys.argv[1]), read_only=True)
context = store.load_verified_context(sys.argv[2], sys.argv[3])
print(json.dumps({"context_id": context["context_id"],
    "context_digest": context["context_digest"],
    "history_record_ids": context["history_record_ids"],
    "history_record_digests": context["history_record_digests"]}, sort_keys=True))
""", str(replacement_root), succession_context.context_id,
        succession_context.context_digest], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, check=True)
    child_context = json.loads(child.stdout.strip().splitlines()[-1])
    assert child_context["context_id"] == succession_context.context_id
    assert child_context["context_digest"] == succession_context.context_digest
    assert child_context["history_record_ids"] == [later.written_record_id]
    assert child_context["history_record_digests"] == [
        succession_context.history_record_digests[0]]
    restarted_replacement = DevelopmentalModelReplacementExperiment(
        context=succession_context, model_a=replacement_a, model_b=replacement_b,
        artifact_root=replacement_root)
    recovered_replacement_run = restarted_replacement.run(
        trial_id="family-history-succession")
    assert recovered_replacement_run["run_id"] == replacement_run["run_id"]
    assert (len(replacement_a.calls), len(replacement_b.calls)) == call_counts
    recovered_context = restarted_replacement.store.load_verified_context(
        succession_context.context_id, succession_context.context_digest)
    assert recovered_context["history_record_ids"] == [later.written_record_id]
    assert recovered_context["history_record_digests"] == [
        succession_context.history_record_digests[0]]

    # Score provenance must survive the model-replacement -> World-State ->
    # epistemic projection path. These endpoints are deterministic test
    # fixtures; their output is not evidence of learned model behavior.
    class ScoredReplacementFixture(ReplacementFixtureEndpoint):
        def infer(self, **kwargs: Any) -> Mapping[str, Any]:
            self.calls.append(kwargs)
            body = json.loads(kwargs["prompt"])
            descriptor = body["objective_task"]
            examples = []
            for record in body["developmental_history"]:
                for fact in record["candidate"]["selected_facts"]:
                    if fact["payload"].get("objective_task_family") == "integer_affine_prediction":
                        examples = fact["payload"].get("acquisition_examples", [])
            answers = [0 for _ in descriptor["probe_inputs"]]
            if self.history_effect and len(examples) >= 2:
                left, right = examples[:2]
                slope = ((right["observed_answer"] - left["observed_answer"])
                    // (right["probe_input"] - left["probe_input"]))
                offset = left["observed_answer"] - slope * left["probe_input"]
                answers = [slope * value + offset for value in descriptor["probe_inputs"]]
            output_text = json.dumps({"answers": answers}, sort_keys=True, separators=(",", ":"))
            output_digest = experiment_digest({"output": output_text})
            number = len(self.calls)
            return {"status": "admitted_completed", "fallback_occurred": False,
                "request_id": f"request-{self.identity.model_id}-{number}",
                "request_digest": experiment_digest({"request": self.identity.model_id,
                    "number": number}),
                "inference_receipt_id": f"receipt-{self.identity.model_id}-{number}",
                "inference_receipt_digest": experiment_digest({"receipt": self.identity.model_id,
                    "number": number}), "output_digest": output_digest,
                "output_text": output_text, "output_truncated": False,
                "actual_generation_parameters": {"temperature": 0,
                    "max_new_tokens": kwargs["budget"]["max_new_tokens"]}}

    scored_a = ScoredReplacementFixture(replacement_identity("scored-family-a"))
    scored_b = ScoredReplacementFixture(replacement_identity("scored-family-b"),
        history_effect=False)
    scored_experiment = DevelopmentalModelReplacementExperiment(
        context=succession_context, model_a=scored_a, model_b=scored_b,
        artifact_root=tmp_path / "family-model-replacement-scored",
        objective_task=ObjectivePredictionTask(3, 2, 10, (11, 12),
            task_family_id="integer_affine_prediction", requires_task_family_history=True))
    scored_run = scored_experiment.run(trial_id="family-score-contract")
    scored_records = scored_experiment.store.world_state_records(
        run_refs=((scored_run["run_id"], scored_run["run_digest"]),))
    score_contract = scored_records[0]["payload"].get("objective_score_contract")
    assert score_contract is not None
    assert score_contract["evaluator"] == "deterministic_exact_integer_suite_oracle_v2"
    assert score_contract["task_digest"] == scored_experiment.objective_plan[
        "task_descriptor"]["task_digest"]
    assert "multiplier" not in json.dumps(scored_records[0]["payload"])
    assert "offset" not in json.dumps(scored_records[0]["payload"])
    call_counts = (len(scored_a.calls), len(scored_b.calls))
    restarted_scored = DevelopmentalModelReplacementExperiment(
        context=succession_context, model_a=scored_a, model_b=scored_b,
        artifact_root=tmp_path / "family-model-replacement-scored",
        objective_task=ObjectivePredictionTask(3, 2, 10, (11, 12),
            task_family_id="integer_affine_prediction", requires_task_family_history=True))
    recovered_scored_run = restarted_scored.run(trial_id="family-score-contract")
    assert recovered_scored_run["run_id"] == scored_run["run_id"]
    assert recovered_scored_run["run_digest"] == scored_run["run_digest"]
    assert (len(scored_a.calls), len(scored_b.calls)) == call_counts
    assert restarted_scored.store.world_state_records(run_refs=(
        (recovered_scored_run["run_id"], recovered_scored_run["run_digest"]),)) == scored_records

    from sentientos.resident_developmental_writeback import (
        _model_replacement_interpretation_projection,
    )
    substituted_score_record = json.loads(json.dumps(scored_records[0]))
    substituted_score_record["payload"]["objective_score_contract"]["task_digest"] = "sha256:" + "0" * 64
    rejected_projection = _model_replacement_interpretation_projection(
        {"fact_id": scored_records[0]["source_id"]},
        substituted_score_record["payload"], scored_records[0])
    assert "objective_score_contract" not in rejected_projection["payload"]
    assert rejected_projection["payload"]["objective_score_contract_posture"] == \
        "invalid_or_inconsistent"

    scored_world = WorldStateBoardBuilder().build(scored_records)
    scored_tick = cognition.run_tick(snapshot=scored_world,
        tick_id="family-model-replacement-score-writeback")
    assert scored_tick.written_record_id
    scored_admitted = cognition.writeback.store.get(scored_tick.written_record_id)
    scored_fact = next(fact for fact in scored_admitted.candidate["selected_facts"]
        if fact["payload"].get("objective_score_contract") is not None)
    assert scored_fact["payload"]["objective_score_contract"] == score_contract
    assert scored_fact["payload"].get("current_truth") is False
    recovered_cognition, _ = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    prior_request_count = len(fake.requests)
    later_trigger = WorldStateBoardBuilder().build([{
        "source_id": "score-recovery-later-trigger", "source_kind": "capability_registry",
        "subject_id": "later-trigger", "stage": "observation", "disposition": "recorded",
        "observed_at": "2026-10-13T00:00:00+00:00", "payload": {"value": 2}}])
    recovered_tick = recovered_cognition.run_tick(snapshot=later_trigger,
        tick_id="family-model-replacement-score-recovered-cognition")
    assert scored_tick.written_record_id in recovered_tick.prior_record_ids
    recovered_packet = None
    for invocation_request in fake.requests[prior_request_count:]:
        try:
            recovered_context = json.loads(invocation_request.prompt)
        except (TypeError, json.JSONDecodeError):
            continue
        for packet in recovered_context.get("developmental_history", ()):
            if packet.get("record_id") == scored_tick.written_record_id:
                recovered_packet = packet
    assert recovered_packet is not None
    assert scored_fact["fact_id"] in recovered_packet["selected_fact_ids"]
    assert recovered_packet["source_bindings"] == [{
        "digest": scored_records[0]["digest"],
        "kind": "embodiment", "source_id": scored_records[0]["source_id"]}]
    assert recovered_packet["current_truth"] is False
    assert recovered_packet["authority"] is False

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
    state_path = tmp_path / "state" / "composition_state.json"
    before_doctor = {path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / "state").rglob("*") if path.is_file()}
    family_readiness = readiness.inspect_readiness(config_path,
        tmp_path / "no-model-selected.gguf", tmp_path,
        task_family_id="integer_affine_prediction")
    qualified_history = family_readiness["findings"]["developmental_history"]
    assert qualified_history["status"] == "matching_task_family_history_present"
    assert qualified_history["matching_task_family_record_ids"] == [later.written_record_id]
    assert len(qualified_history["matching_task_family_record_digests"]) == 1
    unrelated_readiness = readiness.inspect_readiness(config_path,
        tmp_path / "no-model-selected.gguf", tmp_path,
        task_family_id="unrelated_prediction_family")
    unrelated_history = unrelated_readiness["findings"]["developmental_history"]
    assert unrelated_history["status"] == "awaiting_matching_task_family_history"
    assert unrelated_history["matching_task_family_record_ids"] == []
    assert state_path.read_bytes() == before_doctor["state/composition_state.json"]
    assert {path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / "state").rglob("*") if path.is_file()} == before_doctor

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
    assert all(item["schema_version"] == "sentientos.resident_cognition_observation:v7"
        for item in conditions)
    # This fixture uses genuinely unlinked historical-compatible invocation
    # receipts; the new observation version must retain that empty linkage.
    assert all(item["resource_allocation_digest"] is None
        and item["resource_attempt_id"] is None
        and item["resource_consumption_receipt_digests"] == []
        and item["resource_linkage_digest"] is None for item in conditions)
    family_fact = records[0]["payload"]
    source_fact = next(fact for fact in world.facts
        if fact.source.source_id == records[0]["source_id"])
    assert source_fact.fact_id not in present["current_fact_ids"]
    assert source_fact.fact_id not in withheld["current_fact_ids"]
    assert source_fact.fact_id not in restored["current_fact_ids"]
    assert later.written_record_id in present["retrieved_record_ids"]
    assert later.written_record_id not in withheld["retrieved_record_ids"]
    assert later.written_record_id in restored["retrieved_record_ids"]
    assert present["developmental_history_selection"]["retrieval_policy_id"] == \
        "task_family_probe_overlap_then_recency_fill:v2"
    assert present["developmental_history_selection"]["task_family_id"] == \
        "integer_affine_prediction"
    assert withheld["developmental_history_selection"]["treatment"] == "withheld"
    assert withheld["developmental_history_selection"]["selected_records"] == []
    assert withheld["developmental_history_selection"]["omitted_records"] == \
        present["developmental_history_selection"]["available_records"]
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
    assert progression["episodes_with_admitted_task_family_history"] == 2
    assert progression["matching_task_family_history_retrieved_for_all_episodes"] is False
    assert progression["episodes"][0]["task_family_history_record_ids"] == []
    assert progression["episodes"][1]["task_family_history_record_ids"] == [
        later.written_record_id]
    assert set(progression["episodes"][2]["task_family_history_record_ids"]) == {
        later.written_record_id, feedback.written_record_id}
    for episode in progression["episodes"][1:]:
        relevant = episode["task_family_history_record_ids"]
        conditions_by_id = {condition["condition_id"]: condition
            for condition in episode["conditions"]}
        assert conditions_by_id["history_present"][
            "task_family_retrieved_record_ids"] == relevant
        assert conditions_by_id["history_withheld"][
            "task_family_retrieved_record_ids"] == []
        assert conditions_by_id["history_restored"][
            "task_family_retrieved_record_ids"] == relevant
    for episode in progression["episodes"]:
        counts = {condition["condition_id"]: condition["correct_count"]
            for condition in episode["conditions"]}
        contrast = episode["score_contrasts"]
        assert contrast["probe_denominator"] == len(episode["task_family"]["probe_inputs"])
        assert contrast["history_present_minus_withheld_correct_count"] == (
            counts["history_present"] - counts["history_withheld"])
        assert contrast["history_restored_minus_present_correct_count"] == (
            counts["history_restored"] - counts["history_present"])
        assert contrast["learning_established"] is False
    assert progression["actual_nonsynthetic_inference_verified"] is False
    assert progression["independent_backend_observation"] is False
    assert progression["execution_evidence_scope"] == (
        "authenticated_owner_receipts_not_independent_backend_observation")
    assert all(condition["execution_evidence_posture"] ==
        "receipt_does_not_establish_backend_entry"
        for condition in progression["episodes"][1]["conditions"])
    assert progression["learning_established"] is False
    cost = progression["execution_cost_summary"]
    assert cost["condition_count"] == 9
    assert cost["invocation_receipt_identity_count"] == 9
    assert cost["verified_completed_inference_count"] == 0
    assert cost["scoreable_condition_count"] == 9
    assert cost["receipt_linked_resource_condition_count"] == 0
    assert cost["ledger_reconciled_consumption_count"] is None
    assert cost["cpu_time_ms"] is cost["gpu_time_ms"] is cost["energy_joules"] is None
    assert cost["generated_token_count"] is None
    for episode in progression["episodes"]:
        expected_ids = episode["history_record_ids"]
        assert episode["conditions"][0]["retrieved_record_ids"] == expected_ids
        assert episode["conditions"][1]["retrieved_record_ids"] == []
        assert episode["conditions"][2]["retrieved_record_ids"] == expected_ids
        assert episode["conditions"][0]["retrieved_record_digests"] == \
            episode["history_record_digests"]
        assert episode["conditions"][2]["retrieved_record_digests"] == \
            episode["history_record_digests"]
    invocation_count_before_reconstruction = len(fake.requests)
    recovered_owner, _ = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    recovered_progression = recovered_owner.verified_objective_task_family_progression(
        request_refs=(
            ("family-acquisition", request["request_digest"]),
            ("family-transfer", staged["request_digest"]),
            ("family-continued-transfer", continued_request["request_digest"])))
    assert recovered_progression == progression
    assert len(fake.requests) == invocation_count_before_reconstruction
    child_progression = _reconstruct_progression_in_child(tmp_path, fake.receipts, [
        ("family-acquisition", request["request_digest"]),
        ("family-transfer", staged["request_digest"]),
        ("family-continued-transfer", continued_request["request_digest"])])
    assert child_progression == progression
    assert len(fake.requests) == invocation_count_before_reconstruction


def test_objective_staging_arguments_can_require_exact_task_family_history() -> None:
    from scripts.stage_resident_objective_intervention import objective_task_from_arguments

    task = objective_task_from_arguments(multiplier=3, offset=2,
        probes=[10, 11, 12], task_family_id="integer_affine_prediction",
        require_task_family_history=True)
    assert task.public_descriptor()["task_family_id"] == "integer_affine_prediction"
    assert task.public_descriptor()["requires_task_family_history"] is True
    optional = objective_task_from_arguments(multiplier=3, offset=2,
        probes=[10, 11, 12])
    assert optional.public_descriptor().get("task_family_id") is None
    with pytest.raises(ValueError, match="requires --task-family-id"):
        objective_task_from_arguments(multiplier=3, offset=2,
            probes=[10, 11, 12], require_task_family_history=True)


def test_incorrect_family_experience_remains_adverse_through_writeback_and_transfer(
        tmp_path: Path) -> None:
    """A family match is relevant evidence, not an implicit success claim."""
    fake = SessionBoundFakeInvoker()
    fake.active_model_identity = {"provider": "fixture", "model": "adverse-correction-family"}
    fake.objective_mode = "degrade"
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    cognition, _ = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    assert cognition.run_tick(snapshot=snapshot(), tick_id="adverse-family-seed").written_record_id

    from sentientos.codex_task_authority_admission import (
        RESIDENT_EPISTEMIC_STATE_MUTATION,
        RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION,
    )
    from sentientos.resident_epistemic_development import (
        EpistemicDevelopmentConfig, EpistemicDevelopmentRule,
        ResidentEpistemicDevelopmentRuntime,
    )
    from sentientos.resident_epistemic_state_mutation import (
        ResidentEpistemicStateMutationController,
    )
    epistemic_root = tmp_path / "epistemics"
    epistemic_ledger = AdmissionLedger(tmp_path / "epistemic-admissions.json")
    epistemic_definitions = {RESIDENT_EPISTEMIC_STATE_MUTATION:
        RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION}
    epistemic_owner = PersistentEpistemicStateOwner(
        epistemic_root, allowed_namespaces=("operator",))
    proposition = make_proposition(namespace="operator",
        subject="task_family:integer_affine_prediction", predicate="history_effect",
        object_value="Historical examples affect held-out task correctness",
        polarity="positive", qualifiers={"campaign": "adverse-corrective-history"},
        temporal_scope={"kind": "longitudinal_task_family"},
        context_scope={"task_family_id": "integer_affine_prediction"},
        proposition_class="causal_hypothesis")
    epistemic_owner.register_proposition(proposition)
    rule = EpistemicDevelopmentRule("verified-task-family-correction",
        proposition.proposition_id, proposition.proposition_digest,
        {"source_kind": "embodiment",
            "subject_kind": "developmental_history_intervention_experiment"},
        "supports", "unknown_dependency", "bounded_fixture_outcome")
    def current_admission_sequence() -> int:
        return epistemic_ledger.current_sequence()
    epistemic_controller = ResidentEpistemicStateMutationController(
        owner=epistemic_owner,
        admission_verifier=RuntimeAdmissionVerifier(
            definitions=epistemic_definitions, ledger=epistemic_ledger),
        current_sequence=current_admission_sequence,
        receipt_root=tmp_path / "epistemic-mutation-receipts")
    epistemic_runtime = ResidentEpistemicDevelopmentRuntime(
        config=EpistemicDevelopmentConfig(True, 1, 1, (rule,), ("operator",)),
        owner=epistemic_owner, mutation_controller=epistemic_controller,
        admission_authority=RuntimeAdmissionAuthority(
            definitions=epistemic_definitions, ledger=epistemic_ledger),
        admission_ledger=epistemic_ledger)

    def admit_outcome(run: Mapping[str, Any], tick: int):
        binding = cognition.experiments.objective_task_family_evidence_binding(
            run_id=str(run["run_id"]), expected_run_digest=str(run["run_digest"]),
            proposition_id=proposition.proposition_id)
        event_time = max(datetime.fromisoformat(item["observed_at"].replace("Z", "+00:00"))
            for item in run["conditions"])
        feedback = epistemic_runtime.process_verified_task_family_run(
            experiment_store=cognition.experiments, run_id=str(run["run_id"]),
            expected_run_digest=str(run["run_digest"]), rule_id=rule.rule_id,
            tick=tick, recorded_at=(event_time + timedelta(seconds=1)).isoformat())
        assert binding in epistemic_owner.bindings(proposition.proposition_id)
        return binding, feedback

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
    adverse_binding, adverse_admission = admit_outcome(run, 1)
    assert adverse_binding.evidence_relation == "contradicts"
    assert adverse_admission.status == "state_advanced"
    assert epistemic_owner.current_state(proposition.proposition_id).stance == \
        "provisionally_contradicted"
    adverse_projection = epistemic_owner.cognitive_projection(max_states=1, current_tick=2)
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
    assert retained_fact["payload"]["objective_scores"][0]["evaluator"] == \
        "deterministic_exact_integer_suite_oracle_v2"

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
    transfer_binding, transfer_admission = admit_outcome(transfer, 2)
    assert transfer_binding.evidence_relation == "contradicts"
    assert transfer_admission.status == "state_advanced"
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
    progression = cognition.verified_objective_task_family_progression(request_refs=(
        (staged["request_id"], staged["request_digest"]),
        (later_request["request_id"], later_request["request_digest"])))
    assert progression["episodes_with_admitted_task_family_history"] == 1
    assert progression["matching_task_family_history_retrieved_for_all_episodes"] is False
    acquisition_episode, transfer_episode = progression["episodes"]
    assert acquisition_episode["task_family_history_record_ids"] == []
    assert acquisition_episode["task_family_history_relevance_posture"] == \
        "no_matching_admitted_task_family_history"
    assert transfer_episode["task_family_history_record_ids"] == [retained.record_id]
    assert transfer_episode["task_family_history_record_digests"] == [retained.record_digest]
    assert transfer_episode["score_contrasts"][
        "history_present_minus_withheld_correct_count"] == -2
    assert transfer_episode["score_contrasts"][
        "history_restored_minus_present_correct_count"] == 0
    assert transfer_episode["score_contrasts"]["probe_denominator"] == 2
    assert transfer_episode["score_contrasts"]["learning_established"] is False
    transfer_retrieval = {condition["condition_id"]:
        condition["task_family_retrieved_record_ids"]
        for condition in transfer_episode["conditions"]}
    assert transfer_retrieval["history_present"] == [retained.record_id]
    assert transfer_retrieval["history_withheld"] == []
    assert transfer_retrieval["history_restored"] == [retained.record_id]

    # Continue chronologically: a later correct episode is admitted after the
    # adverse one, then a fresh owner reconstructs both before a distinct task.
    fake.objective_mode = "no_difference"
    corrective_task = ObjectivePredictionTask(0, 23, 11, (12,),
        task_family_id="integer_affine_prediction", requires_task_family_history=True)
    corrective_path, corrective_staged, corrective_eligible = stage_request(
        config_path=config_path, request_id="adverse-then-corrective-episode",
        task=corrective_task)
    assert corrective_path.exists() and corrective_eligible >= 1
    corrective_request = load_objective_request(tmp_path / "state")
    assert corrective_request is not None
    corrective_result = cognition.run_objective_intervention_once(snapshot=snapshot(11),
        tick_id="adverse-then-corrective-episode",
        objective_task=objective_task_for_request(corrective_request),
        request_id=corrective_request["request_id"],
        request_digest=corrective_request["request_digest"])
    corrective_run = cognition.experiments.load_run(
        corrective_result.changed_cognition_measurement_id)
    corrective_binding, corrective_admission = admit_outcome(corrective_run, 3)
    assert corrective_binding.evidence_relation == "contextualizes"
    assert corrective_admission.updated_proposition_count == 0
    assert epistemic_owner.current_state(proposition.proposition_id).stance == \
        "provisionally_contradicted"
    corrective_scores = {row["condition_id"]: row["score"]
        for row in corrective_run["objective_scores"]}
    assert corrective_scores["history_present"]["correct_count"] == 2
    assert corrective_scores["history_withheld"]["correct_count"] == 2
    corrective_world = WorldStateBoardBuilder().build(cognition.experiments.world_state_records(
        run_refs=((corrective_run["run_id"], corrective_run["run_digest"]),)))
    corrective_feedback = cognition.run_tick(snapshot=corrective_world,
        tick_id="corrective-episode-feedback")
    assert corrective_feedback.written_record_id
    corrective_record = cognition.writeback.store.get(corrective_feedback.written_record_id)
    corrective_fact = next(fact for fact in corrective_record.candidate["selected_facts"]
        if fact["payload"].get("objective_task_family") == "integer_affine_prediction")
    assert [item["evaluator_correct"] for item in
        corrective_fact["payload"]["acquisition_examples"]] == [True, True]
    assert corrective_record.record_id != retained.record_id

    # Reconstruct owner state and retrieve the corrective and adverse episodes
    # in source chronology; the evaluator's target is held fixed in this fixture.
    # This fixture variant fits the newest two admitted examples while still
    # retaining the earlier adverse record in the same chronological prompt.
    fake.objective_mode = "derive_from_latest_admitted_family"
    restarted, _ = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    final_task = ObjectivePredictionTask(0, 23, 13, (14,),
        task_family_id="integer_affine_prediction", requires_task_family_history=True)
    final_path, final_staged, final_eligible = stage_request(config_path=config_path,
        request_id="post-correction-heldout-episode", task=final_task)
    assert final_path.exists() and final_eligible >= 2
    final_request = load_objective_request(tmp_path / "state")
    assert final_request is not None
    final_result = restarted.run_objective_intervention_once(snapshot=snapshot(13),
        tick_id="post-correction-heldout-episode",
        objective_task=objective_task_for_request(final_request),
        request_id=final_request["request_id"], request_digest=final_request["request_digest"])
    final_run = restarted.experiments.load_run(final_result.changed_cognition_measurement_id)
    favorable_binding, favorable_admission = admit_outcome(final_run, 4)
    assert favorable_binding.evidence_relation == "supports"
    assert favorable_admission.status == "state_advanced"
    assert epistemic_owner.current_state(proposition.proposition_id).stance == "contested"
    final_scores = {row["condition_id"]: row["score"]
        for row in final_run["objective_scores"]}
    final_prompt = next(json.loads(request.prompt) for request in reversed(fake.requests)
        if request.purpose == "resident_developmental_history_intervention_experiment"
        and request.linkage.get("condition_id") == "history_present")
    history_record_order = [packet.get("record_id")
        for packet in final_prompt["developmental_history"]]
    assert history_record_order.index(retained.record_id) < \
        history_record_order.index(corrective_record.record_id)
    assert final_scores["history_present"]["correct_count"] == 2
    assert final_scores["history_withheld"]["correct_count"] == 0
    assert final_scores["history_restored"]["correct_count"] == 2
    final_conditions = final_run["conditions"]
    assert corrective_record.record_id in final_conditions[0]["retrieved_record_ids"]
    assert retained.record_id in final_conditions[0]["retrieved_record_ids"]
    assert final_conditions[1]["retrieved_record_ids"] == []
    final_progression = restarted.verified_objective_task_family_progression(request_refs=(
        (staged["request_id"], staged["request_digest"]),
        (later_request["request_id"], later_request["request_digest"]),
        (corrective_request["request_id"], corrective_request["request_digest"]),
        (final_request["request_id"], final_request["request_digest"])))
    assert final_progression["episode_count"] == 4
    assert final_progression["distinct_probe_sets"] is True
    assert final_progression["episodes"][2]["task_family_history_record_ids"] == [retained.record_id]
    assert set(final_progression["episodes"][3]["task_family_history_record_ids"]) == {
        corrective_record.record_id, retained.record_id}
    assert final_progression["episodes"][3]["score_contrasts"][
        "history_present_minus_withheld_correct_count"] == 2
    assert final_progression["learning_established"] is False
    assert final_progression["performance_improvement_established"] is False

    # Rebuild the epistemic owner and admission controller independently. Both
    # adverse source digests, the contextual tie, and the favorable source
    # digest remain in the same proposition history; the favorable result does
    # not erase the earlier contradiction.
    recovered_epistemics = PersistentEpistemicStateOwner(
        epistemic_root, allowed_namespaces=("operator",))
    recovered_controller = ResidentEpistemicStateMutationController(
        owner=recovered_epistemics,
        admission_verifier=RuntimeAdmissionVerifier(
            definitions=epistemic_definitions, ledger=epistemic_ledger),
        current_sequence=current_admission_sequence,
        receipt_root=tmp_path / "epistemic-mutation-receipts")
    recovered_runtime = ResidentEpistemicDevelopmentRuntime(
        config=EpistemicDevelopmentConfig(True, 1, 1, (rule,), ("operator",)),
        owner=recovered_epistemics, mutation_controller=recovered_controller,
        admission_authority=RuntimeAdmissionAuthority(
            definitions=epistemic_definitions, ledger=epistemic_ledger),
        admission_ledger=epistemic_ledger)
    assert recovered_controller.verify_receipts()["status"] == "verified"
    recovered_state = recovered_epistemics.current_state(proposition.proposition_id)
    assert recovered_state is not None and recovered_state.stance == "contested"
    recovered_bindings = recovered_epistemics.bindings(proposition.proposition_id)
    assert {item.source_digest for item in recovered_bindings} == {
        run["run_digest"], transfer["run_digest"], corrective_run["run_digest"],
        final_run["run_digest"]}
    assert {item.evidence_relation for item in recovered_bindings} == {
        "contradicts", "contextualizes", "supports"}
    assert len(recovered_epistemics.update_events(proposition.proposition_id)) == 3
    trace = recovered_runtime.trace_proposition(
        proposition_id=proposition.proposition_id,
        reconstructed_at="2026-10-15T00:00:00+00:00", max_events=3,
        cognitive_tick=5)
    assert len(trace["mutation_receipts"]) == 7
    assert trace["resulting_prior_projection"]["state_digests"] == [
        recovered_state.state_digest]
    assert {row["source_digest"] for row in trace["evidence"]} == {
        run["run_digest"], transfer["run_digest"], corrective_run["run_digest"],
        final_run["run_digest"]}

    # Reconstruct the proposition owner, mutation controller, admission
    # ledger, and trace in a distinct interpreter process.
    child_trace_script = r'''import json, sys
from pathlib import Path
from sentientos.codex_task_authority_admission import (
    RESIDENT_EPISTEMIC_STATE_MUTATION,
    RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION,
)
from sentientos.persistent_epistemic_state import (
    PersistentEpistemicStateOwner, make_proposition,
)
from sentientos.resident_epistemic_development import (
    EpistemicDevelopmentConfig, EpistemicDevelopmentRule,
    ResidentEpistemicDevelopmentRuntime,
)
from sentientos.resident_epistemic_state_mutation import (
    ResidentEpistemicStateMutationController,
)
from sentientos.runtime_admission import (
    AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier,
)
root = Path(sys.argv[1])
parent = Path(sys.argv[2])
ledger = AdmissionLedger(parent / "epistemic-admissions.json")
definitions = {RESIDENT_EPISTEMIC_STATE_MUTATION:
    RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION}
owner = PersistentEpistemicStateOwner(root, allowed_namespaces=("operator",))
proposition = make_proposition(namespace="operator",
    subject="task_family:integer_affine_prediction", predicate="history_effect",
    object_value="Historical examples affect held-out task correctness",
    polarity="positive", qualifiers={"campaign": "adverse-corrective-history"},
    temporal_scope={"kind": "longitudinal_task_family"},
    context_scope={"task_family_id": "integer_affine_prediction"},
    proposition_class="causal_hypothesis")
rule = EpistemicDevelopmentRule("verified-task-family-correction",
    proposition.proposition_id, proposition.proposition_digest,
    {"source_kind": "embodiment",
        "subject_kind": "developmental_history_intervention_experiment"},
    "supports", "unknown_dependency", "bounded_fixture_outcome")
controller = ResidentEpistemicStateMutationController(owner=owner,
    admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger),
    current_sequence=ledger.current_sequence,
    receipt_root=parent / "epistemic-mutation-receipts")
runtime = ResidentEpistemicDevelopmentRuntime(
    config=EpistemicDevelopmentConfig(True, 1, 1, (rule,), ("operator",)),
    owner=owner, mutation_controller=controller,
    admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
    admission_ledger=ledger)
state = owner.current_state(proposition.proposition_id)
trace = runtime.trace_proposition(proposition_id=proposition.proposition_id,
    reconstructed_at="2026-10-15T00:00:01+00:00", max_events=3, cognitive_tick=5)
print(json.dumps({"stance": state.stance if state else None,
    "state_digest": state.state_digest if state else None,
    "source_digests": sorted(row["source_digest"] for row in trace["evidence"]),
    "event_count": len(trace["events"]),
    "receipt_count": len(trace["mutation_receipts"]),
    "projection_state_digests": trace["resulting_prior_projection"]["state_digests"]}))
'''
    child_trace = subprocess.run([sys.executable, "-c", child_trace_script,
        str(epistemic_root), str(tmp_path)], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, check=True, timeout=30)
    process_trace = json.loads(child_trace.stdout)
    assert process_trace["stance"] == "contested"
    assert process_trace["state_digest"] == recovered_state.state_digest
    assert process_trace["source_digests"] == sorted({
        run["run_digest"], transfer["run_digest"], corrective_run["run_digest"],
        final_run["run_digest"]})
    assert process_trace["event_count"] == 3
    assert process_trace["receipt_count"] == 7
    assert process_trace["projection_state_digests"] == [recovered_state.state_digest]

    class EpistemicAwareFixtureInvoker(FakeInvoker):
        """Fixture consumer reacts to evidence posture, without a treatment label."""
        def __init__(self) -> None:
            super().__init__()
            self.receipts = {}

        def invoke(self, request, *, persist, include_output_in_receipt,
                resource_context=None):
            if request.purpose == "resident_developmental_retrieval_cognition":
                body = json.loads(request.prompt)
                state = body["prior_epistemic_state"]
                packet = next(item for item in state["semantic_packets"]
                    if item["proposition"]["proposition_id"] == proposition.proposition_id)
                has_support = bool(packet["supporting_evidence"])
                has_contradiction = bool(packet["contradicting_evidence"])
                if has_support and has_contradiction:
                    self.lesson_statement = (
                        "Outcomes conflict; defer a single directional recommendation.")
                    self.lesson_uncertainty = "high"
                    self.lesson_uncertainty_rationale = (
                        "Both supporting and adverse task-family outcomes remain active.")
                elif has_contradiction:
                    self.lesson_statement = (
                        "Retain the adverse result within its measured task-family scope.")
                    self.lesson_uncertainty = "medium"
                    self.lesson_uncertainty_rationale = (
                        "Only adverse evidence is present in the prior position.")
            receipt = super().invoke(request, persist=persist,
                include_output_in_receipt=include_output_in_receipt,
                resource_context=resource_context)
            self.receipts[receipt.receipt_id] = receipt
            return receipt

    updated_projection = recovered_epistemics.cognitive_projection(
        max_states=1, current_tick=5)
    assert updated_projection is not None
    later_outputs = []
    for label, projection in (("adverse-only", adverse_projection),
            ("corrected-contested", updated_projection)):
        consumer_invoker = EpistemicAwareFixtureInvoker()
        consumer, _ = owner(tmp_path / ("later-cognition-" + label),
            invoker=consumer_invoker)
        consumer_result = consumer.run_tick(snapshot=snapshot(), tick_id=label,
            prior_epistemic_state=projection)
        assert consumer_result.written_record_id
        consumer_request = next(item for item in reversed(consumer_invoker.requests)
            if item.purpose == "resident_developmental_retrieval_cognition")
        consumer_body = json.loads(consumer_request.prompt)
        delivered_packet = next(item for item in consumer_body[
            "prior_epistemic_state"]["semantic_packets"]
            if item["proposition"]["proposition_id"] == proposition.proposition_id)
        consumer_record = consumer.writeback.store.get(consumer_result.written_record_id)
        # The evaluator depends only on evidence arrays in the delivered packet.
        expected_uncertainty = ("high" if delivered_packet["supporting_evidence"]
            and delivered_packet["contradicting_evidence"] else "medium")
        assert consumer_invoker.lesson_uncertainty == expected_uncertainty
        consumer_receipt = next(item for item in consumer_invoker.receipts.values()
            if item.request["request_id"] == consumer_request.request_id)
        assert consumer_receipt.output_text is not None
        evaluated_output = json.loads(consumer_receipt.output_text)
        assert evaluated_output["uncertainty"] == expected_uncertainty
        assert consumer_receipt.output_digest == digest_payload({
            "output": consumer_receipt.output_text})
        later_outputs.append((evaluated_output["recommendation"],
            evaluated_output["uncertainty"],
            delivered_packet["state"]["state_digest"]))
    assert later_outputs[0][1] == "medium"
    assert later_outputs[1][1] == "high"
    assert later_outputs[0][0] != later_outputs[1][0]
    assert later_outputs[1][2] == recovered_state.state_digest

    from sentientos.goal_executor import ExecutorState
    from sentientos.goal_planner import GoalPlanner
    from sentientos.goal_graph import Goal, GoalGraph
    from sentientos.risk_budget import RiskBudget
    from sentientos.work_allocator import AllocationDecision, allocate_goals
    planning_graph = GoalGraph(schema_version=1, goals=(Goal(
        "integer-affine-followup", "continue the measured task family", 1.0, 1,
        (), "check_forge_last_run_ok", 2, 1,
        (f"epistemic_proposition:{proposition.proposition_id}",), True),))
    planning_allocation = AllocationDecision(selected=("integer-affine-followup",),
        deferred=(), selected_reasons=(), budget_summary={})
    planning_budget = RiskBudget(router_k_max=12, router_m_max=12,
        forge_max_files_changed=10)
    planning_state = ExecutorState(repo_root=tmp_path / "goal-planning",
        created_at="2026-10-15T00:00:00Z", context="measured-task-family",
        operating_mode="normal", quarantine_active=False, allow_mutation=True,
        goal_graph_hash="beef" * 16, allocation_id="followup",
        risk_budget=planning_budget, prior_epistemic_projection=updated_projection)
    planner = GoalPlanner(repo_root=planning_state.repo_root)
    unconditioned_plan = planner.build_plan(planning_allocation,
        ExecutorState(repo_root=planning_state.repo_root,
            created_at=planning_state.created_at, context=planning_state.context,
            operating_mode=planning_state.operating_mode,
            quarantine_active=planning_state.quarantine_active,
            allow_mutation=planning_state.allow_mutation,
            goal_graph_hash=planning_state.goal_graph_hash,
            allocation_id=planning_state.allocation_id,
            risk_budget=planning_state.risk_budget), planning_graph)
    evidence_conditioned_plan = planner.build_plan(planning_allocation,
        planning_state, planning_graph)
    assert any(item.kind == "forge_apply" for item in unconditioned_plan.tasks)
    assert not any(item.kind == "forge_apply" for item in evidence_conditioned_plan.tasks)
    assert ("integer-affine-followup", "forge_apply",
        "epistemic_position_requires_review") in {
            (item.goal_id, item.kind, item.reason)
            for item in evidence_conditioned_plan.omissions}
    assert f"epistemic_projection_digest={updated_projection.projection_digest}" \
        in evidence_conditioned_plan.context
    assert evidence_conditioned_plan.plan_id != unconditioned_plan.plan_id
    allocation_graph = GoalGraph(schema_version=1, goals=(
        Goal("history-sensitive", "mapped goal", 1.0, 10, (), "rule", 2, 1,
            (f"epistemic_proposition:{proposition.proposition_id}",), True),
        Goal("independent", "independent goal", 1.0, 1, (), "rule", 2, 1,
            ("integrity",), True)))
    allocation_budget = RiskBudget(router_k_max=2, router_m_max=2)
    base_allocation = allocate_goals(graph=allocation_graph, budget=allocation_budget,
        operating_mode="normal", integrity_pressure_level=0,
        quarantine_active=False, posture="balanced")
    evidence_allocation = allocate_goals(graph=allocation_graph,
        budget=allocation_budget, operating_mode="normal",
        integrity_pressure_level=0, quarantine_active=False, posture="balanced",
        prior_epistemic_projection=updated_projection)
    assert base_allocation.selected == ("history-sensitive",)
    assert evidence_allocation.selected == ("independent",)
    assert any(item.goal_id == "history-sensitive"
        and item.reason == "epistemic_applicability_unresolved"
        for item in evidence_allocation.deferred)
    assert evidence_allocation.selected_reasons[0][
        "epistemic_projection_digest"] == updated_projection.projection_digest


def test_admitted_family_example_supports_second_heldout_episode_after_restart(
        tmp_path: Path) -> None:
    """Fixture-only episode chain: acquired examples are reused after owner reconstruction."""
    from scripts.stage_resident_objective_intervention import stage_request

    fake = InstallationCustodyFakeInvoker()
    fake.active_model_identity = {"provider": "fixture", "model": "episode-model"}
    _bind_fixture_installation_custody(tmp_path, fake)
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    config_path = tmp_path / "objective-config.json"
    config_path.write_text(json.dumps({"schema": CONFIG_SCHEMA, "enabled": True,
        "history_root": str(tmp_path / "history"), "state_root": str(tmp_path / "state"),
        "allowed_source_kinds": ["capability_registry", "embodiment"],
        "max_selected_facts": 16, "max_retrieved_records": 4,
        "comparison_enabled": True}), encoding="utf-8")
    cognition, model = owner(tmp_path, comparison=True, invoker=fake,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
    assert cognition.run_tick(snapshot=snapshot(), tick_id="episode-seed").written_record_id

    acquisition_task = ObjectivePredictionTask(3, 2, 7, (8, 9),
        task_family_id="integer_affine_prediction")
    _, acquisition_request, _ = stage_request(config_path=config_path,
        request_id="episode-acquisition", task=acquisition_task)
    acquisition = cognition.run_objective_intervention_once(snapshot=snapshot(),
        tick_id="episode-acquisition", objective_task=acquisition_task,
        request_id="episode-acquisition", request_digest=str(acquisition_request["request_digest"]))
    acquisition_run = cognition.experiments.load_run(
        str(acquisition.changed_cognition_measurement_id))
    source_records = cognition.experiments.world_state_records(
        run_refs=((acquisition_run["run_id"], acquisition_run["run_digest"]),))
    source_world = WorldStateBoardBuilder().build(source_records)
    execution_evidence = source_records[0]["payload"]
    assert execution_evidence["execution_evidence_posture"] == (
        "one_or_more_conditions_simulated_or_no_backend_entry")
    assert execution_evidence["execution_evidence_scope"] == (
        "authenticated_owner_receipt_not_independent_backend_observation")
    assert execution_evidence["independent_backend_observation"] is False
    assert len(execution_evidence["execution_evidence_conditions"]) == 3
    assert all(item["receipt_identity_verified"] is True for item in
        execution_evidence["execution_evidence_conditions"])
    assert all(item["posture"] == "receipt_reports_simulation_or_no_backend_entry"
        for item in execution_evidence["execution_evidence_conditions"])
    feedback = cognition.run_tick(snapshot=source_world, tick_id="episode-acquisition-feedback")
    assert feedback.written_record_id
    admitted = cognition.writeback.store.get(feedback.written_record_id)
    family_fact = next(fact for fact in admitted.candidate["selected_facts"]
        if fact["payload"].get("objective_task_family") == "integer_affine_prediction")
    assert family_fact["payload"]["acquisition_examples"]
    assert family_fact["payload"]["active_model_identity"] == fake.active_model_identity
    assert family_fact["payload"]["active_model_identity_digest"]
    from sentientos.resident_developmental_cognition import _task_family_history_examples
    projected_examples = _task_family_history_examples(admitted.candidate,
        task_family_id="integer_affine_prediction")
    assert len(projected_examples) == 1
    assert projected_examples[0]["source_fact_id"] == family_fact["fact_id"]
    assert projected_examples[0]["source_active_model_identity"] == fake.active_model_identity
    assert projected_examples[0]["source_active_model_identity_digest"] == \
        family_fact["payload"]["active_model_identity_digest"]
    assert projected_examples[0]["model_identity_binding_posture"] == \
        "protocol_bound_source_identity"
    assert projected_examples[0]["applicability_posture"] == \
        "target_model_identity_unbound"
    assert projected_examples[0]["examples"] == [{
        "probe_input": row["probe_input"], "observed_answer": row["observed_answer"],
        "evaluator_correct": row["evaluator_correct"]}
        for row in family_fact["payload"]["acquisition_examples"]]
    assert projected_examples[0]["execution_evidence_scope"] == (
        "authenticated_owner_receipt_not_independent_backend_observation")
    assert projected_examples[0]["execution_evidence_posture"] == (
        "one_or_more_conditions_simulated_or_no_backend_entry")
    assert projected_examples[0]["independent_backend_observation"] is False
    assert projected_examples[0]["resource_context"]["posture"] == (
        "unknown_missing_or_unbound_lineage")
    assert [item["condition_id"] for item in
        projected_examples[0]["execution_evidence_conditions"]] == [
            "history_present", "history_withheld", "history_restored"]
    assert [item["invocation_receipt_id"] for item in
        projected_examples[0]["execution_evidence_conditions"]] == [
            item["inference_receipt_id"] for item in family_fact["payload"]["conditions"]]
    assert [item["invocation_receipt_digest"] for item in
        projected_examples[0]["execution_evidence_conditions"]] == [
            item["inference_receipt_digest"] for item in family_fact["payload"]["conditions"]]
    assert all(item["posture"] == "receipt_reports_simulation_or_no_backend_entry"
        for item in projected_examples[0]["execution_evidence_conditions"])
    # Contradictory lineage must not survive as a cognition packet even if the
    # surrounding task-family label and example values still look plausible.
    import copy
    mismatched_score = copy.deepcopy(admitted.candidate)
    mismatched_family_fact = next(fact for fact in mismatched_score["selected_facts"]
        if fact["fact_id"] == family_fact["fact_id"])
    mismatched_family_fact["payload"]["acquisition_examples"][0][
        "source_score_digest"] = "sha256:" + "f" * 64
    assert _task_family_history_examples(mismatched_score,
        task_family_id="integer_affine_prediction") == []
    substituted_receipt = copy.deepcopy(admitted.candidate)
    substituted_fact = next(fact for fact in substituted_receipt["selected_facts"]
        if fact["fact_id"] == family_fact["fact_id"])
    substituted_fact["payload"]["conditions"][0]["inference_receipt_digest"] = "f" * 64
    assert _task_family_history_examples(substituted_receipt,
        task_family_id="integer_affine_prediction") == []
    overstated_backend = copy.deepcopy(admitted.candidate)
    overstated_fact = next(fact for fact in overstated_backend["selected_facts"]
        if fact["fact_id"] == family_fact["fact_id"])
    overstated_fact["payload"]["independent_backend_observation"] = True
    assert _task_family_history_examples(overstated_backend,
        task_family_id="integer_affine_prediction") == []
    substituted_source = copy.deepcopy(admitted.candidate)
    substituted_family_fact = next(fact for fact in substituted_source["selected_facts"]
        if fact["fact_id"] == family_fact["fact_id"])
    substituted_family_fact["source"]["digest"] = "e" * 64
    assert _task_family_history_examples(substituted_source,
        task_family_id="integer_affine_prediction") == []
    substituted_model_identity = copy.deepcopy(admitted.candidate)
    substituted_model_fact = next(fact for fact in substituted_model_identity["selected_facts"]
        if fact["fact_id"] == family_fact["fact_id"])
    substituted_model_fact["payload"]["active_model_identity"]["model_id"] = "other-model"
    assert _task_family_history_examples(substituted_model_identity,
        task_family_id="integer_affine_prediction")[0][
            "model_identity_binding_posture"] == "source_model_identity_unbound"
    bound_model_identity = copy.deepcopy(admitted.candidate)
    bound_model_fact = next(fact for fact in bound_model_identity["selected_facts"]
        if fact["fact_id"] == family_fact["fact_id"])
    identity = {"provider": "fixture", "model": "fixture-model"}
    from sentientos.resident_developmental_cognition import _digest as cognition_digest
    bound_model_fact["payload"]["active_model_identity"] = identity
    bound_model_fact["payload"]["active_model_identity_digest"] = cognition_digest(identity)
    bound_projection = _task_family_history_examples(bound_model_identity,
        task_family_id="integer_affine_prediction")[0]
    assert bound_projection["source_active_model_identity"] == identity
    assert bound_projection["source_active_model_identity_digest"] == cognition_digest(identity)
    assert bound_projection["model_identity_binding_posture"] == \
        "protocol_bound_source_identity"
    from sentientos.resident_developmental_cognition import _task_family_model_applicability
    assert _task_family_model_applicability(bound_projection,
        target_model_identity=identity) == {
            "target_active_model_identity_digest": cognition_digest(identity),
            "model_identity_relation": "same_active_model_identity",
            "applicability_posture": "same_family_same_model_task_scope_unverified"}
    other_identity = {"provider": "fixture", "model": "other-model"}
    assert _task_family_model_applicability(bound_projection,
        target_model_identity=other_identity)["applicability_posture"] == \
        "cross_model_transfer_not_established"
    assert _task_family_model_applicability(bound_projection,
        target_model_identity=None)["model_identity_relation"] == "model_identity_unbound"
    from sentientos.resident_developmental_cognition import _compact_task_family_history_example
    compact = _compact_task_family_history_example({**bound_projection,
        **_task_family_model_applicability(bound_projection,
            target_model_identity=identity)})
    assert compact["model_identity_relation"] == "same_active_model_identity"
    assert compact["target_active_model_identity_digest"] == cognition_digest(identity)
    from sentientos.resident_developmental_cognition import _history_context_packet
    packet = _history_context_packet({"record_id": admitted.record_id,
        "record_digest": admitted.record_digest, "candidate": bound_model_identity,
        "created_at": "fixture-time", "epistemic_posture": "historical_only"},
        task_family_id="integer_affine_prediction",
        target_model_identity=identity, compact_for_input_budget=True)
    task_experience = packet["task_relevant_experience"][0]
    assert task_experience["model_identity_relation"] == "same_active_model_identity"
    assert task_experience["applicability_posture"] == \
        "same_family_same_model_task_scope_unverified"
    cross_model_packet = _history_context_packet({"record_id": admitted.record_id,
        "record_digest": admitted.record_digest, "candidate": bound_model_identity,
        "created_at": "fixture-time", "epistemic_posture": "historical_only"},
        task_family_id="integer_affine_prediction",
        target_model_identity=other_identity, compact_for_input_budget=True)
    assert "task_relevant_experience" not in cross_model_packet
    omission = cross_model_packet["task_relevant_experience_omission"]
    assert omission["posture"] == \
        "identity_not_matched_examples_withheld_from_task_guidance"
    assert omission["omitted_source_fact_ids"] == [bound_projection["source_fact_id"]]
    assert omission["omitted_evidence_digest"]
    assert len(omission["omission_evidence"][0]["historical_outcomes"]) == 3
    assert _task_family_history_examples(admitted.candidate,
        task_family_id="unrelated_family") == []

    # A bounded deterministic join fixture demonstrates how a later example
    # carries measured resource evidence only when run, condition, score, and
    # inference receipt identities all agree.
    resource_candidate = copy.deepcopy(admitted.candidate)
    resource_model_identity = {"provider": "fixture", "model": "resource-test"}
    resource_family_fact = next(fact for fact in resource_candidate["selected_facts"]
        if fact["fact_id"] == family_fact["fact_id"])
    resource_family_fact["payload"]["active_model_identity"] = resource_model_identity
    resource_family_fact["payload"]["active_model_identity_digest"] = \
        cognition_digest(resource_model_identity)
    resource_source = {"source_id": "fixture-resource-source", "kind": "resource_governor",
        "digest": "a" * 64}
    resource_candidate["selected_sources"].append(resource_source)
    for index, condition_id in enumerate(("history_present", "history_withheld",
            "history_restored"), start=1):
        family_condition = next(item for item in family_fact["payload"]["conditions"]
            if item["condition_id"] == condition_id)
        family_score = next(item for item in family_fact["payload"]["objective_scores"]
            if item["condition_id"] == condition_id)
        receipt_digest = f"{index:064x}"
        resource_candidate["selected_facts"].append({
            "fact_id": f"fixture-resource-lineage-fact-{condition_id}",
            "stage": "observation", "disposition": "verified",
            "observed_at": f"2026-01-01T00:00:0{index}+00:00",
            "source": dict(resource_source),
            "subject": {"subject_kind": "developmental_history_invocation_resource_lineage"},
            "payload": {
                "developmental_history_run_id": family_fact["payload"]["run_id"],
                "developmental_history_run_digest": family_fact["payload"]["run_digest"],
                "developmental_history_source_record_id": family_fact["source"]["source_id"],
                "developmental_history_source_record_digest": family_fact["source"]["digest"],
                "developmental_history_condition": condition_id,
                "task_family_id": "integer_affine_prediction",
                "task_outcome": {"posture": "run_owner_score_bound_to_condition",
                    "condition_id": condition_id, "score_digest": family_score["score_digest"],
                    "inference_receipt_id": family_condition["inference_receipt_id"],
                    "inference_receipt_digest": family_condition["inference_receipt_digest"]},
                "resource_measurement_posture": "verified_ledger_receipt_values",
                "resource_consumption_evidence": [{
                    "receipt_id": f"fixture-resource-receipt-{condition_id}",
                    "receipt_digest": receipt_digest,
                    "measured_values": {"call_units_consumed": index},
                    "measurement_posture": {"token_count": "unknown"}}],
                "resource_linkage": {"consumption_receipt_digests": [receipt_digest]},
                "lineage_findings": [],
            }})
    resource_examples = _task_family_history_examples(resource_candidate,
        task_family_id="integer_affine_prediction")
    assert resource_examples[0]["resource_context"]["posture"] == (
        "verified_ledger_receipt_values")
    assert resource_examples[0]["resource_context"]["measurements"][0][
        "measured_values"] == {"call_units_consumed": 1}
    condition_rows = resource_examples[0]["condition_outcomes"]
    assert [item["condition_id"] for item in condition_rows] == [
        "history_present", "history_withheld", "history_restored"]
    assert [item["resource_context"]["resource_receipts"][0]["receipt_id"]
        for item in condition_rows] == [
            "fixture-resource-receipt-history_present",
            "fixture-resource-receipt-history_withheld",
            "fixture-resource-receipt-history_restored"]
    assert [item["resource_context"]["resource_receipts"][0]["measured_values"][
        "call_units_consumed"] for item in condition_rows] == [1, 2, 3]
    from sentientos.resident_developmental_cognition import (
        _resource_condition_recommendation,
    )
    measured_choice = resource_examples[0]["resource_strategy_recommendation"]
    assert measured_choice["evaluator"] == "resource_quality_then_measured_call_units:v1"
    assert measured_choice["posture"] == "bounded_recommendation"
    assert measured_choice["recommendation"]["condition_id"] == "history_present"
    assert measured_choice["recommendation"]["call_units_consumed"] == 1
    assert measured_choice["recommendation"]["resource_receipts"][0][
        "receipt_id"] == "fixture-resource-receipt-history_present"
    assert measured_choice["requirements"]["source"] == (
        "frozen_task_descriptor_full_suite_correctness")
    assert measured_choice["requirements"]["task_digest"] == family_fact[
        "payload"]["objective_task_descriptor"]["task_digest"]
    assert condition_rows[0]["resource_context"]["event_time"] == (
        "2026-01-01T00:00:01+00:00")
    assert condition_rows[0]["resource_context"]["posture"] == (
        "verified_ledger_receipt_values")

    # Exercise the normal bounded history binder: the condition comparison and
    # recommendation enter the same inference prompt as other admitted history.
    from sentientos.resident_developmental_cognition import (
        _bind_history_and_epistemic_context,
    )
    synthetic_record = {"record_id": admitted.record_id,
        "record_digest": admitted.record_digest,
        "candidate": resource_candidate,
        "created_at": admitted.created_at,
        "epistemic_posture": admitted.epistemic_posture}
    _, _, resource_prompt, _, _ = _bind_history_and_epistemic_context(
        context={"instruction": "bounded fixture task",
            "current_evidence": {}, "prior_self_model": None,
            "prior_epistemic_state": None, "developmental_history": [],
            "developmental_history_posture": "historical_interpretation_not_current_truth",
                "developmental_history_task_family_id": "integer_affine_prediction",
                "developmental_history_target_model_identity": resource_model_identity},
        records=(synthetic_record,), projection=None)
    assert measured_choice["recommendation_digest"] in resource_prompt
    assert "fixture-resource-receipt-history_withheld" in resource_prompt

    # The same frozen evaluator permits a more expensive choice when it alone
    # satisfies quality, prefers a cheaper equal quality choice, and reports
    # uncertainty when receipt evidence is absent.
    def measured_conditions(correct: tuple[int, int, int], costs: tuple[int, int, int]):
        return [{"condition_id": condition_id,
            "inference_receipt_id": f"invocation-{condition_id}",
            "inference_receipt_digest": f"{index + 1:064x}",
            "score_digest": f"sha256:{index + 1:064x}",
            "evaluator": "deterministic_exact_integer_suite_oracle_v2",
            "correct_count": correct[index], "probe_count": 3,
            "resource_context": {"posture": "verified_ledger_receipt_values",
                "resource_receipts": [{"receipt_id": f"resource-{condition_id}",
                    "receipt_digest": f"{index + 4:064x}",
                    "measured_values": {"call_units_consumed": costs[index]}}]}}
            for index, condition_id in enumerate(("history_present", "history_withheld",
                "history_restored"))]
    premium = _resource_condition_recommendation(measured_conditions((3, 2, 1), (8, 1, 1)),
        minimum_correct_count=3, probe_count=3, task_digest="sha256:" + "a" * 64)
    assert premium["recommendation"]["condition_id"] == "history_present"
    economical = _resource_condition_recommendation(measured_conditions((3, 3, 2), (8, 2, 1)),
        minimum_correct_count=3, probe_count=3, task_digest="sha256:" + "a" * 64)
    assert economical["recommendation"]["condition_id"] == "history_withheld"
    negative_transfer = _resource_condition_recommendation(
        measured_conditions((1, 3, 2), (5, 2, 4)), minimum_correct_count=3,
        probe_count=3, task_digest="sha256:" + "a" * 64)
    assert negative_transfer["recommendation"]["condition_id"] == "history_withheld"
    incomparable_rows = measured_conditions((3, 3, 3), (1, 1, 1))
    incomparable_rows[1]["resource_context"] = {
        "posture": "unknown_missing_or_unbound_lineage", "resource_receipts": []}
    incomparable = _resource_condition_recommendation(incomparable_rows,
        minimum_correct_count=3, probe_count=3, task_digest="sha256:" + "a" * 64)
    assert incomparable["posture"] == "incomparable_missing_or_unbound_measurement"
    assert incomparable["recommendation"] is None
    mismatched_resource = copy.deepcopy(resource_candidate)
    history_present_resource = next(fact for fact in mismatched_resource["selected_facts"]
        if isinstance(fact.get("payload"), Mapping)
        and fact["payload"].get("developmental_history_condition") == "history_present")
    history_present_resource["payload"]["task_outcome"]["score_digest"] = (
        "sha256:" + "f" * 64)
    assert _task_family_history_examples(mismatched_resource,
        task_family_id="integer_affine_prediction")[0]["resource_context"]["posture"] == (
            "unknown_missing_or_unbound_lineage")
    crossed_condition = copy.deepcopy(resource_candidate)
    crossed_condition["selected_facts"][-1]["payload"]["developmental_history_condition"] = (
        "history_present")
    crossed_rows = _task_family_history_examples(crossed_condition,
        task_family_id="integer_affine_prediction")[0]["condition_outcomes"]
    assert crossed_rows[-1]["resource_context"]["posture"] == (
        "unknown_missing_or_unbound_lineage")
    unrelated_receipt = copy.deepcopy(resource_candidate)
    unrelated_fact = next(fact for fact in unrelated_receipt["selected_facts"]
        if isinstance(fact.get("payload"), Mapping)
        and fact["payload"].get("developmental_history_condition") == "history_present")
    unrelated_fact["payload"]["resource_consumption_evidence"][0]["receipt_digest"] = (
        "f" * 64)
    unrelated_rows = _task_family_history_examples(unrelated_receipt,
        task_family_id="integer_affine_prediction")[0]["condition_outcomes"]
    assert unrelated_rows[0]["resource_context"]["posture"] == (
        "unknown_missing_or_unbound_lineage")
    unqualified_candidate = copy.deepcopy(resource_candidate)
    unqualified_fact = next(fact for fact in unqualified_candidate["selected_facts"]
        if isinstance(fact.get("payload"), Mapping)
        and fact["payload"].get("developmental_history_condition") == "history_withheld")
    unqualified_fact["disposition"] = "degraded"
    unqualified_fact["payload"]["lineage_findings"] = ["receipt_identity_conflict"]
    unqualified_rows = _task_family_history_examples(unqualified_candidate,
        task_family_id="integer_affine_prediction")[0]["condition_outcomes"]
    assert unqualified_rows[1]["resource_context"]["posture"] == (
        "unknown_unqualified_condition_lineage")
    assert unqualified_rows[1]["resource_context"]["unqualified_lineage"][0][
        "lineage_findings"] == ["receipt_identity_conflict"]
    assert "multiplier" not in json.dumps(projected_examples)
    assert "offset" not in json.dumps(projected_examples)

    # Stage the second request, then execute it in a new interpreter. The child
    # receives only the bounded serialized fixture receipts and durable roots;
    # it cannot inherit the parent's invoker, receipt dictionary, owner, or run
    # objects.
    heldout_task = ObjectivePredictionTask(3, 2, 10, (11, 12),
        task_family_id="integer_affine_prediction", requires_task_family_history=True)
    prior_epistemic, _prior_proposition, prior_state = epistemic_projection(
        tmp_path / "epistemic-prior", with_evidence=True)
    _, prior_task_request, prior_task_eligible = stage_request(config_path=config_path,
        request_id="episode-heldout-with-epistemic-prior", task=heldout_task)
    assert prior_task_eligible >= 1
    prior_task_result = cognition.run_objective_intervention_once(snapshot=snapshot(),
        tick_id="episode-heldout-with-epistemic-prior", objective_task=heldout_task,
        request_id="episode-heldout-with-epistemic-prior",
        request_digest=str(prior_task_request["request_digest"]),
        prior_epistemic_state=prior_epistemic)
    assert prior_task_result.status == "objective_intervention_completed"
    prior_task_run = cognition.experiments.load_run(
        str(prior_task_result.changed_cognition_measurement_id))
    assert len(prior_task_run["objective_scores"]) == 3
    assert all(row["condition_id"] in {"history_present", "history_withheld", "history_restored"}
        for row in prior_task_run["objective_scores"])
    assert all(row["score"]["evaluator"]
        == "deterministic_exact_integer_suite_oracle_v2"
        for row in prior_task_run["objective_scores"])
    assert all(isinstance(row["score"]["score_digest"], str)
        and row["score"]["status"] in {"correct", "incorrect", "invalid_answer",
            "output_unavailable", "output_truncated"}
        for row in prior_task_run["objective_scores"])
    epistemic_requests = [request for request in model.requests
        if request.upstream_evidence.get("epistemic_projection_id")
            == prior_epistemic.projection_id]
    assert epistemic_requests
    epistemic_input = json.loads(epistemic_requests[0].prompt)["prior_epistemic_state"]
    [semantic_packet] = epistemic_input["semantic_packets"]
    assert semantic_packet["state"]["state_id"] == prior_state.state_id
    assert semantic_packet["state"]["state_digest"] == prior_state.state_digest

    _, heldout_request, eligible_count = stage_request(config_path=config_path,
        request_id="episode-heldout-after-restart", task=heldout_task)
    assert eligible_count >= 1

    episode = _run_family_episode_in_child(tmp_path,
        acquisition_request_digest=str(acquisition_request["request_digest"]),
        request_id="episode-heldout-after-restart",
        request_digest=str(heldout_request["request_digest"]),
        active_model_identity=fake.active_model_identity)
    heldout_run = episode["run"]
    present, withheld, restored = heldout_run["conditions"]
    assert feedback.written_record_id in present["retrieved_record_ids"]
    assert withheld["retrieved_record_ids"] == []
    assert feedback.written_record_id in restored["retrieved_record_ids"]
    scores = {row["condition_id"]: row["score"]
        for row in heldout_run["objective_scores"]}
    assert scores["history_present"]["correct_count"] == 3
    assert scores["history_withheld"]["correct_count"] == 0
    assert scores["history_restored"]["correct_count"] == 3
    # Exact request correlation binds each control to this held-out tick.
    heldout_prompts = episode["prompts"]
    for condition_id, prompt in heldout_prompts.items():
        body = json.loads(prompt)
        assert not any("task_relevant_experience" in fact
            for fact in body["current_evidence"]["facts"])
        if condition_id in {"history_present", "history_restored"}:
            assert "task_relevant_experience" in json.dumps(body["developmental_history"])
            historical_examples = [item for record in body["developmental_history"]
                for item in record.get("task_relevant_experience", [])]
            assert historical_examples
            assert historical_examples[0]["execution_evidence_posture"] == (
                "one_or_more_conditions_simulated_or_no_backend_entry")
            assert historical_examples[0]["independent_backend_observation"] is False
            assert len(historical_examples[0]["execution_evidence_conditions"]) == 3
        else:
            assert "task_relevant_experience" not in json.dumps(body["developmental_history"])
    assert "multiplier" not in json.dumps(heldout_prompts)
    assert "offset" not in json.dumps(heldout_prompts)
    assert "learning_established" not in heldout_run["objective_evaluation"]
    assert heldout_run["objective_evaluation"]["scope"] == \
        "same_model_task_correctness_not_general_learning_or_weight_change"
    progression = episode["progression"]
    assert progression["episode_count"] == 2
    assert progression["distinct_task_instances"] is True
    assert progression["distinct_probe_sets"] is True
    second_episode = progression["episodes"][1]
    assert second_episode["task_family_history_record_ids"] == [feedback.written_record_id]
    assert second_episode["conditions"][0]["task_family_retrieved_record_ids"] == [
        feedback.written_record_id]
    assert second_episode["conditions"][1]["task_family_retrieved_record_ids"] == []
    assert second_episode["conditions"][2]["task_family_retrieved_record_ids"] == [
        feedback.written_record_id]
    # Canonical receipt validation remains distinct from actual local-model use.
    assert progression["actual_nonsynthetic_inference_verified"] is False
    assert progression["learning_established"] is False
    assert progression["performance_improvement_established"] is False
    assert episode["fresh_process"] is True
    assert episode["fixture_only"] is True

    # Carry the child-completed episode back through its real World-State and
    # ordinary developmental writeback owners, then stage a third distinct
    # episode for another fresh interpreter.
    second_world = WorldStateBoardBuilder().build(cognition.experiments.world_state_records(
        run_refs=((heldout_run["run_id"], heldout_run["run_digest"]),)))
    second_feedback = cognition.run_tick(snapshot=second_world,
        tick_id="episode-heldout-feedback")
    assert second_feedback.written_record_id
    second_admitted = cognition.writeback.store.get(second_feedback.written_record_id)
    second_family_fact = next(fact for fact in second_admitted.candidate["selected_facts"]
        if fact["payload"].get("objective_task_family") == "integer_affine_prediction")
    assert second_family_fact["payload"]["acquisition_examples"]
    third_task = ObjectivePredictionTask(3, 2, 16, (17, 18),
        task_family_id="integer_affine_prediction", requires_task_family_history=True)
    _, third_request, third_eligible = stage_request(config_path=config_path,
        request_id="episode-third-after-recovered-feedback", task=third_task)
    assert third_eligible >= 1
    third_episode = _run_family_episode_in_child(tmp_path,
        acquisition_request_digest=str(acquisition_request["request_digest"]),
        request_id="episode-third-after-recovered-feedback",
        request_digest=str(third_request["request_digest"]),
        prior_request_refs=(
            ("episode-acquisition", str(acquisition_request["request_digest"])),
                ("episode-heldout-after-restart", str(heldout_request["request_digest"]))),
        active_model_identity=fake.active_model_identity)
    third_run = third_episode["run"]
    third_scores = {row["condition_id"]: row["score"]
        for row in third_run["objective_scores"]}
    assert third_scores["history_present"]["correct_count"] == 3
    assert third_scores["history_withheld"]["correct_count"] == 0
    assert third_scores["history_restored"]["correct_count"] == 3
    third_progression = third_episode["progression"]
    assert third_progression["episode_count"] == 3
    assert third_progression["episodes"][2]["task_family_history_record_ids"]
    assert second_feedback.written_record_id in third_progression["episodes"][2][
        "task_family_history_record_ids"]
    assert third_progression["learning_established"] is False
    assert third_progression["performance_improvement_established"] is False
    assert third_progression["independent_backend_observation"] is False
    assert third_progression["execution_evidence_scope"] == (
        "authenticated_owner_receipts_not_independent_backend_observation")

    # Reconstruct again under a different model identity. Historical source
    # scores and omission evidence remain inspectable, while structured probe
    # examples are withheld from this target model's task guidance.
    cross_model_task = ObjectivePredictionTask(3, 2, 20, (21, 22),
        task_family_id="integer_affine_prediction", requires_task_family_history=True)
    _, cross_model_request, cross_model_eligible = stage_request(config_path=config_path,
        request_id="episode-cross-model-guidance-gate", task=cross_model_task)
    assert cross_model_eligible >= 1
    cross_model_identity = {"provider": "fixture", "model": "other-model"}
    cross_model_episode = _run_family_episode_in_child(tmp_path,
        acquisition_request_digest=str(acquisition_request["request_digest"]),
        request_id="episode-cross-model-guidance-gate",
        request_digest=str(cross_model_request["request_digest"]),
        prior_request_refs=(
            ("episode-acquisition", str(acquisition_request["request_digest"])),
            ("episode-heldout-after-restart", str(heldout_request["request_digest"])),
            ("episode-third-after-recovered-feedback", str(third_request["request_digest"]))),
        active_model_identity=cross_model_identity, publish_session=True)
    cross_model_scores = {row["condition_id"]: row["score"]
        for row in cross_model_episode["run"]["objective_scores"]}
    assert all(row["correct_count"] == 0 for row in cross_model_scores.values())
    cross_prompt = json.loads(cross_model_episode["prompts"]["history_present"])
    cross_history = cross_prompt["developmental_history"]
    assert not any("task_relevant_experience" in item for item in cross_history)
    cross_omissions = [item["task_relevant_experience_omission"]
        for item in cross_history if "task_relevant_experience_omission" in item]
    assert cross_omissions
    assert all(item["omitted_evidence_digest"] for item in cross_omissions)
    assert any(any(outcome["correct_count"] == 3
            for evidence in item["omission_evidence"]
            for outcome in evidence["historical_outcomes"])
        for item in cross_omissions)

    tampered_receipt = next(receipt.receipt_id for receipt in fake.receipts.values()
        if receipt.purpose == "resident_developmental_history_intervention_experiment"
        and "objective_task_plan_digest" in receipt.request.get("upstream_evidence", {}))
    tamper_task = ObjectivePredictionTask(3, 2, 13, (14, 15),
        task_family_id="integer_affine_prediction", requires_task_family_history=True)
    _, tamper_request, tamper_eligible = stage_request(config_path=config_path,
        request_id="episode-heldout-tamper-control", task=tamper_task)
    assert tamper_eligible >= 1
    assert _run_family_episode_in_child(tmp_path,
        acquisition_request_digest=str(acquisition_request["request_digest"]),
        request_id="episode-heldout-tamper-control",
        request_digest=str(tamper_request["request_digest"]),
        tamper_receipt_id=tampered_receipt)["rejected_before_owner_recovery"] is True


def test_legacy_oracle_hashes_are_excluded_from_current_cognition(tmp_path: Path) -> None:
    cognition, _ = owner(tmp_path, comparison=False,
        allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=8)
    world = WorldStateBoardBuilder().build([
        {"source_id": "legacy-objective", "source_kind": "embodiment",
            "subject_id": "legacy-run", "subject_kind": "fixture_observation",
            "stage": "observation", "disposition": "recorded", "observed_at": None,
            "payload": {"objective_task_descriptor": {"task_digest": "sha256:" + "1" * 64}}},
        {"source_id": "legacy-ab-score", "source_kind": "embodiment",
            "subject_id": "legacy-ab-run", "subject_kind": "fixture_observation",
            "stage": "observation", "disposition": "recorded", "observed_at": None,
            "payload": {"objective_score_contract": {"task_digest": "sha256:" + "2" * 64}}},
        {"source_id": "safe-objective", "source_kind": "embodiment",
            "subject_id": "safe-run", "subject_kind": "fixture_observation",
            "stage": "observation", "disposition": "recorded", "observed_at": None,
            "payload": {"objective_task_descriptor": {
                "task_digest": "sha256:" + "3" * 64,
                "task_digest_posture": "salted_private_oracle_commitment:v1"}}},
    ])
    projection = cognition._current_projection(world)
    projected_ids = {str(fact["source"]["source_id"]) for fact in projection.facts}
    assert projected_ids == {"safe-objective"}
    selected = cognition._select_fact_ids(world, set())
    assert len(selected) == 1


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
    acquired_later = cognition.run_tick(snapshot=snapshot(2),
        tick_id="succession-history-source-later")
    assert acquired_later.written_record_id
    later_record = cognition.writeback.store.get(acquired_later.written_record_id)
    assert later_record.record_id != record.record_id
    assert later_record.record_digest != record.record_digest
    projection = cognition._current_projection(snapshot(3))
    current_payload = projection.semantic_payload()
    history_ids = (record.record_id, later_record.record_id)
    history_digests = (record.record_digest, later_record.record_digest)
    history = cognition.writeback.retrieve(history_ids, limit=4)
    assert history.requested_record_ids == history_ids
    assert tuple(item["record_digest"] for item in history.records) == history_digests

    context = FrozenCausalContext.create(
        snapshot_id=projection.snapshot_id, snapshot_digest=projection.snapshot_digest,
        current_projection_id=projection.projection_id,
        current_projection_digest=projection.projection_digest,
        current_fact_ids=projection.fact_ids,
        projected_content_digest="sha256:" + digest_payload(current_payload),
        current_projection_payload=current_payload,
        history_record_ids=history_ids, history_record_digests=history_digests,
        history_record_set_digest="sha256:" + digest_payload({
            "record_ids": list(history_ids), "record_digests": list(history_digests)}),
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
    assert experiment.context.history_record_ids == history_ids
    assert experiment.context.history_record_digests == history_digests
    a_history = json.loads(model_a.calls[0]["prompt"])["developmental_history"]
    b_history = json.loads(model_b.calls[0]["prompt"])["developmental_history"]
    assert tuple(item["record_id"] for item in a_history) == history_ids
    assert tuple(item["record_id"] for item in b_history) == history_ids
    assert tuple(item["record_digest"] for item in a_history) == history_digests
    assert tuple(item["record_digest"] for item in b_history) == history_digests
    assert json.loads(model_a.calls[1]["prompt"])["developmental_history"] == []
    assert json.loads(model_b.calls[1]["prompt"])["developmental_history"] == []
    assert json.loads(model_a.calls[2]["prompt"])["developmental_history"] == a_history
    assert all(item["history_record_ids"] == list(history_ids)
        for item in (result["observations"][0], result["observations"][2],
            result["observations"][4]))
    assert all(item["history_record_ids"] == []
        for item in (result["observations"][1], result["observations"][3]))
    assert all(not item.current_truth and not item.authority for item in (record, later_record))
    recovered_ids = {item.record_id for item, _receipt in
        cognition.writeback.inspect_completed_records()}
    assert set(history_ids) <= recovered_ids


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
    assert progression["episodes_with_admitted_task_family_history"] == 0
    assert progression["matching_task_family_history_retrieved_for_all_episodes"] is False
    assert [episode["tick_id"] for episode in progression["episodes"]] == [
        "progression-tick-1", "progression-tick-2"]
    assert progression["same_model_generation_controls"] is True
    assert progression["distinct_task_instances"] is True
    assert progression["distinct_probe_sets"] is True
    assert progression["actual_nonsynthetic_inference_verified"] is False
    assert progression["learning_established"] is False
    assert progression["performance_improvement_established"] is False
    for episode in progression["episodes"]:
        assert episode["task_family_history_record_ids"] == []
        assert episode["task_family_history_relevance_posture"] == \
            "no_matching_admitted_task_family_history"
        assert episode["conditions"][0]["retrieved_record_ids"] == episode["history_record_ids"]
        assert episode["conditions"][0]["task_family_retrieved_record_ids"] == []
        assert episode["conditions"][1]["retrieved_record_ids"] == []
        assert episode["conditions"][2]["retrieved_record_ids"] == episode["history_record_ids"]
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
    fake.truncate_objective_output = True
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
    assert changed["episodes"][2]["scoreable"] is False
    assert changed["episodes"][2]["score_contrasts"] == {
        "schema_version": "sentientos.task_family_episode_score_contrast:v1",
        "probe_denominator": 3,
        "history_present_minus_withheld_correct_count": None,
        "history_restored_minus_present_correct_count": None,
        "posture": "unscoreable_condition_prevents_complete_contrast",
        "learning_established": False,
        "performance_improvement_established": False,
    }
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
    child_report = _reconstruct_progression_in_child(tmp_path, fake.receipts,
        requests + [(third_request["request_id"], third_request["request_digest"])])
    assert child_report == changed
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
    assert [row["generation_budget"]["preregistered_max_output_chars"]
        for row in report["conditions"]] == [4000, 4000, 4000]
    assert all("preregistered_max_output_bytes" not in row["generation_budget"]
        for row in report["conditions"])
    assert all(row["output_size_posture"] == "invocation_receipt_bound"
        and type(row["output_size_bytes"]) is int and row["output_size_bytes"] > 0
        for row in report["conditions"])
    assert all(row["resource_linkage"]["posture"] ==
        "no_resource_linkage_in_invocation_receipt"
        and row["resource_linkage"]["cpu_time_ms"] is None
        and row["resource_linkage"]["gpu_time_ms"] is None
        and row["resource_linkage"]["energy_joules"] is None
        and row["resource_linkage"]["generated_token_count"] is None
        for row in report["conditions"])
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
    projected_comparison = retained["history_intervention_summary"]
    source_comparison = records[0]["payload"]["history_intervention_summary"]
    assert projected_comparison["classification"] == source_comparison["classification"]
    assert projected_comparison["present_vs_withheld_difference_observed"] == source_comparison[
        "present_vs_withheld_difference_observed"]
    assert projected_comparison["restored_vs_withheld_difference_observed"] == source_comparison[
        "restored_vs_withheld_difference_observed"]
    assert projected_comparison["restored_matches_present"] == source_comparison[
        "restored_matches_present"]
    assert len(projected_comparison["measurements"]) == 2
    assert [(item["measurement_id"], item["measurement_digest"],
        item["observable_difference"], item["interpretation"])
        for item in projected_comparison["measurements"]] == [
            (item["measurement_id"], item["measurement_digest"],
                item["observable_difference"], item["interpretation"])
            for item in source_comparison["measurements"]]
    assert retained["execution_evidence_posture"] == "incomplete_or_unverified_condition_receipts"
    assert all(item["receipt_identity_verified"] is False
        and item["posture"] == "receipt_unbound_or_identity_mismatch"
        for item in retained["execution_evidence_conditions"])
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


def test_cognition_event_time_rejects_rfc3339_unknown_offset() -> None:
    from sentientos.resident_developmental_cognition import _aware_event_time

    assert not _aware_event_time("2035-01-03T00:00:00-00:00")
    assert _aware_event_time("2035-01-03T00:00:00+00:00")


def test_final_score_checkpoints_recover_run_after_precommit_interruption(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeInvoker()
    fake.active_model_identity = {"provider": "fixture", "model": "task-family"}
    fake.objective_plan_root = tmp_path / "state" / "developmental_experiments" / "protocols"
    fake.history_interpretation = "Historical examples: input 1 produced 5; input 2 produced 8."
    task = ObjectivePredictionTask(multiplier=3, offset=2, probe_input=7,
        additional_probe_inputs=(8, 9), task_family_id="integer_affine_prediction")
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
    from sentientos.persistent_epistemic_state import (
        PersistentEpistemicStateOwner, make_proposition,
    )
    epistemics = PersistentEpistemicStateOwner(tmp_path / "epistemics",
        allowed_namespaces=("operator",))
    proposition = make_proposition(namespace="operator",
        subject="task_family:integer_affine_prediction", predicate="history_effect",
        object_value="history presence changes held-out correctness", polarity="positive",
        qualifiers={"run_scope": run_id}, temporal_scope={"kind": "single_run"},
        context_scope={"task_family_id": "integer_affine_prediction",
            "active_model_identity_digest": "sha256:" + digest_payload(
                fake.active_model_identity)},
        proposition_class="causal_hypothesis")
    epistemics.register_proposition(proposition)
    with pytest.raises(DevelopmentalHistoryInterventionError,
            match="epistemic_run_digest_mismatch"):
        restarted.experiments.objective_task_family_evidence_binding(
            run_id=run_id, expected_run_digest="sha256:" + "0" * 64,
            proposition_id=proposition.proposition_id)
    outcome_binding = restarted.experiments.objective_task_family_evidence_binding(
        run_id=run_id, expected_run_digest=run_digest,
        proposition_id=proposition.proposition_id)
    assert outcome_binding.source_artifact_id == run_id
    assert outcome_binding.source_digest == run_digest
    assert outcome_binding.source_class == "deterministic_task_family_evaluation"
    assert outcome_binding.dependency_kind == "unknown_dependency"
    assert outcome_binding.freshness == "unknown"
    evaluated_at = max(datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
        for row in run["conditions"]) + timedelta(seconds=1)
    from sentientos.resident_epistemic_development import (
        EpistemicDevelopmentConfig, EpistemicDevelopmentError, EpistemicDevelopmentRule,
        ResidentEpistemicDevelopmentRuntime,
    )
    from sentientos.resident_epistemic_state_mutation import (
        ResidentEpistemicStateMutationController,
    )
    from sentientos.codex_task_authority_admission import (
        RESIDENT_EPISTEMIC_STATE_MUTATION,
        RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION,
    )
    epistemic_ledger = AdmissionLedger(tmp_path / "epistemic-admissions.json")
    epistemic_definitions = {RESIDENT_EPISTEMIC_STATE_MUTATION:
        RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION}
    controller = ResidentEpistemicStateMutationController(owner=epistemics,
        admission_verifier=RuntimeAdmissionVerifier(
            definitions=epistemic_definitions, ledger=epistemic_ledger),
        current_sequence=epistemic_ledger.current_sequence,
        receipt_root=tmp_path / "epistemic-mutation-receipts")
    rule = EpistemicDevelopmentRule("verified-task-family", proposition.proposition_id,
        proposition.proposition_digest,
        {"source_kind": "embodiment",
            "subject_kind": "developmental_history_intervention_experiment"},
        "supports", "unknown_dependency", "bounded_fixture")
    runtime = ResidentEpistemicDevelopmentRuntime(
        config=EpistemicDevelopmentConfig(True, 1, 1, (rule,), ("operator",)),
        owner=epistemics, mutation_controller=controller,
        admission_authority=RuntimeAdmissionAuthority(
            definitions=epistemic_definitions, ledger=epistemic_ledger),
        admission_ledger=epistemic_ledger)
    with pytest.raises(DevelopmentalHistoryInterventionError,
            match="epistemic_run_digest_mismatch"):
        runtime.process_verified_task_family_run(
            experiment_store=restarted.experiments, run_id=run_id,
            expected_run_digest="sha256:" + "0" * 64,
            rule_id=rule.rule_id, tick=1, recorded_at=evaluated_at.isoformat())
    assert epistemic_ledger.load()[0] == ()
    feedback = runtime.process_verified_task_family_run(
        experiment_store=restarted.experiments, run_id=run_id,
        expected_run_digest=run_digest, rule_id=rule.rule_id, tick=1,
        recorded_at=evaluated_at.isoformat())
    assert feedback.status == "state_advanced"
    assert len(feedback.evidence_receipt_ids) == 1
    assert len(feedback.state_receipt_ids) == 1
    assert len(epistemic_ledger.load()[0]) == 2
    assert runtime.process_verified_task_family_run(
        experiment_store=restarted.experiments, run_id=run_id,
        expected_run_digest=run_digest, rule_id=rule.rule_id, tick=1,
        recorded_at=evaluated_at.isoformat()).status == "already_applied"
    state = epistemics.current_state(proposition.proposition_id)
    assert state is not None
    assert state.stance == "provisionally_supported"
    assert state.dependency_unresolved is True

    # A second, independently scored episode in the same family contradicts
    # the first. The governed runtime must retain both exact run identities,
    # advance to a contested position, and preserve that conflict across owner
    # reconstruction rather than letting the newest episode erase history.
    fake.objective_mode = "degrade"
    adverse_cycle = restarted.run_tick(snapshot=snapshot(43),
        tick_id="final-score-recovery-adverse-trial")
    assert adverse_cycle.written_record_id
    adverse_run_id = adverse_cycle.changed_cognition_measurement_id
    assert isinstance(adverse_run_id, str) and adverse_run_id
    adverse_run = restarted.experiments.load_run(adverse_run_id)
    assert adverse_run["objective_evaluation"]["history_correct_probe_delta"] == -1
    assert adverse_run["protocol"]["objective_task_descriptor"]["task_family_id"] == (
        "integer_affine_prediction")
    adverse_recorded_at = max(datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
        for row in adverse_run["conditions"]) + timedelta(seconds=1)
    adverse_feedback = runtime.process_verified_task_family_run(
        experiment_store=restarted.experiments, run_id=adverse_run_id,
        expected_run_digest=adverse_run["run_digest"], rule_id=rule.rule_id,
        tick=2, recorded_at=adverse_recorded_at.isoformat())
    assert adverse_feedback.status == "state_advanced"
    assert len(adverse_feedback.evidence_receipt_ids) == 1
    assert len(adverse_feedback.state_receipt_ids) == 1
    request_count_after_adverse_episode = len(fake.requests)
    refs = (*refs, (adverse_run_id, adverse_run["run_digest"]))
    assert len(epistemic_ledger.load()[0]) == 4
    state = epistemics.current_state(proposition.proposition_id)
    assert state is not None and state.stance == "contested"
    assert state.dependency_unresolved is True
    all_outcome_bindings = epistemics.bindings(proposition.proposition_id)
    assert len(all_outcome_bindings) == 2
    assert {binding.source_artifact_id for binding in all_outcome_bindings} == {
        run_id, adverse_run_id}
    assert {binding.evidence_relation for binding in all_outcome_bindings} == {
        "supports", "contradicts"}
    assert {binding.reliability_posture for binding in all_outcome_bindings} == {
        "bounded_preregistered_task_family_outcome_not_external_observation"}
    recovered_epistemics = PersistentEpistemicStateOwner(tmp_path / "epistemics",
        allowed_namespaces=("operator",))
    recovered_controller = ResidentEpistemicStateMutationController(
        owner=recovered_epistemics,
        admission_verifier=RuntimeAdmissionVerifier(
            definitions=epistemic_definitions, ledger=epistemic_ledger),
        current_sequence=epistemic_ledger.current_sequence,
        receipt_root=tmp_path / "epistemic-mutation-receipts")
    assert recovered_controller.verify_receipts()["status"] == "verified"
    recovered_state = recovered_epistemics.current_state(proposition.proposition_id)
    assert recovered_state == state
    recovered_bindings = recovered_epistemics.bindings(proposition.proposition_id)
    assert {binding.binding_id for binding in recovered_bindings} == {
        binding.binding_id for binding in all_outcome_bindings}
    recovered_runtime = ResidentEpistemicDevelopmentRuntime(
        config=EpistemicDevelopmentConfig(True, 1, 1, (rule,), ("operator",)),
        owner=recovered_epistemics, mutation_controller=recovered_controller,
        admission_authority=RuntimeAdmissionAuthority(
            definitions=epistemic_definitions, ledger=epistemic_ledger),
        admission_ledger=epistemic_ledger)
    trace = recovered_runtime.trace_proposition(
        proposition_id=proposition.proposition_id,
        reconstructed_at="2026-10-15T00:00:00+00:00", max_events=2, cognitive_tick=3)
    trace_evidence = {item["source_run_id"]: item for item in trace["evidence"]}
    assert trace_evidence[run_id]["source_digest"] == run_digest
    assert trace_evidence[run_id]["observation_time"] == outcome_binding.observation_time
    assert trace_evidence[adverse_run_id]["source_digest"] == adverse_run["run_digest"]
    assert {item["relation"] for item in trace["evidence"]} == {"supports", "contradicts"}
    assert {item["dependency_kind"] for item in trace["evidence"]} == {"unknown_dependency"}
    assert [(item["generation"], item["stance"]) for item in trace["states"]] == [
        (0, "provisionally_supported"), (1, "contested")]
    assert [item["generation"] for item in trace["events"]] == [0, 1]
    assert trace["events"][0]["prior_state_digest"] is None
    assert trace["events"][1]["prior_state_digest"] == trace["states"][0]["state_digest"]
    assert trace["events"][1]["successor_state_digest"] == state.state_digest
    assert len(trace["mutation_receipts"]) == 4
    assert trace["resulting_prior_projection"]["state_digests"] == [state.state_digest]
    assert trace["truth"] is False and trace["authority"] is False
    with pytest.raises(EpistemicDevelopmentError, match="selection_invalid"):
        recovered_runtime.trace_proposition(proposition_id=proposition.proposition_id,
            reconstructed_at="now", max_events=0)
    later, later_fake = owner(tmp_path / "later-cognition", invoker=FakeInvoker())
    later.run_tick(snapshot=snapshot(), tick_id="after-admitted-task-family-outcome",
        prior_epistemic_state=recovered_epistemics.cognitive_projection(
            max_states=1, current_tick=3))
    later_request = next(item for item in later_fake.requests
        if item.purpose == "resident_developmental_retrieval_cognition")
    later_packets = json.loads(later_request.prompt)["prior_epistemic_state"]["semantic_packets"]
    assert len(later_packets) == 1
    assert later_packets[0]["state"]["state_digest"] == state.state_digest
    assert later_packets[0]["state"]["stance"] == "contested"
    assert later_packets[0]["evidence_posture"]["dependency_unresolved"] is True
    from sentientos.causal_introspection import CaptureContext, IntrospectionConfig
    from sentientosd import RuntimeMaintenanceSurfaces, _compose_causal_introspection
    surfaces = RuntimeMaintenanceSurfaces(tmp_path / "causal-runtime",
        runtime_state_root=tmp_path / "causal-runtime-state",
        epistemic_state_owner=recovered_epistemics,
        epistemic_state_config={"status": "enabled",
            "cognitive_consumption_enabled": True},
        epistemic_development_runtime=runtime)
    causal = _compose_causal_introspection(surfaces,
        resident_serving_controller=None,
        config=IntrospectionConfig(True, tmp_path / "causal-custody", True, 8,
            ("persistent_epistemics",), ("persistent_epistemics",)))
    captured = causal.capture(CaptureContext("after-admitted-task-family-outcome",
        capture_posture="synthetic_test"))
    [epistemic_projection] = captured.projections
    observations = {item.observation_key: item.bounded_value
        for item in epistemic_projection.observations}
    assert observations["state_count"] == 2
    assert observations["evidence_binding_count"] == 2
    assert observations["mutation_recovery_status"] == "verified"
    assert epistemic_projection.posture.current_truth is False
    assert epistemic_projection.posture.authority is False
    assert recovered_state.authority == {
        "policy": False, "goal": False, "permission": False, "effect_admission": False,
        "adoption": False, "memory_retention": False, "truth_oracle": False}
    projected = restarted.experiments.world_state_records(run_refs=refs)
    assert len(projected) == 2
    assert {row["payload"]["objective_evaluation"]["history_correct_probe_delta"]
        for row in projected} == {3, -1}
    assert "output_text" not in json.dumps(projected)
    assert len(fake.requests) == request_count_after_adverse_episode

    # Carry the recovered run's admitted, dependency-unresolved position into
    # canonical planning. It must change allocation only inside its declared
    # family/model scope and trigger review rather than authority or execution.
    from sentientos.goal_executor import GoalExecutor
    from sentientos.goal_graph import Goal, GoalGraph, persist_goal_graph
    from sentientos.orchestrator import plan_goals

    planning_root = tmp_path / "planning-from-recovered-history"
    (planning_root / "glow/contracts").mkdir(parents=True)
    (planning_root / "glow/contracts/ci_baseline.json").write_text(
        "{}\n", encoding="utf-8")
    history_goal = Goal("history-sensitive", "history-scoped work", 10.0, 100, (),
        "task:forge_propose", 1, 1,
        ("integrity", f"epistemic_proposition:{proposition.proposition_id}",
            "epistemic_task_family:integer_affine_prediction"), True)
    independent_goal = Goal("independent", "independent work", 1.0, 1, (),
        "task:forge_propose", 1, 1, ("integrity",), True)
    persist_goal_graph(planning_root,
        GoalGraph(schema_version=1, goals=(history_goal, independent_goal)))
    planning_time = "2026-10-16T10:01:00+00:00"
    without_history = plan_goals(planning_root,
        planning_time="2026-10-16T10:00:00+00:00")
    assert "history-sensitive" in without_history.allocation.selected

    class ServingIdentityObserver:
        def observed_current_model_identity(self):
            return dict(fake.active_model_identity)

        def current_session(self):
            raise AssertionError("canonical planning cannot acquire a model session")

        def invoke(self, *_args, **_kwargs):
            raise AssertionError("canonical planning cannot invoke a model")

    def forbidden_execute(*_args, **_kwargs):
        raise AssertionError("canonical planning cannot execute goals")

    monkeypatch.setattr(GoalExecutor, "execute_plan", forbidden_execute)
    recovered_state_before_plan = recovered_epistemics.current_state(
        proposition.proposition_id)
    planning_surfaces = RuntimeMaintenanceSurfaces(
        planning_root,
        epistemic_state_owner=recovered_epistemics,
        epistemic_state_config={"status": "configured",
            "cognitive_consumption_enabled": True,
            "max_cognitive_projection_count": 4},
        resident_cognitive_invoker=ServingIdentityObserver())
    with_history = planning_surfaces.plan_canonical_goals(tick_id=planning_time)
    assert "history-sensitive" not in with_history.allocation.selected
    assert "independent" in with_history.allocation.selected
    assert {item.goal_id: item.reason for item in with_history.allocation.deferred}[
        "history-sensitive"] == "epistemic_review_required"
    assert with_history.work_plan is not None
    assert with_history.work_plan.selected_goals == ("independent",)
    assert with_history.work_plan_evidence_path is not None
    planning_evidence = json.loads((planning_root /
        with_history.work_plan_evidence_path).read_text(encoding="utf-8"))
    assert planning_evidence["evidence_binding"]["projection_digest"]
    assert planning_evidence["evidence_binding"]["goal_applicability"][
        "history-sensitive"] == "epistemic_review_required"
    assert recovered_epistemics.current_state(proposition.proposition_id) == (
        recovered_state_before_plan)
    assert list((planning_root / "glow/forge/work_runs").glob("run_*.json")) == []

    # A verified history bound to the former serving identity stays review
    # scoped when the live identity changes. The mismatch must be visible in
    # plan evidence and cannot silently make the historical proposition apply
    # to a replacement model.
    prior_identity_digest = "sha256:" + digest_payload(fake.active_model_identity)
    fake.active_model_identity = {"provider": "fixture", "model": "replacement-model"}
    replacement_identity_digest = "sha256:" + digest_payload(fake.active_model_identity)
    assert replacement_identity_digest != prior_identity_digest
    drift_time = "2026-10-16T10:02:00+00:00"
    after_identity_drift = planning_surfaces.plan_canonical_goals(tick_id=drift_time)
    assert "history-sensitive" not in after_identity_drift.allocation.selected
    assert "independent" in after_identity_drift.allocation.selected
    assert {item.goal_id: item.reason
        for item in after_identity_drift.allocation.deferred}["history-sensitive"] == (
            "epistemic_applicability_unresolved")
    assert after_identity_drift.work_plan is not None
    assert after_identity_drift.work_plan.selected_goals == ("independent",)
    assert after_identity_drift.work_plan_evidence_path is not None
    drift_evidence = json.loads((planning_root /
        after_identity_drift.work_plan_evidence_path).read_text(encoding="utf-8"))
    drift_binding = drift_evidence["evidence_binding"]
    assert drift_binding["projection_digest"] != planning_evidence[
        "evidence_binding"]["projection_digest"]
    assert drift_binding["review_scopes"][proposition.proposition_id][
        "active_model_identity_digest"] == prior_identity_digest
    assert drift_binding["target_active_model_identity_digest"] == (
        replacement_identity_digest)
    assert drift_binding["goal_applicability"]["history-sensitive"] == (
        "epistemic_applicability_unresolved")
    assert recovered_epistemics.current_state(proposition.proposition_id) == (
        recovered_state_before_plan)
    assert list((planning_root / "glow/forge/work_runs").glob("run_*.json")) == []

    state = restarted._state()
    intent = next(row for row in state["incomplete_ticks"]
        if row.get("tick_id") == "final-score-recovery-trial")
    assert intent["status"] == "interrupted_recovered"
    assert intent["experiment_recovery_posture"] == (
        "complete_scored_run_recovered_without_inference_replay")
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        restarted.run_tick(snapshot=snapshot(), tick_id="final-score-recovery-trial")
    assert len(fake.requests) == request_count_after_adverse_episode


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
          max_selected_facts: int = 1, objective_task=None,
          resource_context_owner=None):
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
        invoker=fake, current_sequence=next_sequence, objective_task=objective_task,
        resource_context_owner=resource_context_owner)
    return result, fake


def test_developmental_resource_context_owner_is_consumed_per_condition(
        tmp_path: Path) -> None:
    class ContextOwner:
        def __init__(self) -> None:
            self.issued = []

        def next_context(self):
            context = {"fixture_context_sequence": len(self.issued) + 1}
            self.issued.append(context)
            return context

    resource_owner = ContextOwner()
    cognition, fake = owner(tmp_path, comparison=True,
        allowed_source_kinds=("capability_registry",),
        resource_context_owner=resource_owner)
    first = cognition.run_tick(snapshot=snapshot(), tick_id="resource-context-seed")
    assert first.written_record_id
    comparison = cognition.run_tick(snapshot=snapshot(), tick_id="resource-context-comparison")
    assert comparison.changed_cognition_measurement_id
    assert [row["condition_id"] for row in
        cognition.experiments.load_run(comparison.changed_cognition_measurement_id)["conditions"]] == [
            "history_present", "history_withheld", "history_restored"]
    assert resource_owner.issued == fake.resource_contexts
    assert len(resource_owner.issued) == 3  # one owner-issued context per condition


def _reconstruct_progression_in_child(root: Path, receipts: Mapping[str, Any],
        request_refs: list[tuple[str, str]]) -> Mapping[str, Any]:
    """Reconstruct a task-family progression in a fresh interpreter."""
    receipt_path = root / "fixture-issued-invocation-receipts.json"
    receipt_bytes = json.dumps({receipt_id: receipt.to_dict()
        for receipt_id, receipt in receipts.items()}, sort_keys=True,
        separators=(",", ":")).encode("utf-8")
    if len(receipt_bytes) > 4 * 1024 * 1024:
        raise AssertionError("fixture receipt custody exceeded bounded test size")
    receipt_path.write_bytes(receipt_bytes)
    receipt_digest = hashlib.sha256(receipt_bytes).hexdigest()
    child_code = r'''
import hashlib, json, sys
from pathlib import Path
from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION)
from sentientos.resident_developmental_cognition import (
    ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionOwner)
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier

root, receipt_path = Path(sys.argv[1]), Path(sys.argv[2])
refs = json.loads(sys.argv[3])
raw = receipt_path.read_bytes()
assert len(raw) <= 4 * 1024 * 1024
assert hashlib.sha256(raw).hexdigest() == sys.argv[4]
receipts = json.loads(raw.decode("utf-8"))
assert json.dumps(receipts, sort_keys=True, separators=(",", ":")).encode("utf-8") == raw
from sentientos.governed_local_model_invocation import validate_receipt
class PersistedFixtureReceiptVerifier:
    def verify_persisted_invocation_receipt(self, receipt_id, receipt_digest, **expected):
        value = receipts[receipt_id]
        valid, reasons = validate_receipt(value)
        assert valid, reasons
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
            "output_size_bytes", "resource_allocation_digest", "resource_attempt_id",
            "resource_consumption_receipt_digests", "resource_linkage_digest",
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
    child = subprocess.run([sys.executable, "-c", child_code, str(root), str(receipt_path),
        json.dumps(request_refs), receipt_digest], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, check=True)
    return json.loads(child.stdout.strip().splitlines()[-1])


def _run_family_episode_in_child(root: Path, *, acquisition_request_digest: str,
        request_id: str, request_digest: str,
        active_model_identity: Mapping[str, Any] | None = None,
        publish_session: bool = False,
        prior_request_refs: tuple[tuple[str, str], ...] = (),
        tamper_receipt_id: str | None = None) -> Mapping[str, Any]:
    """Run transfer in a fresh process through installation-scoped production readers.

    Inference itself is issued by a deterministic fixture; the persisted receipt
    verifier and storage path are the normal installation-owned implementations.
    """
    installation_root = root / "installation-custody"
    tampered_path: Path | None = None
    original_receipt: bytes | None = None
    if tamper_receipt_id is not None:
        if (not tamper_receipt_id.startswith("lmrec-") or len(tamper_receipt_id) != 30):
            raise AssertionError("invalid fixture receipt identity for tamper control")
        registry = InstallationStateRegistry._for_testing(installation_root)
        installation_handle = registry.open(
            InstallationIdentity("task-family-transfer-installation"), create=False)
        tampered_path = (installation_handle.root / "local-model" / "resident-cognitive-serving"
            / "inference" / "receipts" / (tamper_receipt_id + ".json"))
        original_receipt = tampered_path.read_bytes()
        altered = json.loads(original_receipt.decode("utf-8"))
        altered["request"]["request_digest"] = "sha256:" + "f" * 64
        tampered_path.write_text(json.dumps(altered, sort_keys=True, indent=2) + "\n",
            encoding="utf-8")
    child_code = r'''
import importlib.util, json, sys
from pathlib import Path

root, installation_root = Path(sys.argv[1]), Path(sys.argv[2])
request_id, request_digest = sys.argv[3:5]
prior_request_refs = json.loads(sys.argv[5])
active_model_identity = json.loads(sys.argv[6])
publish_session = sys.argv[7] == "true"
test_path = Path.cwd() / "tests" / "test_resident_developmental_cognition.py"
spec = importlib.util.spec_from_file_location("fixture_cognition_tests", test_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
invoker = module.InstallationCustodyFakeInvoker()
invoker.active_model_identity = active_model_identity
module._bind_fixture_installation_custody(root, invoker, publish_session=publish_session)
invoker.objective_mode = "derive_from_admitted_family"
invoker.objective_plan_root = root / "state" / "developmental_experiments" / "protocols"
owner, _ = module.owner(root, comparison=True, invoker=invoker,
    allowed_source_kinds=("capability_registry", "embodiment"), max_selected_facts=16)
request = module.load_objective_request(root / "state")
assert request is not None
assert request.get("request_id") == request_id
assert request.get("request_digest") == request_digest
task = module.objective_task_for_request(request)
try:
    result = owner.run_objective_intervention_once(snapshot=module.snapshot(),
        tick_id=request_id, objective_task=task, request_id=request_id,
        request_digest=request_digest)
except Exception as exc:
    print(json.dumps({"status": "rejected", "reason": str(exc),
        "new_invocations": len(invoker.requests)}, sort_keys=True))
    raise SystemExit(0)
run = owner.experiments.load_run(str(result.changed_cognition_measurement_id))
prompts = {request.correlation_id.rsplit(":", 1)[-1]: request.prompt
    for request in invoker.requests
    if request.purpose == "resident_developmental_history_intervention_experiment"
    and request.correlation_id.startswith(request_id + ":")
    and request.prompt.lstrip().startswith("{")}
progression = owner.verified_objective_task_family_progression(request_refs=(
    *(tuple(item) for item in prior_request_refs), (request_id, request_digest)))
print(json.dumps({"fresh_process": True, "fixture_only": True,
    "run": run, "progression": progression, "prompts": prompts}, sort_keys=True))
'''
    try:
        child = subprocess.run([sys.executable, "-c", child_code, str(root),
            str(installation_root), request_id, request_digest,
            json.dumps(prior_request_refs or (("episode-acquisition",
                acquisition_request_digest),)),
            json.dumps(dict(active_model_identity or {})),
            "true" if publish_session else "false"], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True)
        if child.returncode != 0:
            raise AssertionError("fresh-process fixture episode failed: " + child.stderr[-4000:])
        result = json.loads(child.stdout.strip().splitlines()[-1])
        if tampered_path is not None:
            assert result == {"status": "rejected",
                "reason": "cognition_invocation_receipt_reconciliation_failed",
                "new_invocations": 0}
            return {"rejected_before_owner_recovery": True, "fixture_only": True}
        return result
    finally:
        if tampered_path is not None and original_receipt is not None:
            tampered_path.write_bytes(original_receipt)


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


def epistemic_projection(root: Path, *, with_evidence: bool = False):
    epistemic = PersistentEpistemicStateOwner(root, allowed_namespaces=["embodiment"])
    proposition = make_proposition(namespace="embodiment", subject="body:g1", predicate="healthy",
        object_value=True, polarity="positive", qualifiers={}, temporal_scope={"kind":"prior"},
        context_scope={}, proposition_class="descriptive")
    epistemic.register_proposition(proposition)
    binding_ids = []
    stance = "unknown"
    if with_evidence:
        support = make_evidence_binding(proposition_id=proposition.proposition_id,
            source_artifact_id="prior-epistemic-support",
            source_digest="sha256:" + "1" * 64,
            source_schema="sentientos.fixture_observation:v1", source_class="fixture",
            observation_time="2026-01-01T00:00:00Z", evidence_relation="supports",
            dependency_kind="independently_sourced_observation",
            dependency_group="prior-support", upstream_binding_ids=(), freshness="current",
            reliability_posture="verified")
        epistemic.bind_evidence(support)
        binding_ids = [support.binding_id]
        stance = "supported"
    state, _ = epistemic.commit_update(proposition_id=proposition.proposition_id,
        expected_predecessor_digest=None, stance=stance, reason="initialization",
        active_binding_ids=binding_ids, added_binding_ids=binding_ids,
        correlation_id="prior", tick=1, recorded_at="2026-01-01T00:00:00Z")
    projection = epistemic.cognitive_projection(max_states=1)
    assert projection is not None
    return projection, proposition, state


def test_meaning_bearing_epistemic_packets_reach_actual_inference_request(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import sentientos.resident_developmental_cognition as cognition_module
    monkeypatch.setattr(cognition_module, "MAX_RESIDENT_COGNITION_INPUT_CHARS", 16_000)
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


def test_projection_bound_omissions_reach_inference_context(tmp_path: Path) -> None:
    from sentientos.resident_developmental_cognition import _digest as cognition_digest
    epistemic = PersistentEpistemicStateOwner(tmp_path / "epistemic",
        allowed_namespaces=["embodiment"])
    propositions = [make_proposition(namespace="embodiment", subject=f"sensor:{index}",
        predicate="reports_state", object_value=index, polarity="positive",
        qualifiers={}, temporal_scope={"window": "prior"}, context_scope={},
        proposition_class="descriptive") for index in range(2)]
    for index, proposition_value in enumerate(propositions, start=1):
        epistemic.register_proposition(proposition_value)
        epistemic.commit_update(proposition_id=proposition_value.proposition_id,
            expected_predecessor_digest=None, stance="unknown", reason="initialization",
            active_binding_ids=[], correlation_id=f"bounded:{index}", tick=index,
            recorded_at=f"2026-01-01T00:00:0{index}Z")
    projection = epistemic.cognitive_projection(max_states=1, current_tick=3)
    assert isinstance(projection, MeaningBearingEpistemicCognitiveProjection)
    assert projection.omission_manifest is not None
    composition, fake = owner(tmp_path / "cognition")
    result = composition.run_tick(snapshot=snapshot(), tick_id="projection-omission",
        prior_epistemic_state=projection)
    request = next(item for item in fake.requests
        if item.purpose == "resident_developmental_retrieval_cognition")
    prior = json.loads(request.prompt)["prior_epistemic_state"]
    assert prior["schema_version"] == "sentientos.epistemic_cognitive_projection:v3"
    assert cognition_digest(prior["projection_omission_manifest"]) == cognition_digest(
        projection.omission_manifest)
    assert prior["projection_omission_manifest"]["omitted_state_count"] == 1
    recovered, _ = owner(tmp_path / "cognition")
    observation = recovered.verified_cognition_observation(
        result.cognition_observation_ids[0])
    assert observation["epistemic_projection_digest"] == projection.projection_digest
    assert observation["epistemic_projection_context_digest"] == cognition_digest(prior)
    assert observation["epistemic_prompt_digest"] == "sha256:" + request.prompt_digest


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


def test_semantic_packets_are_whole_and_omissions_are_bound_under_input_budget(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import sentientos.resident_developmental_cognition as cognition_module
    monkeypatch.setattr(cognition_module, "MAX_RESIDENT_COGNITION_INPUT_CHARS", 16_000)
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
    assert all(by_request[request.request_id]["schema_version"].endswith(":v7")
        and by_request[request.request_id]["developmental_history_selection"]
            == request.upstream_evidence["developmental_history_selection"]
        for request in cognition)
    assert result.changed_cognition_measurement_id is not None


def test_saturated_history_binding_keeps_ranked_complete_suffix_and_omission_identity(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Variable packet sizes cannot make a newer weak record displace stronger history."""
    import sentientos.resident_developmental_cognition as cognition_module

    # The tuple represents checkpoint order after task relevance ranking:
    # recent irrelevant filler, a disjoint family example, a positive overlap,
    # then a more recent adverse example tied on overlap with the older one.
    records = (
        {"record_id": "unrelated-recent", "record_digest": "u" * 71,
            "padding": 5200, "outcome": "unrelated"},
        {"record_id": "family-disjoint", "record_digest": "d" * 71,
            "padding": 350, "outcome": "correct-no-overlap"},
        {"record_id": "older-positive-overlap", "record_digest": "p" * 71,
            "padding": 900, "outcome": "correct-overlap"},
        {"record_id": "newer-adverse-overlap", "record_digest": "a" * 71,
            "padding": 1600, "outcome": "incorrect-overlap"},
    )

    def packet(record, *, include_source_evidence_context=True,
                compact_for_input_budget=False, task_family_id=None,
                target_model_identity=None):
        del include_source_evidence_context, task_family_id, target_model_identity
        padding = record["padding"]
        if compact_for_input_budget:
            padding = min(padding, 1200)
        return {"record_id": record["record_id"],
            "record_digest": record["record_digest"],
            "task_relevant_experience": [{"evaluator_correct":
                record["outcome"].startswith("correct"), "outcome": record["outcome"]}],
            "packet_payload": "x" * padding}

    monkeypatch.setattr(cognition_module, "_history_context_packet", packet)
    context = {"instruction": "Use history as non-authoritative evidence.",
        "current_evidence": {"held_out_probe": 17},
        "developmental_history": [],
        "developmental_history_task_family_id": "integer_affine_prediction",
        "developmental_history_retrieval_policy_id":
            "task_family_probe_overlap_then_recency_fill:v2"}

    def bind(capacity: int, present: bool = True):
        monkeypatch.setattr(cognition_module, "MAX_RESIDENT_COGNITION_INPUT_CHARS", capacity)
        return _bind_history_and_epistemic_context(context=context, records=records,
            projection=None, history_present=present)

    def minimum_capacity_for(count: int) -> int:
        low, high = 1, 16_000
        while low < high:
            middle = (low + high) // 2
            try:
                selected = bind(middle)[3]
            except ResidentDevelopmentalCognitionError as exc:
                if str(exc) != "cognition_input_budget_exceeded":
                    raise
                selected = ()
            if len(selected) >= count:
                high = middle
            else:
                low = middle + 1
        return low

    prior_ids = tuple(record["record_id"] for record in records)
    observed_counts = []
    for count in (1, 2, 3, 4):
        capacity = minimum_capacity_for(count)
        bound, metadata, prompt, selected_ids, selected_digests = bind(capacity)
        assert len(selected_ids) == count
        assert selected_ids == prior_ids[-count:]
        selection = metadata["developmental_history_selection"]
        assert tuple(item["record_id"] for item in selection["selected_records"]) == selected_ids
        assert tuple(item["record_id"] for item in selection["omitted_records"]) == prior_ids[:-count]
        assert selection["omission_reason"] == ("inference_input_budget"
            if count < len(records) else None)
        assert selection["omitted_records_digest"] == "sha256:" + digest_payload(
            selection["omitted_records"])
        assert all(digest == record["record_digest"] for digest, record in
            zip(selected_digests, records[-count:]))
        prompt_value = json.loads(prompt)
        admitted_packets = prompt_value["developmental_history"]
        assert tuple(item["record_id"] for item in admitted_packets) == selected_ids
        admitted_outcomes = [item["task_relevant_experience"][0]["outcome"]
            for item in admitted_packets]
        assert admitted_outcomes == [record["outcome"] for record in records[-count:]]
        assert not (set(record["outcome"] for record in records[:-count])
            & set(admitted_outcomes))
        assert bound["developmental_history_selection"]["selected_records"] == \
            selection["selected_records"]
        repeated = bind(capacity)
        assert repeated[1]["developmental_history_selection"] == selection
        observed_counts.append(count)
    assert observed_counts == [1, 2, 3, 4]

    withheld_bound, withheld_metadata, withheld_prompt, withheld_ids, _ = bind(
        minimum_capacity_for(1), present=False)
    assert withheld_ids == ()
    assert withheld_bound["developmental_history"] == []
    assert all(record_id not in withheld_prompt for record_id in prior_ids)
    assert withheld_metadata["developmental_history_selection"]["selected_records"] == []
    assert len(withheld_metadata["developmental_history_selection"]["omitted_records"]) == 4


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


def test_sentientosd_rejects_unknown_epistemic_tick_before_owner_reads(
    tmp_path: Path,
) -> None:
    class ProjectionSpy:
        calls = 0

        def cognitive_projection(self, **_kwargs):
            self.calls += 1
            raise AssertionError("uncertain tick must not select epistemic history")

    class CognitionSpy:
        calls = 0

        def run_tick(self, **_kwargs):
            self.calls += 1
            raise AssertionError("uncertain tick must not reach cognition")

    tick = "2026-01-03T00:00:00-00:00"
    projection_owner = ProjectionSpy()
    cognition_owner = CognitionSpy()
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime-unknown-tick",
        resident_developmental_owner=cognition_owner,  # type: ignore[arg-type]
        epistemic_state_owner=projection_owner,  # type: ignore[arg-type]
        epistemic_state_config={
            "status": "configured", "max_cognitive_projection_count": 1,
            "cognitive_consumption_enabled": True,
        },
    )
    surfaces.build_world_state_board(tick_id=tick)

    feedback = surfaces.run_resident_developmental_cognition(tick_id=tick)

    assert feedback["status"] == "degraded"
    assert feedback["reason"] == "ValueError:resident_cognition_tick_offset_unknown"
    assert feedback["write_performed"] is False
    assert projection_owner.calls == 0
    assert cognition_owner.calls == 0


def test_sentientosd_rejects_unrepresentable_epistemic_tick_before_owner_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ProjectionSpy:
        calls = 0

        def cognitive_projection(self, **_kwargs):
            self.calls += 1
            raise AssertionError("unrepresentable tick must not select history")

    class CognitionSpy:
        calls = 0

        def run_tick(self, **_kwargs):
            self.calls += 1
            raise AssertionError("unrepresentable tick must not reach cognition")

    tick = "2026-01-03T00:00:00+00:00"
    projection_owner = ProjectionSpy()
    cognition_owner = CognitionSpy()
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime-overflow-tick",
        resident_developmental_owner=cognition_owner,  # type: ignore[arg-type]
        epistemic_state_owner=projection_owner,  # type: ignore[arg-type]
        epistemic_state_config={
            "status": "configured", "max_cognitive_projection_count": 1,
            "cognitive_consumption_enabled": True,
        },
    )
    surfaces.build_world_state_board(tick_id=tick)

    class UnrepresentableInstant:
        tzinfo = object()

        def utcoffset(self):
            from datetime import timedelta
            return timedelta(0)

        def timestamp(self) -> float:
            raise OverflowError("platform timestamp range")

    class DatetimeShim:
        @staticmethod
        def fromisoformat(_value: str) -> UnrepresentableInstant:
            return UnrepresentableInstant()

    monkeypatch.setattr("sentientosd.datetime", DatetimeShim)

    feedback = surfaces.run_resident_developmental_cognition(tick_id=tick)

    assert feedback["status"] == "degraded"
    assert feedback["reason"] == "ValueError:resident_cognition_tick_unrepresentable"
    assert feedback["write_performed"] is False
    assert projection_owner.calls == 0
    assert cognition_owner.calls == 0


@pytest.mark.parametrize("tick", [
    "2026-01-03T00:00:00-00:00",
    "9999-12-31T23:59:59+00:00",
])
def test_sentientosd_rejects_uncertain_self_model_tick_before_owner_reads(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tick: str,
) -> None:
    from sentientos.longitudinal_self_model import LongitudinalSelfModelRuntimeConfig

    class ProjectionSpy:
        calls = 0

        def cognitive_projection(self, **_kwargs):
            self.calls += 1
            raise AssertionError("uncertain tick must not select self-model history")

    class CognitionSpy:
        calls = 0

        def run_tick(self, **_kwargs):
            self.calls += 1
            raise AssertionError("uncertain tick must not reach cognition")

    projection_owner = ProjectionSpy()
    cognition_owner = CognitionSpy()
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime-self-model-uncertain-tick",
        resident_developmental_owner=cognition_owner,  # type: ignore[arg-type]
        longitudinal_self_model_owner=projection_owner,  # type: ignore[arg-type]
    )
    surfaces._longitudinal_self_model_config = LongitudinalSelfModelRuntimeConfig(
        enabled=True, custody_root=tmp_path / "self-model", cognitive_consumption_enabled=True,
        max_projection_claims=1, allowed_predicates=("health",), installation_id="fixture",
    )
    surfaces.build_world_state_board(tick_id=tick)
    if tick.endswith("+00:00"):
        from datetime import timedelta

        class UnrepresentableInstant:
            tzinfo = object()

            def utcoffset(self):
                return timedelta(0)

            def timestamp(self) -> float:
                raise OverflowError("platform timestamp range")

        class DatetimeShim:
            @staticmethod
            def fromisoformat(_value: str) -> UnrepresentableInstant:
                return UnrepresentableInstant()

        monkeypatch.setattr("sentientosd.datetime", DatetimeShim)

    feedback = surfaces.run_resident_developmental_cognition(tick_id=tick)

    assert feedback["status"] == "degraded"
    expected_reason = ("ValueError:resident_cognition_tick_offset_unknown"
        if tick.endswith("-00:00")
        else "ValueError:resident_cognition_tick_unrepresentable")
    assert feedback["reason"] == expected_reason
    assert feedback["write_performed"] is False
    assert projection_owner.calls == 0
    assert cognition_owner.calls == 0


def test_sentientosd_rejects_unknown_epistemic_write_tick_before_runtime(
    tmp_path: Path,
) -> None:
    class EpistemicDevelopmentSpy:
        calls = 0

        def process_snapshot(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("uncertain tick must not timestamp epistemic updates")

    tick = "2026-01-03T00:00:00-00:00"
    runtime = EpistemicDevelopmentSpy()
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime-epistemic-unknown-tick",
        epistemic_development_runtime=runtime,  # type: ignore[arg-type]
    )
    surfaces.build_world_state_board(tick_id=tick)

    feedback = surfaces.run_epistemic_development(tick_id=tick)

    assert feedback["status"] == "degraded"
    assert feedback["reason"] == (
        "ValueError:resident_epistemic_development_tick_offset_unknown")
    assert feedback["authority"] is False
    assert feedback["next_tick_only"] is True
    assert runtime.calls == 0


def test_sentientosd_rejects_unrepresentable_epistemic_write_tick_before_runtime(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EpistemicDevelopmentSpy:
        calls = 0

        def process_snapshot(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("unrepresentable tick must not timestamp updates")

    tick = "2026-01-03T00:00:00+00:00"
    runtime = EpistemicDevelopmentSpy()
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime-epistemic-overflow-tick",
        epistemic_development_runtime=runtime,  # type: ignore[arg-type]
    )
    surfaces.build_world_state_board(tick_id=tick)

    class UnrepresentableInstant:
        tzinfo = object()

        def utcoffset(self):
            from datetime import timedelta
            return timedelta(0)

        def timestamp(self) -> float:
            raise OverflowError("platform timestamp range")

        def isoformat(self) -> str:
            return tick

    class DatetimeShim:
        @staticmethod
        def fromisoformat(_value: str) -> UnrepresentableInstant:
            return UnrepresentableInstant()

    monkeypatch.setattr("sentientosd.datetime", DatetimeShim)

    feedback = surfaces.run_epistemic_development(tick_id=tick)

    assert feedback["status"] == "degraded"
    assert feedback["reason"] == (
        "ValueError:resident_epistemic_development_tick_unrepresentable")
    assert feedback["authority"] is False
    assert feedback["next_tick_only"] is True
    assert runtime.calls == 0


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
    assert value["schema_version"] == "sentientos.resident_cognition_observation:v7"
    value.pop("observation_id")
    value.pop("observation_digest")
    value.pop("developmental_history_selection")
    for field in ("resource_allocation_digest", "resource_attempt_id",
            "resource_consumption_receipt_digests", "resource_linkage_digest"):
        value.pop(field)
    value["schema_version"] = "sentientos.resident_cognition_observation:v5"
    digest = "sha256:" + digest_payload(value)
    observation_id = "devcog-" + digest[7:31]
    value["observation_id"] = observation_id
    value["observation_digest"] = digest
    migrated_path = path.with_name(observation_id + ".json")
    migrated_path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    migrated_path.chmod(0o600)
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
    assert value["schema_version"] == "sentientos.resident_cognition_observation:v7"
    value.pop("observation_id")
    value.pop("observation_digest")
    for field in ("resource_allocation_digest", "resource_attempt_id",
            "resource_consumption_receipt_digests", "resource_linkage_digest"):
        value.pop(field)
    value["schema_version"] = "sentientos.resident_cognition_observation:v6"
    selection = value["developmental_history_selection"]
    selection["retrieval_policy_id"] = "task_family_relevant_then_recency_fill:v1"
    selection["task_family_id"] = "integer_affine_prediction"
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
    substituted_path.chmod(0o600)
    path.unlink()

    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="cognition_history_selection_invocation_binding_mismatch"):
        composition._recover_observation_ticks(include_records=True)


def test_rehashed_v7_history_selection_substitution_fails_receipt_reconciliation(
        tmp_path: Path) -> None:
    invoker = SessionBoundFakeInvoker()
    composition, _ = owner(tmp_path, comparison=True, invoker=invoker)
    composition.run_tick(snapshot=snapshot(), tick_id="selection-source")
    composition.run_tick(snapshot=snapshot(2), tick_id="selection-comparison")
    path = next(path for path in composition.observations_root.glob("*.json")
        if json.loads(path.read_text(encoding="utf-8")).get("condition_id") == "history_present")
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["schema_version"] == "sentientos.resident_cognition_observation:v7"
    selection = value["developmental_history_selection"]
    assert len(selection["selected_records"]) == 1
    replacement = "sha256:" + "0" * 64
    selection["available_records"][0]["record_digest"] = replacement
    selection["selected_records"][0]["record_digest"] = replacement
    value["retrieved_record_digests"][0] = replacement
    selection_semantic = {key: item for key, item in selection.items()
        if key != "selection_digest"}
    selection["selection_digest"] = "sha256:" + digest_payload(selection_semantic)
    value.pop("observation_id")
    value.pop("observation_digest")
    digest = "sha256:" + digest_payload(value)
    observation_id = "devcog-" + digest[7:31]
    value["observation_id"] = observation_id
    value["observation_digest"] = digest
    substituted_path = path.with_name(observation_id + ".json")
    substituted_path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    substituted_path.chmod(0o600)
    path.unlink()

    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="cognition_history_selection_invocation_binding_mismatch"):
        composition._recover_observation_ticks(include_records=True)


def test_admitted_embodied_consequence_conditions_later_strategy_comparison(
        tmp_path: Path) -> None:
    """A real admitted developmental record reaches the existing review-only strategy experiment."""
    from dataclasses import asdict
    from datetime import timedelta
    from sentientos.avatar_authoring import renderer_handoff
    from sentientos.embodied_consequence import (
        ConsequenceStore, SyntheticIndependentObserver, SyntheticRenderer,
        evaluate_consequence, make_expectation, run_strategy_experiment,
        make_strategy_proposal, strategy_prompt_schema_digest,
        build_operator_codex_strategy_multi_event_packets,
            build_strategy_decision_quality_preregistration,
        score_strategy_experiment, score_strategy_decision_quality,
        strategy_decision_quality_world_state_record,
        world_state_records as consequence_world_state_records,
        digest as consequence_digest,
    )
    from sentientos.resident_developmental_writeback import (
        MAX_STRATEGY_QUALITY_SELECTED_EVIDENCE_BYTES,
    )

    event_start = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    event_observed = (datetime.now(timezone.utc) - timedelta(minutes=9)).isoformat()
    handoff = renderer_handoff({"installation_identity": "fixture-installation",
        "body_identity": "fixture-body", "body_generation": 2,
        "artifact_sha256": "sha256:artifact", "manifest_digest": "sha256:manifest",
        "pointer_digest": "sha256:pointer"}, renderer_interface_id="renderer:fixture:v1",
        requested_pose="wave", requested_expression="neutral",
        correlation_id="developmental-strategy-source", commanded_at=event_start)
    expectation = make_expectation(installation_body_id="fixture-installation",
        body_id="fixture-body", body_generation=2, body_manifest_digest="sha256:manifest",
        handoff_id=handoff["handoff_id"], handoff_digest=handoff["handoff_digest"],
        renderer_interface_id="renderer:fixture:v1", requested={"pose": "wave"},
        predicted_observables={"pose": "wave"}, observable_fields=("pose",),
        comparison_policy={"pose": {"kind": "exact"}},
        expected_observation_source_class="synthetic_independent_fixture",
        correlation_id="developmental-strategy-source", causal_principal_binding_digest=None,
        created_at=event_start,
        expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    report = SyntheticRenderer(applied={"pose": "wave"}, started_at=event_start,
        completed_at=(datetime.now(timezone.utc) - timedelta(minutes=9, seconds=30)).isoformat()
        ).render_test(handoff)
    observation = SyntheticIndependentObserver(observer_id="separate-fixture-observer",
        observed={"pose": "idle"}, observed_at=event_observed).observe(
            expectation=expectation, handoff=handoff, report=report)
    attribution, comparison = evaluate_consequence(expectation=expectation,
        handoff=handoff, current_body={"installation_identity": "fixture-installation",
            "body_identity": "fixture-body", "body_generation": 2,
            "artifact_sha256": "sha256:artifact", "manifest_digest": "sha256:manifest",
            "pointer_digest": "sha256:pointer"}, renderer_report=report,
        observation=observation, evaluated_at=event_observed)
    assert attribution["classification"] == "expectation_contradicted"
    assert attribution["causal_attribution_posture"] == "external_interference_possible"
    assert attribution["effect_proven"] is False

    source_records = consequence_world_state_records(
        expectation=expectation, handoff=handoff, renderer_report=report,
        observation=observation, attribution=attribution, comparison=comparison)
    source_world = WorldStateBoardBuilder().build([row for row in source_records
        if row.get("source_id") == attribution["attribution_id"]])
    cognition_invoker = SessionBoundFakeInvoker()
    cognition, _ = owner(tmp_path / "resident", invoker=cognition_invoker,
        allowed_source_kinds=("embodiment",), max_selected_facts=16)
    admitted = cognition.run_tick(snapshot=source_world,
        tick_id="strategy-consequence-admission")
    assert admitted.written_record_id
    durable_record = cognition.writeback.store.get(admitted.written_record_id)
    history_record = asdict(durable_record)
    source_facts = [fact for fact in history_record["candidate"]["selected_facts"]
        if fact.get("source", {}).get("source_id") == attribution["attribution_id"]]
    assert len(source_facts) == 1
    assert source_facts[0]["payload"] == attribution
    assert history_record["current_truth"] is False
    assert history_record["authority"] is False
    assert history_record["epistemic_posture"] == \
        "historical_interpretation_not_current_truth"

    # A distinct later source event supplies corrective evidence through the
    # same World-State, interpretation, scoped admission, and durable store.
    correction_start = (datetime.now(timezone.utc) - timedelta(minutes=8)).isoformat()
    correction_reported = (datetime.now(timezone.utc) - timedelta(minutes=7, seconds=30)).isoformat()
    correction_observed = (datetime.now(timezone.utc) - timedelta(minutes=7)).isoformat()
    correction_handoff = renderer_handoff({
        "installation_identity":"fixture-installation","body_identity":"fixture-body",
        "body_generation":2,"artifact_sha256":"sha256:artifact",
        "manifest_digest":"sha256:manifest","pointer_digest":"sha256:pointer"},
        renderer_interface_id="renderer:fixture:v1",requested_pose="wave",
        requested_expression="neutral",correlation_id="developmental-strategy-correction",
        commanded_at=correction_start)
    correction_expectation = make_expectation(
        installation_body_id="fixture-installation",body_id="fixture-body",body_generation=2,
        body_manifest_digest="sha256:manifest",handoff_id=correction_handoff["handoff_id"],
        handoff_digest=correction_handoff["handoff_digest"],
        renderer_interface_id="renderer:fixture:v1",requested={"pose":"wave"},
        predicted_observables={"pose":"wave"},observable_fields=("pose",),
        comparison_policy={"pose":{"kind":"exact"}},
        expected_observation_source_class="synthetic_independent_fixture",
        correlation_id="developmental-strategy-correction",causal_principal_binding_digest=None,
        created_at=correction_start,
        expires_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    correction_renderer_report = SyntheticRenderer(applied={"pose":"wave"},
        started_at=correction_start,completed_at=correction_reported).render_test(correction_handoff)
    correction_observation = SyntheticIndependentObserver(
        observer_id="separate-correction-fixture-observer",observed={"pose":"wave"},
        observed_at=correction_observed).observe(expectation=correction_expectation,
            handoff=correction_handoff,report=correction_renderer_report)
    correction_attribution, correction_comparison = evaluate_consequence(
        expectation=correction_expectation,handoff=correction_handoff,
        current_body={"installation_identity":"fixture-installation",
            "body_identity":"fixture-body","body_generation":2,
            "artifact_sha256":"sha256:artifact","manifest_digest":"sha256:manifest",
            "pointer_digest":"sha256:pointer"},renderer_report=correction_renderer_report,
        observation=correction_observation,evaluated_at=correction_observed)
    assert correction_attribution["classification"] == "expectation_satisfied"
    assert correction_attribution["attribution_id"] != attribution["attribution_id"]
    correction_records = consequence_world_state_records(
        expectation=correction_expectation,handoff=correction_handoff,
        renderer_report=correction_renderer_report,observation=correction_observation,
        attribution=correction_attribution,comparison=correction_comparison)
    correction_world = WorldStateBoardBuilder().build([row for row in correction_records
        if row.get("source_id")==correction_attribution["attribution_id"]])
    correction_tick = cognition.run_tick(snapshot=correction_world,
        tick_id="strategy-corrective-consequence-admission")
    assert correction_tick.written_record_id
    correction_record = cognition.writeback.store.get(correction_tick.written_record_id)
    correction_source_facts = [fact for fact in correction_record.candidate["selected_facts"]
        if fact.get("source",{}).get("source_id")==correction_attribution["attribution_id"]]
    assert len(correction_source_facts)==1
    assert correction_source_facts[0]["payload"]==correction_attribution
    assert correction_record.created_at > durable_record.created_at
    assert correction_record.current_truth is False and correction_record.authority is False

    # Re-open canonical persistence and ask its real read-only verifier for
    # the completed inventory. No record or receipt is reconstructed by hand.
    reopened_inventory_owner, _ = owner(tmp_path / "resident",invoker=cognition_invoker,
        allowed_source_kinds=("embodiment",),max_selected_facts=16)
    verified_inventory = reopened_inventory_owner.writeback.inspect_completed_records()
    recovered_by_event = {}
    for recovered_record, recovered_receipt in verified_inventory:
        source_events = [fact["payload"] for fact in recovered_record.candidate["selected_facts"]
            if fact.get("payload",{}).get("schema_version") == attribution["schema_version"]]
        for source_event in source_events:
            recovered_by_event[source_event["attribution_id"]]=(recovered_record,recovered_receipt)
    assert set(recovered_by_event)=={attribution["attribution_id"],
        correction_attribution["attribution_id"]}
    assert recovered_by_event[attribution["attribution_id"]][0].record_id==durable_record.record_id
    assert recovered_by_event[correction_attribution["attribution_id"]][0].record_id==\
        correction_record.record_id
    assert all(receipt.storage_verified for _,receipt in recovered_by_event.values())

    # A newer event from a different renderer situation is retained as
    # irrelevant competition. Explicit relations remain operator-declared and
    # unverified; they may affect bounded selection without becoming truth.
    unrelated_start=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()
    unrelated_reported=(datetime.now(timezone.utc)-timedelta(minutes=4,seconds=30)).isoformat()
    unrelated_observed=(datetime.now(timezone.utc)-timedelta(minutes=4)).isoformat()
    unrelated_handoff=renderer_handoff({
        "installation_identity":"fixture-installation","body_identity":"fixture-body",
        "body_generation":2,"artifact_sha256":"sha256:artifact",
        "manifest_digest":"sha256:manifest","pointer_digest":"sha256:pointer"},
        renderer_interface_id="renderer:fixture:changed-environment:v1",
        requested_pose="turn",requested_expression="neutral",
        correlation_id="developmental-strategy-unrelated",commanded_at=unrelated_start)
    unrelated_expectation=make_expectation(
        installation_body_id="fixture-installation",body_id="fixture-body",body_generation=2,
        body_manifest_digest="sha256:manifest",handoff_id=unrelated_handoff["handoff_id"],
        handoff_digest=unrelated_handoff["handoff_digest"],
        renderer_interface_id="renderer:fixture:changed-environment:v1",
        requested={"pose":"turn"},predicted_observables={"pose":"turn"},
        observable_fields=("pose",),comparison_policy={"pose":{"kind":"exact"}},
        expected_observation_source_class="synthetic_independent_fixture",
        correlation_id="developmental-strategy-unrelated",causal_principal_binding_digest=None,
        created_at=unrelated_start,
        expires_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    unrelated_renderer_report=SyntheticRenderer(applied={"pose":"turn"},
        started_at=unrelated_start,completed_at=unrelated_reported).render_test(unrelated_handoff)
    unrelated_observation=SyntheticIndependentObserver(
        observer_id="separate-unrelated-fixture-observer",observed={"pose":"idle"},
        observed_at=unrelated_observed).observe(expectation=unrelated_expectation,
            handoff=unrelated_handoff,report=unrelated_renderer_report)
    unrelated_attribution,unrelated_comparison=evaluate_consequence(
        expectation=unrelated_expectation,handoff=unrelated_handoff,
        current_body={"installation_identity":"fixture-installation",
            "body_identity":"fixture-body","body_generation":2,
            "artifact_sha256":"sha256:artifact","manifest_digest":"sha256:manifest",
            "pointer_digest":"sha256:pointer"},renderer_report=unrelated_renderer_report,
        observation=unrelated_observation,evaluated_at=unrelated_observed)
    unrelated_records=consequence_world_state_records(expectation=unrelated_expectation,
        handoff=unrelated_handoff,renderer_report=unrelated_renderer_report,
        observation=unrelated_observation,attribution=unrelated_attribution,
        comparison=unrelated_comparison)
    unrelated_world=WorldStateBoardBuilder().build([row for row in unrelated_records
        if row.get("source_id")==unrelated_attribution["attribution_id"]])
    unrelated_tick=cognition.run_tick(snapshot=unrelated_world,
        tick_id="strategy-unrelated-consequence-admission")
    assert unrelated_tick.written_record_id

    # A fourth genuinely admitted event is unresolved because only the
    # renderer reports completion; no independent observer is supplied.
    unresolved_start=(datetime.now(timezone.utc)-timedelta(minutes=3)).isoformat()
    unresolved_reported=(datetime.now(timezone.utc)-timedelta(minutes=2,seconds=30)).isoformat()
    unresolved_eval=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
    unresolved_handoff=renderer_handoff({
        "installation_identity":"fixture-installation","body_identity":"fixture-body",
        "body_generation":2,"artifact_sha256":"sha256:artifact",
        "manifest_digest":"sha256:manifest","pointer_digest":"sha256:pointer"},
        renderer_interface_id="renderer:fixture:unobserved:v1",
        requested_pose="turn",requested_expression="neutral",
        correlation_id="developmental-strategy-unobserved",commanded_at=unresolved_start)
    unresolved_expectation=make_expectation(
        installation_body_id="fixture-installation",body_id="fixture-body",body_generation=2,
        body_manifest_digest="sha256:manifest",handoff_id=unresolved_handoff["handoff_id"],
        handoff_digest=unresolved_handoff["handoff_digest"],
        renderer_interface_id="renderer:fixture:unobserved:v1",
        requested={"pose":"turn"},predicted_observables={"pose":"turn"},
        observable_fields=("pose",),comparison_policy={"pose":{"kind":"exact"}},
        expected_observation_source_class="synthetic_independent_fixture",
        correlation_id="developmental-strategy-unobserved",causal_principal_binding_digest=None,
        created_at=unresolved_start,
        expires_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    unresolved_report=SyntheticRenderer(applied={"pose":"turn"},started_at=unresolved_start,
        completed_at=unresolved_reported).render_test(unresolved_handoff)
    unresolved_attribution,unresolved_comparison=evaluate_consequence(
        expectation=unresolved_expectation,handoff=unresolved_handoff,
        current_body={"installation_identity":"fixture-installation",
            "body_identity":"fixture-body","body_generation":2,
            "artifact_sha256":"sha256:artifact","manifest_digest":"sha256:manifest",
            "pointer_digest":"sha256:pointer"},renderer_report=unresolved_report,
        observation=None,evaluated_at=unresolved_eval)
    assert unresolved_attribution["classification"]=="renderer_report_only"
    unresolved_records=consequence_world_state_records(
        expectation=unresolved_expectation,handoff=unresolved_handoff,
        renderer_report=unresolved_report,observation=None,
        attribution=unresolved_attribution,comparison=unresolved_comparison)
    unresolved_world=WorldStateBoardBuilder().build([row for row in unresolved_records
        if row.get("source_id")==unresolved_attribution["attribution_id"]])
    unresolved_tick=cognition.run_tick(snapshot=unresolved_world,
        tick_id="strategy-unresolved-consequence-admission")
    assert unresolved_tick.written_record_id

    # A later independent observation challenges the earlier corrective
    # result under the same action class, preserving the unresolved conflict.
    challenged_start=(datetime.now(timezone.utc)-timedelta(minutes=1,seconds=30)).isoformat()
    challenged_reported=(datetime.now(timezone.utc)-timedelta(minutes=1,seconds=15)).isoformat()
    challenged_observed=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
    challenged_handoff=renderer_handoff({
        "installation_identity":"fixture-installation","body_identity":"fixture-body",
        "body_generation":2,"artifact_sha256":"sha256:artifact",
        "manifest_digest":"sha256:manifest","pointer_digest":"sha256:pointer"},
        renderer_interface_id="renderer:fixture:v1",requested_pose="wave",
        requested_expression="neutral",correlation_id="developmental-strategy-challenge",
        commanded_at=challenged_start)
    challenged_expectation=make_expectation(
        installation_body_id="fixture-installation",body_id="fixture-body",body_generation=2,
        body_manifest_digest="sha256:manifest",handoff_id=challenged_handoff["handoff_id"],
        handoff_digest=challenged_handoff["handoff_digest"],
        renderer_interface_id="renderer:fixture:v1",requested={"pose":"wave"},
        predicted_observables={"pose":"wave"},observable_fields=("pose",),
        comparison_policy={"pose":{"kind":"exact"}},
        expected_observation_source_class="synthetic_independent_fixture",
        correlation_id="developmental-strategy-challenge",causal_principal_binding_digest=None,
        created_at=challenged_start,
        expires_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    challenged_report=SyntheticRenderer(applied={"pose":"wave"},started_at=challenged_start,
        completed_at=challenged_reported).render_test(challenged_handoff)
    challenged_observation=SyntheticIndependentObserver(
        observer_id="separate-challenge-fixture-observer",observed={"pose":"idle"},
        observed_at=challenged_observed).observe(expectation=challenged_expectation,
            handoff=challenged_handoff,report=challenged_report)
    challenged_attribution,challenged_comparison=evaluate_consequence(
        expectation=challenged_expectation,handoff=challenged_handoff,
        current_body={"installation_identity":"fixture-installation",
            "body_identity":"fixture-body","body_generation":2,
            "artifact_sha256":"sha256:artifact","manifest_digest":"sha256:manifest",
            "pointer_digest":"sha256:pointer"},renderer_report=challenged_report,
        observation=challenged_observation,evaluated_at=challenged_observed)
    assert challenged_attribution["classification"]=="expectation_contradicted"
    assert challenged_attribution["attribution_id"] not in {
        attribution["attribution_id"],correction_attribution["attribution_id"]}
    challenged_records=consequence_world_state_records(
        expectation=challenged_expectation,handoff=challenged_handoff,
        renderer_report=challenged_report,observation=challenged_observation,
        attribution=challenged_attribution,comparison=challenged_comparison)
    challenged_world=WorldStateBoardBuilder().build([row for row in challenged_records
        if row.get("source_id")==challenged_attribution["attribution_id"]])
    challenged_tick=cognition.run_tick(snapshot=challenged_world,
        tick_id="strategy-corrective-result-challenged-admission")
    assert challenged_tick.written_record_id
    reopened_inventory_owner, _ = owner(tmp_path / "resident",invoker=cognition_invoker,
        allowed_source_kinds=("embodiment",),max_selected_facts=16)
    five_event_inventory=reopened_inventory_owner.writeback.inspect_completed_records()
    assert len(five_event_inventory)==5
    assert len({record.record_id for record,_ in five_event_inventory})==5
    irrelevant_record_id=unrelated_tick.written_record_id

    strategy_situation={"situation_binding":"later-distinct-surface-transfer",
        "body_generation":2,"requested_at":datetime.now(timezone.utc).isoformat(),
        "environment":"changed renderer interface; new surface task",
        "independent_observation_available":False,"renderer_report_present":True}
    strategy_settings={"visible_model_name":"synthetic resident strategy fixture",
        "effort_setting":"fixed","generation_settings":{"temperature":0}}
    applicability={event_id:{"relation":"same_action_class",
        "declared_by":"scoped-test-operator","declared_at":strategy_situation["requested_at"],
        "rationale":"older event shares the later strategy action class"}
        for event_id in (attribution["attribution_id"],correction_attribution["attribution_id"],
            challenged_attribution["attribution_id"])}
    applicability[unrelated_attribution["attribution_id"]]={"relation":"operator_other",
        "declared_by":"scoped-test-operator","declared_at":strategy_situation["requested_at"],
        "rationale":"newer event occurred under a changed renderer interface"}
    assert set(strategy_settings)=={"visible_model_name","effort_setting","generation_settings"}
    assert len({source_record.record_id for source_record,_receipt in five_event_inventory})==5
    strategy_bundle=build_operator_codex_strategy_multi_event_packets(
        writeback=reopened_inventory_owner.writeback,
        history_record_ids=[source_record.record_id
            for source_record,_receipt in five_event_inventory],
        situation=strategy_situation,model_settings=strategy_settings,max_event_count=3,
        applicability_by_event=applicability)
    strategy_manifest=strategy_bundle["scorer_manifest"]
    selected_event_ids=[row["attribution"]["attribution_id"] for row in strategy_manifest["events"]]
    assert set(selected_event_ids)=={attribution["attribution_id"],
        correction_attribution["attribution_id"],challenged_attribution["attribution_id"]}
    expected_event_digests={attribution["attribution_id"]:attribution["attribution_digest"],
        correction_attribution["attribution_id"]:correction_attribution["attribution_digest"],
        challenged_attribution["attribution_id"]:challenged_attribution["attribution_digest"]}
    assert {row["attribution"]["attribution_id"]:row["attribution"]["attribution_digest"]
        for row in strategy_manifest["events"]}==expected_event_digests
    assert {row["event_id"]:row["event_digest"]
        for row in strategy_bundle["preregistration"]["selected_event_identities"]}==\
            expected_event_digests
    selected_source_record_ids={row["source_record_id"] for row in strategy_manifest["events"]}
    assert selected_source_record_ids=={durable_record.record_id,correction_record.record_id,
        challenged_tick.written_record_id}
    assert all(row["applicability"]["posture"]=="operator_declared_unverified"
        for row in strategy_manifest["events"])
    omission=strategy_bundle["preregistration"]["omitted_event_identities"]
    assert {row["event_id"] for row in omission}=={
        unrelated_attribution["attribution_id"],unresolved_attribution["attribution_id"]}
    omission_by_event={row["event_id"]:row for row in omission}
    assert omission_by_event[unrelated_attribution["attribution_id"]]["source_record_id"]==irrelevant_record_id
    assert omission_by_event[unresolved_attribution["attribution_id"]]["source_record_id"]==unresolved_tick.written_record_id
    assert omission_by_event[unrelated_attribution["attribution_id"]]["event_digest"]==unrelated_attribution["attribution_digest"]
    assert omission_by_event[unresolved_attribution["attribution_id"]]["event_digest"]==unresolved_attribution["attribution_digest"]
    omitted_record=next(source_record for source_record,_receipt in five_event_inventory
        if source_record.record_id==irrelevant_record_id)
    omitted_fact=next(fact for fact in omitted_record.candidate["selected_facts"]
        if fact.get("source",{}).get("source_id")==unrelated_attribution["attribution_id"])
    assert omission_by_event[unrelated_attribution["attribution_id"]]["source_record_digest"]==omitted_record.record_digest
    assert omission_by_event[unrelated_attribution["attribution_id"]]["source_fact_id"]==omitted_fact["fact_id"]
    unresolved_record=next(source_record for source_record,_receipt in five_event_inventory
        if source_record.record_id==unresolved_tick.written_record_id)
    unresolved_fact=next(fact for fact in unresolved_record.candidate["selected_facts"]
        if fact.get("source",{}).get("source_id")==unresolved_attribution["attribution_id"])
    assert omission_by_event[unresolved_attribution["attribution_id"]]["source_record_digest"]==unresolved_record.record_digest
    assert omission_by_event[unresolved_attribution["attribution_id"]]["source_fact_id"]==unresolved_fact["fact_id"]
    assert all(row["omission_reason"]=="bounded_event_selection" for row in omission)
    packets=strategy_bundle["subject_packets"]
    condition_by_packet=strategy_manifest["condition_by_packet_id"]
    assert len({consequence_digest(packet["current_situation"]) for packet in packets.values()})==1
    assert all(packet["model_settings"]==strategy_settings for packet in packets.values())
    assert all(not any(event_id in json.dumps(packet["current_situation"])
        for event_id in selected_event_ids+[unrelated_attribution["attribution_id"]])
        for packet in packets.values())
    assert all(not any(label in json.dumps(packet)
        for label in ("history_present","history_withheld","history_restored"))
        for packet in packets.values())
    assert {tuple(item["event_id"] for item in packet["historical_evidence"])
        for packet_id,packet in packets.items()
        if condition_by_packet[packet_id] in {"history_present","history_restored"}}=={
            tuple(selected_event_ids)}
    assert all(not packet["historical_evidence"] for packet_id,packet in packets.items()
        if condition_by_packet[packet_id]=="history_withheld")

    # Persist the preregistration and scorer custody before fixture cognition.
    protocol_root=tmp_path/"canonical-multi-event-strategy"
    protocol_root.mkdir()
    (protocol_root/"preregistration.json").write_text(
        json.dumps(strategy_bundle["preregistration"],sort_keys=True),encoding="utf-8")
    (protocol_root/"scorer_manifest.json").write_text(
        json.dumps(strategy_manifest,sort_keys=True),encoding="utf-8")
    subject_root=protocol_root/"subject_packets"
    subject_root.mkdir()
    for packet_id,packet in packets.items():
        (subject_root/f"{packet_id}.json").write_text(
            json.dumps(packet,sort_keys=True),encoding="utf-8")
    frozen_prereg=json.loads((protocol_root/"preregistration.json").read_text(encoding="utf-8"))
    frozen_manifest=json.loads((protocol_root/"scorer_manifest.json").read_text(encoding="utf-8"))

    class EvidenceOnlyStrategyFixture:
        def propose(self, packet):
            history=packet["historical_evidence"]
            # This deliberately overgeneralizes the newest admitted outcome;
            # it derives its mistake from supplied evidence and sees no label.
            if history:
                latest=max(history,key=lambda item:item["evaluated_at"])
                cited=[latest["event_id"]]
                repeats_success=(latest["classification"]=="expectation_satisfied")
                uncertainty="low" if repeats_success else "high"
                ask=not repeats_success
                rationale=("repeat the latest recorded successful action" if repeats_success
                    else "request observation after the latest contradiction")
            else:
                cited=[]
                uncertainty="high"
                ask=True
                rationale="request observation without historical evidence"
            return make_strategy_proposal(
                situation_binding=packet["current_situation"]["situation_binding"],
                body_generation=packet["current_situation"]["body_generation"],
                relevant_consequence_ids=tuple(cited),
                proposed_next_action_class=("repeat_latest" if history and repeats_success
                    else "observe"),
                requested_pose="wave",requested_expression="neutral",retry_prior_strategy=bool(history),
                alter_body_or_rig=False,more_observation_required=ask,
                distinguishes_renderer_and_observer=True,rationale=rationale,
                uncertainty=uncertainty,factual_assertions=())

    fixture=EvidenceOnlyStrategyFixture()
    proposals_by_condition={}
    for packet_id,packet in packets.items():
        proposal=fixture.propose(packet)
        proposals_by_condition[condition_by_packet[packet_id]]=proposal
    assert proposals_by_condition["history_present"]==proposals_by_condition["history_restored"]
    assert proposals_by_condition["history_present"]!=proposals_by_condition["history_withheld"]
    selected_sources=[{key:item[key] for key in ("attribution","source_record_id",
        "source_record_digest","source_fact_id","applicability")}
        for item in frozen_manifest["events"]]
    vector_results={condition:score_strategy_decision_quality(proposal=proposal,
        situation=strategy_situation,events=selected_sources,
        preregistration=frozen_manifest["decision_quality_preregistration"])
        for condition,proposal in proposals_by_condition.items()}
    import copy
    present_packet=next(packets[packet_id] for packet_id,condition in condition_by_packet.items()
        if condition=="history_present")
    before_challenge_packet=copy.deepcopy(present_packet)
    before_challenge_packet["historical_evidence"]=[item
        for item in before_challenge_packet["historical_evidence"]
        if item["event_id"]!=challenged_attribution["attribution_id"]]
    before_challenge_sources=[item for item in selected_sources
        if item["attribution"]["attribution_id"]!=challenged_attribution["attribution_id"]]
    before_challenge_proposal=EvidenceOnlyStrategyFixture().propose(before_challenge_packet)
    before_challenge_prereg=build_strategy_decision_quality_preregistration(
        situation=strategy_situation,events=before_challenge_sources)
    before_challenge_vector=score_strategy_decision_quality(
        proposal=before_challenge_proposal,situation=strategy_situation,
        events=before_challenge_sources,
        preregistration=before_challenge_prereg)
    before_challenge_status={row["criterion_id"]:row["status"]
        for row in before_challenge_vector["criteria"]}
    adverse_vector={row["criterion_id"]:row["status"]
        for row in vector_results["history_present"]["criteria"]}
    withheld_vector={row["criterion_id"]:row["status"]
        for row in vector_results["history_withheld"]["criteria"]}
    assert adverse_vector["uncertainty_under_conflicting_historical_outcomes"]=="pass"
    assert adverse_vector["requests_observation_when_current_evidence_is_incomplete"]=="pass"
    assert before_challenge_status["uncertainty_under_conflicting_historical_outcomes"]=="fail"
    assert before_challenge_status["requests_observation_when_current_evidence_is_incomplete"]=="fail"
    assert withheld_vector["requests_observation_when_current_evidence_is_incomplete"]=="pass"
    same_proposal_relabelled=score_strategy_decision_quality(
        proposal=proposals_by_condition["history_withheld"],situation=strategy_situation,
        events=selected_sources,preregistration=frozen_manifest["decision_quality_preregistration"])
    assert same_proposal_relabelled==vector_results["history_withheld"]
    source_relative_score=score_strategy_experiment(
        proposals=(proposals_by_condition["history_present"],
            proposals_by_condition["history_withheld"],
            proposals_by_condition["history_restored"]),situation=strategy_situation,
        consequence_events=selected_sources)
    assert source_relative_score["synthetic_event_created"] is False
    assert source_relative_score["improvement_claimed"] is False
    score_archive={"score":source_relative_score,"decision_quality":{
        condition:result for condition,result in vector_results.items()},
        "longitudinal_correction_comparison":{
            "before_challenge":before_challenge_vector,
            "after_challenge":vector_results["history_present"]},
        "condition_by_packet_id":condition_by_packet,
        "selected_event_identities":frozen_prereg["selected_event_identities"],
        "omitted_event_identities":frozen_prereg["omitted_event_identities"]}
    (protocol_root/"fixture_scores.json").write_text(
        json.dumps(score_archive,sort_keys=True),encoding="utf-8")
    recovered_archive=json.loads((protocol_root/"fixture_scores.json").read_text(
        encoding="utf-8"))
    assert recovered_archive["selected_event_identities"]==\
        frozen_prereg["selected_event_identities"]
    assert recovered_archive["omitted_event_identities"]==\
        frozen_prereg["omitted_event_identities"]

    class ConflictAwareStrategyFixture:
        def propose(self, packet):
            history=packet["historical_evidence"]
            cited=tuple(item["event_id"] for item in history)
            return make_strategy_proposal(
                situation_binding=packet["current_situation"]["situation_binding"],
                body_generation=packet["current_situation"]["body_generation"],
                relevant_consequence_ids=cited,proposed_next_action_class="observe",
                requested_pose="wave",requested_expression="neutral",retry_prior_strategy=False,
                alter_body_or_rig=False,more_observation_required=True,
                distinguishes_renderer_and_observer=True,
                rationale=("preserve conflicting event provenance and observe" if history
                    else "observe without historical event claims"),
                uncertainty="high",factual_assertions=())

    positive_by_condition={condition:ConflictAwareStrategyFixture().propose(
        packets[packet_id]) for packet_id,condition in condition_by_packet.items()}
    positive_vectors={condition:score_strategy_decision_quality(proposal=proposal,
        situation=strategy_situation,events=selected_sources,
        preregistration=frozen_manifest["decision_quality_preregistration"])
        for condition,proposal in positive_by_condition.items()}
    positive_present={row["criterion_id"]:row["status"]
        for row in positive_vectors["history_present"]["criteria"]}
    positive_withheld={row["criterion_id"]:row["status"]
        for row in positive_vectors["history_withheld"]["criteria"]}
    assert positive_present["event_citation_identity"]=="pass"
    assert positive_present["uncertainty_under_conflicting_historical_outcomes"]=="pass"
    assert positive_withheld["uncertainty_under_conflicting_historical_outcomes"]=="indeterminate"
    # The vector score itself becomes a qualified World-State source, then
    # enters the same scoped developmental writeback store as consequence and
    # proposal history. It carries no execution or effect claim.
    feedback_source = strategy_decision_quality_world_state_record(
        proposal=positive_by_condition["history_present"], situation=strategy_situation,
        events=selected_sources,
        preregistration=frozen_manifest["decision_quality_preregistration"],
        result=positive_vectors["history_present"],
        cognitive_backend_posture="synthetic_fixture")
    assert feedback_source["payload"]["event_dependencies"] == [
        {"event_id": item["attribution"]["attribution_id"],
         "event_digest": item["attribution"]["attribution_digest"],
         "source_record_id": item["source_record_id"],
         "source_record_digest": item["source_record_digest"],
         "source_fact_id": item["source_fact_id"],
         "applicability": {key: item["applicability"].get(key)
            for key in ("relation", "posture", "declaration_digest")},
         "applicability_independently_verified": False}
        for item in selected_sources]
    assert feedback_source["payload"]["execution_occurred"] is False
    assert feedback_source["payload"]["physical_effect_established"] is False
    assert "condition" not in feedback_source["payload"]
    assert len(json.dumps(feedback_source, sort_keys=True,
        separators=(",", ":")).encode("utf-8")) <= \
            MAX_STRATEGY_QUALITY_SELECTED_EVIDENCE_BYTES
    feedback_world = WorldStateBoardBuilder().build([feedback_source])
    feedback_tick = cognition.run_tick(snapshot=feedback_world,
        tick_id="multi-event-decision-quality-feedback-admission")
    assert feedback_tick.written_record_id
    feedback_history = asdict(cognition.writeback.store.get(feedback_tick.written_record_id))
    admitted_feedback_facts = [fact for fact in feedback_history["candidate"]["selected_facts"]
        if fact.get("source", {}).get("source_id") == feedback_source["source_id"]]
    assert len(admitted_feedback_facts) == 1
    assert admitted_feedback_facts[0]["payload"] == feedback_source["payload"]
    assert feedback_history["current_truth"] is False and feedback_history["authority"] is False
    from sentientos.embodied_consequence import _strategy_prior_consequence_binding
    substituted_source = copy.deepcopy(history_record)
    substituted_source["candidate"]["selected_facts"][0]["source"]["digest"] = "f" * 64
    assert _strategy_prior_consequence_binding(substituted_source, attribution)["posture"] == \
        "contradictory_history_source_digest"

    later_snapshot = snapshot(42)
    current_projection = cognition._current_projection(later_snapshot)
    situation = {"situation_binding": "distinct-later-wave-situation",
        "body_generation": 2, "reported_current_pose": "idle"}
    budget = {"max_input_chars": 16000, "max_output_chars": 4000,
        "max_new_tokens": 512, "timeout_seconds": 30}
    protocol = {"protocol_id": "fixture-developmental-strategy",
        "snapshot_digest": later_snapshot.digest, "body_generation": 2,
        "model_id": "fixture-strategy-model", "model_artifact_digest": "sha256:model",
        "inference_budget_digest": consequence_digest(budget),
        "prompt_schema_digest": strategy_prompt_schema_digest(),
        "renderer_situation_digest": consequence_digest(situation),
        "software_generation": "fixture-source-generation",
        "environment_fixture_digest": "sha256:fixture-environment"}

    class HistoryConditionedStrategyFixture:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def propose(self, *, condition, history, situation):
            self.calls.append(condition)
            present = bool(history)
            return make_strategy_proposal(
                situation_binding=situation["situation_binding"], body_generation=2,
                relevant_consequence_ids=(attribution["attribution_id"],) if present else (),
                proposed_next_action_class="observe_then_retry" if present else "retry",
                requested_pose="wave", requested_expression="neutral",
                retry_prior_strategy=not present, alter_body_or_rig=False,
                more_observation_required=present, distinguishes_renderer_and_observer=present,
                rationale="fixture proposal conditioned on admitted contradiction" if present
                    else "fixture baseline proposal without the historical record",
                uncertainty="high", factual_assertions=({"source_id": attribution["attribution_id"],
                    "claim": "contradiction_recorded"},) if present else ())

    backend = HistoryConditionedStrategyFixture()
    store = ConsequenceStore(tmp_path / "strategy-store")
    experiment = run_strategy_experiment(protocol=protocol, history_record=history_record,
        situation=situation, backend=backend, consequence=attribution, store=store,
        cognitive_context={"current_tick": 42, "tick_id": "strategy-later-tick",
            "snapshot": later_snapshot, "current_projection": current_projection,
            "prior_self_model": None, "prior_epistemic_state": None})
    assert experiment["history_record_identity_consistent"] is True
    assert experiment["consequence_context_binding"]["posture"] == \
        "verified_prior_selected_history"
    assert experiment["world_state_binding_posture"] == \
        "verified_resident_snapshot_and_current_projection"
    present, withheld, restored = experiment["proposals"]
    assert present == restored and present != withheld
    assert experiment["scoring"]["outcome"] == "changed"
    assert experiment["scoring"]["improvement_claimed"] is False
    present_score, withheld_score, restored_score = experiment["scoring"]["proposal_scores"]
    assert present_score["prior_consequence_cited_correctly"] is True
    assert present_score["repeats_previously_contradicted_action"] is False
    assert present_score["requests_more_evidence_under_unresolved_attribution"] is True
    assert withheld_score["repeats_previously_contradicted_action"] is True
    assert withheld_score["requests_more_evidence_under_unresolved_attribution"] is False
    assert restored_score == present_score
    assert backend.calls == ["history_present", "history_withheld", "history_restored"]
    assert all(authority is False for authority in experiment["authority"].values())

    restarted_backend = HistoryConditionedStrategyFixture()
    recovered = run_strategy_experiment(protocol=protocol, history_record=history_record,
        situation=situation, backend=restarted_backend, consequence=attribution,
        store=ConsequenceStore(tmp_path / "strategy-store"),
        cognitive_context={"current_tick": 42, "tick_id": "strategy-later-tick",
            "snapshot": later_snapshot, "current_projection": current_projection,
            "prior_self_model": None, "prior_epistemic_state": None})
    assert recovered["experiment_result_id"] == experiment["experiment_result_id"]
    assert restarted_backend.calls == []

    # The later proposal returns through the ordinary historical source and
    # admission path as proposal evidence, with no implied effect or authority.
    proposal_rows = store.world_state_records(
        experiment_result_ids=(experiment["experiment_result_id"],))
    projected_proposals = [row for row in proposal_rows
        if row.get("subject_kind") == "embodied_strategy_proposal"]
    assert len(projected_proposals) == 3
    assert {row["payload"]["condition"] for row in projected_proposals} == {
        "history_present", "history_withheld", "history_restored"}
    assert all(row["payload"]["effect_proven"] is False
        and row["payload"]["current_truth"] is False
        and all(value is False for value in row["payload"]["authority"].values())
        for row in projected_proposals)
    present_proposal = next(row for row in projected_proposals
        if row["payload"]["condition"] == "history_present")
    proposal_world = WorldStateBoardBuilder().build([present_proposal])
    next_cognition, _ = owner(tmp_path / "resident",
        invoker=cognition_invoker, allowed_source_kinds=("embodiment",),
        max_selected_facts=16)
    next_record = next_cognition.run_tick(snapshot=proposal_world,
        tick_id="strategy-proposal-next-developmental-cycle")
    assert next_record.written_record_id
    next_history = asdict(next_cognition.writeback.store.get(next_record.written_record_id))
    admitted_proposal_ids = {fact["source"]["source_id"]
        for fact in next_history["candidate"]["selected_facts"]
        if fact.get("source", {}).get("source_id") == present_proposal["source_id"]}
    assert admitted_proposal_ids == {present_proposal["source_id"]}
    assert next_history["authority"] is False

    # Terminate the composing owners and reconstruct the canonical history in
    # a fresh interpreter. The child receives only serialized fixture-issued
    # invocation receipts and selectors; it reopens admission/history itself,
    # rebuilds the bounded packet, and proposes for a distinct later task.
    receipt_path = tmp_path / "canonical-loop-fixture-receipts.json"
    receipt_bytes = json.dumps({key: value.to_dict()
        for key, value in cognition_invoker.receipts.items()}, sort_keys=True,
        separators=(",", ":")).encode("utf-8")
    receipt_path.write_bytes(receipt_bytes)
    child_code = r'''import hashlib, json, sys
from pathlib import Path
from sentientos.codex_task_authority_admission import RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION
from sentientos.governed_local_model_invocation import validate_receipt
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.resident_developmental_cognition import ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionOwner
from sentientos.resident_developmental_cognition import ResidentDevelopmentalCognitionError
from sentientos.governed_local_model_invocation import LocalModelInvocationReceipt
from tests.test_resident_developmental_cognition import SessionBoundFakeInvoker, snapshot
from sentientos.embodied_consequence import build_operator_codex_strategy_multi_event_packets, make_strategy_proposal, score_strategy_decision_quality
root, receipt_path = Path(sys.argv[1]), Path(sys.argv[2])
receipt_data = receipt_path.read_bytes()
assert hashlib.sha256(receipt_data).hexdigest() == sys.argv[3]
receipts = json.loads(receipt_data)
invoker = SessionBoundFakeInvoker()
for value in receipts.values():
    receipt = LocalModelInvocationReceipt(
        request=value["request"], status=value["status"],
        reason_codes=tuple(value["reason_codes"]), output_text=None,
        output_digest=value["output_digest"], output_size_bytes=value["output_size_bytes"],
        generation_config=value["generation_config"],
        admission_decision_ref=value.get("admission_decision_ref"),
        purpose=value["purpose"], latency_ms=value.get("latency_ms", 0),
        output_truncated=value["output_truncated"],
        fallback_occurred=value["fallback_occurred"], effects=value["effects"],
        observed_at=value["observed_at"],
        resource_allocation_digest=value.get("resource_allocation_digest"),
        resource_attempt_id=value.get("resource_attempt_id"),
        resource_consumption_receipt_digests=tuple(value.get(
            "resource_consumption_receipt_digests", ())),
        resource_linkage_digest=value.get("resource_linkage_digest"),
        schema_version=value["schema_version"],
        backend_completion=value.get("backend_completion"))
    assert receipt.to_dict() == value
    invoker.receipts[receipt.receipt_id] = receipt
ledger = AdmissionLedger(root / "state" / "runtime_admissions.json")
definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
def current_sequence():
    admissions, _ = ledger.load(); return max((x.issued_sequence for x in admissions), default=1)
def next_sequence():
    admissions, revocations = ledger.load(); return max([x.issued_sequence for x in admissions] + [x.sequence for x in revocations] + [0]) + 1
class Verifier:
    def verify_persisted_invocation_receipt(self, receipt_id, receipt_digest, **expected):
        value = receipts[receipt_id]; valid, reasons = validate_receipt(value); assert valid, reasons
        assert value["receipt_id"] == receipt_id and value["receipt_digest"] == receipt_digest
        request = value["request"]
        assert request["request_id"] == expected["expected_request_id"]
        assert request["request_digest"] == expected["expected_request_digest"]
        assert request["active_model_identity"] == expected["expected_active_model_identity"]
        assert request["linkage"]["resident_cognitive_serving"]["session_id"] == expected["expected_session_id"]
        return {key:value[key] for key in ("receipt_id", "receipt_digest", "request", "status", "output_digest", "output_truncated", "generation_config", "output_size_bytes", "backend_completion", "observed_at") if key in value}
writeback = ResidentDevelopmentalWritebackController(history_root=root / "history", admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger), current_sequence=current_sequence)
owner = ResidentDevelopmentalCognitionOwner(config=ResidentDevelopmentalCognitionConfig(root / "history", root / "state", ("embodiment",), 16, 4, False), writeback=writeback, admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger), invoker=invoker, current_sequence=next_sequence)
inventory = owner.writeback.inspect_completed_records()
by_id = {record.record_id:record for record, _ in inventory}
assert len(by_id) == len(inventory)
assert sys.argv[4] in by_id and sys.argv[5] in by_id and sys.argv[6] in by_id
assert sys.argv[7] in by_id
assert sys.argv[8] in by_id
assert sys.argv[16] in by_id
assert sys.argv[18] in by_id
situation, settings, applicability = (json.loads(sys.argv[i]) for i in (9,10,11))
bundle = build_operator_codex_strategy_multi_event_packets(writeback=owner.writeback, history_record_ids=[sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[16], sys.argv[18]], situation=situation, model_settings=settings, max_event_count=3, applicability_by_event=applicability)
manifest = bundle["scorer_manifest"]
assert {row["attribution"]["attribution_id"] for row in manifest["events"]} == {sys.argv[12], sys.argv[13], sys.argv[19]}
assert {row["event_id"] for row in bundle["preregistration"]["omitted_event_identities"]} == {sys.argv[14], sys.argv[17]}
packet = next(packet for packet in bundle["subject_packets"].values() if packet["historical_evidence"])
history = packet["historical_evidence"]
proposal = make_strategy_proposal(situation_binding=situation["situation_binding"], body_generation=situation["body_generation"], relevant_consequence_ids=tuple(row["event_id"] for row in history), proposed_next_action_class="observe", requested_pose="wave", requested_expression="neutral", retry_prior_strategy=False, alter_body_or_rig=False, more_observation_required=True, distinguishes_renderer_and_observer=True, rationale="fresh process preserves conflicting event provenance and requests observation", uncertainty="high", factual_assertions=())
protocol_root=Path(sys.argv[15])
frozen_manifest=json.loads((protocol_root/"scorer_manifest.json").read_text(encoding="utf-8"))
frozen_prereg=json.loads((protocol_root/"preregistration.json").read_text(encoding="utf-8"))
score_archive=json.loads((protocol_root/"fixture_scores.json").read_text(encoding="utf-8"))
assert bundle["preregistration"]["selected_event_identities"] == frozen_prereg["selected_event_identities"], "reconstructed_selected_history_changed"
assert bundle["preregistration"]["omitted_event_identities"] == frozen_prereg["omitted_event_identities"], "reconstructed_omission_manifest_changed"
assert bundle["preregistration"]["history_record_identities"] == frozen_prereg["history_record_identities"], "reconstructed_record_set_changed"
assert bundle["preregistration"]["situation_digest"] == frozen_prereg["situation_digest"], "reconstructed_situation_changed"
assert bundle["scorer_manifest"]["decision_quality_preregistration"] == frozen_manifest["decision_quality_preregistration"], "reconstructed_rubric_changed"
assert score_archive["selected_event_identities"] == frozen_prereg["selected_event_identities"], "archived_selected_identities_changed"
assert score_archive["omitted_event_identities"] == frozen_prereg["omitted_event_identities"], "archived_omitted_identities_changed"
assert score_archive["condition_by_packet_id"] == frozen_manifest["condition_by_packet_id"], "archived_condition_assignment_changed"
for archived in score_archive["decision_quality"].values():
    assert archived["preregistration_digest"] == frozen_manifest["decision_quality_preregistration"]["rubric_digest"]
    assert archived["aggregate_score"] is None
    assert archived["condition_labels_used"] is False
quality=score_strategy_decision_quality(proposal=proposal,situation=situation,
    events=frozen_manifest["events"],
    preregistration=frozen_manifest["decision_quality_preregistration"])
later = owner.run_tick(snapshot=snapshot(43), tick_id="post-restart-distinct-resident-task")
assert later.written_record_id
before_duplicate = owner.writeback.inspect_completed_records()
try:
    owner.run_tick(snapshot=snapshot(43), tick_id="post-restart-distinct-resident-task")
except ResidentDevelopmentalCognitionError as exc:
    assert "tick_already_completed" in str(exc)
else:
    raise AssertionError("completed_tick_replayed_after_restart")
assert [record.record_id for record, _ in owner.writeback.inspect_completed_records()] == [
    record.record_id for record, _ in before_duplicate]
purposes = [request.purpose for request in invoker.requests]
assert "resident_developmental_retrieval_cognition" in purposes
assert "resident_developmental_history_intervention_experiment" not in purposes
retrieval = next(request for request in invoker.requests
    if request.purpose == "resident_developmental_retrieval_cognition")
retrieved_ids = list(retrieval.upstream_evidence["record_ids"])
assert sys.argv[8] in retrieved_ids
after_inventory = owner.writeback.inspect_completed_records()
after_ids = [record.record_id for record, _ in after_inventory]
assert len(after_ids) == len(set(after_ids)) and later.written_record_id in after_ids
print(json.dumps({"record_ids":sorted(after_ids), "retrieved_ids":retrieved_ids, "event_ids":[row["event_id"] for row in history], "proposal_id":proposal.strategy_id, "quality_result":quality, "post_restart_tick_record_id":later.written_record_id, "post_restart_invocation_purposes":purposes, "omitted_ids":[row["event_id"] for row in bundle["preregistration"]["omitted_event_identities"]], "source_times":[row["evaluated_at"] for row in history]}, sort_keys=True))
'''
    child = subprocess.run([sys.executable, "-c", child_code,
        str(tmp_path / "resident"), str(receipt_path),
        hashlib.sha256(receipt_bytes).hexdigest(), durable_record.record_id,
        correction_record.record_id, irrelevant_record_id, next_record.written_record_id,
        feedback_tick.written_record_id,
        json.dumps(strategy_situation, sort_keys=True), json.dumps(strategy_settings, sort_keys=True),
        json.dumps(applicability, sort_keys=True), attribution["attribution_id"],
        correction_attribution["attribution_id"], unrelated_attribution["attribution_id"],
        str(protocol_root), unresolved_tick.written_record_id,
        unresolved_attribution["attribution_id"], challenged_tick.written_record_id,
        challenged_attribution["attribution_id"]],
        check=False, capture_output=True, text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            "SENTIENTOS_GOVERNOR_ROOT": str(tmp_path / "child-governor")})
    assert child.returncode == 0, child.stderr
    recovered_child = json.loads(child.stdout)
    assert set(recovered_child["event_ids"]) == {
        attribution["attribution_id"], correction_attribution["attribution_id"],
        challenged_attribution["attribution_id"]}
    assert set(recovered_child["omitted_ids"]) == {
        unrelated_attribution["attribution_id"], unresolved_attribution["attribution_id"]}
    assert {
        durable_record.record_id, correction_record.record_id, irrelevant_record_id,
        unresolved_tick.written_record_id, challenged_tick.written_record_id,
        next_record.written_record_id,
        feedback_tick.written_record_id} <= set(
            recovered_child["record_ids"])
    assert len(recovered_child["record_ids"]) == 8
    assert recovered_child["post_restart_tick_record_id"] in recovered_child["record_ids"]
    assert feedback_tick.written_record_id in recovered_child["retrieved_ids"]
    assert sorted(recovered_child["source_times"]) == sorted([
        attribution["evaluated_at"], correction_attribution["evaluated_at"],
        challenged_attribution["evaluated_at"]])
    assert recovered_child["quality_result"]["aggregate_score"] is None
    assert recovered_child["quality_result"]["condition_labels_used"] is False
    assert recovered_child["quality_result"]["result_digest"].startswith("sha256:")
    assert recovered_child["post_restart_tick_record_id"]
    assert "resident_developmental_retrieval_cognition" in recovered_child[
        "post_restart_invocation_purposes"]
    assert "resident_developmental_history_intervention_experiment" not in recovered_child[
        "post_restart_invocation_purposes"]

    # A source timestamp edited after admission must fail the durable record
    # identity check before it can change which history is considered prior.
    import shutil
    timestamp_root = tmp_path / "timestamp-substitution"
    shutil.copytree(tmp_path / "resident", timestamp_root)
    stored_path = timestamp_root / "history" / "records" / f"{durable_record.record_id}.json"
    stored_value = json.loads(stored_path.read_text(encoding="utf-8"))
    stored_fact = next(fact for fact in stored_value["candidate"]["selected_facts"]
        if fact.get("payload", {}).get("attribution_id") == attribution["attribution_id"])
    assert stored_fact["payload"]["evaluated_at"] != strategy_situation["requested_at"]
    stored_fact["payload"]["evaluated_at"] = strategy_situation["requested_at"]
    stored_path.write_text(json.dumps(stored_value, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    timestamp_owner, _ = owner(timestamp_root, allowed_source_kinds=("embodiment",),
        max_selected_facts=16)
    with pytest.raises(DevelopmentalWritebackError, match="record_digest_mismatch"):
        timestamp_owner.writeback.inspect_completed_records()

    # Feed the same three admitted consequence records through the existing
    # model-replacement owner with a fixed current projection.
    from sentientos.developmental_model_replacement_experiment import (
        CognitiveModelIdentity, DevelopmentalModelReplacementExperiment, FrozenCausalContext,
    )
    replacement_snapshot=snapshot(44)
    replacement_projection=cognition._current_projection(replacement_snapshot)
    replacement_record_ids=tuple(item["source_record_id"]
        for item in strategy_manifest["events"])
    replacement_history=cognition.writeback.retrieve(replacement_record_ids,limit=4)
    assert replacement_history.requested_record_ids==replacement_record_ids
    replacement_record_digests=tuple(item["record_digest"]
        for item in replacement_history.records)
    assert replacement_record_digests==tuple(item["source_record_digest"]
        for item in strategy_manifest["events"])
    replacement_current_payload=replacement_projection.semantic_payload()
    replacement_instruction=("Use current evidence with optional historical interpretation; "
        "history is not truth or authority.")
    replacement_context=FrozenCausalContext.create(
        snapshot_id=replacement_projection.snapshot_id,
        snapshot_digest=replacement_projection.snapshot_digest,
        current_projection_id=replacement_projection.projection_id,
        current_projection_digest=replacement_projection.projection_digest,
        current_fact_ids=replacement_projection.fact_ids,
        projected_content_digest="sha256:"+digest_payload(replacement_current_payload),
        current_projection_payload=replacement_current_payload,
        history_record_ids=replacement_record_ids,
        history_record_digests=replacement_record_digests,
        history_record_set_digest="sha256:"+digest_payload({
            "record_ids":list(replacement_record_ids),
            "record_digests":list(replacement_record_digests)}),
        history_projection_payload=replacement_history.records,
        instruction_template=replacement_instruction,
        instruction_template_digest="sha256:"+digest_payload({"instruction":replacement_instruction}),
        inference_budget={"max_input_chars":16000,"max_output_chars":4000,
            "max_new_tokens":512,"timeout_seconds":30,"max_calls_per_correlation":1},
        generation_posture={"temperature":0,"hardware_determinism_claimed":False},
        repository_generation_identity="fixture-source-generation")

    def replacement_identity(model_name):
        content="sha256:"+digest_payload({"replacement_model":model_name})
        sidecar="sha256:"+digest_payload({"replacement_sidecar":model_name})
        configuration="sha256:"+digest_payload({"replacement_configuration":model_name})
        active={"semantic_artifact_identity":"fixture-artifact-"+model_name,
            "model_content_sha256":content,"artifact_size_bytes":10,
            "sidecar_metadata_digest":sidecar,"configuration_digest":configuration,
            "engine":"deterministic-test-runtime","candidate_index":0,
            "posture":"production","fallback":False}
        return CognitiveModelIdentity.create(model_id=model_name,
            semantic_artifact_identity=active["semantic_artifact_identity"],
            model_content_sha256=content,artifact_size_bytes=10,
            sidecar_metadata_digest=sidecar,configuration_digest=configuration,
            engine_runtime_family="deterministic-test-runtime",candidate_index=0,
            active_production=True,fallback=False,
            authority_record_id="fixture-authority-"+model_name,
            authority_record_digest="sha256:"+digest_payload({"authority":model_name}),
            active_model_identity=active,
            active_model_identity_digest="sha256:"+digest_payload(active))

    class ConsequenceHistoryEndpoint:
        def __init__(self,identity):
            self.identity=identity
            self.calls=[]
            self.invocation_ids=[]

        def current_identity(self):
            return self.identity

        def infer(self,**kwargs):
            self.calls.append(kwargs)
            number=len(self.calls)
            self.invocation_ids.append("fixture-request-"+self.identity.model_id+"-"+str(number))
            return {"status":"admitted_completed","fallback_occurred":False,
                "request_id":self.invocation_ids[-1],
                "request_digest":"sha256:"+digest_payload({"request":self.identity.model_id,
                    "number":number}),
                "inference_receipt_id":"fixture-receipt-"+self.identity.model_id+"-"+str(number),
                "inference_receipt_digest":"sha256:"+digest_payload({"receipt":self.identity.model_id,
                    "number":number}),
                "output_digest":"sha256:"+digest_payload({"prompt":kwargs["prompt"]}),
                "actual_generation_parameters":{"temperature":0,
                    "max_new_tokens":kwargs["budget"]["max_new_tokens"]}}

    predecessor=ConsequenceHistoryEndpoint(replacement_identity("consequence-predecessor"))
    successor=ConsequenceHistoryEndpoint(replacement_identity("consequence-successor"))
    consequence_replacement=DevelopmentalModelReplacementExperiment(
        context=replacement_context,model_a=predecessor,model_b=successor,
        artifact_root=tmp_path/"consequence-model-replacement")
    replacement_result=consequence_replacement.run()
    assert replacement_result["validity"]=="valid_controlled_observation"
    assert consequence_replacement.context.history_record_ids==replacement_record_ids
    assert consequence_replacement.context.history_record_digests==replacement_record_digests
    predecessor_history=json.loads(predecessor.calls[0]["prompt"])["developmental_history"]
    successor_history=json.loads(successor.calls[0]["prompt"])["developmental_history"]
    assert tuple(item["record_id"] for item in predecessor_history)==replacement_record_ids
    assert tuple(item["record_id"] for item in successor_history)==replacement_record_ids
    assert tuple(item["record_digest"] for item in predecessor_history)==replacement_record_digests
    assert tuple(item["record_digest"] for item in successor_history)==replacement_record_digests
    assert json.loads(predecessor.calls[1]["prompt"])["developmental_history"]==[]
    assert json.loads(successor.calls[1]["prompt"])["developmental_history"]==[]
    assert json.loads(predecessor.calls[2]["prompt"])["developmental_history"]==predecessor_history
    assert len({predecessor.identity.model_id,successor.identity.model_id})==2
    assert len({predecessor.invocation_ids[0],successor.invocation_ids[0]})==2
    assert all(not item.current_truth and not item.authority
        for item in (durable_record,correction_record,
            cognition.writeback.store.get(challenged_tick.written_record_id)))


def test_resource_linkage_cannot_bypass_serving_receipt_verification(tmp_path: Path) -> None:
    composition, _ = owner(tmp_path)
    receipt_digest = "a" * 64
    allocation_digest = "b" * 64
    attempt_id = "attempt-source-backed"
    consumption = ("c" * 64, "d" * 64)
    linkage_digest = digest_payload({"receipt_digest": receipt_digest,
        "allocation_digest": allocation_digest, "attempt_id": attempt_id,
        "consumption_receipt_digests": consumption})
    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="cognition_resource_linked_invocation_session_unbound"):
        composition._verify_observation_invocation({
            "schema_version": "sentientos.resident_cognition_observation:v7",
            "serving_session_id": None, "serving_session_binding": None,
            "resource_allocation_digest": allocation_digest,
            "resource_attempt_id": attempt_id,
            "resource_consumption_receipt_digests": consumption,
            "resource_linkage_digest": linkage_digest,
        })


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
