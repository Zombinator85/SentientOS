#!/usr/bin/env python3
"""Reconstruct one historical-examples pair score from its private journal."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore,
)
from work.historical_examples_intervention import (
    HistoricalExamplesPairJournal, _digest,
    verify_historical_examples_arm_receipt,
)
from sentientos.governed_local_model_invocation import validate_receipt


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("independent_score_duplicate_output_key")
        value[key] = item
    return value


def _schema_item_types(schema: Any) -> set[str]:
    if not isinstance(schema, Mapping):
        return set()
    variants = schema.get("anyOf")
    rows = variants if isinstance(variants, list) else [schema]
    types: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            return set()
        item_type = row.get("type")
        if isinstance(item_type, str):
            types.add(item_type)
        elif (isinstance(item_type, list)
                and all(isinstance(value, str) for value in item_type)):
            types.update(item_type)
        else:
            return set()
    return types


def _independent_outcomes(*, journal: HistoricalExamplesPairJournal,
        protocol: Mapping[str, Any], score: Mapping[str, Any],
        states: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Re-score archived outputs without calling the runtime scoring function."""
    arms = ("examples_included", "examples_omitted")
    task = journal.load_task_for_protocol(
        protocol_digest=protocol["protocol_digest"])
    descriptor, specification = task.public_descriptor(), task.specification()
    inputs = descriptor.get("probe_inputs")
    probes = protocol.get("probe_binding_digests")
    multiplier, offset = specification.get("multiplier"), specification.get("offset")
    if (not isinstance(inputs, (list, tuple)) or not inputs
            or any(type(value) is not int for value in inputs)
            or type(multiplier) is not int or type(offset) is not int
            or not isinstance(probes, list) or len(probes) != len(inputs)
            or descriptor.get("task_digest") != protocol.get("task_digest")):
        raise ValueError("independent_score_private_task_binding_invalid")
    answers: dict[str, int] = {}
    for index, probe_input in enumerate(inputs):
        digest = _canonical_digest({"schema_version":
            "sentientos.objective_probe_binding:v1",
            "task_digest": descriptor["task_digest"],
            "probe_index": index, "probe_input": probe_input})
        if probes[index] != digest:
            raise ValueError("independent_score_probe_order_mismatch")
        answers[digest] = multiplier * probe_input + offset
    if (_canonical_digest(answers) != protocol.get("answer_key_digest")
            or score.get("answer_key_digest") != _canonical_digest(answers)):
        raise ValueError("independent_score_answer_key_binding_mismatch")

    bindings = score.get("invocation_receipt_bindings")
    if not isinstance(bindings, Mapping) or set(bindings) != set(arms):
        raise ValueError("independent_score_receipt_roster_invalid")
    per_arm: dict[str, list[dict[str, Any]]] = {}
    correct = {arm: 0 for arm in arms}
    answered = {arm: 0 for arm in arms}
    brier_sum = {arm: 0 for arm in arms}
    confidence_count = {arm: 0 for arm in arms}
    receipt_digests: dict[str, str] = {}
    for arm in arms:
        state = states[arm]
        receipt, receipt_binding = state.get("receipt"), bindings[arm]
        if (state.get("status") != "completed"
                or not isinstance(receipt, Mapping)
                or not isinstance(receipt_binding, Mapping)):
            raise ValueError("independent_score_receipt_missing:" + arm)
        valid, reasons = validate_receipt(receipt)
        if not valid:
            raise ValueError("independent_score_receipt_invalid:" + arm + ":" +
                ",".join(reasons))
        reconstructed_binding = verify_historical_examples_arm_receipt(
            protocol=protocol, arm=arm, receipt=receipt)
        if dict(receipt_binding) != reconstructed_binding:
            raise ValueError("independent_score_receipt_binding_mismatch:" + arm)
        if dict(bindings[arm]) != reconstructed_binding:
            raise ValueError("independent_score_score_binding_mismatch:" + arm)
        request = receipt.get("request")
        schema = request.get("structured_output_schema")
        props = schema.get("properties") if isinstance(schema, Mapping) else None
        required = schema.get("required") if isinstance(schema, Mapping) else None
        if (not isinstance(schema, Mapping)
                or schema.get("type") != "object"
                or schema.get("additionalProperties") is not False
                or not isinstance(props, Mapping) or not isinstance(required, list)
                or set(required) != set(props)
                or set(props) not in ({"answers"},
                    {"answers", "confidence_basis_points"})):
            raise ValueError("independent_score_output_schema_invalid:" + arm)
        answer_schema = props.get("answers")
        item_schema = (answer_schema.get("items")
            if isinstance(answer_schema, Mapping) else None)
        item_types = _schema_item_types(item_schema)
        if (not isinstance(answer_schema, Mapping)
                or answer_schema.get("type") != "array"
                or answer_schema.get("minItems") != len(probes)
                or answer_schema.get("maxItems") != len(probes)
                or "integer" not in item_types
                or item_types - {"integer", "null"}):
            raise ValueError("independent_score_answer_schema_invalid:" + arm)
        try:
            decoded = json.loads(receipt["output_text"],
                object_pairs_hook=_unique_json_object,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError("nonstandard_json:" + value)))
        except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("independent_score_output_invalid:" + arm) from exc
        if not isinstance(decoded, Mapping) or set(decoded) != set(props):
            raise ValueError("independent_score_output_shape_invalid:" + arm)
        predictions = decoded.get("answers")
        allow_null = "null" in item_types
        if (not isinstance(predictions, list) or len(predictions) != len(probes)
                or any((value is None and not allow_null)
                    or (value is not None and type(value) is not int)
                    for value in predictions)):
            raise ValueError("independent_score_predictions_invalid:" + arm)
        confidences: list[int | None] = [None] * len(probes)
        if "confidence_basis_points" in props:
            confidences = decoded.get("confidence_basis_points")
            confidence_schema = props.get("confidence_basis_points")
            confidence_items = (confidence_schema.get("items")
                if isinstance(confidence_schema, Mapping) else None)
            confidence_variants = (confidence_items.get("anyOf")
                if isinstance(confidence_items, Mapping) else None)
            confidence_types = _schema_item_types(confidence_items)
            if (not isinstance(confidence_schema, Mapping)
                    or confidence_schema.get("type") != "array"
                    or confidence_schema.get("minItems") != len(probes)
                    or confidence_schema.get("maxItems") != len(probes)
                    or not isinstance(confidence_variants, list)
                    or "integer" not in confidence_types
                    or confidence_types - {"integer", "null"}
                    or not any(isinstance(row, Mapping)
                        and row.get("type") == "integer"
                        and row.get("minimum") == 0
                        and row.get("maximum") == 10000
                        for row in confidence_variants)
                    or ("null" in item_types) !=
                        ("null" in confidence_types)):
                raise ValueError("independent_score_confidence_schema_invalid:" + arm)
            if (not isinstance(confidences, list) or len(confidences) != len(probes)
                    or any(value is not None and (type(value) is not int
                        or not 0 <= value <= 10000) for value in confidences)
                    or any((prediction is None) != (confidence is None)
                        for prediction, confidence in
                            zip(predictions, confidences, strict=True))):
                raise ValueError("independent_score_confidence_invalid:" + arm)
        rows: list[dict[str, Any]] = []
        for probe, prediction, confidence in zip(
                probes, predictions, confidences, strict=True):
            is_correct = prediction is not None and prediction == answers[probe]
            row = {"probe_binding_digest": probe,
                "outcome": ("abstained" if prediction is None else
                    "correct" if is_correct else "incorrect")}
            correct[arm] += int(is_correct)
            answered[arm] += int(prediction is not None)
            if confidence is not None:
                error = (confidence - (10000 if is_correct else 0)) ** 2
                row["brier_squared_error_basis_points_squared"] = error
                brier_sum[arm] += error
                confidence_count[arm] += 1
            rows.append(row)
        per_arm[arm] = rows
        receipt_digests[arm] = str(receipt.get("receipt_digest"))
    paired = [{"probe_binding_digest": probe,
        "examples_included": per_arm["examples_included"][index]["outcome"],
        "examples_omitted": per_arm["examples_omitted"][index]["outcome"]}
        for index, probe in enumerate(probes)]
    recomputed = {"outcomes_by_arm": per_arm,
        "paired_probe_outcomes": paired, "correct_counts": correct,
        "answered_counts": answered,
        "coverage_basis_points": {arm: answered[arm] * 10000 // len(probes)
            for arm in arms},
        "confidence_brier_squared_error_sums": brier_sum,
        "confidence_scored_counts": confidence_count}
    if any(score.get(key) != value for key, value in recomputed.items()):
        raise ValueError("independent_score_outcomes_disagree")
    return {"outcomes": recomputed, "receipt_digests": receipt_digests}


