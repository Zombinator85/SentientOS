from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import scripts.doctor_resident_objective_experiment as readiness
import pytest
from sentientos.resident_developmental_writeback import DevelopmentalHistoryStore, DevelopmentalRecord, _identity

pytestmark = pytest.mark.no_legacy_skip


def _config(path: Path, root: Path) -> Path:
    path.write_text(json.dumps({
        "schema": "sentientos.resident_developmental_cognition_config:v1",
        "enabled": True,
        "history_root": str(root / "history"),
        "state_root": str(root / "state"),
        "allowed_source_kinds": ["world_state"],
        "max_selected_facts": 8,
        "max_retrieved_records": 4,
        "comparison_enabled": True,
    }))
    return path


def test_readiness_is_explicitly_preflight_only_and_does_not_mutate(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    config = _config(tmp_path / "cognition.json", root)
    models = tmp_path / "models"
    models.mkdir()
    model = models / "candidate.gguf"
    model.write_bytes(b"GGUF-local-test-bytes")

    report = readiness.inspect_readiness(config, model, models)

    assert report["status"] == "preflight_blocked"
    assert report["trial_execution_ready"] is False
    assert report["authority_effect_posture"] == {
        "model_generation": False, "model_download": False,
        "serving_activation": False, "inference_admission": False,
        "authority_granted": False,
    }
    assert report["findings"]["developmental_history"]["status"] == "awaiting_eligible_history"
    assert report["findings"]["explicit_model_artifact"]["status"] in {
        "verified_local_candidate", "runtime_incompatible"
    }
    assert not (root / "state").exists()
    assert not (root / "history").exists()


def test_readiness_rejects_lfs_pointer_without_treating_it_as_payload(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    config = _config(tmp_path / "cognition.json", root)
    models = tmp_path / "models"
    models.mkdir()
    model = models / "candidate.gguf"
    model.write_bytes(b"version https://git-lfs.github.com/spec/v1\n"
        + b"oid sha256:" + b"c" * 64 + b"\nsize 123456\n")

    report = readiness.inspect_readiness(config, model, models)

    artifact = report["findings"]["explicit_model_artifact"]
    assert artifact == {"status": "invalid_custody",
        "reason_code": "git_lfs_pointer_not_model_payload"}
    assert report["trial_execution_ready"] is False


def test_readiness_cli_uses_only_explicit_paths_and_never_authorizes(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    config = _config(tmp_path / "cognition.json", root)
    models = tmp_path / "models"
    models.mkdir()
    model = models / "candidate.gguf"
    model.write_bytes(b"version https://git-lfs.github.com/spec/v1\n"
        + b"oid sha256:" + b"d" * 64 + b"\nsize 1\n")
    script = Path(__file__).resolve().parents[1] / "scripts" / "doctor_resident_objective_experiment.py"
    result = subprocess.run([sys.executable, str(script), "--config", str(config),
        "--model-path", str(model), "--allowed-root", str(models)], capture_output=True,
        text=True, check=False)

    report = json.loads(result.stdout)
    assert result.returncode == 2
    assert report["status"] == "preflight_blocked"
    assert report["authority_effect_posture"]["model_generation"] is False
    assert "resident_invoker_model_identity_not_observed" in report["unobserved_runtime_gates"]


def test_readiness_names_review_state_without_claiming_execution(tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    config = _config(tmp_path / "cognition.json", root)
    store = DevelopmentalHistoryStore(root / "history")
    record = DevelopmentalRecord("", "", {"interpretation": "fixture only"},
        "admission-fixture", "binding-fixture", "principal-fixture", "operation-fixture",
        "tick-fixture", "2026-10-13T00:00:00Z")
    record_id, record_digest = _identity("devrec", record.semantic_payload())
    store.append(DevelopmentalRecord(record_id, record_digest, record.candidate,
        record.admission_id, record.admission_binding_digest, record.principal,
        record.operation_id, record.correlation_id, record.created_at))
    monkeypatch.setattr(readiness, "inspect_artifact", lambda *args, **kwargs: {
        "artifact_size_bytes": 123, "model_content_sha256": "a" * 64,
        "semantic_artifact_identity": "sha256:" + "b" * 64,
        "configuration_digest": "sha256:" + "c" * 64,
        "llama_cpp_dependency_available": True,
    })

    report = readiness.inspect_readiness(config, tmp_path / "selected.gguf", tmp_path)

    assert report["status"] == "ready_for_operator_review"
    assert report["trial_execution_ready"] is False
    assert report["findings"]["developmental_history"]["verified_record_count"] == 1
    assert report["findings"]["explicit_model_artifact"]["identity_scope"] == \
        "operator_selected_file_not_resident_loaded_model"


def test_host_runtime_report_is_observational_and_does_not_infer_gpu_or_admission() -> None:
    report = readiness.inspect_host_runtime()

    assert report["python"]["version"]
    assert report["python"]["executable"]
    assert report["local_backend"]["engine"] == "llama_cpp"
    assert report["local_backend"]["cuda_or_gpu_offload_status"] == "not_observed"
    assert report["platform"]["wsl_gpu_status"] == "not_observed"
    assert report["experiment_custody"]["filesystem_crash_durability"] == "not_observed"
    assert report["experiment_custody"]["serving_and_inference_admission"] == "not_observed"
    if os.name == "posix":
        assert report["experiment_custody"]["status"] in {
            "required_posix_primitives_available_filesystem_unverified",
            "required_posix_primitive_missing",
        }


def test_non_posix_runtime_is_not_mistaken_for_supported_experiment_custody() -> None:
    primitives = {"open_dir_fd": True, "cross_process_flock": True}

    assert readiness._custody_status("nt", primitives) == \
        "unsupported_by_current_experiment_custody"
    assert readiness._custody_status("posix", primitives) == \
        "required_posix_primitives_available_filesystem_unverified"
    assert readiness._custody_status("posix", {**primitives, "no_follow": False}) == \
        "required_posix_primitive_missing"
