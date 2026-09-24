"""Deterministic, synthetic-only rehearsal of the model-replacement composition."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, cast

from .config import GenerationConfig, ModelCandidate, ModelConfig
from .control_plane_kernel import ControlPlaneKernel
from .developmental_model_replacement_campaign import DevelopmentalModelReplacementCampaign
from .developmental_model_replacement_experiment import (CognitiveModelIdentity,
    DevelopmentalModelReplacementExperiment, FrozenCausalContext, ModelDevelopmentProvenance,
    ModelReplacementArtifactStore, _digest)
from .developmental_model_replacement_experimental_serving import (APPROVAL_SCHEMA,
    ExperimentalModelServingController, approval_bindings)
from .developmental_model_replacement_production_trial import (
    DevelopmentalModelReplacementProductionTrialRunner, verify_production_trial_receipt)
from .installation_state import InstallationIdentity, InstallationStateRegistry
from .local_model import ActiveModelIdentity
from .local_model_authority import atomic_write_json, build_local_model_authority_map
from .local_model_catalog import local_model_catalog_digest, validate_local_model_catalog
from .local_model_catalog_consumer_custody import construct_authoritative_catalog_consumer_proof
from .local_model_catalog_deployment import (CatalogDeploymentAuthority, CatalogDeploymentRequest,
    deploy_local_model_catalog)
from .local_model_catalog_deployment_architecture import EFFECTS as DEPLOY_EFFECTS, EXPECTED_ABSENT
from .local_model_production_commissioning_authority import (CAPABILITY as COMMISSION_CAPABILITY,
    PRINCIPAL as COMMISSION_PRINCIPAL, RECEIPT_SCHEMA as COMMISSION_SCHEMA,
    effect_set_digest as commissioning_effect_set_digest)
from .local_runtime_provisioning import semantic_digest
from .model_catalog_custody import ModelCatalogCustody
from .model_mirror_publication import RECEIPT_SCHEMA as PUBLICATION_SCHEMA

SCENARIO_SCHEMA = "sentientos.developmental_model_replacement_rehearsal:v1"
VERIFICATION_SCHEMA = "sentientos.developmental_model_replacement_rehearsal_verification:v1"
FIXED_TIME = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def _read(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _snapshot(path: Path) -> dict[str, Any]:
    if not path.exists(): return {"state": "absent"}
    raw = path.read_bytes()
    return {"state": "present", "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _catalog(root: Path, artifacts: list[Path]) -> Mapping[str, Any]:
    models = []
    for index, artifact in enumerate(artifacts):
        raw = artifact.read_bytes(); digest = hashlib.sha256(raw).hexdigest(); name = artifact.name
        models.append({"model_id": f"rehearsal-model-{index + 1}", "priority": index + 1,
            "license_id": "synthetic-test-only", "source_repository": "sentientos/rehearsal",
            "source_revision": "1" * 40, "source_artifact_filename": name,
            "artifact_filename": name, "artifact_sha256": digest, "artifact_size_bytes": len(raw),
            "artifact_content_address": f"sha256:{digest}",
            "artifact_urls": [f"https://models.sentientos.org/{name}"],
            "requirements": {"architecture": "x86_64", "ram_gb_min": 1, "avx": False,
                "avx2": False, "avx512": False, "quantization": "synthetic"},
            "execution_routes": [{"route_id": "cpu", "engine": "llama_cpp",
                "backend_family": "cpu", "route_priority": 1}]})
    return cast(Mapping[str, Any], validate_local_model_catalog(
        {"schema_version": "sentientos.local_model_catalog:v1", "models": models}))


def _publication(model: Mapping[str, Any]) -> dict[str, Any]:
    value = {"schema_version": PUBLICATION_SCHEMA, "model_id": model["model_id"],
        "artifact_sha256": model["artifact_sha256"], "artifact_size": model["artifact_size_bytes"],
        "canonical_url": model["artifact_urls"][0], "object_exists": True, "object_verified": True,
        "remote_verification_method": "complete_streamed_sha256", "remote_digest": model["artifact_sha256"],
        "remote_size": model["artifact_size_bytes"], "final_publication_status": "published_verified",
        "catalog_deployment_eligible": True, "catalog_deployed": False}
    value["receipt_id"] = "model-publication-" + semantic_digest(value)[:24]
    value["receipt_semantic_digest"] = semantic_digest(value)
    return value


def _identity_and_receipt(handle: Any, model: Mapping[str, Any], artifact: Path,
                          proof: Mapping[str, Any]) -> tuple[CognitiveModelIdentity, dict[str, Any]]:
    load = {"n_ctx": 512, "n_gpu_layers": 0}
    config = ModelConfig([ModelCandidate(artifact, "llama_cpp", str(model["model_id"]), {"gpu_layers": 0})],
        default_engine="llama_cpp", max_context_tokens=512,
        generation=GenerationConfig(max_new_tokens=8, temperature=0, top_p=1))
    authority = build_local_model_authority_map(config, allowed_roots=[artifact.parent],
        observed_at="1970-01-01T00:00:00+00:00")
    record = authority.records[0]
    observed = ActiveModelIdentity(engine=record.engine, resolved_artifact_path=str(artifact.resolve()),
        semantic_artifact_identity=record.semantic_artifact_identity, model_content_sha256=record.model_content_sha256,
        artifact_size_bytes=record.artifact_size_bytes, sidecar_metadata_digest=record.sidecar_metadata_digest,
        configuration_digest=record.configuration_digest, candidate_index=0, posture="production", fallback=False).to_dict()
    authority_payload = {"model_id": model["model_id"], "authority_map_digest": authority.map_digest,
        "observed_active_model_identity": observed}
    authority_digest = _digest(authority_payload)
    identity = CognitiveModelIdentity.create(model_id=str(model["model_id"]),
        semantic_artifact_identity=str(observed["semantic_artifact_identity"]),
        model_content_sha256=str(observed["model_content_sha256"]), artifact_size_bytes=observed["artifact_size_bytes"],
        sidecar_metadata_digest=observed.get("sidecar_metadata_digest"),
        configuration_digest=str(observed["configuration_digest"]), engine_runtime_family="llama_cpp",
        candidate_index=0, active_production=True, fallback=False,
        authority_record_id="commissioned-authority-record-" + authority_digest[7:31],
        authority_record_digest=authority_digest, active_model_identity=observed,
        active_model_identity_digest=_digest(observed))
    body: dict[str, Any] = {"schema_version": COMMISSION_SCHEMA, "status": "local_model_commissioned",
        "execution_principal": COMMISSION_PRINCIPAL, "commissioning_capability_id": COMMISSION_CAPABILITY,
        "effect_set_digest": commissioning_effect_set_digest(), "synthetic_test_evidence": True,
        "installation_identity": handle.identity.value, "catalog_custody_identity": proof["custody_identity"],
        "current_authoritative_catalog_digest": proof["authoritative_catalog_semantic_digest"],
        "current_authoritative_proof_digest": proof["proof_semantic_digest"],
        "deployment_receipt_id": proof["deployment_receipt_id"],
        "deployment_receipt_semantic_digest": proof["deployment_receipt_semantic_digest"],
        "commissioning_intent_id": "synthetic-intent-" + str(model["model_id"]),
        "commissioning_intent_digest": "sha256:" + "1" * 64, "commissioning_plan_digest": "sha256:" + "2" * 64,
        "external_approval_evidence_id": "synthetic-operator-approval-" + str(model["model_id"]),
        "external_approval_semantic_digest": "sha256:" + "3" * 64,
        "hardened_acquisition_plan_digest": "sha256:" + "4" * 64,
        "hardened_acquisition_receipt_identity": "synthetic-acquisition-" + str(model["model_id"]),
        "hardened_acquisition_receipt_digest": "sha256:" + "5" * 64,
        "model_commissioning_admission_ref": "synthetic:model_commissioning:" + str(model["model_id"]),
        "smoke_local_model_inference_admission_ref": "synthetic:local_model_inference:" + str(model["model_id"]),
        "smoke_receipt_digest": "sha256:" + "6" * 64, "model_id": model["model_id"],
        "artifact_sha256": model["artifact_sha256"], "artifact_size_bytes": model["artifact_size_bytes"],
        "runtime_id": "synthetic-runtime", "interpreter_path": "/synthetic/rehearsal/python",
        "load_configuration": load, "authority_map_digest": authority.map_digest,
        "observed_active_model_identity": observed, "admission_outcome": "allow",
        "control_plane_authority_class": "model_commissioning", "model_left_loaded": False,
        "activated": False, "serving_authority_granted": False, "provider_network": False,
        "tool": False, "memory": False, "action": False, "repository_mutation": False,
        "background_inference": False}
    body["receipt_id"] = "commissioning-receipt-" + semantic_digest(body)[:24]
    body["receipt_semantic_digest"] = semantic_digest(body)
    return identity, body


class _Worker:
    def __init__(self, identity: Mapping[str, Any], *, fail_currentness: bool = False) -> None:
        self.active_identity = ActiveModelIdentity(**identity); self.calls = 0
        self._identity, self._fail = dict(identity), fail_currentness

    def generate(self, prompt: str, **_: Any) -> str:
        self.calls += 1
        if self._fail and self.calls == 2:
            changed = dict(self._identity); changed["configuration_digest"] = "sha256:currentness-drift"
            self.active_identity = ActiveModelIdentity(**changed)
        return "synthetic:" + hashlib.sha256(prompt.encode()).hexdigest()[:16]

    def close(self) -> None: pass


def _context() -> FrozenCausalContext:
    current = {"facts": [{"id": "rehearsal-current", "value": "frozen"}]}
    history = ({"id": "rehearsal-history", "value": "synthetic"},)
    return FrozenCausalContext.create(snapshot_id="rehearsal-snapshot", snapshot_digest=_digest({"snapshot": 1}),
        current_projection_id="rehearsal-current-projection", current_projection_digest=_digest(current),
        current_fact_ids=("rehearsal-current",), projected_content_digest=_digest(current),
        current_projection_payload=current, history_record_ids=("rehearsal-history",),
        history_record_digests=(_digest(history[0]),),
        history_record_set_digest=_digest({"record_ids": ["rehearsal-history"], "record_digests": [_digest(history[0])]}),
        history_projection_payload=history, instruction_template="Context: {context}\nHistory: {history}\nAnswer deterministically.",
        instruction_template_digest=_digest({"instruction": "Context: {context}\nHistory: {history}\nAnswer deterministically."}),
        inference_budget={"max_input_chars": 4096, "max_output_chars": 128, "max_new_tokens": 8, "timeout_seconds": 10},
        generation_posture={"temperature": 0, "top_p": 1}, repository_generation_identity="synthetic-rehearsal")


def _paths(root: Path) -> tuple[Path, Path]: return root / "rehearsal", root / "installation"


def prepare(root: Path, *, fault: str | None = None) -> Mapping[str, Any]:
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()): raise ValueError("rehearsal_root_not_empty")
    bundle, state_base = _paths(root); bundle.mkdir(parents=True)
    artifact_dir = root / "synthetic-models"; artifact_dir.mkdir()
    contents = [b"sentientos synthetic rehearsal model A\n", b"sentientos synthetic rehearsal model B\n"]
    artifacts = [artifact_dir / f"rehearsal-{hashlib.sha256(data).hexdigest()}.gguf" for data in contents]
    for artifact, data in zip(artifacts, contents): artifact.write_bytes(data)
    handle = InstallationStateRegistry._for_testing(state_base).open(InstallationIdentity("model-rehearsal"), create=True)
    catalog = _catalog(root, artifacts); custody = ModelCatalogCustody.for_installation(handle)
    digest = local_model_catalog_digest(catalog)
    request = CatalogDeploymentRequest("deterministic_catalog_deployment_controller", "sentientos.local_model_catalog.deploy",
        DEPLOY_EFFECTS, "synthetic-grant", "synthetic-lease", "rehearsal-catalog-deployment", handle.identity.value,
        custody.custody_identity, digest, EXPECTED_ABSENT)
    authority = CatalogDeploymentAuthority("synthetic-grant", "synthetic-lease", request.principal, request.capability_id,
        DEPLOY_EFFECTS, request.correlation_id, handle.identity.value, custody.custody_identity, digest, EXPECTED_ABSENT,
        True, "2026-09-24T00:00:00Z", "2026-09-25T00:00:00Z", synthetic_test_authority=True)
    deploy_local_model_catalog(handle, request, authority, catalog, [_publication(m) for m in catalog["models"]],
        now=lambda: "2026-09-24T12:00:00Z")
    proof = construct_authoritative_catalog_consumer_proof(handle).proof
    pairs = [_identity_and_receipt(handle, model, artifact, proof)
             for model, artifact in zip(catalog["models"], artifacts)]
    handle.ensure_directory(handle.fixed_object("local-model/commissioning/receipts"))
    for _, receipt in pairs:
        handle.durable_create(handle.fixed_object(f"local-model/commissioning/receipts/{receipt['receipt_id']}.json"),
            (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode())
    context = _context(); provenance = [ModelDevelopmentProvenance.create(item[0]) for item in pairs]
    class Endpoint:
        def __init__(self, identity: CognitiveModelIdentity): self.identity = identity
        def current_identity(self) -> CognitiveModelIdentity: return self.identity
        def infer(self, **_: Any) -> Mapping[str, Any]: raise RuntimeError("prepare_performs_zero_inference")
    experiment = DevelopmentalModelReplacementExperiment(context=context, model_a=Endpoint(pairs[0][0]),
        model_b=Endpoint(pairs[1][0]), artifact_root=bundle, model_a_provenance=provenance[0], model_b_provenance=provenance[1])
    experiment.store.persist_provenance(provenance[0]); experiment.store.persist_provenance(provenance[1])
    experiment.store.persist_protocol(experiment.protocol)
    campaign = DevelopmentalModelReplacementCampaign.create(experiment=experiment, artifact_root=bundle,
        trial_ids=("rehearsal-trial-1", "rehearsal-trial-2"))
    activation = handle.root / "local-model/activation/active.json"; activation.parent.mkdir(parents=True)
    atomic_write_json(activation, {"sentinel": "canonical-activation-unchanged"})
    scenario: dict[str, Any] = {"schema_version": SCENARIO_SCHEMA, "scenario_name": "developmental-model-replacement-system-rehearsal",
        "fault": fault, "installation_identity": handle.identity.value, "context": asdict(context),
        "provenance_a": asdict(provenance[0]), "provenance_b": asdict(provenance[1]),
        "protocol_id": experiment.protocol.protocol_id, "protocol_digest": experiment.protocol.protocol_digest,
        "campaign_id": campaign.protocol.campaign_id, "campaign_digest": campaign.protocol.campaign_digest,
        "commissioning_receipt_a": pairs[0][1]["receipt_id"], "commissioning_receipt_b": pairs[1][1]["receipt_id"],
        "model_a_identity_digest": pairs[0][0].identity_digest, "model_b_identity_digest": pairs[1][0].identity_digest,
        "expected_trial_ids": ["rehearsal-trial-1", "rehearsal-trial-2"],
        "activation_baseline": _snapshot(activation),
        "production_serving_baseline": _snapshot(handle.root / "local-model/serving/active.json"),
        "history_record_set_digest": context.history_record_set_digest, "evidence_posture": "synthetic_test_trial"}
    scenario["scenario_id"] = "model-replacement-rehearsal-" + semantic_digest(scenario)[:24]
    scenario["scenario_digest"] = semantic_digest(scenario)
    atomic_write_json(bundle / "scenario.json", scenario)
    manifest = {"schema_version": SCENARIO_SCHEMA, "scenario_id": scenario["scenario_id"],
        "scenario_digest": scenario["scenario_digest"], "protocol_id": scenario["protocol_id"],
        "protocol_digest": scenario["protocol_digest"], "campaign_id": scenario["campaign_id"],
        "campaign_digest": scenario["campaign_digest"], "frozen_causal_context_digest": context.context_digest,
        "developmental_history_record_set_digest": context.history_record_set_digest,
        "synthetic_commissioning_receipt_ids": [scenario["commissioning_receipt_a"], scenario["commissioning_receipt_b"]],
        "model_identity_digests": [scenario["model_a_identity_digest"], scenario["model_b_identity_digest"]],
        "activation_baseline": scenario["activation_baseline"], "production_serving_baseline": scenario["production_serving_baseline"],
        "expected_trial_inventory": scenario["expected_trial_ids"]}
    manifest["manifest_digest"] = semantic_digest(manifest); atomic_write_json(bundle / "manifest.json", manifest)
    atomic_write_json(bundle / "preparation_receipt.json", {"status": "prepared_zero_trials", **manifest})
    (bundle / "README.md").write_text("Synthetic test-only developmental model-replacement system rehearsal. Not production evidence.\n")
    return scenario


def _load(root: Path) -> tuple[Path, Any, dict[str, Any], FrozenCausalContext, ModelDevelopmentProvenance, ModelDevelopmentProvenance]:
    bundle, base = _paths(Path(root).resolve()); scenario = _read(bundle / "scenario.json")
    claimed = scenario.pop("scenario_digest"); assert claimed == semantic_digest(scenario); scenario["scenario_digest"] = claimed
    handle = InstallationStateRegistry._for_testing(base).open(InstallationIdentity(str(scenario["installation_identity"])))
    context_raw = dict(scenario["context"]); context_raw["current_fact_ids"] = tuple(context_raw["current_fact_ids"])
    context_raw["history_record_ids"] = tuple(context_raw["history_record_ids"]); context_raw["history_record_digests"] = tuple(context_raw["history_record_digests"])
    context_raw["history_projection_payload"] = tuple(context_raw["history_projection_payload"])
    context = FrozenCausalContext(**context_raw)
    def provenance(key: str) -> ModelDevelopmentProvenance:
        raw = dict(scenario[key]); raw["claims"] = tuple(raw["claims"]); return ModelDevelopmentProvenance(**raw)
    return bundle, handle, scenario, context, provenance("provenance_a"), provenance("provenance_b")


def _approval(intent: Mapping[str, Any], suffix: str) -> dict[str, Any]:
    value = {"schema_version": APPROVAL_SCHEMA, "approval_status": "approved",
        "approval_evidence_id": "synthetic-rehearsal-approval-" + suffix, "operator_identity": "rehearsal-operator",
        "evidence_source": "isolated-rehearsal", "evidence_provenance": "synthetic-test-fixture",
        "approval_timestamp": FIXED_TIME.isoformat(), "not_before": (FIXED_TIME - timedelta(hours=1)).isoformat(),
        "expires_at": (FIXED_TIME + timedelta(hours=1)).isoformat(), "synthetic_test_evidence": True,
        **approval_bindings(intent)}
    value["approval_digest"] = semantic_digest(value); return value


def run_next(root: Path) -> Mapping[str, Any]:
    bundle, handle, scenario, context, pa, pb = _load(root)
    controller = ExperimentalModelServingController(handle, ControlPlaneKernel(decisions_path=bundle / "intent-decisions.jsonl"),
        artifact_root=bundle, allow_synthetic_evidence_for_tests=True)
    ia = controller.prepare_intent(protocol_id=scenario["protocol_id"], protocol_digest=scenario["protocol_digest"],
        model_role="model_a", commissioning_receipt_id=scenario["commissioning_receipt_a"], correlation_id="rehearsal-serving-a")
    ib = controller.prepare_intent(protocol_id=scenario["protocol_id"], protocol_digest=scenario["protocol_digest"],
        model_role="model_b", commissioning_receipt_id=scenario["commissioning_receipt_b"], correlation_id="rehearsal-serving-b")
    fault = scenario.get("fault"); constructed = [0]
    def factory(chain: Mapping[str, Any], _: Mapping[str, Any]) -> _Worker:
        constructed[0] += 1
        if fault == "model_b_load_failure" and constructed[0] == 2: raise RuntimeError("injected_model_b_load_failure")
        identity = _read(handle.root / "local-model/commissioning/receipts" / ((scenario["commissioning_receipt_a"] if constructed[0] == 1 else scenario["commissioning_receipt_b"]) + ".json"))["observed_active_model_identity"]
        if fault == "loaded_identity_drift": identity = {**identity, "configuration_digest": "sha256:loaded-drift"}
        return _Worker(identity, fail_currentness=fault == "inference_currentness_failure" and constructed[0] == 1)
    runner = DevelopmentalModelReplacementProductionTrialRunner(handle,
        ControlPlaneKernel(decisions_path=bundle / "run-decisions.jsonl"), campaign_artifact_root=bundle,
        experiment_artifact_root=bundle, model_factory=factory, allow_synthetic_evidence_for_tests=True)
    result = runner.run_one(campaign_id=scenario["campaign_id"], campaign_digest=scenario["campaign_digest"],
        base_protocol_id=scenario["protocol_id"], base_protocol_digest=scenario["protocol_digest"],
        commissioning_receipt_a=scenario["commissioning_receipt_a"], commissioning_receipt_b=scenario["commissioning_receipt_b"],
        serving_correlation_a="rehearsal-serving-a", serving_correlation_b="rehearsal-serving-b",
        serving_approval_a=_approval(ia, "a"), serving_approval_b=_approval(ib, "b"),
        invocation_correlation="rehearsal-run-one", observation_time=FIXED_TIME, context=context,
        provenance_a=pa, provenance_b=pb, evidence_posture="synthetic_test_trial")
    if result["status"] == "completed_one_trial":
        target = bundle / "trial_receipts" / f"{result['receipt']['trial_id']}.json"; target.parent.mkdir(exist_ok=True)
        atomic_write_json(target, dict(result["receipt"]))
    return dict(result)


def verify(root: Path) -> Mapping[str, Any]:
    bundle, handle, scenario, context, pa, pb = _load(root)
    class Endpoint:
        def __init__(self, identity: CognitiveModelIdentity): self.identity = identity
        def current_identity(self) -> CognitiveModelIdentity: return self.identity
        def infer(self, **_: Any) -> Mapping[str, Any]: raise RuntimeError("verification_must_not_infer")
    protocol = ModelReplacementArtifactStore(bundle).load_verified_protocol(scenario["protocol_id"], scenario["protocol_digest"])
    experiment = DevelopmentalModelReplacementExperiment(context=context, model_a=Endpoint(protocol.model_a_identity),
        model_b=Endpoint(protocol.model_b_identity), artifact_root=bundle, model_a_provenance=pa, model_b_provenance=pb)
    campaign = DevelopmentalModelReplacementCampaign.reconstruct(experiment=experiment, artifact_root=bundle,
        campaign_id=scenario["campaign_id"]); state = campaign.store.load_state(campaign.protocol)
    receipts = sorted((bundle / "trial_receipts").glob("*.json")) if (bundle / "trial_receipts").exists() else []
    values = [_read(path) for path in receipts]
    for value in values: verify_production_trial_receipt(value)
    activation = _snapshot(handle.root / "local-model/activation/active.json")
    serving = _snapshot(handle.root / "local-model/serving/active.json")
    if activation != scenario["activation_baseline"]: raise ValueError("canonical_activation_changed")
    if serving != scenario["production_serving_baseline"]: raise ValueError("canonical_production_serving_changed")
    completed = [item["trial_id"] for item in state["completed_trials"]]
    if len(values) != len(completed) or any(v["evidence_posture"] != "synthetic_test_trial" for v in values):
        raise ValueError("rehearsal_evidence_inventory_invalid")
    body: dict[str, Any] = {"schema_version": VERIFICATION_SCHEMA, "scenario_id": scenario["scenario_id"],
        "scenario_digest": scenario["scenario_digest"], "campaign_id": scenario["campaign_id"],
        "campaign_digest": scenario["campaign_digest"], "campaign_state_digest": state["state_digest"],
        "completed_trial_ids": completed, "next_trial_id": state["next_trial_id"],
        "production_trial_receipts": [{"receipt_id": v["receipt_id"], "receipt_digest": v["receipt_digest"]} for v in values],
        "runs": [{"run_id": v["run_id"], "run_digest": v["run_digest"]} for v in values],
        "serving_receipts": [v[key] for v in values for key in ("model_a_serving", "model_b_serving")],
        "closure_receipts": [v[key] for v in values for key in ("model_a_closure", "model_b_closure")],
        "inference_receipts": [item for v in values for item in v["inference_receipts"]],
        "activation_preserved": True, "production_serving_preserved": True,
        "developmental_history_preserved": context.history_record_set_digest == scenario["history_record_set_digest"],
        "synthetic_only_posture": True, "no_autonomous_repetition": True,
        "status": "verified_complete" if len(completed) == 2 else "verified_incomplete"}
    body["verification_receipt_id"] = "rehearsal-verification-" + semantic_digest(body)[:24]
    body["verification_receipt_digest"] = semantic_digest(body)
    target = bundle / "verification" / ("final.json" if len(completed) == 2 else f"after-{len(completed)}-trials.json")
    target.parent.mkdir(exist_ok=True); atomic_write_json(target, body)
    return body


def summarize(root: Path) -> Mapping[str, Any]:
    bundle, _, scenario, context, pa, pb = _load(root)
    protocol = ModelReplacementArtifactStore(bundle).load_verified_protocol(scenario["protocol_id"], scenario["protocol_digest"])
    class E:
        def __init__(self, i: CognitiveModelIdentity): self.i = i
        def current_identity(self) -> CognitiveModelIdentity: return self.i
        def infer(self, **_: Any) -> Mapping[str, Any]: raise RuntimeError("summary_must_not_infer")
    experiment = DevelopmentalModelReplacementExperiment(context=context, model_a=E(protocol.model_a_identity),
        model_b=E(protocol.model_b_identity), artifact_root=bundle, model_a_provenance=pa, model_b_provenance=pb)
    report = DevelopmentalModelReplacementCampaign.reconstruct(experiment=experiment, artifact_root=bundle,
        campaign_id=scenario["campaign_id"]).summarize()
    atomic_write_json(bundle / "campaign_summary.json", report); return cast(Mapping[str, Any], report)