def verify_pair_score(*, journal_root: Path,
        protocol_digest: str) -> dict[str, object]:
    journal = HistoricalExamplesPairJournal(
        store=DevelopmentalExperimentStore(journal_root))
    protocol = journal.load_protocol(protocol_digest=protocol_digest)
    score_event = journal._load_event(protocol_digest=protocol_digest,
        arm="examples_included", event="score")
    if (not isinstance(score_event, Mapping)
            or score_event.get("schema_version") !=
                "sentientos.historical_examples_pair_score:v1"
            or score_event.get("protocol_digest") != protocol_digest
            or score_event.get("authority") is not False
            or not isinstance(score_event.get("score"), Mapping)):
        raise ValueError("independent_score_immutable_event_invalid")
    score = dict(score_event["score"])
    score_body = {key: value for key, value in score.items()
        if key != "score_digest"}
    if (score.get("schema_version") !=
            "sentientos.historical_examples_intervention_score:v2"
            or score.get("protocol_digest") != protocol_digest
            or score.get("score_digest") != _canonical_digest(score_body)):
        raise ValueError("independent_score_artifact_digest_invalid")
    states_by_arm = {arm: journal.arm_state(
        protocol_digest=protocol_digest, arm=arm)
        for arm in protocol["conditions"]}
    states = list(states_by_arm.values())
    inventories = [state.get("runtime_history_inventory") for state in states]
    if (not inventories or any(not isinstance(value, dict)
            for value in inventories)
            or len({value.get("pair_baseline_record_set_digest")
                for value in inventories if isinstance(value, dict)}) != 1
            or len({value.get("runtime_record_count")
                for value in inventories if isinstance(value, dict)}) != 1):
        raise ValueError("historical_examples_pair_history_inventory_mismatch")
    if (len({value.get("pair_baseline_receipt_set_digest")
            for value in inventories if isinstance(value, dict)}) != 1
            or len({value.get("runtime_receipt_count")
                for value in inventories if isinstance(value, dict)}) != 1
            or any(value.get("selected_record_receipts_verified") is not True
                for value in inventories if isinstance(value, dict))):
        raise ValueError("historical_examples_pair_receipt_inventory_mismatch")
    inventory = inventories[0]
    independent = _independent_outcomes(journal=journal, protocol=protocol,
        score=score, states=states_by_arm)
    scorer_implementation_digest = "sha256:" + hashlib.sha256(
        Path(__file__).read_bytes()).hexdigest()
    semantic = {"schema_version":
            "sentientos.historical_examples_pair_score_verification:v2",
        "protocol_digest": protocol["protocol_digest"],
        "score_digest": score["score_digest"],
        "probe_count": score["probe_count"],
        "runtime_history_record_count": inventory["runtime_record_count"],
        "runtime_history_record_set_digest":
            inventory["pair_baseline_record_set_digest"],
        "runtime_history_receipt_count": inventory["runtime_receipt_count"],
        "runtime_history_receipt_set_digest":
            inventory["pair_baseline_receipt_set_digest"],
        "runtime_history_receipt_record_links_verified": True,
        "selected_history_record_receipts_verified": True,
        "correct_counts": score["correct_counts"],
        "independent_recomputed_correct_counts": independent[
            "outcomes"]["correct_counts"],
        "independent_recomputed_outcomes_digest": _canonical_digest(
            independent["outcomes"]),
        "independent_receipt_digests": independent["receipt_digests"],
        "independent_scorer_implementation_digest":
            scorer_implementation_digest,
        "scoring_reconstructed_from_archived_receipts": True,
        "private_answer_key_reconstructed": True,
        "independent_scorer_attested": True,
        "learning_established": False, "authority": False}
    return {**semantic, "verification_digest": _digest(semantic)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal-root", type=Path, required=True)
    parser.add_argument("--protocol-digest", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify_pair_score(journal_root=args.journal_root,
        protocol_digest=args.protocol_digest)
    encoded = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
        print(json.dumps({"verification_path": str(args.output),
            "protocol_digest": report["protocol_digest"],
            "score_digest": report["score_digest"],
            "verification_digest": report["verification_digest"],
            "scoring_reconstructed_from_archived_receipts": True,
            "independent_scorer_attested": report[
                "independent_scorer_attested"],
            "learning_established": False}, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
