"""Constant-size continuation head with an immutable predecessor-linked shard chain."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from scripts.verify_construction_continuation_custody import (
    MAX_CHECKPOINT_BYTES,
    MAX_INDEX_BYTES,
    MAX_SEGMENT_BYTES,
    MAX_SHARD_BYTES,
    _git_blob_sha,
    verify_continuation_reader,
)

V2_INDEX_PATH = "work/construction/index-v2.json"
V2_CHECKPOINT_PATH = "work/construction/active_checkpoint_v2.md"
V3_INDEX_PATH = "work/construction/index-v3.json"
V3_CHECKPOINT_PATH = "work/construction/active_checkpoint_v3.md"
V3_SHARD_DIRECTORY = "work/construction/shards-v3"
MAX_V3_SEQUENCE = 999_999_999
MAX_V3_SHARDS = 999_999_999
MAX_HEAD_BYTES = 4096
MAX_V3_COMPACT_CHECKPOINT_BYTES = 4096
V3_CHECKPOINT_FORMAT = "sentientos.construction_checkpoint:v2"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _valid_digest(value: Any, pattern: re.Pattern[str]) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _checkpoint_identity(data: bytes, sequence: int) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "path": V3_CHECKPOINT_PATH,
        "bytes": len(data),
        "sha256": _sha(data),
        "git_blob_sha": _git_blob_sha(data),
    }


def begin_v3_checkpoint_chain(
    head_bytes: bytes,
    *,
    source_commit: str,
    source_tree: str,
    read: Callable[[str, int], bytes],
) -> bytes:
    """Anchor compact checkpoint history to the current verified v3 checkpoint."""
    head = json.loads(head_bytes)
    if not isinstance(head, dict) or head.get("schema_version") != 3:
        raise ValueError("v3_checkpoint_chain_head_invalid")
    if head.get("active_checkpoint") != V3_CHECKPOINT_PATH:
        raise ValueError("v3_checkpoint_chain_requires_v3_checkpoint")
    if "checkpoint_chain" in head:
        raise ValueError("v3_checkpoint_chain_already_initialized")
    if not _valid_digest(source_commit, _HEX40) or not _valid_digest(source_tree, _HEX40):
        raise ValueError("v3_checkpoint_chain_source_identity_invalid")
    verified = verify_v3_reader(read, V3_INDEX_PATH, head_bytes, head)
    if verified.get("status") != "construction_continuation_custody_ready":
        raise ValueError("v3_checkpoint_chain_source_custody_not_ready")
    checkpoint_bytes = read(str(head.get("active_checkpoint")), MAX_CHECKPOINT_BYTES)
    binding = head.get("active_checkpoint_binding")
    sequence = head.get("latest_sequence")
    if (
        not isinstance(binding, dict)
        or type(sequence) is not int
        or _sha(checkpoint_bytes) != binding.get("checkpoint_sha256")
    ):
        raise ValueError("v3_checkpoint_chain_anchor_binding_invalid")
    anchor = {
        **_checkpoint_identity(checkpoint_bytes, sequence),
        "source_commit": source_commit,
        "source_tree": source_tree,
    }
    head["checkpoint_chain"] = {
        "schema_version": 1,
        "anchor": anchor,
        "latest": _checkpoint_identity(checkpoint_bytes, sequence),
    }
    return _json_bytes(head)


def render_v3_checkpoint(
    *,
    sequence: int,
    latest_main_commit: str,
    latest_main_tree: str,
    binding_origin_commit: str,
    binding_origin_tree: str,
    segment_path: str,
    segment_sha256: str,
    predecessor: Mapping[str, Any],
) -> bytes:
    """Render a bounded recovery checkpoint with an identity pointer to its parent."""
    if (
        type(sequence) is not int
        or sequence < 1
        or any(not _valid_digest(value, _HEX40) for value in (
            latest_main_commit, latest_main_tree, binding_origin_commit, binding_origin_tree
        ))
        or not _valid_digest(segment_sha256, _HEX64)
        or not isinstance(segment_path, str)
        or not segment_path.startswith("work/construction/segments/")
        or not isinstance(predecessor, Mapping)
        or type(predecessor.get("sequence")) is not int
        or type(predecessor.get("bytes")) is not int
        or predecessor.get("path") != V3_CHECKPOINT_PATH
        or not _valid_digest(predecessor.get("sha256"), _HEX64)
        or not _valid_digest(predecessor.get("git_blob_sha"), _HEX40)
    ):
        raise ValueError("v3_compact_checkpoint_input_invalid")
    predecessor_record = {
        "sequence": predecessor["sequence"],
        "path": predecessor["path"],
        "bytes": predecessor["bytes"],
        "sha256": predecessor["sha256"],
        "git_blob_sha": predecessor["git_blob_sha"],
        "source_commit": latest_main_commit,
        "source_tree": latest_main_tree,
    }
    text = (
        f"# Recovery state - sequence {sequence}\n\n"
        f"Checkpoint format: {V3_CHECKPOINT_FORMAT}\n"
        f"Latest verified main: `{latest_main_commit}`, tree `{latest_main_tree}`\n"
        f"Checkpoint binding origin: `{binding_origin_commit}`, tree `{binding_origin_tree}`\n"
        f"Previous checkpoint identity: {json.dumps(predecessor_record, sort_keys=True)}\n"
        f"Latest construction segment: `{segment_path}`\n"
        f"Latest segment SHA-256: `{segment_sha256}`\n"
        f"Sequence: {sequence}\n\n"
        "Recovery: use the v3 immutable predecessor-linked shard chain and the previous checkpoint identity above. "
        "Earlier checkpoint bytes remain available in their verified Git parent trees; do not duplicate snapshots.\n"
    ).encode("utf-8")
    if len(text) > MAX_V3_COMPACT_CHECKPOINT_BYTES:
        raise ValueError("v3_compact_checkpoint_size_exceeded")
    return text


def _anchor_from_v2(v2_bytes: bytes) -> dict[str, Any]:
    if len(v2_bytes) > MAX_INDEX_BYTES:
        raise ValueError("v2_anchor_size_exceeded")
    v2 = json.loads(v2_bytes)
    if (not isinstance(v2, dict) or type(v2.get("schema_version")) is not int
            or v2.get("schema_version") != 2):
        raise ValueError("v2_anchor_schema_invalid")
    binding = v2.get("active_checkpoint_binding")
    latest = v2.get("latest_sequence")
    latest_sha = binding.get("latest_segment_sha256") if isinstance(binding, dict) else None
    if (type(latest) is not int or not 0 <= latest <= MAX_V3_SEQUENCE
            or not isinstance(binding, dict)
            or type(binding.get("latest_segment_sequence")) is not int
            or binding.get("latest_segment_sequence") != latest
            or (latest == 0 and latest_sha is not None)
            or (latest > 0 and not _valid_digest(latest_sha, _HEX64))):
        raise ValueError("v2_anchor_checkpoint_binding_invalid")
    return {
        "path": V2_INDEX_PATH,
        "bytes": len(v2_bytes),
        "sha256": _sha(v2_bytes),
        "git_blob_sha": _git_blob_sha(v2_bytes),
        "latest_sequence": latest,
        "latest_segment_sha256": latest_sha,
    }


def _path_for(shard_sequence: int, first: int, last: int) -> str:
    return (f"{V3_SHARD_DIRECTORY}/{shard_sequence:09d}-"
            f"{first:09d}-{last:09d}.json")


def _descriptor(shard: Mapping[str, Any]) -> dict[str, Any]:
    return {key: shard[key] for key in (
        "path", "bytes", "sha256", "git_blob_sha", "shard_sequence",
        "first_sequence", "last_sequence")}


def _walk_v3_shards(
    head: Mapping[str, Any], read: Callable[[str, int], bytes], failures: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    anchor = head.get("history_anchor")
    descriptor = head.get("latest_shard")
    declared_count = head.get("shard_count")
    latest = head.get("latest_sequence")
    if not isinstance(anchor, dict):
        failures.append("v3_history_anchor_missing")
        return [], []
    anchor_latest = anchor.get("latest_sequence")
    if type(declared_count) is not int or not 0 <= declared_count <= MAX_V3_SHARDS:
        failures.append("v3_shard_count_invalid")
        return [], []
    if (type(latest) is not int or type(anchor_latest) is not int
            or not 0 <= anchor_latest <= latest <= MAX_V3_SEQUENCE):
        failures.append("v3_sequence_bounds_invalid")
        return [], []
    if (declared_count == 0) != (descriptor is None):
        failures.append("v3_latest_shard_count_mismatch")
        return [], []
    if declared_count == 0:
        if latest != anchor_latest:
            failures.append("v3_empty_chain_sequence_mismatch")
        return [], []

    reverse_shards: list[dict[str, Any]] = []
    seen: set[str] = set()
    current: Any = descriptor
    expected_shard_seq = declared_count
    expected_last = latest
    while isinstance(current, dict):
        path = current.get("path")
        shard_seq = current.get("shard_sequence")
        first = current.get("first_sequence")
        last = current.get("last_sequence")
        size = current.get("bytes")
        digest = current.get("sha256")
        blob = current.get("git_blob_sha")
        if (not isinstance(path, str) or path in seen
                or not path.startswith(V3_SHARD_DIRECTORY + "/")
                or type(shard_seq) is not int or shard_seq != expected_shard_seq
                or type(first) is not int or type(last) is not int
                or type(size) is not int or size < 0 or size > MAX_SHARD_BYTES
                or not _valid_digest(digest, _HEX64)
                or not _valid_digest(blob, _HEX40)
                or first > last or last != expected_last
                or path != _path_for(shard_seq, first, last)):
            failures.append("v3_shard_descriptor_invalid")
            break
        seen.add(path)
        try:
            payload = read(path, MAX_SHARD_BYTES)
            if len(payload) != size:
                failures.append("v3_shard_byte_count_mismatch")
            if _sha(payload) != digest:
                failures.append("v3_shard_sha256_mismatch")
            if _git_blob_sha(payload) != blob:
                failures.append("v3_shard_git_blob_mismatch")
            doc = json.loads(payload)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"v3_shard_unreadable:{type(exc).__name__}:{exc}")
            break
        entries = doc.get("segments") if isinstance(doc, dict) else None
        if (not isinstance(doc, dict) or type(doc.get("schema_version")) is not int
                or doc.get("schema_version") != 1
                or type(doc.get("shard_sequence")) is not int
                or doc.get("shard_sequence") != shard_seq
                or type(doc.get("first_sequence")) is not int
                or doc.get("first_sequence") != first
                or type(doc.get("last_sequence")) is not int
                or doc.get("last_sequence") != last
                or not isinstance(entries, list) or len(entries) != last-first+1):
            failures.append("v3_shard_content_invalid")
            break
        reverse_shards.append({"descriptor": _descriptor(current), "document": doc})
        predecessor = doc.get("predecessor")
        if not isinstance(predecessor, dict):
            failures.append("v3_shard_predecessor_invalid")
            break
        if predecessor.get("kind") == "v2-root":
            if (shard_seq != 1 or predecessor.get("path") != anchor.get("path")
                    or predecessor.get("sha256") != anchor.get("sha256")
                    or predecessor.get("git_blob_sha") != anchor.get("git_blob_sha")
                    or predecessor.get("latest_sequence") != anchor_latest
                    or predecessor.get("latest_segment_sha256") != anchor.get("latest_segment_sha256")
                    or first != anchor_latest + 1):
                failures.append("v3_anchor_predecessor_mismatch")
            current = None
            break
        if predecessor.get("kind") != "v3-shard":
            failures.append("v3_predecessor_kind_invalid")
            break
        if (type(predecessor.get("shard_sequence")) is not int
                or predecessor.get("shard_sequence") != shard_seq - 1
                or type(predecessor.get("first_sequence")) is not int
                or type(predecessor.get("last_sequence")) is not int
                or type(predecessor.get("bytes")) is not int
                or not _valid_digest(predecessor.get("sha256"), _HEX64)
                or not _valid_digest(predecessor.get("git_blob_sha"), _HEX40)
                or predecessor.get("last_sequence") != first - 1
                or predecessor.get("path") != _path_for(
                    predecessor["shard_sequence"], predecessor["first_sequence"],
                    predecessor["last_sequence"])):
            failures.append("v3_predecessor_range_invalid")
            break
        current = predecessor
        expected_shard_seq -= 1
        expected_last = first - 1
    if current is not None:
        failures.append("v3_shard_chain_did_not_reach_anchor")
    if len(reverse_shards) != declared_count:
        failures.append("v3_shard_count_chain_mismatch")
    ordered: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    for shard in reversed(reverse_shards):
        document = shard["document"]
        entries = [e for e in document["segments"] if isinstance(e, dict)]
        ordered.extend(entries)
        transition = document.get("checkpoint_transition")
        if transition is not None:
            if not isinstance(transition, dict):
                failures.append("v3_checkpoint_transition_shape_invalid")
            else:
                transitions.append({
                    "document": document,
                    "transition": transition,
                    "last_entry": entries[-1] if entries else None,
                })
    expected_sequence = anchor_latest + 1
    for entry in ordered:
        if type(entry.get("sequence")) is not int or entry.get("sequence") != expected_sequence:
            failures.append(f"v3_segment_sequence_mismatch:{expected_sequence}")
        expected_sequence += 1
    if expected_sequence != latest + 1:
        failures.append("v3_segment_coverage_mismatch")
    return ordered, transitions


def materialize_v3_segments(
    index: dict[str, Any], read: Callable[[str, int], bytes]
) -> list[dict[str, Any]]:
    """Materialize anchor and continuation entries only after validating chain pointers."""
    from scripts.verify_construction_continuation_custody import materialize_index_segments

    failures: list[str] = []
    anchor = index.get("history_anchor")
    if not isinstance(anchor, dict):
        raise ValueError("v3_history_anchor_missing")
    v2_bytes = read(str(anchor.get("path")), MAX_INDEX_BYTES)
    if (_sha(v2_bytes) != anchor.get("sha256")
            or _git_blob_sha(v2_bytes) != anchor.get("git_blob_sha")):
        raise ValueError("v3_history_anchor_identity_mismatch")
    v2_index = json.loads(v2_bytes)
    base = materialize_index_segments(v2_index, read)
    continuation, _ = _walk_v3_shards(index, read, failures)
    if failures:
        raise ValueError(";".join(failures))
    return base + continuation


def v3_shard_paths(head: Mapping[str, Any], read: Callable[[str, int], bytes]) -> list[str]:
    """Return the predecessor-linked shard paths in chronological order."""
    reverse_paths: list[str] = []
    descriptor = head.get("latest_shard")
    seen: set[str] = set()
    while isinstance(descriptor, dict):
        path = descriptor.get("path")
        if not isinstance(path, str) or path in seen:
            raise ValueError("v3_shard_path_cycle_or_invalid")
        seen.add(path)
        reverse_paths.append(path)
        document = json.loads(read(path, MAX_SHARD_BYTES))
        predecessor = document.get("predecessor") if isinstance(document, dict) else None
        if not isinstance(predecessor, dict) or predecessor.get("kind") == "v2-root":
            break
        if predecessor.get("kind") != "v3-shard":
            raise ValueError("v3_predecessor_kind_invalid")
        descriptor = {key: predecessor[key] for key in (
            "path", "bytes", "sha256", "git_blob_sha", "shard_sequence",
            "first_sequence", "last_sequence") if key in predecessor}
    return list(reversed(reverse_paths))


def verify_v3_reader(
    read: Callable[[str, int], bytes], index_path: str, index_bytes: bytes,
    head: dict[str, Any],
) -> dict[str, Any]:
    """Verify the v2 anchor, every immutable v3 link, segment, provenance, and checkpoint."""
    failures: list[str] = []
    legacy_head_keys = {
        "schema_version", "continuation_schema_version", "history_anchor",
        "latest_sequence", "latest_segment_sha256", "shard_count", "latest_shard",
        "active_checkpoint", "active_checkpoint_binding",
    }
    if (type(head.get("schema_version")) is not int or head.get("schema_version") != 3
            or type(head.get("continuation_schema_version")) is not int
            or head.get("continuation_schema_version") != 1
            or index_path != V3_INDEX_PATH
            or frozenset(head) not in {frozenset(legacy_head_keys),
                frozenset(legacy_head_keys | {"checkpoint_chain"})}):
        return {"status": "invalid", "failures": ["v3_head_schema_or_shape_invalid"]}
    if len(index_bytes) > MAX_HEAD_BYTES:
        failures.append("v3_head_size_exceeded")
    anchor = head.get("history_anchor")
    if not isinstance(anchor, dict):
        return {"status": "invalid", "failures": ["v3_history_anchor_missing"]}
    if (set(anchor) != {"path", "bytes", "sha256", "git_blob_sha", "latest_sequence",
            "latest_segment_sha256"}
            or anchor.get("path") != V2_INDEX_PATH
            or type(anchor.get("bytes")) is not int
            or not _valid_digest(anchor.get("sha256"), _HEX64)
            or not _valid_digest(anchor.get("git_blob_sha"), _HEX40)):
        failures.append("v3_history_anchor_invalid")
        anchor_bytes = b""
    else:
        try:
            anchor_bytes = read(V2_INDEX_PATH, MAX_INDEX_BYTES)
            if len(anchor_bytes) != anchor["bytes"]:
                failures.append("v3_history_anchor_byte_count_mismatch")
            if _sha(anchor_bytes) != anchor["sha256"]:
                failures.append("v3_history_anchor_sha256_mismatch")
            if _git_blob_sha(anchor_bytes) != anchor["git_blob_sha"]:
                failures.append("v3_history_anchor_git_blob_mismatch")
        except (OSError, ValueError) as exc:
            failures.append(f"v3_history_anchor_unreadable:{type(exc).__name__}:{exc}")
            anchor_bytes = b""
    anchor_result = verify_continuation_reader(read, V2_INDEX_PATH)
    failures.extend("v2_anchor:" + failure for failure in anchor_result.get("failures", []))
    try:
        v2_index = json.loads(anchor_bytes)
    except (ValueError, json.JSONDecodeError):
        v2_index = {}
        failures.append("v3_history_anchor_json_invalid")
    v2_binding = v2_index.get("active_checkpoint_binding", {}) if isinstance(v2_index, dict) else {}
    anchor_latest = v2_index.get("latest_sequence") if isinstance(v2_index, dict) else None
    anchor_sha = v2_binding.get("latest_segment_sha256") if isinstance(v2_binding, dict) else None
    if (anchor.get("latest_sequence") != anchor_latest
            or anchor.get("latest_segment_sha256") != anchor_sha
            or anchor_result.get("segments_verified") != anchor_latest):
        failures.append("v3_history_anchor_checkpoint_mismatch")

    continuation, checkpoint_transitions = _walk_v3_shards(head, read, failures)
    checkpoint_chain = head.get("checkpoint_chain")
    if checkpoint_chain is None:
        if checkpoint_transitions:
            failures.append("v3_checkpoint_transition_without_chain")
    elif not isinstance(checkpoint_chain, dict) or set(checkpoint_chain) != {
        "schema_version", "anchor", "latest"
    } or type(checkpoint_chain.get("schema_version")) is not int or checkpoint_chain.get("schema_version") != 1:
        failures.append("v3_checkpoint_chain_shape_invalid")
    else:
        anchor_descriptor = checkpoint_chain.get("anchor")
        latest_checkpoint = checkpoint_chain.get("latest")
        identity_keys = {"sequence", "path", "bytes", "sha256", "git_blob_sha"}
        anchor_keys = identity_keys | {"source_commit", "source_tree"}

        def valid_checkpoint_identity(value: Any, *, anchor: bool = False) -> bool:
            if not isinstance(value, dict) or set(value) != (anchor_keys if anchor else identity_keys):
                return False
            return (
                type(value.get("sequence")) is int
                and value["sequence"] >= 0
                and value.get("path") == V3_CHECKPOINT_PATH
                and type(value.get("bytes")) is int
                and 0 <= value["bytes"] <= MAX_CHECKPOINT_BYTES
                and _valid_digest(value.get("sha256"), _HEX64)
                and _valid_digest(value.get("git_blob_sha"), _HEX40)
                and (not anchor or (
                    _valid_digest(value.get("source_commit"), _HEX40)
                    and _valid_digest(value.get("source_tree"), _HEX40)
                ))
            )

        def identity_only(value: Mapping[str, Any]) -> dict[str, Any]:
            return {key: value[key] for key in (
                "sequence", "path", "bytes", "sha256", "git_blob_sha"
            )}

        if not valid_checkpoint_identity(anchor_descriptor, anchor=True):
            failures.append("v3_checkpoint_chain_anchor_invalid")
        if not valid_checkpoint_identity(latest_checkpoint):
            failures.append("v3_checkpoint_chain_latest_invalid")
        if isinstance(anchor_descriptor, dict) and isinstance(latest_checkpoint, dict):
            if checkpoint_transitions:
                expected_predecessor = identity_only(anchor_descriptor)
                previous_current: dict[str, Any] | None = None
                for item in checkpoint_transitions:
                    transition = item["transition"]
                    document = item["document"]
                    predecessor = transition.get("predecessor") if isinstance(transition, dict) else None
                    current = transition.get("current") if isinstance(transition, dict) else None
                    last_entry = item.get("last_entry")
                    if not (
                        isinstance(transition, dict)
                        and isinstance(predecessor, dict)
                        and isinstance(current, dict)
                        and isinstance(last_entry, dict)
                    ):
                        failures.append("v3_checkpoint_transition_invalid")
                        continue
                    predecessor_sequence = predecessor.get("sequence")
                    current_sequence = current.get("sequence")
                    transition_valid = (
                        set(transition) == {"schema_version", "predecessor", "current"}
                        and type(transition.get("schema_version")) is int
                        and transition.get("schema_version") == 1
                        and set(predecessor) == anchor_keys
                        and valid_checkpoint_identity(current)
                        and identity_only(predecessor) == expected_predecessor
                        and type(predecessor_sequence) is int
                        and type(current_sequence) is int
                        and predecessor_sequence < current_sequence
                        and current_sequence == document.get("last_sequence")
                        and predecessor.get("source_commit") == last_entry.get("source_commit")
                        and predecessor.get("source_tree") == last_entry.get("source_tree")
                    )
                    if not transition_valid:
                        failures.append("v3_checkpoint_transition_invalid")
                        continue
                    if previous_current is None and (
                        predecessor.get("source_commit") != anchor_descriptor.get("source_commit")
                        or predecessor.get("source_tree") != anchor_descriptor.get("source_tree")
                    ):
                        failures.append("v3_checkpoint_chain_anchor_source_mismatch")
                    expected_predecessor = identity_only(current)
                    previous_current = identity_only(current)
                    evidence_path = last_entry.get("evidence_path")
                    try:
                        evidence = json.loads(read(str(evidence_path), MAX_SEGMENT_BYTES))
                        source = evidence.get("source", {}) if isinstance(evidence, dict) else {}
                        publication = evidence.get("publication", {}) if isinstance(evidence, dict) else {}
                        readbacks = publication.get("verified_main_file_readbacks", {}) if isinstance(publication, dict) else {}
                        remote_ref = source.get("remote_ref_readback", {}) if isinstance(source, dict) else {}
                        if (
                            source.get("verified_remote_main") != predecessor.get("source_commit")
                            or source.get("verified_remote_main_tree") != predecessor.get("source_tree")
                            or remote_ref.get("commit") != predecessor.get("source_commit")
                            or readbacks.get("active_checkpoint_v3") != predecessor.get("git_blob_sha")
                        ):
                            failures.append("v3_checkpoint_transition_evidence_mismatch")
                    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                        failures.append(f"v3_checkpoint_transition_evidence_unreadable:{type(exc).__name__}")
                if previous_current != identity_only(latest_checkpoint):
                    failures.append("v3_checkpoint_chain_latest_transition_mismatch")
                if latest_checkpoint.get("sequence") != head.get("latest_sequence"):
                    failures.append("v3_checkpoint_chain_latest_sequence_mismatch")
            elif (
                identity_only(anchor_descriptor) != identity_only(latest_checkpoint)
                or latest_checkpoint.get("sequence") != head.get("latest_sequence")
            ):
                failures.append("v3_checkpoint_chain_empty_state_invalid")
    latest_descriptor = head.get("latest_shard")
    if isinstance(latest_descriptor, dict) and set(latest_descriptor) != {
        "path", "bytes", "sha256", "git_blob_sha", "shard_sequence",
        "first_sequence", "last_sequence",
    }:
        failures.append("v3_latest_shard_shape_invalid")
    try:
        from scripts.verify_construction_continuation_custody import materialize_index_segments
        prior = materialize_index_segments(v2_index, read)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        prior = []
        failures.append(f"v3_anchor_materialization_failed:{type(exc).__name__}:{exc}")
    segments = prior + continuation
    if head.get("latest_sequence") != len(segments):
        failures.append("v3_latest_sequence_mismatch")
    if head.get("latest_segment_sha256") != (segments[-1].get("sha256") if segments else None):
        failures.append("v3_latest_segment_digest_mismatch")

    seen = {entry.get("path") for entry in prior if isinstance(entry, dict)}
    legacy = v2_index.get("legacy_journal", {}) if isinstance(v2_index, dict) else {}
    previous = anchor_sha or (
        str(legacy.get("git_blob_sha")) if isinstance(legacy, dict) else ""
    )
    for expected, entry in enumerate(continuation, start=(anchor_latest or 0) + 1):
        if not isinstance(entry, dict):
            failures.append(f"v3_segment_{expected}_entry_invalid")
            continue
        path = entry.get("path")
        if not isinstance(path, str) or path in seen:
            failures.append(f"v3_segment_{expected}_path_invalid_or_duplicate")
            continue
        seen.add(path)
        expected_segment_predecessor = (
            f"segment-sha256:{previous}" if expected > (anchor_latest or 0)
            and previous != legacy.get("git_blob_sha")
            else f"legacy-blob:{previous}"
            if expected == 1 else f"segment-sha256:{previous}"
        )
        if entry.get("predecessor") != expected_segment_predecessor:
            failures.append(f"v3_segment_{expected}_predecessor_mismatch")
        try:
            content = read(path, MAX_SEGMENT_BYTES)
            digest = _sha(content)
            if type(entry.get("bytes")) is not int or len(content) != entry.get("bytes"):
                failures.append(f"v3_segment_{expected}_byte_count_mismatch")
            if digest != entry.get("sha256"):
                failures.append(f"v3_segment_{expected}_sha256_mismatch")
            if not isinstance(entry.get("source_commit") or entry.get("source_candidate_commit"), str):
                failures.append(f"v3_segment_{expected}_source_commit_missing")
            if "evidence_path" in entry:
                evidence_path = entry.get("evidence_path")
                evidence_sha = entry.get("evidence_sha256")
                evidence_size = entry.get("evidence_bytes")
                if (not isinstance(evidence_path, str) or not _valid_digest(evidence_sha, _HEX64)
                        or type(evidence_size) is not int):
                    failures.append(f"v3_segment_{expected}_evidence_binding_invalid")
                else:
                    evidence = read(evidence_path, MAX_SEGMENT_BYTES)
                    if (len(evidence) != evidence_size or _sha(evidence) != evidence_sha):
                        failures.append(f"v3_segment_{expected}_evidence_identity_mismatch")
            previous = digest
        except (OSError, ValueError) as exc:
            failures.append(f"v3_segment_{expected}_unreadable:{type(exc).__name__}:{exc}")
            previous = str(entry.get("sha256", ""))

    shard_count = head.get("shard_count")
    latest_shard = head.get("latest_shard")
    if (type(shard_count) is not int or shard_count < 0
            or (shard_count == 0) != (latest_shard is None)):
        failures.append("v3_head_shard_summary_invalid")
    binding = head.get("active_checkpoint_binding")
    checkpoint_path = head.get("active_checkpoint")
    expected_binding_keys = {"checkpoint_sha256", "latest_segment_sequence",
        "latest_segment_sha256", "source_commit", "source_tree"}
    if not isinstance(binding, dict) or set(binding) != expected_binding_keys:
        failures.append("v3_checkpoint_binding_shape_invalid")
    if isinstance(v2_binding, dict) and isinstance(binding, dict):
        if shard_count == 0:
            if (checkpoint_path != v2_index.get("active_checkpoint")
                    or binding != v2_binding):
                failures.append("v3_unadvanced_checkpoint_must_match_v2_anchor")
        elif (checkpoint_path != V3_CHECKPOINT_PATH
                or binding.get("source_commit") != v2_binding.get("source_commit")
                or binding.get("source_tree") != v2_binding.get("source_tree")):
            failures.append("v3_checkpoint_origin_changed")
    if not isinstance(binding, dict) or not isinstance(checkpoint_path, str):
        failures.append("v3_checkpoint_binding_missing")
    else:
        try:
            checkpoint = read(checkpoint_path, MAX_CHECKPOINT_BYTES)
            text = checkpoint.decode("utf-8")
            checkpoint_sha = _sha(checkpoint)
            latest = segments[-1] if segments else None
            if binding.get("checkpoint_sha256") != checkpoint_sha:
                failures.append("v3_checkpoint_sha256_mismatch")
            if checkpoint_chain is not None:
                if isinstance(checkpoint_chain, dict) and isinstance(checkpoint_chain.get("latest"), dict):
                    latest_cp = checkpoint_chain["latest"]
                    if (
                        latest_cp.get("sequence") != head.get("latest_sequence")
                        or latest_cp.get("bytes") != len(checkpoint)
                        or latest_cp.get("sha256") != _sha(checkpoint)
                        or latest_cp.get("git_blob_sha") != _git_blob_sha(checkpoint)
                    ):
                        failures.append("v3_checkpoint_chain_active_identity_mismatch")
                if checkpoint_transitions:
                    if len(checkpoint) > MAX_V3_COMPACT_CHECKPOINT_BYTES:
                        failures.append("v3_compact_checkpoint_size_exceeded")
                    if V3_CHECKPOINT_FORMAT not in text:
                        failures.append("v3_compact_checkpoint_format_missing")
                    try:
                        marker = "Previous checkpoint identity: "
                        predecessor_line = next(
                            line for line in text.splitlines() if line.startswith(marker)
                        )
                        recorded_predecessor = json.loads(predecessor_line[len(marker):])
                        if recorded_predecessor != checkpoint_transitions[-1]["transition"].get("predecessor"):
                            failures.append("v3_compact_checkpoint_predecessor_mismatch")
                    except (StopIteration, ValueError, json.JSONDecodeError):
                        failures.append("v3_compact_checkpoint_predecessor_invalid")
            if type(binding.get("latest_segment_sequence")) is not int or binding.get("latest_segment_sequence") != len(segments):
                failures.append("v3_checkpoint_sequence_mismatch")
            if binding.get("latest_segment_sha256") != (latest.get("sha256") if latest else None):
                failures.append("v3_checkpoint_segment_digest_mismatch")
            if not isinstance(binding.get("source_commit"), str) or not isinstance(binding.get("source_tree"), str):
                failures.append("v3_checkpoint_source_binding_missing")
            if latest:
                if (str(latest.get("path")) not in text
                        or str(latest.get("sha256")) not in text
                        or f"`{binding.get('source_commit')}`" not in text
                        or f"`{binding.get('source_tree')}`" not in text):
                    failures.append("v3_checkpoint_latest_binding_mismatch")
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            failures.append(f"v3_checkpoint_unreadable:{type(exc).__name__}:{exc}")
    return {
        "status": "construction_continuation_custody_ready" if not failures else "invalid",
        "failures": failures,
        "segments_verified": len(segments) if not failures else None,
        "active_checkpoint": checkpoint_path if isinstance(checkpoint_path, str) else None,
        "legacy_journal": anchor_result.get("legacy_journal"),
    }


def append_v3_shard(
    head_bytes: bytes,
    existing_shards: Mapping[str, bytes],
    new_segments: list[dict[str, Any]],
    checkpoint_bytes: bytes,
    *,
    read: Callable[[str, int], bytes],
) -> tuple[bytes, dict[str, bytes]]:
    """Append a bounded immutable V3 shard; root fields never accumulate history."""
    head = json.loads(head_bytes)
    if (not isinstance(head, dict) or type(head.get("schema_version")) is not int
            or head.get("schema_version") != 3 or not isinstance(new_segments, list)
            or not new_segments or len(new_segments) > 64):
        raise ValueError("v3_append_input_invalid")
    if len(head_bytes) > MAX_HEAD_BYTES:
        raise ValueError("v3_head_size_exceeded")
    current_verification = verify_v3_reader(read, V3_INDEX_PATH, head_bytes, head)
    if current_verification.get("status") != "construction_continuation_custody_ready":
        raise ValueError("v3_current_custody_not_ready:" + ";".join(current_verification["failures"]))
    previous = head.get("latest_shard")
    anchor = head.get("history_anchor")
    if not isinstance(anchor, dict):
        raise ValueError("v3_history_anchor_invalid")
    shard_seq = head.get("shard_count")
    latest_sequence = head.get("latest_sequence")
    latest_digest = head.get("latest_segment_sha256")
    if (type(shard_seq) is not int or type(latest_sequence) is not int
            or shard_seq >= MAX_V3_SHARDS or latest_sequence + len(new_segments) > MAX_V3_SEQUENCE):
        raise ValueError("v3_capacity_exceeded")
    predecessor = ({"kind": "v2-root", "path": anchor["path"], "sha256": anchor["sha256"],
                    "git_blob_sha": anchor["git_blob_sha"],
                    "latest_sequence": anchor["latest_sequence"],
                    "latest_segment_sha256": anchor["latest_segment_sha256"]}
                   if previous is None else
                   {"kind": "v3-shard", **_descriptor(previous)})
    first = latest_sequence + 1
    last = latest_sequence + len(new_segments)
    checkpoint_transition: dict[str, Any] | None = None
    chain = head.get("checkpoint_chain")
    if chain is not None:
        current_checkpoint = read(str(head.get("active_checkpoint")), MAX_CHECKPOINT_BYTES)
        expected_previous_checkpoint = chain.get("latest") if isinstance(chain, dict) else None
        actual_previous_checkpoint = _checkpoint_identity(current_checkpoint, latest_sequence)
        if actual_previous_checkpoint != expected_previous_checkpoint:
            raise ValueError("v3_checkpoint_chain_predecessor_mismatch")
        if len(checkpoint_bytes) > MAX_V3_COMPACT_CHECKPOINT_BYTES:
            raise ValueError("v3_compact_checkpoint_size_exceeded")
        try:
            checkpoint_text = checkpoint_bytes.decode("utf-8")
            marker = "Previous checkpoint identity: "
            predecessor_line = next(
                line for line in checkpoint_text.splitlines() if line.startswith(marker)
            )
            recorded_predecessor = json.loads(predecessor_line[len(marker):])
        except (UnicodeDecodeError, StopIteration, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("v3_compact_checkpoint_predecessor_invalid") from exc
        final_segment = new_segments[-1]
        source_commit = final_segment.get("source_commit") or final_segment.get("source_candidate_commit")
        source_tree = final_segment.get("source_tree") or final_segment.get("source_candidate_tree")
        predecessor_record = {
            **actual_previous_checkpoint,
            "source_commit": source_commit,
            "source_tree": source_tree,
        }
        if (
            V3_CHECKPOINT_FORMAT not in checkpoint_text
            or recorded_predecessor != predecessor_record
            or not _valid_digest(source_commit, _HEX40)
            or not _valid_digest(source_tree, _HEX40)
            or f"`{source_commit}`" not in checkpoint_text
            or f"`{source_tree}`" not in checkpoint_text
        ):
            raise ValueError("v3_compact_checkpoint_binding_invalid")
        checkpoint_transition = {
            "schema_version": 1,
            "predecessor": predecessor_record,
            "current": _checkpoint_identity(checkpoint_bytes, last),
        }
    elif V3_CHECKPOINT_FORMAT in checkpoint_bytes.decode("utf-8", errors="ignore"):
        raise ValueError("v3_checkpoint_chain_not_initialized")
    seen_paths = {
        entry.get("path") for entry in materialize_v3_segments(head, read)
        if isinstance(entry, dict)
    }
    expected_segment_predecessor = (
        f"segment-sha256:{latest_digest}" if latest_sequence > 0
        else f"legacy-blob:{json.loads(read(anchor['path'], MAX_INDEX_BYTES))['legacy_journal']['git_blob_sha']}"
    )
    for offset, entry in enumerate(new_segments):
        seq = first + offset
        if (not isinstance(entry, dict) or type(entry.get("sequence")) is not int
                or entry.get("sequence") != seq
                or entry.get("predecessor") != expected_segment_predecessor
                or not isinstance(entry.get("path"), str)
                or not entry["path"].startswith("work/construction/segments/")
                or any(part in {"", ".", ".."} for part in Path(entry["path"]).parts)
                or entry["path"] in seen_paths
                or type(entry.get("bytes")) is not int
                or not 0 <= entry["bytes"] <= MAX_SEGMENT_BYTES
                or not _valid_digest(entry.get("sha256"), _HEX64)
                or not isinstance(entry.get("source_commit") or entry.get("source_candidate_commit"), str)):
            raise ValueError(f"v3_new_segment_binding_invalid:{seq}")
        seen_paths.add(entry["path"])
        latest_digest = entry.get("sha256")
        expected_segment_predecessor = f"segment-sha256:{latest_digest}"
    shard_sequence = shard_seq + 1
    path = _path_for(shard_sequence, first, last)
    shard_document = {"schema_version": 1, "shard_sequence": shard_sequence,
        "first_sequence": first, "last_sequence": last, "predecessor": predecessor,
        "segments": new_segments}
    if checkpoint_transition is not None:
        shard_document["checkpoint_transition"] = checkpoint_transition
    shard_bytes = _json_bytes(shard_document)
    if len(shard_bytes) > MAX_SHARD_BYTES:
        raise ValueError("v3_shard_size_exceeded")
    descriptor = {"path": path, "bytes": len(shard_bytes), "sha256": _sha(shard_bytes),
        "git_blob_sha": _git_blob_sha(shard_bytes), "shard_sequence": shard_sequence,
        "first_sequence": first, "last_sequence": last}
    existing = existing_shards.get(path)
    if existing is None:
        try:
            existing = read(path, MAX_SHARD_BYTES)
        except FileNotFoundError:
            existing = None
    if existing is not None and existing != shard_bytes:
        raise ValueError("v3_existing_shard_conflicts_with_reconstruction")
    head["latest_sequence"] = last
    head["latest_segment_sha256"] = latest_digest
    head["shard_count"] = shard_sequence
    head["latest_shard"] = descriptor
    head["active_checkpoint"] = V3_CHECKPOINT_PATH
    if checkpoint_transition is not None:
        head["checkpoint_chain"]["latest"] = checkpoint_transition["current"]
    binding = head.get("active_checkpoint_binding")
    if not isinstance(binding, dict):
        raise ValueError("v3_checkpoint_binding_invalid")
    try:
        text = checkpoint_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("v3_checkpoint_not_utf8") from exc
    if (len(checkpoint_bytes) > MAX_CHECKPOINT_BYTES
            or str(new_segments[-1].get("path")) not in text
            or str(new_segments[-1].get("sha256")) not in text
            or f"`{binding.get('source_commit')}`" not in text
            or f"`{binding.get('source_tree')}`" not in text):
        raise ValueError("v3_checkpoint_does_not_bind_latest")
    binding.update({"checkpoint_sha256": _sha(checkpoint_bytes),
        "latest_segment_sequence": last, "latest_segment_sha256": latest_digest})
    root_bytes = _json_bytes(head)
    if len(root_bytes) > MAX_HEAD_BYTES:
        raise ValueError("v3_head_size_exceeded")
    return root_bytes, {path: shard_bytes}


def migrate_v2_head(
    v2_index_bytes: bytes,
    v2_checkpoint_bytes: bytes,
    *,
    read: Callable[[str, int], bytes],
) -> bytes:
    """Create a V3 root only after validating the complete V2 history and checkpoint."""
    anchor = _anchor_from_v2(v2_index_bytes)
    if read(V2_INDEX_PATH, MAX_INDEX_BYTES) != v2_index_bytes:
        raise ValueError("v2_anchor_readback_mismatch")
    verified = verify_continuation_reader(read, V2_INDEX_PATH)
    if verified.get("status") != "construction_continuation_custody_ready":
        raise ValueError("v2_anchor_custody_not_ready:" + ";".join(verified.get("failures", [])))
    v2 = json.loads(v2_index_bytes)
    binding = v2.get("active_checkpoint_binding")
    if not isinstance(binding, dict) or _sha(v2_checkpoint_bytes) != binding.get("checkpoint_sha256"):
        raise ValueError("v2_checkpoint_identity_mismatch")
    if not isinstance(v2.get("active_checkpoint"), str):
        raise ValueError("v2_checkpoint_path_missing")
    # The caller performs full path and segment verification before activating this prepared root.
    head = {
        "schema_version": 3,
        "continuation_schema_version": 1,
        "history_anchor": anchor,
        "latest_sequence": anchor["latest_sequence"],
        "latest_segment_sha256": anchor["latest_segment_sha256"],
        "shard_count": 0,
        "latest_shard": None,
        "active_checkpoint": v2["active_checkpoint"],
        "active_checkpoint_binding": dict(binding),
    }
    payload = _json_bytes(head)
    if len(payload) > MAX_HEAD_BYTES:
        raise ValueError("v3_head_size_exceeded")
    return payload
