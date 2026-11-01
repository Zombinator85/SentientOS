from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from sentientos.commissioned_model_evidence import (
    CommissionedModelEvidenceError, verify_commissioned_model,
)
from sentientos.control_plane_kernel import (
    AdmissionOutcome, ControlActionDecision, LifecyclePhase,
)
from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model import ActiveModelIdentity
from sentientos.local_model_authority import (
    build_local_model_authority_map, build_rootless_experimental_model_authority_map,
)
from sentientos.local_runtime_provisioning import semantic_digest
from sentientos.rootless_experimental_local_model import (
    EXPERIMENT_ROOT, MODEL_MANIFEST_SCHEMA, RootlessExperimentalError,
    _rootless_governance_custody,
    execute_intent, prepare_intent, validate_experiment_root, verify_model_manifest,
    verify_intent, verify_rootless_receipt,
)

pytestmark = pytest.mark.no_legacy_skip


def _configure_workspace(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = workspace / "sentientos-data" / "rootless-experimental"
    monkeypatch.setattr("sentientos.rootless_experimental_local_model.WORKSPACE_ROOT", workspace)
    monkeypatch.setattr("sentientos.rootless_experimental_local_model.EXPERIMENT_ROOT", root)
    return workspace, root


def _manifest(root: Path) -> dict:
    model = b"verified test model bytes"
    digest = hashlib.sha256(model).hexdigest()
    artifact = root / "models" / "sha256" / digest / "tiny.gguf"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(model)
    card = root / "source" / "README.md"
    license_file = root / "source" / "LICENSE"
    card.parent.mkdir(parents=True)
    card.write_text("---\nlicense: apache-2.0\n---\nTest model card\n", encoding="utf-8")
    license_file.write_text("Apache License\nVersion 2.0\n", encoding="utf-8")
    repo = "test-org/test-model"
    revision = "a" * 40
    value = {"schema_version": MODEL_MANIFEST_SCHEMA, "model_id": "test-model",
        "repo_id": repo, "repo_revision": revision, "file_revision": "b" * 40,
        "filename": "tiny.gguf", "artifact_path": str(artifact),
        "source_url": f"https://huggingface.co/{repo}/resolve/{revision}/tiny.gguf",
        "model_card_url": f"https://huggingface.co/{repo}/resolve/{revision}/README.md",
        "model_card_path": str(card), "model_card_sha256": hashlib.sha256(card.read_bytes()).hexdigest(),
        "license_id": "apache-2.0", "license_url": f"https://huggingface.co/{repo}/blob/{revision}/LICENSE",
        "license_file_path": str(license_file),
        "license_file_sha256": hashlib.sha256(license_file.read_bytes()).hexdigest(),
        "artifact_sha256": digest, "artifact_size_bytes": len(model),
        "retrieved_at": "2026-11-01T00:00:00+00:00", "retrieval_final_host": "huggingface.co",
        "huggingface_lfs_oid": digest}
    value["manifest_digest"] = semantic_digest(value)
    return value


def _receipt(value: dict) -> dict:
    value["receipt_semantic_digest"] = semantic_digest(value)
    return value


def _runtime_receipts(workspace: Path, tmp_path: Path) -> tuple[Path, Path, Path]:
    runtime = workspace / "runtime" / "installation.json"
    imported = workspace / "runtime" / "import.json"
    backend = workspace / "runtime" / "backend.json"
    runtime.parent.mkdir(parents=True)
    install_value = _receipt({"schema_version": "sentientos.local_runtime_installation_receipt:v1",
        "status": "installed_verified", "runtime_installed": True, "engine": "llama_cpp",
        "backend_family": "cpu", "runtime_id": "llama-cpp-python-0.3.35-cpu-linux-x86_64",
        "model_load_performed": False, "commissioning_performed": False,
        "runtime_execution_authority_granted": False,
        "venv_interpreter_identity": {"executable": sys.executable},
        "artifacts": [{"package": "llama-cpp-python", "version": "0.3.35"}]})
    import_value = _receipt({"schema_version": "sentientos.local_runtime_import_verification_receipt:v1",
        "status": "runtime_import_verified", "runtime_available_for_import": True,
        "runtime_import_performed": True, "model_load_performed": False,
        "commissioning_performed": False, "runtime_id": install_value["runtime_id"],
        "installation_receipt_semantic_digest": install_value["receipt_semantic_digest"]})
    backend_value = _receipt({"schema_version": "sentientos.local_runtime_backend_verification_receipt:v1",
        "status": "runtime_backend_verified", "selected_backend": "CPU",
        "selected_backend_verified": True, "native_runtime_library_loaded": True,
        "inference_performed": False,
        "model_load_performed": False, "commissioning_performed": False,
        "runtime_execution_authority_granted": False,
        "runtime_id": install_value["runtime_id"],
        "installation_receipt_semantic_digest": install_value["receipt_semantic_digest"],
        "runtime_import_verification_receipt_semantic_digest": import_value["receipt_semantic_digest"]})
    for path, value in ((runtime, install_value), (imported, import_value), (backend, backend_value)):
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return runtime, imported, backend


def _prepare(monkeypatch, tmp_path, prompt="Return exactly: ROOTLESS-OK"):
    workspace, root = _configure_workspace(monkeypatch, tmp_path)
    manifest = _manifest(root)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "model-artifact-manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    runtime_paths = _runtime_receipts(workspace, tmp_path)
    intent = prepare_intent(model_manifest_path=manifest_path,
        installation_receipt_path=runtime_paths[0], import_receipt_path=runtime_paths[1],
        backend_receipt_path=runtime_paths[2], prompt=prompt, root=root,
        correlation_id="rootless-experiment-" + "1" * 32)
    return workspace, root, manifest, manifest_path, runtime_paths, intent


def test_experimental_custody_is_workspace_scoped_and_rejects_symlinks(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(RootlessExperimentalError, match="outside_workspace"):
        validate_experiment_root(tmp_path / "outside", workspace_root=workspace)
    actual = workspace / "actual"
    actual.mkdir()
    link = workspace / "linked"
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(RootlessExperimentalError, match="symlinked"):
        validate_experiment_root(link, workspace_root=workspace)


def test_governor_auxiliary_state_is_scoped_and_restored(tmp_path, monkeypatch):
    import sentientos.federated_governance as federation_module
    import sentientos.trust_ledger as trust_ledger_module

    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", "/previous/pulse-root")
    monkeypatch.delenv("PULSE_TRUST_EPOCH_STATE", raising=False)
    run_root = tmp_path / "workspace" / "rootless" / "runs" / "intent"
    with _rootless_governance_custody(run_root):
        assert federation_module.get_controller()._federation_root == run_root / "federation"
        assert trust_ledger_module.get_trust_ledger()._federation_root == run_root / "federation"
        assert Path(os.environ["PULSE_TRUST_EPOCH_ROOT"]) == run_root / "pulse-trust-epoch"
        assert Path(os.environ["PULSE_TRUST_EPOCH_STATE"]) == (
            run_root / "pulse-trust-epoch" / "epoch_state.json")
    assert federation_module.get_controller()._federation_root != run_root / "federation"
    assert trust_ledger_module.get_trust_ledger()._federation_root != run_root / "federation"
    assert os.environ["PULSE_TRUST_EPOCH_ROOT"] == "/previous/pulse-root"
    assert "PULSE_TRUST_EPOCH_STATE" not in os.environ


def test_artifact_manifest_verifies_license_source_size_and_sha(tmp_path, monkeypatch):
    _, root = _configure_workspace(monkeypatch, tmp_path)
    manifest = _manifest(root)
    verified = verify_model_manifest(manifest, root=root)
    assert verified["verified_artifact_sha256"] == manifest["artifact_sha256"]
    assert verified["verified_artifact_size_bytes"] == manifest["artifact_size_bytes"]
    artifact = Path(manifest["artifact_path"])
    artifact.write_bytes(b"tampered")
    with pytest.raises(RootlessExperimentalError, match="integrity_mismatch"):
        verify_model_manifest(manifest, root=root)


class _AllowKernel:
    def __init__(self, root: Path):
        self.root = root

    def admit(self, request):
        return ControlActionDecision(AdmissionOutcome.ALLOW, ("admitted",),
            LifecyclePhase.RUNTIME, request.requested_phase, request.authority_class,
            request.action_kind, request.actor, request.target_subsystem, {},
            str(request.metadata["correlation_id"]))


class _OneResponseModel:
    def __init__(self, chain, load):
        config = ModelConfig([ModelCandidate(Path(chain["artifact_path"]), "llama_cpp", chain["model_id"],
            {"gpu_layers": load["n_gpu_layers"], "n_threads": load["n_threads"]})],
            default_engine="llama_cpp", max_context_tokens=load["n_ctx"],
            generation=GenerationConfig(max_new_tokens=load["max_new_tokens"], temperature=0, top_p=1))
        authority = build_rootless_experimental_model_authority_map(config,
            allowed_roots=[Path(chain["artifact_path"]).parent])
        record = authority.records[0]
        self.active_identity = ActiveModelIdentity(engine="llama_cpp",
            resolved_artifact_path=record.observed_metadata["resolved_artifact_path"],
            semantic_artifact_identity=record.semantic_artifact_identity,
            model_content_sha256=record.model_content_sha256,
            artifact_size_bytes=record.artifact_size_bytes,
            sidecar_metadata_digest=record.sidecar_metadata_digest,
            configuration_digest=record.configuration_digest, candidate_index=0,
            posture="rootless_experimental", fallback=False)
        self.peak_rss_kib = 1024
        self.user_cpu_seconds = 0.1
        self.system_cpu_seconds = 0.01

    def generate(self, prompt, **generation):
        assert generation["temperature"] == 0
        assert generation["max_new_tokens"] <= 16
        return "ROOTLESS-OK"

    def close(self):
        return None


def test_one_shot_executor_uses_governed_invoker_and_verifiable_nonproduction_receipt(tmp_path, monkeypatch):
    workspace, root, _, manifest_path, runtime_paths, intent = _prepare(monkeypatch, tmp_path)
    factory_calls = []

    def model_factory(chain, load, *, identity_posture):
        assert identity_posture == "rootless_experimental"
        factory_calls.append((chain, load))
        return _OneResponseModel(chain, load)

    result = execute_intent(intent_path=root / "intents" / f"{intent['intent_id']}.json",
        confirm_intent_digest=intent["intent_digest"], model_manifest_path=manifest_path,
        installation_receipt_path=runtime_paths[0], import_receipt_path=runtime_paths[1],
        backend_receipt_path=runtime_paths[2], root=root, model_factory=model_factory,
        kernel_factory=_AllowKernel)
    assert result["status"] == "rootless_experimental_inference_completed"
    assert result["raw_response"] == "ROOTLESS-OK"
    assert result["prompt"] == intent["prompt"]
    assert result["worker_identity"]["posture"] == "rootless_experimental"
    assert result["execution_budget"]["n_ctx"] == 512
    assert result["execution_budget"]["n_gpu_layers"] == 0
    assert result["execution_budget"]["n_threads"] == 5
    assert result["execution_budget"]["max_new_tokens"] == 16
    assert result["production_authority"] is False
    assert result["eligible_as_production_commissioning_evidence"] is False
    assert result["resource_measurements"]["peak_rss_bytes"] == 1024 * 1024
    assert verify_rootless_receipt(result, root=root) == (True, [])
    assert len(factory_calls) == 1

    tampered_response = dict(result)
    tampered_response["raw_response"] = "modified"
    assert verify_rootless_receipt(tampered_response, root=root)[0] is False
    excessive_budget = dict(intent)
    excessive_budget["limits"] = {**intent["limits"], "n_gpu_layers": 1}
    excessive_body = dict(excessive_budget)
    excessive_body.pop("intent_digest")
    excessive_budget["intent_digest"] = semantic_digest(excessive_body)
    with pytest.raises(RootlessExperimentalError, match="scope_or_limit_invalid"):
        verify_intent(excessive_budget, root=root)

    with pytest.raises(RootlessExperimentalError, match="one_shot"):
        execute_intent(intent_path=root / "intents" / f"{intent['intent_id']}.json",
            confirm_intent_digest=intent["intent_digest"], model_manifest_path=manifest_path,
            installation_receipt_path=runtime_paths[0], import_receipt_path=runtime_paths[1],
            backend_receipt_path=runtime_paths[2], root=root, model_factory=model_factory,
            kernel_factory=_AllowKernel)
    assert len(factory_calls) == 1


def test_denied_control_plane_never_executes_model_and_receipt_is_not_production_custody(
        tmp_path, monkeypatch):
    workspace, root, _, manifest_path, runtime_paths, intent = _prepare(monkeypatch, tmp_path)
    class DenyKernel:
        def admit(self, request):
            return ControlActionDecision(AdmissionOutcome.DENY, ("operator_policy_denied",),
                LifecyclePhase.RUNTIME, request.requested_phase, request.authority_class,
                request.action_kind, request.actor, request.target_subsystem, {},
                str(request.metadata["correlation_id"]))

    class CountingModel(_OneResponseModel):
        calls = 0
        def generate(self, prompt, **generation):
            self.calls += 1
            return super().generate(prompt, **generation)

    instances = []
    def model_factory(chain, load, *, identity_posture):
        value = CountingModel(chain, load); instances.append(value); return value

    result = execute_intent(intent_path=root / "intents" / f"{intent['intent_id']}.json",
        confirm_intent_digest=intent["intent_digest"], model_manifest_path=manifest_path,
        installation_receipt_path=runtime_paths[0], import_receipt_path=runtime_paths[1],
        backend_receipt_path=runtime_paths[2], root=root, model_factory=model_factory,
        kernel_factory=lambda path: DenyKernel())
    assert result["status"] == "rootless_experimental_inference_blocked"
    assert instances[0].calls == 0
    assert result["raw_response"] is None
    assert result["eligible_as_production_commissioning_evidence"] is False

    registry = InstallationStateRegistry._for_testing(tmp_path / "canonical-state")
    handle = registry.open(InstallationIdentity.parse("rootless-test"), create=True)
    with pytest.raises(CommissionedModelEvidenceError, match="not_in_canonical_custody"):
        verify_commissioned_model(handle, "commissioning-receipt-" + "a" * 24)


def test_experimental_identity_cannot_satisfy_production_authority_map(tmp_path):
    artifact = tmp_path / "model.gguf"
    artifact.write_bytes(b"model")
    config = ModelConfig([ModelCandidate(artifact, "llama_cpp", "model", {"gpu_layers": 0})],
        default_engine="llama_cpp", max_context_tokens=512,
        generation=GenerationConfig(max_new_tokens=8, temperature=0, top_p=1))
    production = build_local_model_authority_map(config, allowed_roots=[tmp_path])
    record = production.records[0]
    experimental_identity = ActiveModelIdentity("llama_cpp", str(artifact.resolve()),
        record.semantic_artifact_identity, record.model_content_sha256, record.artifact_size_bytes,
        record.sidecar_metadata_digest, record.configuration_digest, 0,
        "rootless_experimental", False)
    assert production.record_for_active_identity(experimental_identity, "local_user_chat") is None

