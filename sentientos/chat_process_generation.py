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

from .local_runtime_provisioning import semantic_digest
from .installation_state import (
    InstallationIdentity, InstallationStateError, InstallationStateHandle,
    InstallationStateReadOnlyView, WindowsInstallationStateReadOnlyView,
    InstallationStateRegistry,
)

SCHEMA = "sentientos.chat_process_generation_handoff:v3"
V2_SCHEMA = "sentientos.chat_process_generation_handoff:v2"
LEGACY_SCHEMA = "sentientos.chat_process_generation_handoff:v1"
RELATIVE_ROOT = "local-model/chat/runtime-handoffs"
HANDOFF_ID = re.compile(r"^[0-9a-f]{32}$")
MAX_HANDOFF_BYTES = 1_048_576
MAX_PRIOR_SNAPSHOT_BYTES = 65_536
MAX_HANDOFF_ENTRIES = 256
MAX_LAUNCH_ARGUMENTS = 128
MAX_LAUNCH_ARGUMENT_BYTES = 4096
MAX_LAUNCH_ARGUMENT_TOTAL_BYTES = 32_768
RUNTIME_OBSERVATION_SCHEMA = "sentientos.chat_process_runtime_observation:v3"
V2_RUNTIME_OBSERVATION_SCHEMA = "sentientos.chat_process_runtime_observation:v2"
LEGACY_RUNTIME_OBSERVATION_SCHEMA = "sentientos.chat_process_runtime_observation:v1"
RUNTIME_OBSERVATION_PATH = "local-model/chat/runtime-observations/current.json"
RUNTIME_OBSERVATION_LOCK = "local-model/chat/runtime-observations/owner.lock"
MAX_RUNTIME_OBSERVATION_BYTES = 65_536
MIN_RUNTIME_OBSERVATION_REFRESH_SECONDS = 30
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
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
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


def _read_source_at(parent_fd: int, name: str) -> bytes:
    if (not name or name in {".", ".."} or "/" in name or "\\" in name
            or not hasattr(os, "O_NOFOLLOW")):
        raise ChatProcessGenerationError("chat_source_member_invalid")
    descriptor: int | None = None
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW
            | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd)
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


def _source_generation_posix(root: Path) -> tuple[str, tuple[dict[str, Any], ...]]:
    root_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        root_fd = os.open(root, root_flags)
    except OSError as exc:
        raise ChatProcessGenerationError("chat_source_root_unavailable") from exc
    members: list[dict[str, Any]] = []
    total = 0
    directory_count = 0
    candidate_count = 0
    try:
        root_before = os.fstat(root_fd)
        if not stat.S_ISDIR(root_before.st_mode):
            raise ChatProcessGenerationError("chat_source_root_invalid")
        for source_name in ("sentientos", "scripts"):
            try:
                source_fd = os.open(source_name,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
                    | getattr(os, "O_CLOEXEC", 0), dir_fd=root_fd)
            except OSError as exc:
                raise ChatProcessGenerationError("chat_source_root_incomplete") from exc
            try:
                if not stat.S_ISDIR(os.fstat(source_fd).st_mode):
                    raise ChatProcessGenerationError("chat_source_root_incomplete")
                for current, directories, filenames, directory_fd in os.fwalk(
                        ".", topdown=True, follow_symlinks=False, dir_fd=source_fd):
                    directory_count += 1
                    if directory_count > MAX_SOURCE_DIRECTORIES:
                        raise ChatProcessGenerationError("chat_source_directory_bound_exceeded")
                    directories.sort()
                    for dirname in directories:
                        try:
                            entry = os.stat(dirname, dir_fd=directory_fd, follow_symlinks=False)
                        except OSError as exc:
                            raise ChatProcessGenerationError("chat_source_directory_invalid") from exc
                        if not stat.S_ISDIR(entry.st_mode):
                            raise ChatProcessGenerationError("chat_source_directory_symlink")
                    parts = tuple(part for part in Path(current).parts if part not in {"", "."})
                    for filename in sorted(name for name in filenames if name.endswith(".py")):
                        candidate_count += 1
                        if candidate_count > MAX_SOURCE_FILES:
                            raise ChatProcessGenerationError("chat_source_file_bound_exceeded")
                        raw = _read_source_at(directory_fd, filename)
                        total += len(raw)
                        if total > MAX_SOURCE_TOTAL_BYTES:
                            raise ChatProcessGenerationError("chat_source_total_bound_exceeded")
                        relative = Path(source_name, *parts, filename).as_posix()
                        members.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest(),
                                        "size_bytes": len(raw)})
            finally:
                os.close(source_fd)
        try:
            root_after_path = os.stat(root, follow_symlinks=False)
        except OSError as exc:
            raise ChatProcessGenerationError("chat_source_root_changed") from exc
        root_after = os.fstat(root_fd)
        if (not stat.S_ISDIR(root_after_path.st_mode)
                or (root_after_path.st_dev, root_after_path.st_ino) != (root_before.st_dev, root_before.st_ino)
                or (root_after.st_dev, root_after.st_ino) != (root_before.st_dev, root_before.st_ino)):
            raise ChatProcessGenerationError("chat_source_root_changed")
    finally:
        os.close(root_fd)
    members.sort(key=lambda item: str(item["path"]))
    manifest_digest = _digest(members)
    return "sha256:" + manifest_digest, tuple(members)


