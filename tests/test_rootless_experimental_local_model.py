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
from sentientos.governed_local_model_invocation import (
    LocalModelInvocationBudget, RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA,
)
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model import ActiveModelIdentity
from sentientos.local_model_authority import (
    ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
    build_local_model_authority_map,
    build_rootless_experimental_epistemic_authority_map,
    build_rootless_experimental_model_authority_map,
)
from sentientos.local_runtime_provisioning import semantic_digest
from sentientos.epistemic_revision_pressure_control import UnsupportedPressurePair
from sentientos.epistemic_revision_qualification import (
    IndependentAnswerKey, RevisionCase,
)
from sentientos.epistemic_revision_stability_series import (
    EpistemicCorrectionPressureSeries,
)
from sentientos.rootless_experimental_local_model import (
    EXPERIMENT_ROOT, MODEL_MANIFEST_SCHEMA, RootlessExperimentalError,
    _rootless_governance_custody,
    execute_intent, prepare_intent, validate_experiment_root, verify_model_manifest,
    verify_runtime_bundle,
    verify_intent, verify_rootless_receipt,
)
from sentientos.rootless_experimental_epistemic_session import (
    MAX_CALL_TIMEOUT_SECONDS, MAX_PROMPT_CHARS,
    RootlessExperimentalEpistemicSession,
)
from sentientos.rootless_experimental_epistemic_series import (
    _call_budget_record, _case_commitment_material, _case_from_material,
    _persist_score_record, _persist_series_failure_record, _pop_prompt_condition,
)
from scripts.run_rootless_experimental_epistemic_series import (
    PRESSURE_STATEMENT, _snapshot,
)
from sentientos.world_state_board import to_dict

pytestmark = pytest.mark.no_legacy_skip


def test_rootless_preregistration_binds_finite_no_retry_call_deadline():
    assert _call_budget_record() == {
        "max_calls": 4, "max_calls_per_correlation": 1,
        "per_call_timeout_seconds": MAX_CALL_TIMEOUT_SECONDS,
        "retry_policy": "no_retry"}
    assert MAX_CALL_TIMEOUT_SECONDS == 180


def test_rootless_score_write_failure_preserves_partial_and_capture_custody(
        tmp_path, monkeypatch):
    import sentientos.rootless_experimental_epistemic_series as series_module

    _, root = _configure_workspace(monkeypatch, tmp_path)
    monkeypatch.setattr(series_module, "EXPERIMENT_ROOT", root)
    run_root = root / "epistemic-runs" / ("rootless-epistemic-run-" + "1" * 24)
    run_root.mkdir(parents=True, mode=0o700)
    partial = b'{"partial":'
    score = {
        "run_id": run_root.name,
        "preregistration_digest": "a" * 64,
        "capture_index_digest": "b" * 64,
    }
    expected_score_digest = semantic_digest(score)
    original_write = series_module._exclusive_json
    write_attempts = []

    def fail_score_write(path, value, *, root):
        write_attempts.append(path.name)
        if path.name == "scores.json":
            path.write_bytes(partial)
            raise OSError("simulated partial score write")
        return original_write(path, value, root=root)

    monkeypatch.setattr(series_module, "_exclusive_json", fail_score_write)

    with pytest.raises(RootlessExperimentalError,
            match="epistemic_score_record_write_failed"):
        _persist_score_record(run_root, score)

    failure_path = run_root / "scoring-write-failure.json"
    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    assert write_attempts == ["scores.json", "scoring-write-failure.json"]
    assert failure["schema_version"] == (
        "sentientos.rootless_experimental_scoring_write_failure:v1")
    assert failure["capture_index_digest"] == score["capture_index_digest"]
    assert failure["attempted_score_record_digest"] == expected_score_digest
    assert failure["complete_score_record_written"] is False
    assert failure["inference_replayed"] is False
    assert failure["production_authority"] is False
    assert failure["partial_score_artifact"] == {
        "path": str((run_root / "scores.json").relative_to(root)),
        "status": "captured",
        "size_bytes": len(partial),
        "sha256": hashlib.sha256(partial).hexdigest(),
    }
    assert (run_root / "scores.json").read_bytes() == partial


