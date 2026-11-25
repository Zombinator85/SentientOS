"""Verify equal history delivery in a matched pair of no-inference previews.

The paired campaign preflight binds owner-selected history, while each runtime
preview records the smaller set actually projected by the prompt binder. This
read-only audit checks that the delivered, score-bound history content matches
across targets and remains tied to the paired plan and its held-out task.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.developmental_model_replacement_experiment import (  # noqa: E402
    rootless_integer_affine_transfer_task_pair,
)

CONDITIONS = ("history_present", "history_withheld", "history_restored")
TARGETS = ("same_model_artifact_target", "different_model_artifact_target")
HEX = re.compile(r"[0-9a-f]{64}")
SHA = re.compile(r"sha256:[0-9a-f]{64}")


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _read_object(path: Path, *, max_bytes: int = 16 * 1024 * 1024) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("matched_preview_input_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("matched_preview_object_required")
    return value


def _verify_digest_envelope(value: Mapping[str, Any], digest_key: str) -> str:
    semantic = {key: item for key, item in value.items() if key != digest_key}
    expected = _canonical_digest(semantic)
    claimed = value.get(digest_key)
    if claimed not in {expected, expected.removeprefix("sha256:")}:
        raise ValueError("matched_preview_digest_mismatch:" + digest_key)
    return expected


def _file_ref(root: Path, reference: Any) -> tuple[dict[str, Any], Path]:
    if not isinstance(reference, Mapping) or set(reference) != {"path", "sha256"}:
        raise ValueError("matched_preview_file_reference_invalid")
    rel = reference.get("path")
    digest = reference.get("sha256")
    if (not isinstance(rel, str) or not rel or "\\" in rel
            or Path(rel).is_absolute() or ".." in Path(rel).parts
            or not isinstance(digest, str) or HEX.fullmatch(digest) is None):
        raise ValueError("matched_preview_file_reference_invalid")
    path = root / Path(rel)
    if (path.is_symlink() or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
        raise ValueError("matched_preview_file_digest_mismatch")
    return _read_object(path), path


def _projected_history(preview: Mapping[str, Any]) -> dict[str, Any]:
    evidence = preview.get("owner_preview_evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("matched_preview_owner_evidence_missing")
    if ("sha256:" + hashlib.sha256(json.dumps(dict(evidence), sort_keys=True,
            separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            .encode("utf-8")).hexdigest()
            != preview.get("runtime_owner_preview_digest")):
        raise ValueError("matched_preview_owner_evidence_digest_mismatch")
    conditions = evidence.get("conditions")
    if not isinstance(conditions, Mapping) or set(conditions) != set(CONDITIONS):
        raise ValueError("matched_preview_owner_conditions_invalid")

    def signature(condition: str) -> list[dict[str, Any]]:
        row = conditions.get(condition)
        records = row.get("projected_records") if isinstance(row, Mapping) else None
        if not isinstance(records, list):
            raise ValueError("matched_preview_projected_records_invalid")
        result = []
        for record in records:
            if not isinstance(record, Mapping):
                raise ValueError("matched_preview_projected_record_invalid")
            required = {
                "record_id", "record_digest", "prompt_packet_digest",
                "prompt_packet_serialization_present", "experience_count",
                "example_count", "examples_digest",
                "score_bound_source_run_digests", "score_bound_source_score_digests",
            }
            if (set(record) != required
                    or not isinstance(record.get("record_id"), str)
                    or not isinstance(record.get("record_digest"), str)
                    or SHA.fullmatch(record["record_digest"]) is None
                    or not isinstance(record.get("prompt_packet_digest"), str)
                    or SHA.fullmatch(record["prompt_packet_digest"]) is None
                    or not isinstance(record.get("examples_digest"), str)
                    or SHA.fullmatch(record["examples_digest"]) is None
                    or record.get("prompt_packet_serialization_present") is not True
                    or type(record.get("experience_count")) is not int
                    or record["experience_count"] < 0
                    or type(record.get("example_count")) is not int
                    or record["example_count"] < 0
                    or any(not isinstance(record.get(key), list)
                        or record[key] != sorted(set(record[key]))
                        or any(not isinstance(digest, str) or SHA.fullmatch(digest) is None
                            for digest in record[key])
                        for key in ("score_bound_source_run_digests",
                            "score_bound_source_score_digests"))):
                raise ValueError("matched_preview_projected_record_invalid")
            result.append(dict(record))
        return result

    present = signature("history_present")
    restored = signature("history_restored")
    withheld = signature("history_withheld")
    if present != restored or withheld:
        raise ValueError("matched_preview_condition_history_mismatch")
    return {"history_present": present, "history_restored": restored,
        "history_withheld": withheld}


def _score_bound_history(signatures: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Compare source experience while leaving target-bound prompt packets visible."""
    return [{key: record[key] for key in (
        "record_id", "record_digest", "experience_count", "example_count",
        "examples_digest", "score_bound_source_run_digests",
        "score_bound_source_score_digests")}
        for record in signatures["history_present"]]


