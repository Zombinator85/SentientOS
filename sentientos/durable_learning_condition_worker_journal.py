"""Immutable intent/completion journal for condition-worker mutations.

An intent without a completion is ambiguous after restart and must never be
replayed automatically. The journal is scoped to one protocol condition and
uses the handle-bound Windows publisher and reader on a dedicated root.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Mapping

from .local_model_authority import digest_payload


_LEGACY_INTENT_SCHEMA = "sentientos.durable_learning_condition_worker_intent:v2"
_LEGACY_RECEIPT_SCHEMA = "sentientos.durable_learning_condition_worker_completion:v2"
INTENT_SCHEMA = "sentientos.durable_learning_condition_worker_intent:v3"
RECEIPT_SCHEMA = "sentientos.durable_learning_condition_worker_completion:v3"
SCOPE_SCHEMA = "sentientos.durable_learning_condition_worker_scope_reservation:v1"
SCOPE_FILENAME = "durable-learning-worker-scope.json"
_PROTOCOL_ID = re.compile(r"devexp-durable-learning-protocol-[0-9a-f]{24}")
_HEX = re.compile(r"[0-9a-f]{64}")
_REQUEST_ID = re.compile(r"[0-9a-f]{32}")
_CONDITIONS = {"relevant_experience_available",
    "relevant_experience_withheld"}
_INTENT_FIELDS = {"schema_version", "protocol_id", "protocol_digest",
    "condition", "branch_id", "request_id", "operation", "request_digest",
    "snapshot_digest", "request_payload", "authority", "intent_digest"}
_LEGACY_INTENT_FIELDS = _INTENT_FIELDS - {"request_payload"}
_RECEIPT_FIELDS = {"schema_version", "protocol_id", "protocol_digest",
    "condition", "branch_id", "request_id", "request_digest",
    "intent_digest", "snapshot_digest", "result_digest", "result", "authority",
    "receipt_digest"}
_LEGACY_RECEIPT_FIELDS = _RECEIPT_FIELDS
_SCOPE_FIELDS = {"schema_version", "protocol_id", "protocol_digest",
    "condition", "branch_id", "request_id", "request_digest",
    "snapshot_digest", "authority", "scope_digest"}
MAX_JOURNAL_FILE_BYTES = 1_048_576
MAX_JOURNAL_ENTRIES = 8192
MAX_JOURNAL_TOTAL_BYTES = 16_777_216


class ConditionWorkerJournalError(ValueError):
    """A worker operation journal failed closed."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_duplicate_json_key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ConditionWorkerJournalError(
        "durable_learning_worker_journal_non_json_constant")


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        raw = json.dumps(dict(value), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":")).encode(
                "utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise ConditionWorkerJournalError(
            "durable_learning_worker_journal_json_invalid") from exc
    if not raw or len(raw) > MAX_JOURNAL_FILE_BYTES:
        raise ConditionWorkerJournalError(
            "durable_learning_worker_journal_file_over_bound")
    return raw