def test_rootless_score_write_success_has_no_failure_record(tmp_path, monkeypatch):
    import sentientos.rootless_experimental_epistemic_series as series_module

    _, root = _configure_workspace(monkeypatch, tmp_path)
    monkeypatch.setattr(series_module, "EXPERIMENT_ROOT", root)
    run_root = root / "epistemic-runs" / ("rootless-epistemic-run-" + "2" * 24)
    run_root.mkdir(parents=True, mode=0o700)
    score = {"run_id": run_root.name}

    written_score = _persist_score_record(run_root, score)

    assert json.loads((run_root / "scores.json").read_text(encoding="utf-8")) == written_score
    assert written_score["score_record_digest"] == semantic_digest(score)
    assert not (run_root / "scoring-write-failure.json").exists()


def test_rootless_post_capture_scoring_failure_binds_durable_capture_index(
        tmp_path, monkeypatch):
    import sentientos.rootless_experimental_epistemic_series as series_module

    _, root = _configure_workspace(monkeypatch, tmp_path)
    monkeypatch.setattr(series_module, "EXPERIMENT_ROOT", root)
    run_root = root / "epistemic-runs" / ("rootless-epistemic-run-" + "3" * 24)
    run_root.mkdir(parents=True, mode=0o700)
    capture_index = {
        "schema_version": "sentientos.rootless_experimental_epistemic_capture_index:v1",
        "run_id": run_root.name,
        "preregistration_digest": "f" * 64,
        "capture_count": 4,
        "captures": [],
        "scoring_started": False,
        "production_authority": False,
    }
    capture_index["capture_index_digest"] = semantic_digest(capture_index)
    series_module._exclusive_json(run_root / "capture-index.json", capture_index,
        root=root)
    error = RootlessExperimentalError("pressure_treatment_binding_invalid")
    capture_digest = capture_index["capture_index_digest"]

    _persist_series_failure_record(run_root, run_id=run_root.name,
        preregistration_digest="f" * 64, captures_durable=True,
        capture_index_digest=capture_digest, error=error)

    failure = json.loads((run_root / "scoring-failure-review.json").read_text(
        encoding="utf-8"))
    assert failure["schema_version"] == (
        "sentientos.rootless_experimental_epistemic_scoring_failure:v1")
    assert failure["run_id"] == run_root.name
    assert failure["preregistration_digest"] == "f" * 64
    assert failure["capture_index_digest"] == capture_digest
    assert failure["captured_observations"] == 4
    assert failure["failure_code"] == "pressure_treatment_binding_invalid"
    assert failure["scoring_started"] is True
    assert failure["score_record_write_attempted"] is False
    assert failure["complete_score_record_written"] is False
    assert failure["inference_replayed"] is False
    assert failure["production_authority"] is False
    assert not (run_root / "execution-failure.json").exists()


def test_rootless_post_capture_failure_rejects_changed_capture_index(
        tmp_path, monkeypatch):
    import sentientos.rootless_experimental_epistemic_series as series_module

    _, root = _configure_workspace(monkeypatch, tmp_path)
    monkeypatch.setattr(series_module, "EXPERIMENT_ROOT", root)
    run_root = root / "epistemic-runs" / ("rootless-epistemic-run-" + "5" * 24)
    run_root.mkdir(parents=True, mode=0o700)
    capture_index = {
        "schema_version": "sentientos.rootless_experimental_epistemic_capture_index:v1",
        "run_id": run_root.name,
        "preregistration_digest": "2" * 64,
        "capture_count": 4,
        "captures": [],
        "scoring_started": False,
        "production_authority": False,
    }
    capture_index["capture_index_digest"] = semantic_digest(capture_index)
    series_module._exclusive_json(run_root / "capture-index.json", capture_index,
        root=root)
    changed_index = dict(capture_index)
    changed_index.pop("capture_index_digest")
    changed_index["capture_count"] = 3
    changed_index["capture_index_digest"] = semantic_digest(changed_index)
    (run_root / "capture-index.json").write_text(
        json.dumps(changed_index), encoding="utf-8")

    with pytest.raises(RootlessExperimentalError,
            match="epistemic_scoring_failure_capture_index_changed"):
        _persist_series_failure_record(run_root, run_id=run_root.name,
            preregistration_digest="2" * 64, captures_durable=True,
            capture_index_digest=capture_index["capture_index_digest"],
            error=ValueError("scoring failed"))

    assert not (run_root / "scoring-failure-review.json").exists()


