"""Bounded, derived semantic vectors for resident developmental history.

The index stores no history text and carries no epistemic or execution authority.
Every vector is joined back to an immutable history record and its exact projected
text before it can influence retrieval ranking.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .private_file_custody import (PrivateFileCustodyError,
    list_bounded_json_names_at, open_private_directory, publish_immutable_bytes,
    read_private_file_at)
from .windows_handle_custody import (WindowsHandleCustodyError,
    ensure_private_child_directory, observe_private_directory_identity,
    read_regular_files, verify_explicit_directory)
from .windows_peer_replay_custody import (WindowsReplayCustodyError,
    publish_immutable_replay_bytes)


SCHEMA = "sentientos.semantic_history_vector:v1"
TEXT_PROJECTION_POLICY = "resident_history_semantic_text:v1"
MAX_INDEX_RECORDS = 4096
MAX_INDEX_ENTRY_BYTES = 32_768
MAX_INDEX_BYTES = 134_217_728
MAX_VECTOR_DIMENSION = 1024


class SemanticHistoryIndexError(ValueError):
    """The derived index cannot be safely read or extended."""


@dataclass(frozen=True, slots=True)
class SemanticHistoryIndexSnapshot:
    vectors: Mapping[str, tuple[float, ...]]
    digest: str


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SemanticHistoryIndexError("semantic_history_index_payload_invalid") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _vector(value: object) -> tuple[float, ...] | None:
    if (not isinstance(value, (list, tuple)) or not value
            or len(value) > MAX_VECTOR_DIMENSION):
        return None
    if any(isinstance(item, bool) or not isinstance(item, (int, float))
            or not math.isfinite(float(item)) for item in value):
        return None
    result = tuple(float(item) for item in value)
    norm = math.sqrt(sum(item * item for item in result))
    if not 0.95 <= norm <= 1.05:
        return None
    return result


class SemanticHistoryIndex:
    """Immutable per-record CPU-vector cache, scoped to one pinned embedder."""

    def __init__(self, *, state_root: Path, embedder_identity_digest: str) -> None:
        if not _valid_digest(embedder_identity_digest):
            raise SemanticHistoryIndexError("semantic_history_embedder_identity_invalid")
        self.state_root = Path(state_root)
        scope_digest = _sha256(_canonical({
            "embedder_identity_digest": embedder_identity_digest,
            "text_projection_policy": TEXT_PROJECTION_POLICY,
        }))
        self.root = self.state_root / f"semantic_history_index_{scope_digest[:32]}"
        self.embedder_identity_digest = embedder_identity_digest
        self._lock = threading.RLock()
        self._root_identity: tuple[int, bytes] | None = None
        self._root_ready = False
        self._cache_signature: tuple[int, int, int] | None = None
        self._cache_loaded = False
        self._payload_cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _filename(record_id: str) -> str:
        return "semantic-" + _sha256(record_id.encode("utf-8")) + ".json"

    def _ensure_root(self) -> tuple[int, bytes] | None:
        if self._root_ready:
            return self._root_identity
        if os.name == "nt":
            try:
                verify_explicit_directory(self.state_root, require_private_acl=True)
                ensure_private_child_directory(self.state_root, self.root.name)
                self._root_identity = observe_private_directory_identity(self.root)
                self._root_ready = True
                return self._root_identity
            except (WindowsHandleCustodyError, OSError) as exc:
                raise SemanticHistoryIndexError(
                    "semantic_history_index_windows_custody_invalid") from exc
        try:
            descriptor = open_private_directory(self.root, create=True)
        except PrivateFileCustodyError as exc:
            raise SemanticHistoryIndexError(
                "semantic_history_index_root_unavailable") from exc
        os.close(descriptor)
        self._root_ready = True
        return None

    def publish(self, *, record_id: str, record_digest: str, text_digest: str,
            indexed_tick_digest: str, vector: Sequence[float]) -> None:
        values = _vector(vector)
        if (not isinstance(record_id, str) or not re.fullmatch(
                r"devrec-[0-9a-f]{24}", record_id)
                or not _valid_digest(record_digest) or not _valid_digest(text_digest)
                or not _valid_digest(indexed_tick_digest) or values is None):
            raise SemanticHistoryIndexError("semantic_history_index_entry_invalid")
        with self._lock:
            signature = self._signature()
            if not self._cache_loaded or signature != self._cache_signature:
                self._refresh_cache()
            existing = self._payload_cache.get(record_id)
            if existing is not None:
                if (existing.get("record_digest") != record_digest
                        or existing.get("text_digest") != text_digest
                        or tuple(existing.get("vector", ())) != values):
                    raise SemanticHistoryIndexError(
                        "semantic_history_index_identity_collision")
                return
        body = {"schema_version": SCHEMA,
            "embedder_identity_digest": self.embedder_identity_digest,
            "text_projection_policy": TEXT_PROJECTION_POLICY,
            "record_id": record_id, "record_digest": record_digest,
            "text_digest": text_digest, "indexed_tick_digest": indexed_tick_digest,
            "vector": list(values), "authority": False}
        payload = {**body, "entry_digest": _sha256(_canonical(body))}
        data = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False,
            allow_nan=False).encode("utf-8") + b"\n"
        if len(data) > MAX_INDEX_ENTRY_BYTES:
            raise SemanticHistoryIndexError("semantic_history_index_entry_unbounded")
        self._ensure_root()
        path = self.root / self._filename(record_id)
        if os.name == "nt":
            root_identity = self._ensure_root()
            try:
                publish_immutable_replay_bytes(path, data,
                    max_bytes=MAX_INDEX_ENTRY_BYTES, max_entries=MAX_INDEX_RECORDS,
                    expected_root_identity=root_identity,
                    filename_policy="resident_semantic_history_index")
                self._remember_published(payload)
                return
            except WindowsReplayCustodyError as exc:
                if exc.code != "replay_owner_record_conflict":
                    raise SemanticHistoryIndexError(
                        "semantic_history_index_publication_failed") from exc
        else:
            try:
                publish_immutable_bytes(path, data,
                    max_bytes=MAX_INDEX_ENTRY_BYTES, max_entries=MAX_INDEX_RECORDS,
                    collision_code="semantic_history_index_identity_collision")
                self._remember_published(payload)
                return
            except PrivateFileCustodyError as exc:
                if exc.code != "semantic_history_index_identity_collision":
                    raise SemanticHistoryIndexError(
                        "semantic_history_index_publication_failed") from exc
        existing_bytes = self._read_one(path.name)
        if existing_bytes != data:
            raise SemanticHistoryIndexError("semantic_history_index_identity_collision")
        self._remember_published(payload)

    def load(self, *, expected_records: Mapping[str, tuple[str, str]],
            current_tick_digest: str) -> SemanticHistoryIndexSnapshot:
        if (len(expected_records) > MAX_INDEX_RECORDS
                or not _valid_digest(current_tick_digest)):
            raise SemanticHistoryIndexError("semantic_history_index_read_bounds_invalid")
        with self._lock:
            signature = self._signature()
            if not self._cache_loaded or signature != self._cache_signature:
                self._refresh_cache()
            cached_payloads = tuple(self._payload_cache.items())
        expected = dict(expected_records)
        result: dict[str, tuple[float, ...]] = {}
        used_entries: list[dict[str, Any]] = []
        dimensions: int | None = None
        for record_id, payload in cached_payloads:
            try:
                actual = expected.get(record_id)
                vector = tuple(payload["vector"])
                if (actual is None
                        or (payload["record_digest"], payload["text_digest"]) != actual
                        or payload.get("indexed_tick_digest") == current_tick_digest
                        or (dimensions is not None and len(vector) != dimensions)):
                    continue
                dimensions = len(vector)
                result[record_id] = vector
                used_entries.append({key: payload[key] for key in (
                    "record_id", "record_digest", "text_digest",
                    "indexed_tick_digest", "entry_digest")})
            except (KeyError, TypeError, ValueError):
                continue
        snapshot_digest = _sha256(_canonical(sorted(
            used_entries, key=lambda item: item["record_id"])))
        return SemanticHistoryIndexSnapshot(MappingProxyType(result), snapshot_digest)

    def _signature(self) -> tuple[int, int, int] | None:
        try:
            metadata = self.root.stat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise SemanticHistoryIndexError(
                "semantic_history_index_root_unavailable") from exc
        if not stat.S_ISDIR(metadata.st_mode):
            raise SemanticHistoryIndexError("semantic_history_index_root_invalid")
        return metadata.st_mtime_ns, metadata.st_ctime_ns, metadata.st_ino

    def _refresh_cache(self) -> None:
        entries = self._read_entries()
        payloads: dict[str, dict[str, Any]] = {}
        for name, raw in entries:
            try:
                if (len(raw) > MAX_INDEX_ENTRY_BYTES
                        or not name.startswith("semantic-") or not name.endswith(".json")):
                    continue
                payload = json.loads(raw.decode("utf-8"))
                if (not isinstance(payload, dict)
                        or json.dumps(payload, sort_keys=True, indent=2,
                            ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n" != raw
                        or set(payload) != {"schema_version", "embedder_identity_digest",
                            "text_projection_policy", "record_id", "record_digest",
                            "text_digest", "indexed_tick_digest", "vector", "authority",
                            "entry_digest"}):
                    continue
                record_id = payload.get("record_id")
                vector = _vector(payload.get("vector"))
                body = {key: payload[key] for key in (
                    "schema_version", "embedder_identity_digest", "text_projection_policy",
                    "record_id", "record_digest", "text_digest", "indexed_tick_digest",
                    "vector", "authority")}
                if (not isinstance(record_id, str)
                        or not re.fullmatch(r"devrec-[0-9a-f]{24}", record_id)
                        or self._filename(record_id) != name
                        or payload.get("schema_version") != SCHEMA
                        or payload.get("embedder_identity_digest") != self.embedder_identity_digest
                        or payload.get("text_projection_policy") != TEXT_PROJECTION_POLICY
                        or not _valid_digest(payload.get("record_digest"))
                        or not _valid_digest(payload.get("text_digest"))
                        or not _valid_digest(payload.get("indexed_tick_digest"))
                        or payload.get("authority") is not False
                        or payload.get("entry_digest") != _sha256(_canonical(body))
                        or vector is None):
                    continue
                payloads[record_id] = {**payload, "vector": vector}
            except (UnicodeError, json.JSONDecodeError, TypeError, ValueError,
                    SemanticHistoryIndexError, KeyError):
                continue
        self._payload_cache = payloads
        self._cache_signature = self._signature()
        self._cache_loaded = True

    def _read_entries(self) -> tuple[tuple[str, bytes], ...]:
        try:
            metadata = self.root.lstat()
        except FileNotFoundError:
            return ()
        except OSError as exc:
            raise SemanticHistoryIndexError("semantic_history_index_root_unavailable") from exc
        if not stat.S_ISDIR(metadata.st_mode):
            raise SemanticHistoryIndexError("semantic_history_index_root_invalid")
        if os.name == "nt":
            try:
                return tuple(read_regular_files(self.root, max_entries=MAX_INDEX_RECORDS,
                    max_file_bytes=MAX_INDEX_ENTRY_BYTES, max_total_bytes=MAX_INDEX_BYTES,
                    require_private_acl=True))
            except WindowsHandleCustodyError as exc:
                raise SemanticHistoryIndexError(
                    "semantic_history_index_windows_recovery_failed") from exc
        try:
            descriptor = open_private_directory(self.root, create=False)
        except PrivateFileCustodyError as exc:
            raise SemanticHistoryIndexError(
                "semantic_history_index_root_unavailable") from exc
        try:
            opened = os.fstat(descriptor)
            if opened.st_dev != metadata.st_dev or opened.st_ino != metadata.st_ino:
                raise SemanticHistoryIndexError(
                    "semantic_history_index_collection_changed")
            names = list_bounded_json_names_at(descriptor,
                max_entries=MAX_INDEX_RECORDS,
                max_directory_entries=MAX_INDEX_RECORDS + 128)
            entries = []
            total = 0
            for name in names:
                try:
                    raw = read_private_file_at(descriptor, name,
                        max_bytes=MAX_INDEX_ENTRY_BYTES)
                except PrivateFileCustodyError as exc:
                    raise SemanticHistoryIndexError(
                        "semantic_history_index_entry_unavailable") from exc
                total += len(raw)
                if total > MAX_INDEX_BYTES:
                    raise SemanticHistoryIndexError(
                        "semantic_history_index_root_unbounded")
                entries.append((name, raw))
            after = os.fstat(descriptor)
            if (after.st_dev != opened.st_dev or after.st_ino != opened.st_ino
                    or after.st_mtime_ns != opened.st_mtime_ns
                    or after.st_ctime_ns != opened.st_ctime_ns):
                raise SemanticHistoryIndexError(
                    "semantic_history_index_collection_changed")
            return tuple(entries)
        except PrivateFileCustodyError as exc:
            raise SemanticHistoryIndexError(
                "semantic_history_index_root_unavailable") from exc
        finally:
            os.close(descriptor)

    def _remember_published(self, payload: Mapping[str, Any]) -> None:
        record_id = payload.get("record_id")
        if isinstance(record_id, str):
            values = _vector(payload.get("vector"))
            if values is not None:
                with self._lock:
                    self._payload_cache[record_id] = {**dict(payload), "vector": values}
                    self._cache_loaded = True
                    self._cache_signature = self._signature()

    def _read_one(self, name: str) -> bytes:
        if os.name == "nt":
            try:
                rows = read_regular_files(self.root, max_entries=MAX_INDEX_RECORDS,
                    max_file_bytes=MAX_INDEX_ENTRY_BYTES,
                    max_total_bytes=MAX_INDEX_BYTES, selected_names=(name,),
                    require_private_acl=True)
            except WindowsHandleCustodyError as exc:
                raise SemanticHistoryIndexError(
                    "semantic_history_index_entry_unavailable") from exc
            if len(rows) != 1 or rows[0][0] != name:
                raise SemanticHistoryIndexError("semantic_history_index_entry_missing")
            return rows[0][1]
        try:
            descriptor = open_private_directory(self.root, create=False)
            try:
                return read_private_file_at(descriptor, name,
                    max_bytes=MAX_INDEX_ENTRY_BYTES)
            finally:
                os.close(descriptor)
        except PrivateFileCustodyError as exc:
            raise SemanticHistoryIndexError(
                "semantic_history_index_entry_unavailable") from exc


__all__ = ["SemanticHistoryIndex", "SemanticHistoryIndexError",
    "SemanticHistoryIndexSnapshot",
    "TEXT_PROJECTION_POLICY"]