def source_generation(repository_root: str | Path) -> tuple[str, tuple[dict[str, Any], ...]]:
    """Measure bounded source bytes for the installed chat script and SentientOS package."""
    root = Path(repository_root)
    if not root.is_absolute() or root.resolve() != root or root.is_symlink():
        raise ChatProcessGenerationError("chat_source_root_invalid")
    if os.name == "posix":
        return _source_generation_posix(root)
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


def _handoff_path(handle: Any, handoff_id: str) -> Any:
    if not HANDOFF_ID.fullmatch(handoff_id):
        raise ChatProcessGenerationError("chat_process_handoff_id_invalid")
    relative = f"{RELATIVE_ROOT}/{handoff_id}.json"
    if isinstance(handle, (InstallationStateReadOnlyView, WindowsInstallationStateReadOnlyView)):
        return relative
    return handle.fixed_object(relative)


def _read_handoff_bytes(handle: Any, path: Any) -> bytes:
    if isinstance(handle, (InstallationStateReadOnlyView, WindowsInstallationStateReadOnlyView)):
        return handle.read_regular_bounded(path, max_bytes=MAX_HANDOFF_BYTES)
    return handle.read_regular_bounded(path, max_bytes=MAX_HANDOFF_BYTES)


def _configured_serving_operation(argv: Sequence[str]) -> str | None:
    positions = [index for index, argument in enumerate(argv)
        if argument == "--serving-operation-id"]
    if len(positions) != 1 or positions[0] + 1 >= len(argv):
        return None
    value = argv[positions[0] + 1]
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value) > 128 or any(character in value for character in "*?[]{}")):
        return None
    return value