def test_rootless_pre_capture_failure_remains_execution_failure(
        tmp_path, monkeypatch):
    import sentientos.rootless_experimental_epistemic_series as series_module

    _, root = _configure_workspace(monkeypatch, tmp_path)
    monkeypatch.setattr(series_module, "EXPERIMENT_ROOT", root)
    run_root = root / "epistemic-runs" / ("rootless-epistemic-run-" + "4" * 24)
    run_root.mkdir(parents=True, mode=0o700)

    _persist_series_failure_record(run_root, run_id=run_root.name,
        preregistration_digest="1" * 64, captures_durable=False,
        capture_index_digest=None, error=ValueError("backend unavailable"))

    failure = json.loads((run_root / "execution-failure.json").read_text(
        encoding="utf-8"))
    assert failure["schema_version"] == (
        "sentientos.rootless_experimental_epistemic_failure:v1")
    assert failure["failure_type"] == "ValueError"
    assert failure["failure_code"] == "ValueError"
    assert failure["inference_replayed"] is False
    assert failure["production_authority"] is False
    assert not (run_root / "scoring-failure-review.json").exists()


def test_rootless_partial_capture_failure_binds_durable_index(
        tmp_path, monkeypatch):
    import sentientos.rootless_experimental_epistemic_series as series_module

    _, root = _configure_workspace(monkeypatch, tmp_path)
    monkeypatch.setattr(series_module, "EXPERIMENT_ROOT", root)
    run_root = root / "epistemic-runs" / ("rootless-epistemic-run-" + "6" * 24)
    run_root.mkdir(parents=True, mode=0o700)
    partial_index = {
        "schema_version":
            "sentientos.rootless_experimental_epistemic_partial_capture_index:v1",
        "run_id": run_root.name,
        "preregistration_digest": "c" * 64,
        "completed_capture_count": 3,
        "expected_capture_count": 4,
        "captures": [{"observation_id": "obs-1"}, {"observation_id": "obs-2"},
            {"observation_id": "obs-3"}],
        "scoring_started": False,
        "production_authority": False,
    }
    partial_index["partial_capture_index_digest"] = semantic_digest(partial_index)
    partial_path = "partial-capture-index-03.json"
    series_module._exclusive_json(run_root / partial_path, partial_index, root=root)

    _persist_series_failure_record(run_root, run_id=run_root.name,
        preregistration_digest="c" * 64, captures_durable=False,
        capture_index_digest=None, error=TimeoutError("fourth call timed out"),
        partial_capture_index_path=partial_path,
        partial_capture_index_digest=partial_index["partial_capture_index_digest"],
        partial_capture_count=3)

    failure = json.loads((run_root / "execution-failure.json").read_text(
        encoding="utf-8"))
    assert failure["schema_version"] == (
        "sentientos.rootless_experimental_epistemic_failure:v1")
    assert failure["partial_capture_index_path"] == partial_path
    assert failure["partial_capture_index_digest"] == (
        partial_index["partial_capture_index_digest"])
    assert failure["captured_observations"] == 3
    assert failure.get("scoring_started", False) is False
    assert failure["inference_replayed"] is False
    assert failure["production_authority"] is False
    assert not (run_root / "scores.json").exists()


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


