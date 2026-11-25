#!/usr/bin/env python3
"""Reconcile negative-guidance response dynamics with frozen scored outcomes.

This verifier reads only persisted JSON evidence. It does not load a model,
reopen invocation receipts, rescore answers, or establish causal learning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_RELATIONS = (
    "both_abstained", "present_only_answered", "omitted_only_answered",
    "same_answer", "different_answers")
_ARMS = ("negative_guidance_present", "negative_guidance_omitted")
_MAX_BYTES = 8 * 1024 * 1024


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("negative_guidance_series_duplicate_json_key")
        result[key] = value
    return result


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("negative_guidance_series_input_not_regular:" + str(path))
    raw = path.read_bytes()
    if len(raw) > _MAX_BYTES:
        raise ValueError("negative_guidance_series_input_oversize:" + str(path))
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("negative_guidance_series_nonstandard_json")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("negative_guidance_series_input_invalid:" + str(path)) from exc
    if not isinstance(value, dict):
        raise ValueError("negative_guidance_series_input_invalid:" + str(path))
    return value, raw


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _require_digest(value: Any, code: str) -> str:
    if (not isinstance(value, str) or len(value) != 71
            or not value.startswith("sha256:")
            or any(char not in "0123456789abcdef" for char in value[7:])):
        raise ValueError(code)
    return value


def _count_mapping(value: Any, names: tuple[str, ...], code: str
        ) -> dict[str, int]:
    if (not isinstance(value, Mapping) or set(value) != set(names)
            or any(type(value[name]) is not int or value[name] < 0
                for name in names)):
        raise ValueError(code)
    return {name: value[name] for name in names}


def _recompute_pair_answer_relations(*, journal_root: Path,
        protocol_digest: str, task_generation_seed: int,
        dynamics_pair: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute answer equality from verified journal receipts, without exporting answers."""
    from sentientos.developmental_history_intervention_experiment import (
        DevelopmentalExperimentStore,
    )
    from work.negative_guidance_intervention import (
        ARMS, NegativeGuidancePairJournal,
    )

    store = DevelopmentalExperimentStore(journal_root)
    journal = NegativeGuidancePairJournal(store=store)
    protocol = journal.load_protocol(protocol_digest)
    if protocol.get("task_digest") != dynamics_pair.get("task_digest"):
        raise ValueError("negative_guidance_series_journal_task_mismatch")
    probe_digests = protocol.get("probe_binding_digests")
    if not isinstance(probe_digests, list) or not probe_digests:
        raise ValueError("negative_guidance_series_journal_probe_bindings_invalid")

    outputs: dict[str, list[int | None]] = {}
    expected_receipt_bindings: dict[str, dict[str, str]] = {}
    for arm in ARMS:
        state = journal.arm_state(protocol_digest=protocol_digest, arm=arm)
        receipt = state.get("receipt")
        if state.get("status") != "completed" or not isinstance(receipt, Mapping):
            raise ValueError("negative_guidance_series_journal_arm_incomplete:" + arm)
        request = receipt.get("request")
        output_text = receipt.get("output_text")
        if not isinstance(request, Mapping) or not isinstance(output_text, str):
            raise ValueError("negative_guidance_series_journal_receipt_invalid:" + arm)
        try:
            decoded = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise ValueError("negative_guidance_series_journal_output_invalid:" + arm) from exc
        answers = decoded.get("answers") if isinstance(decoded, Mapping) else None
        if (not isinstance(answers, list) or len(answers) != len(probe_digests)
                or any(value is not None and type(value) is not int
                    for value in answers)):
            raise ValueError("negative_guidance_series_journal_answer_shape_invalid:" + arm)
        outputs[arm] = answers
        expected_receipt_bindings[arm] = {
            "receipt_id": str(receipt.get("receipt_id")),
            "receipt_digest": str(receipt.get("receipt_digest")),
            "request_digest": str(request.get("request_digest")),
            "prompt_digest": "sha256:" + str(request.get("prompt_digest")),
        }

    supplied_bindings = dynamics_pair.get("arm_receipt_bindings")
    if supplied_bindings != expected_receipt_bindings:
        raise ValueError("negative_guidance_series_journal_receipt_binding_mismatch")

    relations: dict[str, str] = {}
    for index, probe_digest in enumerate(probe_digests):
        present = outputs[ARMS[0]][index]
        omitted = outputs[ARMS[1]][index]
        relation = (
            "both_abstained" if present is None and omitted is None
            else "omitted_only_answered" if present is None
            else "present_only_answered" if omitted is None
            else "same_answer" if present == omitted
            else "different_answers"
        )
        relations[probe_digest] = relation

    reported = dynamics_pair.get("per_probe_relations")
    expected_rows = [
        {"probe_binding_digest": probe_digest,
            "response_relation": relations[probe_digest]}
        for probe_digest in probe_digests
    ]
    if reported != expected_rows:
        raise ValueError("negative_guidance_series_journal_answer_relation_mismatch")
    return {
        "same_answer_count": sum(value == "same_answer" for value in relations.values()),
        "different_answers_count": sum(value == "different_answers" for value in relations.values()),
        "receipt_bindings_verified": True,
        "probe_answer_relations_recomputed": True,
    }


