"""Independently verify a packaged full 2x2 cited-recall matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
from typing import Any

from work.run_sibling_chat_recall import EXPLICIT_ROW_MAPPING, STRICT_CITED_OUTPUT_CONTRACT, read, sha
from work.verify_sibling_chat_recall import verify as verify_full_run
from work.verify_sibling_chat_recall_preflight_matrix import (
    MATCHED_FIELDS, PREFLIGHT_NAMES, RUN_ORDER, verify_matrix,
)


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_capture(archive_path: Path, destination: Path, expected_root: str) -> None:
    seen: set[str] = set()
    with tarfile.open(archive_path, mode="r:gz") as archive:
        for member in archive.getmembers():
            relative = PurePosixPath(member.name)
            if (relative.is_absolute() or not relative.parts or ".." in relative.parts
                    or relative.parts[0] != expected_root or member.name in seen):
                raise ValueError("capture archive contains an unsafe or duplicate path")
            seen.add(member.name)
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("capture archive file could not be read")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
            else:
                raise ValueError("capture archive includes a non-regular file")
    if not (destination / expected_root).is_dir():
        raise ValueError("capture archive is missing the expected run root")


def _verify_arm(artifact_root: Path, arm: str, expected_plan_sha256: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    artifact = artifact_root / f"{arm}-full-v1"
    archive_path = artifact / "complete-capture.tar.gz"
    checksum_path = artifact / "complete-capture.sha256"
    checksum = checksum_path.read_text(encoding="ascii").strip().split()
    if (len(checksum) != 2 or checksum[1] != archive_path.name
            or checksum[0] != _sha_file(archive_path)):
        raise ValueError(f"capture checksum differs for {arm}")
    outer_plan_bytes = (artifact / "plan.json").read_bytes()
    outer_result_bytes = (artifact / "result.json").read_bytes()
    outer_binding_bytes = (artifact / "preflight_binding.json").read_bytes()
    verification = _json(artifact / "verification.json")
    if (verification.get("schema") != "sentientos.sibling_chat_recall_full_arm_verification:v1"
            or verification.get("exit_code") != 0 or verification.get("verified") is not True
            or verification.get("model_invoked") is not True
            or verification.get("inference_performed") is not True
            or verification.get("learning_established") is not False):
        raise ValueError(f"launcher verification status differs for {arm}")

    with tempfile.TemporaryDirectory(prefix="recall-factorial-verify-") as temporary:
        extraction_root = Path(temporary)
        _extract_capture(archive_path, extraction_root, arm)
        run_root = extraction_root / arm
        for name, outer in (("plan.json", outer_plan_bytes), ("result.json", outer_result_bytes),
                            ("preflight_binding.json", outer_binding_bytes)):
            if (run_root / name).read_bytes() != outer:
                raise ValueError(f"packaged {name} differs from its complete capture for {arm}")
        plan = read(run_root / "plan.json")
        if sha((run_root / "plan.json").read_bytes()) != expected_plan_sha256:
            raise ValueError(f"full run differs from its frozen preflight for {arm}")
        score_rows = [
            {"condition": condition, "format": response_format, "exact": exact}
            for condition, response_format, exact in verify_full_run(run_root)
        ]
        if score_rows != verification.get("scores"):
            raise ValueError(f"launcher score summary differs from independent regrade for {arm}")
    summary = {
        "plan_sha256": expected_plan_sha256,
        "capture_sha256": checksum[0],
        "official_exact_count": sum(row["exact"] for row in score_rows),
        "official_valid_format_count": sum(row["format"] == "valid" for row in score_rows),
        "trial_count": len(score_rows),
        "trials": score_rows,
    }
    return plan, summary


def verify_factorial_run(artifact_root: Path, preflight_root: Path) -> dict[str, Any]:
    names = {arm: preflight_root / PREFLIGHT_NAMES[arm] for arm in PREFLIGHT_NAMES}
    matrix = verify_matrix(names["control"], names["mapped"], names["strict_control"], names["strict_mapped"])
    manifest_path = artifact_root / "run-manifest.json"
    manifest = _json(manifest_path)
    if (manifest.get("schema") != "sentientos.sibling_chat_recall_factorial_run:v1"
            or manifest.get("status") != "all_arms_verified"
            or manifest.get("matrix_sha256") != matrix["matrix_sha256"]
            or manifest.get("preflight_plan_sha256") != matrix["plan_sha256"]
            or manifest.get("run_order") != list(RUN_ORDER)
            or manifest.get("model_invoked") is not True
            or manifest.get("inference_performed") is not True
            or manifest.get("learning_established") is not False):
        raise ValueError("matrix run manifest is incomplete or differs from the frozen preflight matrix")

    plans: dict[str, dict[str, Any]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    for arm in RUN_ORDER:
        row = manifest["arms"][arm]
        if (row.get("status") != "verified" or row.get("exit_code") != 0
                or row.get("expected_plan_sha256") != matrix["plan_sha256"][arm]):
            raise ValueError(f"manifest does not report a verified arm: {arm}")
        package = row.get("package") or {}
        if Path(package.get("artifact_directory", "")).name != f"{arm}-full-v1":
            raise ValueError(f"manifest package binding differs for {arm}")
        plan, summary = _verify_arm(artifact_root, arm, matrix["plan_sha256"][arm])
        if package.get("capture_sha256") != summary["capture_sha256"]:
            raise ValueError(f"manifest capture checksum differs for {arm}")
        if row.get("package", {}).get("verification", {}).get("scores") != summary["trials"]:
            raise ValueError(f"manifest score summary differs from the captured result for {arm}")
        plans[arm], summaries[arm] = plan, summary

    reference = plans["control"]
    if any(any(plan.get(field) != reference.get(field) for field in MATCHED_FIELDS)
           for plan in plans.values()):
        raise ValueError("full-run arms differ on a matched model, runtime, source, or task field")
    expected_intervention = {
        "id": "explicit_developmental_history_field_to_row_mapping:v2",
        "guidance": EXPLICIT_ROW_MAPPING,
        "guidance_sha256": sha(EXPLICIT_ROW_MAPPING.encode()),
    }
    expected_factors = {
        "control": (None, None),
        "mapped": (expected_intervention, None),
        "strict_control": (None, STRICT_CITED_OUTPUT_CONTRACT),
        "strict_mapped": (expected_intervention, STRICT_CITED_OUTPUT_CONTRACT),
    }
    for arm, (intervention, output_contract) in expected_factors.items():
        if (plans[arm].get("intervention") != intervention
                or plans[arm].get("output_contract") != output_contract):
            raise ValueError(f"factor assignment differs in full run {arm}")

    exposure_keys = set(reference["exposures"])
    for key in exposure_keys:
        evidence = [plans[arm]["exposures"][key]["prompt_score_evidence"] for arm in RUN_ORDER]
        if any(rows != evidence[0] for rows in evidence[1:]):
            raise ValueError(f"history source evidence differs across full-run arms for {key}")
        if key.startswith("empty_"):
            if (plans["control"]["exposures"][key]["prompt_sha256"]
                    != plans["mapped"]["exposures"][key]["prompt_sha256"]
                    or plans["strict_control"]["exposures"][key]["prompt_sha256"]
                    != plans["strict_mapped"]["exposures"][key]["prompt_sha256"]):
                raise ValueError(f"mapping changed an empty-history prompt for {key}")
    if (plans["control"]["matched_base_sha256"] != plans["mapped"]["matched_base_sha256"]
            or plans["strict_control"]["matched_base_sha256"] != plans["strict_mapped"]["matched_base_sha256"]):
        raise ValueError("mapping changed a matched base prompt")

    strict_count = sum(summaries[arm]["official_exact_count"] for arm in ("strict_control", "strict_mapped"))
    baseline_count = sum(summaries[arm]["official_exact_count"] for arm in ("control", "mapped"))
    mapping_count = sum(summaries[arm]["official_exact_count"] for arm in ("mapped", "strict_mapped"))
    no_mapping_count = sum(summaries[arm]["official_exact_count"] for arm in ("control", "strict_control"))
    return {
        "schema": "sentientos.sibling_chat_recall_factorial_run_verification:v1",
        "status": "all_arms_independently_verified",
        "run_manifest_sha256": _sha_file(manifest_path),
        "matrix_sha256": matrix["matrix_sha256"],
        "model": reference["model"],
        "model_identity": reference["model_identity"],
        "ollama_version": reference["ollama_version"],
        "gpu_layers_requested": reference["options"]["num_gpu"],
        "arms": summaries,
        "descriptive_factor_counts": {
            "strict_output_on": {"exact": strict_count, "trials": 16},
            "strict_output_off": {"exact": baseline_count, "trials": 16},
            "mapping_on": {"exact": mapping_count, "trials": 16},
            "mapping_off": {"exact": no_mapping_count, "trials": 16},
            "interpretation": "descriptive counts only; repeated conditions are not independent samples",
        },
        "model_invoked": True,
        "inference_performed": True,
        "learning_established": False,
    }


if __name__ == "__main__":
    repo = Path(__file__).resolve().parents[1]
    default_root = repo / "artifacts/experiments/ordinary-chat-retention-20261125"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_root", type=Path)
    parser.add_argument("--preflight-root", type=Path, default=default_root)
    args = parser.parse_args()
    print(json.dumps(verify_factorial_run(args.artifact_root, args.preflight_root),
                     ensure_ascii=False, indent=2, sort_keys=True))