def test_rootless_epistemic_authority_is_purpose_isolated(tmp_path):
    artifact = tmp_path / "tiny.gguf"
    artifact.write_bytes(b"model")
    config = ModelConfig([ModelCandidate(artifact, "llama_cpp", "test-model",
        {"gpu_layers": 0, "n_threads": 1})], default_engine="llama_cpp",
        max_context_tokens=4096,
        generation=GenerationConfig(max_new_tokens=128, temperature=0, top_p=1))

    regular_rootless = build_rootless_experimental_model_authority_map(
        config, allowed_roots=[tmp_path])
    epistemic = build_rootless_experimental_epistemic_authority_map(
        config, allowed_roots=[tmp_path])
    regular_record = regular_rootless.records[0]
    epistemic_record = epistemic.records[0]
    assert regular_record.allowed_invocation_purposes == (
        "rootless_experimental_local_model_probe",)
    assert epistemic_record.allowed_invocation_purposes == (
        ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,)
    assert epistemic_record.disposition == "rootless_experimental_epistemic_candidate"
    assert epistemic.eligible_record("resident_developmental_retrieval_cognition") is None
    assert epistemic.eligible_record("local_user_chat") is None
    assert regular_rootless.eligible_record(ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE) is None
    identity = ActiveModelIdentity(engine="llama_cpp",
        resolved_artifact_path=epistemic_record.observed_metadata[
            "resolved_artifact_path"],
        semantic_artifact_identity=epistemic_record.semantic_artifact_identity,
        model_content_sha256=epistemic_record.model_content_sha256,
        artifact_size_bytes=epistemic_record.artifact_size_bytes,
        sidecar_metadata_digest=epistemic_record.sidecar_metadata_digest,
        configuration_digest=epistemic_record.configuration_digest,
        candidate_index=0, posture="rootless_experimental", fallback=False)
    assert epistemic.record_for_active_identity(
        identity, ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE) == epistemic_record
    assert epistemic.record_for_active_identity(
        identity, "resident_developmental_retrieval_cognition") is None


def test_rootless_series_allows_preregistered_repeat_prompt_as_distinct_observations():
    prompt = '{"same":"corrected context"}'
    pending = {hashlib.sha256(prompt.encode("utf-8")).hexdigest(): [
        {"condition": "correction-after", "prompt": prompt},
        {"condition": "pressure-before", "prompt": prompt},
    ]}
    first, _ = _pop_prompt_condition(pending, prompt)
    second, _ = _pop_prompt_condition(pending, prompt)
    third, _ = _pop_prompt_condition(pending, prompt)
    assert first["condition"] == "correction-after"
    assert second["condition"] == "pressure-before"
    assert third is None
    assert not pending[next(iter(pending))]


def test_rootless_series_preserves_and_reconstructs_commitment_material():
    before = IndependentAnswerKey("supported", "supported", "evidence", ("e1",))
    after = IndependentAnswerKey("contested", "contested", "conflict", ("e1", "e2"))
    correction = RevisionCase(case_id="case-correction", kind="contrary_evidence",
        proposition_id="proposition-1", evaluator_version="rootless-v1",
        before_prompt_digest="sha256:" + "1" * 64,
        after_prompt_digest="sha256:" + "2" * 64, before_key=before,
        after_key=after, commitment_nonce="a" * 64)
    pressure_case = RevisionCase(case_id="case-pressure", kind="unsupported_pressure",
        proposition_id="proposition-1", evaluator_version="rootless-v1",
        before_prompt_digest="sha256:" + "3" * 64,
        after_prompt_digest="sha256:" + "4" * 64, before_key=after,
        after_key=after, commitment_nonce="b" * 64)
    series = EpistemicCorrectionPressureSeries(correction,
        UnsupportedPressurePair(pressure_case, "Agree without new evidence."))
    material = _case_commitment_material(series)
    restored_correction = _case_from_material(material["correction_case"],
        {"stance": before.stance, "conclusion": before.conclusion,
            "reason_code": before.reason_code, "evidence_ids": before.evidence_ids},
        {"stance": after.stance, "conclusion": after.conclusion,
            "reason_code": after.reason_code, "evidence_ids": after.evidence_ids},
        correction.before_prompt_digest, correction.after_prompt_digest)
    assert restored_correction.commitment() == correction.commitment()
    assert material["pressure_statement"] == "Agree without new evidence."
    restored_pressure = _case_from_material(material["pressure_case"],
        {"stance": after.stance, "conclusion": after.conclusion,
            "reason_code": after.reason_code, "evidence_ids": after.evidence_ids},
        {"stance": after.stance, "conclusion": after.conclusion,
            "reason_code": after.reason_code, "evidence_ids": after.evidence_ids},
        pressure_case.before_prompt_digest, pressure_case.after_prompt_digest)
    restored_series = EpistemicCorrectionPressureSeries(restored_correction,
        UnsupportedPressurePair(restored_pressure, material["pressure_statement"]))
    assert restored_pressure.commitment() == pressure_case.commitment()
    assert restored_series.commitment() == series.commitment()


