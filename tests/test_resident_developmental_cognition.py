Warning: truncated output (original token count: 108184)
Total output lines: 7084

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
    trial…93184 tokens truncated…te_score"] is None
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
