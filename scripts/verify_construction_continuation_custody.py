from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any, Callable

MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_CHECKPOINT_BYTES = 64 * 1024
MAX_LEGACY_BYTES = 2 * 1024 * 1024
MAX_SEGMENT_BYTES = 64 * 1024
MAX_SEGMENTS = 4096
MAX_SHARDS = 4096
MAX_SHARD_BYTES = 128 * 1024
MAX_SHARD_SEGMENTS = 64
V2_SHARD_DIRECTORY = "work/construction/shards-v2"
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def _git_blob_sha(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def _read_regular(root: Path, relative: str, *, limit: int) -> bytes:
    rel = PurePosixPath(relative)
    if rel.is_absolute() or not rel.parts or any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError(f"unsafe_path:{relative}")
    candidate = root.joinpath(*rel.parts)
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        info = cursor.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"symlink_path:{relative}")
    info = candidate.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"not_regular_file:{relative}")
    if info.st_size > limit:
        raise ValueError(f"file_too_large:{relative}")
    return candidate.read_bytes()


def verify_construction_continuation(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    v2_index = root / "work/construction/index-v2.json"
    index_path = (
        "work/construction/index-v2.json"
        if v2_index.exists() or v2_index.is_symlink()
        else "work/construction/index.json"
    )
    return verify_continuation_reader(
        lambda path, limit: _read_regular(root, path, limit=limit), index_path
    )


def _load_index_segments(
    index: dict[str, Any],
    read: Callable[[str, int], bytes],
    failures: list[str],
) -> list[dict[str, Any]]:
    """Load v1 inline entries or bounded v2 shards and verify shard custody."""
    schema_version = index.get("schema_version")
    if type(schema_version) is int and schema_version == 1:
        inline_segments = index.get("segments")
        if (
            not isinstance(inline_segments, list)
            or len(inline_segments) > MAX_SEGMENTS
            or type(index.get("latest_sequence")) is not int
            or index.get("latest_sequence") != len(inline_segments)
        ):
            failures.append("segments_invalid_or_unbounded")
            return []
        return [entry for entry in inline_segments if isinstance(entry, dict)]

    if type(schema_version) is not int or schema_version != 2:
        failures.append("index_schema_invalid")
        return []
    if "segments" in index:
        failures.append("sharded_index_inline_segments_forbidden")
    if type(index.get("shard_schema_version")) is not int or index.get("shard_schema_version") != 1:
        failures.append("shard_schema_version_unsupported")
    anchor = index.get("history_anchor")
    if not isinstance(anchor, dict):
        failures.append("history_anchor_missing")
        anchor = {}
    anchor_sha = anchor.get("source_index_sha256")
    anchor_blob = anchor.get("source_index_git_blob_sha")
    anchor_count = anchor.get("segment_count")
    latest_sequence_value = index.get("latest_sequence")
    latest_sequence = (
        latest_sequence_value if type(latest_sequence_value) is int else -1
    )
    anchor_latest = anchor.get("latest_sequence")
    anchor_latest_sha = anchor.get("latest_segment_sha256")
    anchor_path = anchor.get("path")
    if type(anchor_count) is not int:
        anchor_count = -1
    if (
        type(anchor.get("schema_version")) is not int
        or anchor.get("schema_version") != 1
        or type(anchor.get("source_index_schema_version")) is not int
        or anchor.get("source_index_schema_version") != 1
        or anchor_path != "work/construction/index.json"
        or not isinstance(anchor_sha, str)
        or _HEX64_RE.fullmatch(anchor_sha) is None
        or not isinstance(anchor_blob, str)
        or _HEX40_RE.fullmatch(anchor_blob) is None
        or type(anchor_count) is not int
        or not 0 <= anchor_count <= MAX_SEGMENTS
        or type(anchor_latest) is not int
        or anchor_latest != anchor_count
        or (anchor_count == 0 and anchor_latest_sha is not None)
        or (anchor_count > 0 and (
            not isinstance(anchor_latest_sha, str)
            or _HEX64_RE.fullmatch(anchor_latest_sha) is None
        ))
    ):
        failures.append("history_anchor_invalid")
    anchor_segments: list[dict[str, Any]] = []
    if isinstance(anchor_path, str):
        try:
            anchor_bytes = read(anchor_path, MAX_INDEX_BYTES)
            if hashlib.sha256(anchor_bytes).hexdigest() != anchor_sha:
                failures.append("history_anchor_index_sha256_mismatch")
            if _git_blob_sha(anchor_bytes) != anchor_blob:
                failures.append("history_anchor_index_git_blob_mismatch")
            frozen_index = json.loads(anchor_bytes)
            if (
                not isinstance(frozen_index, dict)
                or type(frozen_index.get("schema_version")) is not int
                or frozen_index.get("schema_version") != 1
            ):
                failures.append("history_anchor_index_schema_mismatch")
            else:
                frozen_segments = frozen_index.get("segments")
                if isinstance(frozen_segments, list):
                    anchor_segments = [e for e in frozen_segments if isinstance(e, dict)]
                if (
                    type(frozen_index.get("latest_sequence")) is not int
                    or frozen_index.get("latest_sequence") != anchor_count
                    or len(anchor_segments) != anchor_count
                    or frozen_index.get("legacy_journal") != index.get("legacy_journal")
                    or (anchor_count < latest_sequence
                        and frozen_index.get("active_checkpoint") == index.get("active_checkpoint"))
                ):
                    failures.append("history_anchor_index_metadata_mismatch")
                if anchor_segments and anchor_segments[-1].get("sha256") != anchor_latest_sha:
                    failures.append("history_anchor_latest_segment_mismatch")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"history_anchor_index_unreadable:{type(exc).__name__}:{exc}")

    descriptors = index.get("shards")
    if (
        not isinstance(descriptors, list)
        or len(descriptors) > MAX_SHARDS
        or not 0 <= latest_sequence <= MAX_SEGMENTS
    ):
        failures.append("shard_descriptors_invalid_or_unbounded")
        return []
    if (latest_sequence == anchor_count) != (len(descriptors) == 0):
        failures.append("shard_empty_history_mismatch")

    segments: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    expected_sequence = anchor_count + 1
    previous_shard = f"index-sha256:{anchor_sha}" if isinstance(anchor_sha, str) else ""
    for expected_shard_sequence, descriptor in enumerate(descriptors, start=1):
        if not isinstance(descriptor, dict):
            failures.append(f"shard_{expected_shard_sequence}_descriptor_invalid")
            continue
        path = descriptor.get("path")
        first_sequence = descriptor.get("first_sequence")
        last_sequence = descriptor.get("last_sequence")
        count = descriptor.get("segment_count")
        size = descriptor.get("bytes")
        digest = descriptor.get("sha256")
        blob_sha = descriptor.get("git_blob_sha")
        if (
            type(descriptor.get("shard_sequence")) is not int
            or descriptor.get("shard_sequence") != expected_shard_sequence
            or not isinstance(path, str)
            or path in seen_paths
            or type(first_sequence) is not int
            or type(last_sequence) is not int
            or type(count) is not int
            or type(size) is not int
            or not isinstance(digest, str)
            or _HEX64_RE.fullmatch(digest) is None
            or not isinstance(blob_sha, str)
            or _HEX40_RE.fullmatch(blob_sha) is None
        ):
            failures.append(f"shard_{expected_shard_sequence}_descriptor_invalid")
            continue
        seen_paths.add(path)
        if (
            first_sequence != expected_sequence
            or last_sequence < first_sequence
            or count != last_sequence - first_sequence + 1
            or count > MAX_SHARD_SEGMENTS
        ):
            failures.append(f"shard_{expected_shard_sequence}_range_invalid")
        expected_path = (
            f"{V2_SHARD_DIRECTORY}/{expected_shard_sequence:04d}-"
            f"{first_sequence:04d}-{last_sequence:04d}.json"
        )
        if path != expected_path:
            failures.append(f"shard_{expected_shard_sequence}_path_invalid")
        if descriptor.get("predecessor") != previous_shard:
            failures.append(f"shard_{expected_shard_sequence}_predecessor_mismatch")
        if size > MAX_SHARD_BYTES:
            failures.append(f"shard_{expected_shard_sequence}_size_exceeded")
            expected_sequence = last_sequence + 1
            previous_shard = f"shard-sha256:{digest}"
            continue
        try:
            content = read(path, MAX_SHARD_BYTES)
            if len(content) != size:
                failures.append(f"shard_{expected_shard_sequence}_byte_count_mismatch")
            if hashlib.sha256(content).hexdigest() != digest:
                failures.append(f"shard_{expected_shard_sequence}_sha256_mismatch")
            if _git_blob_sha(content) != blob_sha:
                failures.append(f"shard_{expected_shard_sequence}_git_blob_mismatch")
            shard = json.loads(content)
            shard_segments = shard.get("segments") if isinstance(shard, dict) else None
            if (
                not isinstance(shard, dict)
                or type(shard.get("schema_version")) is not int
                or shard.get("schema_version") != 1
                or type(shard.get("shard_sequence")) is not int
                or shard.get("shard_sequence") != expected_shard_sequence
                or type(shard.get("first_sequence")) is not int
                or shard.get("first_sequence") != first_sequence
                or type(shard.get("last_sequence")) is not int
                or shard.get("last_sequence") != last_sequence
                or shard.get("predecessor") != previous_shard
                or not isinstance(shard_segments, list)
                or len(shard_segments) != count
            ):
                failures.append(f"shard_{expected_shard_sequence}_content_invalid")
            elif all(isinstance(entry, dict) for entry in shard_segments):
                segments.extend(shard_segments)
            else:
                failures.append(f"shard_{expected_shard_sequence}_segments_invalid")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(
                f"shard_{expected_shard_sequence}_unreadable:{type(exc).__name__}:{exc}"
            )
        expected_sequence = last_sequence + 1
        previous_shard = f"shard-sha256:{digest}"

    if len(segments) != latest_sequence - anchor_count or expected_sequence != latest_sequence + 1:
        failures.append("shard_sequence_coverage_mismatch")
    return segments


