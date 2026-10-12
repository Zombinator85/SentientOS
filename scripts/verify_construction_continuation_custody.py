from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path, PurePosixPath
from typing import Any

MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_CHECKPOINT_BYTES = 64 * 1024
MAX_LEGACY_BYTES = 2 * 1024 * 1024
MAX_SEGMENT_BYTES = 64 * 1024
MAX_SEGMENTS = 4096


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
    failures: list[str] = []
    index_path = "work/construction/index.json"
    try:
        index_bytes = _read_regular(root, index_path, limit=MAX_INDEX_BYTES)
        index = json.loads(index_bytes)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "failures": [f"index_unreadable:{type(exc).__name__}:{exc}"]}
    if not isinstance(index, dict) or index.get("schema_version") != 1:
        return {"status": "invalid", "failures": ["index_schema_invalid"]}

    legacy = index.get("legacy_journal")
    if not isinstance(legacy, dict) or legacy.get("frozen") is not True:
        failures.append("legacy_journal_not_declared_frozen")
        legacy = {}
    try:
        legacy_bytes = _read_regular(root, str(legacy["path"]), limit=MAX_LEGACY_BYTES)
        actual_sha256 = hashlib.sha256(legacy_bytes).hexdigest()
        actual_blob = _git_blob_sha(legacy_bytes)
        if len(legacy_bytes) != legacy.get("bytes"):
            failures.append("legacy_journal_byte_count_mismatch")
        if actual_sha256 != legacy.get("sha256"):
            failures.append("legacy_journal_sha256_mismatch")
        if actual_blob != legacy.get("git_blob_sha"):
            failures.append("legacy_journal_git_blob_mismatch")
    except (OSError, KeyError, ValueError) as exc:
        failures.append(f"legacy_journal_unreadable:{type(exc).__name__}:{exc}")

    segments = index.get("segments")
    if not isinstance(segments, list) or len(segments) > MAX_SEGMENTS:
        failures.append("segments_invalid_or_unbounded")
        segments = []
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
        if entry.get("sequence") != expected_sequence:
            failures.append(f"segment_{expected_sequence}_sequence_mismatch")
        expected_predecessor = (
            f"legacy-blob:{previous_sha}"
            if expected_sequence == 1
            else f"segment-sha256:{previous_sha}"
        )
        if entry.get("predecessor") != expected_predecessor:
            failures.append(f"segment_{expected_sequence}_predecessor_mismatch")
        try:
            content = _read_regular(root, path, limit=MAX_SEGMENT_BYTES)
            digest = hashlib.sha256(content).hexdigest()
            if len(content) != entry.get("bytes"):
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
            checkpoint = _read_regular(root, checkpoint_path, limit=MAX_CHECKPOINT_BYTES)
            text = checkpoint.decode("utf-8")
            checkpoint_digest = hashlib.sha256(checkpoint).hexdigest()
            if binding.get("checkpoint_sha256") != checkpoint_digest:
                failures.append("active_checkpoint_sha256_mismatch")
            if binding.get("latest_segment_sequence") != len(segments):
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
