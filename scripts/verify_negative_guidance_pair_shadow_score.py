"""Recompute negative-guidance pair metrics from persisted outputs.

This is a separately implemented shadow scorer. It is a reproducibility check,
not an independent scorer attestation: it reads the same private task and
receipt custody as the pair coordinator and writes no raw model outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore,
)
from work.historical_examples_intervention import HistoricalExamplesPairJournal
from work.negative_guidance_intervention import (
    ARMS,
    NegativeGuidancePairJournal,
)


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _answer_key(task: Any, protocol: Mapping[str, Any]) -> tuple[list[int], dict[str, int]]:
    descriptor = task.public_descriptor()
    specification = task.specification()
    probes = descriptor.get("probe_inputs")
    multiplier = specification.get("multiplier")
    offset = specification.get("offset")
    task_digest = descriptor.get("task_digest")
    if (not isinstance(probes, list) or not probes
            or any(type(value) is not int for value in probes)
            or type(multiplier) is not int or type(offset) is not int
            or task_digest != protocol.get("task_digest")
            or len(probes) != len(protocol.get("probe_binding_digests", ()))):
        raise ValueError("shadow_score_private_task_binding_invalid")
    answer_key: dict[str, int] = {}
    for index, probe in enumerate(probes):
        binding = {"schema_version": "sentientos.objective_probe_binding:v1",
            "task_digest": task_digest, "probe_index": index,
            "probe_input": probe}
        binding_digest = _digest(binding)
        if binding_digest != protocol["probe_binding_digests"][index]:
            raise ValueError("shadow_score_probe_binding_mismatch")
        answer_key[binding_digest] = multiplier * probe + offset
    if _digest(answer_key) != protocol.get("answer_key_digest"):
        raise ValueError("shadow_score_answer_key_commitment_mismatch")
    return probes, answer_key


def _score_arm(*, arm: str, receipt: Mapping[str, Any],
        protocol: Mapping[str, Any], probes: list[int],
        answer_key: Mapping[str, int]) -> tuple[list[dict[str, Any]], int, int, int, int]:
    request = receipt.get("request")
    if (not isinstance(request, Mapping)
            or request.get("prompt_digest") !=
                protocol["invocation_prompt_digests"][arm].removeprefix("sha256:")):
        raise ValueError("shadow_score_receipt_prompt_binding_mismatch:" + arm)
    raw = receipt.get("output_text")
    if not isinstance(raw, str):
        raise ValueError("shadow_score_receipt_output_missing:" + arm)
    decoded = json.loads(raw)
    answers = decoded.get("answers") if isinstance(decoded, Mapping) else None
    confidence = (decoded.get("confidence_basis_points")
        if isinstance(decoded, Mapping) else None)
    if (not isinstance(answers, list) or len(answers) != len(probes)
            or not isinstance(confidence, list) or len(confidence) != len(probes)):
        raise ValueError("shadow_score_output_shape_invalid:" + arm)
    rows: list[dict[str, Any]] = []
    correct = answered = brier_sum = brier_count = 0
    for index, (probe, answer, certainty) in enumerate(
            zip(probes, answers, confidence, strict=True)):
        binding_digest = protocol["probe_binding_digests"][index]
        if answer is None:
            if certainty is not None:
                raise ValueError("shadow_score_abstention_confidence_invalid:" + arm)
            outcome = "abstained"
        else:
            if type(answer) is not int or type(certainty) is not int or not 0 <= certainty <= 10_000:
                raise ValueError("shadow_score_answer_or_confidence_invalid:" + arm)
            outcome = "correct" if answer == answer_key[binding_digest] else "incorrect"
            answered += 1
            correct += outcome == "correct"
            brier_sum += (certainty - (10_000 if outcome == "correct" else 0)) ** 2
            brier_count += 1
        rows.append({"probe_binding_digest": binding_digest,
            "outcome": outcome})
    return rows, correct, answered, brier_sum, brier_count


def _mcnemar_fraction(present_only: int, omitted_only: int) -> dict[str, int]:
    discordant = present_only + omitted_only
    if not discordant:
        return {"numerator": 1, "denominator": 1}
    tail = sum(math.comb(discordant, index)
        for index in range(min(present_only, omitted_only) + 1))
    numerator = min(2 * tail, 2 ** discordant)
    denominator = 2 ** discordant
    divisor = math.gcd(numerator, denominator)
    return {"numerator": numerator // divisor,
        "denominator": denominator // divisor}


def shadow_score(*, journal_root: Path, protocol_digest: str) -> dict[str, Any]:
    store = DevelopmentalExperimentStore(journal_root)
    pair_journal = NegativeGuidancePairJournal(store=store)
    protocol = pair_journal.load_protocol(protocol_digest)
    historical_journal = HistoricalExamplesPairJournal(store=store)
    task = historical_journal.load_private_task_plan(
        task_digest=protocol["task_digest"],
        task_plan_digest=protocol["private_task_plan_digest"])
    probes, answer_key = _answer_key(task, protocol)
    rows_by_arm: dict[str, list[dict[str, Any]]] = {}
    correct_by_arm: dict[str, int] = {}
    answered_by_arm: dict[str, int] = {}
    brier_sums: dict[str, int] = {}
    brier_counts: dict[str, int] = {}
    for arm in ARMS:
        state = pair_journal.arm_state(protocol_digest=protocol_digest, arm=arm)
        if state.get("status") != "completed" or not isinstance(
                state.get("receipt"), Mapping):
            raise ValueError("shadow_score_pair_arm_incomplete:" + arm)
        rows, correct, answered, brier_sum, brier_count = _score_arm(
            arm=arm, receipt=state["receipt"], protocol=protocol,
            probes=probes, answer_key=answer_key)
        rows_by_arm[arm] = rows
        correct_by_arm[arm] = correct
        answered_by_arm[arm] = answered
        brier_sums[arm] = brier_sum
        brier_counts[arm] = brier_count
    transitions = {"both_correct": 0, "present_only_correct": 0,
        "omitted_only_correct": 0, "neither_correct": 0}
    paired_rows = []
    for index, probe_digest in enumerate(protocol["probe_binding_digests"]):
        present = rows_by_arm[ARMS[0]][index]["outcome"] == "correct"
        omitted = rows_by_arm[ARMS[1]][index]["outcome"] == "correct"
        label = ("both_correct" if present and omitted else
            "present_only_correct" if present else
            "omitted_only_correct" if omitted else "neither_correct")
        transitions[label] += 1
        paired_rows.append({"probe_binding_digest": probe_digest,
            ARMS[0]: rows_by_arm[ARMS[0]][index]["outcome"],
            ARMS[1]: rows_by_arm[ARMS[1]][index]["outcome"]})
    shadow = {"schema_version": "sentientos.negative_guidance_shadow_score:v1",
        "protocol_digest": protocol_digest,
        "answer_key_digest": protocol["answer_key_digest"],
        "probe_count": len(probes),
        "correct_counts": correct_by_arm,
        "answered_counts": answered_by_arm,
        "coverage_basis_points": {arm: answered_by_arm[arm] * 10_000 // len(probes)
            for arm in ARMS},
        "confidence_brier_squared_error_sums": brier_sums,
        "confidence_scored_counts": brier_counts,
        "paired_correctness_transition_counts": transitions,
        "paired_probe_outcomes": paired_rows,
        "discordant_probe_count": (transitions["present_only_correct"]
            + transitions["omitted_only_correct"]),
        "omitted_minus_present_correct_count": (
            correct_by_arm[ARMS[1]] - correct_by_arm[ARMS[0]]),
        "exact_two_sided_mcnemar_p_value_fraction": _mcnemar_fraction(
            transitions["present_only_correct"],
            transitions["omitted_only_correct"]),
        "scoring_implementation": "separate_deterministic_shadow_reimplementation",
        "independent_scorer_attested": False,
        "learning_established": False,
        "authority": False}
    shadow["shadow_score_digest"] = _digest(shadow)
    owner_score = pair_journal.load_score(protocol_digest=protocol_digest)
    compare_fields = ("correct_counts", "answered_counts", "coverage_basis_points",
        "confidence_brier_squared_error_sums", "confidence_scored_counts",
        "paired_correctness_transition_counts", "paired_probe_outcomes",
        "discordant_probe_count", "omitted_minus_present_correct_count",
        "exact_two_sided_mcnemar_p_value_fraction")
    mismatches = [field for field in compare_fields
        if shadow[field] != owner_score.get(field)]
    if mismatches:
        raise ValueError("shadow_score_disagrees_with_owner:" + ",".join(mismatches))
    return {**shadow,
        "owner_score_digest": owner_score.get("score_digest"),
        "owner_score_recomputed_match": True,
        "owner_score_mismatch_fields": [],
        "raw_prompts_and_model_outputs_excluded": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal-root", required=True, type=Path)
    parser.add_argument("--protocol-digest", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = shadow_score(journal_root=args.journal_root,
        protocol_digest=args.protocol_digest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True,
            ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print(json.dumps({key: result[key] for key in (
        "schema_version", "protocol_digest", "shadow_score_digest",
        "owner_score_digest", "owner_score_recomputed_match",
        "independent_scorer_attested", "correct_counts", "answered_counts",
        "coverage_basis_points")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
