"""Installation-bound runtime handoff for the supervised production chat process.

The runtime launcher publishes the process instance and an exact digest of the
SentientOS Python source bundle it launched. The child checks that handoff against
its own PID, parent PID, argv, cwd, environment and still-present source bundle
before inference. This is local launcher evidence, not a hardware attestation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .installation_state import (
    InstallationIdentity, InstallationStateError, InstallationStateHandle, InstallationStateRegistry,
)

SCHEMA = "sentientos.chat_process_generation_handoff:v1"
RELATIVE_ROOT = "local-model/chat/runtime-handoffs"
HANDOFF_ID = re.compile(r"^[0-9a-f]{32}$")
MAX_HANDOFF_BYTES = 1_048_576
MAX_HANDOFF_ENTRIES = 256
MAX_SOURCE_FILES = 2_048
MAX_SOURCE_DIRECTORIES = 8_192
MAX_SOURCE_FILE_BYTES = 2_097_152
MAX_SOURCE_TOTAL_BYTES = 67_108_864


class ChatProcessGenerationError(ValueError):
    """Invalid, incomplete or stale supervised chat-process lineage."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    except (TypeError, ValueError, RecursionError) as exc:
        raise ChatProcessGenerationError("chat_process_handoff_noncanonical_value") from exc


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_source(path: Path) -> bytes:
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                             | getattr(os, "O_NONBLOCK", 0))
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SOURCE_FILE_BYTES:
            raise ChatProcessGenerationError("chat_source_member_invalid")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65_536, MAX_SOURCE_FILE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_SOURCE_FILE_BYTES:
                raise ChatProcessGenerationError("chat_source_member_too_large")
        after = os.fstat(descriptor)
        raw = b"".join(chunks)
        if (len(raw) != before.st_size or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns
                or after.st_dev != before.st_dev or after.st_ino != before.st_ino):
            raise ChatProcessGenerationError("chat_source_member_changed")
        return raw
    except ChatProcessGenerationError:
        raise
    except OSError as exc:
        raise ChatProcessGenerationError("chat_source_member_unavailable") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def source_generation(repository_root: str | Path) -> tuple[str, tuple[dict[str, Any], ...]]:
    """Measure bounded source bytes for the installed chat script and SentientOS package."""
    root = Path(repository_root)
    if not root.is_absolute() or root.resolve() != root or root.is_symlink():
        raise ChatProcessGenerationError("chat_source_root_invalid")
    source_directories = (root / "sentientos", root / "scripts")
    if any(path.is_symlink() or not path.is_dir() for path in source_directories):
        raise ChatProcessGenerationError("chat_source_root_incomplete")
    candidates: list[Path] = []
    directory_count = 0
    for source_directory in source_directories:
        for current, directories, filenames in os.walk(source_directory, followlinks=False):
            directory_count += 1
            if directory_count > MAX_SOURCE_DIRECTORIES:
                raise ChatProcessGenerationError("chat_source_directory_bound_exceeded")
            base = Path(current)
            if base.is_symlink():
                raise ChatProcessGenerationError("chat_source_directory_symlink")
            for directory in directories:
                if (base / directory).is_symlink():
                    raise ChatProcessGenerationError("chat_source_directory_symlink")
            for filename in filenames:
                path = base / filename
                if path.suffix == ".py":
                    if path.is_symlink():
                        raise ChatProcessGenerationError("chat_source_member_symlink")
                    candidates.append(path)
                    if len(candidates) > MAX_SOURCE_FILES:
                        raise ChatProcessGenerationError("chat_source_file_bound_exceeded")
    members: list[dict[str, Any]] = []
    total = 0
    for path in sorted(candidates, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        raw = _read_source(path)
        total += len(raw)
        if total > MAX_SOURCE_TOTAL_BYTES:
            raise ChatProcessGenerationError("chat_source_total_bound_exceeded")
        members.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest(),
                        "size_bytes": len(raw)})
    manifest_digest = _digest(members)
    return "sha256:" + manifest_digest, tuple(members)