def _verify_self_digest(value: Mapping[str, Any], field: str,
        code: str) -> str:
    supplied = _require_digest(value.get(field), code)
    semantic = {key: item for key, item in value.items() if key != field}
    if _digest(semantic) != supplied:
        raise ValueError(code)
    return supplied


def verify_series_analysis(*, plan: Mapping[str, Any],
        outcome: Mapping[str, Any], dynamics: Mapping[str, Any],
        analysis: Mapping[str, Any], dynamics_bytes: bytes,
        journal_root: Path | None = None) -> dict[str, Any]:
    """Verify cross-report identity, per-probe coverage, and score totals."""
    if (plan.get("schema_version") !=
            "sentientos.negative_guidance_replication_series_plan:v1"
            or outcome.get("schema_version") !=
                "sentientos.negative_guidance_replication_series_outcome:v1"
            or dynamics.get("schema_version") !=
                "sentientos.negative_guidance_response_dynamics_series:v1"
            or analysis.get("schema_version") !=
                "sentientos.negative_guidance_replication_series_analysis:v1"):
        raise ValueError("negative_guidance_series_schema_mismatch")

    plan_digest = _verify_self_digest(plan, "series_plan_digest",
        "negative_guidance_series_plan_digest_invalid")
    outcome_digest = _verify_self_digest(outcome, "outcome_digest",
        "negative_guidance_series_outcome_digest_invalid")
    analysis_digest = _verify_self_digest(analysis, "analysis_digest",
        "negative_guidance_series_analysis_digest_invalid")
    dynamics_file_digest = "sha256:" + hashlib.sha256(dynamics_bytes).hexdigest()

    series_id = plan.get("series_id")
    if (not isinstance(series_id, str) or not series_id
            or outcome.get("series_id") != series_id
            or analysis.get("series_id") != series_id
            or outcome.get("series_plan_digest") != plan_digest
            or analysis.get("series_plan_digest") != plan_digest
            or analysis.get("primary_outcome_digest") != outcome_digest
            or analysis.get("exploratory_response_dynamics_file_sha256")
                != dynamics_file_digest):
        raise ValueError("negative_guidance_series_cross_report_binding_mismatch")
    if (analysis.get("primary_outcome_path") != "negative-guidance-replication-series_outcome_20261124_v1.json"
            or analysis.get("exploratory_response_dynamics_path")
                != "response_dynamics_seed169_173_179_v1.json"):
        raise ValueError("negative_guidance_series_analysis_path_mismatch")

    planned = plan.get("planned_pairs")
    scored = outcome.get("per_pair_outcomes")
    pairs = dynamics.get("pairs")
    if (not isinstance(planned, list) or not isinstance(scored, list)
            or not isinstance(pairs, list) or not planned
            or len(planned) != len(scored) or len(scored) != len(pairs)
            or type(outcome.get("planned_pair_count")) is not int
            or type(outcome.get("completed_pair_count")) is not int
            or outcome.get("planned_pair_count") != len(planned)
            or outcome.get("completed_pair_count") != len(scored)
            or outcome.get("all_pair_journals_reconstructed") is not True
            or outcome.get("all_shadow_scores_match_owner_scores") is not True
            or analysis.get("independent_scorer_attested") is not False):
        raise ValueError("negative_guidance_series_pair_set_incomplete")

    pooled = outcome.get("pooled_descriptive_outcomes")
    if (not isinstance(pooled, Mapping)
            or analysis.get("primary_outcomes") != dict(pooled)):
        raise ValueError("negative_guidance_series_primary_outcome_mismatch")
    pooled_probe_rows = pooled.get("paired_probe_outcomes")
    if not isinstance(pooled_probe_rows, list):
        raise ValueError("negative_guidance_series_pooled_probe_rows_invalid")
    pooled_answered = _count_mapping(pooled.get("answered_counts"), _ARMS,
        "negative_guidance_series_pooled_answered_counts_invalid")
    pooled_correct = _count_mapping(pooled.get("correct_counts"), _ARMS,
        "negative_guidance_series_pooled_correct_counts_invalid")
    if type(pooled.get("probe_count")) is not int or pooled["probe_count"] < 0:
        raise ValueError("negative_guidance_series_pooled_probe_count_invalid")
    analysis_relations = _count_mapping(
        analysis.get("exploratory_response_relation_counts"), _RELATIONS,
        "negative_guidance_series_analysis_relation_counts_invalid")
    dynamics_relations = _count_mapping(
        dynamics.get("aggregate_relation_counts"), _RELATIONS,
        "negative_guidance_series_dynamics_relation_counts_invalid")
    if type(dynamics.get("aggregate_changed_answer_or_abstention_count")) is not int:
        raise ValueError("negative_guidance_series_dynamics_changed_count_invalid")
    if (type(analysis.get("changed_answer_or_abstention_count")) is not int
            or analysis["changed_answer_or_abstention_count"] < 0):
        raise ValueError("negative_guidance_series_analysis_changed_count_invalid")
    score_rows_by_seed: dict[int, dict[str, Mapping[str, Any]]] = {}
    receipt_recomputation: dict[int, dict[str, Any]] = {}
    for row in pooled_probe_rows:
        if (not isinstance(row, Mapping)
                or type(row.get("task_generation_seed")) is not int
                or not isinstance(row.get("probe_binding_digest"), str)
                or row.get(_ARMS[0]) not in {"correct", "incorrect", "abstained"}
                or row.get(_ARMS[1]) not in {"correct", "incorrect", "abstained"}):
            raise ValueError("negative_guidance_series_pooled_probe_row_invalid")
        seed_rows = score_rows_by_seed.setdefault(row["task_generation_seed"], {})
        if row["probe_binding_digest"] in seed_rows:
            raise ValueError("negative_guidance_series_duplicate_probe_binding")
        seed_rows[row["probe_binding_digest"]] = row

    aggregate = {name: 0 for name in _RELATIONS}
    changed_total = 0
    answered = {arm: 0 for arm in _ARMS}
    correct = {arm: 0 for arm in _ARMS}
    probe_total = 0
    for planned_row, score_pair, dynamics_pair in zip(planned, scored, pairs,
            strict=True):
        if (not isinstance(planned_row, Mapping)
                or not isinstance(score_pair, Mapping)
                or not isinstance(dynamics_pair, Mapping)):
            raise ValueError("negative_guidance_series_pair_row_invalid")
        seed = planned_row.get("task_generation_seed")
        if (type(seed) is not int or score_pair.get("task_generation_seed") != seed
                or dynamics_pair.get("task_generation_seed") != seed
                or score_pair.get("runtime_protocol_digest")
                    != dynamics_pair.get("protocol_digest")
                or score_pair.get("preflight_protocol_digest")
                    != planned_row.get("protocol_digest")
                or score_pair.get("task_digest") != dynamics_pair.get("task_digest")
                or planned_row.get("task_digest") != dynamics_pair.get("task_digest")):
            raise ValueError("negative_guidance_series_pair_binding_mismatch")
        per_probe = dynamics_pair.get("per_probe_relations")
        relation_counts = _count_mapping(
            dynamics_pair.get("response_relation_counts"), _RELATIONS,
            "negative_guidance_series_pair_relation_counts_invalid")
        pair_score_rows = score_rows_by_seed.get(seed)
        if (not isinstance(per_probe, list)
                or not isinstance(pair_score_rows, Mapping)
                or type(dynamics_pair.get("probe_count")) is not int
                or dynamics_pair.get("probe_count") != len(per_probe)):
            raise ValueError("negative_guidance_series_dynamics_pair_invalid")
        if journal_root is not None:
            receipt_recomputation[seed] = _recompute_pair_answer_relations(
                journal_root=journal_root,
                protocol_digest=dynamics_pair["protocol_digest"],
                task_generation_seed=seed,
                dynamics_pair=dynamics_pair)
        counted = {name: 0 for name in _RELATIONS}
        seen: set[str] = set()
        for probe in per_probe:
            if (not isinstance(probe, Mapping)
                    or not isinstance(probe.get("probe_binding_digest"), str)
                    or probe.get("response_relation") not in _RELATIONS):
                raise ValueError("negative_guidance_series_probe_relation_invalid")
            digest = probe["probe_binding_digest"]
            relation = probe["response_relation"]
            score_row = pair_score_rows.get(digest)
            if digest in seen or not isinstance(score_row, Mapping):
                raise ValueError("negative_guidance_series_probe_join_invalid")
            seen.add(digest)
            present_answered = score_row[_ARMS[0]] != "abstained"
            omitted_answered = score_row[_ARMS[1]] != "abstained"
            expected = (
                "both_abstained" if not present_answered and not omitted_answered
                else "present_only_answered" if present_answered and not omitted_answered
                else "omitted_only_answered" if omitted_answered and not present_answered
                else relation)
            if expected != relation:
                raise ValueError("negative_guidance_series_answer_coverage_mismatch")
            counted[relation] += 1
        if seen != set(pair_score_rows):
            raise ValueError("negative_guidance_series_probe_set_mismatch")
        if dict(relation_counts) != counted or sum(counted.values()) != len(per_probe):
            raise ValueError("negative_guidance_series_relation_count_mismatch")
        changed = sum(counted[name] for name in (
            "present_only_answered", "omitted_only_answered", "different_answers"))
        if (type(dynamics_pair.get("changed_answer_or_abstention_count")) is not int
                or dynamics_pair.get("changed_answer_or_abstention_count") != changed):
            raise ValueError("negative_guidance_series_changed_count_mismatch")
        for name in _RELATIONS:
            aggregate[name] += counted[name]
        changed_total += changed
        probe_total += len(per_probe)
        for row in pair_score_rows.values():
            for arm in _ARMS:
                answered[arm] += row[arm] != "abstained"
                correct[arm] += row[arm] == "correct"

    if (dynamics_relations != aggregate
            or dynamics.get("aggregate_changed_answer_or_abstention_count")
                != changed_total
            or analysis_relations != aggregate
            or analysis.get("changed_answer_or_abstention_count") != changed_total
            or pooled["probe_count"] != probe_total
            or pooled_answered != answered
            or pooled_correct != correct
            or analysis.get("improvement_established") is not False
            or analysis.get("learning_established") is not False
            or analysis.get("authority") is not False):
        raise ValueError("negative_guidance_series_aggregate_reconciliation_failed")

    return {
        "schema_version": "sentientos.negative_guidance_replication_series_analysis_verification:v2",
        "series_id": series_id,
        "series_plan_digest": plan_digest,
        "primary_outcome_digest": outcome_digest,
        "analysis_digest": analysis_digest,
        "response_dynamics_file_sha256": dynamics_file_digest,
        "planned_pair_count": len(planned),
        "verified_probe_count": probe_total,
        "verified_answered_counts": answered,
        "verified_correct_counts": correct,
        "reconciled_coverage_relation_counts": {
            name: aggregate[name] for name in (
                "both_abstained", "present_only_answered",
                "omitted_only_answered")},
        "source_report_answer_relation_counts": {
            name: aggregate[name] for name in ("same_answer", "different_answers")},
        "source_report_changed_answer_or_abstention_count": changed_total,
        "answer_value_relation_independently_recomputed": journal_root is not None,
        "receipt_answer_relation_recomputation": {
            str(seed): receipt_recomputation[seed]
            for seed in sorted(receipt_recomputation)},
        "cross_report_probe_bindings_reconciled": True,
        "correctness_and_response_change_reconciled_separately": True,
        "independent_scorer_attested": False,
        "causal_effect_established": False,
        "learning_established": False,
        "improvement_established": False,
        "model_loaded": False,
        "model_invoked": False,
        "authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--outcome", required=True, type=Path)
    parser.add_argument("--dynamics", required=True, type=Path)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--journal-root", type=Path,
        help="Optional read-only root containing developmental_experiments journal data")
    parser.add_argument("--output", type=Path,
        help="Optional create-only JSON verification artifact")
    args = parser.parse_args()
    plan, _ = _read_json(args.plan)
    outcome, _ = _read_json(args.outcome)
    dynamics, dynamics_bytes = _read_json(args.dynamics)
    analysis, _ = _read_json(args.analysis)
    report = verify_series_analysis(plan=plan, outcome=outcome,
        dynamics=dynamics, analysis=analysis, dynamics_bytes=dynamics_bytes,
        journal_root=args.journal_root)
    report["verification_digest"] = _digest(report)
    rendered = json.dumps(report, indent=2, sort_keys=True,
        ensure_ascii=False, allow_nan=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        raise SystemExit(str(exc))
