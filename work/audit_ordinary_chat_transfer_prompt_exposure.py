"""Audit prompt-length balance in a frozen ordinary-chat transfer preflight."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_SCHEMA = "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v8"
ARMS = ("history", "derived_history", "empty")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _derive_candidate_from_support(task_family_id: Any, rows: Any) -> dict[str, Any]:
    if (not isinstance(task_family_id, str)
            or not task_family_id.startswith("rootless_integer_affine_transfer_")
            or not isinstance(rows, list) or len(rows) < 3):
        raise ValueError("preflight support cannot derive an affine candidate")
    examples = []
    for row in rows:
        if (not isinstance(row, dict) or type(row.get("probe_input")) is not int
                or type(row.get("observed_answer")) is not int
                or row.get("evaluator_correct") is not True
                or row.get("abstained") is not False):
            raise ValueError("preflight support contains an ineligible row")
        examples.append((row["probe_input"], row["observed_answer"]))
    if len({x for x, _ in examples}) < 3:
        raise ValueError("preflight support has fewer than three distinct inputs")
    first = examples[0]
    second = next((row for row in examples[1:] if row[0] != first[0]), None)
    if second is None:
        raise ValueError("preflight support has no distinct input pair")
    multiplier = Fraction(second[1] - first[1], second[0] - first[0])
    offset = Fraction(first[1]) - multiplier * first[0]
    if (multiplier.denominator != 1 or offset.denominator != 1
            or any(multiplier * x + offset != y for x, y in examples)):
        raise ValueError("preflight support does not fit one exact integer-affine candidate")
    return {"multiplier": multiplier.numerator, "offset": offset.numerator,
            "support_input_range": [min(x for x, _ in examples),
                                    max(x for x, _ in examples)]}


def audit(preflight_path: Path) -> dict[str, Any]:
    resolved_preflight = preflight_path.resolve()
    try:
        portable_path = resolved_preflight.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("preflight must be inside the repository for a portable audit") from exc
    raw = resolved_preflight.read_bytes()
    preflight = json.loads(raw)
    if preflight.get("schema") != EXPECTED_SCHEMA:
        raise ValueError("prompt exposure audit requires the frozen v8 candidate preflight")
    if tuple(preflight.get("arms", ())) != ARMS:
        raise ValueError("preflight arms differ from the frozen candidate experiment")
    if preflight.get("inference_performed") is not False or preflight.get(
            "learning_established") is not False:
        raise ValueError("prompt exposure audit only accepts a model-free preflight")
    if preflight.get("all_tier_prompts_match_outside_probe_values") is not True:
        raise ValueError("preflight does not attest matched prompt bases")
    if preflight.get("derived_rule_hypothesis_treatment") != (
            "exact_integer_affine_fit_from_scored_rows:v1"):
        raise ValueError("preflight does not bind the expected candidate derivation")
    derivation_path = REPOSITORY_ROOT / "sentientos/cognition_retrieval.py"
    frozen_derivation_hash = preflight.get("implementation_sha256", {}).get(
        "sentientos/cognition_retrieval.py")
    if (not isinstance(frozen_derivation_hash, str)
            or hashlib.sha256(derivation_path.read_bytes()).hexdigest()
                != frozen_derivation_hash):
        raise ValueError("candidate derivation implementation differs from frozen preflight")

    expected_hypothesis = _derive_candidate_from_support(
        preflight.get("support_task_family_id"), preflight.get("support_rows"))
    support_evidence = None
    for tier_data in preflight.get("tiers", {}).values():
        evidence = tier_data.get("captures", {}).get("derived_history", {}).get(
            "prompt_score_evidence", [])
        if len(evidence) != 1:
            raise ValueError("derived arm does not contain exactly one scored support record")
        if support_evidence is None:
            support_evidence = evidence[0]
        elif evidence[0] != support_evidence:
            raise ValueError("derived arm support record changes across tiers")
    if (not isinstance(support_evidence, dict)
            or support_evidence.get("record_id") != preflight.get("support_record_id")
            or support_evidence.get("task_family_id")
                != preflight.get("support_task_family_id")
            or support_evidence.get("examples") != preflight.get("support_rows")):
        raise ValueError("frozen support rows differ from derived-arm score evidence")
    expected_candidate = {
        "hypothesis": expected_hypothesis,
        "record_id": support_evidence["record_id"],
        "source_fact_id": support_evidence["source_fact_id"],
        "source_run_id": support_evidence["source_run_id"],
        "source_score_digest": support_evidence["source_score_digest"],
        "task_family_id": support_evidence["task_family_id"],
    }

    by_tier: dict[str, Any] = {}
    for tier, tier_data in preflight.get("tiers", {}).items():
        captures = tier_data.get("captures", {})
        if set(captures) != set(ARMS):
            raise ValueError(f"{tier}: expected exactly the three frozen arms")
        lengths: dict[str, int] = {}
        for arm in ARMS:
            chars = captures[arm].get("prompt_chars")
            if type(chars) is not int or chars < 1:
                raise ValueError(f"{tier}/{arm}: missing valid prompt character count")
            lengths[arm] = chars
        raw_history = captures["history"].get("history_instruction")
        derived_history = captures["derived_history"].get("history_instruction")
        if not raw_history or raw_history != derived_history:
            raise ValueError(f"{tier}: history guidance differs between history arms")
        if not captures["history"].get("history_block_digest") or not captures[
                "derived_history"].get("history_block_digest"):
            raise ValueError(f"{tier}: history arm is missing its history block")
        if captures["empty"].get("history_block_digest") is not None:
            raise ValueError(f"{tier}: empty arm unexpectedly contains a history block")
        if (captures["history"].get("derived_rule_hypotheses", [])
                or captures["empty"].get("derived_rule_hypotheses", [])
                or captures["derived_history"].get("derived_rule_hypotheses")
                    != [expected_candidate]):
            raise ValueError(f"{tier}: candidate is missing, misplaced, or not support-derived")
        by_tier[tier] = {
            "prompt_chars": lengths,
            "derived_minus_raw_history_chars": (
                lengths["derived_history"] - lengths["history"]),
            "history_minus_empty_chars": lengths["history"] - lengths["empty"],
            "derived_minus_empty_chars": lengths["derived_history"] - lengths["empty"],
            "history_guidance_equal": True,
        }
    if not by_tier:
        raise ValueError("preflight contains no tiers")

    candidate_deltas = {item["derived_minus_raw_history_chars"]
                        for item in by_tier.values()}
    return {
        "schema": "sentientos.ordinary_chat_transfer_prompt_exposure_audit:v3",
        "preflight_path": portable_path,
        "preflight_sha256": hashlib.sha256(raw).hexdigest(),
        "audit_implementation_sha256": hashlib.sha256(
            Path(__file__).resolve().read_bytes()).hexdigest(),
        "inference_performed": False,
        "learning_established": False,
        "tiers": by_tier,
        "candidate_character_delta_constant_across_tiers": len(candidate_deltas) == 1,
        "candidate_character_delta_values": sorted(candidate_deltas),
        "interpretation": (
            "Raw and derived history share guidance; the derived arm adds its candidate payload. "
            "Character counts quantify the added prompt text but do not equal tokenizer token "
            "counts or control for prompt-length effects."),
        "remaining_control_gap": (
            "No length-matched sham-candidate arm is present. The raw-versus-derived contrast "
            "therefore estimates the effect of adding the candidate payload, including its "
            "additional prompt length."),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preflight", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = audit(args.preflight)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"output": args.output.as_posix(),
                      "preflight_sha256": report["preflight_sha256"],
                      "candidate_character_delta_values":
                          report["candidate_character_delta_values"],
                      "length_matched_control_present": False}, sort_keys=True))


if __name__ == "__main__":
    main()
