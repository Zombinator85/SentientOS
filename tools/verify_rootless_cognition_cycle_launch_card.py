"""Verify a private launch card for a frozen rootless cognition campaign."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _read_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("launch_card_source_file_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("launch_card_source_json_invalid")
    return value


def _sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("launch_card_source_file_invalid")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_under(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=True)
    resolved.relative_to(root.resolve(strict=True))
    return resolved


def _verify_initial_history_source_chain(*, card: Mapping[str, Any],
        plan: Mapping[str, Any], workspace: Path) -> dict[str, Any]:
    protocol = plan.get("cross_range_history_enabled_competence")
    boundary = plan.get("initial_history_boundary")
    nonempty_history = (isinstance(boundary, Mapping)
        and type(boundary.get("file_count")) is int
        and boundary.get("file_count", 0) > 0)
    required = isinstance(protocol, Mapping) or nonempty_history
    binding = card.get("initial_history_source_chain")
    if not required and not isinstance(binding, Mapping):
        return {"required": False, "verified": True, "reason": None}
    if not isinstance(binding, Mapping):
        return {"required": True, "verified": False,
            "reason": "initial_history_source_chain_binding_missing"}
    from work.rootless_history_boundary_campaign import (
        _history_boundary, _load_plan, verify_chain)
    try:
        source_plan_path = _safe_under(Path(binding.get("source_plan_path", "")),
            workspace)
        audit_path = _safe_under(Path(binding.get("audit_path", "")), workspace)
        source_plan = _load_plan(source_plan_path)
        cycle_ids = source_plan.get("ordered_cycle_ids")
        expected_family = (protocol.get("source_task_family_id")
            if isinstance(protocol, Mapping) else plan.get("task_family_id"))
        if (not isinstance(cycle_ids, list) or not cycle_ids
                or source_plan.get("plan_digest") != binding.get("source_plan_digest")
                or source_plan.get("task_family_id") != expected_family):
            return {"required": True, "verified": False,
                "reason": "initial_history_source_plan_binding_invalid"}
        roots_raw = binding.get("cycle_root_paths")
        allow_prefix = binding.get("allow_prefix") is True
        if (not isinstance(roots_raw, list) or not roots_raw
                or len(roots_raw) > len(cycle_ids)
                or len(roots_raw) < len(cycle_ids) and not allow_prefix):
            return {"required": True, "verified": False,
                "reason": "initial_history_source_cycle_roots_invalid"}
        source_cycle_ids = cycle_ids[:len(roots_raw)]
        if binding.get("source_cycle_ids", source_cycle_ids) != source_cycle_ids:
            return {"required": True, "verified": False,
                "reason": "initial_history_source_cycle_order_invalid"}
        cycle_roots = [_safe_under(Path(value), workspace) for value in roots_raw]
        expected_roots = [(workspace / "sentientos-data" / "rootless-experimental"
            / "developmental-cognition-cycles" / cycle_id).resolve(strict=True)
            for cycle_id in source_cycle_ids]
        if cycle_roots != expected_roots:
            return {"required": True, "verified": False,
                "reason": "initial_history_source_cycle_order_invalid"}
        audit = _read_object(audit_path)
        audit_sha256 = _sha256(audit_path)
        if audit_sha256 != binding.get("audit_file_sha256"):
            return {"required": True, "verified": False,
                "reason": "initial_history_source_audit_digest_mismatch"}
        chain = verify_chain(plan_path=source_plan_path, cycle_roots=cycle_roots,
            allow_prefix=allow_prefix)
        rows = chain.get("cycle_boundaries", [])
        target_boundary = boundary.get("boundary_digest") if isinstance(
            boundary, Mapping) else None
        source_boundary = rows[-1].get("history_boundary_digest") if rows else None
        audit_matches = audit.get("audit_digest") == chain.get("audit_digest")
        rows_completed = (len(rows) == len(cycle_roots)
            and all(row.get("terminal_status") == "completed" for row in rows))
        verified = (
            audit_matches
            and rows_completed
            and chain.get("append_only_history_chain_verified") is True
            and chain.get("seed_boundary_chain_verified") is True
            and chain.get("runtime_admission_chain_verified") is True
            and chain.get("cognition_recovery_state_chain_verified") is True
            and source_boundary == target_boundary)
        return {"required": True, "verified": verified,
            "source_plan_digest": source_plan["plan_digest"],
            "source_cycle_ids": source_cycle_ids,
            "source_history_boundary_digest": source_boundary,
            "target_history_boundary_digest": target_boundary,
            "source_audit_digest": chain.get("audit_digest"),
            "source_audit_file_sha256": audit_sha256,
            "audit_matches_recomputed_chain": audit_matches,
            "append_only_history_chain_verified": chain.get(
                "append_only_history_chain_verified"),
            "seed_boundary_chain_verified": chain.get(
                "seed_boundary_chain_verified"),
            "runtime_admission_chain_verified": chain.get(
                "runtime_admission_chain_verified"),
            "cognition_recovery_state_chain_verified": chain.get(
                "cognition_recovery_state_chain_verified"),
            "reason": None if verified else "initial_history_source_chain_not_verified"}
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return {"required": True, "verified": False,
            "reason": "initial_history_source_chain_recomputation_failed"}


def _gpu_sample() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader"],
            check=False, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "utilization_percent": None,
            "memory_used_mib": None, "memory_total_mib": None}
    if result.returncode != 0:
        return {"available": False, "utilization_percent": None,
            "memory_used_mib": None, "memory_total_mib": None}
    first = result.stdout.splitlines()[0] if result.stdout.splitlines() else ""
    parts = [part.strip() for part in first.split(",")]
    if len(parts) != 3:
        return {"available": False, "utilization_percent": None,
            "memory_used_mib": None, "memory_total_mib": None}
    try:
        return {
            "available": True,
            "utilization_percent": float(parts[0].removesuffix("%").strip()),
            "memory_used_mib": int(parts[1].removesuffix("MiB").strip()),
            "memory_total_mib": int(parts[2].removesuffix("MiB").strip()),
        }
    except ValueError:
        return {"available": False, "utilization_percent": None,
            "memory_used_mib": None, "memory_total_mib": None}


def _git_text(*args: str) -> str:
    result = subprocess.run(["git", "-C", str(REPO_ROOT), *args],
        check=True, capture_output=True, text=True, timeout=10)
    return result.stdout.strip()


def verify_launch_card(*, card_path: Path,
        receipt_path: Path | None = None) -> dict[str, Any]:
    card_path = card_path.resolve(strict=True)
    card = _read_object(card_path)
    if card.get("schema_version") != "sentientos.rootless_cognition_cycle_launch_card:v1":
        raise ValueError("launch_card_schema_invalid")
    if card.get("status") != "prepared_not_started":
        raise ValueError("launch_card_not_prepared")
    if card.get("authority") is not False or card.get("learning_established") is not False:
        raise ValueError("launch_card_claim_scope_invalid")
    if card.get("preregistration_timing_independently_attested") is not False:
        raise ValueError("launch_card_preregistration_posture_invalid")

    workspace = Path(card.get("workspace", "")).resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("launch_card_workspace_invalid")
    card_mode = stat.S_IMODE(card_path.stat().st_mode)
    if card_mode != 0o600:
        raise ValueError("launch_card_private_mode_invalid")

    cycles = card.get("cycles")
    if not isinstance(cycles, list) or len(cycles) != 2:
        raise ValueError("launch_card_cycle_list_invalid")
    env_name = "SENTIENTOS_HERMES_GPU_AVAILABLE_FOR_CYCLE"
    plan_path_raw = cycles[0].get("environment", {}).get(
        "SENTIENTOS_HERMES_CAMPAIGN_PLAN_PATH")
    if not isinstance(plan_path_raw, str):
        raise ValueError("launch_card_plan_path_missing")
    plan_path = _safe_under(Path(plan_path_raw), workspace)
    plan = _read_object(plan_path)
    source_history_chain = _verify_initial_history_source_chain(
        card=card, plan=plan, workspace=workspace)
    from work.rootless_history_boundary_campaign import (
        _RANGE_TASK_FAMILIES, _history_boundary, verify_chain,
        verify_experiment_implementation, verify_model_identity_recipe)
    identity = verify_model_identity_recipe(plan)
    implementation = verify_experiment_implementation(plan)
    if plan.get("campaign_id") != card.get("campaign_id"):
        raise ValueError("launch_card_campaign_mismatch")
    if plan.get("plan_digest") != card.get("plan_digest"):
        raise ValueError("launch_card_plan_digest_mismatch")
    if _sha256(plan_path) != card.get("plan_file_sha256"):
        raise ValueError("launch_card_plan_file_digest_mismatch")
    if implementation.get("experiment_implementation_digest") != card.get(
            "implementation_digest"):
        raise ValueError("launch_card_implementation_digest_mismatch")
    if implementation.get("experiment_implementation_source_count") != card.get(
            "implementation_source_count"):
        raise ValueError("launch_card_implementation_source_count_mismatch")
    if (identity.get("identity_digests_verified") is not True
            or identity.get("identity_count") != len(
                plan.get("ordered_model_identity_digests", []))):
        raise ValueError("launch_card_identity_recipe_mismatch")
    card_source = card.get("source_commit_at_card_creation")
    if not isinstance(card_source, str) or not re.fullmatch(r"[0-9a-f]{40}", card_source):
        raise ValueError("launch_card_source_commit_invalid")
    _git_text("merge-base", "--is-ancestor", card_source, "HEAD")

    recipe = plan.get("model_identity_recipe")
    model = card.get("model")
    if not isinstance(recipe, Mapping) or not isinstance(model, Mapping):
        raise ValueError("launch_card_model_binding_invalid")
    for card_key, plan_key in (("engine", "engine"), ("name", "model_name"),
            ("manifest_path", "resolved_manifest_path"),
            ("manifest_sha256", "manifest_sha256"), ("gpu_layers", "gpu_layers")):
        if model.get(card_key) != recipe.get(plan_key):
            raise ValueError("launch_card_model_recipe_mismatch")
    if model.get("identity_digests") != plan.get("ordered_model_identity_digests"):
        raise ValueError("launch_card_model_identity_mismatch")

    bundle_path = plan_path.with_name("initial-history-bundle.json")
    bundle = _read_object(bundle_path)
    if _sha256(bundle_path) != card.get("private_history_bundle_file_sha256"):
        raise ValueError("launch_card_history_bundle_file_digest_mismatch")
    boundary = plan.get("initial_history_boundary", {})
    if (bundle.get("campaign_id") != plan.get("campaign_id")
            or bundle.get("plan_digest") != plan.get("plan_digest")
            or bundle.get("source_history_boundary_digest") != boundary.get("boundary_digest")
            or bundle.get("source_history_file_count") != boundary.get("file_count")
            or bundle.get("source_history_total_size_bytes") != boundary.get("total_size_bytes")
            or bundle.get("task_family_id") != plan.get("task_family_id")
            or card.get("history_boundary_digest") != boundary.get("boundary_digest")):
        raise ValueError("launch_card_history_bundle_binding_mismatch")

    plan_ids = plan.get("ordered_cycle_ids")
    task_seeds = plan.get("ordered_task_generation_seeds")
    backend_seeds = plan.get("ordered_backend_seeds")
    identities = plan.get("ordered_model_identity_digests")
    if not all(isinstance(v, list) and len(v) == 2
            for v in (plan_ids, task_seeds, backend_seeds, identities)):
        raise ValueError("launch_card_plan_cycle_inventory_invalid")
    if len(cycles) != len(plan_ids):
        raise ValueError("launch_card_cycle_count_mismatch")

    root = workspace / "sentientos-data" / "rootless-experimental" / "developmental-cognition-cycles"
    cycle_results: list[dict[str, Any]] = []
    for index, cycle in enumerate(cycles):
        if not isinstance(cycle, Mapping):
            raise ValueError("launch_card_cycle_invalid")
        cid = plan_ids[index]
        if (cycle.get("cycle_index") != index or cycle.get("cycle_id") != cid
                or cycle.get("task_generation_seed") != task_seeds[index]
                or cycle.get("backend_seed") != backend_seeds[index]
                or cycle.get("model_identity_digest") != identities[index]):
            raise ValueError("launch_card_cycle_binding_mismatch")
        environment = cycle.get("environment")
        if not isinstance(environment, Mapping):
            raise ValueError("launch_card_cycle_environment_invalid")
        expected_env = {
            "SENTIENTOS_HERMES_CYCLE_ID": cid,
            "SENTIENTOS_HERMES_CAMPAIGN_PLAN_PATH": str(plan_path),
            "SENTIENTOS_HERMES_PREREGISTRATION_DIGEST": plan["plan_digest"],
            "SENTIENTOS_HERMES_EXPERIMENT_SEED": str(task_seeds[index]),
            "SENTIENTOS_HERMES_BACKEND_SEED": str(backend_seeds[index]),
            "SENTIENTOS_HERMES_MODEL": recipe["model_name"],
            "SENTIENTOS_HERMES_MODEL_MANIFEST_PATH": recipe["resolved_manifest_path"],
            "SENTIENTOS_HERMES_GPU_LAYERS": str(recipe["gpu_layers"]),
            "SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE": str(workspace),
        }
        if any(environment.get(key) != value for key, value in expected_env.items()):
            raise ValueError("launch_card_cycle_environment_mismatch")
        if environment.get(env_name) is not None:
            raise ValueError("launch_card_gpu_confirmation_must_remain_unset")
        prior_root = Path(cycle.get("prior_history_root", ""))
        if not prior_root.is_absolute() or not prior_root.name == "history":
            raise ValueError("launch_card_prior_history_path_invalid")
        if index == 0:
            prior_root = _safe_under(prior_root, workspace)
            if _history_boundary(prior_root) != plan.get("initial_history_boundary"):
                raise ValueError("launch_card_initial_history_boundary_mismatch")
        else:
            expected_prior = (workspace / "sentientos-data" / "rootless-experimental"
                / "developmental-cognition-cycles" / plan_ids[index - 1]
                / "resident-cognition" / "history").absolute()
            if prior_root.absolute() != expected_prior:
                raise ValueError("launch_card_prior_history_cycle_mismatch")
            if prior_root.exists() or prior_root.is_symlink():
                if _safe_under(prior_root, workspace) != expected_prior:
                    raise ValueError("launch_card_prior_history_cycle_mismatch")
        cycle_root = root / cid
        if cycle_root.exists() or cycle_root.is_symlink():
            cycle_results.append({"cycle_id": cid, "cycle_root_absent": False})
        else:
            cycle_results.append({"cycle_id": cid, "cycle_root_absent": True})

    preflight_results: list[dict[str, Any]] = []
    preflight_artifacts: dict[str, dict[str, str] | None] = {}
    for index, cycle in enumerate(cycles):
        cid = plan_ids[index]
        binding = cycle.get("preflight_evidence")
        if binding is None and index > 0:
            preflight_results.append({"cycle_id": cid, "verified": False,
                "reason": "sequential_preflight_not_yet_bound"})
            preflight_artifacts[cid] = None
            continue
        if not isinstance(binding, Mapping):
            raise ValueError("launch_card_required_preflight_missing")
        preflight_path = _safe_under(Path(binding["path"]), workspace)
        verify_path = _safe_under(Path(binding["verification_path"]), workspace)
        preflight = _read_object(preflight_path)
        verification = _read_object(verify_path)
        if (_sha256(preflight_path) != binding.get("sha256")
                or _sha256(verify_path) != binding.get("verification_sha256")
                or preflight.get("campaign_id") != plan.get("campaign_id")
                or preflight.get("plan_digest") != plan.get("plan_digest")
                or preflight.get("cycle_id") != cid
                or preflight.get("inference_performed") is not False
                or preflight.get("learning_established") is not False
                or verification.get("status") != "verified"
                or verification.get("implementation_matches_current") is not True
                or verification.get("inference_performed") is not False
                or verification.get("plan_digest") != plan.get("plan_digest")):
            raise ValueError("launch_card_preflight_evidence_mismatch")
        preflight_results.append({"cycle_id": cid, "verified": True,
            "reason": None})
        preflight_artifacts[cid] = {
            "report_sha256": _sha256(preflight_path),
            "verification_sha256": _sha256(verify_path),
            "status": verification["status"],
        }

    prior_chain_results: list[dict[str, Any]] = []
    for index, cid in enumerate(plan_ids):
        if index == 0:
            chain_verified = (bundle.get("source_history_boundary_digest")
                == plan.get("initial_history_boundary", {}).get("boundary_digest"))
            prior_chain_results.append({"cycle_id": cid,
                "verified": chain_verified,
                "reason": None if chain_verified else "initial_history_boundary_unverified"})
            continue
        predecessor_roots = [root / prior_id for prior_id in plan_ids[:index]]
        if not all(path.is_dir() and not path.is_symlink() for path in predecessor_roots):
            prior_chain_results.append({"cycle_id": cid, "verified": False,
                "reason": "predecessor_cycle_incomplete_or_absent"})
            continue
        try:
            chain_options = {}
            if plan.get("task_family_id") in _RANGE_TASK_FAMILIES:
                chain_options["initial_history_bundle_path"] = bundle_path
            prefix = verify_chain(plan_path=plan_path,
                cycle_roots=predecessor_roots, allow_prefix=True,
                **chain_options)
            rows = prefix.get("cycle_boundaries", [])
            chain_verified = (
                prefix.get("append_only_history_chain_verified") is True
                and prefix.get("runtime_admission_chain_verified") is True
                and prefix.get("cognition_recovery_state_chain_verified") is True
                and len(rows) == index
                and all(row.get("campaign_binding_verified") is True
                    and row.get("history_seed_boundary_verified") is True
                    and row.get("runtime_admission_ledger_append_only") is True
                    and row.get("cognition_recovery_state_append_only") is True
                    for row in rows)
                and rows[-1].get("cycle_id") == plan_ids[index - 1])
            prior_chain_results.append({"cycle_id": cid,
                "verified": chain_verified,
                "reason": None if chain_verified else "predecessor_chain_verification_failed",
                "audit_digest": prefix.get("audit_digest")})
        except (OSError, ValueError, KeyError, IndexError):
            prior_chain_results.append({"cycle_id": cid, "verified": False,
                "reason": "predecessor_chain_verification_failed"})

    receipt_bound = False
    if receipt_path is not None:
        receipt = receipt_path.read_text(encoding="utf-8")
        receipt_bound = _sha256(card_path) in receipt
        if not receipt_bound:
            raise ValueError("launch_card_receipt_digest_missing")

    gpu = _gpu_sample()
    max_util = card.get("gpu_gate", {}).get(
        "maximum_preinference_utilization_percent")
    if type(max_util) not in (int, float):
        raise ValueError("launch_card_gpu_threshold_invalid")
    confirmation = os.environ.get(env_name)
    confirmations = {cycle.get("cycle_id"): confirmation == cycle.get("cycle_id")
        for cycle in cycles}
    launch_gates = {
        cycle["cycle_id"]: {
            "cycle_root_absent": cycle_results[i]["cycle_root_absent"],
            "cycle_preflight_verified": preflight_results[i]["verified"],
            "prior_history_chain_verified": prior_chain_results[i]["verified"],
            "initial_history_source_chain_verified": source_history_chain["verified"],
            "gpu_telemetry_available": gpu["available"],
            "gpu_utilization_within_limit": (
                gpu["available"] and gpu["utilization_percent"] <= max_util),
            "operator_confirmation_matches_cycle": confirmations[cycle["cycle_id"]],
            "card_gpu_confirmation_unset": (
                cycle["environment"].get(env_name) is None),
        }
        for i, cycle in enumerate(cycles)
    }
    return {
        "schema_version": "sentientos.rootless_cognition_cycle_launch_card_verification:v3",
        "status": "verified",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "campaign_id": plan["campaign_id"],
        "plan_digest": plan["plan_digest"],
        "card_file_sha256": _sha256(card_path),
        "card_mode_octal": oct(card_mode),
        "source_commit_at_card_creation": card.get("source_commit_at_card_creation"),
        "source_current_implementation_matches_plan": True,
        "source_implementation_digest": implementation[
            "experiment_implementation_digest"],
        "source_implementation_file_count": implementation[
            "experiment_implementation_source_count"],
        "model_identity_recipe_verified": True,
        "history_bundle_file_sha256": _sha256(bundle_path),
        "history_bundle_boundary_matches_plan": True,
        "cycle_state": cycle_results,
        "cycle_preflight": preflight_results,
        "prior_history_chain": prior_chain_results,
        "initial_history_source_chain": source_history_chain,
        "cycle_preflight_artifacts": preflight_artifacts,
        "custody_receipt_digest_bound": receipt_bound if receipt_path else None,
        "gpu_telemetry": gpu,
        "launch_gates": launch_gates,
        "launch_eligible": {
            cycle_id: all(gates.values())
            for cycle_id, gates in launch_gates.items()},
        "operator_confirmations_in_card": {
            cycle["cycle_id"]: cycle["environment"].get(env_name) for cycle in cycles},
        "inference_performed": False,
        "model_loaded_by_verifier": False,
        "learning_established": False,
        "authority": False,
    }


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError("launch_card_verification_output_exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(report, sort_keys=True, indent=2) + "\n")
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card", required=True, type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--output", type=Path,
        help="optional write-once report path; output mode is 0600")
    args = parser.parse_args()
    card = _read_object(args.card)
    workspace = card.get("workspace")
    if not isinstance(workspace, str):
        raise SystemExit("launch_card_workspace_missing")
    os.environ["SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE"] = workspace
    report = verify_launch_card(card_path=args.card,
        receipt_path=args.receipt)
    if args.output is not None:
        _write_report(args.output, report)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
