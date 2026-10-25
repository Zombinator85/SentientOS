"""Build the versioned sharded construction index without rewriting history."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from scripts.verify_construction_continuation_custody import (
    _read_regular,
    materialize_index_segments,
    verify_construction_continuation,
    verify_continuation_reader,
)

MAX_SEGMENTS_PER_SHARD = 64
MAX_SHARDS = 4096
MAX_SHARD_BYTES = 128 * 1024
V2_INDEX_PATH = "work/construction/index-v2.json"
V2_CHECKPOINT_PATH = "work/construction/active_checkpoint_v2.md"
V2_SHARD_DIRECTORY = "work/construction/shards-v2"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _ensure_directory_chain(root: Path, relative_directory: str) -> Path:
    cursor = root
    for component in Path(relative_directory).parts:
        if component in {"", ".", ".."}:
            raise ValueError("shard_directory_path_invalid")
        cursor = cursor / component
        try:
            cursor.lstat()
        except FileNotFoundError:
            cursor.mkdir()
            cursor.lstat()
        if cursor.is_symlink() or not cursor.is_dir():
            raise ValueError("shard_directory_component_rejected")
    return cursor


def _atomic_write(root: Path, destination: Path, payload: bytes, suffix: str) -> None:
    try:
        relative = destination.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("destination_outside_repository") from exc
    rel = PurePosixPath(relative)
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError("destination_path_invalid")
    _ensure_directory_chain(root, rel.parent.as_posix())
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError("destination_not_regular_file")
    temporary = destination.with_name(destination.name + suffix)
    if temporary.is_symlink() or (temporary.exists() and not temporary.is_file()):
        raise ValueError("temporary_path_not_regular_file")
    if temporary.exists():
        if temporary.read_bytes() != payload:
            raise ValueError("temporary_path_conflict")
    else:
        temporary.write_bytes(payload)
    os.replace(temporary, destination)


def build_sharded_index(
    current_index_bytes: bytes,
    anchor_index_bytes: bytes,
) -> tuple[bytes, dict[str, bytes]]:
    """Convert a v1 index to v2 while retaining its exact ordered segment records.

    ``anchor_index_bytes`` must be the exact v1 index from the immutable base
    commit. The current v1 index may append records after that base; the anchor
    and every record before it are checked before any shard bytes are returned.
    """
    current = json.loads(current_index_bytes)
    anchor = json.loads(anchor_index_bytes)
    if (not isinstance(current, dict)
            or type(current.get("schema_version")) is not int
            or current.get("schema_version") != 1):
        raise ValueError("current_index_must_be_schema_v1")
    if (not isinstance(anchor, dict)
            or type(anchor.get("schema_version")) is not int
            or anchor.get("schema_version") != 1):
        raise ValueError("anchor_index_must_be_schema_v1")
    current_segments = current.get("segments")
    anchor_segments = anchor.get("segments")
    if not isinstance(current_segments, list) or not isinstance(anchor_segments, list):
        raise ValueError("index_segments_invalid")
    if len(current_segments) > MAX_SHARDS or len(anchor_segments) > len(current_segments):
        raise ValueError("index_segment_count_out_of_bounds")
    if current.get("legacy_journal") != anchor.get("legacy_journal"):
        raise ValueError("frozen_journal_definition_changed")
    if current_segments[: len(anchor_segments)] != anchor_segments:
        raise ValueError("immutable_anchor_segment_prefix_changed")
    if (type(current.get("latest_sequence")) is not int
            or current.get("latest_sequence") != len(current_segments)):
        raise ValueError("current_index_latest_sequence_mismatch")
    if (type(anchor.get("latest_sequence")) is not int
            or anchor.get("latest_sequence") != len(anchor_segments)):
        raise ValueError("anchor_index_latest_sequence_mismatch")

    anchor_latest_sha = (
        anchor_segments[-1].get("sha256") if anchor_segments else None
    )
    anchor_sha = _sha256(anchor_index_bytes)
    history_anchor = {
        "schema_version": 1,
        "source_index_schema_version": 1,
        "path": "work/construction/index.json",
        "source_index_sha256": anchor_sha,
        "source_index_git_blob_sha": _git_blob_sha(anchor_index_bytes),
        "segment_count": len(anchor_segments),
        "latest_sequence": len(anchor_segments),
        "latest_segment_sha256": anchor_latest_sha,
    }

    shards: dict[str, bytes] = {}
    descriptors: list[dict[str, Any]] = []
    previous = f"index-sha256:{anchor_sha}"
    continuation_segments = current_segments[len(anchor_segments):]
    for offset in range(0, len(continuation_segments), MAX_SEGMENTS_PER_SHARD):
        chunk = continuation_segments[offset : offset + MAX_SEGMENTS_PER_SHARD]
        shard_sequence = len(descriptors) + 1
        first_sequence = len(anchor_segments) + offset + 1
        last_sequence = first_sequence + len(chunk) - 1
        path = (
            f"{V2_SHARD_DIRECTORY}/"
            f"{shard_sequence:04d}-{first_sequence:04d}-{last_sequence:04d}.json"
        )
        shard_doc = {
            "schema_version": 1,
            "shard_sequence": shard_sequence,
            "first_sequence": first_sequence,
            "last_sequence": last_sequence,
            "predecessor": previous,
            "segments": chunk,
        }
        payload = _json_bytes(shard_doc)
        if len(payload) > MAX_SHARD_BYTES:
            raise ValueError(f"shard_size_exceeded:{shard_sequence}")
        digest = _sha256(payload)
        descriptor = {
            "shard_sequence": shard_sequence,
            "first_sequence": first_sequence,
            "last_sequence": last_sequence,
            "segment_count": len(chunk),
            "path": path,
            "bytes": len(payload),
            "sha256": digest,
            "git_blob_sha": _git_blob_sha(payload),
            "predecessor": previous,
        }
        descriptors.append(descriptor)
        shards[path] = payload
        previous = f"shard-sha256:{digest}"
    if len(descriptors) > MAX_SHARDS:
        raise ValueError("shard_count_out_of_bounds")

    v2 = dict(current)
    v2.pop("segments", None)
    v2["schema_version"] = 2
    v2["shard_schema_version"] = 1
    v2["history_anchor"] = history_anchor
    v2["shards"] = descriptors
    v2["active_checkpoint"] = (
        V2_CHECKPOINT_PATH if continuation_segments else anchor["active_checkpoint"]
    )
    return _json_bytes(v2), shards


def append_segments_to_sharded_index(
    index_bytes: bytes,
    existing_shards: Mapping[str, bytes],
    new_segments: list[dict[str, Any]],
    checkpoint_bytes: bytes,
) -> tuple[bytes, dict[str, bytes]]:
    """Append immutable shard bytes and update only the small root index.

    The caller writes the returned shard under its returned path and the supplied
    checkpoint bytes at the root's active checkpoint path. Existing shard bytes
    are read-only inputs and are never returned for rewriting.
    """
    index = json.loads(index_bytes)
    if (not isinstance(index, dict)
            or type(index.get("schema_version")) is not int
            or index.get("schema_version") != 2):
        raise ValueError("current_index_must_be_schema_v2")
    if not isinstance(new_segments, list) or not new_segments:
        raise ValueError("new_segments_required")
    if len(new_segments) > MAX_SEGMENTS_PER_SHARD:
        raise ValueError("new_segment_batch_exceeds_shard_limit")

    def read(path: str, limit: int) -> bytes:
        payload = existing_shards.get(path)
        if payload is None:
            raise ValueError(f"existing_shard_missing:{path}")
        if len(payload) > limit:
            raise ValueError(f"existing_shard_too_large:{path}")
        return payload

    prior = materialize_index_segments(index, read)
    if (type(index.get("latest_sequence")) is not int
            or index.get("latest_sequence") != len(prior)):
        raise ValueError("current_index_latest_sequence_mismatch")
    legacy = index.get("legacy_journal")
    if not isinstance(legacy, dict) or not isinstance(legacy.get("git_blob_sha"), str):
        raise ValueError("legacy_journal_identity_missing")
    previous_segment = str(legacy["git_blob_sha"])
    seen_paths: set[str] = set()
    for expected_sequence, entry in enumerate(prior, start=1):
        if type(entry.get("sequence")) is not int or entry.get("sequence") != expected_sequence:
            raise ValueError(f"existing_segment_sequence_mismatch:{expected_sequence}")
        expected_predecessor = (
            f"legacy-blob:{previous_segment}"
            if expected_sequence == 1
            else f"segment-sha256:{previous_segment}"
        )
        if entry.get("predecessor") != expected_predecessor:
            raise ValueError(f"existing_segment_predecessor_mismatch:{expected_sequence}")
        path = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(path, str) or path in seen_paths:
            raise ValueError("existing_segment_path_invalid_or_duplicate")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"existing_segment_digest_invalid:{expected_sequence}")
        seen_paths.add(path)
        previous_segment = digest

    next_sequence = len(prior) + 1
    for offset, entry in enumerate(new_segments):
        expected_sequence = next_sequence + offset
        if (not isinstance(entry, dict)
                or type(entry.get("sequence")) is not int
                or entry.get("sequence") != expected_sequence):
            raise ValueError(f"new_segment_sequence_mismatch:{expected_sequence}")
        expected_predecessor = (
            f"legacy-blob:{previous_segment}"
            if expected_sequence == 1
            else f"segment-sha256:{previous_segment}"
        )
        if entry.get("predecessor") != expected_predecessor:
            raise ValueError(f"new_segment_predecessor_mismatch:{expected_sequence}")
        path = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(path, str) or path in seen_paths:
            raise ValueError("new_segment_path_invalid_or_duplicate")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"new_segment_digest_invalid:{expected_sequence}")
        seen_paths.add(path)
        previous_segment = digest

    descriptors = index.get("shards")
    anchor = index.get("history_anchor")
    binding = index.get("active_checkpoint_binding")
    if not isinstance(descriptors, list) or not isinstance(anchor, dict) or not isinstance(binding, dict):
        raise ValueError("sharded_index_metadata_invalid")
    if len(descriptors) >= MAX_SHARDS or len(prior) + len(new_segments) > 4096:
        raise ValueError("sharded_index_capacity_exceeded")
    latest_descriptor = descriptors[-1] if descriptors else None
    previous_shard = (
        f"shard-sha256:{latest_descriptor['sha256']}"
        if isinstance(latest_descriptor, dict)
        else f"index-sha256:{anchor['source_index_sha256']}"
    )
    shard_sequence = len(descriptors) + 1
    first_sequence = len(prior) + 1
    last_sequence = len(prior) + len(new_segments)
    path = (
        f"{V2_SHARD_DIRECTORY}/"
        f"{shard_sequence:04d}-{first_sequence:04d}-{last_sequence:04d}.json"
    )
    if path in existing_shards:
        raise ValueError("new_shard_path_already_exists")
    shard_doc = {
        "schema_version": 1,
        "shard_sequence": shard_sequence,
        "first_sequence": first_sequence,
        "last_sequence": last_sequence,
        "predecessor": previous_shard,
        "segments": new_segments,
    }
    shard_bytes = _json_bytes(shard_doc)
    if len(shard_bytes) > MAX_SHARD_BYTES:
        raise ValueError("new_shard_size_exceeded")
    digest = _sha256(shard_bytes)
    descriptors.append({
        "shard_sequence": shard_sequence,
        "first_sequence": first_sequence,
        "last_sequence": last_sequence,
        "segment_count": len(new_segments),
        "path": path,
        "bytes": len(shard_bytes),
        "sha256": digest,
        "git_blob_sha": _git_blob_sha(shard_bytes),
        "predecessor": previous_shard,
    })

    try:
        checkpoint_text = checkpoint_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("checkpoint_not_utf8") from exc
    if len(checkpoint_bytes) > 64 * 1024:
        raise ValueError("checkpoint_size_exceeded")
    source_commit = binding.get("source_commit")
    source_tree = binding.get("source_tree")
    latest = new_segments[-1]
    if (
        not isinstance(source_commit, str)
        or not isinstance(source_tree, str)
        or f"`{source_commit}`" not in checkpoint_text
        or f"`{source_tree}`" not in checkpoint_text
        or str(latest.get("path")) not in checkpoint_text
        or str(latest.get("sha256")) not in checkpoint_text
    ):
        raise ValueError("checkpoint_does_not_bind_new_latest_segment")

    checkpoint_digest = _sha256(checkpoint_bytes)
    binding["checkpoint_sha256"] = checkpoint_digest
    binding["latest_segment_sequence"] = last_sequence
    binding["latest_segment_sha256"] = previous_segment
    index["checkpoint_sha256"] = checkpoint_digest
    index["latest_sequence"] = last_sequence
    index["active_checkpoint_binding"] = binding
    index["active_checkpoint"] = V2_CHECKPOINT_PATH
    root_bytes = _json_bytes(index)
    if len(root_bytes) > 2 * 1024 * 1024:
        raise ValueError("root_index_size_exceeded")
    return root_bytes, {path: shard_bytes}


def migrate_repository(
    root: Path, anchor_index_path: Path, anchor_checkpoint_path: Path
) -> dict[str, Any]:
    """Freeze v1 and recoverably activate a continuation-only v2 root."""
    root = root.resolve(strict=True)
    index_path = root / "work/construction/index.json"
    if index_path.is_symlink():
        raise ValueError("construction_index_symlink_rejected")
    v2_index_path = root / V2_INDEX_PATH
    v2_checkpoint_path = root / V2_CHECKPOINT_PATH
    current_bytes = index_path.read_bytes()
    if len(current_bytes) > 2 * 1024 * 1024:
        raise ValueError("construction_index_size_exceeded")
    anchor_bytes = anchor_index_path.read_bytes()
    if len(anchor_bytes) > 2 * 1024 * 1024:
        raise ValueError("anchor_index_size_exceeded")
    anchor_checkpoint = anchor_checkpoint_path.read_bytes()
    anchor = json.loads(anchor_bytes)
    anchor_binding = anchor.get("active_checkpoint_binding")
    if not isinstance(anchor_binding, dict) or _sha256(anchor_checkpoint) != anchor_binding.get("checkpoint_sha256"):
        raise ValueError("anchor_checkpoint_identity_mismatch")
    anchor_checkpoint_relative = anchor.get("active_checkpoint")
    if not isinstance(anchor_checkpoint_relative, str):
        raise ValueError("anchor_checkpoint_path_invalid")
    anchor_checkpoint_destination = root / anchor_checkpoint_relative
    if anchor_checkpoint_destination.is_symlink():
        raise ValueError("anchor_checkpoint_symlink_rejected")

    reader = lambda path, limit: _read_regular(root, path, limit=limit)
    if v2_index_path.exists() or v2_index_path.is_symlink():
        if v2_index_path.is_symlink() or not v2_index_path.is_file():
            raise ValueError("v2_index_not_regular_file")
        if current_bytes == anchor_bytes:
            # Recovery after v2 activation and v1 index replacement: restore the
            # exact frozen checkpoint first, then require complete v2 custody.
            _atomic_write(root, anchor_checkpoint_destination, anchor_checkpoint, ".anchor.tmp")
            final = verify_construction_continuation(root)
            if final.get("status") != "construction_continuation_custody_ready":
                raise ValueError("activated_v2_recovery_verification_failed")
            return {"status": "construction_index_sharded_v2_ready", "recovered": True,
                "root_index_bytes": v2_index_path.stat().st_size, "shards_written": 0,
                "shard_bytes_total": 0, "latest_sequence": final.get("segments_verified")}

    current_index = json.loads(current_bytes)
    if (not isinstance(current_index, dict)
            or type(current_index.get("schema_version")) is not int
            or current_index.get("schema_version") != 1):
        raise ValueError("current_index_must_be_schema_v1")
    current_checkpoint_path = current_index.get("active_checkpoint")
    if not isinstance(current_checkpoint_path, str):
        raise ValueError("current_checkpoint_path_invalid")
    binding = current_index.get("active_checkpoint_binding")
    if not isinstance(binding, dict):
        raise ValueError("current_checkpoint_binding_invalid")
    current_checkpoint_path_abs = root / current_checkpoint_path
    current_checkpoint = None
    for checkpoint_candidate in (current_checkpoint_path_abs, v2_checkpoint_path):
        if checkpoint_candidate.is_symlink() or not checkpoint_candidate.is_file():
            continue
        candidate_bytes = checkpoint_candidate.read_bytes()
        if _sha256(candidate_bytes) == binding.get("checkpoint_sha256"):
            current_checkpoint = candidate_bytes
            break
    if current_checkpoint is None:
        raise ValueError("current_checkpoint_bytes_unavailable_for_recovery")

    # Before activation, v1 itself must still be complete. After activation, an
    # interrupted prior attempt is allowed only if its prepared root and shard
    # bytes exactly match deterministic reconstruction from the surviving v1 data.
    if not (v2_index_path.exists() or v2_index_path.is_symlink()):
        custody = verify_continuation_reader(reader, "work/construction/index.json")
        if custody.get("status") != "construction_continuation_custody_ready":
            raise ValueError("current_construction_custody_not_ready")
    new_index, shards = build_sharded_index(current_bytes, anchor_bytes)
    new_index_doc = json.loads(new_index)
    if new_index_doc.get("active_checkpoint") == V2_CHECKPOINT_PATH and _sha256(current_checkpoint) != new_index_doc.get("checkpoint_sha256"):
        raise ValueError("prepared_v2_checkpoint_identity_mismatch")
    if v2_index_path.exists():
        if v2_index_path.read_bytes() != new_index:
            raise ValueError("interrupted_v2_root_conflicts_with_reconstruction")
    if v2_checkpoint_path.is_symlink():
        raise ValueError("v2_checkpoint_symlink_rejected")
    if v2_checkpoint_path.exists():
        if v2_checkpoint_path.read_bytes() != current_checkpoint:
            raise ValueError("interrupted_v2_checkpoint_conflicts_with_reconstruction")

    for relative, payload in shards.items():
        destination = root / relative
        _ensure_directory_chain(root, V2_SHARD_DIRECTORY)
        if destination.is_symlink():
            raise ValueError(f"shard_symlink_rejected:{relative}")
        if destination.exists():
            if destination.read_bytes() != payload:
                raise ValueError(f"existing_shard_conflict:{relative}")
            continue
        _atomic_write(root, destination, payload, ".tmp")

    if new_index_doc["active_checkpoint"] == V2_CHECKPOINT_PATH and not v2_checkpoint_path.exists():
        _atomic_write(root, v2_checkpoint_path, current_checkpoint, ".tmp")
    if not v2_index_path.exists():
        _atomic_write(root, v2_index_path, new_index, ".tmp")
    # V2 activation precedes restoration of the anchor. An interruption here
    # remains fail-closed and the identical invocation can finish the restore.
    _atomic_write(root, anchor_checkpoint_destination, anchor_checkpoint, ".anchor.tmp")
    _atomic_write(root, index_path, anchor_bytes, ".anchor.tmp")
    final_verification = verify_construction_continuation(root)
    if final_verification.get("status") != "construction_continuation_custody_ready":
        raise ValueError("migrated_construction_custody_not_ready")
    return {
        "status": "construction_index_sharded_v2_ready",
        "root_index_bytes": len(new_index),
        "shards_written": len(shards),
        "shard_bytes_total": sum(map(len, shards.values())),
        "latest_sequence": json.loads(new_index)["latest_sequence"],
        "recovered": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--anchor-index", type=Path, required=True)
    parser.add_argument("--anchor-checkpoint", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = migrate_repository(args.repo_root, args.anchor_index, args.anchor_checkpoint)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"status": "invalid", "reason": f"{type(exc).__name__}:{exc}"}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "construction_index_sharded_v2_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
