"""Replay a saved pre-transfer history allowlist through the current owner and binder.

This read-only CPU audit uses the saved request's admitted history IDs to avoid
post-transfer records in a completed composition state. The original current
evidence payload is not retained in invocation receipts, so the cycle result's
answer-free evidence summary is used as a clearly labeled budget surrogate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.resident_developmental_cognition import (  # noqa: E402
    EXPERIMENT_CONTEXT_INSTRUCTION,
    ResidentDevelopmentalCognitionOwner,
    _bind_history_and_epistemic_context,
    _digest,
    _task_family_history_prompt_projection,
)
from sentientos.resident_developmental_writeback import (  # noqa: E402
    DevelopmentalHistoryProjection,
)


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("preflight_source_file_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("preflight_source_json_invalid")
    return value


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class _ReadOnlyRecordStore:
    def __init__(self, records_root: Path,
            expected_refs: dict[str, str]) -> None:
        self.records_root = records_root
        self.expected_refs = expected_refs
        self.cache: dict[str, SimpleNamespace] = {}

    def get(self, record_id: str) -> SimpleNamespace:
        if record_id not in self.cache:
            path = self.records_root / (record_id + ".json")
            row = _read_json(path)
            if (row.get("record_id") != record_id
                    or (record_id in self.expected_refs
                        and row.get("record_digest") != self.expected_refs[record_id])
                    or not isinstance(row.get("record_digest"), str)
                    or re.fullmatch(r"sha256:[0-9a-f]{64}",
                        row["record_digest"]) is None
                    or not isinstance(row.get("candidate"), dict)):
                raise ValueError("preflight_history_record_binding_invalid")
            self.cache[record_id] = SimpleNamespace(
                record_id=record_id,
                record_digest=row["record_digest"],
                candidate=row["candidate"],
            )
        return self.cache[record_id]


class _ReadOnlyWriteback:
    def __init__(self, store: _ReadOnlyRecordStore) -> None:
        self.store = store

    def retrieve(self, record_ids: list[str], *, limit: int
            ) -> DevelopmentalHistoryProjection:
        selected = record_ids[:limit]
        records = tuple({
            "record_id": record_id,
            "record_digest": self.store.get(record_id).record_digest,
            "candidate": self.store.get(record_id).candidate,
        } for record_id in selected)
        return DevelopmentalHistoryProjection(
            records=records, requested_record_ids=tuple(selected))


def create_report(*, cycle_root: Path, receipt_id: str,
        output_path: Path) -> dict[str, Any]:
    if re.fullmatch(r"lmrec-[0-9a-f]{24}", receipt_id) is None:
        raise ValueError("preflight_receipt_id_invalid")
    state_path = cycle_root / "resident-cognition" / "state" / "composition_state.json"
    history_root = cycle_root / "resident-cognition" / "history"
    receipt_path = cycle_root / "inference-custody" / "receipts" / (receipt_id + ".json")
    result_path = cycle_root / "cycle-result.json"
    state = _read_json(state_path)
    receipt = _read_json(receipt_path)
    cycle_result = _read_json(result_path)
    state_semantic = {key: value for key, value in state.items()
        if key != "state_digest"}
    state_digest_valid = state.get("state_digest") == _digest(state_semantic)
    request = receipt.get("request")
    upstream = request.get("upstream_evidence") if isinstance(request, dict) else None
    selection = (upstream.get("developmental_history_selection")
        if isinstance(upstream, dict) else None)
    identity = request.get("active_model_identity") if isinstance(request, dict) else None
    transfer = cycle_result.get("objective_task_family_transfer")
    probe_outcomes = (transfer.get("probe_level_outcomes", {}).get("probe_outcomes")
        if isinstance(transfer, dict)
        and isinstance(transfer.get("probe_level_outcomes"), dict) else None)
    if (not state_digest_valid
            or not isinstance(selection, dict)
            or selection.get("treatment") != "present"
            or selection.get("schema_version")
                != "sentientos.developmental_history_selection:v1"
            or selection.get("policy") != "most_recent_complete_record_suffix:v1"
            or not isinstance(selection.get("task_family_id"), str)
            or not isinstance(selection.get("available_records"), list)
            or not 1 <= len(selection["available_records"]) <= 16
            or not isinstance(identity, dict) or not identity
            or not isinstance(probe_outcomes, list)
            or not 2 <= len(probe_outcomes) <= 16
            or not isinstance(receipt.get("generation_config"), dict)
            or type(receipt["generation_config"].get("max_input_chars")) is not int):
        raise ValueError("preflight_owner_evidence_invalid")
    family = selection["task_family_id"]
    limit = receipt["generation_config"]["max_input_chars"]
    probe_inputs = tuple(row.get("probe_input") for row in probe_outcomes
        if isinstance(row, dict))
    if (len(probe_inputs) != len(probe_outcomes)
            or any(type(value) is not int for value in probe_inputs)
            or len(set(probe_inputs)) != len(probe_inputs)):
        raise ValueError("preflight_probe_inputs_invalid")
    available_refs = selection["available_records"]
    state_refs: dict[str, str] = {}
    completed_ids = {row.get("record_id")
        for row in state.get("completed_ticks", ()) if isinstance(row, dict)}
    for row in available_refs:
        if (not isinstance(row, dict)
                or not isinstance(row.get("record_id"), str)
                or not isinstance(row.get("record_digest"), str)
                or row["record_id"] not in completed_ids
                or row["record_id"] in state_refs):
            raise ValueError("preflight_saved_allowlist_invalid")
        state_refs[row["record_id"]] = row["record_digest"]
    transfer_writeback_id = transfer.get("transfer_history_record_id")
    allowlist_ids = tuple(state_refs)
    if transfer_writeback_id in allowlist_ids:
        raise ValueError("preflight_transfer_writeback_in_allowlist")

    store = _ReadOnlyRecordStore(history_root / "records", state_refs)
    for ref in available_refs:
        if store.get(ref["record_id"]).record_digest != ref["record_digest"]:
            raise ValueError("preflight_saved_allowlist_record_digest_invalid")
    owner = ResidentDevelopmentalCognitionOwner.__new__(
        ResidentDevelopmentalCognitionOwner)
    owner.config = SimpleNamespace(
        max_retrieved_records=min(4, len(allowlist_ids)),
        semantic_history_model_id=None,
        semantic_history_model_revision=None,
        state_root=None,
    )
    owner.writeback = _ReadOnlyWriteback(store)
    owner.objective_task = None
    projection = owner._prior_projection(state,
        "offline-pretransfer-owner-prompt-preflight",
        task_family_id=family, task_probe_inputs=probe_inputs,
        target_model_identity=identity, record_allowlist=allowlist_ids,
        require_task_family_history=True, use_semantic_retrieval=False)

    retrieval_policy_id = (
        "task_family_outcome_then_evaluator_correct_coverage_then_model_probe_overlap_recency:v9"
        if identity else
        "task_family_correct_input_coverage_then_probe_overlap_then_recency_fill:v4")
    evidence_summary = cycle_result.get("source_evidence")
    if not isinstance(evidence_summary, dict):
        raise ValueError("preflight_evidence_summary_missing")
    evidence_json = json.dumps(evidence_summary, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False)
    context = {
        "instruction": EXPERIMENT_CONTEXT_INSTRUCTION,
        "current_evidence": evidence_summary,
        "developmental_history_task_family_id": family,
        "developmental_history_task_family_history_required": True,
        "developmental_history_target_model_identity": identity,
        "developmental_history_retrieval_policy_id": retrieval_policy_id,
    }
    bound, _, prompt, selected_ids, selected_digests = (
        _bind_history_and_epistemic_context(context=context,
            records=projection.records, projection=None,
            history_present=True, compact_history_for_input=True,
            max_input_chars=limit))
    prompt_digest = _digest({"prompt": prompt})
    task_family_projection = _task_family_history_prompt_projection(
        bound, condition_id="history_present", task_family_id=family,
        task_probe_inputs=probe_inputs,
        governed_request_prompt_digest=prompt_digest[7:], prompt=prompt)
    strategy = bound.get("task_family_accumulated_candidate_strategy")
    report = {
        "schema_version": "sentientos.rootless_task_family_owner_prompt_preflight:v2",
        "cycle_id": cycle_root.name,
        "source_run_id": cycle_result.get("run_id"),
        "receipt_id": receipt_id,
        "receipt_digest": receipt.get("receipt_digest"),
        "saved_allowlist_selection_digest": selection.get("selection_digest"),
        "saved_allowlist_record_ids": list(allowlist_ids),
        "posttransfer_writeback_record_id_excluded": transfer_writeback_id,
        "composition_state_digest": state["state_digest"],
        "composition_state_digest_verified": state_digest_valid,
        "completed_tick_count": len(state.get("completed_ticks", ())),
        "task_family_id": family,
        "task_probe_inputs": list(probe_inputs),
        "target_model_identity_digest": _digest(identity),
        "semantic_encoder_used": False,
        "owner_selected_record_ids": list(projection.requested_record_ids),
        "binder_selected_record_ids": list(selected_ids),
        "binder_selected_record_digests": list(selected_digests),
        "prompt_chars": len(prompt),
        "prompt_digest": prompt_digest[7:],
        "prompt_limit_chars": limit,
        "prompt_within_bound": len(prompt) <= limit,
        "task_family_prompt_projection_verified": True,
        "task_family_prompt_projection_schema": (
            task_family_projection["schema_version"]),
        "task_family_prompt_projection_digest": (
            task_family_projection["projection_digest"]),
        "current_evidence_posture": (
            "cycle_result_answer_free_summary_surrogate_not_original_full_payload"),
        "current_evidence_summary_chars": len(evidence_json),
        "current_evidence_summary_digest": _canonical_digest(evidence_summary),
        "accumulated_strategy_present": isinstance(strategy, dict),
        "accumulated_strategy_schema_version": (
            strategy.get("schema_version") if isinstance(strategy, dict) else None),
        "accumulated_strategy_run_count": (
            strategy.get("supporting_run_count") if isinstance(strategy, dict) else None),
        "accumulated_strategy_distinct_input_count": (
            strategy.get("supporting_distinct_input_count")
            if isinstance(strategy, dict) else None),
        "posttransfer_writeback_excluded_from_allowlist": (
            transfer_writeback_id not in allowlist_ids),
        "exact_prompt_reconstructed": False,
        "inference_performed": False,
        "model_attention_established": False,
        "learning_established": False,
        "authority": False,
    }
    report["audit_digest"] = _canonical_digest(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-root", required=True, type=Path)
    parser.add_argument("--receipt-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = create_report(cycle_root=args.cycle_root,
        receipt_id=args.receipt_id, output_path=args.output)
    print(json.dumps({key: report[key] for key in (
        "audit_digest", "owner_selected_record_ids", "binder_selected_record_ids",
        "prompt_chars", "prompt_limit_chars", "accumulated_strategy_run_count",
        "accumulated_strategy_distinct_input_count", "inference_performed",
        "learning_established")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
