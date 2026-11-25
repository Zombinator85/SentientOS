"""Score-free condition-scoped acquisition receipt bundles.

The supervisor verifies complete outcomes before projecting only receipt and
prompt/output digest linkage into one condition's bundle. Bundle verification
checks binding and integrity; it is not a signature or an OS custody proof.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .local_model_authority import digest_payload


_SCHEMA_V1 = "sentientos.durable_learning_condition_acquisition_receipts:v1"
SCHEMA = "sentientos.durable_learning_condition_acquisition_receipts:v2"
_DIGEST = re.compile(r"[0-9a-f]{64}")
_TAGGED_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_OUTCOME_ID = re.compile(r"devexp-durable-learning-outcome-[0-9a-f]{24}")
_ATTEMPT_ID = re.compile(r"devexp-durable-learning-attempt-[0-9a-f]{24}")
_ENTRY_FIELDS_V1 = {"task_digest", "outcome_id", "outcome_digest",
    "outcome_verification_digest", "prompt_digest", "output_digest",
    "invocation_attempt_id", "invocation_receipt_id",
    "invocation_receipt_digest", "retained_state_digest",
    "available_experience_digests", "preceding_feedback_digests"}
_ENTRY_FIELDS = _ENTRY_FIELDS_V1 | {"retained_state_record_refs"}
_BUNDLE_FIELDS = {"schema_version", "protocol_id", "protocol_digest",
    "condition", "branch_id", "task_receipts",
    "source_outcomes_verified_before_projection", "score_material_included",
    "raw_prompt_or_output_included", "authority", "bundle_digest"}
_STORE_ARTIFACT_FIELDS = {"schema_version", "protocol_id",
    "protocol_digest", "condition", "branch_id", "root_identity",
    "appcontainer_sid", "bundle_file_name", "bundle_digest",
    "access_policy", "effective_access_verified",
    "peer_denial_verified", "bundle_receipt_authentication_verified",
    "authority", "artifact_digest"}
_BUNDLE_FILE = re.compile(
    r"durable-learning-condition-receipts-[0-9a-f]{24}\.json")
MAX_STAGED_BUNDLE_BYTES = 4_194_304


class ConditionReceiptBundleError(ValueError):
    """A condition-scoped receipt bundle failed its closed binding check."""


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConditionReceiptBundleError(
                "condition_receipt_bundle_duplicate_json_key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ConditionReceiptBundleError(
        "condition_receipt_bundle_non_json_constant")


def build_condition_scoped_acquisition_receipt_bundle(*, protocol: Mapping[str, Any],
        condition: str, outcomes: Sequence[Mapping[str, Any]],
        invocation_receipt_verifier: Callable[..., Mapping[str, Any]]) -> dict[str, Any]:
    """Verify and redact one complete condition's acquisition outcomes.

    The source outcomes are verified while still in supervisor custody. The
    resulting bundle contains no score, scorer attestation, prompt text, or
    model output text. It must be staged into condition-only custody whose
    identity is pinned separately before a worker may trust it.
    """
    from .durable_developmental_learning_experiment import (
        _CONDITIONS, _verify_history_state_refs,
        verify_durable_learning_outcome,
        verify_durable_learning_protocol,
    )

    verification = verify_durable_learning_protocol(protocol)
    branch_ids = verification.get("condition_branch_ids")
    expected_tasks = protocol.get("acquisition_task_digests")
    if (condition not in _CONDITIONS
            or not isinstance(branch_ids, Mapping)
            or not isinstance(branch_ids.get(condition), str)
            or not isinstance(expected_tasks, list)
            or not callable(invocation_receipt_verifier)
            or not isinstance(outcomes, Sequence)
            or isinstance(outcomes, (str, bytes))
            or len(outcomes) > 512):
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_inputs_invalid")

    selected: dict[str, dict[str, Any]] = {}
    for outcome in outcomes:
        if (not isinstance(outcome, Mapping)
                or outcome.get("condition") != condition
                or outcome.get("phase") != "acquisition"
                or outcome.get("task_digest") not in expected_tasks
                or outcome.get("task_digest") in selected):
            raise ConditionReceiptBundleError(
                "condition_receipt_bundle_outcome_binding_invalid")
        try:
            outcome_verification = verify_durable_learning_outcome(
                protocol, outcome,
                invocation_receipt_verifier=invocation_receipt_verifier)
            retained_state_record_refs = _verify_history_state_refs(
                outcome.get("retained_state_digest"),
                outcome.get("retained_state_record_refs"))
        except (TypeError, ValueError) as exc:
            raise ConditionReceiptBundleError(
                "condition_receipt_bundle_source_outcome_unverified") from exc
        selected[outcome["task_digest"]] = {
            "task_digest": outcome["task_digest"],
            "outcome_id": outcome["outcome_id"],
            "outcome_digest": outcome["outcome_digest"],
            "outcome_verification_digest": digest_payload(
                dict(outcome_verification)),
            "prompt_digest": outcome["prompt_digest"],
            "output_digest": outcome["output_digest"],
            "invocation_attempt_id": outcome["invocation_attempt_id"],
            "invocation_receipt_id": outcome["invocation_receipt_id"],
            "invocation_receipt_digest": outcome[
                "invocation_receipt_digest"],
            "retained_state_digest": outcome["retained_state_digest"],
            "retained_state_record_refs": retained_state_record_refs,
            "available_experience_digests": list(
                outcome["available_experience_digests"]),
            "preceding_feedback_digests": list(
                outcome["preceding_feedback_digests"]),
        }
    if set(selected) != set(expected_tasks):
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_acquisition_set_incomplete")
    semantic = {"schema_version": SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "protocol_digest": protocol["protocol_digest"],
        "condition": condition, "branch_id": branch_ids[condition],
        "task_receipts": [selected[task] for task in expected_tasks],
        "source_outcomes_verified_before_projection": True,
        "score_material_included": False,
        "raw_prompt_or_output_included": False,
        "authority": False}
    return {**semantic, "bundle_digest": digest_payload(semantic)}


def verify_condition_scoped_acquisition_receipt_bundle(value: Any, *,
        protocol: Mapping[str, Any], condition: str) -> dict[str, Any]:
    """Check closed shape, protocol binding, task coverage, and bundle digest.

    This does not independently reverify the original model receipts. The
    caller must bind this digest to a supervisor-created immutable manifest or
    another authenticated custody record before treating the bundle as trusted.
    """
    from .durable_developmental_learning_experiment import (
        _CONDITIONS, _verify_history_state_refs,
        verify_durable_learning_protocol,
    )

    verification = verify_durable_learning_protocol(protocol)
    branch_ids = verification.get("condition_branch_ids")
    tasks = protocol.get("acquisition_task_digests")
    if (type(value) is not dict or set(value) != _BUNDLE_FIELDS
            or condition not in _CONDITIONS
            or value.get("schema_version") not in (_SCHEMA_V1, SCHEMA)
            or value.get("protocol_id") != protocol.get("protocol_id")
            or value.get("protocol_digest") != protocol.get("protocol_digest")
            or value.get("condition") != condition
            or not isinstance(branch_ids, Mapping)
            or value.get("branch_id") != branch_ids.get(condition)
            or value.get("source_outcomes_verified_before_projection") is not True
            or value.get("score_material_included") is not False
            or value.get("raw_prompt_or_output_included") is not False
            or value.get("authority") is not False
            or not isinstance(value.get("task_receipts"), list)
            or len(value["task_receipts"]) != len(tasks)
            or value.get("bundle_digest") != digest_payload({key: item
                for key, item in value.items() if key != "bundle_digest"})):
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_invalid")

    schema_v2 = value["schema_version"] == SCHEMA
    seen_outcomes: set[str] = set()
    seen_attempts: set[str] = set()
    seen_receipts: set[str] = set()
    entry_fields = _ENTRY_FIELDS if schema_v2 else _ENTRY_FIELDS_V1
    for index, entry in enumerate(value["task_receipts"]):
        if (not isinstance(entry, Mapping) or set(entry) != entry_fields
                or entry.get("task_digest") != tasks[index]
                or not isinstance(entry.get("outcome_id"), str)
                or _OUTCOME_ID.fullmatch(entry["outcome_id"]) is None
                or any(not isinstance(entry.get(key), str)
                    or _DIGEST.fullmatch(entry[key]) is None
                    for key in ("task_digest", "outcome_digest",
                        "outcome_verification_digest", "prompt_digest",
                        "output_digest", "invocation_receipt_digest"))
                or not isinstance(entry.get("invocation_attempt_id"), str)
                or _ATTEMPT_ID.fullmatch(entry["invocation_attempt_id"]) is None
                or not isinstance(entry.get("invocation_receipt_id"), str)
                or not entry["invocation_receipt_id"]
                or entry["outcome_id"] in seen_outcomes
                or entry["invocation_attempt_id"] in seen_attempts
                or entry["invocation_receipt_id"] in seen_receipts
                or not isinstance(entry.get("retained_state_digest"), str)
                or _TAGGED_DIGEST.fullmatch(
                    entry["retained_state_digest"]) is None
                or (schema_v2 and not isinstance(
                    entry.get("retained_state_record_refs"), list))
                or any(not isinstance(entry.get(key), list)
                    or any(not isinstance(digest, str)
                        or _TAGGED_DIGEST.fullmatch(digest) is None
                        for digest in entry[key])
                    or len(set(entry[key])) != len(entry[key])
                    for key in ("available_experience_digests",
                        "preceding_feedback_digests"))):
            raise ConditionReceiptBundleError(
                "condition_receipt_bundle_entry_invalid")
        if schema_v2:
            try:
                checked_state_refs = _verify_history_state_refs(
                    entry["retained_state_digest"],
                    entry["retained_state_record_refs"])
            except (TypeError, ValueError) as exc:
                raise ConditionReceiptBundleError(
                    "condition_receipt_bundle_history_state_refs_invalid") from exc
            if checked_state_refs != entry["retained_state_record_refs"]:
                raise ConditionReceiptBundleError(
                    "condition_receipt_bundle_history_state_refs_invalid")
        seen_outcomes.add(entry["outcome_id"])
        seen_attempts.add(entry["invocation_attempt_id"])
        seen_receipts.add(entry["invocation_receipt_id"])
    return {"schema_version":
            ("sentientos.durable_learning_condition_receipt_bundle_verification:v2"
                if schema_v2 else
                "sentientos.durable_learning_condition_receipt_bundle_verification:v1"),
        "protocol_id": value["protocol_id"],
        "condition": condition,
        "branch_id": value["branch_id"],
        "bundle_digest": value["bundle_digest"],
        "task_count": len(value["task_receipts"]),
        "closed_shape_verified": True,
        "protocol_condition_task_binding_verified": True,
        "bundle_integrity_verified": True,
        "retained_state_refs_verified": schema_v2,
        "source_invocation_receipts_reverified": False,
        "custody_authenticated": False,
        "score_material_included": False,
        "authority": False}


def stage_condition_scoped_acquisition_receipt_bundle(*, root: Path,
        expected_root_identity: tuple[int, bytes], appcontainer_sid: str,
        protocol: Mapping[str, Any], condition: str,
        bundle: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Publish one immutable bundle, then grant its worker read-only access.

    The root must be a dedicated, otherwise-empty directory with a private ACL
    and matching handle-derived identity. The worker receives read/traverse
    access only to this root. Effective worker access and peer denial remain
    unverified until the live access matrix runs.
    """
    if os.name != "nt":
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_windows_custody_required")
    from .windows_appcontainer_access import grant_appcontainer_directory_access
    from .windows_handle_custody import (WindowsHandleCustodyError,
        observe_private_directory_identity, read_regular_files)
    from .windows_peer_replay_custody import publish_immutable_replay_bytes

    if (not isinstance(root, Path)
            or not isinstance(expected_root_identity, tuple)
            or len(expected_root_identity) != 2
            or type(expected_root_identity[0]) is not int
            or not isinstance(expected_root_identity[1], bytes)
            or len(expected_root_identity[1]) != 16
            or not isinstance(appcontainer_sid, str)
            or re.fullmatch(r"S-1-15-2-(?:[0-9]+-)*[0-9]+",
                appcontainer_sid) is None):
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_stage_arguments_invalid")
    try:
        bundle_snapshot = json.loads(json.dumps(dict(bundle),
            ensure_ascii=False, allow_nan=False, sort_keys=True))
        verify_condition_scoped_acquisition_receipt_bundle(
            bundle_snapshot, protocol=protocol, condition=condition)
    except (TypeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ConditionReceiptBundleError):
            raise
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_snapshot_invalid") from exc
    if observe_private_directory_identity(root,
            permitted_appcontainer_sid=appcontainer_sid) != expected_root_identity:
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_root_identity_mismatch")
    file_name = ("durable-learning-condition-receipts-" +
        bundle_snapshot["bundle_digest"][:24] + ".json")
    if _BUNDLE_FILE.fullmatch(file_name) is None:
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_file_name_invalid")
    raw = (json.dumps(bundle_snapshot, sort_keys=True, indent=2,
        ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > MAX_STAGED_BUNDLE_BYTES:
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_over_bound")
    try:
        try:
            existing = read_regular_files(root, max_entries=1,
                max_file_bytes=MAX_STAGED_BUNDLE_BYTES,
                max_total_bytes=MAX_STAGED_BUNDLE_BYTES, suffix="",
                require_private_acl=True,
                permitted_appcontainer_sid=appcontainer_sid,
                expected_root_identity=expected_root_identity)
        except WindowsHandleCustodyError as exc:
            if exc.code != "explicit_file_missing":
                raise
            existing = []
        if existing:
            if len(existing) != 1 or existing[0] != (file_name, raw):
                raise ConditionReceiptBundleError(
                    "condition_receipt_bundle_immutable_collision")
        else:
            publish_immutable_replay_bytes(root / file_name, raw,
                max_bytes=MAX_STAGED_BUNDLE_BYTES, max_entries=16,
                expected_root_identity=expected_root_identity,
                filename_policy="durable_learning_condition_receipt_bundle")
        acl = grant_appcontainer_directory_access(root=root,
            expected_directory_identity=expected_root_identity,
            appcontainer_sid=appcontainer_sid,
            access_policy="condition_receipt_read")
        if observe_private_directory_identity(root,
                permitted_appcontainer_sid=appcontainer_sid) != \
                expected_root_identity:
            raise ConditionReceiptBundleError(
                "condition_receipt_bundle_root_changed_after_acl")
        stored = read_regular_files(root, max_entries=1,
            max_file_bytes=MAX_STAGED_BUNDLE_BYTES,
            max_total_bytes=MAX_STAGED_BUNDLE_BYTES, suffix="",
            require_private_acl=True,
            permitted_appcontainer_sid=appcontainer_sid,
            expected_root_identity=expected_root_identity)
    except Exception as exc:
        if isinstance(exc, ConditionReceiptBundleError):
            raise
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_stage_failed") from exc
    if (len(stored) != 1 or stored[0][0] != file_name
            or stored[0][1] != raw):
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_readback_mismatch")
    root_identity = {"volume_serial": expected_root_identity[0],
        "file_id_hex": expected_root_identity[1].hex()}
    semantic = {"schema_version":
            "sentientos.durable_learning_condition_receipt_bundle_store:v1",
        "protocol_id": protocol["protocol_id"],
        "protocol_digest": protocol["protocol_digest"],
        "condition": condition, "branch_id": bundle_snapshot["branch_id"],
        "root_identity": root_identity,
        "appcontainer_sid": appcontainer_sid,
        "bundle_file_name": file_name,
        "bundle_digest": bundle_snapshot["bundle_digest"],
        "access_policy": "condition_receipt_read",
        "effective_access_verified": False,
        "peer_denial_verified": False,
        "bundle_receipt_authentication_verified": False,
        "authority": False}
    artifact = {**semantic, "artifact_digest": digest_payload(semantic)}
    return artifact, {**acl, "file_readback_verified": True,
        "root_identity_stable": True,
        "effective_access_verified": False,
        "peer_denial_verified": False,
        "retention_contrast_eligible": False,
        "authority": False}


def load_staged_condition_scoped_acquisition_receipt_bundle(*, root: Path,
        expected_root_identity: tuple[int, bytes], appcontainer_sid: str,
        artifact: Mapping[str, Any], protocol: Mapping[str, Any],
        condition: str) -> dict[str, Any]:
    """Read one pinned bundle through reparse-safe custody and verify it."""
    if os.name != "nt":
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_windows_custody_required")
    from .windows_handle_custody import read_regular_files

    if (not isinstance(root, Path)
            or not isinstance(expected_root_identity, tuple)
            or len(expected_root_identity) != 2
            or type(expected_root_identity[0]) is not int
            or not isinstance(expected_root_identity[1], bytes)
            or len(expected_root_identity[1]) != 16
            or not isinstance(artifact, Mapping)
            or set(artifact) != _STORE_ARTIFACT_FIELDS
            or artifact.get("schema_version") !=
                "sentientos.durable_learning_condition_receipt_bundle_store:v1"
            or artifact.get("protocol_id") != protocol.get("protocol_id")
            or artifact.get("protocol_digest") != protocol.get("protocol_digest")
            or artifact.get("condition") != condition
            or not isinstance(artifact.get("appcontainer_sid"), str)
            or not isinstance(appcontainer_sid, str)
            or re.fullmatch(r"S-1-15-2-(?:[0-9]+-)*[0-9]+",
                artifact["appcontainer_sid"]) is None
            or artifact["appcontainer_sid"].casefold() != appcontainer_sid.casefold()
            or artifact.get("access_policy") != "condition_receipt_read"
            or artifact.get("effective_access_verified") is not False
            or artifact.get("peer_denial_verified") is not False
            or artifact.get("bundle_receipt_authentication_verified") is not False
            or artifact.get("authority") is not False
            or not isinstance(artifact.get("bundle_file_name"), str)
            or _BUNDLE_FILE.fullmatch(artifact["bundle_file_name"]) is None
            or not isinstance(artifact.get("bundle_digest"), str)
            or _DIGEST.fullmatch(artifact["bundle_digest"]) is None
            or artifact.get("bundle_file_name") != (
                "durable-learning-condition-receipts-" +
                artifact["bundle_digest"][:24] + ".json")):
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_store_artifact_invalid")
    semantic = {key: item for key, item in artifact.items()
        if key != "artifact_digest"}
    if (artifact.get("artifact_digest") != digest_payload(semantic)
            or artifact.get("root_identity") != {
                "volume_serial": expected_root_identity[0],
                "file_id_hex": expected_root_identity[1].hex()}):
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_store_artifact_digest_invalid")
    try:
        raw = read_regular_files(root, max_entries=1,
            max_file_bytes=MAX_STAGED_BUNDLE_BYTES,
            max_total_bytes=MAX_STAGED_BUNDLE_BYTES, suffix="",
            require_private_acl=True,
            permitted_appcontainer_sid=appcontainer_sid,
            expected_root_identity=expected_root_identity)
        if len(raw) != 1:
            raise ConditionReceiptBundleError(
                "condition_receipt_bundle_file_missing")
        value = json.loads(raw[0][1].decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant)
    except ConditionReceiptBundleError:
        raise
    except Exception as exc:
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_file_invalid") from exc
    verified = verify_condition_scoped_acquisition_receipt_bundle(
        value, protocol=protocol, condition=condition)
    if (raw[0][0] != artifact["bundle_file_name"]
            or value.get("bundle_digest") != artifact.get("bundle_digest")
            or value.get("branch_id") != artifact.get("branch_id")):
        raise ConditionReceiptBundleError(
            "condition_receipt_bundle_store_binding_mismatch")
    return {"bundle": value, "bundle_verification": verified,
        "store_artifact_digest": artifact["artifact_digest"],
        "file_readback_verified": True,
        "custody_authenticated": False,
        "effective_access_verified": False,
        "peer_denial_verified": False,
        "authority": False}
