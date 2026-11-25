"""Canonical freeze and reconstruction for historical-example analysis plans."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def _digest(value: Any) -> str:
    """Canonical experiment-artifact digest, matching the pair journal."""
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            "historical_examples_analysis_value_not_canonical_json") from exc
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def freeze_analysis_plan(cohort: Mapping[str, Any], *,
        require_independent_scorer: bool = True) -> dict[str, Any]:
    """Derive a score-free analysis plan; independent scoring is the default."""
    if (not isinstance(cohort, Mapping)
            or cohort.get("schema_version") !=
                "sentientos.historical_examples_preflight_cohort_audit:v1"
            or cohort.get("model_loaded") is not False
            or cohort.get("model_invoked") is not False
            or cohort.get("learning_established") is not False
            or cohort.get("authority") is not False):
        raise ValueError("historical_examples_analysis_cohort_posture_invalid")
    cohort_digest = cohort.get("cohort_digest")
    semantic_cohort = {key: value for key, value in cohort.items()
        if key != "cohort_digest"}
    if not isinstance(cohort_digest, str) or cohort_digest != _digest(
            semantic_cohort):
        raise ValueError("historical_examples_analysis_cohort_digest_invalid")
    trials = cohort.get("trials")
    probe_counts = ({row.get("probe_count") for row in trials
        if isinstance(row, Mapping)} if isinstance(trials, list) else set())
    if (not isinstance(trials, list) or len(trials) < 2
            or cohort.get("trial_count") != len(trials)
            or len({row.get("task_digest") for row in trials
                if isinstance(row, Mapping)}) != len(trials)
            or any(not isinstance(row, Mapping)
                or type(row.get("probe_count")) is not int
                or not 1 <= row.get("probe_count") <= 16 for row in trials)
            or len(probe_counts) != 1
            or sum(row["probe_count"] for row in trials)
                != cohort.get("unique_probe_input_count")):
        raise ValueError("historical_examples_analysis_trial_set_invalid")

    semantic = {
        "schema_version": ("sentientos.historical_examples_pair_cohort_analysis_plan:v2"
            if require_independent_scorer else
            "sentientos.historical_examples_pair_cohort_analysis_plan:v1"),
        "cohort_digest": cohort_digest,
        "trial_count": len(trials),
        "unique_probe_input_count": cohort["unique_probe_input_count"],
        "analysis_timing": "after_cohort_freeze_before_any_model_inference",
        "analysis_unit": "task_seed_pair_not_individual_probe",
        "primary_outcome": {
            "name": "per_task_accuracy_difference",
            "condition_difference": "examples_included_minus_examples_omitted",
            "per_task_formula":
                "correct_count / probe_count per arm; subtract omitted accuracy from included accuracy",
            "cohort_summary":
                "unweighted arithmetic mean of per_task_accuracy_difference",
            "requires_all_frozen_pairs_complete": True,
        },
        "required_reporting": [
            "per_trial_correct_counts_by_arm",
            "per_trial_accuracy_difference",
            "per_trial_probe_outcomes",
            "arm_order_by_trial",
            "number_of_complete_trials",
            "whether_any_trial_is_incomplete",
        ],
        "incomplete_trial_policy": {
            "cohort_mean_reportable": False,
            "replace_trial": False,
            "retry_ambiguous_invocation": False,
            "exclude_incomplete_trial_and_recompute_mean": False,
        },
        "inferential_statistics": "none; report descriptive results only",
        "pooled_probe_counts_posture":
            "supplementary_descriptive_only; probes_are_nested_within_task",
        "scoring_posture": (
            "independent_raw_receipt_rescore_required; separate_scorer_process_not_attested"
            if require_independent_scorer else
            "same_process_answer_key_and_arm_labeled_receipts; independent scorer not attested"),
        "claim_limits": {
            "immediate_response_difference_only": True,
            "durable_learning_established": False,
            "model_attention_established": False,
            "general_transfer_established": False,
            "model_independence_established": False,
            "authority": False,
        },
        "outcomes_observed": False,
        "model_loaded": False,
        "model_invoked": False,
        "learning_established": False,
        "authority": False,
    }
    if require_independent_scorer:
        scorer_source = (Path(__file__).resolve().parents[1] / "scripts" /
            "verify_historical_examples_pair_score.py")
        semantic["independent_scorer_implementation_digest"] = (
            "sha256:" + hashlib.sha256(scorer_source.read_bytes()).hexdigest())
    return {**semantic, "analysis_plan_digest": _digest(semantic)}


def verify_analysis_plan(*, cohort: Mapping[str, Any],
        plan: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct the exact plan from its cohort and pinned scorer source."""
    if not isinstance(plan, Mapping):
        raise ValueError("historical_examples_analysis_plan_schema_invalid")
    version = plan.get("schema_version")
    if version not in {
            "sentientos.historical_examples_pair_cohort_analysis_plan:v1",
            "sentientos.historical_examples_pair_cohort_analysis_plan:v2"}:
        raise ValueError("historical_examples_analysis_plan_schema_invalid")
    expected = freeze_analysis_plan(cohort,
        require_independent_scorer=(version ==
            "sentientos.historical_examples_pair_cohort_analysis_plan:v2"))
    if dict(plan) != expected:
        raise ValueError(
            "historical_examples_analysis_plan_reconstruction_mismatch")
    return {"schema_version":
            "sentientos.historical_examples_pair_analysis_plan_verification:v1",
        "cohort_digest": expected["cohort_digest"],
        "analysis_plan_digest": expected["analysis_plan_digest"],
        "trial_count": expected["trial_count"],
        "unique_probe_input_count": expected["unique_probe_input_count"],
        "plan_reconstructed_from_cohort": True,
        "outcomes_observed": False, "model_loaded": False,
        "model_invoked": False, "learning_established": False,
        "authority": False}