def materialize_index_segments(
    index: dict[str, Any], read: Callable[[str, int], bytes]
) -> list[dict[str, Any]]:
    """Return ordered records only when the selected index schema verifies."""
    failures: list[str] = []
    segments = _load_index_segments(index, read, failures)
    if index.get("schema_version") == 2:
        anchor = index.get("history_anchor")
        try:
            if not isinstance(anchor, dict):
                raise ValueError("history_anchor_missing")
            anchor_index = json.loads(read(str(anchor.get("path")), MAX_INDEX_BYTES))
            if not isinstance(anchor_index, dict):
                raise ValueError("history_anchor_index_invalid")
            anchor_segments = _load_index_segments(anchor_index, read, failures)
            segments = anchor_segments + segments
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"history_anchor_materialization_failed:{type(exc).__name__}:{exc}")
    if failures:
        raise ValueError(";".join(failures))
    return segments


def verify_continuation_reader(
    read: Callable[[str, int], bytes],
    index_path: str = "work/construction/index.json",
) -> dict[str, Any]:
    """Verify identical custody predicates for disk or an immutable Git tree."""
    failures: list[str] = []
    try:
        index_bytes = read(index_path, MAX_INDEX_BYTES)
        index = json.loads(index_bytes)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "failures": [f"index_unreadable:{type(exc).__name__}:{exc}"]}
    if (
        not isinstance(index, dict)
        or type(index.get("schema_version")) is not int
        or index.get("schema_version") not in {1, 2}
    ):
        return {"status": "invalid", "failures": ["index_schema_invalid"]}

    legacy = index.get("legacy_journal")
    if not isinstance(legacy, dict) or legacy.get("frozen") is not True:
        failures.append("legacy_journal_not_declared_frozen")
        legacy = {}
    try:
        legacy_bytes = read(str(legacy["path"]), MAX_LEGACY_BYTES)
        actual_sha256 = hashlib.sha256(legacy_bytes).hexdigest()
        actual_blob = _git_blob_sha(legacy_bytes)
        if (type(legacy.get("bytes")) is not int
                or len(legacy_bytes) != legacy.get("bytes")):
            failures.append("legacy_journal_byte_count_mismatch")
        if actual_sha256 != legacy.get("sha256"):
            failures.append("legacy_journal_sha256_mismatch")
        if actual_blob != legacy.get("git_blob_sha"):
            failures.append("legacy_journal_git_blob_mismatch")
    except (OSError, KeyError, ValueError) as exc:
        failures.append(f"legacy_journal_unreadable:{type(exc).__name__}:{exc}")

    if index.get("schema_version") == 2:
        anchor = index.get("history_anchor")
        try:
            if not isinstance(anchor, dict):
                raise ValueError("history_anchor_missing")
            anchor_index = json.loads(read(str(anchor.get("path")), MAX_INDEX_BYTES))
            if (
                not isinstance(anchor_index, dict)
                or type(anchor_index.get("schema_version")) is not int
                or anchor_index.get("schema_version") != 1
            ):
                raise ValueError("history_anchor_index_invalid")
            anchor_segments = _load_index_segments(anchor_index, read, failures)
            anchor_checkpoint_path = anchor_index.get("active_checkpoint")
            anchor_binding = anchor_index.get("active_checkpoint_binding")
            if not isinstance(anchor_checkpoint_path, str) or not isinstance(anchor_binding, dict):
                failures.append("history_anchor_checkpoint_binding_missing")
            else:
                anchor_checkpoint = read(anchor_checkpoint_path, MAX_CHECKPOINT_BYTES)
                if hashlib.sha256(anchor_checkpoint).hexdigest() != anchor_binding.get("checkpoint_sha256"):
                    failures.append("history_anchor_checkpoint_sha256_mismatch")
                if anchor_binding.get("latest_segment_sequence") != len(anchor_segments):
                    failures.append("history_anchor_checkpoint_sequence_mismatch")
                if anchor_segments and anchor_binding.get("latest_segment_sha256") != anchor_segments[-1].get("sha256"):
                    failures.append("history_anchor_checkpoint_segment_mismatch")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"history_anchor_unreadable:{type(exc).__name__}:{exc}")
            anchor_segments = []
    else:
        anchor_segments = []
    continuation_segments = _load_index_segments(index, read, failures)
    segments = anchor_segments + continuation_segments
    seen_paths: set[str] = set()
    previous_sha = str(legacy.get("git_blob_sha", ""))
    for expected_sequence, entry in enumerate(segments, start=1):
        if not isinstance(entry, dict):
            failures.append(f"segment_{expected_sequence}_entry_invalid")
            continue
        path = entry.get("path")
        if not isinstance(path, str) or path in seen_paths:
            failures.append(f"segment_{expected_sequence}_path_missing_or_duplicate")
            continue
        seen_paths.add(path)
        if type(entry.get("sequence")) is not int or entry.get("sequence") != expected_sequence:
            failures.append(f"segment_{expected_sequence}_sequence_mismatch")
        expected_predecessor = (
            f"legacy-blob:{previous_sha}"
            if expected_sequence == 1
            else f"segment-sha256:{previous_sha}"
        )
        if entry.get("predecessor") != expected_predecessor:
            failures.append(f"segment_{expected_sequence}_predecessor_mismatch")
        try:
            content = read(path, MAX_SEGMENT_BYTES)
            digest = hashlib.sha256(content).hexdigest()
            if (type(entry.get("bytes")) is not int
                    or len(content) != entry.get("bytes")):
                failures.append(f"segment_{expected_sequence}_byte_count_mismatch")
            if digest != entry.get("sha256"):
                failures.append(f"segment_{expected_sequence}_sha256_mismatch")
            if not isinstance(entry.get("source_commit") or entry.get("source_candidate_commit"), str):
                failures.append(f"segment_{expected_sequence}_source_commit_missing")
            previous_sha = digest
        except (OSError, ValueError) as exc:
            failures.append(f"segment_{expected_sequence}_unreadable:{type(exc).__name__}:{exc}")
            previous_sha = str(entry.get("sha256", ""))

    checkpoint_path = index.get("active_checkpoint")
    binding = index.get("active_checkpoint_binding")
    if not isinstance(checkpoint_path, str) or not isinstance(binding, dict):
        failures.append("active_checkpoint_binding_missing")
    else:
        try:
            checkpoint = read(checkpoint_path, MAX_CHECKPOINT_BYTES)
            text = checkpoint.decode("utf-8")
            checkpoint_digest = hashlib.sha256(checkpoint).hexdigest()
            if binding.get("checkpoint_sha256") != checkpoint_digest:
                failures.append("active_checkpoint_sha256_mismatch")
            if (
                type(binding.get("latest_segment_sequence")) is not int
                or binding.get("latest_segment_sequence") != len(segments)
            ):
                failures.append("active_checkpoint_segment_sequence_mismatch")
            if segments and binding.get("latest_segment_sha256") != segments[-1].get("sha256"):
                failures.append("active_checkpoint_segment_digest_mismatch")
            if not segments and binding.get("latest_segment_sha256") is not None:
                failures.append("active_checkpoint_empty_segment_binding_mismatch")
            source_commit = binding.get("source_commit")
            source_tree = binding.get("source_tree")
            if not isinstance(source_commit, str) or not isinstance(source_tree, str):
                failures.append("active_checkpoint_source_identity_missing")
            elif f"`{source_commit}`" not in text or f"`{source_tree}`" not in text:
                failures.append("active_checkpoint_source_identity_contradiction")
            if segments:
                latest_path = str(segments[-1].get("path", ""))
                latest_sha = str(segments[-1].get("sha256", ""))
                if latest_path not in text or latest_sha not in text:
                    failures.append("active_checkpoint_latest_segment_contradiction")
            segment_hashes = {
                str(entry.get("path")): str(entry.get("sha256"))
                for entry in segments
                if isinstance(entry, dict)
                and isinstance(entry.get("path"), str)
                and isinstance(entry.get("sha256"), str)
            }
            checkpoint_lines = text.splitlines()
            for line_index, line in enumerate(checkpoint_lines):
                marker = re.match(
                    r"^Latest (?:local |construction )?segment:\s*(?:`([^`]+)`|(\S+))",
                    line,
                )
                if marker is None:
                    continue
                path = marker.group(1) or marker.group(2)
                expected_sha = segment_hashes.get(path)
                if expected_sha is None:
                    if path.startswith("work/construction/segments/"):
                        failures.append(
                            f"active_checkpoint_segment_reference_unknown:{path}"
                        )
                    continue
                inline_sha = re.search(r"\b([0-9a-f]{64})\b", line)
                if inline_sha is None and line_index + 1 < len(checkpoint_lines):
                    next_line = checkpoint_lines[line_index + 1]
                    if next_line.startswith("Latest ") and "segment SHA-256:" in next_line:
                        inline_sha = re.search(
                            r"\b([0-9a-f]{64})\b", next_line
                        )
                if inline_sha is None or inline_sha.group(1) != expected_sha:
                    failures.append(
                        f"active_checkpoint_segment_reference_digest_mismatch:{path}"
                    )
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            failures.append(f"active_checkpoint_unreadable:{type(exc).__name__}:{exc}")

    return {
        "status": "construction_continuation_custody_ready" if not failures else "invalid",
        "failures": failures,
        "legacy_journal": {
            "path": legacy.get("path"),
            "bytes": legacy.get("bytes"),
            "git_blob_sha": legacy.get("git_blob_sha"),
            "sha256": legacy.get("sha256"),
        },
        "segments_verified": len(segments) if not failures else None,
        "active_checkpoint": checkpoint_path if isinstance(checkpoint_path, str) else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only verification of frozen construction continuation custody.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    result = verify_construction_continuation(args.repo_root)
    print(json.dumps(result, sort_keys=True) if args.summary else json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "construction_continuation_custody_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
