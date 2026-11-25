"""Model-free, condition-local verification of persisted invocation receipts."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping


_RECEIPT_ID = re.compile(r"lmrec-[0-9a-f]{24}")
_APP_CONTAINER_SID = re.compile(r"S-1-15-2-(?:[0-9]+-)*[0-9]+")
_MAX_RECEIPT_BYTES = 256 * 1024
_MAX_RECEIPTS = 12_288
_STORE_SCHEMA = "sentientos.durable_learning_condition_invocation_receipt_store:v1"
_INDEX_SCHEMA = "sentientos.durable_learning_condition_invocation_receipt_index:v1"
_STORE_FIELDS = {"schema_version", "protocol_id", "protocol_digest",
    "condition", "branch_id", "root_identity", "appcontainer_sid",
    "index_file_name", "index_digest", "receipt_count", "access_policy", "effective_access_verified",
    "peer_denial_verified", "source_receipts_reverified", "authority",
    "artifact_digest"}


def _reject_json_constant(value: str) -> None:
    raise ValueError("condition_invocation_receipt_non_json_constant")


def _decode_receipt(raw: bytes) -> Mapping[str, Any]:
    value = json.loads(raw.decode("utf-8"),
        object_pairs_hook=ConditionInvocationReceiptVerifier._reject_duplicate_keys,
        parse_constant=_reject_json_constant)
    if not isinstance(value, Mapping):
        raise ValueError("condition_invocation_receipt_shape_invalid")
    return value


def stage_condition_invocation_receipts(*, root: Path,
        expected_root_identity: tuple[int, bytes], appcontainer_sid: str,
        protocol: Mapping[str, Any], condition: str,
        receipt_refs: list[Mapping[str, str]],
        source_verifier: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Copy exact, source-verified receipts into a condition-only immutable store."""
    if os.name != "nt":
        raise ValueError("condition_invocation_receipt_store_windows_only")
    from .durable_developmental_learning_experiment import (
        verify_durable_learning_protocol)
    from .governed_local_model_invocation import validate_receipt
    from .local_model_authority import digest_payload
    from .windows_appcontainer_access import grant_appcontainer_directory_access
    from .windows_handle_custody import (WindowsHandleCustodyError,
        observe_private_directory_identity, read_regular_files)
    from .windows_peer_replay_custody import publish_immutable_replay_bytes

    checked_protocol = verify_durable_learning_protocol(protocol)
    branch_id = checked_protocol.get("condition_branch_ids", {}).get(condition)
    if (not isinstance(root, Path) or not root.is_absolute()
            or not isinstance(expected_root_identity, tuple)
            or len(expected_root_identity) != 2
            or type(expected_root_identity[0]) is not int
            or not isinstance(expected_root_identity[1], bytes)
            or len(expected_root_identity[1]) != 16
            or not isinstance(appcontainer_sid, str)
            or _APP_CONTAINER_SID.fullmatch(appcontainer_sid) is None
            or not isinstance(branch_id, str)
            or not isinstance(receipt_refs, list)
            or not 1 <= len(receipt_refs) <= _MAX_RECEIPTS
            or not callable(getattr(source_verifier,
                "verify_persisted_invocation_receipt", None))):
        raise ValueError("condition_invocation_receipt_store_arguments_invalid")
    refs: dict[str, str] = {}
    for item in receipt_refs:
        if (not isinstance(item, Mapping) or set(item) != {
                "receipt_id", "receipt_digest"}
                or not isinstance(item.get("receipt_id"), str)
                or _RECEIPT_ID.fullmatch(item["receipt_id"]) is None
                or not isinstance(item.get("receipt_digest"), str)
                or re.fullmatch(r"[0-9a-f]{64}",
                    item["receipt_digest"]) is None
                or item["receipt_id"] in refs):
            raise ValueError("condition_invocation_receipt_store_ref_invalid")
        refs[item["receipt_id"]] = item["receipt_digest"]

    payloads: dict[str, bytes] = {}
    for receipt_id, receipt_digest in refs.items():
        receipt = source_verifier.verify_persisted_invocation_receipt(
            receipt_id, receipt_digest)
        valid, _reasons = validate_receipt(receipt)
        if (not valid or receipt.get("receipt_id") != receipt_id
                or receipt.get("receipt_digest") != receipt_digest):
            raise ValueError("condition_invocation_receipt_source_unverified")
        detached = dict(receipt)
        detached.pop("output_text", None)
        raw = (json.dumps(detached, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        if len(raw) > _MAX_RECEIPT_BYTES:
            raise ValueError("condition_invocation_receipt_over_bound")
        payloads[receipt_id] = raw

    index_semantic = {"schema_version": _INDEX_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "protocol_digest": protocol["protocol_digest"],
        "condition": condition, "branch_id": branch_id,
        "receipt_refs": [{"receipt_id": receipt_id,
            "receipt_digest": refs[receipt_id]} for receipt_id in sorted(refs)],
        "authority": False}
    index_digest = digest_payload(index_semantic)
    index_file_name = f"durable-learning-invocation-index-{index_digest[:24]}.json"
    index_payload = {**index_semantic, "index_digest": index_digest}
    index_raw = (json.dumps(index_payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    if len(index_raw) > 2_097_152:
        raise ValueError("condition_invocation_receipt_index_over_bound")
    try:
        existing = read_regular_files(root, max_entries=1,
            max_file_bytes=1, max_total_bytes=1,
            suffix="", require_private_acl=True,
            expected_root_identity=expected_root_identity)
        if existing:
            raise ValueError("condition_invocation_receipt_store_not_empty")
        for receipt_id, raw in payloads.items():
            publish_immutable_replay_bytes(root / (receipt_id + ".json"), raw,
                max_bytes=_MAX_RECEIPT_BYTES, max_entries=_MAX_RECEIPTS + 1,
                expected_root_identity=expected_root_identity,
                filename_policy="durable_learning_condition_invocation_receipt")
        publish_immutable_replay_bytes(root / index_file_name, index_raw,
            max_bytes=2_097_152, max_entries=_MAX_RECEIPTS + 1,
            expected_root_identity=expected_root_identity,
            filename_policy="durable_learning_condition_invocation_receipt_index")
        acl = grant_appcontainer_directory_access(root=root,
            expected_directory_identity=expected_root_identity,
            appcontainer_sid=appcontainer_sid,
            access_policy="condition_receipt_read")
        if observe_private_directory_identity(root,
                permitted_appcontainer_sid=appcontainer_sid) != expected_root_identity:
            raise ValueError("condition_invocation_receipt_root_changed")
        stored = read_regular_files(root, max_entries=1,
            max_file_bytes=2_097_152, max_total_bytes=2_097_152,
            suffix="", require_private_acl=True,
            permitted_appcontainer_sid=appcontainer_sid,
            expected_root_identity=expected_root_identity,
            selected_names=(index_file_name,))
    except WindowsHandleCustodyError as exc:
        raise ValueError("condition_invocation_receipt_store_custody_failed") from exc
    if len(stored) != 1 or stored[0] != (index_file_name, index_raw):
        raise ValueError("condition_invocation_receipt_index_readback_mismatch")
    semantic = {"schema_version": _STORE_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "protocol_digest": protocol["protocol_digest"],
        "condition": condition, "branch_id": branch_id,
        "root_identity": {"volume_serial": expected_root_identity[0],
            "file_id_hex": expected_root_identity[1].hex()},
        "appcontainer_sid": appcontainer_sid,
        "index_file_name": index_file_name, "index_digest": index_digest,
        "receipt_count": len(refs),
        "access_policy": "condition_receipt_read",
        "effective_access_verified": False, "peer_denial_verified": False,
        "source_receipts_reverified": True, "authority": False}
    artifact = {**semantic, "artifact_digest": digest_payload(semantic)}
    return artifact, {**acl, "file_readback_verified": True,
        "root_identity_stable": True, "effective_access_verified": False,
        "peer_denial_verified": False, "authority": False}


def load_condition_invocation_receipt_store(*, root: Path,
        expected_root_identity: tuple[int, bytes], appcontainer_sid: str,
        artifact: Mapping[str, Any], protocol: Mapping[str, Any],
        condition: str) -> dict[str, Any]:
    """Authenticate the closed store artifact and pin its exact receipt index."""
    if os.name != "nt":
        raise ValueError("condition_invocation_receipt_store_windows_only")
    from .durable_developmental_learning_experiment import (
        verify_durable_learning_protocol)
    from .local_model_authority import digest_payload
    from .windows_handle_custody import read_regular_files

    protocol_check = verify_durable_learning_protocol(protocol)
    expected_branch = protocol_check.get("condition_branch_ids", {}).get(condition)
    if (not isinstance(root, Path) or not root.is_absolute()
            or not isinstance(expected_root_identity, tuple)
            or len(expected_root_identity) != 2
            or type(expected_root_identity[0]) is not int
            or not isinstance(expected_root_identity[1], bytes)
            or len(expected_root_identity[1]) != 16
            or not isinstance(artifact, Mapping) or set(artifact) != _STORE_FIELDS
            or artifact.get("schema_version") != _STORE_SCHEMA
            or artifact.get("protocol_id") != protocol.get("protocol_id")
            or artifact.get("protocol_digest") != protocol.get("protocol_digest")
            or artifact.get("condition") != condition
            or artifact.get("branch_id") != expected_branch
            or artifact.get("root_identity") != {
                "volume_serial": expected_root_identity[0],
                "file_id_hex": expected_root_identity[1].hex()}
            or artifact.get("appcontainer_sid") != appcontainer_sid
            or not isinstance(artifact.get("index_file_name"), str)
            or not isinstance(artifact.get("index_digest"), str)
            or re.fullmatch(r"[0-9a-f]{64}",
                artifact["index_digest"]) is None
            or artifact.get("index_file_name") != (
                "durable-learning-invocation-index-"
                + artifact["index_digest"][:24] + ".json")
            or type(artifact.get("receipt_count")) is not int
            or not 1 <= artifact["receipt_count"] <= _MAX_RECEIPTS
            or artifact.get("access_policy") != "condition_receipt_read"
            or artifact.get("effective_access_verified") is not False
            or artifact.get("peer_denial_verified") is not False
            or artifact.get("source_receipts_reverified") is not True
            or artifact.get("authority") is not False):
        raise ValueError("condition_invocation_receipt_store_artifact_invalid")
    semantic = {key: value for key, value in artifact.items()
        if key != "artifact_digest"}
    if artifact.get("artifact_digest") != digest_payload(semantic):
        raise ValueError("condition_invocation_receipt_store_artifact_digest_invalid")
    index_entries = read_regular_files(root, max_entries=1,
        max_file_bytes=2_097_152, max_total_bytes=2_097_152,
        suffix="", selected_names=(artifact["index_file_name"],),
        require_private_acl=True,
        permitted_appcontainer_sid=appcontainer_sid,
        expected_root_identity=expected_root_identity)
    if len(index_entries) != 1:
        raise ValueError("condition_invocation_receipt_index_missing")
    index = _decode_receipt(index_entries[0][1])
    index_fields = {"schema_version", "protocol_id", "protocol_digest",
        "condition", "branch_id", "receipt_refs", "authority", "index_digest"}
    index_semantic = {key: value for key, value in index.items()
        if key != "index_digest"}
    if (index_entries[0][0] != artifact["index_file_name"]
            or set(index) != index_fields
            or index.get("schema_version") != _INDEX_SCHEMA
            or index.get("protocol_id") != protocol.get("protocol_id")
            or index.get("protocol_digest") != protocol.get("protocol_digest")
            or index.get("condition") != condition
            or index.get("branch_id") != expected_branch
            or index.get("authority") is not False
            or index.get("index_digest") != artifact["index_digest"]
            or index.get("index_digest") != digest_payload(index_semantic)
            or not isinstance(index.get("receipt_refs"), list)
            or len(index["receipt_refs"]) != artifact["receipt_count"]):
        raise ValueError("condition_invocation_receipt_index_invalid")
    refs: dict[str, str] = {}
    for item in index["receipt_refs"]:
        if (not isinstance(item, Mapping) or set(item) != {
                "receipt_id", "receipt_digest"}
                or not isinstance(item.get("receipt_id"), str)
                or _RECEIPT_ID.fullmatch(item["receipt_id"]) is None
                or not isinstance(item.get("receipt_digest"), str)
                or re.fullmatch(r"[0-9a-f]{64}", item["receipt_digest"]) is None
                or item["receipt_id"] in refs):
            raise ValueError("condition_invocation_receipt_store_ref_invalid")
        refs[item["receipt_id"]] = item["receipt_digest"]
    if list(refs) != sorted(refs):
        raise ValueError("condition_invocation_receipt_index_order_invalid")
    return {"receipt_digests": refs,
        "artifact_digest": artifact["artifact_digest"],
        "root_identity": expected_root_identity,
        "appcontainer_sid": appcontainer_sid}


class ConditionInvocationReceiptVerifier:
    """Read and bind one receipt from a pre-pinned condition-local store.

    This adapter does not initialize or call an inference backend. The caller
    must supply the store root identity and the worker's permitted AppContainer
    SID from an independently verified launch manifest. Each lookup is an
    exact-name, bounded, handle-custody read; this class never discovers files
    or follows a receipt reference into another store.
    """

    def __init__(self, *, receipt_root: Path,
            expected_root_identity: tuple[int, bytes],
            appcontainer_sid: str,
            allowed_receipt_digests: Mapping[str, str]) -> None:
        if (os.name != "nt" or not isinstance(receipt_root, Path)
                or not receipt_root.is_absolute()
                or not isinstance(expected_root_identity, tuple)
                or len(expected_root_identity) != 2
                or type(expected_root_identity[0]) is not int
                or not isinstance(expected_root_identity[1], bytes)
                or len(expected_root_identity[1]) != 16
                or not isinstance(appcontainer_sid, str)
                or _APP_CONTAINER_SID.fullmatch(appcontainer_sid) is None
                or not isinstance(allowed_receipt_digests, Mapping)
                or not 1 <= len(allowed_receipt_digests) <= _MAX_RECEIPTS
                or any(not isinstance(receipt_id, str)
                    or _RECEIPT_ID.fullmatch(receipt_id) is None
                    or not isinstance(digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                    for receipt_id, digest in allowed_receipt_digests.items())):
            raise ValueError("condition_invocation_receipt_store_binding_invalid")
        self._receipt_root = receipt_root
        self._expected_root_identity = expected_root_identity
        self._appcontainer_sid = appcontainer_sid
        self._allowed_receipt_digests = dict(allowed_receipt_digests)

    @classmethod
    def from_staged_store(cls, *, root: Path,
            expected_root_identity: tuple[int, bytes], appcontainer_sid: str,
            artifact: Mapping[str, Any], protocol: Mapping[str, Any],
            condition: str) -> "ConditionInvocationReceiptVerifier":
        checked = load_condition_invocation_receipt_store(root=root,
            expected_root_identity=expected_root_identity,
            appcontainer_sid=appcontainer_sid, artifact=artifact,
            protocol=protocol, condition=condition)
        return cls(receipt_root=root,
            expected_root_identity=expected_root_identity,
            appcontainer_sid=appcontainer_sid,
            allowed_receipt_digests=checked["receipt_digests"])

    @staticmethod
    def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("condition_invocation_receipt_duplicate_json_key")
            result[key] = value
        return result

    @staticmethod
    def _reject_constant(value: str) -> None:
        raise ValueError("condition_invocation_receipt_non_json_constant")

    def verify_persisted_invocation_receipt(self, receipt_id: str,
            receipt_digest: str, **expected: Any) -> Mapping[str, Any]:
        """Verify receipt integrity and the observation's request/session binding."""
        if (not isinstance(receipt_id, str)
                or _RECEIPT_ID.fullmatch(receipt_id) is None
                or not isinstance(receipt_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", receipt_digest) is None
                or self._allowed_receipt_digests.get(receipt_id) != receipt_digest):
            raise ValueError("condition_invocation_receipt_identity_invalid")

        from .windows_handle_custody import read_regular_files
        from .governed_local_model_invocation import validate_receipt

        entries = read_regular_files(self._receipt_root, max_entries=1,
            max_file_bytes=_MAX_RECEIPT_BYTES,
            max_total_bytes=_MAX_RECEIPT_BYTES,
            selected_names=(receipt_id + ".json",),
            require_private_acl=True,
            permitted_appcontainer_sid=self._appcontainer_sid,
            expected_root_identity=self._expected_root_identity)
        if len(entries) != 1 or entries[0][0] != receipt_id + ".json":
            raise ValueError("condition_invocation_receipt_missing")
        try:
            payload = json.loads(entries[0][1].decode("utf-8"),
                object_pairs_hook=self._reject_duplicate_keys,
                parse_constant=self._reject_constant)
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("condition_invocation_receipt_json_invalid") from exc
        valid, _reasons = validate_receipt(payload) if isinstance(payload, Mapping) else (False, [])
        request = payload.get("request") if isinstance(payload, Mapping) else None
        linkage = request.get("linkage") if isinstance(request, Mapping) else None
        serving = (linkage.get("resident_cognitive_serving")
            if isinstance(linkage, Mapping) else None)
        session_id = expected.get("expected_session_id")
        session_binding = expected.get("expected_session_binding")
        active_model_identity = expected.get("expected_active_model_identity")
        expected_serving = ({"session_id": session_id, **dict(session_binding)}
            if isinstance(session_id, str) and isinstance(session_binding, Mapping)
            else None)
        session_receipt_id = expected.get("expected_session_receipt_id")
        session_receipt_digest = expected.get("expected_session_receipt_digest")
        if session_receipt_id is not None:
            if not isinstance(expected_serving, dict):
                expected_serving = None
            else:
                expected_serving.update({
                    "session_receipt_id": session_receipt_id,
                    "session_receipt_semantic_digest": session_receipt_digest})
        if (not valid or not isinstance(request, Mapping)
                or payload.get("receipt_id") != receipt_id
                or payload.get("receipt_digest") != receipt_digest
                or request.get("request_id") != expected.get("expected_request_id")
                or request.get("request_digest") != expected.get("expected_request_digest")
                or not isinstance(active_model_identity, Mapping)
                or request.get("active_model_identity") != dict(active_model_identity)
                or not isinstance(serving, Mapping)
                or expected_serving is None or dict(serving) != expected_serving):
            raise ValueError("condition_invocation_receipt_binding_failed")
        return payload

    def verify_receipt_refs(self, receipt_refs: Any) -> dict[str, Any]:
        """Require an exact reference-set match against this staged store."""
        from .local_model_authority import digest_payload

        if (not isinstance(receipt_refs, list)
                or len(receipt_refs) != len(self._allowed_receipt_digests)):
            raise ValueError("condition_invocation_receipt_ref_set_invalid")
        observed: dict[str, str] = {}
        for item in receipt_refs:
            if (not isinstance(item, Mapping)
                    or set(item) != {"receipt_id", "receipt_digest"}
                    or not isinstance(item.get("receipt_id"), str)
                    or _RECEIPT_ID.fullmatch(item["receipt_id"]) is None
                    or not isinstance(item.get("receipt_digest"), str)
                    or re.fullmatch(r"[0-9a-f]{64}",
                        item["receipt_digest"]) is None
                    or item["receipt_id"] in observed):
                raise ValueError(
                    "condition_invocation_receipt_ref_set_invalid")
            observed[item["receipt_id"]] = item["receipt_digest"]
        if observed != self._allowed_receipt_digests:
            raise ValueError(
                "condition_invocation_receipt_ref_set_mismatch")
        return {"receipt_count": len(observed),
            "receipt_ref_set_digest": digest_payload({
                "receipt_refs": [{"receipt_id": receipt_id,
                    "receipt_digest": observed[receipt_id]}
                    for receipt_id in sorted(observed)]}),
            "exact_store_set_match": True, "authority": False}

    def verify_store_artifact(self, *, artifact: Mapping[str, Any],
            protocol: Mapping[str, Any], condition: str) -> dict[str, Any]:
        """Reload the pinned store index and bind it to this verifier instance."""
        checked = load_condition_invocation_receipt_store(
            root=self._receipt_root,
            expected_root_identity=self._expected_root_identity,
            appcontainer_sid=self._appcontainer_sid, artifact=artifact,
            protocol=protocol, condition=condition)
        if checked.get("receipt_digests") != self._allowed_receipt_digests:
            raise ValueError(
                "condition_invocation_receipt_store_verifier_binding_mismatch")
        return {"artifact_digest": checked["artifact_digest"],
            "receipt_count": len(checked["receipt_digests"]),
            "store_index_reloaded": True,
            "verifier_allowlist_matches_store": True, "authority": False}
