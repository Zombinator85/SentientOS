"""Reproject an owner's available history packets and estimate compact suffix fit.

This is a read-only CPU audit. It does not assemble the exact governed prompt,
invoke a model, or establish that a later owner will select the projected suffix.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.resident_developmental_cognition import (  # noqa: E402
    MAX_HISTORY,
    _candidate_integer_affine_strategy_from_history,
    _compact_accumulated_integer_affine_strategy,
    _history_context_packet,
    _task_family_unsettled_outcome_groups,
)


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("budget_audit_source_file_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("budget_audit_source_json_invalid")
    return value


def create_report(*, history_root: Path, owner_receipt_path: Path,
        previous_selected_packet_chars: int, output_path: Path,
        history_family_ids: tuple[str, ...] | None = None,
        additional_guidance_chars: int = 0) -> dict[str, Any]:
    if (type(previous_selected_packet_chars) is not int
            or previous_selected_packet_chars < 0
            or type(additional_guidance_chars) is not int
            or additional_guidance_chars < 0):
        raise ValueError("budget_audit_previous_packet_size_invalid")
    owner = _read_json(owner_receipt_path)
    request = owner.get("request")
    upstream = request.get("upstream_evidence") if isinstance(request, dict) else None
    selection = (upstream.get("developmental_history_selection")
        if isinstance(upstream, dict) else None)
    if (not isinstance(request, dict) or not isinstance(upstream, dict)
            or not isinstance(selection, dict)
            or selection.get("schema_version")
                != "sentientos.developmental_history_selection:v1"
            or selection.get("policy") != "most_recent_complete_record_suffix:v1"
            or selection.get("treatment") != "present"
            or not isinstance(selection.get("task_family_id"), str)
            or not isinstance(selection.get("available_records"), list)
            or not 1 <= len(selection["available_records"]) <= MAX_HISTORY
            or not isinstance(request.get("active_model_identity"), dict)
            or type(request.get("prompt_size")) is not int
            or not isinstance(owner.get("generation_config"), dict)
            or type(owner["generation_config"].get("max_input_chars")) is not int):
        raise ValueError("budget_audit_owner_selection_invalid")
    family = selection["task_family_id"]
    if history_family_ids is None:
        history_family_ids = (family,)
    if (not isinstance(history_family_ids, tuple)
            or not history_family_ids or len(history_family_ids) > 4
            or any(not isinstance(value, str) or not value
                or len(value) > 128 for value in history_family_ids)
            or family not in history_family_ids
            or len(set(history_family_ids)) != len(history_family_ids)):
        raise ValueError("budget_audit_history_family_ids_invalid")
    target_identity = request["active_model_identity"]
    records_root = history_root / "records"
    rows: list[dict[str, Any]] = []
    primary_packets: list[dict[str, Any]] = []
    alternate_mode_packets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for reference in selection["available_records"]:
        if (not isinstance(reference, dict)
                or not isinstance(reference.get("record_id"), str)
                or not re.fullmatch(r"devrec-[0-9a-f]{24}",
                    reference["record_id"])
                or reference["record_id"] in seen_ids
                or not isinstance(reference.get("record_digest"), str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}",
                    reference["record_digest"]) is None):
            raise ValueError("budget_audit_available_record_reference_invalid")
        seen_ids.add(reference["record_id"])
        record = _read_json(records_root / (reference["record_id"] + ".json"))
        candidate = record.get("candidate")
        facts = candidate.get("selected_facts", ()) if isinstance(candidate, dict) else ()
        if (record.get("record_id") != reference["record_id"]
                or record.get("record_digest") != reference["record_digest"]
                or not isinstance(candidate, dict)
                or not any(isinstance(fact, dict)
                    and isinstance(fact.get("payload"), dict)
                    and fact["payload"].get("objective_task_family")
                        in history_family_ids
                    for fact in facts)):
            raise ValueError("budget_audit_record_binding_or_family_mismatch")
        packet_input = {"record_id": record["record_id"],
            "record_digest": record["record_digest"], "candidate": candidate}
        common = {"include_source_evidence_context": False,
            "compact_for_input_budget": True,
            "task_family_id": history_family_ids,
            "target_model_identity": target_identity}
        primary = _history_context_packet(packet_input,
            **common, omit_historical_embodiment_details=False)
        alternate = _history_context_packet(packet_input,
            **common, omit_historical_embodiment_details=True)
        if (primary.get("record_id") != reference["record_id"]
                or alternate.get("record_digest") != reference["record_digest"]):
            raise ValueError("budget_audit_packet_identity_mismatch")
        experiences = primary.get("task_relevant_experience", ())
        correct_count = sum(len(item.get("examples", ()))
            for item in experiences if isinstance(item, dict))
        incorrect_count = sum(len(item.get("prior_incorrect_examples", {}).get(
            "examples", ())) for item in experiences
            if isinstance(item, dict)
            and isinstance(item.get("prior_incorrect_examples"), dict))
        abstained_count = sum(len(item.get("prior_abstained_examples", {}).get(
            "examples", ())) for item in experiences
            if isinstance(item, dict)
            and isinstance(item.get("prior_abstained_examples"), dict))
        primary_chars = len(json.dumps(primary, sort_keys=True,
            separators=(",", ":"), ensure_ascii=True))
        alternate_chars = len(json.dumps(alternate, sort_keys=True,
            separators=(",", ":"), ensure_ascii=True))
        rows.append({"record_id": reference["record_id"],
            "record_digest": reference["record_digest"],
            "compact_packet_chars": primary_chars,
            "alternate_compact_packet_chars": alternate_chars,
            "score_bound_correct_example_count": correct_count,
            "score_bound_incorrect_example_count": incorrect_count,
            "prior_abstained_example_count": abstained_count})
        primary_packets.append(primary)
        alternate_mode_packets.append(alternate)

    owner_prompt_chars = request["prompt_size"]
    input_limit = owner["generation_config"]["max_input_chars"]
    if previous_selected_packet_chars > owner_prompt_chars:
        raise ValueError("budget_audit_prior_packet_size_exceeds_prompt")
    fixed_remainder = owner_prompt_chars - previous_selected_packet_chars
    old_projection = upstream.get("task_family_history_prompt_projection")
    old_strategy = (old_projection.get(
        "accumulated_candidate_integer_affine_strategy")
        if isinstance(old_projection, dict) else None)
    old_prompt_strategy_chars = (len(json.dumps(
        _compact_accumulated_integer_affine_strategy(old_strategy),
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False)) if isinstance(old_strategy, dict) else 0)
    experiences_by_record = {packet["record_id"]: packet.get(
        "task_relevant_experience", ()) for packet in primary_packets}
    unsettled_groups = _task_family_unsettled_outcome_groups(
        experiences_by_record, target_model_identity=target_identity)
    suffix_estimates: list[dict[str, Any]] = []
    for count in range(1, len(primary_packets) + 1):
        selected = primary_packets[-count:]
        omitted = primary_packets[:-count]
        packet_chars = sum(row["compact_packet_chars"] for row in rows[-count:])
        selected_packets = primary_packets[-count:]
        current_strategy = _candidate_integer_affine_strategy_from_history(
            selected_packets, task_family_id=family,
            history_task_family_ids=history_family_ids,
            unsettled_outcome_groups=unsettled_groups)
        prompt_strategy = (_compact_accumulated_integer_affine_strategy(
            current_strategy) if isinstance(current_strategy, dict) else None)
        prompt_strategy_chars = (len(json.dumps(prompt_strategy,
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False)) if prompt_strategy is not None else 0)
        strategy_delta = prompt_strategy_chars - old_prompt_strategy_chars
        correct_run_digests = {
            experience.get("source_run_digest")
            for packet in selected
            for experience in packet.get("task_relevant_experience", ())
            if isinstance(experience, dict)
            and experience.get("examples")
            and isinstance(experience.get("source_run_digest"), str)}
        estimated_chars = fixed_remainder + packet_chars
        suffix_estimates.append({
            "newest_complete_suffix_record_count": count,
            "selected_record_ids": [packet["record_id"] for packet in selected],
            "omitted_record_ids": [packet["record_id"] for packet in omitted],
            "compact_packet_chars": packet_chars,
            "correct_example_source_run_count": len(correct_run_digests),
            "compact_accumulated_strategy_chars": prompt_strategy_chars,
            "compact_accumulated_strategy_present": prompt_strategy is not None,
            "baseline_compact_accumulated_strategy_chars": old_prompt_strategy_chars,
            "unsettled_outcome_group_count": len(unsettled_groups),
            "accumulated_strategy_prompt_char_delta": strategy_delta,
            "additional_confidence_guidance_chars": additional_guidance_chars,
            "estimated_prompt_chars_with_strategy_and_guidance": (
                estimated_chars + strategy_delta + additional_guidance_chars),
            "remaining_input_chars_after_strategy_and_guidance": (
                input_limit - estimated_chars - strategy_delta
                - additional_guidance_chars),
            "fits_under_fixed_remainder_estimate": (
                estimated_chars + strategy_delta + additional_guidance_chars
                <= input_limit),
        })
    predicted_count = max((row["newest_complete_suffix_record_count"]
        for row in suffix_estimates
        if row["fits_under_fixed_remainder_estimate"]), default=0)
    semantic: dict[str, Any] = {
        "schema_version": "sentientos.compact_history_packet_budget_audit:v1",
        "owner_receipt_id": owner.get("receipt_id"),
        "owner_receipt_digest": owner.get("receipt_digest"),
        "history_selection_digest": selection.get("selection_digest"),
        "task_family_id": family,
        "history_task_family_ids": list(history_family_ids),
        "input_limit_chars": input_limit,
        "prechange_owner_prompt_chars": owner_prompt_chars,
        "prechange_selected_record_count": len(selection.get("selected_records", ())),
        "prechange_available_record_count": len(rows),
        "prechange_omission_reason": selection.get("omission_reason"),
        "fixed_prompt_remainder_estimate_chars": fixed_remainder,
        "fixed_remainder_estimate_method": (
            "prechange_owner_prompt_chars_minus_supplied_prechange_packet_chars"),
        "prechange_selected_packet_chars": previous_selected_packet_chars,
        "available_compact_packets": rows,
        "alternate_compact_mode_sizes_match": all(
            row["compact_packet_chars"] == row["alternate_compact_packet_chars"]
            for row in rows),
        "suffix_budget_estimates": suffix_estimates,
        "estimated_newest_suffix_count": predicted_count,
        "fixed_remainder_difference_from_current_prompt_not_measured": True,
        "baseline_compact_accumulated_strategy_chars": old_prompt_strategy_chars,
        "additional_confidence_guidance_chars": additional_guidance_chars,
        "accumulated_strategy_delta_included": True,
        "exact_prompt_assembled": False,
        "postchange_owner_receipt_observed": False,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    artifact = {**semantic, "artifact_digest": _canonical_digest(semantic)}
    output_path = output_path.expanduser()
    if any(path.is_symlink() for path in (output_path, *output_path.parents)):
        raise ValueError("budget_audit_output_path_symlink")
    try:
        output_path.resolve(strict=False).relative_to(
            history_root.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise ValueError("budget_audit_output_inside_history_store")
    serialized = json.dumps(artifact, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False) + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        if output_path.read_text(encoding="utf-8") != serialized:
            raise ValueError("budget_audit_output_immutable_mismatch")
    else:
        output_path.write_text(serialized, encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--owner-receipt", type=Path, required=True)
    parser.add_argument("--previous-selected-packet-chars", type=int, required=True)
    parser.add_argument("--history-family-id", action="append", dest="history_family_ids",
        help="additional task family admitted by the task's history descriptor; repeatable")
    parser.add_argument("--additional-guidance-chars", type=int, default=0,
        help="new prompt guidance characters not present in the baseline receipt")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = create_report(history_root=args.history_root,
        owner_receipt_path=args.owner_receipt,
        previous_selected_packet_chars=args.previous_selected_packet_chars,
        history_family_ids=tuple(args.history_family_ids)
            if args.history_family_ids else None,
        additional_guidance_chars=args.additional_guidance_chars,
        output_path=args.output)
    print(json.dumps({"artifact": str(args.output),
        "artifact_digest": report["artifact_digest"],
        "available_records": report["prechange_available_record_count"],
        "estimated_newest_suffix_count": report[
            "estimated_newest_suffix_count"],
        "exact_prompt_assembled": False,
        "inference_performed": False,
        "learning_established": False}, sort_keys=True))


if __name__ == "__main__":
    main()