def _read_handoff(handle: Any, handoff_id: str, *,
                  verify_predecessor: bool = True) -> dict[str, Any]:
    try:
        raw = _read_handoff_bytes(handle, _handoff_path(handle, handoff_id))
        value = json.loads(raw.decode("utf-8"))
    except ChatProcessGenerationError:
        raise
    except Exception as exc:
        raise ChatProcessGenerationError("chat_process_handoff_unavailable") from exc
    base_fields = {"schema_version", "handoff_id", "installation_identity", "issuer",
        "source_root", "software_generation_digest", "source_members", "process_id",
        "parent_process_id", "startup_timestamp", "python_executable", "argv_digest",
        "working_directory", "environment_digest", "process_instance_id", "handoff_digest"}
    lineage_fields = {"prior_snapshot_handoff", "prior_snapshot_digest",
        "prior_snapshot_supervisor_generation", "prior_startup_snapshot",
        "predecessor_relation", "prior_process_overlap_status"}
    if not isinstance(value, dict) or value.get("handoff_id") != handoff_id:
        raise ChatProcessGenerationError("chat_process_handoff_shape_invalid")
    if value.get("schema_version") == LEGACY_SCHEMA:
        expected_fields = base_fields
    elif value.get("schema_version") == V2_SCHEMA:
        expected_fields = base_fields | lineage_fields
    elif value.get("schema_version") == SCHEMA:
        expected_fields = base_fields | lineage_fields | {
            "launch_argv", "configured_serving_operation_id"}
    else:
        raise ChatProcessGenerationError("chat_process_handoff_shape_invalid")
    if set(value) != expected_fields:
        raise ChatProcessGenerationError("chat_process_handoff_shape_invalid")
    if raw != _canonical(value):
        raise ChatProcessGenerationError("chat_process_handoff_noncanonical")
    semantic = {key: item for key, item in value.items() if key != "handoff_digest"}
    if value.get("handoff_digest") != _digest(semantic):
        raise ChatProcessGenerationError("chat_process_handoff_digest_mismatch")
    if value.get("installation_identity") != handle.identity.value or value.get("issuer") != "LocalModelChatServiceAdapter":
        raise ChatProcessGenerationError("chat_process_handoff_installation_mismatch")
    if value.get("schema_version") in {V2_SCHEMA, SCHEMA}:
        prior = value.get("prior_snapshot_handoff")
        snapshot_digest = value.get("prior_snapshot_digest")
        prior_supervisor = value.get("prior_snapshot_supervisor_generation")
        prior_snapshot = value.get("prior_startup_snapshot")
        relation = value.get("predecessor_relation")
        if prior is None:
            if (snapshot_digest is not None or prior_supervisor is not None
                    or prior_snapshot is not None
                    or relation != "prior_snapshot_handoff_unavailable"
                    or value.get("prior_process_overlap_status") != "unknown"):
                raise ChatProcessGenerationError("chat_process_handoff_predecessor_invalid")
        elif (not isinstance(prior, dict)
                or not isinstance(snapshot_digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", snapshot_digest)
                or not isinstance(prior_supervisor, str) or not prior_supervisor
                or not isinstance(prior_snapshot, dict)
                or len(_canonical(prior_snapshot)) > MAX_PRIOR_SNAPSHOT_BYTES
                or prior_snapshot.get("installation_identity") != handle.identity.value
                or prior_snapshot.get("snapshot_semantic_digest") != snapshot_digest
                or semantic_digest({key: item for key, item in prior_snapshot.items()
                    if key != "snapshot_semantic_digest"}) != snapshot_digest
                or prior_snapshot.get("runtime_supervisor_generation") != prior_supervisor
                or not isinstance(prior_snapshot.get("chat_process_handoff"), dict)
                or prior_snapshot["chat_process_handoff"] != prior
                or relation != "prior_snapshot_reference_not_direct"
                or value.get("prior_process_overlap_status") != "unknown"):
            raise ChatProcessGenerationError("chat_process_handoff_predecessor_invalid")
        else:
            if prior["handoff_id"] == handoff_id:
                raise ChatProcessGenerationError("chat_process_handoff_predecessor_cycle")
            if verify_predecessor:
                predecessor_record = _read_handoff(handle, str(prior["handoff_id"]),
                    verify_predecessor=False)
                if prior["handoff_digest"] != predecessor_record["handoff_digest"]:
                    raise ChatProcessGenerationError("chat_process_handoff_predecessor_digest_mismatch")
                if prior.get("status") != "runtime_launcher_child_launch_and_source_bound":
                    raise ChatProcessGenerationError("chat_process_handoff_predecessor_status_invalid")
                expected_prior_summary = _handoff_summary(
                    predecessor_record, "runtime_launcher_child_launch_and_source_bound")
                if prior != expected_prior_summary:
                    raise ChatProcessGenerationError("chat_process_handoff_predecessor_identity_mismatch")
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
    if value.get("schema_version") == SCHEMA:
        launch_argv = value.get("launch_argv")
        if (not isinstance(launch_argv, list) or not launch_argv
                or len(launch_argv) > MAX_LAUNCH_ARGUMENTS
                or any(not isinstance(argument, str) or not argument
                    or len(argument.encode("utf-8")) > MAX_LAUNCH_ARGUMENT_BYTES
                    for argument in launch_argv)
                or len(_canonical(launch_argv)) > MAX_LAUNCH_ARGUMENT_TOTAL_BYTES
                or _digest(launch_argv) != value.get("argv_digest")
                or _configured_serving_operation(launch_argv)
                    != value.get("configured_serving_operation_id")):
            raise ChatProcessGenerationError("chat_process_handoff_launch_arguments_invalid")
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
                                 python_executable: str, repository_root: str | Path,
                                 prior_startup_snapshot: Mapping[str, Any] | None = None,
                                 source_snapshot: tuple[str, Sequence[Mapping[str, Any]]] | None = None) -> dict[str, Any]:
    """Publish immutable launch evidence from the actual child-owning runtime adapter."""
    if type(handle) is not InstallationStateHandle:
        raise ChatProcessGenerationError("authenticated_installation_handle_required")
    if os.name != "posix":
        raise ChatProcessGenerationError("chat_process_handoff_publication_unsupported_platform")
    if not HANDOFF_ID.fullmatch(handoff_id) or not argv or any(not isinstance(item, str) or not item for item in argv):
        raise ChatProcessGenerationError("chat_process_launch_identity_invalid")
    root = Path(repository_root)
    current_generation_digest, current_members = source_generation(root)
    if source_snapshot is None:
        generation_digest, members = current_generation_digest, current_members
    else:
        generation_digest, source_members = source_snapshot
        members = tuple(dict(item) for item in source_members)
        if (generation_digest != current_generation_digest
                or members != current_members):
            raise ChatProcessGenerationError("chat_process_source_changed_during_launch")
    argv_digest = _digest(list(argv))
    configured_operation = _configured_serving_operation(argv)
    launch_arguments = list(argv)
    if (configured_operation is None or len(launch_arguments) > MAX_LAUNCH_ARGUMENTS
            or any(len(argument.encode("utf-8")) > MAX_LAUNCH_ARGUMENT_BYTES
                for argument in launch_arguments)
            or len(_canonical(launch_arguments)) > MAX_LAUNCH_ARGUMENT_TOTAL_BYTES):
        raise ChatProcessGenerationError("chat_process_launch_arguments_unbounded_or_unbound")
    record: dict[str, Any] = {"schema_version": SCHEMA, "handoff_id": handoff_id,
        "installation_identity": handle.identity.value, "issuer": "LocalModelChatServiceAdapter",
        "source_root": str(root), "software_generation_digest": generation_digest,
        "launch_argv": launch_arguments,
        "configured_serving_operation_id": configured_operation,
        "source_members": list(members), "process_id": process_id, "parent_process_id": parent_process_id,
        "startup_timestamp": startup_timestamp, "python_executable": os.path.realpath(python_executable),
        "argv_digest": argv_digest, "working_directory": str(Path(working_directory).resolve()),
        "environment_digest": _digest(dict(environment)),
        "prior_snapshot_handoff": None, "prior_snapshot_digest": None,
        "prior_snapshot_supervisor_generation": None, "prior_startup_snapshot": None,
        "predecessor_relation": "prior_snapshot_handoff_unavailable",
        "prior_process_overlap_status": "unknown"}
    if prior_startup_snapshot is not None:
        if (not isinstance(prior_startup_snapshot, Mapping)
                or len(_canonical(prior_startup_snapshot)) > MAX_PRIOR_SNAPSHOT_BYTES):
            raise ChatProcessGenerationError("chat_process_predecessor_snapshot_invalid")
        snapshot = dict(prior_startup_snapshot)
        snapshot_digest = snapshot.get("snapshot_semantic_digest")
        prior_snapshot_handoff = snapshot.get("chat_process_handoff")
        prior_supervisor = snapshot.get("runtime_supervisor_generation")
        if (snapshot.get("installation_identity") != handle.identity.value
                or not isinstance(snapshot_digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", snapshot_digest)
                or semantic_digest({key: item for key, item in snapshot.items()
                    if key != "snapshot_semantic_digest"}) != snapshot_digest
                or not isinstance(prior_supervisor, str) or not prior_supervisor
                or not isinstance(prior_snapshot_handoff, Mapping)):
            raise ChatProcessGenerationError("chat_process_predecessor_snapshot_invalid")
        prior = _handoff_identity(prior_snapshot_handoff)
        verified_prior = verify_stored_chat_process_handoff(handle=handle,
            handoff_id=str(prior["handoff_id"]), expected_digest=str(prior["handoff_digest"]))
        if any(prior[key] != verified_prior[key] for key in prior):
            raise ChatProcessGenerationError("chat_process_predecessor_handoff_mismatch")
        if prior_snapshot_handoff.get("status") != "runtime_launcher_child_launch_and_source_bound":
            raise ChatProcessGenerationError("chat_process_predecessor_handoff_status_invalid")
        predecessor_record = _read_handoff(handle, str(prior["handoff_id"]))
        if dict(prior_snapshot_handoff) != _handoff_summary(
                predecessor_record, "runtime_launcher_child_launch_and_source_bound"):
            raise ChatProcessGenerationError("chat_process_predecessor_handoff_mismatch")
        record["prior_snapshot_handoff"] = dict(prior_snapshot_handoff)
        record["prior_snapshot_digest"] = snapshot_digest
        record["prior_snapshot_supervisor_generation"] = prior_supervisor
        record["prior_startup_snapshot"] = snapshot
        record["predecessor_relation"] = "prior_snapshot_reference_not_direct"
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



def _handoff_summary(record: Mapping[str, Any], status: str) -> dict[str, Any]:
    summary: dict[str, Any] = {"status": status,
        "handoff_id": record["handoff_id"], "handoff_digest": record["handoff_digest"],
        "process_instance_id": record["process_instance_id"],
        "software_generation_digest": record["software_generation_digest"],
        "process_id": record["process_id"], "parent_process_id": record["parent_process_id"],
        "startup_timestamp": record["startup_timestamp"],
        "source_generation_scope": "sentientos_and_scripts_python_sources"}
    if record.get("schema_version") in {V2_SCHEMA, SCHEMA}:
        summary["prior_snapshot_generation"] = {
            "handoff": record["prior_snapshot_handoff"],
            "startup_snapshot_digest": record["prior_snapshot_digest"],
            "supervisor_generation": record["prior_snapshot_supervisor_generation"],
            "relation": record["predecessor_relation"],
            "overlap_status": record["prior_process_overlap_status"],
            "direct_predecessorship": "not_proven",
            "intervening_runtime_generations": "unknown"}
    if record.get("schema_version") == SCHEMA:
        summary["configured_serving_operation_id"] = record["configured_serving_operation_id"]
    return summary


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
    return _handoff_summary(record, "runtime_launcher_process_and_source_bound")



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
    return _handoff_summary(record, "runtime_launcher_child_launch_and_source_bound")



def _handoff_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = ("handoff_id", "handoff_digest", "process_instance_id",
        "software_generation_digest", "process_id", "parent_process_id",
        "startup_timestamp", "source_generation_scope")
    if any(key not in value for key in fields):
        raise ChatProcessGenerationError("chat_process_generation_edge_handoff_incomplete")
    return {key: value[key] for key in fields}



def verify_chat_process_generation_lineage(*, handle: Any,
        handoff_id: str, expected_digest: str | None = None) -> tuple[dict[str, Any], ...]:
    """Reconstruct the bounded immutable prior-snapshot chain without asserting liveness."""
    current = _read_handoff(handle, handoff_id, verify_predecessor=False)
    if expected_digest is not None and current["handoff_digest"] != expected_digest:
        raise ChatProcessGenerationError("chat_process_handoff_identity_mismatch")
    lineage: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _ in range(MAX_HANDOFF_ENTRIES):
        current_id = str(current["handoff_id"])
        if current_id in seen:
            raise ChatProcessGenerationError("chat_process_handoff_lineage_cycle")
        seen.add(current_id)
        lineage.append(_handoff_summary(current, "historical_launcher_handoff_custody_verified"))
        prior = current.get("prior_snapshot_handoff")
        if prior is None:
            return tuple(lineage)
        if not isinstance(prior, Mapping):
            raise ChatProcessGenerationError("chat_process_handoff_predecessor_invalid")
        predecessor = _read_handoff(handle, str(prior.get("handoff_id", "")),
            verify_predecessor=False)
        if predecessor["handoff_digest"] != prior.get("handoff_digest"):
            raise ChatProcessGenerationError("chat_process_handoff_predecessor_digest_mismatch")
        expected_summary = _handoff_summary(
            predecessor, "runtime_launcher_child_launch_and_source_bound")
        if dict(prior) != expected_summary:
            raise ChatProcessGenerationError("chat_process_handoff_predecessor_identity_mismatch")
        current = predecessor
    raise ChatProcessGenerationError("chat_process_handoff_lineage_depth_exceeded")


def verify_stored_chat_process_handoff(*, handle: Any,
                                       handoff_id: str, expected_digest: str) -> dict[str, Any]:
    """Verify historical owner custody without asserting the old process still runs."""
    record = _read_handoff(handle, handoff_id)
    if record["handoff_digest"] != expected_digest:
        raise ChatProcessGenerationError("chat_process_handoff_identity_mismatch")
    verify_chat_process_generation_lineage(handle=handle, handoff_id=handoff_id,
        expected_digest=expected_digest)
    return _handoff_summary(record, "runtime_launcher_process_and_source_bound")



def publish_chat_process_runtime_observation(*, handle: InstallationStateHandle,
        supervisor_generation: str, handoff: Mapping[str, Any],
        status: str = "running_observed", reason_code: str | None = None,
        configured_serving_receipt_posture: str = "not_observed",
        serving_receipt: Mapping[str, Any] | None = None,
        expected_serving_operation_id: str | None = None) -> dict[str, Any]:
    """Atomically publish the canonical runtime owner's bounded point observation."""
    if type(handle) is not InstallationStateHandle:
        raise ChatProcessGenerationError("runtime_observation_mutable_owner_required")
    if (not isinstance(supervisor_generation, str) or not supervisor_generation
            or len(supervisor_generation) > 128
            or status not in {"running_observed", "not_verified"}
            or configured_serving_receipt_posture not in {
                "not_observed", "selected_receipt_for_configured_operation",
                "configured_operation_not_verified", "configured_operation_receipt_unavailable", "configured_operation_receipt_invalid",
                "runtime_not_verified"}
            or (status == "not_verified" and not reason_code)
            or (serving_receipt is not None and (
                status != "running_observed"
                or configured_serving_receipt_posture != "selected_receipt_for_configured_operation"
                or not isinstance(expected_serving_operation_id, str)
                or not expected_serving_operation_id))
            or (configured_serving_receipt_posture == "selected_receipt_for_configured_operation"
                and serving_receipt is None)
            or (reason_code is not None and (not isinstance(reason_code, str)
                or not re.fullmatch(r"[a-z0-9_]{1,80}", reason_code)))):
        raise ChatProcessGenerationError("runtime_observation_fields_invalid")
    if status == "running_observed":
        if not isinstance(handoff, Mapping) or handoff.get("status") != "runtime_launcher_process_and_source_bound":
            raise ChatProcessGenerationError("runtime_observation_handoff_unverified")
    try:
        historical = verify_stored_chat_process_handoff(handle=handle,
            handoff_id=str(handoff.get("handoff_id", "")),
            expected_digest=str(handoff.get("handoff_digest", "")))
    except Exception as exc:
        raise ChatProcessGenerationError("runtime_observation_handoff_invalid") from exc
    if dict(handoff) != historical:
        raise ChatProcessGenerationError("runtime_observation_handoff_mismatch")
    historical_operation = historical.get("configured_serving_operation_id")
    if expected_serving_operation_id is not None and (
            expected_serving_operation_id != historical_operation):
        raise ChatProcessGenerationError("runtime_observation_serving_operation_handoff_mismatch")
    if serving_receipt is not None and (
            expected_serving_operation_id is None
            or expected_serving_operation_id != historical_operation):
        raise ChatProcessGenerationError("runtime_observation_serving_operation_handoff_mismatch")
    serving_projection = None
    if serving_receipt is not None:
        receipt_binding = serving_receipt.get("binding")
        if (serving_receipt.get("schema_version")
                != "sentientos.local_model_serving_session_receipt:v1"
                or not isinstance(serving_receipt.get("receipt_id"), str)
                or not isinstance(serving_receipt.get("session_id"), str)
                or re.fullmatch(r"serving-receipt-[0-9a-f]{24}",
                    str(serving_receipt.get("receipt_id", ""))) is None
                or serving_receipt.get("receipt_id") != "serving-receipt-" + semantic_digest({
                    key: value for key, value in serving_receipt.items()
                    if key not in {"receipt_id", "receipt_semantic_digest"}})[:24]
                or serving_receipt.get("session_id") != "serving-session-" + semantic_digest(receipt_binding)[:24]
                or serving_receipt.get("receipt_semantic_digest")
                    != semantic_digest({key: value for key, value in serving_receipt.items()
                        if key != "receipt_semantic_digest"})
                or serving_receipt.get("control_plane_authority_class") != "model_serving"
                or serving_receipt.get("admission_outcome") != "allow"
                or serving_receipt.get("model_loaded") is not True
                or serving_receipt.get("serving_session_bound") is not True
                or serving_receipt.get("inference_performed") is not False
                or not isinstance(receipt_binding, Mapping)
                or receipt_binding.get("installation_identity") != handle.identity.value
                or receipt_binding.get("serving_operation_id") != expected_serving_operation_id):
            raise ChatProcessGenerationError("runtime_observation_configured_operation_receipt_invalid")
        identity_fields = (
            "model_id", "artifact_id", "runtime_id", "authority_map_digest",
            "activation_state_semantic_digest", "activation_generation",
            "activation_receipt_id", "activation_receipt_semantic_digest")
        model_identity = {key: receipt_binding.get(key) for key in identity_fields}
        if any(value is None for value in model_identity.values()):
            raise ChatProcessGenerationError("runtime_observation_serving_identity_incomplete")
        serving_projection = {
            "receipt_id": serving_receipt["receipt_id"],
            "receipt_semantic_digest": serving_receipt["receipt_semantic_digest"],
            "session_id": serving_receipt.get("session_id"),
            "serving_operation_id": expected_serving_operation_id,
            "model_identity_in_receipt": model_identity,
            "model_loaded_in_receipt": True,
            "selection_posture": "selected_receipt_for_configured_operation",
        }
    body: dict[str, Any] = {
        "schema_version": RUNTIME_OBSERVATION_SCHEMA,
        "installation_identity": handle.identity.value,
        "runtime_supervisor_generation": supervisor_generation,
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "runtime_status": status,
        "reason_code": reason_code,
        "configured_serving_receipt_posture": configured_serving_receipt_posture,
        "serving_receipt": serving_projection,
        "configured_serving_operation_id": historical.get("configured_serving_operation_id"),
        "handoff_id": historical["handoff_id"],
        "handoff_digest": historical["handoff_digest"],
        "process_instance_id": historical["process_instance_id"],
        "process_id": historical["process_id"],
        "parent_process_id": historical["parent_process_id"],
        "software_generation_digest": historical["software_generation_digest"],
        "source_generation_scope": historical["source_generation_scope"],
        "currentness_posture": "runtime_owner_observed_at_recorded_event_time",
        "independent_signature": False,
        "effect_authority": False,
    }
    body["observation_semantic_digest"] = semantic_digest(body)
    encoded = _canonical(body)
    if len(encoded) > MAX_RUNTIME_OBSERVATION_BYTES:
        raise ChatProcessGenerationError("runtime_observation_too_large")
    directory = handle.fixed_object("local-model/chat/runtime-observations")
    handle.ensure_directory(directory)
    lock = handle.fixed_object(RUNTIME_OBSERVATION_LOCK)
    target = handle.fixed_object(RUNTIME_OBSERVATION_PATH)
    try:
        with handle.exclusive_lock(lock):
            previous = read_stored_chat_process_runtime_observation(handle)
            if previous is not None and all(previous.get(key) == body.get(key) for key in (
                    "schema_version", "runtime_supervisor_generation", "runtime_status", "handoff_id",
                    "handoff_digest", "reason_code", "configured_serving_receipt_posture",
                    "serving_receipt")):
                previous_time = datetime.fromisoformat(
                    str(previous["observed_at"]).replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - previous_time).total_seconds()
                if 0 <= age < MIN_RUNTIME_OBSERVATION_REFRESH_SECONDS:
                    return previous
            handle.durable_replace(target, encoded)
    except InstallationStateError as exc:
        raise ChatProcessGenerationError("runtime_observation_publication_failed") from exc
    return body


def read_stored_chat_process_runtime_observation(handle: Any) -> dict[str, Any] | None:
    """Read the selected installation's immutable-identity, replaceable status image."""
    try:
        path = (RUNTIME_OBSERVATION_PATH
            if isinstance(handle, (InstallationStateReadOnlyView, WindowsInstallationStateReadOnlyView))
            else handle.fixed_object(RUNTIME_OBSERVATION_PATH))
        raw = handle.read_optional_regular_bounded(
            path, max_bytes=MAX_RUNTIME_OBSERVATION_BYTES)
    except InstallationStateError as exc:
        raise ChatProcessGenerationError("runtime_observation_read_failed") from exc
    if raw is None:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ChatProcessGenerationError("runtime_observation_malformed") from exc
    if (not isinstance(value, dict) or raw != _canonical(value)
            or value.get("schema_version") not in {RUNTIME_OBSERVATION_SCHEMA,
                V2_RUNTIME_OBSERVATION_SCHEMA, LEGACY_RUNTIME_OBSERVATION_SCHEMA}
            or value.get("installation_identity") != handle.identity.value
            or not isinstance(value.get("runtime_supervisor_generation"), str)
            or not value.get("runtime_supervisor_generation")
            or len(value["runtime_supervisor_generation"]) > 128
            or value.get("observation_semantic_digest")
                != semantic_digest(_without(value, "observation_semantic_digest"))
            or value.get("runtime_status") not in {"running_observed", "not_verified"}
            or (value.get("runtime_status") == "not_verified"
                and not isinstance(value.get("reason_code"), str))
            or (value.get("runtime_status") == "running_observed"
                and value.get("reason_code") is not None)
            or value.get("currentness_posture") != "runtime_owner_observed_at_recorded_event_time"
            or value.get("independent_signature") is not False
            or value.get("effect_authority") is not False):
        raise ChatProcessGenerationError("runtime_observation_identity_invalid")
    base_fields = {
        "schema_version", "installation_identity", "runtime_supervisor_generation",
        "observed_at", "runtime_status", "reason_code", "handoff_id", "handoff_digest",
        "process_instance_id", "process_id", "parent_process_id",
        "software_generation_digest", "source_generation_scope", "currentness_posture",
        "independent_signature", "effect_authority", "observation_semantic_digest",
    }
    if value["schema_version"] == LEGACY_RUNTIME_OBSERVATION_SCHEMA:
        expected_fields = base_fields
    elif value["schema_version"] == V2_RUNTIME_OBSERVATION_SCHEMA:
        expected_fields = base_fields | {"configured_serving_receipt_posture", "serving_receipt"}
    else:
        expected_fields = base_fields | {"configured_serving_receipt_posture", "serving_receipt",
            "configured_serving_operation_id"}
    if set(value) != expected_fields:
        raise ChatProcessGenerationError("runtime_observation_shape_invalid")
    try:
        timestamp = datetime.fromisoformat(str(value.get("observed_at", "")).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ChatProcessGenerationError("runtime_observation_time_invalid") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ChatProcessGenerationError("runtime_observation_time_invalid")
    handoff = verify_stored_chat_process_handoff(handle=handle,
        handoff_id=str(value.get("handoff_id", "")), expected_digest=str(value.get("handoff_digest", "")))
    expected = {
        "process_instance_id": handoff["process_instance_id"],
        "process_id": handoff["process_id"],
        "parent_process_id": handoff["parent_process_id"],
        "software_generation_digest": handoff["software_generation_digest"],
        "source_generation_scope": handoff["source_generation_scope"],
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise ChatProcessGenerationError("runtime_observation_handoff_binding_mismatch")
    if (value.get("schema_version") == RUNTIME_OBSERVATION_SCHEMA
            and value.get("configured_serving_operation_id")
                != handoff.get("configured_serving_operation_id")):
        raise ChatProcessGenerationError("runtime_observation_serving_operation_handoff_mismatch")
    serving = value.get("serving_receipt")
    if serving is not None:
        if (not isinstance(serving, Mapping)
                or value.get("configured_serving_receipt_posture") != "selected_receipt_for_configured_operation"
                or serving.get("selection_posture") != "selected_receipt_for_configured_operation"
                or serving.get("model_loaded_in_receipt") is not True
                or set(serving) != {"receipt_id", "receipt_semantic_digest", "session_id",
                    "serving_operation_id", "model_identity_in_receipt", "model_loaded_in_receipt",
                    "selection_posture"}):
            raise ChatProcessGenerationError("runtime_observation_serving_projection_invalid")
        serving_id = serving.get("receipt_id")
        serving_digest = serving.get("receipt_semantic_digest")
        if (not isinstance(serving_id, str)
                or re.fullmatch(r"serving-receipt-[0-9a-f]{24}", serving_id) is None
                or not isinstance(serving_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", serving_digest) is None
                or not isinstance(serving.get("session_id"), str)
                or re.fullmatch(r"serving-session-[0-9a-f]{24}",
                    serving["session_id"]) is None
                or not isinstance(serving.get("serving_operation_id"), str)
                or not serving["serving_operation_id"] or len(serving["serving_operation_id"]) > 128):
            raise ChatProcessGenerationError("runtime_observation_serving_identity_invalid")
        path = f"local-model/serving/receipts/{serving_id}.json"
        try:
            receipt_path = (path if isinstance(handle, (
                InstallationStateReadOnlyView, WindowsInstallationStateReadOnlyView))
                else handle.fixed_object(path))
            serving_raw = handle.read_regular_bounded(receipt_path, max_bytes=262_144)
            serving_record = json.loads(serving_raw.decode("utf-8"))
        except Exception as exc:
            raise ChatProcessGenerationError("runtime_observation_configured_operation_receipt_unavailable") from exc
        serving_canonical = (json.dumps(serving_record, sort_keys=True, separators=(",", ":"))
            + "\n").encode("utf-8") if isinstance(serving_record, dict) else b""
        if (not isinstance(serving_record, dict) or serving_raw != serving_canonical
                or serving_record.get("receipt_id") != serving_id
                or serving_record.get("receipt_semantic_digest") != serving_digest
                or serving_digest != semantic_digest({key: item for key, item in serving_record.items()
                    if key != "receipt_semantic_digest"})
                or serving_record.get("schema_version")
                    != "sentientos.local_model_serving_session_receipt:v1"
                or serving_record.get("control_plane_authority_class") != "model_serving"
                or serving_record.get("admission_outcome") != "allow"
                or serving_record.get("model_loaded") is not True
                or serving_record.get("serving_session_bound") is not True
                or serving_record.get("inference_performed") is not False):
            raise ChatProcessGenerationError("runtime_observation_configured_operation_receipt_invalid")
        binding = serving_record.get("binding")
        if (not isinstance(binding, Mapping)
                or serving_record.get("receipt_id") != "serving-receipt-" + semantic_digest({
                    key: item for key, item in serving_record.items()
                    if key not in {"receipt_id", "receipt_semantic_digest"}})[:24]
                or serving_record.get("session_id") != "serving-session-" + semantic_digest(binding)[:24]
                or binding.get("installation_identity") != handle.identity.value
                or binding.get("serving_operation_id") != serving.get("serving_operation_id")
                or serving_record.get("session_id") != serving.get("session_id")):
            raise ChatProcessGenerationError("runtime_observation_serving_receipt_binding_mismatch")
        fields = serving.get("model_identity_in_receipt")
        expected_model_fields = {"model_id", "artifact_id", "runtime_id",
            "authority_map_digest", "activation_state_semantic_digest", "activation_generation",
            "activation_receipt_id", "activation_receipt_semantic_digest"}
        if (not isinstance(fields, Mapping) or set(fields) != expected_model_fields
                or any(binding.get(key) != item for key, item in fields.items())):
            raise ChatProcessGenerationError("runtime_observation_serving_model_identity_mismatch")
    elif value.get("configured_serving_receipt_posture") not in {
            None, "not_observed", "configured_operation_not_verified",
            "configured_operation_receipt_unavailable", "configured_operation_receipt_invalid", "runtime_not_verified"}:
        raise ChatProcessGenerationError("runtime_observation_serving_posture_invalid")
    return value


def open_chat_process_handoff(*, installation_identity: str, handoff_id: str,
                              wait_seconds: float = 5.0) -> tuple[InstallationStateHandle, dict[str, Any]]:
    """Open an exact handoff, allowing the parent a short publication window after spawn."""
    import time
    identity = InstallationIdentity.parse(installation_identity)
    handle = InstallationStateRegistry.system().open(identity)
    deadline = time.monotonic() + max(0.0, min(float(wait_seconds), 5.0))
    while True:
        try:
            current = verify_current_chat_process_handoff(handle=handle, handoff_id=handoff_id)
            verify_chat_process_generation_lineage(handle=handle, handoff_id=handoff_id,
                expected_digest=str(current["handoff_digest"]))
            return handle, current
        except ChatProcessGenerationError as exc:
            if str(exc) != "chat_process_handoff_unavailable" or time.monotonic() >= deadline:
                raise
            time.sleep(0.01)
