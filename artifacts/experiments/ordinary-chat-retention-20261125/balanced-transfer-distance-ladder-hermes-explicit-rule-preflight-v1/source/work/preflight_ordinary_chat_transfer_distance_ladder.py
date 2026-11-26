"""Preflight matched ordinary-chat transfer probes across increasing distances."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from sentientos.developmental_model_replacement_experiment import (
    FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS,
    FIXED_OBJECTIVE_TASK_FAMILY_PROBE_RANGES,
    ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
)
from sentientos.local_model_authority import digest_payload
from sentientos.resident_developmental_cognition import _ordinary_chat_integer_experiences
from work.preflight_ordinary_chat_retention import (
    PARAPHRASE_PROBES, PROBES, _owner, _read_receipt, _service_request,
    _source_kinds_from_history,
)
from work.preflight_sibling_chat_histories import (
    CYCLES, ROOT, TARGET, admitted_boundary, archive, read,
)


SOURCE_REPORT = ROOT / "artifacts/experiments/ordinary-chat-retention-20261125/later-session-novel-transfer-preflight-v3.json"
PILOT = ROOT / "artifacts/experiments/identity-neutral-journal-recovery-20261125-wide-power-v1/strategy_inclusion_cpu_preflight_v11.json"
TASK_FAMILY = ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY
TIERS = {
    "near": (1001, 1013, 1097),
    "middle": (5003, 7777, 10007),
    "far": (60013, 200003, 900001),
}
QUESTION_TEMPLATE = (
    "Earlier we practiced a number prediction exercise. What outputs should go "
    "with these inputs: {inputs}? If the history does not support a prediction, "
    "use null for that answer. Reply only as one JSON object with an answers "
    "array, one integer or null for each input in order.")
ARMS = ("history", "empty")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _answer_commitment(inputs: tuple[int, ...]) -> str:
    mapping = FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS[TASK_FAMILY]
    return "sha256:" + digest_payload({
        "task_family_id": TASK_FAMILY,
        "probe_inputs": list(inputs),
        "expected_outputs": [mapping[0] * item + mapping[1] for item in inputs],
    })


def build_report(cycles_root: Path) -> dict[str, Any]:
    cycles = cycles_root
    target_cycle = cycles / ("rootless-cognition-cycle-" + TARGET)
    parent_cycle = cycles / ("rootless-cognition-cycle-" + CYCLES["parent"])
    prior = read(SOURCE_REPORT)
    request = _read_receipt(target_cycle)[1]["request"]
    identity = request["active_model_identity"]
    ranges = FIXED_OBJECTIVE_TASK_FAMILY_PROBE_RANGES[TASK_FAMILY]
    mapping = FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS[TASK_FAMILY]
    if (mapping != FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS[
            "rootless_integer_affine_transfer_low_range_v6"]
            or mapping != FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS[
                "rootless_integer_affine_transfer_wide_range_v7"]):
        raise ValueError("source and novel task families do not share the preregistered mapping")
    all_inputs = [value for values in TIERS.values() for value in values]
    if (len(all_inputs) != len(set(all_inputs))
            or any(not any(lower <= value <= upper for lower, upper in ranges)
                   for value in all_inputs)):
        raise ValueError("distance ladder probes are duplicated or outside the novel task family")

    pilot = read(PILOT)
    pilot_inputs = set(pilot["owner_arm_protocols"]["strategy_included"]
        ["objective_task_descriptor"]["probe_inputs"])
    reference_inputs = pilot_inputs | set(PROBES) | set(PARAPHRASE_PROBES)
    prior_inputs = set(prior["novel_transfer_protocol"]["probe_inputs"])
    overlaps = sorted(set(all_inputs) & (reference_inputs | prior_inputs))
    if overlaps:
        raise ValueError(f"distance ladder overlaps prior probes: {overlaps}")

    with tempfile.TemporaryDirectory(prefix="sentientos-transfer-distance-ladder-") as temp:
        root = Path(temp)
        parent_root = root / "history" / "resident-cognition"
        _, _, _, _, _ = archive(parent_cycle, parent_root)
        kinds = _source_kinds_from_history(parent_root / "history")
        owner = _owner(parent_root, kinds, parent_cycle, request)
        baseline_arm = prior["arms"]["parent"]
        if admitted_boundary(owner.writeback.inspect_completed_records()) != baseline_arm[
                "admitted_boundary_digest"]:
            raise ValueError("parent history differs from the frozen sibling-history report")
        historical_inputs: set[int] = set()
        for record, _ in owner.writeback.inspect_completed_records():
            for experience in _ordinary_chat_integer_experiences(record.candidate):
                for example in experience["examples"]:
                    probe_input = example.get("probe_input")
                    if type(probe_input) is not int:
                        raise ValueError("parent history contains an invalid integer probe")
                    historical_inputs.add(probe_input)
        history_overlap = sorted(set(all_inputs) & historical_inputs)
        if history_overlap:
            raise ValueError(f"distance ladder reuses parent-history probes: {history_overlap}")

        empty_root = root / "empty" / "resident-cognition"
        empty_root.mkdir(parents=True)
        empty_owner = _owner(empty_root, kinds, target_cycle, request)
        expected_evidence = prior["questions"]["novel_range_transfer"]["captures"]["parent"][
            "prompt_score_evidence"]
        if len(expected_evidence) != 1 or len(expected_evidence[0]["examples"]) != 3:
            raise ValueError("parent history does not contain the frozen three-example support record")
        support_rows = expected_evidence[0]["examples"]
        if any(row.get("abstained") is not False
                or row.get("evaluator_correct") is not True
                or row.get("observed_answer") != mapping[0] * row["probe_input"] + mapping[1]
                for row in support_rows):
            raise ValueError("parent support record does not consistently demonstrate the fixed mapping")

        tiers: dict[str, Any] = {}
        normalized_bases: list[str] = []
        for tier, probes in TIERS.items():
            question = QUESTION_TEMPLATE.format(inputs=", ".join(map(str, probes)))
            captures: dict[str, Any] = {}
            bases: dict[str, str] = {}
            for arm, current_owner in (("history", owner), ("empty", empty_owner)):
                base, capture = _service_request(current_owner,
                    root / "chats" / tier / arm, identity, question)
                bases[arm] = base
                captures[arm] = capture
            if (bases["history"] != bases["empty"]
                    or captures["empty"]["history_block_digest"] is not None
                    or captures["empty"]["prompt_score_evidence"]):
                raise ValueError(f"{tier} history and empty prompts differ outside history")
            actual = captures["history"]["prompt_score_evidence"]
            if actual != expected_evidence:
                raise ValueError(f"{tier} query did not retrieve the exact frozen support record")
            normalized = bases["history"].replace(", ".join(map(str, probes)), "[PROBES]")
            normalized_bases.append(normalized)
            tiers[tier] = {
                "probe_inputs": list(probes),
                "input_distance_from_largest_source_example": {
                    "minimum": min(probes) - max(row["probe_input"] for row in expected_evidence[0]["examples"]),
                    "maximum": max(probes) - max(row["probe_input"] for row in expected_evidence[0]["examples"]),
                },
                "answer_key_commitment": _answer_commitment(probes),
                "question": question,
                "captures": captures,
            }
        if len(set(normalized_bases)) != 1:
            raise ValueError("distance tiers differ outside the probe values")

        source_files = (
            "work/preflight_ordinary_chat_transfer_distance_ladder.py",
            "work/preflight_ordinary_chat_retention.py",
            "work/preflight_sibling_chat_histories.py",
            "sentientos/chat_service.py",
            "sentientos/conversation_session.py",
            "sentientos/resident_developmental_cognition.py",
            "sentientos/developmental_model_replacement_experiment.py",
        )
        return {
            "schema": "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v1",
            "source_report_sha256": _sha(SOURCE_REPORT.read_bytes()),
            "task_family_id": TASK_FAMILY,
            "source_task_family_ids": [
                "rootless_integer_affine_transfer_low_range_v6",
                "rootless_integer_affine_transfer_wide_range_v7",
            ],
            "arms": list(ARMS),
            "tiers": tiers,
            "probe_inputs_disjoint_from_history_and_prior_probes": True,
            "historical_probe_overlap": history_overlap,
            "all_tier_prompts_match_outside_probe_values": True,
            "fixed_mapping_shared_by_source_and_novel_task_families": True,
            "support_record_id": expected_evidence[0]["record_id"],
            "support_task_family_id": expected_evidence[0]["task_family_id"],
            "support_rows": support_rows,
            "support_rows_all_correct_and_mapping_consistent": True,
            "answer_values_withheld": True,
            "scoring": "Exact integer equality per probe, fixed three-probe denominator per tier and arm.",
            "primary_outcome": "History-minus-empty exact-answer count within each distance tier.",
            "secondary_outcome": "Strict JSON-only format validity, reported separately from answer accuracy.",
            "order_policy": "Fresh sessions; deterministic model settings and fixed tier/arm order must be bound by the later model execution plan.",
            "implementation_sha256": {name: _sha((ROOT / name).read_bytes()) for name in source_files},
            "inference_performed": False,
            "model_bound_execution_plan_created": False,
            "learning_established": False,
            "authority": False,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cycles_root", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    report = build_report(args.cycles_root)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.verify_report is not None:
        if json.loads(args.verify_report.read_text(encoding="utf-8")) != report:
            raise ValueError("saved distance-ladder preflight differs from reconstructed evidence")
        print("distance_ladder_preflight_reconstructed",
              _sha(args.verify_report.read_bytes()), flush=True)
    elif args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        parser.error("provide output or --verify-report")


if __name__ == "__main__":
    main()