def _process_instance_id(*, handoff_id: str, pid: int, parent_pid: int,
                         argv_digest: str, startup_timestamp: str) -> str:
    return "sha256:" + _digest({"handoff_id": handoff_id, "pid": pid, "parent_pid": parent_pid,
        "argv_digest": argv_digest, "startup_timestamp": startup_timestamp})


def _handoff_path(handle: InstallationStateHandle, handoff_id: str):
    if not HANDOFF_ID.fullmatch(handoff_id):
        raise ChatProcessGenerationError("chat_process_handoff_id_invalid")
    return handle.fixed_object(f"{RELATIVE_ROOT}/{handoff_id}.json")


def _read_handoff(handle: InstallationStateHandle, handoff_id: str) -> dict[str, Any]:
    try:
        raw = handle.read_regular_bounded(_handoff_path(handle, handoff_id), max_bytes=MAX_HANDOFF_BYTES)
        value = json.loads(raw.decode("utf-8"))
    except ChatProcessGenerationError:
        raise
    except Exception as exc:
        raise ChatProcessGenerationError("chat_process_handoff_unavailable") from exc
    expected_fields = {"schema_version", "handoff_id", "installation_identity", "issuer",
        "source_root", "software_generation_digest", "source_members", "process_id",
        "parent_process_id", "startup_timestamp", "python_executable", "argv_digest",
        "working_directory", "environment_digest", "process_instance_id", "handoff_digest"}
    if (not isinstance(value, dict) or set(value) != expected_fields
            or value.get("schema_version") != SCHEMA or value.get("handoff_id") != handoff_id):
        raise ChatProcessGenerationError("chat_process_handoff_shape_invalid")
    if raw != _canonical(value):
        raise ChatProcessGenerationError("chat_process_handoff_noncanonical")
    semantic = {key: item for key, item in value.items() if key != "handoff_digest"}
    if value.get("handoff_digest") != _digest(semantic):
        raise ChatProcessGenerationError("chat_process_handoff_digest_mismatch")
    if value.get("installation_identity") != handle.identity.value or value.get("issuer") != "LocalModelChatServiceAdapter":
        raise ChatProcessGenerationError("chat_process_handoff_installation_mismatch")
    members = value.get("source_members")
    if (not isinstance(members, list) or not members or len(members) > MAX_SOURCE_FILES
            or any(not isinstance(item, dict) or set(item) != {"path", "sha256", "size_bytes"}
                   or not isinstance(item.get("path"), str)
                   or not item["path"].startswith(("sentientos/", "scripts/"))
                   or item["path"].startswith("/")
                   or any(part in {"", ".", ".."} for part in item["path"].split("/"))
                   or not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64
                   or any(character not in "0123456789abcdef" for character in item["sha256"])
                   or type(item.get("size_bytes")) is not int
                   or not 0 <= item["size_bytes"] <= MAX_SOURCE_FILE_BYTES
                   for item in members)
            or len({item["path"] for item in members}) != len(members)
            or sum(item["size_bytes"] for item in members) > MAX_SOURCE_TOTAL_BYTES
            or members != sorted(members, key=lambda item: item["path"])
            or value.get("software_generation_digest") != "sha256:" + _digest(members)):
        raise ChatProcessGenerationError("chat_process_handoff_source_manifest_invalid")
    if (type(value.get("process_id")) is not int or value["process_id"] < 1
            or type(value.get("parent_process_id")) is not int or value["parent_process_id"] < 1
            or not isinstance(value.get("python_executable"), str)
            or not isinstance(value.get("working_directory"), str)
            or not isinstance(value.get("argv_digest"), str)
            or not isinstance(value.get("environment_digest"), str)
            or value.get("process_instance_id") != _process_instance_id(
                handoff_id=handoff_id, pid=value["process_id"], parent_pid=value["parent_process_id"],
                argv_digest=value["argv_digest"], startup_timestamp=value.get("startup_timestamp", ""))):
        raise ChatProcessGenerationError("chat_process_handoff_process_binding_invalid")
    try:
        timestamp = datetime.fromisoformat(str(value["startup_timestamp"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ChatProcessGenerationError("chat_process_handoff_time_invalid") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ChatProcessGenerationError("chat_process_handoff_time_invalid")
    return value


def publish_chat_process_handoff(*, handle: InstallationStateHandle, handoff_id: str,
                                 argv: Sequence[str], environment: Mapping[str, str],
                                 working_directory: str | Path, process_id: int,
                                 parent_process_id: int, startup_timestamp: str,
                                 python_executable: str, repository_root: str | Path) -> dict[str, Any]:
    """Publish immutable launch evidence from the actual child-owning runtime adapter."""
    if type(handle) is not InstallationStateHandle:
        raise ChatProcessGenerationError("authenticated_installation_handle_required")
    if os.name != "posix":
        raise ChatProcessGenerationError("chat_process_handoff_publication_unsupported_platform")
    if not HANDOFF_ID.fullmatch(handoff_id) or not argv or any(not isinstance(item, str) or not item for item in argv):
        raise ChatProcessGenerationError("chat_process_launch_identity_invalid")
    root = Path(repository_root)
    generation_digest, members = source_generation(root)
    argv_digest = _digest(list(argv))
    record: dict[str, Any] = {"schema_version": SCHEMA, "handoff_id": handoff_id,
        "installation_identity": handle.identity.value, "issuer": "LocalModelChatServiceAdapter",
        "source_root": str(root), "software_generation_digest": generation_digest,
        "source_members": list(members), "process_id": process_id, "parent_process_id": parent_process_id,
        "startup_timestamp": startup_timestamp, "python_executable": os.path.realpath(python_executable),
        "argv_digest": argv_digest, "working_directory": str(Path(working_directory).resolve()),
        "environment_digest": _digest(dict(environment))}
    record["process_instance_id"] = _process_instance_id(handoff_id=handoff_id,
        pid=process_id, parent_pid=parent_process_id, argv_digest=argv_digest,
        startup_timestamp=startup_timestamp)
    record["handoff_digest"] = _digest(record)
    target = _handoff_path(handle, handoff_id)
    directory = handle.fixed_object(RELATIVE_ROOT)
    handle.ensure_directory(directory)
    try:
        existing_names = handle.list_regular_names(directory, max_entries=MAX_HANDOFF_ENTRIES)
    except InstallationStateError as exc:
        reason = ("chat_process_handoff_retention_limit_exceeded"
            if str(exc) == "state_directory_entry_bound_exceeded"
            else "chat_process_handoff_directory_invalid")
        raise ChatProcessGenerationError(reason) from exc
    if len(existing_names) >= MAX_HANDOFF_ENTRIES:
        raise ChatProcessGenerationError("chat_process_handoff_retention_limit_exceeded")
    if f"{handoff_id}.json" in existing_names:
        raise ChatProcessGenerationError("chat_process_handoff_identity_collision")
    raw = _canonical(record)
    if len(raw) > MAX_HANDOFF_BYTES:
        raise ChatProcessGenerationError("chat_process_handoff_too_large")
    def verify_published(observed: bytes) -> None:
        if observed != raw:
            raise ChatProcessGenerationError("chat_process_handoff_publication_mismatch")
    try:
        handle.durable_create(target, raw, verify=verify_published)
    except Exception as exc:
        if isinstance(exc, ChatProcessGenerationError):
            raise
        raise ChatProcessGenerationError("chat_process_handoff_publication_failed") from exc
    return record


def verify_current_chat_process_handoff(*, handle: InstallationStateHandle,
                                         handoff_id: str) -> dict[str, Any]:
    """Check this child process against the parent's immutable launch record."""
    record = _read_handoff(handle, handoff_id)
    argv = [sys.executable, *sys.argv]
    if (os.getpid() != record["process_id"] or os.getppid() != record["parent_process_id"]
            or os.path.realpath(sys.executable) != record["python_executable"]
            or str(Path.cwd().resolve()) != record["working_directory"]
            or _digest(argv) != record["argv_digest"]
            or _digest(dict(os.environ)) != record["environment_digest"]):
        raise ChatProcessGenerationError("chat_process_instance_changed")
    generation_digest, _members = source_generation(record["source_root"])
    if generation_digest != record["software_generation_digest"]:
        raise ChatProcessGenerationError("chat_process_source_generation_changed")
    return {"status": "runtime_launcher_process_and_source_bound",
        "handoff_id": handoff_id, "handoff_digest": record["handoff_digest"],
        "process_instance_id": record["process_instance_id"],
        "software_generation_digest": record["software_generation_digest"],
        "process_id": record["process_id"], "parent_process_id": record["parent_process_id"],
        "startup_timestamp": record["startup_timestamp"],
        "source_generation_scope": "sentientos_and_scripts_python_sources"}



def verify_supervised_chat_process_handoff(*, handle: InstallationStateHandle, handoff_id: str,
        process_id: int, parent_process_id: int, argv: Sequence[str],
        environment: Mapping[str, str], working_directory: str | Path,
        python_executable: str | Path, repository_root: str | Path) -> dict[str, Any]:
    """Verify the launcher-owned record against the exact child Popen arguments.

    This is deliberately distinct from verify_current_chat_process_handoff:
    only the child can compare its own PID, parent, argv and environment to itself.
    A parent may verify its immutable launch record and source bytes, while its
    Popen.poll() check supplies the separate process-liveness observation.
    """
    record = _read_handoff(handle, handoff_id)
    expected = {
        "process_id": process_id,
        "parent_process_id": parent_process_id,
        "argv_digest": _digest(list(argv)),
        "environment_digest": _digest(dict(environment)),
        "working_directory": str(Path(working_directory).resolve()),
        "python_executable": os.path.realpath(str(python_executable)),
        "source_root": str(Path(repository_root)),
    }
    if any(record.get(key) != value for key, value in expected.items()):
        raise ChatProcessGenerationError("chat_process_launcher_record_mismatch")
    generation_digest, _members = source_generation(record["source_root"])
    if generation_digest != record["software_generation_digest"]:
        raise ChatProcessGenerationError("chat_process_source_generation_changed")
    return {"status": "runtime_launcher_child_launch_and_source_bound",
        "handoff_id": handoff_id, "handoff_digest": record["handoff_digest"],
        "process_instance_id": record["process_instance_id"],
        "software_generation_digest": record["software_generation_digest"],
        "process_id": record["process_id"], "parent_process_id": record["parent_process_id"],
        "startup_timestamp": record["startup_timestamp"],
        "source_generation_scope": "sentientos_and_scripts_python_sources"}


def verify_stored_chat_process_handoff(*, handle: InstallationStateHandle,
                                       handoff_id: str, expected_digest: str) -> dict[str, Any]:
    """Verify historical owner custody without asserting the old process still runs."""
    record = _read_handoff(handle, handoff_id)
    if record["handoff_digest"] != expected_digest:
        raise ChatProcessGenerationError("chat_process_handoff_identity_mismatch")
    return {"status": "runtime_launcher_process_and_source_bound",
        "handoff_id": handoff_id, "handoff_digest": record["handoff_digest"],
        "process_instance_id": record["process_instance_id"],
        "software_generation_digest": record["software_generation_digest"],
        "process_id": record["process_id"], "parent_process_id": record["parent_process_id"],
        "startup_timestamp": record["startup_timestamp"],
        "source_generation_scope": "sentientos_and_scripts_python_sources"}


def open_chat_process_handoff(*, installation_identity: str, handoff_id: str,
                              wait_seconds: float = 5.0) -> tuple[InstallationStateHandle, dict[str, Any]]:
    """Open an exact handoff, allowing the parent a short publication window after spawn."""
    import time
    identity = InstallationIdentity.parse(installation_identity)
    handle = InstallationStateRegistry.system().open(identity)
    deadline = time.monotonic() + max(0.0, min(float(wait_seconds), 5.0))
    while True:
        try:
            return handle, verify_current_chat_process_handoff(handle=handle, handoff_id=handoff_id)
        except ChatProcessGenerationError as exc:
            if str(exc) != "chat_process_handoff_unavailable" or time.monotonic() >= deadline:
                raise
            time.sleep(0.01)
