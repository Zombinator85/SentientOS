"""CPU-only binding checks for matched cross-model historical examples."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping


class IdentityNeutralHistoryBindingError(ValueError):
    """The saved audit, allowlist, source evidence, or protocol do not bind."""


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _read_json_with_file_digest(path: Path, *, label: str
        ) -> tuple[dict[str, Any], str]:
    if not path.is_absolute():
        path = path.resolve()
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise IdentityNeutralHistoryBindingError(label + "_symlink")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise IdentityNeutralHistoryBindingError(label + "_unreadable") from exc
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size > 8 * 1024 * 1024):
            raise IdentityNeutralHistoryBindingError(label + "_file_invalid")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(remaining, 64 * 1024))
            if not chunk:
                raise IdentityNeutralHistoryBindingError(label + "_truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
        if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise IdentityNeutralHistoryBindingError(label + "_changed_during_read")
    finally:
        os.close(fd)
    raw = b"".join(chunks)

    def object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise IdentityNeutralHistoryBindingError(label + "_duplicate_key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise IdentityNeutralHistoryBindingError(label + "_invalid_constant:" + value)

    try:
        value = json.loads(raw.decode("utf-8"),
            object_pairs_hook=object_without_duplicates,
            parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise IdentityNeutralHistoryBindingError(label + "_invalid_json") from exc
    if not isinstance(value, dict):
        raise IdentityNeutralHistoryBindingError(label + "_object_required")
    return value, "sha256:" + hashlib.sha256(raw).hexdigest()


def _record_provenance_valid(*, record_digest: str, provenance: Any,
        target_digests: set[Any], task_digest: Any) -> bool:
    if not isinstance(provenance, Mapping):
        return False
    sources = provenance.get("source_model_identity_digests")
    bindings = provenance.get("source_fact_bindings")
    families = provenance.get("objective_task_families")
    if (provenance.get("record_digest") != record_digest
            or provenance.get("selected_by_left_target") is not True
            or provenance.get("selected_by_right_target") is not True
            or provenance.get("source_identity_matches_left_target") is not False
            or provenance.get("source_identity_matches_right_target") is not False
            or provenance.get("source_identity_relation_equal_across_targets") is not True
            or not isinstance(sources, list) or not sources
            or any(not isinstance(value, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
                or value in target_digests for value in sources)
            or len(set(sources)) != len(sources)
            or not isinstance(bindings, list) or not bindings
            or not isinstance(families, list) or not families
            or any(not isinstance(item, str) or not item for item in families)):
        return False
    bound_sources: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, Mapping):
            return False
        family = binding.get("objective_task_family")
        source_identity = binding.get("source_active_model_identity_digest")
        source_fact_id = binding.get("source_fact_id")
        source_task_digest = binding.get("source_task_digest")
        if (family not in families or not isinstance(source_fact_id, str)
                or not source_fact_id or not isinstance(source_task_digest, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", source_task_digest) is None
                or source_task_digest == task_digest
                or not isinstance(source_identity, str)
                or source_identity not in sources):
            return False
        bound_sources.add(source_identity)
    return bound_sources == set(sources)


def verify_identity_neutral_history_binding(*, objective_task: Any,
        protocol: Mapping[str, Any], target_identity_digest: str,
        parity_audit_path: str | None, allowlist_path: str | None,
        pair_verification_path: str | None, left_preflight_path: str | None,
        right_preflight_path: str | None,
        left_preflight_verification_path: str | None,
        right_preflight_verification_path: str | None,
        source_cycle_root: Path) -> dict[str, Any] | None:
    """Reconstruct identity-neutral parity and bind it to a frozen runtime pair."""
    descriptor = objective_task.public_descriptor()
    optional_paths = (parity_audit_path, allowlist_path, pair_verification_path,
        left_preflight_path, right_preflight_path,
        left_preflight_verification_path, right_preflight_verification_path)
    if descriptor.get("history_prompt_identity_policy") is None:
        if any(value is not None for value in optional_paths):
            raise IdentityNeutralHistoryBindingError(
                "unexpected_identity_neutral_audit")
        return None
    if (descriptor.get("history_prompt_identity_policy") !=
            "matched_cross_model_identity_omitted:v1"
            or any(not isinstance(value, str) or not value.strip()
                for value in optional_paths)):
        raise IdentityNeutralHistoryBindingError("identity_neutral_audit_required")

    audit, audit_file_digest = _read_json_with_file_digest(
        Path(parity_audit_path).expanduser(), label="parity_audit")
    allowlist, allowlist_file_digest = _read_json_with_file_digest(
        Path(allowlist_path).expanduser(), label="allowlist")
    try:
        from analysis.audit_matched_task_commitment_prompt_parity import audit_pair
        reconstructed = audit_pair(
            receipt_path=Path(pair_verification_path).expanduser(),
            left_path=Path(left_preflight_path).expanduser(),
            right_path=Path(right_preflight_path).expanduser(),
            left_verification_path=Path(
                left_preflight_verification_path).expanduser(),
            right_verification_path=Path(
                right_preflight_verification_path).expanduser(),
            cycle_root_path=source_cycle_root)
    except (OSError, TypeError, ValueError) as exc:
        raise IdentityNeutralHistoryBindingError(
            "source_parity_reconstruction_failed") from exc

    audit_semantic = {key: value for key, value in audit.items()
        if key != "audit_digest"}
    allowlist_semantic = {key: value for key, value in allowlist.items()
        if key != "allowlist_digest"}
    ids = allowlist.get("record_ids")
    record_digests = allowlist.get("record_digests")
    if (not isinstance(ids, list) or not ids
            or any(not isinstance(item, str) or not item for item in ids)
            or len(set(ids)) != len(ids)
            or not isinstance(record_digests, Mapping)
            or set(record_digests) != set(ids)
            or any(not isinstance(value, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
                for value in record_digests.values())):
        raise IdentityNeutralHistoryBindingError("allowlist_selection_invalid")
    target_digests = {audit.get("left_target_model_identity_digest"),
        audit.get("right_target_model_identity_digest")}
    provenance = audit.get("selected_record_provenance")
    provenance_valid = (isinstance(provenance, Mapping)
        and set(provenance) == set(ids)
        and all(_record_provenance_valid(record_digest=record_digests[record_id],
            provenance=provenance[record_id], target_digests=target_digests,
            task_digest=descriptor.get("task_digest")) for record_id in ids))
    if (audit.get("schema_version") !=
            "sentientos.matched_task_preflight_prompt_parity:v4"
            or reconstructed != audit
            or audit.get("audit_digest") != _canonical_digest(audit_semantic)
            or audit.get("cross_model_prompt_comparison_ready") is not True
            or audit.get("identity_bindings_verified") is not True
            or audit.get("selected_record_source_reconstructed") is not True
            or audit.get("selected_history_applicability_relations_equal") is not True
            or audit.get("selected_record_sets_equal") is not True
            or audit.get("withheld_examples_equal_by_count_and_digest") is not True
            or len(target_digests) != 2 or provenance_valid is not True
            or audit.get("learning_established") is not False
            or audit.get("inference_performed") is not False
            or audit.get("all_shared_record_digests_equal") is not True
            or audit.get("left_selected_record_ids") != ids
            or audit.get("right_selected_record_ids") != ids
            or audit.get("shared_selected_record_ids") != ids
            or not isinstance(audit.get("prompt_digests_equal_by_arm"), Mapping)
            or set(audit["prompt_digests_equal_by_arm"]) != {
                "examples_included", "examples_omitted"}
            or any(value is not True for value in
                audit["prompt_digests_equal_by_arm"].values())
            or allowlist.get("schema_version") !=
                "sentientos.historical_examples_record_allowlist:v1"
            or allowlist.get("allowlist_digest") !=
                _canonical_digest(allowlist_semantic)
            or audit.get("history_record_allowlist_digest") !=
                allowlist.get("allowlist_digest")
            or audit.get("history_record_allowlist_file_sha256") !=
                allowlist_file_digest
            or allowlist.get("task_digest") != descriptor.get("task_digest")
            or allowlist.get("cycle_root_id") != source_cycle_root.name
            or audit.get("task_digest") != descriptor.get("task_digest")
            or audit.get("shared_cycle_root_id") != source_cycle_root.name
            or audit.get("shared_selected_record_digests") != dict(record_digests)
            or allowlist.get("inference_performed") is not False
            or allowlist.get("learning_established") is not False
            or allowlist.get("authority") is not False
            or target_identity_digest not in target_digests
            or protocol.get("history_record_ids") != ids
            or protocol.get("history_record_digests") !=
                [record_digests[item] for item in ids]):
        raise IdentityNeutralHistoryBindingError(
            "identity_neutral_history_binding_mismatch")
    return {"status": "verified_identity_neutral_shared_history_binding",
        "parity_audit_digest": audit["audit_digest"],
        "parity_audit_file_digest": audit_file_digest,
        "source_parity_reconstruction_verified": True,
        "allowlist_digest": allowlist["allowlist_digest"],
        "allowlist_file_digest": allowlist_file_digest,
        "selected_record_ids": list(ids),
        "selected_record_digests": [record_digests[item] for item in ids],
        "authority": False, "inference_performed": False,
        "learning_established": False}
