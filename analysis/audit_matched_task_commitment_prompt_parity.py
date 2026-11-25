"""Audit digest-only history and prompt parity for a verified matched preflight."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

MAX_ARTIFACT_BYTES = 8 * 1024 * 1024


def _is_digest(value: Any, *, prefixed: bool = True) -> bool:
    if not isinstance(value, str):
        return False
    raw = value[7:] if prefixed and value.startswith("sha256:") else value
    return (len(raw) == 64 and (not prefixed or value.startswith("sha256:"))
        and all(character in "0123456789abcdef" for character in raw))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("matched_prompt_parity_duplicate_json_key")
        result[key] = value
    return result


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ValueError("matched_prompt_parity_input_unreadable") from exc
    try:
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_ARTIFACT_BYTES
                or metadata.st_nlink != 1):
            raise ValueError("matched_prompt_parity_input_invalid")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise ValueError("matched_prompt_parity_input_truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if ((metadata.st_dev, metadata.st_ino, metadata.st_size,
                metadata.st_mtime_ns) != (after.st_dev, after.st_ino,
                after.st_size, after.st_mtime_ns)):
            raise ValueError("matched_prompt_parity_input_changed")
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("matched_prompt_parity_nonstandard_json")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("matched_prompt_parity_json_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("matched_prompt_parity_object_required")
    return value, "sha256:" + hashlib.sha256(raw).hexdigest()


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _validate_verification(report: dict[str, Any], verification: dict[str, Any]
        ) -> None:
    if (verification.get("schema_version") !=
            "sentientos.resident_historical_examples_preflight_verification:v7"
            or verification.get("preflight_report_digest") !=
                _canonical_digest(report)
            or verification.get("protocol_digest") != report.get("protocol_digest")
            or verification.get("source_history_reconstructed") is not True
            or verification.get("owner_prompt_pair_reconstructed") is not True
            or verification.get("journal_protocol_verified") is not True
            or verification.get("resident_owner_protocol_gate_verified") is not True
            or verification.get("model_loaded") is not False
            or verification.get("model_invoked") is not False
            or verification.get("learning_established") is not False
            or verification.get("authority") is not False):
        raise ValueError("matched_prompt_parity_preflight_verification_invalid")


def _selected_records(report: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    protocol = report.get("historical_examples_protocol")
    ablation = (protocol.get("historical_examples_prompt_ablation")
        if isinstance(protocol, dict) else None)
    if not isinstance(protocol, dict) or not isinstance(ablation, dict):
        raise ValueError("matched_prompt_parity_history_selection_missing")
    ids = ablation.get("selected_record_ids")
    digests = ablation.get("selected_record_digests")
    if (not isinstance(ids, list) or not isinstance(digests, list)
            or len(ids) != len(digests) or len(ids) != len(set(ids))
            or any(not isinstance(item, str) or not item for item in ids)
            or any(not isinstance(value, str) or len(value) != 71
                or not value.startswith("sha256:")
                or any(char not in "0123456789abcdef" for char in value[7:])
                for value in digests)):
        raise ValueError("matched_prompt_parity_history_selection_invalid")
    if (type(protocol.get("withheld_example_count")) is not int
            or protocol["withheld_example_count"] < 0
            or not _is_digest(protocol.get("withheld_examples_digest"))):
        raise ValueError("matched_prompt_parity_withheld_examples_invalid")
    return ids, dict(zip(ids, digests, strict=True))


def _record_provenance(cycle_root: Path, *, record_ids: list[str],
        left_digests: dict[str, str], right_digests: dict[str, str],
        left_target: str, right_target: str) -> dict[str, Any]:
    if cycle_root.is_symlink() or not cycle_root.is_dir():
        raise ValueError("matched_prompt_parity_cycle_root_invalid")
    records_root = cycle_root / "resident-cognition" / "history" / "records"
    if records_root.is_symlink() or not records_root.is_dir():
        raise ValueError("matched_prompt_parity_history_records_unavailable")
    result: dict[str, Any] = {}
    for record_id in record_ids:
        if (not record_id.startswith("devrec-")
                or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
                    for character in record_id)):
            raise ValueError("matched_prompt_parity_record_id_invalid")
        path = records_root / f"{record_id}.json"
        record, _ = _read_json(path)
        record_digest = record.get("record_digest")
        expected_digests = {value for value in (
            left_digests.get(record_id), right_digests.get(record_id))
            if value is not None}
        if (record.get("record_id") != record_id
                or not _is_digest(record_digest)
                or expected_digests != {record_digest}):
            raise ValueError("matched_prompt_parity_source_record_binding_invalid")
        candidate = record.get("candidate")
        facts = candidate.get("selected_facts") if isinstance(candidate, dict) else None
        if not isinstance(facts, list):
            raise ValueError("matched_prompt_parity_source_facts_invalid")
        families: set[str] = set()
        source_identities: set[str] = set()
        source_fact_bindings: list[dict[str, str]] = []
        for fact in facts:
            payload = fact.get("payload") if isinstance(fact, dict) else None
            if not isinstance(payload, dict):
                continue
            family = payload.get("objective_task_family")
            source_identity = payload.get("active_model_identity_digest")
            if isinstance(family, str) and family:
                families.add(family)
                descriptor = payload.get("objective_task_descriptor")
                task_digest = (descriptor.get("task_digest")
                    if isinstance(descriptor, dict) else None)
                fact_id = fact.get("fact_id") if isinstance(fact, dict) else None
                identity = payload.get("active_model_identity")
                if (not isinstance(fact_id, str) or not fact_id
                        or not _is_digest(task_digest)
                        or not _is_digest(source_identity)
                        or not isinstance(identity, dict)
                        or _canonical_digest(identity) != source_identity):
                    raise ValueError(
                        "matched_prompt_parity_source_fact_binding_invalid")
                source_fact_bindings.append({
                    "source_fact_id": fact_id,
                    "source_task_digest": task_digest,
                    "source_active_model_identity_digest": source_identity,
                    "objective_task_family": family,
                })
            if source_identity is not None:
                if not _is_digest(source_identity):
                    raise ValueError("matched_prompt_parity_source_identity_invalid")
                source_identities.add(source_identity)
        source_fact_bindings = [dict(row) for row in sorted({
            tuple(sorted(row.items())) for row in source_fact_bindings})]
        result[record_id] = {
            "record_digest": record_digest,
            "selected_by_left_target": record_id in left_digests,
            "selected_by_right_target": record_id in right_digests,
            "objective_task_families": sorted(families),
            "source_model_identity_digests": sorted(source_identities),
            "source_fact_bindings": source_fact_bindings,
            "source_identity_matches_left_target": left_target in source_identities,
            "source_identity_matches_right_target": right_target in source_identities,
            "source_identity_relation_equal_across_targets": bool(source_identities)
                and (left_target in source_identities) ==
                    (right_target in source_identities),
        }
    return result


def _validate_identity_binding(report: dict[str, Any], *, target_digest: str,
        selected_record_ids: list[str],
        provenance: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if (report.get("schema_version") not in {
                "sentientos.resident_historical_examples_cpu_preflight:v8",
                "sentientos.resident_historical_examples_cpu_preflight:v9",
                "sentientos.resident_historical_examples_cpu_preflight:v10"}
            or report.get("history_prompt_identity_policy") !=
                "matched_cross_model_identity_omitted:v1"):
        raise ValueError("matched_prompt_parity_identity_policy_report_invalid")
    by_arm = report.get("history_prompt_identity_bindings_by_arm")
    if (not isinstance(by_arm, dict)
            or set(by_arm) != {"examples_included", "examples_omitted"}
            or by_arm["examples_included"] != by_arm["examples_omitted"]):
        raise ValueError("matched_prompt_parity_identity_binding_arms_invalid")
    binding = by_arm["examples_included"]
    if not isinstance(binding, dict):
        raise ValueError("matched_prompt_parity_identity_binding_invalid")
    target_identity = binding.get("target_model_identity")
    rows = binding.get("source_target_bindings")
    if (set(binding) != {"schema_version", "policy", "target_model_identity",
            "target_active_model_identity_digest", "source_target_bindings",
            "source_target_bindings_digest", "posture", "inference_performed",
            "learning_established", "authority"}
            or binding.get("schema_version") !=
                "sentientos.history_prompt_identity_binding:v1"
            or binding.get("policy") !=
                "matched_cross_model_identity_omitted:v1"
            or not isinstance(target_identity, dict)
            or _canonical_digest(target_identity) != target_digest
            or binding.get("target_active_model_identity_digest") != target_digest
            or not isinstance(rows, list) or not rows
            or binding.get("source_target_bindings_digest") != _canonical_digest(rows)
            or binding.get("posture") !=
                "controller_verified_target_digest_omitted_from_prompt"
            or binding.get("inference_performed") is not False
            or binding.get("learning_established") is not False
            or binding.get("authority") is not False):
        raise ValueError("matched_prompt_parity_identity_binding_invalid")
    selected_ids = set(selected_record_ids)
    seen: set[tuple[str, str, str]] = set()
    bound_record_ids: set[str] = set()
    for row in rows:
        if (not isinstance(row, dict)
                or set(row) != {"record_id", "record_digest", "source_fact_id",
                    "source_task_digest", "source_active_model_identity_digest",
                    "target_active_model_identity_digest", "model_identity_relation"}
                or row.get("record_id") not in selected_ids
                or row.get("target_active_model_identity_digest") != target_digest
                or row.get("model_identity_relation") !=
                    "different_active_model_identity"
                or not _is_digest(row.get("record_digest"))
                or not _is_digest(row.get("source_task_digest"))
                or not _is_digest(row.get("source_active_model_identity_digest"))
                or row.get("source_active_model_identity_digest") == target_digest
                or not isinstance(row.get("source_fact_id"), str)
                or not row["source_fact_id"]):
            raise ValueError("matched_prompt_parity_identity_binding_row_invalid")
        source = provenance.get(row["record_id"])
        source_fact_key = (row["source_fact_id"], row["source_task_digest"],
            row["source_active_model_identity_digest"])
        source_fact_keys = ({(item["source_fact_id"], item["source_task_digest"],
            item["source_active_model_identity_digest"])
            for item in source.get("source_fact_bindings", ())
            if isinstance(item, dict)} if isinstance(source, dict) else set())
        if (not isinstance(source, dict)
                or source.get("record_digest") != row.get("record_digest")
                or row.get("source_active_model_identity_digest") not in
                    source.get("source_model_identity_digests", ())
                or source_fact_key not in source_fact_keys):
            raise ValueError("matched_prompt_parity_identity_binding_source_mismatch")
        key = (row["record_id"], row["source_fact_id"], row["source_task_digest"])
        if key in seen:
            raise ValueError("matched_prompt_parity_identity_binding_duplicate")
        seen.add(key)
        bound_record_ids.add(row["record_id"])
    if {row["record_id"] for row in rows} != selected_ids \
            or bound_record_ids != selected_ids:
        raise ValueError("matched_prompt_parity_identity_binding_selection_mismatch")
    return binding


def audit_pair(*, receipt_path: Path, left_path: Path, right_path: Path,
        left_verification_path: Path, right_verification_path: Path,
        cycle_root_path: Path
        ) -> dict[str, Any]:
    pair, pair_file_digest = _read_json(receipt_path)
    left, left_file_digest = _read_json(left_path)
    right, right_file_digest = _read_json(right_path)
    left_verification, left_verification_file_digest = _read_json(
        left_verification_path)
    right_verification, right_verification_file_digest = _read_json(
        right_verification_path)
    pair_schema = pair.get("schema_version")
    if (pair_schema not in {
            "sentientos.matched_task_commitment_pair_verification:v2",
            "sentientos.matched_task_commitment_pair_verification:v3"}
            or pair.get("verification_digest") != _canonical_digest(
                {key: value for key, value in pair.items()
                    if key != "verification_digest"})
            or pair.get("left_preflight_sha256") != left_file_digest
            or pair.get("right_preflight_sha256") != right_file_digest
            or pair.get("matched_task_commitments") is not True
            or pair.get("task_digest_recomputed") is not True
            or pair.get("distinct_model_targets") is not True
            or pair.get("inference_performed") is not False
            or pair.get("learning_established") is not False
            or pair.get("authority") is not False):
        raise ValueError("matched_prompt_parity_pair_receipt_invalid")
    allowlist_digest = pair.get("shared_history_record_allowlist_digest")
    allowlist_file_digest = pair.get(
        "shared_history_record_allowlist_file_sha256")
    for report, identity_digest in ((left,
                pair.get("left_target_model_identity_digest")),
            (right, pair.get("right_target_model_identity_digest"))):
        if (report.get("schema_version") not in {
                "sentientos.resident_historical_examples_cpu_preflight:v7",
                "sentientos.resident_historical_examples_cpu_preflight:v8",
                "sentientos.resident_historical_examples_cpu_preflight:v9",
                "sentientos.resident_historical_examples_cpu_preflight:v10"}
                or report.get("cycle_root_id") != pair.get("shared_cycle_root_id")
                or report.get("source_receipt_digest") !=
                    pair.get("shared_source_receipt_digest")
                or report.get("source_model_identity_digest") != identity_digest
                or report.get("task_digest") != pair.get("task_digest")
                or report.get("task_commitment_nonce_pair_digest") !=
                    pair.get("task_commitment_nonce_pair_digest")
                or report.get("history_record_allowlist_digest") !=
                    allowlist_digest
                or (allowlist_digest is not None and
                    report.get("history_record_allowlist_file_sha256") !=
                        allowlist_file_digest)
                or report.get("inference_performed") is not False
                or report.get("runtime_condition_created") is not False
                or report.get("learning_established") is not False
                or report.get("authority") is not False):
            raise ValueError("matched_prompt_parity_preflight_binding_invalid")
    _validate_verification(left, left_verification)
    _validate_verification(right, right_verification)
    left_ids, left_digests = _selected_records(left)
    right_ids, right_digests = _selected_records(right)
    if cycle_root_path.name != pair.get("shared_cycle_root_id"):
        raise ValueError("matched_prompt_parity_cycle_root_binding_invalid")
    shared_ids = sorted(set(left_ids) & set(right_ids))
    left_only_ids = sorted(set(left_ids) - set(right_ids))
    right_only_ids = sorted(set(right_ids) - set(left_ids))
    if any(left_digests[item] != right_digests[item] for item in shared_ids):
        raise ValueError("matched_prompt_parity_shared_record_digest_conflict")
    selected_ids = sorted(set(left_ids) | set(right_ids))
    selected_record_provenance = _record_provenance(cycle_root_path,
        record_ids=selected_ids, left_digests=left_digests,
        right_digests=right_digests,
        left_target=pair["left_target_model_identity_digest"],
        right_target=pair["right_target_model_identity_digest"])
    selected_history_applicability_relations_equal = (
        bool(selected_record_provenance)
        and all(item["source_identity_relation_equal_across_targets"]
            for item in selected_record_provenance.values()))
    left_protocol = left["historical_examples_protocol"]
    right_protocol = right["historical_examples_protocol"]
    identity_bindings = None
    if pair_schema == "sentientos.matched_task_commitment_pair_verification:v3":
        if (pair.get("history_prompt_identity_policy") !=
                "matched_cross_model_identity_omitted:v1"):
            raise ValueError("matched_prompt_parity_identity_policy_pair_invalid")
        left_binding = _validate_identity_binding(left,
            target_digest=pair["left_target_model_identity_digest"],
            selected_record_ids=left_ids, provenance=selected_record_provenance)
        right_binding = _validate_identity_binding(right,
            target_digest=pair["right_target_model_identity_digest"],
            selected_record_ids=right_ids, provenance=selected_record_provenance)
        identity_bindings = (left_binding, right_binding)
    elif (left.get("history_prompt_identity_policy") is not None
            or right.get("history_prompt_identity_policy") is not None):
        raise ValueError("matched_prompt_parity_identity_policy_receipt_missing")
    left_prompts = left_protocol.get("invocation_prompt_digests")
    right_prompts = right_protocol.get("invocation_prompt_digests")
    if (not isinstance(left_prompts, dict) or not isinstance(right_prompts, dict)
            or set(left_prompts) != {"examples_included", "examples_omitted"}
            or set(right_prompts) != set(left_prompts)
            or any(not _is_digest(value) for value in left_prompts.values())
            or any(not _is_digest(value) for value in right_prompts.values())):
        raise ValueError("matched_prompt_parity_prompt_digests_missing")
    shared_withheld = (
        left_protocol.get("withheld_example_count") ==
            right_protocol.get("withheld_example_count")
        and left_protocol.get("withheld_examples_digest") ==
            right_protocol.get("withheld_examples_digest"))
    prompt_digests_equal_by_arm = {
        arm: left_prompts[arm] == right_prompts[arm]
        for arm in ("examples_included", "examples_omitted")}
    selected_record_sets_equal = not left_only_ids and not right_only_ids
    if not selected_record_sets_equal:
        prompt_comparison_readiness_posture = "blocked_selected_history_set_mismatch"
    elif not shared_withheld:
        prompt_comparison_readiness_posture = "blocked_withheld_examples_mismatch"
    elif not selected_history_applicability_relations_equal:
        prompt_comparison_readiness_posture = (
            "blocked_source_identity_applicability_mismatch")
    elif not all(prompt_digests_equal_by_arm.values()):
        prompt_comparison_readiness_posture = (
            "blocked_model_visible_prompt_digest_mismatch")
    else:
        prompt_comparison_readiness_posture = (
            "ready_shared_task_history_and_prompt_digests")
    semantic = {
        "schema_version": "sentientos.matched_task_preflight_prompt_parity:v4",
        "pair_verification_file_sha256": pair_file_digest,
        "left_preflight_sha256": left_file_digest,
        "right_preflight_sha256": right_file_digest,
        "left_preflight_verification_sha256": left_verification_file_digest,
        "right_preflight_verification_sha256": right_verification_file_digest,
        "shared_cycle_root_id": pair["shared_cycle_root_id"],
        "shared_source_receipt_digest": pair["shared_source_receipt_digest"],
        "task_generation_seed": pair["task_generation_seed"],
        "task_family_id": pair["task_family_id"],
        "task_digest": pair["task_digest"],
        "task_commitment_nonce_pair_digest":
            pair["task_commitment_nonce_pair_digest"],
        **({"history_record_allowlist_digest": allowlist_digest}
            if isinstance(allowlist_digest, str) else {}),
        **({"history_record_allowlist_file_sha256": allowlist_file_digest}
            if isinstance(allowlist_file_digest, str) else {}),
        "left_target_model_identity_digest":
            pair["left_target_model_identity_digest"],
        "right_target_model_identity_digest":
            pair["right_target_model_identity_digest"],
        "left_selected_record_ids": left_ids,
        "right_selected_record_ids": right_ids,
        "shared_selected_record_ids": shared_ids,
        "shared_selected_record_digests": {
            item: left_digests[item] for item in shared_ids},
        "selected_record_provenance": selected_record_provenance,
        "selected_record_source_reconstructed": True,
        "selected_history_applicability_relations_equal": (
            selected_history_applicability_relations_equal),
        "left_only_selected_record_ids": left_only_ids,
        "right_only_selected_record_ids": right_only_ids,
        "left_selected_record_count": len(left_ids),
        "right_selected_record_count": len(right_ids),
        "selected_record_sets_equal": selected_record_sets_equal,
        "all_shared_record_digests_equal": True,
        "left_withheld_example_count":
            left_protocol["withheld_example_count"],
        "right_withheld_example_count":
            right_protocol["withheld_example_count"],
        "left_withheld_examples_digest":
            left_protocol["withheld_examples_digest"],
        "right_withheld_examples_digest":
            right_protocol["withheld_examples_digest"],
        "withheld_examples_equal_by_count_and_digest": shared_withheld,
        "left_prompt_digests": left_prompts,
        "right_prompt_digests": right_prompts,
        "prompt_digests_equal_by_arm": prompt_digests_equal_by_arm,
        "cross_model_prompt_comparison_ready": (
            prompt_comparison_readiness_posture ==
                "ready_shared_task_history_and_prompt_digests"),
        "prompt_comparison_readiness_posture":
            prompt_comparison_readiness_posture,
        **({"history_prompt_identity_policy":
                "matched_cross_model_identity_omitted:v1",
            "identity_bindings_verified": True,
            "left_identity_binding_digest": _canonical_digest(
                identity_bindings[0]),
            "right_identity_binding_digest": _canonical_digest(
                identity_bindings[1])}
            if identity_bindings is not None else {}),
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
        "interpretation_limit":
            "digest_parity_only_no_prompt_content_or_model_attention_claim",
    }
    return {**semantic, "audit_digest": _canonical_digest(semantic)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair-verification", required=True, type=Path)
    parser.add_argument("--left-report", required=True, type=Path)
    parser.add_argument("--right-report", required=True, type=Path)
    parser.add_argument("--left-preflight-verification", required=True, type=Path)
    parser.add_argument("--right-preflight-verification", required=True, type=Path)
    parser.add_argument("--cycle-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_pair(receipt_path=args.pair_verification,
        left_path=args.left_report, right_path=args.right_report,
        left_verification_path=args.left_preflight_verification,
        right_verification_path=args.right_preflight_verification,
        cycle_root_path=args.cycle_root)
    rendered = json.dumps(report, sort_keys=True, indent=2,
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
    except (OSError, TypeError, ValueError) as exc:
        print("matched_prompt_parity_error:" + str(exc), file=sys.stderr)
        raise SystemExit(2)
