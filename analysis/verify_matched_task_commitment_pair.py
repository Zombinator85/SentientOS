"""Verify shared private task commitments across matched target preflights.

This CPU-only verifier reads the private key in scoring custody and two saved
preflight reports. It emits only report/key hashes and task commitment IDs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.developmental_model_replacement_experiment import (  # noqa: E402
    ROOTLESS_INTEGER_AFFINE_TRANSFER_TASK_FAMILY,
    ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
    derive_rootless_task_commitment_nonces,
    rootless_integer_affine_transfer_task_pair,
)

MAX_REPORT_BYTES = 8 * 1024 * 1024
MODEL_IDENTITY_IMPLEMENTATION_PATHS = (
    "sentientos/local_model.py",
    "sentientos/rootless_experimental_local_model.py",
    "sentientos/rootless_experimental_ollama_epistemic_session.py",
    "work/rootless_history_boundary_campaign.py",
)


def _read_regular(path: Path, *, maximum: int,
        private: bool = False) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ValueError("matched_task_commitment_input_unreadable") from exc
    try:
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or metadata.st_size > maximum
                or private and os.name != "nt" and metadata.st_mode & 0o077):
            raise ValueError("matched_task_commitment_input_invalid")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise ValueError("matched_task_commitment_input_truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if ((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                != (metadata.st_dev, metadata.st_ino, metadata.st_size,
                    metadata.st_mtime_ns)):
            raise ValueError("matched_task_commitment_input_changed")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("matched_task_commitment_duplicate_json_key")
        result[key] = value
    return result


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _source_sha256(path: Path) -> str:
    raw = _read_regular(path, maximum=32 * 1024 * 1024)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _normalized_source_sha256(path: Path) -> str:
    raw = _read_regular(path, maximum=32 * 1024 * 1024)
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _verify_identity_recipe_evidence(report: dict[str, Any]) -> None:
    binding = report.get("plan_binding")
    evidence = (binding.get("identity_recipe_evidence")
        if isinstance(binding, dict) else None)
    if (not isinstance(evidence, dict)
            or evidence.get("identity_digests_verified") is not True
            or evidence.get("inference_performed") is not False
            or type(evidence.get("identity_count")) is not int
            or evidence["identity_count"] < 1):
        raise ValueError("matched_task_commitment_identity_recipe_evidence_missing")
    pinned = evidence.get("pinned_identity_implementation_sha256")
    replayed = evidence.get("replay_identity_implementation_sha256")
    if not isinstance(pinned, dict) or not isinstance(replayed, dict):
        raise ValueError("matched_task_commitment_identity_recipe_pins_missing")
    if set(pinned) != set(MODEL_IDENTITY_IMPLEMENTATION_PATHS) or set(replayed) != set(pinned):
        raise ValueError("matched_task_commitment_identity_recipe_pin_set_invalid")
    for relative_path in MODEL_IDENTITY_IMPLEMENTATION_PATHS:
        expected_current = _normalized_source_sha256(
            REPO_ROOT / relative_path)
        if replayed.get(relative_path) != expected_current:
            raise ValueError("matched_task_commitment_identity_replay_source_mismatch")
        for value in (pinned[relative_path], replayed[relative_path]):
            if (not isinstance(value, str) or len(value) != 64
                    or any(character not in "0123456789abcdef" for character in value)):
                raise ValueError("matched_task_commitment_identity_recipe_pin_invalid")
    differing_paths = {path for path in pinned
        if pinned[path] != replayed[path]}
    posture = evidence.get("implementation_pin_posture")
    if (posture == "all_identity_source_pins_match" and differing_paths
            or posture == "campaign_source_pin_mismatch_replayed_against_current_identity_outputs"
                and differing_paths not in {
                    frozenset({"work/rootless_history_boundary_campaign.py"}),
                    frozenset({"work/rootless_history_boundary_campaign.py",
                        "sentientos/rootless_experimental_ollama_epistemic_session.py"})}
            or posture not in {
                "all_identity_source_pins_match",
                "campaign_source_pin_mismatch_replayed_against_current_identity_outputs"}):
        raise ValueError("matched_task_commitment_identity_recipe_posture_invalid")


def _report(path: Path) -> tuple[dict[str, Any], str]:
    raw = _read_regular(path, maximum=MAX_REPORT_BYTES)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("matched_task_commitment_nonstandard_json")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("matched_task_commitment_report_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("matched_task_commitment_report_invalid")
    return value, "sha256:" + hashlib.sha256(raw).hexdigest()


def _private_key(path: Path) -> tuple[str, str]:
    raw = _read_regular(path, maximum=64, private=True)
    if len(raw) != 64:
        raise ValueError("matched_task_commitment_key_not_private")
    try:
        key = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("matched_task_commitment_key_invalid") from exc
    if any(character not in "0123456789abcdef" for character in key):
        raise ValueError("matched_task_commitment_key_invalid")
    return key, "sha256:" + hashlib.sha256(raw).hexdigest()


def verify_pair(*, left_path: Path, right_path: Path,
        key_path: Path) -> dict[str, Any]:
    left, left_file_digest = _report(left_path)
    right, right_file_digest = _report(right_path)
    key, key_file_digest = _private_key(key_path)
    for report in (left, right):
        if (report.get("schema_version") not in {
                    "sentientos.resident_negative_guidance_prompt_preview:v2",
                    "sentientos.resident_historical_examples_cpu_preflight:v7",
                    "sentientos.resident_historical_examples_cpu_preflight:v8",
                    "sentientos.resident_historical_examples_cpu_preflight:v9",
                    "sentientos.resident_historical_examples_cpu_preflight:v10"}
                or report.get("model_loaded") is not False
                or report.get("model_invoked") is not False
                or report.get("inference_performed") is not False
                or report.get("runtime_condition_created") is not False
                or report.get("learning_established") is not False
                or report.get("authority") is not False
                or report.get("task_commitment_key_file_sha256")
                    != key_file_digest):
            raise ValueError("matched_task_commitment_report_posture_invalid")
        _verify_identity_recipe_evidence(report)
    shared_fields = ("cycle_root_id", "source_receipt_digest",
        "task_generation_seed", "task_family_id", "task_digest",
        "transfer_probe_count",
        "task_commitment_nonce_pair_digest")
    if any(left.get(field) != right.get(field) for field in shared_fields):
        raise ValueError("matched_task_commitment_targets_not_paired")
    task_factory_source = _source_sha256(REPO_ROOT /
        "sentientos/developmental_model_replacement_experiment.py")
    preflight_source = _source_sha256(REPO_ROOT /
        "scripts/preflight_resident_historical_examples_pair.py")
    resident_cognition_source = _source_sha256(REPO_ROOT /
        "sentientos/resident_developmental_cognition.py")
    if (left.get("task_factory_source_sha256") != task_factory_source
            or right.get("task_factory_source_sha256") != task_factory_source
            or left.get("preflight_source_sha256") != preflight_source
            or right.get("preflight_source_sha256") != preflight_source
            or left.get("resident_cognition_source_sha256") !=
                resident_cognition_source
            or right.get("resident_cognition_source_sha256") !=
                resident_cognition_source):
        raise ValueError("matched_task_commitment_source_pin_mismatch")
    seed = left.get("task_generation_seed")
    family = left.get("task_family_id")
    probe_count = left.get("transfer_probe_count", 3)
    if (type(seed) is not int
            or family not in {ROOTLESS_INTEGER_AFFINE_TRANSFER_TASK_FAMILY,
                ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY}
            or type(probe_count) is not int or not 1 <= probe_count <= 16):
        raise ValueError("matched_task_commitment_task_identity_invalid")
    nonces = derive_rootless_task_commitment_nonces(key, seed=seed,
        task_family_id=family)
    _, transfer_task = rootless_integer_affine_transfer_task_pair(seed,
        task_family_id=family, transfer_probe_count=probe_count,
        commitment_nonces=nonces)
    expected_task_digest = transfer_task.public_descriptor().get("task_digest")
    if left.get("task_digest") != expected_task_digest:
        raise ValueError("matched_task_commitment_task_digest_mismatch")
    expected_pair_digest = _digest({
        "schema_version": "sentientos.matched_task_commitment_pair:v1",
        "task_generation_seed": seed,
        "task_family_id": family,
        "acquisition_nonce": nonces[0],
        "transfer_nonce": nonces[1],
    })
    if left.get("task_commitment_nonce_pair_digest") != expected_pair_digest:
        raise ValueError("matched_task_commitment_nonce_digest_mismatch")
    left_allowlist_digest = left.get("history_record_allowlist_digest")
    right_allowlist_digest = right.get("history_record_allowlist_digest")
    if left_allowlist_digest is not None or right_allowlist_digest is not None:
        left_allowlist_file_digest = left.get(
            "history_record_allowlist_file_sha256")
        right_allowlist_file_digest = right.get(
            "history_record_allowlist_file_sha256")
        left_protocol = left.get("historical_examples_protocol")
        right_protocol = right.get("historical_examples_protocol")
        left_ids = (left_protocol.get("history_record_ids")
            if isinstance(left_protocol, dict) else None)
        right_ids = (right_protocol.get("history_record_ids")
            if isinstance(right_protocol, dict) else None)
        left_digests = (left_protocol.get("history_record_digests")
            if isinstance(left_protocol, dict) else None)
        right_digests = (right_protocol.get("history_record_digests")
            if isinstance(right_protocol, dict) else None)
        if (not isinstance(left_allowlist_digest, str)
                or left_allowlist_digest != right_allowlist_digest
                or not isinstance(left_allowlist_file_digest, str)
                or left_allowlist_file_digest != right_allowlist_file_digest
                or len(left_allowlist_file_digest) != 71
                or not left_allowlist_file_digest.startswith("sha256:")
                or not isinstance(left_ids, list) or not isinstance(right_ids, list)
                or not isinstance(left_digests, list)
                or not isinstance(right_digests, list)
                or dict(zip(left_ids, left_digests, strict=True))
                    != dict(zip(right_ids, right_digests, strict=True))):
            raise ValueError("matched_task_commitment_history_allowlist_mismatch")
    left_identity = left.get("source_model_identity_digest")
    right_identity = right.get("source_model_identity_digest")
    if (not isinstance(left_identity, str) or not isinstance(right_identity, str)
            or not left_identity.startswith("sha256:")
            or not right_identity.startswith("sha256:")
            or len(left_identity) != 71 or len(right_identity) != 71
            or any(character not in "0123456789abcdef"
                for character in left_identity[7:] + right_identity[7:])
            or left_identity == right_identity):
        raise ValueError("matched_task_commitment_model_targets_not_distinct")
    left_policy = left.get("history_prompt_identity_policy")
    right_policy = right.get("history_prompt_identity_policy")
    if left_policy is not None or right_policy is not None:
        if (left_policy != "matched_cross_model_identity_omitted:v1"
                or right_policy != left_policy):
            raise ValueError("matched_task_commitment_identity_policy_mismatch")
        for report, expected_target in ((left, left_identity),
                (right, right_identity)):
            bindings_by_arm = report.get(
                "history_prompt_identity_bindings_by_arm")
            if (report.get("schema_version") not in {
                    "sentientos.resident_historical_examples_cpu_preflight:v8",
                    "sentientos.resident_historical_examples_cpu_preflight:v9",
                    "sentientos.resident_historical_examples_cpu_preflight:v10"}
                    or not isinstance(bindings_by_arm, Mapping)
                    or set(bindings_by_arm) != {
                        "examples_included", "examples_omitted"}
                    or bindings_by_arm["examples_included"] !=
                        bindings_by_arm["examples_omitted"]):
                raise ValueError(
                    "matched_task_commitment_identity_binding_arms_invalid")
            binding = bindings_by_arm["examples_included"]
            target_identity = (binding.get("target_model_identity")
                if isinstance(binding, Mapping) else None)
            source_bindings = (binding.get("source_target_bindings")
                if isinstance(binding, Mapping) else None)
            if (not isinstance(binding, Mapping)
                    or binding.get("schema_version") !=
                        "sentientos.history_prompt_identity_binding:v1"
                    or binding.get("policy") != left_policy
                    or not isinstance(target_identity, Mapping)
                    or _digest(dict(target_identity)) != expected_target
                    or binding.get("target_active_model_identity_digest")
                        != expected_target
                    or not isinstance(source_bindings, list)
                    or binding.get("source_target_bindings_digest")
                        != _digest(source_bindings)
                    or any(not isinstance(item, Mapping)
                        or item.get("model_identity_relation") !=
                            "different_active_model_identity"
                        or item.get("target_active_model_identity_digest")
                            != expected_target
                        or item.get("source_active_model_identity_digest")
                            == expected_target
                        for item in source_bindings)
                    or binding.get("inference_performed") is not False
                    or binding.get("learning_established") is not False
                    or binding.get("authority") is not False):
                raise ValueError(
                    "matched_task_commitment_identity_binding_invalid")
    semantic = {
        "schema_version": ("sentientos.matched_task_commitment_pair_verification:v3"
            if left_policy is not None else
            "sentientos.matched_task_commitment_pair_verification:v2"),
        "left_preflight_sha256": left_file_digest,
        "right_preflight_sha256": right_file_digest,
        "shared_cycle_root_id": left["cycle_root_id"],
        "shared_source_receipt_digest": left["source_receipt_digest"],
        "task_commitment_key_file_sha256": key_file_digest,
        "task_factory_source_sha256": task_factory_source,
        "preflight_source_sha256": preflight_source,
        "resident_cognition_source_sha256": resident_cognition_source,
        "task_commitment_nonce_pair_digest": expected_pair_digest,
        "task_generation_seed": seed,
        "task_family_id": family,
        "task_digest": left["task_digest"],
        "left_target_model_identity_digest": left_identity,
        "right_target_model_identity_digest": right_identity,
        "matched_task_commitments": True,
        "task_digest_recomputed": True,
        "distinct_model_targets": True,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    if left_allowlist_digest is not None:
        semantic["shared_history_record_allowlist_digest"] = left_allowlist_digest
        semantic["shared_history_record_allowlist_file_sha256"] = (
            left_allowlist_file_digest)
    if left_policy is not None:
        semantic["history_prompt_identity_policy"] = left_policy
    return {**semantic, "verification_digest": _digest(semantic)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left-report", required=True, type=Path)
    parser.add_argument("--right-report", required=True, type=Path)
    parser.add_argument("--key-file", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify_pair(left_path=args.left_report,
        right_path=args.right_report, key_path=args.key_file)
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
        print("matched_task_commitment_verification_error:" + str(exc),
            file=sys.stderr)
        raise SystemExit(2)
