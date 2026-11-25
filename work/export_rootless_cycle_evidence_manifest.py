"""Write an answer-free digest inventory for one persisted rootless cycle.

The exporter reads a completed or failed cycle root without invoking inference
and writes a portable manifest outside that root. It records relative paths,
sizes, and SHA-256 digests, never file contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.local_model_authority import digest_payload  # noqa: E402

_MAX_FILES = 50_000
_MAX_FILE_BYTES = 128 * 1024 * 1024
_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
_CYCLE_ID = re.compile(r"rootless-cognition-cycle-[0-9a-f]{20}")


def _hash_regular_file(path: Path) -> tuple[str, int]:
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or path.is_symlink()
            or before.st_nlink != 1):
        raise ValueError("cycle_manifest_nonregular_file")
    if before.st_size > _MAX_FILE_BYTES:
        raise ValueError("cycle_manifest_file_over_bound")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino, opened.st_size) !=
                    (before.st_dev, before.st_ino, before.st_size)):
            raise ValueError("cycle_manifest_file_changed_before_read")
        hasher = hashlib.sha256()
        total = 0
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_FILE_BYTES:
                    raise ValueError("cycle_manifest_file_over_bound")
                hasher.update(chunk)
        after = os.fstat(descriptor)
        path_after = path.lstat()
        if ((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                or (opened.st_dev, opened.st_ino, opened.st_size) !=
                    (path_after.st_dev, path_after.st_ino, path_after.st_size)
                or not stat.S_ISREG(path_after.st_mode)
                or total != opened.st_size):
            raise ValueError("cycle_manifest_file_changed_during_read")
        return hasher.hexdigest(), total
    finally:
        os.close(descriptor)


def _cycle_identity(root: Path) -> tuple[str, str, Path]:
    if root.is_symlink():
        raise ValueError("cycle_manifest_root_symlink")
    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("cycle_manifest_root_not_directory")
    cycle_id = resolved.name
    if _CYCLE_ID.fullmatch(cycle_id) is None:
        raise ValueError("cycle_manifest_cycle_id_invalid")
    result_path = resolved / "cycle-result.json"
    failure_path = resolved / "cycle-failure.json"
    result_present = result_path.exists() or result_path.is_symlink()
    failure_present = failure_path.exists() or failure_path.is_symlink()
    if result_present and failure_present:
        raise ValueError("cycle_manifest_multiple_terminal_records")
    if result_path.is_file() and not result_path.is_symlink():
        cycle_path, status = result_path, "completed"
    elif failure_path.is_file() and not failure_path.is_symlink():
        cycle_path, status = failure_path, "incomplete"
    else:
        raise ValueError("cycle_manifest_terminal_record_missing")
    cycle_stat = cycle_path.lstat()
    if (not stat.S_ISREG(cycle_stat.st_mode) or cycle_stat.st_nlink != 1
            or cycle_stat.st_size > _MAX_FILE_BYTES):
        raise ValueError("cycle_manifest_terminal_record_over_bound")
    try:
        terminal = json.loads(cycle_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("cycle_manifest_terminal_record_invalid") from exc
    if (not isinstance(terminal, dict)
            or terminal.get("run_id") != cycle_id
            or (status == "completed" and terminal.get("status") != "completed")
            or (status == "incomplete" and terminal.get("status") != "incomplete")):
        raise ValueError("cycle_manifest_terminal_record_binding_invalid")
    return cycle_id, status, cycle_path


def create_manifest(*, cycle_root: Path, output_path: Path) -> dict[str, Any]:
    if cycle_root.is_symlink():
        raise ValueError("cycle_manifest_root_symlink")
    root = cycle_root.resolve(strict=True)
    output = output_path.resolve(strict=False)
    try:
        output.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("cycle_manifest_output_inside_source_root")
    cycle_id, cycle_status, _ = _cycle_identity(root)
    files: list[dict[str, Any]] = []
    total_bytes = 0
    for current, directories, names in os.walk(root, topdown=True,
            followlinks=False):
        current_path = Path(current)
        directories.sort()
        names.sort()
        for directory in directories:
            path = current_path / directory
            if path.is_symlink() or not path.is_dir():
                raise ValueError("cycle_manifest_directory_link_or_type_invalid")
        for name in names:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if len(files) >= _MAX_FILES:
                raise ValueError("cycle_manifest_file_count_over_bound")
            file_digest, size = _hash_regular_file(path)
            total_bytes += size
            if total_bytes > _MAX_TOTAL_BYTES:
                raise ValueError("cycle_manifest_total_size_over_bound")
            files.append({"path": relative, "size_bytes": size,
                "sha256": file_digest})
    if not files:
        raise ValueError("cycle_manifest_empty_source_root")
    files.sort(key=lambda item: item["path"])
    semantic = {
        "schema_version": "sentientos.rootless_cycle_evidence_manifest:v1",
        "cycle_id": cycle_id,
        "cycle_status": cycle_status,
        "file_count": len(files),
        "total_size_bytes": total_bytes,
        "files": files,
        "file_contents_included": False,
        "atomic_snapshot": False,
        "independent_signature": False,
        "inference_performed": False,
        "authority": False,
    }
    return {**semantic, "manifest_digest": digest_payload(semantic)}


def persist_manifest(value: dict[str, Any], output_path: Path) -> None:
    if not output_path.parent.is_dir():
        raise ValueError("cycle_manifest_output_parent_missing")
    parent = output_path.parent.resolve(strict=True)
    if output_path.parent.absolute() != parent:
        raise ValueError("cycle_manifest_output_parent_symlink")
    body = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".rootless-cycle-manifest-", dir=parent)
    temporary_path = Path(temporary_name)
    try:
        os.chmod(temporary_path, 0o600)
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = -1
        with handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        # Hard-link publication is atomic and refuses to replace an existing
        # target, preserving immutable manifest naming under concurrent runs.
        os.link(temporary_path, output_path)
        temporary_path.unlink()
        if os.name != "nt":
            directory_descriptor = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    except Exception:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def verify_manifest(*, cycle_root: Path, manifest_path: Path) -> dict[str, Any]:
    if (manifest_path.is_symlink() or not manifest_path.is_file()
            or manifest_path.stat().st_size > 64 * 1024 * 1024):
        raise ValueError("cycle_manifest_verification_input_invalid")
    try:
        stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("cycle_manifest_verification_input_invalid") from exc
    if not isinstance(stored, dict):
        raise ValueError("cycle_manifest_verification_input_invalid")
    expected = create_manifest(cycle_root=cycle_root,
        output_path=manifest_path)
    if stored != expected:
        raise ValueError("cycle_manifest_source_mismatch")
    return stored


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-existing", action="store_true",
        help="verify an existing manifest against the source cycle root")
    args = parser.parse_args()
    manifest = (verify_manifest(cycle_root=args.cycle_root,
        manifest_path=args.output) if args.verify_existing else
        create_manifest(cycle_root=args.cycle_root, output_path=args.output))
    if not args.verify_existing:
        persist_manifest(manifest, args.output)
    print(json.dumps({"manifest": str(args.output),
        "operation": "verified" if args.verify_existing else "created",
        "manifest_digest": manifest["manifest_digest"],
        "cycle_id": manifest["cycle_id"],
        "cycle_status": manifest["cycle_status"],
        "file_count": manifest["file_count"],
        "total_size_bytes": manifest["total_size_bytes"],
        "file_contents_included": False,
        "inference_performed": False,
        "authority": False}, sort_keys=True))


if __name__ == "__main__":
    main()
