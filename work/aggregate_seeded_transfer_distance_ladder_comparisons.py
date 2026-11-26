"""Aggregate matched presentation comparisons across preregistered seeds."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


COMPARISON_SCHEMA = (
    "sentientos.ordinary_chat_transfer_distance_ladder_history_guidance_comparison:v1")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _required_true(report: dict[str, Any], fields: tuple[str, ...], path: Path) -> None:
    if any(report.get(field) is not True for field in fields):
        raise ValueError(f"{path} lacks a required matched-pair qualification")


def aggregate(comparisons: list[Path], output: Path) -> dict[str, Any]:
    if len(comparisons) < 2:
        raise ValueError("seeded aggregation requires at least two matched pairs")

    rows = []
    seen_seeds: set[int] = set()
    invariant_fields = (
        "model", "model_manifest_sha256", "model_content_sha256",
        "non_seed_generation_settings_sha256", "task_probes_and_order_sha256",
        "scored_support_sha256")
    invariant_values: dict[str, Any] = {}
    pair_qualifications = (
        "same_model_identity", "same_generation_and_gpu_settings", "same_seed",
        "same_task_probes_and_trial_order", "same_scored_history_evidence",
        "same_empty_prompts", "same_prompt_outside_history_block",
        "same_format_constraint", "history_example_presentation_changed",
        "history_prompt_block_changed")

    for path in comparisons:
        report = _read(path)
        if (report.get("schema") != COMPARISON_SCHEMA
                or report.get("learning_established") is not False
                or report.get("history_example_presentation") != {
                    "control": "structured_only", "treatment": "record_linked"}):
            raise ValueError(f"{path} is not a qualified structured-only/record-linked comparison")
        _required_true(report, pair_qualifications, path)
        seed = report.get("seed")
        if type(seed) is not int or seed in seen_seeds:
            raise ValueError(f"{path} has a missing or duplicate integer seed")
        seen_seeds.add(seed)
        for field in invariant_fields:
            value = report.get(field)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{path} lacks the cross-seed binding {field}")
            if field in invariant_values and invariant_values[field] != value:
                raise ValueError(f"cross-seed comparison changed {field}")
            invariant_values[field] = value

        exact = report.get("exact_answers", {})
        for arm in ("history", "empty"):
            for condition in ("control", "treatment"):
                pair = exact.get(arm, {}).get(condition)
                if (not isinstance(pair, list) or len(pair) != 2
                        or any(type(value) is not int for value in pair)
                        or pair[0] < 0 or pair[1] <= 0 or pair[0] > pair[1]):
                    raise ValueError(f"{path} has malformed exact-answer totals")
        format_totals = report.get("strict_json_valid_trials", {})
        for condition in ("control", "treatment"):
            pair = format_totals.get(condition)
            if (not isinstance(pair, list) or len(pair) != 2
                    or any(type(value) is not int for value in pair)
                    or pair[0] < 0 or pair[1] <= 0 or pair[0] > pair[1]):
                raise ValueError(f"{path} has malformed strict-format totals")

        history_control = exact["history"]["control"]
        history_treatment = exact["history"]["treatment"]
        empty_control = exact["empty"]["control"]
        empty_treatment = exact["empty"]["treatment"]
        tier_results = report.get("tier_results")
        if not isinstance(tier_results, dict) or not tier_results:
            raise ValueError(f"{path} has no tier-level outcomes")
        rows.append({
            "seed": seed,
            "comparison_sha256": _sha(path.read_bytes()),
            "plan_sha256": {"structured_only": report.get("control_plan_sha256"),
                            "record_linked": report.get("treatment_plan_sha256")},
            "history_correct": {"structured_only": history_control,
                                "record_linked": history_treatment},
            "empty_correct": {"structured_only": empty_control,
                              "record_linked": empty_treatment},
            "history_gain": history_treatment[0] - history_control[0],
            "empty_gain": empty_treatment[0] - empty_control[0],
            "strict_json_valid_trials": format_totals,
            "history_payload_changed": report.get("answer_payloads_unchanged") is False,
            "strict_json_validity_unchanged": report.get("strict_json_validity_unchanged"),
            "exact_accuracy_unchanged": report.get("exact_accuracy_unchanged"),
            "tier_results": tier_results,
        })

    rows.sort(key=lambda item: item["seed"])
    totals = {}
    for arm, key in (("history", "history_correct"), ("empty", "empty_correct")):
        structured = sum(row[key]["structured_only"][0] for row in rows)
        linked = sum(row[key]["record_linked"][0] for row in rows)
        denominator = sum(row[key]["structured_only"][1] for row in rows)
        if any(row[key]["record_linked"][1] != row[key]["structured_only"][1]
               for row in rows):
            raise ValueError(f"{arm} denominators differ across presentations or seeds")
        totals[arm] = {
            "structured_only": [structured, denominator],
            "record_linked": [linked, denominator],
            "record_linked_minus_structured_only": linked - structured,
        }

    format_totals = {}
    for condition in ("control", "treatment"):
        valid = sum(row["strict_json_valid_trials"][condition][0] for row in rows)
        denominator = sum(row["strict_json_valid_trials"][condition][1] for row in rows)
        format_totals[condition] = [valid, denominator]

    all_tiers = set(rows[0]["tier_results"])
    if any(set(row["tier_results"]) != all_tiers for row in rows):
        raise ValueError("tier set differs across seeds")
    tier_totals = {}
    for tier in sorted(all_tiers):
        tier_totals[tier] = {}
        for arm in ("history", "empty"):
            structured_count = linked_count = denominator = 0
            for row in rows:
                result = row["tier_results"][tier][arm]
                structured_count += result["control_correct"]
                linked_count += result["treatment_correct"]
                denominator += result["denominator"]
            tier_totals[tier][arm] = {
                "structured_only_correct": structured_count,
                "record_linked_correct": linked_count,
                "denominator": denominator,
                "record_linked_minus_structured_only": linked_count - structured_count,
            }

    gains = [row["seed"] for row in rows if row["history_gain"] > 0]
    losses = [row["seed"] for row in rows if row["history_gain"] < 0]
    unchanged = [row["seed"] for row in rows if row["history_gain"] == 0]
    report = {
        "schema": "sentientos.ordinary_chat_transfer_distance_ladder_seeded_aggregation:v1",
        "comparison_source_sha256": _sha(Path(__file__).read_bytes()),
        "comparison_count": len(rows),
        "seeds": [row["seed"] for row in rows],
        "cross_seed_invariants": invariant_values,
        "presentation": {"control": "structured_only", "treatment": "record_linked"},
        "matched_pairs": rows,
        "totals": totals,
        "strict_json_valid_trials": format_totals,
        "tier_totals": tier_totals,
        "history_accuracy_gain_seeds": gains,
        "history_accuracy_loss_seeds": losses,
        "history_accuracy_unchanged_seeds": unchanged,
        "history_payload_changed_pair_count": sum(row["history_payload_changed"] for row in rows),
        "strict_json_validity_changed_pair_count": sum(
            row["strict_json_validity_unchanged"] is False for row in rows),
        "learning_established": False,
        "interpretation": (
            f"Across {len(rows)} matched seeds ({', '.join(str(row['seed']) for row in rows)}), "
            f"record-linked rendering yielded {totals['history']['record_linked'][0]}/"
            f"{totals['history']['record_linked'][1]} exact history answers versus "
            f"{totals['history']['structured_only'][0]}/"
            f"{totals['history']['structured_only'][1]} with structured-only history. "
            f"History accuracy improved on {len(gains)} seed(s), worsened on {len(losses)}, "
            f"and was unchanged on {len(unchanged)}. This measures immediate responses to "
            "history presentation in one frozen task and model; it does not establish durable "
            "learning or general transfer."),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("comparisons", type=Path, nargs="+")
    args = parser.parse_args()
    result = aggregate(args.comparisons, args.output)
    print("seeded_comparison_aggregation_saved", result["comparison_count"],
          result["seeds"], flush=True)
