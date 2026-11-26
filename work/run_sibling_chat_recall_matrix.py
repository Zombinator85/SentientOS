"""Execute and package a preverified 2x2 cited-recall matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from typing import Any
from urllib.parse import urlsplit

from work.run_sibling_chat_recall import MODEL_MANIFESTS
from work.verify_sibling_chat_recall import verify as verify_full_run
from work.verify_sibling_chat_recall_preflight_matrix import RUN_ORDER, verify_matrix


MODEL = "sentientos-hermes4:14b-q4km"
ARM_FLAGS = {
    "control": (),
    "strict_mapped": ("--explicit-row-mapping", "--strict-cited-output"),
    "mapped": ("--explicit-row-mapping",),
    "strict_control": ("--strict-cited-output",),
}
PREFLIGHT_NAMES = {
    "control": "cuda-hermes-recall-control-baseline-preflight-v1",
    "mapped": "cuda-hermes-recall-mapping-baseline-preflight-v1",
    "strict_control": "cuda-hermes-recall-control-strict-preflight-v1",
    "strict_mapped": "cuda-hermes-recall-mapping-strict-preflight-v1",
}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_run(run_root: Path, destination: Path, *, exit_code: int,
                 scores: list[dict[str, Any]] | None) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("plan.json", "result.json", "preflight_binding.json", "preflight_rejection.json"):
        source = run_root / name
        if source.is_file():
            shutil.copy2(source, destination / name)
    receipt_directory = run_root / "inference-custody" / "receipts"
    model_invoked = receipt_directory.is_dir() and any(receipt_directory.glob("*.json"))
    verification = {
        "schema": "sentientos.sibling_chat_recall_full_arm_verification:v1",
        "exit_code": exit_code,
        "verified": scores is not None,
        "scores": scores,
        "model_invoked": model_invoked,
        "inference_performed": model_invoked,
        "learning_established": False,
    }
    _write_json(destination / "verification.json", verification)
    archive_path = destination / "complete-capture.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        archive.add(run_root, arcname=run_root.name, recursive=True)
    (destination / "complete-capture.sha256").write_text(
        f"{_sha_file(archive_path)}  complete-capture.tar.gz\n", encoding="ascii")
    return {
        "artifact_directory": str(destination),
        "run_directory": str(run_root),
        "verification": verification,
        "capture_sha256": _sha_file(archive_path),
    }


def execute_matrix(cycles: Path, ollama_install: Path, models: Path, output_root: Path,
                   preflight_root: Path, artifact_root: Path) -> dict[str, Any]:
    if MODEL not in MODEL_MANIFESTS:
        raise ValueError("pinned matrix model is missing from the runner registry")
    if not (os.environ.get("SENTIENTOS_OLLAMA_MODELS")
            or os.environ.get("SENTIENTOS_OLLAMA_CPU_MODELS")):
        raise ValueError("GPU matrix requires the explicitly isolated external Ollama model store")
    target = urlsplit(os.environ.get("SENTIENTOS_OLLAMA_CPU_TARGET", ""))
    if target.scheme != "http" or not target.hostname or not target.port:
        raise ValueError("GPU matrix requires an explicit isolated Ollama HTTP target")
    preflight_paths = {name: preflight_root / PREFLIGHT_NAMES[name] for name in PREFLIGHT_NAMES}
    matrix = verify_matrix(preflight_paths["control"], preflight_paths["mapped"],
                           preflight_paths["strict_control"], preflight_paths["strict_mapped"])
    if matrix["model"] != MODEL or matrix["gpu_layers_for_later_inference"] != 24:
        raise ValueError("preflight matrix does not bind the pinned 24-layer Hermes run")
    if output_root.resolve() == artifact_root.resolve():
        raise ValueError("transient run data and packaged artifacts need separate directories")
    if artifact_root.exists():
        raise FileExistsError(f"matrix artifact directory already exists: {artifact_root}")
    for arm_index, arm in enumerate(RUN_ORDER):
        if (output_root / arm).exists():
            raise FileExistsError(f"matrix arm output already exists: {output_root / arm}")

    artifact_root.mkdir(parents=True)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "schema": "sentientos.sibling_chat_recall_factorial_run:v1",
        "matrix_sha256": matrix["matrix_sha256"],
        "preflight_plan_sha256": matrix["plan_sha256"],
        "run_order": list(RUN_ORDER),
        "pinned_model_reuse_policy": (
            "first arm requires an empty server; later arms allow only one resident model "
            "with the pinned digest"),
        "model_invoked": False,
        "inference_performed": False,
        "learning_established": False,
        "arms": {arm: {"status": "pending"} for arm in RUN_ORDER},
    }
    manifest_path = artifact_root / "run-manifest.json"
    _write_json(manifest_path, manifest)
    repository = Path(__file__).resolve().parents[1]

    for arm in RUN_ORDER:
        run_root = output_root / arm
        command = [
            sys.executable, "-m", "work.run_sibling_chat_recall",
            str(cycles), str(ollama_install), str(models), str(run_root),
            "--model", MODEL, "--cited", "--gpu-layers", "24",
            "--expected-plan-sha256", matrix["plan_sha256"][arm],
            *ARM_FLAGS[arm],
        ]
        manifest["active_arm"] = arm
        manifest["arms"][arm] = {
            "status": "running",
            "expected_plan_sha256": matrix["plan_sha256"][arm],
        }
        _write_json(manifest_path, manifest)
        child_environment = os.environ.copy()
        if arm_index:
            child_environment["SENTIENTOS_OLLAMA_RECALL_MATRIX_REUSE_PINNED"] = "1"
        completed = subprocess.run(command, cwd=repository, env=child_environment, check=False)
        scores = None
        verification_error = None
        if completed.returncode == 0:
            try:
                scores = [
                    {"condition": condition, "format": response_format, "exact": exact}
                    for condition, response_format, exact in verify_full_run(run_root)
                ]
            except Exception as error:
                verification_error = f"{type(error).__name__}: {error}"
        package = None
        if run_root.exists():
            package = _package_run(run_root, artifact_root / f"{arm}-full-v1",
                                   exit_code=completed.returncode, scores=scores)
        manifest["arms"][arm] = {
            "status": "verified" if scores is not None else "failed_or_unverified",
            "exit_code": completed.returncode,
            "expected_plan_sha256": matrix["plan_sha256"][arm],
            "verification_error": verification_error,
            "package": package,
        }
        model_invoked = bool(package and package["verification"]["model_invoked"])
        manifest["model_invoked"] = manifest["model_invoked"] or model_invoked
        manifest["inference_performed"] = manifest["inference_performed"] or model_invoked
        _write_json(manifest_path, manifest)
        if completed.returncode != 0 or scores is None:
            manifest["status"] = "stopped_after_arm_failure"
            _write_json(manifest_path, manifest)
            return manifest

    manifest.pop("active_arm", None)
    manifest["status"] = "all_arms_verified"
    _write_json(manifest_path, manifest)
    return manifest


if __name__ == "__main__":
    repo = Path(__file__).resolve().parents[1]
    default_preflight = repo / "artifacts/experiments/ordinary-chat-retention-20261125"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cycles", type=Path)
    parser.add_argument("ollama_install", type=Path)
    parser.add_argument("models", type=Path)
    parser.add_argument("output_root", type=Path, help="Use a WSL filesystem path for transient model state")
    parser.add_argument("--preflight-root", type=Path, default=default_preflight)
    parser.add_argument("--artifact-root", type=Path,
                        default=default_preflight / "cuda-hermes-recall-factorial-full-v1")
    args = parser.parse_args()
    result = execute_matrix(args.cycles, args.ollama_install, args.models, args.output_root,
                            args.preflight_root, args.artifact_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result.get("status") != "all_arms_verified":
        raise SystemExit(1)
