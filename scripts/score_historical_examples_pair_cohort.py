#!/usr/bin/env python3
"""Aggregate a complete frozen historical-examples cohort without a model."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore, MAX_EXPERIMENT_ARTIFACT_BYTES,
)
from sentientos.historical_examples_analysis_plan import verify_analysis_plan
from sentientos.local_runtime_provisioning import semantic_digest
from scripts.verify_historical_examples_pair_score import verify_pair_score
from work.historical_examples_intervention import (
    HistoricalExamplesPairJournal, _digest, validate_historical_examples_pair_execution_plan,
)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("historical_examples_cohort_score_duplicate_key")
        value[key] = item
    return value


def _read_object(path: Path, *, code: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(code + "_not_regular")
    if path.stat().st_size > MAX_EXPERIMENT_ARTIFACT_BYTES:
        raise ValueError(code + "_unbounded")
    try:
        value = json.loads(path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError(code + "_nonstandard_json")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(code + "_unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(code + "_object_required")
    return value


def _verify_self_digest(value: Mapping[str, Any], field: str, code: str) -> None:
    semantic = {key: item for key, item in value.items() if key != field}
    if value.get(field) != _digest(semantic):
        raise ValueError(code + "_digest_mismatch")


def _verify_score(score: Mapping[str, Any], trial: Mapping[str, Any], *,
        runtime_history_inventory: Mapping[str, Any]) -> dict[str, Any]:
    _verify_self_digest(score, "score_digest",
        "historical_examples_cohort_score")
    protocol_digest = trial.get("protocol_digest")
    probe_count = trial.get("probe_count")
    probe_set_digest = trial.get("probe_binding_set_digest")
    if (score.get("schema_version") !=
            "sentientos.historical_examples_intervention_score:v2"
            or score.get("protocol_digest") != protocol_digest
            or type(probe_count) is not int
            or score.get("probe_count") != probe_count
            or score.get("paired_delivery_verified") is not True
            or score.get("inference_performed") is not True
            or score.get("independent_scorer_attested") is not False
            or score.get("learning_established") is not False
            or score.get("authority") is not False):
        raise ValueError("historical_examples_cohort_score_trial_binding_invalid")
    arms = ("examples_included", "examples_omitted")
    outcomes = score.get("outcomes_by_arm")
    paired = score.get("paired_probe_outcomes")
    arm_order = trial.get("arm_order")
    if (not isinstance(arm_order, list) or len(arm_order) != len(arms)
            or set(arm_order) != set(arms)
            or not isinstance(outcomes, Mapping) or set(outcomes) != set(arms)
            or not isinstance(paired, list) or len(paired) != probe_count
            or any(not isinstance(outcomes.get(arm), list)
                or len(outcomes[arm]) != probe_count for arm in arms)):
        raise ValueError("historical_examples_cohort_score_outcomes_invalid")
    probe_digests: list[str] = []
    correct = {arm: 0 for arm in arms}
    for index, row in enumerate(paired):
        if (not isinstance(row, Mapping)
                or set(row) != {"probe_binding_digest", *arms}):
            raise ValueError("historical_examples_cohort_score_pair_invalid")
        probe_digest = row.get("probe_binding_digest")
        if not isinstance(probe_digest, str):
            raise ValueError("historical_examples_cohort_score_probe_invalid")
        probe_digests.append(probe_digest)
        for arm in arms:
            arm_row = outcomes[arm][index]
            if (not isinstance(arm_row, Mapping)
                    or arm_row.get("probe_binding_digest") != probe_digest
                    or arm_row.get("outcome") != row.get(arm)
                    or row.get(arm) not in {"correct", "incorrect", "abstained"}):
                raise ValueError("historical_examples_cohort_score_pair_mismatch")
            correct[arm] += row[arm] == "correct"
    if (len(set(probe_digests)) != probe_count
            or _digest(sorted(probe_digests)) != probe_set_digest
            or score.get("correct_counts") != correct
            or not isinstance(runtime_history_inventory, Mapping)
            or runtime_history_inventory.get("stable_within_arm") is not True
            or runtime_history_inventory.get("selected_records_verified") is not True
            or runtime_history_inventory.get("receipt_record_links_verified") is not True
            or runtime_history_inventory.get("selected_record_receipts_verified") is not True
            or runtime_history_inventory.get("authority") is not False
            or runtime_history_inventory.get("schema_version") !=
                "sentientos.historical_examples_runtime_history_inventory:v2"):
        raise ValueError("historical_examples_cohort_score_count_or_probe_mismatch")
    return {"protocol_digest": protocol_digest,
        "score_digest": score["score_digest"],
        "task_generation_seed": trial.get("task_generation_seed"),
        "probe_count": probe_count,
        "runtime_history_record_count": runtime_history_inventory[
            "runtime_record_count"],
        "runtime_history_record_set_digest": runtime_history_inventory[
            "pair_baseline_record_set_digest"],
        "runtime_history_receipt_count": runtime_history_inventory[
            "runtime_receipt_count"],
        "runtime_history_receipt_set_digest": runtime_history_inventory[
            "pair_baseline_receipt_set_digest"],
        "runtime_history_receipt_record_links_verified": True,
        "selected_history_record_receipts_verified": True,
        "arm_order": list(arm_order),
        "paired_probe_outcomes": [dict(row) for row in paired],
        "correct_counts": correct,
        "per_task_accuracy_difference": {
            "numerator": correct["examples_included"] - correct["examples_omitted"],
            "denominator": probe_count}}


def _attribute_execution(*, execution_plan: Mapping[str, Any], cycle_roots: Path,
        cohort: Mapping[str, Any], analysis_plan: Mapping[str, Any],
        journal: HistoricalExamplesPairJournal) -> list[dict[str, Any]]:
    """Link each archived receipt to the run that registered this execution plan."""
    slots = execution_plan.get("trials")
    if (not isinstance(slots, list) or not slots
            or not all(isinstance(slot, Mapping) for slot in slots)):
        raise ValueError("historical_examples_cohort_execution_roster_invalid")
    run_ids = [slot.get("runner_cycle_id") for slot in slots]
    validate_historical_examples_pair_execution_plan(cohort=cohort,
        analysis_plan=analysis_plan, runner_cycle_ids=run_ids,
        backend_seed=slots[0].get("backend_seed"), plan=execution_plan)
    external_digest = execution_plan["execution_plan_digest"].removeprefix("sha256:")
    attributed = []
    for slot in slots:
        run_id = slot["runner_cycle_id"]
        arms = {arm: journal.arm_execution_history(
            protocol_digest=slot["protocol_digest"], arm=arm) for arm in slot["arm_order"]}
        if any(arm["status"] != "completed" or arm["receipt_run_id"] != run_id
                for arm in arms.values()):
            raise ValueError("historical_examples_cohort_receipt_run_mismatch:" + run_id)
        path = cycle_roots.absolute() / run_id / "preregistration.json"
        if any(parent.is_symlink() for parent in path.parents):
            raise ValueError("historical_examples_cohort_run_path_invalid")
        registration = _read_object(path, code="historical_examples_cohort_run_preregistration")
        digest = registration.pop("preregistration_digest", None)
        if (registration.get("schema_version") != "sentientos.rootless_hermes_cycle_preregistration:v1"
                or digest != semantic_digest(registration) or registration.get("run_id") != run_id
                or registration.get("experiment_seed") != slot["task_generation_seed"]
                or registration.get("external_protocol_digest") != external_digest
                or any(arm["run_preregistration_digest"] != digest for arm in arms.values())):
            raise ValueError("historical_examples_cohort_run_preregistration_mismatch:" + run_id)
        attributed.append({"runner_cycle_id": run_id, "protocol_digest": slot["protocol_digest"],
            "run_preregistration_digest": digest,
            "receipt_digests": {name: arm["receipt_digest"] for name, arm in arms.items()}})
    return attributed


def score_cohort(*, cohort: Mapping[str, Any], plan: Mapping[str, Any],
        journal: HistoricalExamplesPairJournal,
        independent_verifications: Sequence[Mapping[str, Any]] | None = None,
        execution_plan: Mapping[str, Any] | None = None, cycle_roots: Path | None = None
        ) -> dict[str, Any]:
    """Require every frozen pair and produce the preregistered descriptive mean."""
    semantic_cohort = {key: value for key, value in cohort.items()
        if key != "cohort_digest"}
    if (cohort.get("schema_version") !=
            "sentientos.historical_examples_preflight_cohort_audit:v1"
            or cohort.get("cohort_digest") != _digest(semantic_cohort)
            or cohort.get("model_loaded") is not False
            or cohort.get("model_invoked") is not False
            or cohort.get("learning_established") is not False
            or cohort.get("authority") is not False):
        raise ValueError("historical_examples_cohort_manifest_invalid")
    verify_analysis_plan(cohort=cohort, plan=plan)
    if (execution_plan is None) != (cycle_roots is None):
        raise ValueError("historical_examples_cohort_execution_plan_and_cycle_roots_required")
    attribution = None
    if execution_plan is not None and cycle_roots is not None:
        attribution = _attribute_execution(execution_plan=execution_plan, cycle_roots=cycle_roots,
            cohort=cohort, analysis_plan=plan, journal=journal)
    independent_scorer_required = plan.get("schema_version") == (
        "sentientos.historical_examples_pair_cohort_analysis_plan:v2")
    expected_scorer_digest = None
    if independent_scorer_required or independent_verifications is not None:
        scorer_source_path = Path(__file__).with_name(
            "verify_historical_examples_pair_score.py")
        expected_scorer_digest = "sha256:" + hashlib.sha256(
            scorer_source_path.read_bytes()).hexdigest()
        if (independent_scorer_required
                and plan.get("independent_scorer_implementation_digest")
                    != expected_scorer_digest):
            raise ValueError(
                "historical_examples_cohort_independent_scorer_source_changed")
    if independent_scorer_required and independent_verifications is None:
        raise ValueError(
            "historical_examples_cohort_independent_verification_required")
    trials = cohort.get("trials")
    if (not isinstance(trials, list)
            or len(trials) != plan.get("trial_count")
            or not isinstance(journal, HistoricalExamplesPairJournal)):
        raise ValueError("historical_examples_cohort_incomplete")
    if (any(not isinstance(row, Mapping) for row in trials)
            or len({row.get("protocol_digest") for row in trials}) != len(trials)
            or len({row.get("task_generation_seed") for row in trials}) != len(trials)
            or len({row.get("task_digest") for row in trials}) != len(trials)
            or sum(row.get("probe_count", 0) for row in trials)
                != cohort.get("unique_probe_input_count")):
        raise ValueError("historical_examples_cohort_trial_set_invalid")
    trials_by_protocol = {row.get("protocol_digest"): row for row in trials
        if isinstance(row, Mapping)}
    scores_by_protocol: dict[str, Mapping[str, Any]] = {}
    inventory_by_protocol: dict[str, Mapping[str, Any]] = {}
    for protocol_digest in trials_by_protocol:
        protocol = journal.load_protocol(protocol_digest=protocol_digest)
        trial = trials_by_protocol[protocol_digest]
        if (protocol.get("protocol_digest") != protocol_digest
                or protocol.get("task_digest") != trial.get("task_digest")
                or protocol.get("conditions") != trial.get("arm_order")
                or not isinstance(protocol.get("probe_binding_digests"), list)
                or len(protocol["probe_binding_digests"]) !=
                    trial.get("probe_count")
                or _digest(sorted(protocol["probe_binding_digests"])) !=
                    trial.get("probe_binding_set_digest")):
            raise ValueError("historical_examples_cohort_journal_mismatch")
        scores_by_protocol[protocol_digest] = journal.load_score(
            protocol_digest=protocol_digest)
        states = [journal.arm_state(protocol_digest=protocol_digest, arm=arm)
            for arm in protocol["conditions"]]
        inventories = [state.get("runtime_history_inventory")
            for state in states]
        if (not inventories or any(not isinstance(value, Mapping)
                for value in inventories)
                or len({value.get("pair_baseline_record_set_digest")
                    for value in inventories if isinstance(value, Mapping)}) != 1
                or len({value.get("pair_baseline_receipt_set_digest")
                    for value in inventories if isinstance(value, Mapping)}) != 1
                or len({value.get("runtime_record_count")
                    for value in inventories if isinstance(value, Mapping)}) != 1
                or len({value.get("runtime_receipt_count")
                    for value in inventories if isinstance(value, Mapping)}) != 1):
            raise ValueError("historical_examples_cohort_runtime_history_inventory_invalid")
        inventory_by_protocol[protocol_digest] = inventories[0]

    rows = [_verify_score(scores_by_protocol[trial["protocol_digest"]], trial,
        runtime_history_inventory=inventory_by_protocol[trial["protocol_digest"]])
        for trial in sorted(trials, key=lambda row: row["task_generation_seed"])]
    if independent_verifications is not None:
        if len(independent_verifications) != len(rows):
            raise ValueError(
                "historical_examples_cohort_independent_verification_count_invalid")
        verifications: dict[str, Mapping[str, Any]] = {}
        store_root = getattr(getattr(journal, "_store", None), "root", None)
        if (not isinstance(store_root, Path)
                or store_root.name != "developmental_experiments"):
            raise ValueError(
                "historical_examples_cohort_independent_journal_root_invalid")
        journal_root = store_root.parent
        for verification in independent_verifications:
            if not isinstance(verification, Mapping):
                raise ValueError(
                    "historical_examples_cohort_independent_verification_invalid")
            _verify_self_digest(verification, "verification_digest",
                "historical_examples_independent_score_verification")
            protocol_digest = verification.get("protocol_digest")
            score = scores_by_protocol.get(protocol_digest)
            receipt_digests = verification.get("independent_receipt_digests")
            score_bindings = (score.get("invocation_receipt_bindings")
                if isinstance(score, Mapping) else None)
            if (verification.get("schema_version") !=
                    "sentientos.historical_examples_pair_score_verification:v2"
                    or verification.get("independent_scorer_attested") is not True
                    or verification.get(
                        "independent_scorer_implementation_digest") !=
                            expected_scorer_digest
                    or not isinstance(protocol_digest, str)
                    or protocol_digest not in trials_by_protocol
                    or protocol_digest in verifications
                    or verification.get("score_digest") != score.get("score_digest")
                    or verification.get("correct_counts") != score.get("correct_counts")
                    or verification.get("independent_recomputed_correct_counts")
                        != score.get("correct_counts")
                    or not isinstance(receipt_digests, Mapping)
                    or set(receipt_digests) != {
                        "examples_included", "examples_omitted"}
                    or any(not isinstance(value, str) or len(value) != 64
                        or any(character not in "0123456789abcdef"
                            for character in value)
                        for value in receipt_digests.values())
                    or not isinstance(verification.get(
                        "independent_recomputed_outcomes_digest"), str)
                    or len(verification[
                        "independent_recomputed_outcomes_digest"]) != 71
                    or not verification[
                        "independent_recomputed_outcomes_digest"].startswith(
                            "sha256:")
                    or not isinstance(score_bindings, Mapping)
                    or any(not isinstance(score_bindings.get(arm), Mapping)
                        for arm in ("examples_included", "examples_omitted"))
                    or any(receipt_digests.get(arm) !=
                        score_bindings.get(arm, {}).get("receipt_digest")
                        for arm in ("examples_included", "examples_omitted"))):
                raise ValueError(
                    "historical_examples_cohort_independent_verification_binding_invalid")
            try:
                reconstructed_verification = verify_pair_score(
                    journal_root=journal_root,
                    protocol_digest=protocol_digest)
            except Exception as exc:
                raise ValueError(
                    "historical_examples_cohort_independent_rescore_reconstruction_failed") from exc
            if dict(verification) != reconstructed_verification:
                raise ValueError(
                    "historical_examples_cohort_independent_rescore_reconstruction_mismatch")
            verifications[protocol_digest] = verification
        for row in rows:
            verification = verifications.get(row["protocol_digest"])
            if verification is None:
                raise ValueError(
                    "historical_examples_cohort_independent_verification_missing")
            row["independent_score_verification_digest"] = verification[
                "verification_digest"]
    differences = [Fraction(row["per_task_accuracy_difference"]["numerator"],
        row["per_task_accuracy_difference"]["denominator"]) for row in rows]
    mean = sum(differences, Fraction()) / len(differences)
    semantic = {"schema_version":
            "sentientos.historical_examples_pair_cohort_score:v3",
        "cohort_digest": cohort["cohort_digest"],
        "analysis_plan_digest": plan["analysis_plan_digest"],
        "trial_count": len(rows), "complete_trial_count": len(rows),
        "number_of_complete_trials": len(rows),
        "whether_any_trial_is_incomplete": False,
        "per_trial_correct_counts_by_arm": [{
            "protocol_digest": row["protocol_digest"],
            "task_generation_seed": row["task_generation_seed"],
            "correct_counts": row["correct_counts"]} for row in rows],
        "per_trial_accuracy_difference": [{
            "protocol_digest": row["protocol_digest"],
            "task_generation_seed": row["task_generation_seed"],
            "accuracy_difference": row["per_task_accuracy_difference"]}
            for row in rows],
        "per_trial_probe_outcomes": [{
            "protocol_digest": row["protocol_digest"],
            "task_generation_seed": row["task_generation_seed"],
            "paired_probe_outcomes": row["paired_probe_outcomes"]}
            for row in rows],
        "arm_order_by_trial": [{
            "protocol_digest": row["protocol_digest"],
            "task_generation_seed": row["task_generation_seed"],
            "arm_order": row["arm_order"]} for row in rows],
        "per_trial_results": rows,
        "cohort_mean_accuracy_difference": {
            "numerator": mean.numerator, "denominator": mean.denominator,
            "decimal_rounded_6": round(float(mean), 6)},
        "analysis_unit": "task_seed_pair_not_individual_probe",
        "inference_scope": "immediate_response_difference_only",
        "source_score_artifact_verification":
            "reconstructed_from_private_task_plan_archived_verified_arm_receipts_and_stable_record_and_receipt_inventory:v2",
        "independent_scorer_attested": independent_verifications is not None,
        "durable_learning_established": False,
        "model_attention_established": False,
        "general_transfer_established": False,
        "model_independence_established": False,
        "learning_established": False, "authority": False}
    if attribution is not None and execution_plan is not None:
        semantic.update(schema_version="sentientos.historical_examples_pair_cohort_score:v4",
            execution_plan_digest=execution_plan["execution_plan_digest"],
            receipt_run_attribution=attribution)
    return {**semantic, "cohort_score_digest": _digest(semantic)}


def verify_cohort_score(*, saved_score: Mapping[str, Any],
        cohort: Mapping[str, Any], plan: Mapping[str, Any],
        journal: HistoricalExamplesPairJournal,
        independent_verifications: Sequence[Mapping[str, Any]] | None = None,
        execution_plan: Mapping[str, Any] | None = None, cycle_roots: Path | None = None
        ) -> dict[str, Any]:
    """Reconstruct a saved aggregate from frozen inputs and journal scores."""
    expected = score_cohort(cohort=cohort, plan=plan, journal=journal,
        independent_verifications=independent_verifications, execution_plan=execution_plan,
        cycle_roots=cycle_roots)
    if not isinstance(saved_score, Mapping) or dict(saved_score) != expected:
        raise ValueError("historical_examples_cohort_score_reconstruction_mismatch")
    return {"schema_version":
            "sentientos.historical_examples_pair_cohort_score_verification:v2",
        "cohort_score_digest": expected["cohort_score_digest"],
        "cohort_digest": expected["cohort_digest"],
        "analysis_plan_digest": expected["analysis_plan_digest"],
        "cohort_score_schema_version": expected["schema_version"],
        "complete_trial_count": expected["complete_trial_count"],
        "cohort_score_reconstructed": True,
        "learning_established": False, "authority": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--journal-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-score", type=Path)
    parser.add_argument("--execution-plan", type=Path,
        help="bind the score to the exact run IDs and execution plan cited by the receipts")
    parser.add_argument("--cycle-roots", type=Path,
        help="developmental-cognition-cycles directory containing those runs' preregistrations")
    parser.add_argument("--independent-verifications", type=Path, nargs="+",
        help="one independent raw-receipt rescore verification per frozen trial")
    args = parser.parse_args()
    if (args.output is None) == (args.verify_score is None):
        raise ValueError("historical_examples_cohort_score_output_mode_required")
    cohort = _read_object(args.cohort, code="historical_examples_cohort")
    plan = _read_object(args.plan, code="historical_examples_analysis_plan")
    execution_plan = (_read_object(args.execution_plan, code="historical_examples_execution_plan")
        if args.execution_plan is not None else None)
    journal = HistoricalExamplesPairJournal(
        store=DevelopmentalExperimentStore(args.journal_root))
    independent_verifications = ([ _read_object(path,
        code="historical_examples_independent_score_verification")
        for path in args.independent_verifications]
        if args.independent_verifications is not None else None)
    if args.verify_score is not None:
        verification = verify_cohort_score(
            saved_score=_read_object(args.verify_score,
                code="historical_examples_cohort_score"),
            cohort=cohort, plan=plan, journal=journal,
            independent_verifications=independent_verifications, execution_plan=execution_plan,
            cycle_roots=args.cycle_roots)
        print(json.dumps(verification, sort_keys=True, indent=2))
        return 0
    result = score_cohort(cohort=cohort, plan=plan, journal=journal,
        independent_verifications=independent_verifications, execution_plan=execution_plan,
        cycle_roots=args.cycle_roots)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"cohort_score_digest": result["cohort_score_digest"],
        "cohort_digest": result["cohort_digest"],
        "analysis_plan_digest": result["analysis_plan_digest"],
        "complete_trial_count": result["complete_trial_count"],
        "cohort_mean_accuracy_difference":
            result["cohort_mean_accuracy_difference"],
        "learning_established": False, "authority": False},
        sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