class ConditionWorkerOperationJournal:
    """Journal one condition's mutating RPC operations under immutable names."""

    def __init__(self, *, root: Path,
            expected_root_identity: tuple[int, bytes], appcontainer_sid: str,
            protocol_id: str, protocol_digest: str, condition: str,
            branch_id: str) -> None:
        if (not isinstance(root, Path) or not root.is_absolute()
                or not isinstance(expected_root_identity, tuple)
                or len(expected_root_identity) != 2
                or type(expected_root_identity[0]) is not int
                or not 0 <= expected_root_identity[0] <= 0xFFFFFFFFFFFFFFFF
                or not isinstance(expected_root_identity[1], bytes)
                or len(expected_root_identity[1]) != 16
                or not isinstance(appcontainer_sid, str)
                or re.fullmatch(r"S-1-15-2-(?:[0-9]+-)*[0-9]+",
                    appcontainer_sid) is None
                or not isinstance(protocol_id, str)
                or _PROTOCOL_ID.fullmatch(protocol_id) is None
                or not isinstance(protocol_digest, str)
                or _HEX.fullmatch(protocol_digest) is None
                or condition not in _CONDITIONS
                or not isinstance(branch_id, str) or not branch_id
                or len(branch_id) > 256 or "\0" in branch_id):
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_binding_invalid")
        self._root = root
        self._root_identity = expected_root_identity
        self._sid = appcontainer_sid
        self._protocol_id = protocol_id
        self._protocol_digest = protocol_digest
        self._condition = condition
        self._branch_id = branch_id
        self._lock = threading.RLock()

    @property
    def binding(self) -> dict[str, Any]:
        """Return immutable journal scope metadata for worker setup checks."""
        return {"protocol_id": self._protocol_id,
            "protocol_digest": self._protocol_digest,
            "condition": self._condition, "branch_id": self._branch_id,
            "root": self._root,
            "root_identity": self._root_identity,
            "appcontainer_sid": self._sid,
            "authority": False}

    def _read(self) -> dict[str, bytes]:
        if os.name != "nt":
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_windows_only")
        from .windows_handle_custody import read_regular_files

        try:
            rows = read_regular_files(self._root,
                max_entries=MAX_JOURNAL_ENTRIES,
                max_file_bytes=MAX_JOURNAL_FILE_BYTES,
                max_total_bytes=MAX_JOURNAL_TOTAL_BYTES,
                suffix=".json", require_private_acl=True,
                permitted_appcontainer_sid=self._sid,
                expected_root_identity=self._root_identity)
        except Exception as exc:
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_read_failed") from exc
        result: dict[str, bytes] = {}
        for name, raw in rows:
            if (re.fullmatch(
                    r"durable-learning-worker-(?:intent|completion)-[0-9a-f]{32}\.json",
                    name) is None and name != SCOPE_FILENAME or name in result):
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_unexpected_entry")
            result[name] = raw
        decoded = {name: self._decode(raw) for name, raw in result.items()}
        scope = decoded.get(SCOPE_FILENAME)
        if scope is not None:
            self._verify_scope(scope)
        intent_names = [name for name in decoded
            if name.startswith("durable-learning-worker-intent-")]
        if len(intent_names) > 1:
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_multiple_scope_intents")
        for name, value in decoded.items():
            if name == SCOPE_FILENAME:
                continue
            match = re.fullmatch(
                r"durable-learning-worker-intent-([0-9a-f]{32})\.json", name)
            if match is not None:
                self._verify_intent(value, request_id=match.group(1),
                    request_digest=value.get("request_digest"))
                if (scope is not None and any(scope.get(key) != value.get(key)
                        for key in ("request_id", "request_digest",
                            "snapshot_digest"))):
                    raise ConditionWorkerJournalError(
                        "durable_learning_worker_journal_scope_intent_mismatch")
                continue
            match = re.fullmatch(
                r"durable-learning-worker-completion-([0-9a-f]{32})\.json",
                name)
            if match is None:
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_unexpected_entry")
            intent_name, _receipt_name = self._filenames(match.group(1))
            intent = decoded.get(intent_name)
            if intent is None:
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_completion_without_intent")
            self._verify_intent(intent, request_id=match.group(1),
                request_digest=intent.get("request_digest"))
            self._verify_receipt(value, intent=intent)
        return result

    def _decode(self, raw: bytes) -> dict[str, Any]:
        try:
            value = json.loads(raw.decode("utf-8", errors="strict"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_json_constant)
        except ConditionWorkerJournalError:
            raise
        except Exception as exc:
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_json_invalid") from exc
        if type(value) is not dict:
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_record_invalid")
        return value

    def _request_binding(self, request: Mapping[str, Any]
            ) -> tuple[str, str, str]:
        if (not isinstance(request, Mapping)
                or request.get("protocol_id") != self._protocol_id
                or request.get("protocol_digest") != self._protocol_digest
                or request.get("condition") != self._condition
                or request.get("operation") != "consolidate_branch"
                or not isinstance(request.get("request_id"), str)
                or _REQUEST_ID.fullmatch(request["request_id"]) is None
                or not isinstance(request.get("payload"), Mapping)
                or not isinstance(request["payload"].get("snapshot_digest"), str)
                or _HEX.fullmatch(request["payload"]["snapshot_digest"]) is None):
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_request_binding_invalid")
        from .durable_learning_condition_worker_rpc import (
            verify_condition_worker_rpc_request)
        try:
            checked_request = verify_condition_worker_rpc_request(dict(request))
        except (TypeError, ValueError) as exc:
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_request_invalid") from exc
        if checked_request != dict(request):
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_request_not_canonical")
        request_id = request["request_id"]
        request_digest = digest_payload({"request": dict(request)})
        return request_id, request_digest, self._filenames(request_id)[0]

    def _verify_request_intent(self, raw: bytes, *, request: Mapping[str, Any],
            request_id: str, snapshot_digest: str) -> dict[str, Any]:
        """Verify current or legacy intent against the matching request shape."""
        value = self._decode(raw)
        if value.get("schema_version") == _LEGACY_INTENT_SCHEMA:
            payload = request.get("payload")
            if not isinstance(payload, Mapping):
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_request_binding_invalid")
            legacy_request = dict(request)
            legacy_request["payload"] = {key: payload[key] for key in (
                "acquisition_receipt_digests",
                "consolidation_policy_digest", "snapshot_digest")
                if key in payload}
            request_digest = digest_payload({"request": legacy_request})
        else:
            request_digest = digest_payload({"request": dict(request)})
        return self._verify_intent(value, request_id=request_id,
            request_digest=request_digest, snapshot_digest=snapshot_digest)

    @staticmethod
    def _filenames(request_id: str) -> tuple[str, str]:
        return (f"durable-learning-worker-intent-{request_id}.json",
            f"durable-learning-worker-completion-{request_id}.json")

    def _verify_scope(self, value: Any) -> dict[str, Any]:
        if (type(value) is not dict or set(value) != _SCOPE_FIELDS
                or value.get("schema_version") != SCOPE_SCHEMA
                or value.get("protocol_id") != self._protocol_id
                or value.get("protocol_digest") != self._protocol_digest
                or value.get("condition") != self._condition
                or value.get("branch_id") != self._branch_id
                or not isinstance(value.get("request_id"), str)
                or _REQUEST_ID.fullmatch(value["request_id"]) is None
                or not isinstance(value.get("request_digest"), str)
                or _HEX.fullmatch(value["request_digest"]) is None
                or not isinstance(value.get("snapshot_digest"), str)
                or _HEX.fullmatch(value["snapshot_digest"]) is None
                or value.get("authority") is not False
                or value.get("scope_digest") != digest_payload({
                    key: item for key, item in value.items()
                    if key != "scope_digest"})):
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_scope_reservation_invalid")
        return value

    def inspect_baseline_inventory(self) -> dict[str, Any]:
        """Bind every root entry and establish whether this journal starts empty."""
        if os.name != "nt":
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_windows_only")
        from .windows_handle_custody import read_regular_files

        directories: list[tuple[str, tuple[int, bytes]]] = []
        files: list[tuple[str, tuple[int, bytes], int]] = []
        try:
            rows = read_regular_files(self._root,
                max_entries=MAX_JOURNAL_ENTRIES,
                max_file_bytes=MAX_JOURNAL_FILE_BYTES,
                max_total_bytes=MAX_JOURNAL_TOTAL_BYTES,
                suffix="", directory_identities=directories,
                file_identities=files, require_private_acl=True,
                permitted_appcontainer_sid=self._sid,
                expected_root_identity=self._root_identity)
        except Exception as exc:
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_baseline_inventory_failed") from exc
        identities_by_name = {name: (identity, size)
            for name, identity, size in files}
        entries = [{
            "name_digest": digest_payload({"name": name}),
            "kind": "file",
            "identity_digest": digest_payload({"identity": {
                "volume_serial_number": identity[0],
                "file_id": identity[1].hex()}}),
            "content_digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
        } for name, raw in rows for identity, size in [identities_by_name[name]]
            if size == len(raw)]
        if len(entries) != len(rows) or len(files) != len(rows):
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_baseline_inventory_mismatch")
        entries.extend({
            "name_digest": digest_payload({"name": name}),
            "kind": "directory",
            "identity_digest": digest_payload({"identity": {
                "volume_serial_number": identity[0],
                "file_id": identity[1].hex()}}),
            "content_digest": None,
            "size": None,
        } for name, identity in directories)
        entries.sort(key=lambda row: (row["kind"], row["name_digest"]))
        semantic = {"schema_version":
                "sentientos.durable_learning_worker_journal_baseline_inventory:v1",
            "file_count": len(files), "directory_count": len(directories),
            "entries_digest": digest_payload({"entries": entries}),
            "empty": not entries, "authority": False}
        return {**semantic, "inventory_digest": digest_payload(semantic)}

    def _verify_intent(self, value: Any, *, request_id: str,
            request_digest: str,
            snapshot_digest: str | None = None) -> dict[str, Any]:
        is_legacy = (isinstance(value, dict)
            and value.get("schema_version") == _LEGACY_INTENT_SCHEMA)
        expected_fields = (_LEGACY_INTENT_FIELDS if is_legacy else _INTENT_FIELDS)
        if (type(value) is not dict or set(value) != expected_fields
                or value.get("schema_version") != (
                    _LEGACY_INTENT_SCHEMA if is_legacy else INTENT_SCHEMA)
                or value.get("protocol_id") != self._protocol_id
                or value.get("protocol_digest") != self._protocol_digest
                or value.get("condition") != self._condition
                or value.get("branch_id") != self._branch_id
                or value.get("request_id") != request_id
                or value.get("operation") != "consolidate_branch"
                or not isinstance(value.get("request_digest"), str)
                or _HEX.fullmatch(value["request_digest"]) is None
                or value.get("request_digest") != request_digest
                or not isinstance(value.get("snapshot_digest"), str)
                or _HEX.fullmatch(value["snapshot_digest"]) is None
                or (not is_legacy and (
                    not isinstance(value.get("request_payload"), Mapping)
                    or value["request_payload"].get("snapshot_digest") !=
                        value.get("snapshot_digest")
                    or value.get("request_digest") != digest_payload({"request": {
                    "schema_version": "sentientos.durable_learning_condition_worker_rpc:v1",
                    "message_type": "request",
                    "protocol_id": self._protocol_id,
                    "protocol_digest": self._protocol_digest,
                    "condition": self._condition,
                    "request_id": request_id,
                    "operation": "consolidate_branch",
                    "payload": dict(value["request_payload"]),
                    "authority": False}})))
                or (snapshot_digest is not None
                    and value.get("snapshot_digest") != snapshot_digest)
                or value.get("authority") is not False
                or value.get("intent_digest") != digest_payload({
                    key: item for key, item in value.items()
                    if key != "intent_digest"})):
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_intent_invalid")
        if is_legacy:
            return value
        from .durable_learning_condition_worker_rpc import (
            verify_condition_worker_rpc_request)
        try:
            checked_request = verify_condition_worker_rpc_request({
                "schema_version":
                    "sentientos.durable_learning_condition_worker_rpc:v1",
                "message_type": "request", "protocol_id": self._protocol_id,
                "protocol_digest": self._protocol_digest,
                "condition": self._condition, "request_id": request_id,
                "operation": "consolidate_branch",
                "payload": dict(value["request_payload"]),
                "authority": False})
        except (TypeError, ValueError) as exc:
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_intent_request_payload_invalid") from exc
        if checked_request.get("payload") != dict(value["request_payload"]):
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_intent_request_payload_invalid")
        return value

    def _verify_receipt(self, value: Any, *, intent: Mapping[str, Any]
            ) -> dict[str, Any]:
        legacy = intent.get("schema_version") == _LEGACY_INTENT_SCHEMA
        expected_schema = (_LEGACY_RECEIPT_SCHEMA if legacy else RECEIPT_SCHEMA)
        if (type(value) is not dict or set(value) != _LEGACY_RECEIPT_FIELDS
                or value.get("schema_version") != expected_schema
                or value.get("protocol_id") != self._protocol_id
                or value.get("protocol_digest") != self._protocol_digest
                or value.get("condition") != self._condition
                or value.get("branch_id") != self._branch_id
                or value.get("request_id") != intent.get("request_id")
                or value.get("request_digest") != intent.get("request_digest")
                or value.get("intent_digest") != intent.get("intent_digest")
                or value.get("snapshot_digest") != intent.get("snapshot_digest")
                or not isinstance(value.get("snapshot_digest"), str)
                or _HEX.fullmatch(value["snapshot_digest"]) is None
                or not isinstance(value.get("result"), Mapping)
                or value.get("result_digest") != digest_payload(
                    dict(value["result"]))
                or value.get("authority") is not False
                or value.get("receipt_digest") != digest_payload({
                    key: item for key, item in value.items()
                    if key != "receipt_digest"})):
            raise ConditionWorkerJournalError(
                "durable_learning_worker_journal_completion_invalid")
        return value

    def begin(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Persist intent before effects; refuse ambiguous re-execution."""
        with self._lock:
            request_id, request_digest, intent_name = self._request_binding(request)
            snapshot_digest = request["payload"]["snapshot_digest"]
            _intent_name, receipt_name = self._filenames(request_id)
            rows = self._read()
            intent_raw, receipt_raw = rows.get(intent_name), rows.get(receipt_name)
            if intent_raw is not None:
                intent = self._verify_request_intent(intent_raw,
                    request=request, request_id=request_id,
                    snapshot_digest=snapshot_digest)
                if receipt_raw is None:
                    return {"state": "ambiguous", "intent": intent,
                        "authority": False}
                receipt = self._verify_receipt(self._decode(receipt_raw),
                    intent=intent)
                return {"state": "completed", "intent": intent,
                    "receipt": receipt, "authority": False}
            if receipt_raw is not None:
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_completion_without_intent")
            if any(name.startswith("durable-learning-worker-intent-")
                    for name in rows):
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_scope_already_started")
            scope_semantic = {"schema_version": SCOPE_SCHEMA,
                "protocol_id": self._protocol_id,
                "protocol_digest": self._protocol_digest,
                "condition": self._condition, "branch_id": self._branch_id,
                "request_id": request_id, "request_digest": request_digest,
                "snapshot_digest": snapshot_digest, "authority": False}
            scope = {**scope_semantic,
                "scope_digest": digest_payload(scope_semantic)}
            scope_raw = rows.get(SCOPE_FILENAME)
            if scope_raw is None:
                from .windows_peer_replay_custody import (
                    publish_immutable_replay_bytes)
                try:
                    publish_immutable_replay_bytes(
                        self._root / SCOPE_FILENAME, _canonical_bytes(scope),
                        max_bytes=MAX_JOURNAL_FILE_BYTES,
                        max_entries=MAX_JOURNAL_ENTRIES,
                        expected_root_identity=self._root_identity,
                        filename_policy="durable_learning_condition_worker_scope",
                        permitted_appcontainer_sid=self._sid)
                except Exception as exc:
                    try:
                        rows = self._read()
                    except Exception:
                        raise ConditionWorkerJournalError(
                            "durable_learning_worker_journal_scope_publish_failed") from exc
                    scope_raw = rows.get(SCOPE_FILENAME)
                    if scope_raw is None:
                        raise ConditionWorkerJournalError(
                            "durable_learning_worker_journal_scope_publish_failed") from exc
                rows = self._read()
                scope_raw = rows.get(SCOPE_FILENAME)
            if scope_raw is None:
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_scope_missing_after_publish")
            stored_scope = self._verify_scope(self._decode(scope_raw))
            if any(stored_scope.get(key) != scope.get(key) for key in (
                    "protocol_id", "protocol_digest", "condition", "branch_id",
                    "request_id", "request_digest", "snapshot_digest")):
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_scope_already_started")
            # Another exact-request worker may have published its intent while
            # this caller was reserving the scope. Treat it as recovery state.
            rows = self._read()
            intent_raw, receipt_raw = rows.get(intent_name), rows.get(receipt_name)
            if intent_raw is not None:
                intent = self._verify_request_intent(intent_raw,
                    request=request, request_id=request_id,
                    snapshot_digest=snapshot_digest)
                if receipt_raw is None:
                    return {"state": "ambiguous", "intent": intent,
                        "authority": False}
                receipt = self._verify_receipt(self._decode(receipt_raw),
                    intent=intent)
                return {"state": "completed", "intent": intent,
                    "receipt": receipt, "authority": False}
            semantic = {"schema_version": INTENT_SCHEMA,
                "protocol_id": self._protocol_id,
                "protocol_digest": self._protocol_digest,
                "condition": self._condition, "branch_id": self._branch_id,
                "request_id": request_id, "operation": "consolidate_branch",
                "request_digest": request_digest,
                "snapshot_digest": snapshot_digest,
                "request_payload": json.loads(json.dumps(
                    dict(request["payload"]), ensure_ascii=False,
                    allow_nan=False, sort_keys=True)),
                "authority": False}
            intent = {**semantic, "intent_digest": digest_payload(semantic)}
            from .windows_peer_replay_custody import (
                publish_immutable_replay_bytes)
            path = self._root / intent_name
            try:
                created = publish_immutable_replay_bytes(path,
                    _canonical_bytes(intent),
                    max_bytes=MAX_JOURNAL_FILE_BYTES,
                    max_entries=MAX_JOURNAL_ENTRIES,
                    expected_root_identity=self._root_identity,
                    filename_policy="durable_learning_condition_worker_intent",
                    permitted_appcontainer_sid=self._sid)
            except Exception as exc:
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_intent_publish_failed") from exc
            if not created:
                rows = self._read()
                receipt_raw = rows.get(self._filenames(request_id)[1])
                if receipt_raw is not None:
                    intent_raw = rows.get(intent_name)
                    if intent_raw is None:
                        raise ConditionWorkerJournalError(
                            "durable_learning_worker_journal_completion_without_intent")
                    stored_intent = self._verify_request_intent(intent_raw,
                        request=request, request_id=request_id,
                        snapshot_digest=snapshot_digest)
                    receipt = self._verify_receipt(self._decode(receipt_raw),
                        intent=stored_intent)
                    return {"state": "completed", "intent": stored_intent,
                        "receipt": receipt, "authority": False}
                return {"state": "ambiguous", "intent": intent,
                    "authority": False}
            return {"state": "started", "intent": intent,
                "authority": False}

    def inspect(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Read restart state without creating an intent or permitting replay."""
        with self._lock:
            request_id, request_digest, intent_name = self._request_binding(request)
            snapshot_digest = request["payload"]["snapshot_digest"]
            _intent_name, receipt_name = self._filenames(request_id)
            rows = self._read()
            intent_raw = rows.get(intent_name)
            receipt_raw = rows.get(receipt_name)
            if intent_raw is None:
                if receipt_raw is not None:
                    raise ConditionWorkerJournalError(
                        "durable_learning_worker_journal_completion_without_intent")
                scope_raw = rows.get(SCOPE_FILENAME)
                if scope_raw is not None:
                    scope = self._verify_scope(self._decode(scope_raw))
                    if any(scope.get(key) != value for key, value in (
                            ("request_id", request_id),
                            ("request_digest", request_digest),
                            ("snapshot_digest", snapshot_digest))):
                        return {"state": "scope_conflict",
                            "automatic_replay_performed": False,
                            "authority": False}
                if any(name.startswith(
                        "durable-learning-worker-intent-")
                        for name in rows):
                    return {"state": "scope_conflict",
                        "automatic_replay_performed": False,
                        "authority": False}
                return {"state": "not_started", "authority": False}
            intent = self._verify_request_intent(intent_raw,
                request=request, request_id=request_id,
                snapshot_digest=snapshot_digest)
            if receipt_raw is None:
                return {"state": "ambiguous", "intent": intent,
                    "authority": False}
            receipt = self._verify_receipt(self._decode(receipt_raw),
                intent=intent)
            return {"state": "completed", "intent": intent,
                "receipt": receipt, "authority": False}

    def complete(self, request: Mapping[str, Any], *,
            result: Mapping[str, Any]) -> dict[str, Any]:
        """Publish completion once; exact retries return the durable receipt."""
        with self._lock:
            request_id, request_digest, intent_name = self._request_binding(request)
            snapshot_digest = request["payload"]["snapshot_digest"]
            _intent_name, receipt_name = self._filenames(request_id)
            rows = self._read()
            intent_raw = rows.get(intent_name)
            if intent_raw is None:
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_intent_missing")
            intent = self._verify_request_intent(intent_raw,
                request=request, request_id=request_id,
                snapshot_digest=snapshot_digest)
            if not isinstance(result, Mapping):
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_result_invalid")
            try:
                result_value = json.loads(json.dumps(dict(result),
                    ensure_ascii=False, allow_nan=False, sort_keys=True))
            except (TypeError, ValueError, RecursionError) as exc:
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_result_invalid") from exc
            result_digest = digest_payload(result_value)
            receipt_raw = rows.get(receipt_name)
            if receipt_raw is not None:
                receipt = self._verify_receipt(self._decode(receipt_raw),
                    intent=intent)
                if receipt["result_digest"] != result_digest:
                    raise ConditionWorkerJournalError(
                        "durable_learning_worker_journal_completion_result_conflict")
                return receipt
            if intent.get("schema_version") != INTENT_SCHEMA:
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_legacy_intent_not_completable")
            semantic = {"schema_version": RECEIPT_SCHEMA,
                "protocol_id": self._protocol_id,
                "protocol_digest": self._protocol_digest,
                "condition": self._condition, "branch_id": self._branch_id,
                "request_id": request_id, "request_digest": request_digest,
                "intent_digest": intent["intent_digest"],
                "snapshot_digest": intent["snapshot_digest"],
                "result_digest": result_digest,
                "result": result_value, "authority": False}
            receipt = {**semantic,
                "receipt_digest": digest_payload(semantic)}
            from .windows_peer_replay_custody import (
                publish_immutable_replay_bytes)
            path = self._root / receipt_name
            try:
                publish_immutable_replay_bytes(path, _canonical_bytes(receipt),
                    max_bytes=MAX_JOURNAL_FILE_BYTES,
                    max_entries=MAX_JOURNAL_ENTRIES,
                    expected_root_identity=self._root_identity,
                    filename_policy="durable_learning_condition_worker_completion",
                    permitted_appcontainer_sid=self._sid)
            except Exception as exc:
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_completion_publish_failed") from exc
            # Publication can lose a race to another exact-request completion.
            # Return the immutable stored winner, never the caller's local
            # candidate, and fail if the competing result differs.
            persisted = self._read().get(receipt_name)
            if persisted is None:
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_completion_missing_after_publish")
            stored_receipt = self._verify_receipt(self._decode(persisted),
                intent=intent)
            if stored_receipt.get("result_digest") != result_digest:
                raise ConditionWorkerJournalError(
                    "durable_learning_worker_journal_completion_result_conflict")
            return stored_receipt