def _verify_seeded_task_specifications(*, plans: Mapping[str, Mapping[str, Any]],
        seeds: Any, task_family_id: str, probe_count: int,
        expected_transfer_probes: list[int]) -> str:
    if (not isinstance(seeds, list) or len(seeds) != 2
            or any(type(seed) is not int for seed in seeds)
            or any(plan.get("ordered_task_generation_seeds") != seeds
                for plan in plans.values())):
        raise ValueError("matched_preview_task_seed_binding_invalid")
    relative_source = "sentientos/developmental_model_replacement_experiment.py"
    pinned_hashes = []
    for plan in plans.values():
        pins = plan.get("experiment_implementation_sha256")
        pinned = pins.get(relative_source) if isinstance(pins, Mapping) else None
        if not isinstance(pinned, str) or HEX.fullmatch(pinned) is None:
            raise ValueError("matched_preview_task_factory_pin_missing")
        pinned_hashes.append(pinned)
    if len(set(pinned_hashes)) != 1:
        raise ValueError("matched_preview_task_factory_pin_mismatch")
    source = REPO_ROOT / relative_source
    if (source.is_symlink() or not source.is_file()
            or hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")
                .replace(b"\r", b"\n")).hexdigest() != pinned_hashes[0]):
        raise ValueError("matched_preview_task_factory_source_mismatch")

    for seed_index, seed in enumerate(seeds):
        left_acquisition, left_transfer = rootless_integer_affine_transfer_task_pair(
            seed, task_family_id=task_family_id,
            transfer_probe_count=probe_count)
        right_acquisition, right_transfer = rootless_integer_affine_transfer_task_pair(
            seed, task_family_id=task_family_id,
            transfer_probe_count=probe_count)
        if (left_acquisition.specification() != right_acquisition.specification()
                or left_transfer.specification() != right_transfer.specification()
                or not left_transfer.specification().get(
                    "requires_task_family_history")
                or left_transfer.specification().get("task_family_id")
                    != task_family_id):
            raise ValueError("matched_preview_seeded_task_specification_mismatch")
        if (seed_index == 0
                and left_transfer.public_descriptor().get("probe_inputs")
                    != expected_transfer_probes):
            raise ValueError("matched_preview_seeded_probe_reconstruction_mismatch")
    return pinned_hashes[0]


