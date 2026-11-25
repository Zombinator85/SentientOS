"""Summarize answer/abstention changes across a completed negative-guidance pair.

This is an exploratory behavior description. It does not rescore correctness,
expose answer values, or establish learning or a causal effect.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore,
)
from work.negative_guidance_intervention import (
    ARMS,
    NegativeGuidancePairJournal,
)

_RELATIONS = (
    "both_abstained", "present_only_answered", "omitted_only_answered",
    "same_answer", "different_answers")


def analyze_pair(*, journal_root: Path, protocol_digest: str,
        task_generation_seed: int) -> dict[str, Any]:
    if type(task_generation_seed) is not int or task_generation_seed < 0:
        raise ValueError("response_dynamics_task_seed_invalid")
    store = DevelopmentalExperimentStore(journal_root)
    journal = NegativeGuidancePairJournal(store=store)
    protocol = journal.load_protocol(protocol_digest)
    outputs: dict[str, list[int | None]] = {}
    arm_bindings: dict[str, dict[str, str]] = {}
    for arm in ARMS:
        state = journal.arm_state(protocol_digest=protocol_digest, arm=arm)
        receipt = state.get("receipt")
        if state.get("status") != "completed" or not isinstance(receipt, Mapping):
            raise ValueError("response_dynamics_pair_arm_incomplete:" + arm)
        request = receipt.get("request")
        if not isinstance(request, Mapping):
            raise ValueError("response_dynamics_request_missing:" + arm)
        decoded = json.loads(receipt["output_text"])
        answers = decoded.get("answers") if isinstance(decoded, Mapping) else None
        if (not isinstance(answers, list)
                or len(answers) != len(protocol["probe_binding_digests"])
                or any(value is not None and type(value) is not int
                    for value in answers)):
            raise ValueError("response_dynamics_answer_shape_invalid:" + arm)
        outputs[arm] = answers
        arm_bindings[arm] = {"receipt_id": receipt["receipt_id"],
            "receipt_digest": receipt["receipt_digest"],
            "request_digest": request["request_digest"],
            "prompt_digest": "sha256:" + request["prompt_digest"]}
    relation_counts = Counter()
    probe_relations = []
    for index, probe_digest in enumerate(protocol["probe_binding_digests"]):
        present = outputs[ARMS[0]][index]
        omitted = outputs[ARMS[1]][index]
        if present is None and omitted is None:
            relation = "both_abstained"
        elif present is None:
            relation = "omitted_only_answered"
        elif omitted is None:
            relation = "present_only_answered"
        elif present == omitted:
            relation = "same_answer"
        else:
            relation = "different_answers"
        relation_counts[relation] += 1
        probe_relations.append({"probe_binding_digest": probe_digest,
            "response_relation": relation})
    semantic = {"schema_version": "sentientos.negative_guidance_response_dynamics:v1",
        "task_generation_seed": task_generation_seed,
        "task_digest": protocol["task_digest"],
        "protocol_digest": protocol_digest,
        "probe_count": len(probe_relations),
        "arm_receipt_bindings": arm_bindings,
        "response_relation_counts": {name: relation_counts[name]
            for name in _RELATIONS},
        "changed_answer_or_abstention_count": sum(relation_counts[name]
            for name in ("present_only_answered", "omitted_only_answered",
                "different_answers")),
        "per_probe_relations": probe_relations,
        "analysis_posture": "exploratory_posthoc_response_change_summary",
        "primary_correctness_score_replaced": False,
        "answer_values_excluded": True,
        "raw_prompts_and_model_outputs_excluded": True,
        "learning_established": False,
        "causal_effect_established": False,
        "authority": False}
    return semantic


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal-root", required=True, type=Path)
    parser.add_argument("--pair", required=True, action="append",
        metavar="SEED:PROTOCOL_DIGEST",
        help="Repeat once per completed pair; digest includes sha256: prefix")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    pairs = []
    for value in args.pair:
        seed_text, separator, digest = value.partition(":sha256:")
        if not separator or not seed_text.isdecimal():
            raise SystemExit("response_dynamics_pair_argument_invalid")
        pairs.append(analyze_pair(journal_root=args.journal_root,
            task_generation_seed=int(seed_text),
            protocol_digest="sha256:" + digest))
    report = {"schema_version":
            "sentientos.negative_guidance_response_dynamics_series:v1",
        "pairs": pairs,
        "aggregate_relation_counts": {name: sum(
            pair["response_relation_counts"][name] for pair in pairs)
            for name in _RELATIONS},
        "aggregate_changed_answer_or_abstention_count": sum(
            pair["changed_answer_or_abstention_count"] for pair in pairs),
        "analysis_posture": "exploratory_posthoc_secondary_outcome",
        "answer_values_excluded": True,
        "learning_established": False,
        "causal_effect_established": False,
        "authority": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, sort_keys=True,
            ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"schema_version": report["schema_version"],
        "pair_count": len(pairs),
        "aggregate_relation_counts": report["aggregate_relation_counts"],
        "aggregate_changed_answer_or_abstention_count":
            report["aggregate_changed_answer_or_abstention_count"],
        "causal_effect_established": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