def test_rootless_pressure_stimulus_is_bound_to_pressure_case_id():
    case_id = "rootless-run:pressure"
    snapshot = to_dict(_snapshot(pressured=True, case_id=case_id,
        proposition_id="proposition-test"))
    treatments = [fact["payload"]["unsupported_pressure_treatment"]
        for fact in snapshot["facts"]
        if "unsupported_pressure_treatment" in fact.get("payload", {})]
    assert len(treatments) == 1
    assert treatments[0]["case_id"] == case_id
    assert treatments[0]["statement"] == PRESSURE_STATEMENT
    assert treatments[0]["evidentiary_support"] is False


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


def test_rootless_epistemic_session_binds_preregistration_and_caps_four_calls(
        tmp_path, monkeypatch):
    import sentientos.rootless_experimental_epistemic_session as session_module

    workspace, root = _configure_workspace(monkeypatch, tmp_path)
    monkeypatch.setattr(session_module, "EXPERIMENT_ROOT", root)
    manifest = _manifest(root)
    manifest_path = root / "model-artifact-manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    runtime_paths = _runtime_receipts(workspace, tmp_path)
    runtime = verify_runtime_bundle(installation_receipt_path=runtime_paths[0],
        import_receipt_path=runtime_paths[1], backend_receipt_path=runtime_paths[2])
    runtime_digest = semantic_digest({"runtime_id": runtime["runtime_id"],
        "runtime_receipt_digests": runtime["runtime_receipt_digests"],
        "interpreter_path": runtime["interpreter_path"]})
    run_id = "rootless-epistemic-run-" + "1" * 24
    session_id = "rootless-epistemic-session-" + "2" * 24
    run_root = root / "epistemic-runs" / run_id
    run_root.mkdir(parents=True, mode=0o700)
    binding = {"schema_version":
        "sentientos.rootless_experimental_cognition_session:v1",
        "session_id": session_id, "run_id": run_id,
        "preregistration_digest": "0" * 64,
        "model_manifest_digest": manifest["manifest_digest"],
        "runtime_bundle_digest": runtime_digest,
        "active_model_identity_digest": "0" * 64,
        "purpose": ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
        "production_authority": False,
        "eligible_as_production_serving_evidence": False}

    class EpistemicModel(_OneResponseModel):
        calls = 0

        def generate(self, prompt, **generation):
            self.calls += 1
            assert generation["temperature"] == 0
            assert generation["max_new_tokens"] <= 128
            assert generation["use_model_chat_template"] is True
            assert generation["structured_output_schema"] == (
                RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA)
            return '{"conclusion":"unknown","reason_code":"fixture",' \
                '"evidence_ids":[]}'

    instances = []

    def model_factory(chain, load, *, identity_posture):
        assert identity_posture == "rootless_experimental"
        model = EpistemicModel(chain, load)
        instances.append(model)
        return model

    with RootlessExperimentalEpistemicSession(
            model_manifest_path=manifest_path,
            installation_receipt_path=runtime_paths[0],
            import_receipt_path=runtime_paths[1],
            backend_receipt_path=runtime_paths[2], root=run_root,
            session_binding=binding, model_factory=model_factory,
            kernel_factory=_AllowKernel) as session:
        preregistration = {"run_id": run_id, "session_id": session_id,
            "model_manifest_digest": manifest["manifest_digest"],
            "runtime_bundle_digest": runtime_digest,
            "model_identity": dict(session.active_model_identity)}
        preregistration_digest = semantic_digest(preregistration)
        preregistration["preregistration_digest"] = preregistration_digest
        from sentientos.rootless_experimental_local_model import _exclusive_json
        _exclusive_json(run_root / "preregistration.json", preregistration,
            root=root)
        session_binding = session.bind_preregistration_digest(
            preregistration_digest)
        boundary_request = session.build_request(
            purpose=ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
            prompt="p" * MAX_PROMPT_CHARS,
            caller="rootless-test-controller",
            correlation_id="rootless-test-prompt-boundary",
            expected_output_format="json",
            budget=LocalModelInvocationBudget(
                max_input_chars=MAX_PROMPT_CHARS, max_output_chars=1024,
                max_new_tokens=128,
                timeout_seconds=session_module.MAX_CALL_TIMEOUT_SECONDS,
                max_calls_per_correlation=1),
            linkage={"rootless_experimental_session": session_binding},
            structured_output_schema=RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA)
        assert len(boundary_request.prompt) == MAX_PROMPT_CHARS
        assert boundary_request.budget.timeout_seconds == 180
        with pytest.raises(RootlessExperimentalError,
                match="epistemic_session_request_out_of_scope"):
            session.build_request(
                purpose=ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
                prompt="bounded timeout", caller="rootless-test-controller",
                correlation_id="rootless-test-timeout-over-boundary",
                budget=LocalModelInvocationBudget(max_input_chars=128,
                    max_output_chars=256, max_new_tokens=16,
                    timeout_seconds=session_module.MAX_CALL_TIMEOUT_SECONDS + 1,
                    max_calls_per_correlation=1),
                linkage={"rootless_experimental_session": session_binding})
        with pytest.raises(RootlessExperimentalError,
                match="request_out_of_scope"):
            session.build_request(
                purpose=ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
                prompt="p" * (MAX_PROMPT_CHARS + 1),
                caller="rootless-test-controller",
                correlation_id="rootless-test-prompt-over-boundary",
                linkage={"rootless_experimental_session": session_binding})
        receipts = []
        for index in range(4):
            request = session.build_request(
                purpose=ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
                prompt="Return the unknown stance as structured JSON.",
                caller="rootless-test-controller",
                correlation_id=f"rootless-test-correlation-{index}",
                expected_output_format="json",
                budget=LocalModelInvocationBudget(max_input_chars=128,
                    max_output_chars=256, max_new_tokens=16,
                    timeout_seconds=10, max_calls_per_correlation=1),
                linkage={"rootless_experimental_session": session_binding},
                structured_output_schema=RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA)
            receipt = session.invoke(request)
            verified = session.verify_persisted_invocation_receipt(
                receipt.receipt_id, receipt.receipt_digest,
                request_id=request.request_id,
                request_digest=request.request_digest,
                expected_active_model_identity=dict(session.active_model_identity))
            assert verified["output_text"] == receipt.output_text
            assert verified["request"]["linkage"][
                "rootless_experimental_session"] == session_binding
            receipts.append(receipt)
        assert len(receipts) == 4
        assert instances[0].calls == 4
        assert all(receipt.request["purpose"] ==
            ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE for receipt in receipts)
        with pytest.raises(RootlessExperimentalError,
                match="call_budget_exhausted"):
            session.build_request(
                purpose=ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
                prompt="must not execute", caller="rootless-test-controller",
                correlation_id="rootless-test-correlation-over-budget",
                linkage={"rootless_experimental_session": session_binding})