def _verify_pinned_preview_replay(*, receipt_path: Path,
        pair_digest: str, preview_digests: Mapping[str, str]) -> dict[str, Any]:
    receipt = _read_object(receipt_path)
    semantic = {key: value for key, value in receipt.items()
        if key != "receipt_digest"}
    expected = _canonical_digest(semantic)
    if (receipt.get("schema_version") !=
            "sentientos.rootless_matched_model_target_bundle_replay:v1"
            or receipt.get("receipt_digest") != expected):
        raise ValueError("matched_preview_source_replay_receipt_invalid")
    result = receipt.get("verification_result")
    verifications = receipt.get("runtime_preview_verifications")
    if (not isinstance(result, Mapping) or result.get("status") != "verified"
            or result.get("pair_digest") != pair_digest
            or result.get("inference_performed") is not False
            or result.get("learning_established") is not False
            or result.get("authority") is not False
            or not isinstance(verifications, list) or len(verifications) != 2):
        raise ValueError("matched_preview_source_replay_scope_invalid")
    by_target = {row.get("target"): row for row in verifications
        if isinstance(row, Mapping)}
    if set(by_target) != set(TARGETS):
        raise ValueError("matched_preview_source_replay_targets_invalid")
    for target, preview_digest in preview_digests.items():
        row = by_target[target]
        if (row.get("preview_digest") != preview_digest
                or row.get("implementation_matches_current") is not True
                or row.get("owner_payload_digest_verified") is not True
                or row.get("report_origin_attested") is not False
                or row.get("inference_performed") is not False
                or row.get("learning_established") is not False
                or row.get("authority") is not False):
            raise ValueError("matched_preview_source_replay_binding_mismatch")
    return {
        "receipt_digest": receipt["receipt_digest"],
        "launcher_sha256": receipt.get("launcher_sha256"),
        "bundle_manifest_digest": receipt.get("bundle_manifest_digest"),
        "runtime_preview_verifications": [
            dict(by_target[target]) for target in TARGETS],
        "report_origin_attested": False,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }


