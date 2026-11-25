"""Describe same-family acquisition competence outcomes offline.

This post-hoc analysis tool is scoped to same-family acquisition, not
cross-range transfer. It keeps the existing incremental-transfer
gate intact and does not itself establish causality, learning, or authority.
For future confirmatory use, freeze this implementation and its thresholds in
the campaign plan before inference.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.local_model_authority import digest_payload  # noqa: E402
from work.rootless_history_boundary_campaign import (  # noqa: E402
    _load_plan,
    verify_chain,
    verify_experiment_implementation,
    verify_model_identity_recipe,
)

_WIDE_FAMILY = "rootless_integer_affine_transfer_wide_range_v7"
_SOURCE_FAMILIES = [
    "rootless_integer_affine_transfer_low_range_v6",
    _WIDE_FAMILY,
]
_CONDITIONS = ["history_present", "history_withheld", "history_restored"]
_MIN_REPLICATED_CYCLES = 2


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _classify_cycle(*, cycle_root: Path, plan: Mapping[str, Any],
        index: int) -> dict[str, Any]:
    terminal_path = cycle_root / "cycle-result.json"
    if terminal_path.is_symlink() or not terminal_path.is_file():
        raise ValueError("same_family_acquisition_terminal_missing")
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    _require(isinstance(terminal, Mapping),
        "same_family_acquisition_terminal_invalid")
    cycle_id = plan["ordered_cycle_ids"][index]
    _require(cycle_root.name == cycle_id and terminal.get("run_id") == cycle_id,
        "same_family_acquisition_cycle_binding_mismatch")
    _require(terminal.get("status") == "completed",
        "same_family_acquisition_cycle_incomplete")
    _require(terminal.get("external_preregistration_digest") ==
        plan.get("plan_digest"),
        "same_family_acquisition_plan_binding_mismatch")
    _require(terminal.get("source_provenance_stable_for_run") is True and
        terminal.get("source_provenance_fingerprint_complete") is True,
        "same_family_acquisition_source_provenance_incomplete")
    _require(terminal.get("model_id") ==
        plan["model_identity_recipe"]["model_name"] and
        terminal.get("model_manifest_digest") ==
            plan["model_identity_recipe"]["manifest_sha256"],
        "same_family_acquisition_model_binding_mismatch")
    expected_backend_seed = plan["ordered_backend_seeds"][index]
    expected_task_seed = plan["ordered_task_generation_seeds"][index]
    model_config = terminal.get("model_configuration_observation")
    config_payload = (model_config.get("payload")
        if isinstance(model_config, Mapping) else None)
    config_options = (config_payload.get("options")
        if isinstance(config_payload, Mapping) else None)
    _require(terminal.get("task_generation_seed") == expected_task_seed and
        terminal.get("requested_backend_seed") == expected_backend_seed and
        terminal.get("gpu_layers_requested") ==
            plan["model_identity_recipe"]["gpu_layers"] and
        isinstance(config_options, Mapping) and
        config_options.get("model") ==
            plan["model_identity_recipe"]["model_name"] and
        config_options.get("manifest_sha256") ==
            plan["model_identity_recipe"]["manifest_sha256"] and
        config_options.get("num_gpu") ==
            plan["model_identity_recipe"]["gpu_layers"] and
        config_options.get("seed") == expected_backend_seed,
        "same_family_acquisition_runtime_identity_mismatch")

    binding = terminal.get("history_campaign_binding")
    _require(isinstance(binding, Mapping) and
        binding.get("campaign_id") == plan.get("campaign_id") and
        binding.get("campaign_plan_digest") == plan.get("plan_digest") and
        binding.get("cycle_index") == index,
        "same_family_acquisition_campaign_binding_mismatch")
    preflight = binding.get("transfer_probe_preflight")
    _require(isinstance(preflight, Mapping) and
        preflight.get("schema_version") ==
            "sentientos.rootless_campaign_transfer_probe_preflight:v2" and
        preflight.get("history_task_family_ids") == _SOURCE_FAMILIES and
        preflight.get("held_out_transfer_qualified") is True and
        preflight.get("inference_performed") is False and
        preflight.get("learning_claimed") is False and
        preflight.get("authority_granted") is False,
        "same_family_acquisition_preflight_invalid")
    semantic_preflight = {k: v for k, v in preflight.items()
        if k != "preflight_digest"}
    _require(preflight.get("preflight_digest") ==
        digest_payload(semantic_preflight),
        "same_family_acquisition_preflight_digest_mismatch")
    overlap = preflight.get("historical_probe_overlap")
    _require(isinstance(overlap, Mapping) and
        overlap.get("historical_probe_overlap_measurement_complete") is True and
        overlap.get("historical_probe_overlap_input_count") == 0 and
        overlap.get("historical_probe_overlap_scope") ==
            "selected_score_bound_correct_incorrect_and_abstained_examples",
        "same_family_acquisition_overlap_invalid")
    task_inputs = preflight.get("acquisition_probe_inputs")
    _require(isinstance(task_inputs, list) and task_inputs and
        all(type(value) is int for value in task_inputs) and
        len(set(task_inputs)) == len(task_inputs),
        "same_family_acquisition_task_inputs_invalid")

    acquisition = terminal.get("objective_task_family_acquisition")
    _require(isinstance(acquisition, Mapping) and
        acquisition.get("task_family_id") == _WIDE_FAMILY,
        "same_family_acquisition_acquisition_invalid")
    acquisition_projection = acquisition.get("history_projection_audit")
    _require(isinstance(acquisition_projection, Mapping) and
        acquisition_projection.get("task_family_id") == _WIDE_FAMILY,
        "same_family_acquisition_acquisition_scope_invalid")
    prior_score_projection = acquisition_projection.get(
        "source_run_score_projection")
    _require(isinstance(prior_score_projection, Mapping),
        "same_family_acquisition_prior_score_projection_missing")
    transfer = terminal.get("objective_task_family_transfer")
    _require(isinstance(transfer, Mapping),
        "same_family_acquisition_transfer_outcome_missing")
    score_binding = acquisition.get("history_score_binding")
    _require(isinstance(score_binding, Mapping) and
        score_binding.get("verified") is True and
        score_binding.get("status") ==
            "verified_exact_source_run_score_to_history_binding" and
        score_binding.get("expected_counts") ==
            score_binding.get("observed_counts") and
        isinstance(score_binding.get("source_run_id"), str) and
        score_binding.get("source_run_id"),
        "same_family_acquisition_score_binding_invalid")

    outcome = acquisition.get("task_outcome")
    _require(isinstance(outcome, Mapping),
        "same_family_acquisition_outcome_missing")
    _require(score_binding.get("expected_score_digest") ==
        outcome.get("history_present_score_digest"),
        "same_family_acquisition_source_score_digest_mismatch")
    probe_level = outcome.get("probe_level_outcomes")
    _require(isinstance(probe_level, Mapping) and
        probe_level.get("posture") ==
            "independent_oracle_correctness_only_answer_values_omitted" and
        probe_level.get("condition_order") == _CONDITIONS,
        "same_family_acquisition_probe_scores_invalid")
    probes = probe_level.get("probe_outcomes")
    probe_count = outcome.get("probe_count")
    _require(isinstance(probes, list) and type(probe_count) is int and
        probe_count > 0 and len(probes) == probe_count and
        len(task_inputs) == probe_count,
        "same_family_acquisition_probe_count_invalid")
    counts = {condition: 0 for condition in _CONDITIONS}
    restoration_matches = True
    for probe in probes:
        _require(isinstance(probe, Mapping),
            "same_family_acquisition_probe_invalid")
        correctness = probe.get("correctness_by_condition")
        _require(isinstance(correctness, Mapping) and
            all(correctness.get(condition) in (True, False, None)
                for condition in _CONDITIONS),
            "same_family_acquisition_probe_correctness_invalid")
        for condition in _CONDITIONS:
            counts[condition] += correctness[condition] is True
        restoration_matches = restoration_matches and (
            correctness["history_present"] ==
            correctness["history_restored"])
    _require(outcome.get("condition_correct_counts") ==
        [counts[condition] for condition in _CONDITIONS],
        "same_family_acquisition_aggregate_score_mismatch")
    digests = outcome.get("condition_score_digests")
    _require(isinstance(digests, list) and len(digests) == len(_CONDITIONS)
        and all(isinstance(value, str) and value.startswith("sha256:")
            and len(value) == 71 for value in digests),
        "same_family_acquisition_score_digest_invalid")
    threshold = outcome.get("baseline_competence_threshold")
    _require(type(threshold) is int and threshold > 0,
        "same_family_acquisition_threshold_invalid")

    present = counts["history_present"]
    withheld = counts["history_withheld"]
    restored = counts["history_restored"]
    if (present >= threshold and withheld < threshold and
            restored >= threshold and restoration_matches):
        classification = "same_family_acquisition_competence_pattern"
    elif withheld >= threshold:
        classification = "same_family_withheld_baseline_competence_also_demonstrated"
    elif present < threshold or restored < threshold:
        classification = "same_family_acquisition_competence_not_demonstrated"
    else:
        classification = "same_family_restoration_did_not_match_present_correctness"
    return {
        "cycle_id": cycle_id,
        "measurement_scope": "wide_range_acquisition_same_family_history",
        "acquisition_projection_task_family_id":
            acquisition_projection.get("task_family_id"),
        "cross_range_transfer_status": transfer.get("status"),
        "cross_range_transfer_evaluated": False,
        "task_probe_input_digest": overlap.get("task_probe_input_digest"),
        "acquisition_output_run_id": score_binding["source_run_id"],
        "acquisition_output_score_binding_verified": True,
        "prior_history_projectable_source_run_count":
            acquisition_projection.get("projectable_source_run_count"),
        "prior_history_correct_example_count":
            prior_score_projection.get("correct_example_count"),
        "prior_history_source_run_id":
            prior_score_projection.get("source_run_id"),
        "probe_count": probe_count,
        "competence_threshold": threshold,
        "correct_counts": [counts[condition] for condition in _CONDITIONS],
        "condition_score_digests": digests,
        "_task_inputs": task_inputs,
        "restored_correctness_matches_present": restoration_matches,
        "classification": classification,
    }


def classify(*, plan_path: Path, cycle_roots: list[Path]) -> dict[str, Any]:
    plan = _load_plan(plan_path)
    _require(plan.get("task_family_id") == _WIDE_FAMILY,
        "same_family_acquisition_family_unsupported")
    _require(len(cycle_roots) >= _MIN_REPLICATED_CYCLES and
        len(cycle_roots) == len(plan.get("ordered_cycle_ids", [])),
        "same_family_acquisition_cycle_set_incomplete")
    _require([root.name for root in cycle_roots] == plan["ordered_cycle_ids"],
        "same_family_acquisition_cycle_order_mismatch")
    model_verification = verify_model_identity_recipe(plan)
    implementation_verification = verify_experiment_implementation(plan)
    chain = verify_chain(plan_path=plan_path, cycle_roots=cycle_roots)
    _require(chain.get("append_only_history_chain_verified") is True and
        chain.get("seed_boundary_chain_verified") is True and
        chain.get("all_planned_cycles_completed") is True and
        chain.get("learning_established") is False,
        "same_family_acquisition_chain_invalid")

    cycles = [_classify_cycle(cycle_root=root, plan=plan, index=index)
        for index, root in enumerate(cycle_roots)]
    _require(len({cycle["acquisition_output_run_id"] for cycle in cycles}) == len(cycles),
        "same_family_acquisition_source_runs_not_independent")
    input_digests = [cycle["task_probe_input_digest"] for cycle in cycles]
    _require(all(isinstance(value, str) and value.startswith("sha256:")
            for value in input_digests) and
        len(set(input_digests)) == len(input_digests),
        "same_family_acquisition_probe_inputs_not_independent")
    seen_inputs: set[int] = set()
    cross_cycle_overlap_count = 0
    for cycle in cycles:
        inputs = set(cycle.pop("_task_inputs"))
        cycle_overlap_count = len(inputs & seen_inputs)
        cycle["cross_cycle_probe_overlap_count"] = cycle_overlap_count
        cross_cycle_overlap_count += cycle_overlap_count
        seen_inputs.update(inputs)
    qualified = all(cycle["classification"] ==
        "same_family_acquisition_competence_pattern" for cycle in cycles)
    input_sets_disjoint = cross_cycle_overlap_count == 0
    if qualified and input_sets_disjoint:
        status = "replicated_same_family_acquisition_competence_pattern"
    elif qualified:
        status = "replication_not_independent_due_probe_overlap"
    else:
        status = "same_family_acquisition_competence_not_demonstrated"
    return {
        "schema_version": "sentientos.same_family_acquisition_competence_analysis:v1",
        "analysis_timing": "posthoc_same_family_acquisition_analysis",
        "campaign_id": plan["campaign_id"],
        "campaign_plan_digest": plan["plan_digest"],
        "task_family_id": plan["task_family_id"],
        "registered_overlap_source_families": list(_SOURCE_FAMILIES),
        "measurement_scope": "wide_range_acquisition_same_family_history",
        "cross_range_transfer_evaluated": False,
        "minimum_replicated_cycles": _MIN_REPLICATED_CYCLES,
        "status": status,
        "cross_cycle_probe_overlap_count": cross_cycle_overlap_count,
        "replication_input_sets_disjoint": input_sets_disjoint,
        "cycles": cycles,
        "plan_verification": {
            **model_verification,
            **implementation_verification,
        },
        "chain_verification": {
            "append_only_history_chain_verified": True,
            "seed_boundary_chain_verified": True,
            "all_planned_cycles_completed": True,
        },
        "learning_established": False,
        "causal_claim_made": False,
        "performance_improvement_established": False,
        "authority_granted": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--cycle-root", type=Path, action="append",
        required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = classify(plan_path=args.plan, cycle_roots=args.cycle_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "schema_version", "analysis_timing", "campaign_id",
        "campaign_plan_digest", "status", "learning_established",
        "causal_claim_made", "performance_improvement_established")},
        sort_keys=True))


if __name__ == "__main__":
    main()


