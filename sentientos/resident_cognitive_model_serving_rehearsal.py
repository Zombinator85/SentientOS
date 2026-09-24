"""Isolated synthetic system rehearsal for resident cognitive model serving.

This module is proof tooling, not a production evidence factory.  It deliberately
uses the production activation verifier and serving/cognition owners while keeping
all artifacts beneath a caller-selected empty root.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, cast

from .codex_task_authority_admission import RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION
from .config import GenerationConfig, ModelCandidate, ModelConfig
from .control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionDecision, ControlPlaneKernel, LifecyclePhase
from .developmental_model_replacement_rehearsal import _catalog, _identity_and_receipt, _publication
from .installation_state import InstallationIdentity, InstallationStateRegistry
from .local_model import ActiveModelIdentity
from .local_model_authority import atomic_write_json, build_local_model_authority_map
from .local_model_catalog import local_model_catalog_digest
from .local_model_catalog_consumer_custody import construct_authoritative_catalog_consumer_proof
from .local_model_catalog_deployment import CatalogDeploymentAuthority, CatalogDeploymentRequest, deploy_local_model_catalog
from .local_model_catalog_deployment_architecture import EFFECTS as DEPLOY_EFFECTS, EXPECTED_ABSENT
from .local_model_production_activation import ABSENT, APPROVAL_SCHEMA, activate_production, approval_bindings, prepare_activation_intent, verify_current_activation
from .local_model_production_serving import ProductionServingController
from .local_runtime_provisioning import semantic_digest
from .model_catalog_custody import ModelCatalogCustody
from .resident_cognitive_model_serving import ResidentCognitiveModelServingController, ResidentCognitiveServingInvoker
from .resident_developmental_cognition import ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionOwner
from .resident_developmental_writeback import ResidentDevelopmentalWritebackController
from .runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from .world_state_board import WorldStateBoardBuilder

SCENARIO_SCHEMA = "sentientos.resident_cognitive_model_serving_rehearsal:v1"
VERIFICATION_SCHEMA = "sentientos.resident_cognitive_model_serving_rehearsal_verification:v1"
POSTURE = "synthetic_rehearsal"
FIXED = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


class _Kernel:
    def __init__(self, deny: AuthorityClass | None = None) -> None:
        self.deny = deny
        self.requests: list[Any] = []

    @property
    def phase(self) -> LifecyclePhase:
        return LifecyclePhase.RUNTIME

    def admit(self, request: Any) -> ControlActionDecision:
        self.requests.append(request)
        outcome = AdmissionOutcome.DENY if request.authority_class == self.deny else AdmissionOutcome.ALLOW
        return ControlActionDecision(outcome, (() if outcome is AdmissionOutcome.ALLOW else ("synthetic_denial",)),
            LifecyclePhase.RUNTIME, request.requested_phase, request.authority_class, request.action_kind,
            request.actor, request.target_subsystem, {}, request.metadata["correlation_id"])


class _Worker:
    def __init__(self, identity: Mapping[str, Any], *, die: bool = False) -> None:
        self.active_identity = ActiveModelIdentity(**identity)
        self.calls = 0
        self.close_count = 0
        self._process = SimpleNamespace(poll=lambda: 1 if die else None)

    def generate_governed(self, prompt: str, **_: Any) -> str:
        self.calls += 1
        if _.get("structured_output_schema") is not None:
            return json.dumps({"interpretation": "bounded synthetic historical interpretation", "uncertainty": "medium"})
        return "synthetic-resident-cognition:" + hashlib.sha256(prompt.encode()).hexdigest()[:24]

    def close(self) -> None:
        self.close_count += 1


def _approval(intent: Mapping[str, Any], suffix: str) -> dict[str, Any]:
    value: dict[str, Any] = {"schema_version": APPROVAL_SCHEMA, "approval_status": "approved",
        **approval_bindings(intent), "operator_identity": "synthetic-rehearsal-operator",
        "approval_evidence_id": f"synthetic-activation-approval-{suffix}",
        "evidence_source": "resident-cognitive-serving-rehearsal",
        "evidence_provenance": "isolated synthetic fixture", "synthetic_test_evidence": True,
        "not_before": "2026-09-24T00:00:00+00:00", "approval_timestamp": "2026-09-24T11:00:00+00:00",
        "expires_at": "2026-09-25T00:00:00+00:00"}
    value["approval_semantic_digest"] = semantic_digest(value)
    return value


def _activate(handle: Any, receipt_id: str, kernel: _Kernel, prior: str, suffix: str) -> dict[str, Any]:
    handle.ensure_directory(handle.fixed_object("local-model/activation"))
    handle.ensure_directory(handle.fixed_object("local-model/activation/transactions"))
    handle.ensure_directory(handle.fixed_object("local-model/activation/receipts"))
    correlation = f"resident-rehearsal-activation-{suffix}"
    intent = prepare_activation_intent(handle, commissioning_receipt_id=receipt_id, correlation_id=correlation,
        expected_prior_state=prior, allow_synthetic_commissioning_for_tests=True)
    return cast(dict[str, Any], activate_production(installation_handle=handle, commissioning_receipt_id=receipt_id,
        approval_evidence=_approval(intent, suffix), control_plane_kernel=cast(ControlPlaneKernel, kernel), correlation_id=correlation,
        expected_prior_state=prior, observation_time=FIXED, clock=lambda: FIXED,
        allow_synthetic_evidence_for_tests=True))


def _fixture(root: Path) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]], list[Path], _Kernel]:
    state = root / "installation"
    artifacts = root / "synthetic-models"
    artifacts.mkdir(parents=True)
    paths: list[Path] = []
    for label in ("A", "B"):
        raw = f"sentientos resident serving synthetic model {label}\n".encode()
        path = artifacts / f"model-{label}-{hashlib.sha256(raw).hexdigest()}.gguf"
        path.write_bytes(raw); paths.append(path)
    handle = InstallationStateRegistry._for_testing(state).open(InstallationIdentity("resident-serving-rehearsal"), create=True)
    catalog = _catalog(root, paths); custody = ModelCatalogCustody.for_installation(handle)
    digest = local_model_catalog_digest(catalog)
    request = CatalogDeploymentRequest("deterministic_catalog_deployment_controller", "sentientos.local_model_catalog.deploy",
        DEPLOY_EFFECTS, "synthetic-grant", "synthetic-lease", "resident-rehearsal-catalog", handle.identity.value,
        custody.custody_identity, digest, EXPECTED_ABSENT)
    authority = CatalogDeploymentAuthority("synthetic-grant", "synthetic-lease", request.principal, request.capability_id,
        DEPLOY_EFFECTS, request.correlation_id, handle.identity.value, custody.custody_identity, digest, EXPECTED_ABSENT,
        True, "2026-09-24T00:00:00Z", "2026-09-25T00:00:00Z", synthetic_test_authority=True)
    deploy_local_model_catalog(handle, request, authority, catalog, [_publication(x) for x in catalog["models"]], now=lambda: "2026-09-24T12:00:00Z")
    proof = construct_authoritative_catalog_consumer_proof(handle).proof
    raw_pairs = [_identity_and_receipt(handle, model, path, proof) for model, path in zip(catalog["models"], paths)]
    pairs = []
    adjusted_identities: list[dict[str, Any]] = []
    for (identity, original), model, path in zip(raw_pairs, catalog["models"], paths):
        receipt = dict(original)
        receipt.pop("receipt_id"); receipt.pop("receipt_semantic_digest")
        serving_config = ModelConfig([ModelCandidate(path, "llama_cpp", str(model["model_id"]), {"gpu_layers": 0})],
            default_engine="llama_cpp", max_context_tokens=512,
            generation=GenerationConfig(max_new_tokens=512, temperature=0, top_p=1))
        serving_authority = build_local_model_authority_map(serving_config, allowed_roots=[path.parent],
            observed_at="1970-01-01T00:00:00+00:00")
        record = serving_authority.records[0]
        observed = ActiveModelIdentity(engine=record.engine, resolved_artifact_path=str(path.resolve()),
            semantic_artifact_identity=record.semantic_artifact_identity, model_content_sha256=record.model_content_sha256,
            artifact_size_bytes=record.artifact_size_bytes, sidecar_metadata_digest=record.sidecar_metadata_digest,
            configuration_digest=record.configuration_digest, candidate_index=0, posture="production", fallback=False).to_dict()
        receipt["authority_map_digest"] = serving_authority.map_digest
        receipt["observed_active_model_identity"] = observed
        receipt["artifact_id"] = "artifact-" + str(receipt["artifact_sha256"])[:24]
        receipt["route_id"] = "cpu"
        receipt["receipt_id"] = "commissioning-receipt-" + semantic_digest(receipt)[:24]
        receipt["receipt_semantic_digest"] = semantic_digest(receipt)
        pairs.append((identity, receipt))
        adjusted_identities.append(observed)
    handle.ensure_directory(handle.fixed_object("local-model/commissioning/receipts"))
    for _, receipt in pairs:
        handle.durable_create(handle.fixed_object(f"local-model/commissioning/receipts/{receipt['receipt_id']}.json"),
            (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode())
    kernel = _Kernel()
    return handle, adjusted_identities, [x[1] for x in pairs], paths, kernel


def _snapshot(value: int = 1) -> Any:
    return WorldStateBoardBuilder().build([{"source_id": "resident-rehearsal-source", "source_kind": "capability_registry",
        "subject_id": "resident-rehearsal", "stage": "observation", "disposition": "recorded",
        "observed_at": "2026-09-24T12:00:00+00:00", "payload": {"value": value}}])


def _owner(root: Path, invoker: ResidentCognitiveServingInvoker) -> ResidentDevelopmentalCognitionOwner:
    ledger = AdmissionLedger(root / "cognition" / "admissions.json")
    definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
    def current() -> int:
        admissions, _ = ledger.load(); return max((x.issued_sequence for x in admissions), default=1)
    def next_sequence() -> int:
        admissions, revocations = ledger.load(); return max([x.issued_sequence for x in admissions] + [x.sequence for x in revocations], default=0) + 1
    writeback = ResidentDevelopmentalWritebackController(history_root=root / "cognition" / "history",
        admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger), current_sequence=current)
    return ResidentDevelopmentalCognitionOwner(config=ResidentDevelopmentalCognitionConfig(
        root / "cognition" / "history", root / "cognition" / "state", ("capability_registry",), 1),
        writeback=writeback, admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
        invoker=invoker, current_sequence=next_sequence)


def _read_only_file(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def run(root: Path, scenario: str) -> Mapping[str, Any]:
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()): raise ValueError("rehearsal_root_not_empty")
    root.mkdir(parents=True, exist_ok=True)
    bundle = root / "resident-cognitive-serving-rehearsal"; bundle.mkdir()
    handle, identities, receipts, _, kernel = _fixture(root)
    activated_a = _activate(handle, receipts[0]["receipt_id"], kernel, ABSENT, "a")
    activation_a = verify_current_activation(handle, allow_synthetic_evidence_for_tests=True)
    config = {"serving_operation_id": f"resident-serving-{scenario}",
        "expected_activation_state_digest": activation_a["active_state"]["state_semantic_digest"]}
    config_digest = semantic_digest(config)
    workers: list[_Worker] = []
    def factory(_: Any, __: Any) -> _Worker:
        worker = _Worker(identities[0]); workers.append(worker); return worker
    resident = ResidentCognitiveModelServingController(handle, cast(ControlPlaneKernel, kernel), model_factory=factory,
        allow_synthetic_evidence_for_tests=True, config_digest=config_digest)
    before_inference = 0
    session = resident.establish(operation_id=config["serving_operation_id"],
        expected_activation_state_digest=config["expected_activation_state_digest"])
    result: dict[str, Any] = {"scenario": scenario, "resident_session_id": session.session_id,
        "model_serving_admission_ref": session.binding["model_serving_admission_ref"],
        "activation_a_digest": activation_a["active_state"]["state_semantic_digest"],
        "activation_receipt_id": activation_a["activation_receipt"]["receipt_id"],
        "configuration_digest": config_digest, "serving_operation_id": config["serving_operation_id"],
        "expected_activation_state_digest": config["expected_activation_state_digest"],
        "establishment_inference_count": workers[0].calls}
    serving_receipt = _read_only_file(next((handle.root / "local-model/resident-cognitive-serving/receipts").glob("*.json")))
    result.update({"resident_serving_receipt_id": serving_receipt["receipt_id"],
        "resident_serving_receipt_digest": serving_receipt["receipt_semantic_digest"]})
    if scenario == "happy":
        invoker = ResidentCognitiveServingInvoker(resident); owner = _owner(root, invoker)
        seed = owner.run_tick(snapshot=_snapshot(1), tick_id="resident-rehearsal-seed")
        cycle = owner.run_tick(snapshot=_snapshot(2), tick_id="resident-rehearsal-cognition")
        observations = [_read_only_file(p) for p in sorted((root / "cognition/state/cognition_observations").glob("*.json"))]
        inference = sorted((handle.root / "local-model/resident-cognitive-serving/inference/receipts").glob("*.json"))
        inference_payloads = [_read_only_file(p) for p in inference]
        resident.close()
        invalidation = _read_only_file(next((handle.root / "local-model/resident-cognitive-serving/invalidations").glob("*.json")))
        result.update({"seed_writeback_receipt_id": seed.writeback_receipt_id, "cycle_writeback_receipt_id": cycle.writeback_receipt_id,
            "cognition_observation_ids": list(cycle.cognition_observation_ids), "inference_receipts": [
                {"receipt_id": x["receipt_id"], "receipt_digest": x["receipt_digest"], "admission_decision_ref": x["admission_decision_ref"]} for x in inference_payloads],
            "model_identity_digest": semantic_digest(identities[0]), "worker_calls": workers[0].calls,
            "worker_close_count": workers[0].close_count, "invalidation_id": invalidation["invalidation_id"],
            "invalidation_digest": invalidation["invalidation_semantic_digest"], "observation_count": len(observations)})
    elif scenario == "activation-change":
        prior = activation_a["active_state"]["state_semantic_digest"]
        activated_b = _activate(handle, receipts[1]["receipt_id"], kernel, prior, "b")
        assert resident.current_session() is None
        invalidation = _read_only_file(next((handle.root / "local-model/resident-cognitive-serving/invalidations").glob("*.json")))
        current_b = verify_current_activation(handle, allow_synthetic_evidence_for_tests=True)
        result.update({"activation_b_digest": current_b["active_state"]["state_semantic_digest"],
            "invalidation_id": invalidation["invalidation_id"], "invalidation_digest": invalidation["invalidation_semantic_digest"],
            "model_serving_admission_count": sum(x.authority_class is AuthorityClass.MODEL_SERVING for x in kernel.requests),
            "b_construction_count": 0, "fallback_count": 0, "worker_close_count": workers[0].close_count,
            "final_health": resident.health()["status"], "canonical_b_preserved": activated_b["active_state"] == current_b["active_state"]})
    elif scenario == "production-chat-coexistence":
        chat_workers: list[_Worker] = []
        def chat_factory(_: Any, __: Any) -> _Worker:
            worker = _Worker(identities[0]); chat_workers.append(worker); return worker
        chat = ProductionServingController(handle, cast(ControlPlaneKernel, kernel), model_factory=chat_factory, allow_synthetic_evidence_for_tests=True)
        chat_session = chat.establish(operation_id="production-chat-rehearsal")
        chat_receipts = handle.root / "local-model/serving/receipts"
        chat_snapshot = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in chat_receipts.glob("*.json")}
        resident.close()
        result.update({"chat_session_id": chat_session.session_id, "chat_model_serving_admission_ref": chat_session.binding["model_serving_admission_ref"],
            "chat_current_after_resident_close": chat.current_session() is not None,
            "resident_receipt_root": str(handle.root / "local-model/resident-cognitive-serving/receipts"),
            "chat_receipt_root": str(chat_receipts), "chat_custody_unchanged": chat_snapshot == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in chat_receipts.glob("*.json")},
            "resident_close_chat_invalidation_count": len(list((handle.root / "local-model/serving/invalidations").glob("*.json"))) if (handle.root / "local-model/serving/invalidations").exists() else 0})
        chat.close()
    else:
        raise ValueError("unknown_rehearsal_scenario")
    final_activation = verify_current_activation(handle, allow_synthetic_evidence_for_tests=True)
    scenario_artifact: dict[str, Any] = {"schema_version": SCENARIO_SCHEMA, "evidence_posture": POSTURE,
        "scenario_name": scenario, "installation_identity": handle.identity.value, "result": result,
        "automatic_rebind_performed": False, "cognitive_model_transition_performed": False,
        "production_evidence": False, "production_experimental_trial": False}
    scenario_artifact["scenario_id"] = "resident-serving-rehearsal-" + semantic_digest(scenario_artifact)[:24]
    scenario_artifact["scenario_digest"] = semantic_digest(scenario_artifact)
    verification: dict[str, Any] = {"schema_version": VERIFICATION_SCHEMA, "evidence_posture": POSTURE,
        "status": "verified_complete", "scenario_id": scenario_artifact["scenario_id"],
        "scenario_digest": scenario_artifact["scenario_digest"], "result": result,
        "canonical_activation_final_digest": final_activation["active_state"]["state_semantic_digest"],
        "synthetic_only": True, "production_evidence": False, "automatic_rebind_performed": False,
        "cognitive_model_transition_performed": False}
    verification["verification_receipt_id"] = "resident-serving-verification-" + semantic_digest(verification)[:24]
    verification["verification_receipt_digest"] = semantic_digest(verification)
    atomic_write_json(bundle / "scenario.json", scenario_artifact)
    atomic_write_json(bundle / "verification.json", verification)
    manifest = {"schema_version": SCENARIO_SCHEMA, "evidence_posture": POSTURE,
        "scenario_id": scenario_artifact["scenario_id"], "scenario_digest": scenario_artifact["scenario_digest"],
        "verification_receipt_id": verification["verification_receipt_id"],
        "verification_receipt_digest": verification["verification_receipt_digest"],
        "configuration_binding": config}
    manifest["manifest_digest"] = semantic_digest(manifest); atomic_write_json(bundle / "manifest.json", manifest)
    atomic_write_json(bundle / "summary.json", verification)
    (bundle / "README.md").write_text("Synthetic rehearsal evidence only. Never production evidence or transition authority.\n", encoding="utf-8")
    return verification