def verify(*, pair_path: Path, left_preview_path: Path,
        right_preview_path: Path, artifact_root: Path,
        pinned_preview_replay_path: Path | None = None) -> dict[str, Any]:
    pair = _read_object(pair_path)
    pair_digest = _verify_digest_envelope(pair, "pair_digest")
    members = pair.get("members")
    shared = pair.get("shared")
    equivalence = pair.get("equivalence_checks")
    if (pair.get("schema_version") != "sentientos.rootless_matched_model_target_pair:v2"
            or not isinstance(members, Mapping) or set(members) != set(TARGETS)
            or not isinstance(shared, Mapping)
            or not isinstance(equivalence, Mapping)
            or any(equivalence.get(key) is not True for key in (
                "same_implementation_pin", "same_task_family",
                "same_task_generation_seeds", "same_backend_seeds",
                "same_cycle0_transfer_probes"))):
        raise ValueError("matched_preview_pair_schema_invalid")
    evidence: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    plans: dict[str, Mapping[str, Any]] = {}
    for key, preview_path in zip(TARGETS, (left_preview_path, right_preview_path)):
        member = members[key]
        if not isinstance(member, Mapping):
            raise ValueError("matched_preview_pair_member_invalid")
        plan, _ = _file_ref(artifact_root, member.get("plan_file"))
        plans[key] = plan
        preflight, _ = _file_ref(artifact_root, member.get("owner_report_file"))
        preview = _read_object(preview_path)
        _verify_digest_envelope(preview, "audit_digest")
        if (preview.get("schema_version") !=
                "sentientos.rootless_planned_cycle_runtime_owner_preview:v5"
                or preview.get("campaign_id") != member.get("campaign_id")
                or preview.get("cycle_id") != member.get("cycle_id")
                or preview.get("plan_digest") != member.get("plan_digest")
                or plan.get("plan_digest") != member.get("plan_digest")
                or plan.get("campaign_id") != member.get("campaign_id")
                or plan.get("task_family_id") != shared.get("task_family_id")
                or plan.get("transfer_probe_count") !=
                    len(shared.get("heldout_probe_set", []))
                or plan.get("ordered_task_generation_seeds") !=
                    shared.get("ordered_task_generation_seeds")
                or plan.get("ordered_backend_seeds") !=
                    shared.get("ordered_backend_seeds")
                or preview.get("target_model_identity_digest") !=
                    "sha256:" + str(member.get("target_model_identity_digest"))
                or preview.get("source_history_boundary_digest") !=
                    shared.get("initial_history_boundary_digest")
                or preview.get("implementation_digest") !=
                    shared.get("implementation_digest")
                or preview.get("target_task_family_id") != shared.get("task_family_id")
                or preview.get("target_task_probe_inputs") !=
                    shared.get("heldout_probe_set")
                or preflight.get("binder_selected_record_ids") !=
                    preview.get("history_record_ids")
                or preflight.get("binder_selected_record_digests") !=
                    preview.get("history_record_digests")
                or preflight.get("audit_digest") !=
                    member.get("owner_report_digest")
                or preflight.get("campaign_id") != member.get("campaign_id")
                or preflight.get("plan_digest") != member.get("plan_digest")
                or preflight.get("cycle_id") != member.get("cycle_id")
                or preflight.get("target_model_identity_digest") !=
                    member.get("target_model_identity_digest")
                or preflight.get("prior_history_boundary_digest") !=
                    shared.get("initial_history_boundary_digest")
                or preflight.get("inference_performed") is not False):
            raise ValueError("matched_preview_member_binding_mismatch")
        owner_selected = member.get("selected_history_record_ids")
        delivered_ids = preview.get("history_record_ids")
        delivered_digests = preview.get("history_record_digests")
        if (not isinstance(owner_selected, list)
                or not isinstance(delivered_ids, list) or not delivered_ids
                or not isinstance(delivered_digests, list)
                or len(delivered_ids) != len(delivered_digests)
                or not set(delivered_ids).issubset(set(owner_selected))
                or preview.get("condition_order") != list(CONDITIONS)
                or preview.get("condition_selected_record_ids") != {
                    "history_present": delivered_ids,
                    "history_withheld": [],
                    "history_restored": delivered_ids}
                or preview.get("condition_selected_record_digests") != {
                    "history_present": delivered_digests,
                    "history_withheld": [],
                    "history_restored": delivered_digests}
                or preview.get("inference_performed") is not False
                or preview.get("learning_established") is not False
                or preview.get("authority") is not False
                or preview.get("full_prompt_text_included") is not False
                or preview.get("model_outputs_included") is not False):
            raise ValueError("matched_preview_delivery_contract_invalid")
        signatures = _projected_history(preview)
        for condition in ("history_present", "history_restored"):
            if ([record["record_id"] for record in signatures[condition]] != delivered_ids
                    or [record["record_digest"] for record in signatures[condition]]
                        != delivered_digests):
                raise ValueError("matched_preview_projected_history_binding_invalid")
        evidence[key] = (preview, signatures)

    left, right = (evidence[key] for key in TARGETS)
    task_factory_source_sha256 = _verify_seeded_task_specifications(
        plans=plans, seeds=shared.get("ordered_task_generation_seeds"),
        task_family_id=str(shared.get("task_family_id")),
        probe_count=len(shared.get("heldout_probe_set", [])),
        expected_transfer_probes=shared.get("heldout_probe_set"))
    left_preview, left_history = left
    right_preview, right_history = right
    left_ids = left_preview["history_record_ids"]
    right_ids = right_preview["history_record_ids"]
    left_digests = left_preview["history_record_digests"]
    right_digests = right_preview["history_record_digests"]
    left_score_bound = _score_bound_history(left_history)
    right_score_bound = _score_bound_history(right_history)
    if (left_ids != right_ids or left_digests != right_digests
            or left_score_bound != right_score_bound
            or left_preview["condition_prompt_sizes"] !=
                right_preview["condition_prompt_sizes"]
            or left_preview["target_model_identity_digest"] ==
                right_preview["target_model_identity_digest"]):
        raise ValueError("matched_preview_cross_target_parity_failed")
    result = {
        "schema_version": "sentientos.rootless_matched_model_target_runtime_preview_parity:v1",
        "pair_digest": pair_digest,
        "previews": {
            "same_model_artifact_target": {
                "campaign_id": left_preview["campaign_id"],
                "cycle_id": left_preview["cycle_id"],
                "preview_digest": left_preview["audit_digest"],
                "target_model_identity_digest":
                    left_preview["target_model_identity_digest"],
                "condition_prompt_digests": left_preview["condition_prompt_digests"],
                "owner_selected_record_ids":
                    members[TARGETS[0]]["selected_history_record_ids"],
                "delivered_record_ids": left_ids,
                "delivered_record_digests": left_digests,
                "condition_task_digests": left_preview[
                    "condition_task_digests"],
                "prompt_packet_digests": {
                    condition: [record["prompt_packet_digest"] for record in
                        left_history[condition]]
                    for condition in ("history_present", "history_restored")},
            },
            "different_model_artifact_target": {
                "campaign_id": right_preview["campaign_id"],
                "cycle_id": right_preview["cycle_id"],
                "preview_digest": right_preview["audit_digest"],
                "target_model_identity_digest":
                    right_preview["target_model_identity_digest"],
                "condition_prompt_digests": right_preview["condition_prompt_digests"],
                "owner_selected_record_ids":
                    members[TARGETS[1]]["selected_history_record_ids"],
                "delivered_record_ids": right_ids,
                "delivered_record_digests": right_digests,
                "condition_task_digests": right_preview[
                    "condition_task_digests"],
                "prompt_packet_digests": {
                    condition: [record["prompt_packet_digest"] for record in
                        right_history[condition]]
                    for condition in ("history_present", "history_restored")},
            },
        },
        "shared_delivered_score_bound_history": left_score_bound,
        "condition_order": list(CONDITIONS),
        "heldout_probe_set": shared["heldout_probe_set"],
        "heldout_probe_count": len(shared["heldout_probe_set"]),
        "ordered_task_generation_seeds":
            shared["ordered_task_generation_seeds"],
        "ordered_backend_seeds": shared["ordered_backend_seeds"],
        "task_factory_source_sha256": task_factory_source_sha256,
        "nonce_stripped_task_specifications_match": True,
        "present_and_restored_share_exact_history": True,
        "withheld_history_empty": True,
        "cross_target_score_bound_history_evidence_matches": True,
        "condition_task_digests_match": (
            left_preview["condition_task_digests"] ==
            right_preview["condition_task_digests"]),
        "seeded_task_contract_matches": True,
        "task_digest_difference_posture":
            "public_task_digest_commits_to_each_task_private_nonce; "
            "seeded_family_and_probe_inputs_match",
        "prompt_packet_serializations_match": (
            [row["prompt_packet_digest"] for row in
                left_history["history_present"]] ==
            [row["prompt_packet_digest"] for row in
                right_history["history_present"]]),
        "prompt_sizes_match": True,
        "prompt_digests_match": (
            left_preview["condition_prompt_digests"] ==
            right_preview["condition_prompt_digests"]),
        "prompt_digest_parity_interpretation":
            "full_prompt_digest_equality_is_not_required_for_distinct_target_identities; prompt text is not exported",
        "model_loaded": False,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    if pinned_preview_replay_path is not None:
        preview_digests = {
            "same_model_artifact_target": left_preview["audit_digest"],
            "different_model_artifact_target": right_preview["audit_digest"],
        }
        result["pinned_source_runtime_preview_replay"] = (
            _verify_pinned_preview_replay(
                receipt_path=pinned_preview_replay_path,
                pair_digest=pair_digest,
                preview_digests=preview_digests))
    return {**result, "verification_digest": _canonical_digest(result)}


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    if (path.name in {"", ".", ".."} or path.parent.is_symlink()
            or not path.parent.is_dir()):
        raise ValueError("matched_preview_output_path_invalid")
    path = path.parent.resolve(strict=True) / path.name
    if path.exists() or path.is_symlink():
        raise ValueError("matched_preview_output_path_invalid")
    rendered = json.dumps(dict(value), sort_keys=True, indent=2,
        ensure_ascii=False, allow_nan=False) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(rendered)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", required=True, type=Path)
    parser.add_argument("--left-preview", required=True, type=Path)
    parser.add_argument("--right-preview", required=True, type=Path)
    parser.add_argument("--artifact-root", type=Path, default=Path("."))
    parser.add_argument("--pinned-preview-replay", type=Path,
        help="Optional receipt from the pinned-source runtime preview replay")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = verify(pair_path=args.pair,
            left_preview_path=args.left_preview,
            right_preview_path=args.right_preview,
            artifact_root=args.artifact_root,
            pinned_preview_replay_path=args.pinned_preview_replay)
        if args.output:
            _write_exclusive(args.output, report)
            report = {**report, "report_path": str(args.output)}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("matched_runtime_preview_parity_error:" + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
