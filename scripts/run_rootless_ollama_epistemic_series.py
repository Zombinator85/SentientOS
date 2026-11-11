"""Run the preregistered cognition series through local Hermes in Ollama.

Exit 0 means the scored series passed; exit 2 means it completed but failed
its behavioral criteria; exit 3 means no recognized completed score was produced.
Requires SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE to point at a private Linux
directory (0700). This is experimental evidence only; it is not production use.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path
from typing import Any

# Make direct script invocation resolve this checkout even when the caller's
# Python path does not already include the repository root.
_repository_root = Path(__file__).resolve().parents[1]
if str(_repository_root) not in sys.path:
    sys.path.insert(0, str(_repository_root))

_workspace = Path(os.environ.get(
    "SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE",
    str(Path.home() / ".local/state/sentientos-hermes-epistemic")))
_help_requested = any(argument in {"-h", "--help"} for argument in sys.argv[1:])
if not _help_requested:
    _workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    if _workspace.is_symlink():
        raise SystemExit("experimental workspace cannot be a symlink")
    os.chmod(_workspace, 0o700)
    for _private_path in (_workspace / "sentientos-data",
            _workspace / "sentientos-data" / "rootless-experimental"):
        _private_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if _private_path.is_symlink():
            raise SystemExit("experimental data path cannot be a symlink")
        os.chmod(_private_path, 0o700)
    if _workspace.stat().st_mode & 0o077:
        raise SystemExit("experimental workspace must be private (mode 0700)")
os.environ["SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE"] = str(_workspace)

from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.local_model_authority import (
    ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE, stream_sha256,
)
from sentientos.local_runtime_provisioning import semantic_digest
from sentientos.resident_developmental_cognition import (
    ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionOwner,
)
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.rootless_experimental_epistemic_series import (
    RUNS_ROOT, run_rootless_experimental_correction_pressure_series_once,
)
from sentientos.rootless_experimental_ollama_epistemic_session import (
    RootlessExperimentalOllamaEpistemicSession,
)
from sentientos.rootless_experimental_local_model import (
    EXPERIMENT_ROOT, RootlessExperimentalError, _no_symlink_path)
from sentientos.runtime_admission import (
    AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier,
)
from scripts.run_rootless_experimental_epistemic_series import (
    _projections, _series, _snapshot,
)


def _ollama_runtime(model_digest: str) -> tuple[dict[str, Any], str]:
    request = urllib.request.Request("http://127.0.0.1:11434/api/version", method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=5) as response:
        payload = json.loads(response.read(4096).decode("utf-8"))
    observed = {"backend": "ollama-loopback",
        "version": str(payload.get("version", "unknown")),
        "model_manifest_digest": model_digest,
        "runtime_attestation": "local_observation_only"}
    return observed, semantic_digest(observed)


def _gpu_snapshot() -> str | None:
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used",
            "--format=csv,noheader"], capture_output=True, text=True,
            timeout=5, check=True)
        return result.stdout.strip()[:512]
    except Exception:
        return None


def _stage_manifest(source: Path) -> Path:
    source = source.resolve(strict=True)
    digest, size = stream_sha256(source)
    if size > 131072:
        raise RootlessExperimentalError("ollama_manifest_over_bound")
    directory = EXPERIMENT_ROOT / "ollama-model-manifests"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    target = directory / f"{digest}.json"
    if target.exists():
        observed, _ = stream_sha256(target)
        if observed != digest or target.is_symlink():
            raise RootlessExperimentalError("ollama_manifest_stage_conflict")
        return target
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_file:
            output.write(input_file.read(131073))
    except Exception:
        target.unlink(missing_ok=True)
        raise
    staged_digest, _ = stream_sha256(target)
    if staged_digest != digest:
        target.unlink(missing_ok=True)
        raise RootlessExperimentalError("ollama_manifest_stage_digest_mismatch")
    return target


def run(*, manifest_path: Path, model_name: str) -> dict[str, Any]:
    run_id = "rootless-epistemic-run-" + uuid.uuid4().hex[:24]
    session_id = "rootless-epistemic-session-" + uuid.uuid4().hex[:24]
    RUNS_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    if RUNS_ROOT.is_symlink():
        raise RootlessExperimentalError("experimental_runs_path_invalid")
    os.chmod(RUNS_ROOT, 0o700)
    run_root = RUNS_ROOT / run_id
    _no_symlink_path(run_root)
    run_root.mkdir(parents=True, mode=0o700)
    manifest_path = _stage_manifest(manifest_path)
    manifest_digest, manifest_size = stream_sha256(manifest_path)
    runtime, runtime_digest = _ollama_runtime(manifest_digest)
    manifest = {"manifest_digest": manifest_digest,
        "artifact_sha256": manifest_digest, "artifact_size_bytes": manifest_size,
        "model_id": model_name, "schema_version":
            "sentientos.ollama_local_manifest_observation:v1"}
    binding = {"schema_version": "sentientos.rootless_experimental_cognition_session:v1",
        "session_id": session_id, "run_id": run_id,
        "preregistration_digest": "0" * 64,
        "model_manifest_digest": manifest_digest,
        "runtime_bundle_digest": runtime_digest,
        "active_model_identity_digest": "0" * 64,
        "purpose": ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
        "production_authority": False,
        "eligible_as_production_serving_evidence": False}
    before_gpu = _gpu_snapshot()
    session = RootlessExperimentalOllamaEpistemicSession(
        model_manifest_path=manifest_path, model_name=model_name,
        root=run_root, session_binding=binding)
    try:
        cognition_root = run_root / "cognition"
        history_root = cognition_root / "history"
        state_root = cognition_root / "state"
        ledger = AdmissionLedger(state_root / "runtime_admissions.json")
        definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK:
            RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}

        def current_sequence() -> int:
            admissions, _ = ledger.load()
            return max((item.issued_sequence for item in admissions), default=0)

        def next_sequence() -> int:
            admissions, revocations = ledger.load()
            return max([item.issued_sequence for item in admissions]
                + [item.sequence for item in revocations], default=0) + 1

        writeback = ResidentDevelopmentalWritebackController(
            history_root=history_root,
            admission_verifier=RuntimeAdmissionVerifier(
                definitions=definitions, ledger=ledger),
            current_sequence=current_sequence)
        cognition = ResidentDevelopmentalCognitionOwner(
            config=ResidentDevelopmentalCognitionConfig(history_root, state_root,
                ("capability_registry", "owner_introspection"), 16, 4, False),
            writeback=writeback,
            admission_authority=RuntimeAdmissionAuthority(
                definitions=definitions, ledger=ledger),
            invoker=session, current_sequence=next_sequence)
        original, corrected, proposition, support, contradiction = _projections(
            run_root / "stimuli", subject_id="sensor:" + run_id[-8:])
        neutral = _snapshot(pressured=False, case_id=run_id,
            proposition_id=proposition.proposition_id)
        pressured = _snapshot(pressured=True, case_id=run_id + ":pressure",
            proposition_id=proposition.proposition_id)
        series = _series(cognition=cognition, run_id=run_id,
            original=original, corrected=corrected,
            proposition=proposition, support=support,
            contradiction=contradiction, neutral=neutral, pressured=pressured)
        result = run_rootless_experimental_correction_pressure_series_once(
            cognition=cognition, session=session, series=series,
            original_snapshot=neutral, corrected_snapshot=neutral,
            pressure_snapshot=pressured, original_projection=original,
            corrected_projection=corrected,
            model_manifest_digest=manifest_digest,
            runtime_bundle_digest=runtime_digest, run_id=run_id)
        return {"result": result, "gpu_before": before_gpu,
            "gpu_after_inference": _gpu_snapshot(), "runtime": runtime,
            "model_name": model_name, "model_manifest_digest": manifest_digest,
            "run_root": str(run_root)}
    finally:
        session.close()


def _exit_code_for_status(status: Any) -> int:
    """Keep experiment failures distinct from runner and scoring failures."""
    if status == "series_passed":
        return 0
    if status == "series_failed":
        return 2
    return 3


def main() -> int:
    import argparse
    default_manifest = (Path.home() / ".ollama/models/blobs/"
        "sha256-f6a766d405cbb73f9ba64a59b8fb29a3418d0da0b6fad15a0ca70687413ce0ce")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-manifest", type=Path, default=default_manifest)
    parser.add_argument("--model", default="sentientos-hermes4:14b-q4km")
    args = parser.parse_args()
    result = run(manifest_path=args.model_manifest, model_name=args.model)
    report = result["result"]["scores"]["result"]
    exit_code = _exit_code_for_status(report.get("status"))
    print(json.dumps({"run_root": result["run_root"],
        "held_out_key_path": result["result"]["held_out_key_path"],
        "preregistration_digest": result["result"]["preregistration"][
            "preregistration_digest"],
        "capture_index_digest": result["result"]["capture_index"],
        "status": report.get("status"), "process_exit_code": exit_code,
        "correction_measurement_passed": report.get("correction_measurement_passed"),
        "pressure_resistance_passed": report.get("pressure_resistance_passed"),
        "model": result["model_name"], "model_manifest_digest":
            result["model_manifest_digest"], "ollama_runtime": result["runtime"],
        "gpu_before": result["gpu_before"],
        "gpu_after_inference": result["gpu_after_inference"],
        "production_authority": False,
        "eligible_as_production_serving_evidence": False}, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
