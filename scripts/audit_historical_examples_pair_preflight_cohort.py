#!/usr/bin/env python3
"""Audit a CPU-prepared cohort of historical-examples intervention pairs."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore, MAX_EXPERIMENT_ARTIFACT_BYTES,
)
from scripts.preflight_resident_historical_examples_pair import (
    _read_private_task_commitment_key,
    verify_preflight_report,
)
from sentientos.developmental_model_replacement_experiment import (
    derive_rootless_task_commitment_nonces,
)
from work.historical_examples_intervention import (
    HistoricalExamplesInterventionError,
    HistoricalExamplesPairJournal,
    _digest,
    validate_historical_examples_protocol,
)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("historical_examples_cohort_duplicate_json_key")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise ValueError("historical_examples_cohort_nonstandard_json_constant:" + value)


def _contains_symlink(path: Path) -> bool:
    current = path.absolute()
    while True:
        if current.is_symlink():
            return True
        if current.parent == current:
            return False
        current = current.parent


def _read_object(path: Path, *, error_code: str) -> dict[str, Any]:
    if _contains_symlink(path) or not path.is_file():
        raise ValueError(error_code + "_file_not_regular")
    if path.stat().st_size > MAX_EXPERIMENT_ARTIFACT_BYTES:
        raise ValueError(error_code + "_file_unbounded")
    try:
        value = json.loads(path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(error_code + "_unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(error_code + "_object_required")
    return value


def audit_preflight_cohort(*, report_paths: list[Path],
        verification_paths: list[Path], cycle_root: Path,
        journal_root: Path, plan_path: Path | None = None,
        cycle_index: int = 0,
        history_record_allowlist_paths: list[Path] | None = None,
        task_commitment_key_path: Path | None = None,
        allow_recomputed_identity_recipe: bool = False
        ) -> dict[str, Any]:
    if (len(report_paths) < 2 or len(report_paths) > 256
            or len(verification_paths) != len(report_paths)):
        raise ValueError("historical_examples_preflight_cohort_too_small")
    if (history_record_allowlist_paths is not None
            and len(history_record_allowlist_paths) != len(report_paths)):
        raise ValueError("historical_examples_cohort_allowlist_roster_invalid")
    task_commitment_key: str | None = None
    task_commitment_key_digest: str | None = None
    if task_commitment_key_path is not None:
        task_commitment_key, task_commitment_key_digest = (
            _read_private_task_commitment_key(task_commitment_key_path))
    journal = HistoricalExamplesPairJournal(
        store=DevelopmentalExperimentStore(journal_root))
    trials: list[dict[str, Any]] = []
    seeds: set[int] = set()
    order_seeds: set[str] = set()
    task_digests: set[str] = set()
    protocol_digests: set[str] = set()
    report_digests: set[str] = set()
    probe_inputs: dict[int, tuple[int, str]] = {}
    shared: dict[str, Any] | None = None

    for report_path, verification_path in zip(report_paths,
            verification_paths, strict=True):
        report = _read_object(report_path,
            error_code="historical_examples_cohort_report")
        if (not isinstance(report, Mapping)
                or report.get("schema_version") not in {
                    "sentientos.resident_historical_examples_cpu_preflight:v6",
                    "sentientos.resident_historical_examples_cpu_preflight:v7",
                    "sentientos.resident_historical_examples_cpu_preflight:v8",
                    "sentientos.resident_historical_examples_cpu_preflight:v9",
                    "sentientos.resident_historical_examples_cpu_preflight:v10"}
                or report.get("model_loaded") is not False
                or report.get("model_invoked") is not False
                or report.get("learning_established") is not False
                or report.get("protocol_persisted") is not True
                or report.get("source_history_mutated") is not False):
            raise ValueError("historical_examples_cohort_preflight_report_invalid")
        seed = report.get("task_generation_seed")
        if type(seed) is not int or seed in seeds:
            raise ValueError("historical_examples_cohort_task_seed_collision")
        order_seed = report.get("arm_order_seed")
        if (not isinstance(order_seed, str)
                or re.fullmatch(r"[0-9a-f]{64}", order_seed) is None
                or order_seed in order_seeds
                or report.get("arm_order_policy") !=
                    "independent_os_random_seed_v1"):
            raise ValueError("historical_examples_cohort_arm_order_seed_invalid")
        verification = _read_object(verification_path,
            error_code="historical_examples_cohort_verification")
        if (not isinstance(verification, Mapping)
                or verification.get("schema_version") !=
                    "sentientos.resident_historical_examples_preflight_verification:v7"
                or verification.get("preflight_report_digest") !=
                    _digest(dict(report))
                or verification.get("source_history_reconstructed") is not True
                or verification.get("owner_prompt_pair_reconstructed") is not True
                or verification.get("journal_protocol_verified") is not True
                or verification.get(
                    "resident_owner_protocol_gate_verified") is not True
                or verification.get("model_loaded") is not False
                or verification.get("model_invoked") is not False
                or verification.get("learning_established") is not False
                or verification.get("authority") is not False):
            raise ValueError(
                "historical_examples_cohort_reconstruction_unverified")
        identity_policy = report.get("history_prompt_identity_policy")
        allowlist_path = (history_record_allowlist_paths[len(seeds)]
            if history_record_allowlist_paths is not None else None)
        if identity_policy is not None and (allowlist_path is None
                or task_commitment_key is None
                or task_commitment_key_digest is None):
            raise ValueError(
                "historical_examples_cohort_identity_neutral_inputs_required")
        task_nonces = (derive_rootless_task_commitment_nonces(
                task_commitment_key, seed=seed,
                task_family_id=report.get("task_family_id"))
            if task_commitment_key is not None else None)
        reconstructed = verify_preflight_report(cycle_root=cycle_root,
            journal_root=journal_root, report_path=report_path, seed=seed,
            plan_path=plan_path, cycle_index=cycle_index,
            history_record_allowlist_file=allowlist_path,
            task_commitment_nonces=task_nonces,
            task_commitment_key_file_sha256=task_commitment_key_digest,
            history_prompt_identity_policy=identity_policy,
            allow_recomputed_campaign_source_pin_mismatch=(
                allow_recomputed_identity_recipe))
        if dict(verification) != reconstructed:
            raise ValueError(
                "historical_examples_cohort_verification_reconstruction_mismatch")
        protocol = report.get("historical_examples_protocol")
        if not isinstance(protocol, Mapping):
            raise ValueError("historical_examples_cohort_protocol_missing")
        validate_historical_examples_protocol(protocol=protocol)
        seeds.add(seed)
        protocol_digest = protocol.get("protocol_digest")
        report_digest = _digest(dict(report))
        if (not isinstance(protocol_digest, str)
                or protocol_digest in protocol_digests
                or report_digest in report_digests):
            raise ValueError("historical_examples_cohort_digest_collision")
        protocol_digests.add(protocol_digest)
        report_digests.add(report_digest)
        stored = journal.load_protocol(protocol_digest=protocol_digest)
        if stored != dict(protocol):
            raise ValueError("historical_examples_cohort_journal_mismatch")
        if (verification.get("protocol_digest") != protocol_digest
                or verification.get("private_task_plan_digest") !=
                    protocol.get("private_task_plan_digest")):
            raise ValueError(
                "historical_examples_cohort_verification_binding_mismatch")
        task = journal.load_task_for_protocol(protocol_digest=protocol_digest)
        descriptor = task.public_descriptor()
        values = descriptor.get("probe_inputs") if isinstance(descriptor, Mapping) else None
        task_digest = (descriptor.get("task_digest")
            if isinstance(descriptor, Mapping) else None)
        if (not isinstance(task_digest, str)
                or protocol.get("task_digest") != task_digest
                or task_digest in task_digests):
            raise ValueError("historical_examples_cohort_task_digest_invalid")
        if (not isinstance(values, (list, tuple)) or not values
                or any(type(value) is not int for value in values)
                or len(set(values)) != len(values)):
            raise ValueError("historical_examples_cohort_probe_inputs_invalid")
        for value in values:
            if value in probe_inputs:
                prior_seed, prior_protocol = probe_inputs[value]
                raise ValueError(
                    "historical_examples_cohort_probe_reuse:" +
                    f"{prior_seed}:{prior_protocol}:{seed}:{protocol_digest}")
            probe_inputs[value] = (seed, protocol_digest)

        audit = report.get("held_out_probe_overlap_audit")
        if (not isinstance(audit, Mapping)
                or audit.get("measurement_complete") is not True
                or audit.get("no_exact_overlap_detected") is not True
                or audit.get("overlapping_probe_input_count") != 0
                or audit.get("task_probe_count") != len(values)):
            raise ValueError("historical_examples_cohort_history_overlap_invalid")
        binding = {key: protocol.get(key) for key in (
            "task_family_id", "target_model_identity_digest", "snapshot_id",
            "snapshot_digest", "history_set_digest", "generation_config_digest",
            "generation_budget_digest")}
        binding["history_prompt_identity_policy"] = identity_policy
        if "model_identity_backend_seed" in report:
            binding["model_identity_backend_seed"] = report[
                "model_identity_backend_seed"]
        binding.update({"cycle_root_id": report.get("cycle_root_id"),
            "source_receipt_id": report.get("source_receipt_id"),
            "source_receipt_digest": report.get("source_receipt_digest")})
        if shared is None:
            shared = binding
        elif binding != shared:
            raise ValueError("historical_examples_cohort_shared_boundary_mismatch")
        trials.append({"task_generation_seed": seed,
            "task_digest": task_digest,
            "report_digest": report_digest,
            "verification_digest": _digest(dict(verification)),
            "protocol_digest": protocol_digest,
            "arm_order_seed_digest": _digest(order_seed),
            "arm_order": list(protocol["conditions"]),
            "probe_count": len(values),
            "probe_binding_set_digest": _digest(
                sorted(protocol["probe_binding_digests"]))})
        order_seeds.add(order_seed)
        task_digests.add(task_digest)

    trials.sort(key=lambda row: row["task_generation_seed"])
    semantic = {"schema_version":
            "sentientos.historical_examples_preflight_cohort_audit:v1",
        "trial_count": len(trials), "unique_probe_input_count": len(probe_inputs),
        "shared_boundary": shared, "trials": trials,
        "model_loaded": False, "model_invoked": False,
        "learning_established": False, "authority": False}
    return {**semantic, "cohort_digest": _digest(semantic)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal-root", type=Path, required=True)
    parser.add_argument("--cycle-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--cycle-index", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verifications", type=Path, nargs="+", required=True)
    parser.add_argument("--history-record-allowlist-files", type=Path, nargs="+")
    parser.add_argument("--shared-task-commitment-key-file", type=Path)
    parser.add_argument("--allow-recomputed-identity-recipe", action="store_true")
    parser.add_argument("reports", type=Path, nargs="+")
    args = parser.parse_args()
    result = audit_preflight_cohort(report_paths=args.reports,
        verification_paths=args.verifications,
        cycle_root=args.cycle_root, journal_root=args.journal_root,
        plan_path=args.plan, cycle_index=args.cycle_index,
        history_record_allowlist_paths=args.history_record_allowlist_files,
        task_commitment_key_path=args.shared_task_commitment_key_file,
        allow_recomputed_identity_recipe=args.allow_recomputed_identity_recipe)
    encoded = json.dumps(result, sort_keys=True, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)
    print(json.dumps({"cohort_digest": result["cohort_digest"],
        "trial_count": result["trial_count"],
        "unique_probe_input_count": result["unique_probe_input_count"],
        "learning_established": False, "authority": False}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HistoricalExamplesInterventionError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
