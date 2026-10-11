"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
import collections
import datetime
import hashlib
import json
import logging
import math
import os
import stat
import secrets
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timezone
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, ParamSpec, Sequence, TypeVar, Union

from tools.storage_policy import (
    StoragePolicyConfig as StoragePolicy,
    rotate_text_digests,
    stash_highlight,
)

from sentientos.privilege import require_admin_banner, require_lumos_approval

LOGGER = logging.getLogger(__name__)


class MemorySidecarIncompleteError(ValueError):
    """An append-only memory sidecar contains malformed evidence."""
    def __init__(self, sidecar: str, line_number: int) -> None:
        self.sidecar = sidecar
        self.line_number = line_number
        super().__init__(f"memory_sidecar_incomplete:{sidecar}:line:{line_number}")

# Vector type can be either an embedding vector or bag-of-words mapping
Vector = Union[List[float], Dict[str, int]]
from emotions import empty_emotion_vector
import emotion_memory as em
import semantic_embeddings as se

# Optional upgrade: use simple embedding vectors instead of bag-of-words
USE_EMBEDDINGS = os.getenv("USE_EMBEDDINGS", "0") == "1"

# Root folder for persistent memory fragments. The ``MEMORY_DIR`` environment
# variable is described in ``docs/ENVIRONMENT.md``.
from sentientos.canonical_memory import sentientos_data_dir, sentientos_memory_dir

_DATA_ROOT = sentientos_data_dir()
MEMORY_DIR = sentientos_memory_dir(_DATA_ROOT)
RAW_PATH = MEMORY_DIR / "raw"
DAY_PATH = MEMORY_DIR / "distilled"
TOPIC_PATH = MEMORY_DIR / "topics"
TURN_PATH = MEMORY_DIR / "turns"
SESSION_PATH = MEMORY_DIR / "sessions"
VECTOR_INDEX_PATH = MEMORY_DIR / "vector.idx"
GOALS_PATH = MEMORY_DIR / "goals.json"
TOMB_PATH = MEMORY_DIR / "memory_tomb.jsonl"
OBSERVATION_LOG_PATH = MEMORY_DIR / "perception_observations.jsonl"
CURIOSITY_REFLECTIONS_PATH = MEMORY_DIR / "curiosity_reflections.jsonl"
TRANSCRIPT_LOG_PATH = MEMORY_DIR / "audio_transcripts.jsonl"
SCREEN_DIGEST_PATH = MEMORY_DIR / "screen_ocr.jsonl"
GLOW_DIR = MEMORY_DIR / "glow"
DIGEST_DIR = GLOW_DIR / "digests"
HIGHLIGHT_DIR = GLOW_DIR / "highlights"


_HEADLESS_APPROVAL_REPORTED = False
_LEGACY_OPERATION_STATE: ContextVar[tuple[int, bool]] = ContextVar(
    "legacy_memory_operation_state", default=(0, False)
)
_P = ParamSpec("_P")
_R = TypeVar("_R")


def _legacy_mutation_operation(function: Callable[_P, _R]) -> Callable[_P, _R]:
    """Share one successful authorization across nested writes in one public operation."""
    @wraps(function)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        depth, authorized = _LEGACY_OPERATION_STATE.get()
        token = _LEGACY_OPERATION_STATE.set((depth + 1, authorized if depth else False))
        try:
            return function(*args, **kwargs)
        finally:
            _LEGACY_OPERATION_STATE.reset(token)

    return wrapped


def _authorize_legacy_mutation() -> None:
    """Retain the legacy Administrator/Lumos boundary for each memory effect."""
    global _HEADLESS_APPROVAL_REPORTED
    depth, authorized = _LEGACY_OPERATION_STATE.get()
    if depth and authorized:
        return
    require_admin_banner()
    if os.getenv("LUMOS_AUTO_APPROVE") == "1" or os.getenv("SENTIENTOS_HEADLESS") == "1":
        if depth:
            _LEGACY_OPERATION_STATE.set((depth, True))
        if not _HEADLESS_APPROVAL_REPORTED:
            print("[Lumos] Blessing auto-approved (headless mode).")
            _HEADLESS_APPROVAL_REPORTED = True
        return
    require_lumos_approval()
    if depth:
        _LEGACY_OPERATION_STATE.set((depth, True))


def _open_legacy_memory_root(*, prepare_for_write: bool = False) -> int:
    """Use the canonical owner for the shared user-memory root."""
    if os.name != "posix":
        raise PermissionError("legacy_memory_root_custody_unsupported_platform")
    from sentientos.canonical_memory import CanonicalMemoryStore
    return CanonicalMemoryStore(MEMORY_DIR).open_memory_root(
        prepare_for_write=prepare_for_write)


def _read_legacy_memory_file(path: Path, *, max_bytes: int = 8 * 1024 * 1024) -> bytes | None:
    """Read one top-level memory sidecar through the held private root."""
    try:
        relative = path.relative_to(MEMORY_DIR)
    except ValueError as exc:
        raise PermissionError("legacy_memory_read_outside_configured_root") from exc
    if len(relative.parts) != 1 or relative.name in {"", ".", ".."}:
        raise PermissionError("legacy_memory_sidecar_path_invalid")
    if os.name == "nt":
        from sentientos.windows_handle_custody import (
            WindowsHandleCustodyError, read_explicit_file, verify_explicit_directory,
        )
        try:
            verify_explicit_directory(MEMORY_DIR, require_private_acl=True)
            return read_explicit_file(path, max_bytes=max_bytes, require_private_acl=True)
        except WindowsHandleCustodyError as exc:
            if exc.args == ("explicit_file_missing",):
                return None
            raise PermissionError("legacy_memory_sidecar_custody_unavailable") from exc
    root_fd = _open_legacy_memory_root()
    descriptor: int | None = None
    try:
        try:
            descriptor = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW
                | getattr(os, "O_NONBLOCK", 0), dir_fd=root_fd)
        except FileNotFoundError:
            return None
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.geteuid()
                or before.st_size > max_bytes):
            raise PermissionError("legacy_memory_sidecar_custody_invalid")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (len(payload) > max_bytes or len(payload) != before.st_size
                or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns
                or after.st_ctime_ns != before.st_ctime_ns
                or after.st_dev != before.st_dev or after.st_ino != before.st_ino):
            raise PermissionError("legacy_memory_sidecar_changed")
        return payload
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(root_fd)


@contextmanager
def _open_legacy_memory_text(path: Path, mode: str):
    """Open a shared sidecar through held custody; replace-mode writes publish atomically."""
    if mode not in {"a", "w"}:
        raise ValueError("legacy_memory_write_mode_invalid")
    _authorize_legacy_mutation()
    try:
        relative = path.relative_to(MEMORY_DIR)
    except ValueError as exc:
        raise PermissionError("legacy_memory_write_outside_configured_root") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise PermissionError("legacy_memory_write_path_invalid")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = _open_legacy_memory_root(prepare_for_write=True)
    current_fd = root_fd
    descriptor: int | None = None
    temporary_name: str | None = None
    temporary_exists = False
    try:
        for component in relative.parts[:-1]:
            created = False
            try:
                os.mkdir(component, mode=0o700, dir_fd=current_fd)
                created = True
            except FileExistsError:
                pass
            child_fd = os.open(component, directory_flags, dir_fd=current_fd)
            metadata = os.fstat(child_fd)
            if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
                os.close(child_fd)
                raise PermissionError("legacy_memory_parent_custody_invalid")
            if stat.S_IMODE(metadata.st_mode) & 0o077:
                os.fchmod(child_fd, 0o700)
                metadata = os.fstat(child_fd)
                if stat.S_IMODE(metadata.st_mode) & 0o077:
                    os.close(child_fd)
                    raise PermissionError("legacy_memory_parent_permissions_invalid")
            if created:
                os.fsync(current_fd)
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = child_fd
        target_name = relative.parts[-1]
        if mode == "a":
            flags = (os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW
                | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
            descriptor = os.open(target_name, flags, 0o600, dir_fd=current_fd)
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_uid != os.geteuid()):
                raise PermissionError("legacy_memory_target_custody_invalid")
            os.fchmod(descriptor, 0o600)
            result = os.fdopen(descriptor, "a", encoding="utf-8")
            descriptor = None
            try:
                yield result
            finally:
                result.flush()
                os.fsync(result.fileno())
                result.close()
                os.fsync(current_fd)
        else:
            temporary_name = f".legacy-sidecar-{secrets.token_hex(16)}.tmp"
            flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
            descriptor = os.open(temporary_name, flags, 0o600, dir_fd=current_fd)
            temporary_exists = True
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_uid != os.geteuid()):
                raise PermissionError("legacy_memory_temporary_custody_invalid")
            os.fchmod(descriptor, 0o600)
            result = os.fdopen(descriptor, "w", encoding="utf-8")
            descriptor = None
            try:
                yield result
                result.flush()
                if os.fstat(result.fileno()).st_size > 8 * 1024 * 1024:
                    raise ValueError("legacy_memory_sidecar_size_limit")
                os.fsync(result.fileno())
            finally:
                result.close()
            try:
                current = os.stat(target_name, dir_fd=current_fd, follow_symlinks=False)
            except FileNotFoundError:
                try:
                    os.link(temporary_name, target_name, src_dir_fd=current_fd,
                        dst_dir_fd=current_fd, follow_symlinks=False)
                except FileExistsError:
                    current = os.stat(target_name, dir_fd=current_fd, follow_symlinks=False)
                    if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
                            or current.st_uid != os.geteuid()):
                        raise PermissionError("legacy_memory_target_custody_invalid")
                    os.replace(temporary_name, target_name,
                        src_dir_fd=current_fd, dst_dir_fd=current_fd)
                    temporary_exists = False
                else:
                    os.fsync(current_fd)
            else:
                if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
                        or current.st_uid != os.geteuid()):
                    raise PermissionError("legacy_memory_target_custody_invalid")
                os.replace(temporary_name, target_name,
                    src_dir_fd=current_fd, dst_dir_fd=current_fd)
                temporary_exists = False
            os.fsync(current_fd)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_exists and temporary_name is not None and current_fd >= 0:
            try:
                os.unlink(temporary_name, dir_fd=current_fd)
                os.fsync(current_fd)
            except FileNotFoundError:
                pass
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def _open_legacy_raw_directory(*, prepare_for_write: bool = False) -> int:
    """Open the shared raw user-memory root through canonical held custody."""
    if os.name != "posix":
        raise PermissionError("legacy_raw_memory_private_custody_unsupported_platform")
    from sentientos.canonical_memory import CanonicalMemoryStore
    return CanonicalMemoryStore(MEMORY_DIR).open_raw_directory(
        prepare_for_write=prepare_for_write)


def _read_legacy_raw_fragment(name: str) -> bytes | None:
    """Read one owner-private legacy fragment from the held shared raw root."""
    if (not isinstance(name, str) or not name.endswith(".json")
            or name in {".", ".."} or "/" in name or "\\" in name
            or _is_canonical_retention_path(Path(name))):
        raise PermissionError("legacy_raw_memory_fragment_name_invalid")
    if os.name == "nt":
        from sentientos.windows_handle_custody import (
            WindowsHandleCustodyError, read_explicit_file, verify_explicit_directory,
        )
        try:
            verify_explicit_directory(RAW_PATH, require_private_acl=True)
            return read_explicit_file(RAW_PATH / name, max_bytes=262144,
                require_private_acl=True)
        except WindowsHandleCustodyError as exc:
            if exc.args == ("explicit_file_missing",):
                return None
            raise PermissionError("legacy_raw_memory_fragment_custody_unavailable") from exc
    directory_fd = _open_legacy_raw_directory()
    descriptor: int | None = None
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW
            | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) & 0o022
                or before.st_size > 262144):
            raise PermissionError("legacy_raw_memory_fragment_custody_invalid")
        chunks: list[bytes] = []
        remaining = 262145
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (len(payload) > 262144 or len(payload) != before.st_size
                or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns
                or after.st_ctime_ns != before.st_ctime_ns
                or after.st_dev != before.st_dev or after.st_ino != before.st_ino):
            raise PermissionError("legacy_raw_memory_fragment_changed")
        return payload
    except FileNotFoundError:
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_fd)

# Registered callbacks invoked whenever a new reflection is stored.
ReflectionListener = Callable[[dict], None]
_REFLECTION_LISTENERS: list[ReflectionListener] = []


def add_reflection_listener(listener: ReflectionListener) -> None:
    """Register *listener* to be invoked after :func:`save_reflection`."""

    _REFLECTION_LISTENERS.append(listener)


def _notify_reflection_listeners(summary: dict) -> None:
    if not _REFLECTION_LISTENERS:
        return
    for listener in list(_REFLECTION_LISTENERS):
        try:
            listener(dict(summary))
        except PermissionError:
            raise
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("Reflection listener %r failed", listener, exc_info=True)

# --- Importance & forgetting heuristics -------------------------------------

FORGETTING_HALF_LIFE_DAYS = float(os.getenv("MEMORY_HALF_LIFE_DAYS", "14"))
IMPORTANCE_FLOOR = float(os.getenv("MEMORY_IMPORTANCE_FLOOR", "0.2"))
IMPORTANCE_TAG_BOOSTS = {
    "goal": 0.15,
    "reflection": 0.2,
    "self_patch": 0.1,
    "escalation": 0.25,
    "blessing": 0.12,
}
_INDEX_LOCK = RLock()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _fragment_path(fragment_id: str) -> Path:
    return RAW_PATH / f"{fragment_id}.json"

def _is_canonical_retention_path(path: Path) -> bool:
    """Keep explicitly retained chat artifacts outside legacy mutation/forgetting."""
    return path.name.startswith("memory-") and path.name.endswith(".json")


def _legacy_fragment_paths() -> list[Path]:
    """Enumerate bounded owner-private legacy fragments through a held directory."""
    if os.name == "nt":
        from sentientos.windows_handle_custody import (
            WindowsHandleCustodyError, read_regular_files, verify_explicit_directory,
        )
        try:
            verify_explicit_directory(MEMORY_DIR, require_private_acl=True)
            entries = read_regular_files(RAW_PATH, max_entries=4096,
                max_file_bytes=262144, max_total_bytes=16777216,
                suffix=".json", require_private_acl=True)
        except WindowsHandleCustodyError as exc:
            if exc.args == ("explicit_file_missing",):
                return []
            raise PermissionError("legacy_raw_memory_scan_custody_unavailable") from exc
        return [RAW_PATH / name for name, _data in entries
            if not _is_canonical_retention_path(Path(name))]
    try:
        directory_fd = _open_legacy_raw_directory()
    except FileNotFoundError:
        return []
    try:
        names: list[str] = []
        total = 0
        with os.scandir(directory_fd) as entries:
            for index, entry in enumerate(entries):
                if index >= 4096:
                    raise PermissionError("legacy_raw_memory_scan_bound_exceeded")
                if not entry.name.endswith(".json"):
                    continue
                if _is_canonical_retention_path(Path(entry.name)):
                    continue
                metadata = entry.stat(follow_symlinks=False)
                if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                        or metadata.st_uid != os.geteuid()
                        or stat.S_IMODE(metadata.st_mode) & 0o022):
                    raise PermissionError("legacy_raw_memory_fragment_custody_invalid")
                total += metadata.st_size
                if metadata.st_size > 262144 or total > 16777216:
                    raise PermissionError("legacy_raw_memory_scan_byte_bound_exceeded")
                names.append(entry.name)
        return [RAW_PATH / name for name in sorted(names)]
    finally:
        os.close(directory_fd)




def _load_fragment(fragment_id: str) -> dict | None:
    path = _fragment_path(fragment_id)
    if _is_canonical_retention_path(path) or path.parent != RAW_PATH:
        return None
    payload = _read_legacy_raw_fragment(path.name)
    if payload is None:
        return None
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MemorySidecarIncompleteError("legacy_raw_fragment", 0) from exc
    if not isinstance(data, dict) or data.get("id") != fragment_id:
        raise MemorySidecarIncompleteError("legacy_raw_fragment_identity", 0)
    return data


def _unlink_legacy_raw_fragment(fragment_id: str) -> bool:
    """Remove one owner-private legacy fragment without following path aliases."""
    path = _fragment_path(fragment_id)
    if (_is_canonical_retention_path(path) or path.parent != RAW_PATH
            or not path.name or "/" in path.name or "\\\\" in path.name):
        raise PermissionError("legacy_raw_memory_fragment_path_invalid")
    _authorize_legacy_mutation()
    directory_fd = _open_legacy_raw_directory(prepare_for_write=True)
    try:
        try:
            metadata = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077):
            raise PermissionError("legacy_raw_memory_fragment_custody_invalid")
        os.unlink(path.name, dir_fd=directory_fd)
        os.fsync(directory_fd)
        return True
    finally:
        os.close(directory_fd)


def _write_fragment(fragment_id: str, data: dict) -> None:
    path = _fragment_path(fragment_id)
    if _is_canonical_retention_path(path):
        raise PermissionError("canonical_retention_artifact_is_not_a_legacy_fragment")
    if (path.parent != RAW_PATH or not path.name or path.name in {".", ".."}
            or "/" in path.name or "\\" in path.name):
        raise PermissionError("legacy_raw_memory_fragment_path_invalid")
    _authorize_legacy_mutation()
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    if len(payload) > 262144:
        raise ValueError("legacy_raw_memory_fragment_size_limit")
    directory_fd = _open_legacy_raw_directory(prepare_for_write=True)
    temporary_name = f".legacy-fragment-{secrets.token_hex(16)}.tmp"
    descriptor: int | None = None
    temporary_exists = False
    try:
        flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
        temporary_exists = True
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short_legacy_raw_memory_write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            # Create-only publication preserves a concurrently created record.
            os.link(temporary_name, path.name, src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd, follow_symlinks=False)
        except FileExistsError:
            # Updates replace only a regular, singly-linked owner file.  Rename
            # is atomic within this held directory and never follows the target.
            current = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
            if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
                    or current.st_uid != os.geteuid()):
                raise PermissionError("legacy_raw_memory_fragment_custody_invalid")
            os.replace(temporary_name, path.name,
                src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            temporary_exists = False
        os.fsync(directory_fd)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except FileNotFoundError:
                pass
        os.close(directory_fd)


def iter_fragments(*, limit: int | None = None, reverse: bool = True) -> Iterable[dict]:
    """Yield raw memory fragments as dictionaries.

    Parameters
    ----------
    limit:
        Maximum number of fragments to yield. ``None`` returns every fragment.
    reverse:
        When ``True`` (default) iterate from newest to oldest.
    """

    files = sorted(_legacy_fragment_paths(), reverse=reverse)
    count = 0
    for fp in files:
        data = _load_fragment(fp.stem)
        if data is None:
            continue
        yield data
        count += 1
        if limit is not None and count >= limit:
            break


def _load_index_records() -> list[dict]:
    payload = _read_legacy_memory_file(VECTOR_INDEX_PATH)
    if payload is None:
        return []
    lines = payload.decode("utf-8").splitlines()
    records: list[dict] = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if i >= 4096:
            raise MemorySidecarIncompleteError("vector_index_entry_bound_exceeded", i + 1)
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MemorySidecarIncompleteError("vector_index", i + 1) from exc
        if not isinstance(value, dict):
            raise MemorySidecarIncompleteError("vector_index", i + 1)
        records.append(value)
    return records


def _save_index_records(records: Sequence[dict]) -> None:
    if len(records) > 4096:
        raise MemorySidecarIncompleteError("vector_index_entry_bound_exceeded", 0)
    with _INDEX_LOCK:
        with _open_legacy_memory_text(VECTOR_INDEX_PATH, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")


@contextmanager
def _vector_index_transaction():
    from sentientos.platform_fcntl import fcntl, require_flock
    require_flock()
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise PermissionError("vector_index_lock_custody_unsupported")
    root_fd = _open_legacy_memory_root(prepare_for_write=True)
    descriptor: int | None = None
    acquired = False
    try:
        flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(".vector-index.lock", flags, 0o600, dir_fd=root_fd)
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077):
            raise PermissionError("vector_index_lock_custody_invalid")
        deadline = time.monotonic() + 5.0
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("vector_index_lock_timeout")
                time.sleep(0.01)
        yield
    finally:
        if descriptor is not None:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
        os.close(root_fd)


def _remove_from_index(fragment_id: str) -> None:
    with _INDEX_LOCK, _vector_index_transaction():
        records = [rec for rec in _load_index_records() if rec.get("id") != fragment_id]
        _save_index_records(records)


@contextmanager
def _memory_tomb_lock():
    from sentientos.platform_fcntl import fcntl, require_flock
    require_flock()
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise PermissionError("memory_tomb_lock_custody_unsupported")
    root_fd = _open_legacy_memory_root(prepare_for_write=True)
    descriptor: int | None = None
    acquired = False
    try:
        flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(".memory-tomb.lock", flags, 0o600, dir_fd=root_fd)
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077):
            raise PermissionError("memory_tomb_lock_custody_invalid")
        deadline = time.monotonic() + 5.0
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("memory_tomb_lock_timeout")
                time.sleep(0.01)
        yield
    finally:
        if descriptor is not None:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
        os.close(root_fd)


def _append_tomb(entry: Dict) -> None:
    """Append a digest- and predecessor-bound purge event under single-writer lock."""
    _authorize_legacy_mutation()
    with _memory_tomb_lock():
        current = _read_legacy_memory_file(TOMB_PATH)
        previous_digest = None
        if current is not None:
            # A valid JSON object without its record delimiter is still an
            # interrupted append; do not concatenate a new event onto it.
            if current and not current.endswith(b"\n"):
                raise MemorySidecarIncompleteError("memory_tomb_unterminated", 0)
            # Refuse to extend a sidecar that cannot be recovered truthfully.
            list_tomb()
            prior_lines = [line for line in current.splitlines() if line]
            if prior_lines:
                previous_digest = hashlib.sha256(prior_lines[-1]).hexdigest()
        payload = entry.copy()
        payload.pop("hash", None)
        payload["previous_tomb_entry_digest"] = previous_digest
        if os.getenv("TOMB_HASH", "1") != "0":
            payload["hash"] = hashlib.sha256(
                json.dumps({key: value for key, value in payload.items() if key != "hash"},
                    sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
        with _open_legacy_memory_text(TOMB_PATH, "a") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _collapse_tomb_operations(records: Sequence[Dict]) -> List[Dict]:
    intents: dict[str, Dict] = {}
    results: dict[str, str] = {}
    ordinary: list[Dict] = []
    for entry in records:
        event_type = entry.get("event_type")
        if event_type not in {"purge_intent", "purge_result"}:
            ordinary.append(entry)
            continue
        operation_id = entry.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            raise MemorySidecarIncompleteError("memory_tomb_operation_identity", 0)
        if event_type == "purge_intent":
            prior = intents.get(operation_id)
            if prior is not None and prior != entry:
                raise MemorySidecarIncompleteError("memory_tomb_operation_conflict", 0)
            intents[operation_id] = entry
            continue
        state = entry.get("operation_state")
        if state not in {"deleted", "not_deleted"}:
            raise MemorySidecarIncompleteError("memory_tomb_operation_result", 0)
        prior_state = results.get(operation_id)
        if prior_state is not None and prior_state != state:
            raise MemorySidecarIncompleteError("memory_tomb_operation_conflict", 0)
        results[operation_id] = state
    if set(results) - set(intents):
        raise MemorySidecarIncompleteError("memory_tomb_orphan_result", 0)
    projected: list[Dict] = list(ordinary)
    for operation_id, intent in intents.items():
        value = dict(intent)
        state = results.get(operation_id)
        if state is not None:
            value["operation_state"] = state
            value["recovery_status"] = "result_recorded"
        else:
            value["operation_state"] = "incomplete"
            fragment = intent.get("fragment")
            fragment_id = fragment.get("id") if isinstance(fragment, dict) else None
            try:
                raw = (_read_legacy_raw_fragment(str(fragment_id) + ".json")
                    if isinstance(fragment_id, str) and fragment_id else None)
            except (OSError, ValueError):
                raw = None
                value["recovery_status"] = "custody_unavailable"
            if "recovery_status" not in value:
                if raw is None:
                    value["recovery_status"] = "delete_outcome_unconfirmed"
                else:
                    try:
                        stored = json.loads(raw.decode("utf-8"))
                    except (UnicodeError, json.JSONDecodeError):
                        stored = None
                    if stored == fragment:
                        value["recovery_status"] = "interrupted_before_delete"
                    else:
                        value["recovery_status"] = "pending_fragment_conflict"
        projected.append(value)
    return projected


def list_tomb(
    *, tag: str | None = None, reason: str | None = None, date: str | None = None
) -> List[Dict]:
    """Return tomb entries filtered by tag, reason, or date."""
    payload = _read_legacy_memory_file(TOMB_PATH)
    if payload is None:
        return []
    out: List[Dict] = []
    lines = payload.decode("utf-8").splitlines()
    raw_lines = payload.splitlines()
    parsed_records: list[Dict] = []
    previous_line_digest: str | None = None
    for line_number, (line, raw_line) in enumerate(zip(lines, raw_lines), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MemorySidecarIncompleteError("memory_tomb", line_number) from exc
        if not isinstance(entry, dict):
            raise MemorySidecarIncompleteError("memory_tomb", line_number)
        stored_hash = entry.get("hash")
        if stored_hash is not None:
            if (not isinstance(stored_hash, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", stored_hash)):
                raise MemorySidecarIncompleteError("memory_tomb_digest_invalid", line_number)
            unhashed = dict(entry)
            unhashed.pop("hash", None)
            expected_hash = hashlib.sha256(json.dumps(unhashed, sort_keys=True,
                ensure_ascii=False).encode("utf-8")).hexdigest()
            if stored_hash != expected_hash:
                raise MemorySidecarIncompleteError("memory_tomb_digest_mismatch", line_number)
        if "previous_tomb_entry_digest" in entry:
            if entry.get("previous_tomb_entry_digest") != previous_line_digest:
                raise MemorySidecarIncompleteError("memory_tomb_predecessor_mismatch", line_number)
        parsed_records.append(entry)
        if raw_line:
            previous_line_digest = hashlib.sha256(raw_line).hexdigest()
    for entry in _collapse_tomb_operations(parsed_records):
        frag = entry.get("fragment", {})
        if tag and tag not in frag.get("tags", []):
            continue
        if reason and reason not in entry.get("reason", ""):
            continue
        ts = entry.get("time", "") or frag.get("timestamp", "")
        if date and not ts.startswith(date):
            continue
        out.append(entry)
    return out


def _estimate_importance(entry: dict) -> float:
    text = entry.get("text", "")
    score = 0.35
    word_count = len(text.split())
    score += min(0.2, word_count / 400.0)
    emotions = entry.get("emotions") or {}
    intensity = max(emotions.values()) if isinstance(emotions, dict) and emotions else 0.0
    score += min(0.2, intensity * 0.5)
    for tag in entry.get("tags", []):
        score += IMPORTANCE_TAG_BOOSTS.get(tag, 0.05)
    if entry.get("source") == "reflector":
        score += 0.05
    return max(0.05, min(1.0, score))


def _touch_fragment(fragment_id: str, *, accessed_at: datetime.datetime) -> None:
    data = _load_fragment(fragment_id)
    if not data:
        return
    data["access_count"] = data.get("access_count", 0) + 1
    data["last_accessed"] = accessed_at.isoformat()
    _write_fragment(fragment_id, data)


def _decay_factor(last_access: datetime.datetime, importance: float, now: datetime.datetime) -> float:
    age_days = max((now - last_access).total_seconds() / 86400.0, 0.0)
    if FORGETTING_HALF_LIFE_DAYS <= 0:
        return importance
    decay = math.exp(-age_days / FORGETTING_HALF_LIFE_DAYS)
    return importance * decay


def _parse_ts(value: str | None) -> datetime.datetime:
    if not value:
        return datetime.datetime.utcnow().replace(tzinfo=timezone.utc)
    try:
        dt = datetime.datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.datetime.utcnow().replace(tzinfo=timezone.utc)


@_legacy_mutation_operation
def append_memory(
    text: str,
    tags: List[str] | None = None,
    source: str = "unknown",
    emotions: Dict[str, float] | None = None,
    emotion_features: Dict[str, float] | None = None,
    emotion_breakdown: Dict[str, Dict[str, float]] | None = None,
    meta: Dict[str, object] | None = None,
    category: str | None = None,
    summary: str | None = None,
    importance: float | None = None,
    reflective: bool | None = None,
) -> str:
    if os.getenv("INCOGNITO") == "1":
        print("[MEMORY] Incognito mode enabled – skipping persistence")
        return "incognito"
    fragment_id = _hash(text + datetime.datetime.utcnow().isoformat())
    entry = {
        "id": fragment_id,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "tags": tags or [],
        "source": source,
        "text": text.strip(),
        "emotions": emotions or empty_emotion_vector(),
        "emotion_features": emotion_features or {},
        "emotion_breakdown": emotion_breakdown or {},
    }
    if meta:
        entry["meta"] = meta
    if summary:
        entry["summary"] = summary
    if category:
        entry["category"] = category
    if reflective is not None:
        entry["reflective"] = bool(reflective)
    if importance is not None:
        try:
            score = float(importance)
        except (TypeError, ValueError):
            score = _estimate_importance(entry)
        entry["importance"] = max(IMPORTANCE_FLOOR, min(1.0, score))
    else:
        entry["importance"] = _estimate_importance(entry)
    entry["access_count"] = 0
    entry["last_accessed"] = entry["timestamp"]
    vector = _vectorize(entry["text"])
    _authorize_legacy_mutation()
    with _INDEX_LOCK, _vector_index_transaction():
        if _load_fragment(fragment_id) is not None:
            raise MemorySidecarIncompleteError("legacy_raw_fragment_id_collision", 0)
        _write_fragment(fragment_id, entry)
        _update_vector_index_locked(entry, vector)
    em.add_emotion(entry["emotions"])
    print(f"[MEMORY] Appended fragment → {fragment_id} | tags={tags} | source={source}")
    return fragment_id


def _update_vector_index_locked(entry: Dict, vector: Vector) -> None:
    """Update derived metadata while the caller holds the cross-process lock."""
    records = [rec for rec in _load_index_records() if rec.get("id") != entry["id"]]
    record = {
        "id": entry["id"],
        "vector": vector,
        "snippet": entry["text"][:400],
        "importance": entry.get("importance", 0.3),
        "tags": entry.get("tags", []),
        "last_accessed": entry.get("last_accessed"),
        "access_count": entry.get("access_count", 0),
        "category": entry.get("category"),
        "summary": entry.get("summary"),
    }
    records.append(record)
    _save_index_records(records)
    print(f"[VECTOR] Index updated for {entry['id']}")


def _update_vector_index(entry: Dict) -> None:
    vector = _vectorize(entry["text"])
    with _INDEX_LOCK, _vector_index_transaction():
        _update_vector_index_locked(entry, vector)


def _bag_of_words(text: str) -> Dict[str, int]:
    words = text.lower().split()
    return {w: words.count(w) for w in set(words)}


def _embedding(text: str) -> List[float]:
    """Return a semantic embedding for ``text`` with deterministic fallback."""

    try:
        vectors = se.encode([text])
        if vectors:
            return vectors[0]
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[EMBEDDING WARNING] Falling back to hash embedding: {exc}")
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [b / 255.0 for b in digest[:64]]


def _vectorize(text: str) -> Vector:
    """Return either an embedding vector or bag-of-words mapping."""
    return _embedding(text) if USE_EMBEDDINGS else _bag_of_words(text)


def _cosine(a: Vector, b: Vector) -> float:
    """Cosine similarity for dict or list vectors."""
    if isinstance(a, dict) and isinstance(b, dict):
        dot = sum(a.get(t, 0) * b.get(t, 0) for t in a)
        mag = (sum(v * v for v in a.values()) ** 0.5) * (
            sum(v * v for v in b.values()) ** 0.5
        )
        return dot / mag if mag else 0.0
    # assume numeric vectors
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return dot / mag if mag else 0.0


def _load_index() -> List[Dict]:
    return list(_load_index_records())


@contextmanager
def _observation_log_lock():
    """Serialize one observation fragment/log publication across processes."""
    from sentientos.platform_fcntl import fcntl, require_flock
    require_flock()
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise PermissionError("observation_lock_custody_unsupported")
    root_fd = _open_legacy_memory_root(prepare_for_write=True)
    descriptor: int | None = None
    acquired = False
    try:
        flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(".observation-summary.lock", flags, 0o600, dir_fd=root_fd)
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077):
            raise PermissionError("observation_lock_custody_invalid")
        deadline = time.monotonic() + 5.0
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("observation_lock_timeout")
                time.sleep(0.01)
        yield
    finally:
        if descriptor is not None:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
        os.close(root_fd)


def _observation_digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_observation_records() -> List[Dict[str, Any]]:
    payload = _read_legacy_memory_file(OBSERVATION_LOG_PATH)
    if payload is None:
        return []
    records: List[Dict[str, Any]] = []
    identities: dict[str, Dict[str, Any]] = {}
    for line_number, line in enumerate(payload.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MemorySidecarIncompleteError("perception_observations", line_number) from exc
        if not isinstance(value, dict):
            raise MemorySidecarIncompleteError("perception_observations", line_number)
        stored_digest = value.get("observation_record_digest")
        if stored_digest is not None:
            unhashed = dict(value)
            unhashed.pop("observation_record_digest", None)
            if (not isinstance(stored_digest, str)
                    or stored_digest != _observation_digest(unhashed)):
                raise MemorySidecarIncompleteError("perception_observation_digest_mismatch", line_number)
        identity = value.get("observation_id")
        if isinstance(identity, str) and identity:
            prior = identities.get(identity)
            if prior is not None:
                if prior != value:
                    raise MemorySidecarIncompleteError("perception_observation_identity_conflict", line_number)
                continue
            identities[identity] = value
        records.append(value)
    return records


def _observation_fragment_link_status(record: Mapping[str, Any]) -> str:
    fragment_id = record.get("fragment_id")
    if not isinstance(fragment_id, str) or not fragment_id:
        return "missing_identity"
    try:
        raw = _read_legacy_raw_fragment(fragment_id + ".json")
    except (OSError, ValueError):
        return "custody_unavailable"
    if raw is None:
        return "missing_fragment"
    try:
        fragment = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return "malformed_fragment"
    if not isinstance(fragment, dict) or fragment.get("id") != fragment_id:
        return "identity_conflict"
    if fragment.get("text") != record.get("summary"):
        return "payload_conflict"
    meta = fragment.get("meta")
    if not isinstance(meta, dict):
        return "lineage_missing"
    stored_record = meta.get("observation_record")
    if stored_record is not None:
        return "verified" if stored_record == dict(record) else "lineage_conflict"
    historical = meta.get("observation")
    if (isinstance(historical, dict)
            and historical.get("observation_id") == record.get("observation_id")
            and historical.get("timestamp") == record.get("timestamp")):
        return "historical_identity_verified"
    return "lineage_missing"


def _observation_index_link_status(record: Mapping[str, Any],
                                   index_records: Sequence[Mapping[str, Any]]) -> str:
    fragment_id = record.get("fragment_id")
    if not isinstance(fragment_id, str) or not fragment_id:
        return "missing_identity"
    matches = [entry for entry in index_records if entry.get("id") == fragment_id]
    if not matches:
        return "missing_index_entry"
    if len(matches) != 1:
        return "duplicate_index_identity"
    entry = matches[0]
    if (entry.get("snippet") != str(record.get("summary", ""))[:400]
            or entry.get("tags") != record.get("tags", ["observation", "perception"])):
        return "index_payload_conflict"
    return "identity_and_excerpt_match"


def _write_observation_record(record: Mapping[str, Any]) -> None:
    with _open_legacy_memory_text(OBSERVATION_LOG_PATH, "a") as handle:
        handle.write(json.dumps(dict(record), ensure_ascii=False) + "\n")


def _rewrite_observation_records(records: Sequence[Mapping[str, Any]]) -> None:
    with _open_legacy_memory_text(OBSERVATION_LOG_PATH, "w") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), ensure_ascii=False) + "\n")


def _append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    """Append one bounded owner record under shared cross-process sidecar custody."""
    _authorize_legacy_mutation()
    with _observation_log_lock():
        with _open_legacy_memory_text(path, "a") as handle:
            handle.write(json.dumps(dict(record), ensure_ascii=False) + "\n")


def _parse_observation_timestamp(value: str | None) -> datetime.datetime:
    if not value:
        return datetime.datetime.utcnow().replace(tzinfo=timezone.utc)
    try:
        dt = datetime.datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.datetime.utcnow().replace(tzinfo=timezone.utc)


def _store_observation_summary_unlocked(summary: Mapping[str, Any]) -> Dict[str, Any]:
    """Persist one source-timestamped observation idempotently across interruption."""
    summary_text = str(summary.get("summary") or summary.get("text") or "").strip()
    if not summary_text:
        raise ValueError("Observation summary text is required")
    supplied_timestamp = summary.get("timestamp")
    timestamp = str(supplied_timestamp or datetime.datetime.utcnow().isoformat())
    source_payload = dict(summary)
    source_payload["timestamp"] = timestamp
    source_payload["summary"] = summary_text
    source_digest = _observation_digest(source_payload)
    observation_id = _hash(summary_text + timestamp)
    fragment_id = "observation-" + observation_id
    if os.getenv("INCOGNITO") == "1":
        return {"summary": summary_text, "timestamp": timestamp,
            "observation_id": observation_id, "fragment_id": None,
            "event_time_status": ("source_timestamp_supplied" if supplied_timestamp
                else "timestamp_generated_at_ingestion"),
            "persistence_status": "incognito_not_persisted"}

    previous = _load_observation_records()
    prior_records = [record for record in previous
        if record.get("observation_id") == observation_id]
    if len(prior_records) > 1:
        raise MemorySidecarIncompleteError("perception_observation_identity_conflict", 0)
    if prior_records:
        prior = prior_records[0]
        prior_source_digest = prior.get("observation_source_digest")
        if (prior.get("summary") != summary_text or prior.get("timestamp") != timestamp
                or (prior_source_digest is not None and prior_source_digest != source_digest)):
            raise MemorySidecarIncompleteError("perception_observation_identity_conflict", 0)
        prior_fragment_id = prior.get("fragment_id")
        if not isinstance(prior_fragment_id, str) or not prior_fragment_id:
            raise MemorySidecarIncompleteError("perception_observation_fragment_link_missing", 0)
        raw_fragment = _read_legacy_raw_fragment(prior_fragment_id + ".json")
        if raw_fragment is None:
            raise MemorySidecarIncompleteError("perception_observation_fragment_missing", 0)
        try:
            stored_fragment = json.loads(raw_fragment.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise MemorySidecarIncompleteError("perception_observation_fragment_malformed", 0) from exc
        meta = stored_fragment.get("meta") if isinstance(stored_fragment, dict) else None
        stored_observation = meta.get("observation_record") if isinstance(meta, dict) else None
        legacy_observation = meta.get("observation") if isinstance(meta, dict) else None
        if stored_observation is not None and stored_observation != prior:
            raise MemorySidecarIncompleteError("perception_observation_fragment_conflict", 0)
        if stored_observation is None and (
                not isinstance(legacy_observation, dict)
                or legacy_observation.get("observation_id") != observation_id
                or legacy_observation.get("timestamp") != timestamp):
            raise MemorySidecarIncompleteError("perception_observation_fragment_conflict", 0)
        if (not isinstance(stored_fragment, dict)
                or stored_fragment.get("id") != prior_fragment_id
                or stored_fragment.get("text") != summary_text):
            raise MemorySidecarIncompleteError("perception_observation_fragment_conflict", 0)
        return prior

    raw_existing = _read_legacy_raw_fragment(fragment_id + ".json")
    if raw_existing is not None:
        try:
            existing_fragment = json.loads(raw_existing.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise MemorySidecarIncompleteError("perception_observation_fragment_malformed", 0) from exc
        existing_meta = existing_fragment.get("meta") if isinstance(existing_fragment, dict) else None
        existing_record = (existing_meta.get("observation_record")
            if isinstance(existing_meta, dict) else None)
        if (not isinstance(existing_record, dict)
                or existing_record.get("observation_source_digest") != source_digest
                or existing_record.get("observation_id") != observation_id
                or existing_record.get("fragment_id") != fragment_id):
            raise MemorySidecarIncompleteError("perception_observation_fragment_conflict", 0)
        stored_digest = existing_record.get("observation_record_digest")
        unhashed = dict(existing_record)
        unhashed.pop("observation_record_digest", None)
        if stored_digest != _observation_digest(unhashed):
            raise MemorySidecarIncompleteError("perception_observation_fragment_digest_mismatch", 0)
        record = existing_record
        fragment = existing_fragment
    else:
        embedding = _embedding(summary_text)
        similarities = [
            _cosine(embedding, rec.get("embedding", []))
            for rec in previous if isinstance(rec.get("embedding"), list)
        ]
        novelty = max(0.0, min(1.0, 1.0 - (max(similarities) if similarities else 0.0)))
        record: Dict[str, Any] = dict(source_payload)
        record.setdefault("objects", [])
        record.setdefault("novel_objects", [])
        record.setdefault("transcripts", [])
        record.setdefault("screen", [])
        record.setdefault("emotions", {})
        record.setdefault("source_events", 0)
        record["novelty"] = novelty
        record["embedding"] = embedding
        record["observation_id"] = observation_id
        record["fragment_id"] = fragment_id
        record["observation_source_digest"] = source_digest
        record["event_time_status"] = ("source_timestamp_supplied" if supplied_timestamp
            else "timestamp_generated_at_ingestion")
        record["observation_record_digest"] = _observation_digest(record)
        tags = list(record.get("tags", ["observation", "perception"]))
        emotions = record.get("emotions") or empty_emotion_vector()
        meta_payload = {key: value for key, value in record.items() if key != "embedding"}
        fragment = {
            "id": fragment_id, "timestamp": timestamp, "tags": tags,
            "source": str(record.get("source", "perception_reasoner")),
            "text": summary_text, "emotions": emotions,
            "emotion_features": dict(record.get("emotion_features") or {}),
            "emotion_breakdown": dict(record.get("emotion_breakdown") or {}),
            "meta": {"observation": meta_payload, "observation_record": record},
        }
        fragment["importance"] = _estimate_importance(fragment)
        fragment["access_count"] = 0
        fragment["last_accessed"] = timestamp
        
    vector = _vectorize(fragment["text"])
    _write_fragment(fragment_id, fragment)
    _update_vector_index_locked(fragment, vector)
    _write_observation_record(record)
    emotions_to_add = record.get("emotions")
    if isinstance(emotions_to_add, dict):
        em.add_emotion(emotions_to_add)
    return record


@_legacy_mutation_operation
def store_observation_summary(summary: Mapping[str, Any]) -> Dict[str, Any]:
    if os.getenv("INCOGNITO") == "1":
        return _store_observation_summary_unlocked(summary)
    _authorize_legacy_mutation()
    with _observation_log_lock():
        with _INDEX_LOCK, _vector_index_transaction():
            return _store_observation_summary_unlocked(summary)

@_legacy_mutation_operation
def store_observation(observation: Mapping[str, Any]) -> Dict[str, Any]:
    """Persist a raw multimodal observation from ASR or screen OCR."""

    payload = dict(observation)
    modality = str(payload.get("modality", "unknown"))
    timestamp = payload.get("timestamp")
    if not timestamp:
        payload["timestamp"] = datetime.datetime.utcnow().isoformat()
    if modality == "audio":
        _append_jsonl(TRANSCRIPT_LOG_PATH, payload)
    elif modality == "screen":
        _append_jsonl(SCREEN_DIGEST_PATH, payload)
        text = str(payload.get("text", "")).strip()
        if text:
            policy = StoragePolicy(digest_dir=DIGEST_DIR, highlight_dir=HIGHLIGHT_DIR)
            _authorize_legacy_mutation()
            rotate_text_digests(policy, [text])
        snapshot = payload.get("highlight_image")
        if isinstance(snapshot, (bytes, bytearray)):
            policy = StoragePolicy(digest_dir=DIGEST_DIR, highlight_dir=HIGHLIGHT_DIR)
            timestamp_value = str(payload.get("timestamp"))
            name = f"highlight-{_hash(timestamp_value)}.png"
            _authorize_legacy_mutation()
            stash_highlight(policy, name, bytes(snapshot))
    else:
        _append_jsonl(OBSERVATION_LOG_PATH, payload)
    return payload


def _coerce_since(value: object) -> datetime.datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.datetime.fromisoformat(value)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            try:
                return datetime.datetime.fromtimestamp(float(value), tz=timezone.utc)
            except Exception:
                return None
    return None


def recent_observations(
    *,
    limit: int = 20,
    since: object | None = None,
    include_embeddings: bool = False,
) -> List[Dict[str, Any]]:
    """Return recent observation summaries, newest first."""

    records = _load_observation_records()
    since_dt = _coerce_since(since)
    if since_dt is not None:
        filtered: List[Dict[str, Any]] = []
        for rec in records:
            ts = _parse_observation_timestamp(str(rec.get("timestamp")))
            if ts >= since_dt:
                filtered.append(rec)
        records = filtered
    if limit > 0:
        records = records[-int(limit) :]
    records = list(reversed(records))
    try:
        index_records = _load_index_records()
        index_status = "available"
    except (MemorySidecarIncompleteError, PermissionError):
        index_records = []
        index_status = "incomplete_or_unavailable"
    sanitized: List[Dict[str, Any]] = []
    for rec in records:
        clean = dict(rec) if include_embeddings else {
            k: v for k, v in rec.items() if k != "embedding"}
        fragment_status = _observation_fragment_link_status(rec)
        clean["fragment_link_status"] = fragment_status
        clean["vector_index_link_status"] = (
            _observation_index_link_status(rec, index_records)
            if index_status == "available" else index_status)
        clean["evidence_custody_status"] = (
            "verified" if fragment_status in {"verified", "historical_identity_verified"}
            else "incomplete")
        sanitized.append(clean)
    return sanitized


@_legacy_mutation_operation
def update_novelty_score(observation_id: str, delta: float) -> bool:
    """Adjust a novelty annotation with digest-bound sidecar publication."""

    _authorize_legacy_mutation()
    with _observation_log_lock():
        records = _load_observation_records()
        updated = False
        for record in records:
            if record.get("observation_id") != observation_id:
                continue
            novelty = float(record.get("novelty", 0.0)) + float(delta)
            record["novelty"] = max(0.0, min(1.0, novelty))
            history = record.setdefault("novelty_history", [])
            history.append({
                "delta": float(delta),
                "timestamp": datetime.datetime.utcnow().isoformat(),
            })
            record.pop("observation_record_digest", None)
            record["observation_record_digest"] = _observation_digest(record)
            updated = True
            break
        if updated:
            _rewrite_observation_records(records)
        return updated


@_legacy_mutation_operation
def store_reflection(reflection: Mapping[str, Any]) -> Dict[str, Any]:
    """Persist one idempotent reflection and bind it to its raw fragment."""
    summary = str(reflection.get("insight_summary") or "").strip()
    if not summary:
        raise ValueError("Reflection insight summary required")
    timestamp = str(reflection.get("timestamp") or datetime.datetime.utcnow().isoformat())
    record = dict(reflection)
    record["timestamp"] = timestamp
    record.setdefault("goal_id", None)
    record.setdefault("observation_id", None)
    supplied_identity = record.get("reflection_id")
    reflection_id = str(supplied_identity) if supplied_identity else _hash(summary + timestamp)
    if not reflection_id or len(reflection_id) > 256:
        raise ValueError("Reflection identity is invalid")
    record["reflection_id"] = reflection_id
    fragment_id = "reflection-" + _hash(reflection_id)
    record["fragment_id"] = fragment_id
    record.pop("reflection_record_digest", None)
    record["reflection_record_digest"] = _observation_digest(record)

    if os.getenv("INCOGNITO") == "1":
        result = dict(record)
        result["fragment_id"] = None
        result.pop("reflection_record_digest", None)
        result["persistence_status"] = "incognito_not_persisted"
        return result

    fragment = {
        "id": fragment_id,
        "timestamp": timestamp,
        "tags": ["reflection", "curiosity"],
        "source": "curiosity_executor",
        "text": summary,
        "emotions": empty_emotion_vector(),
        "emotion_features": {},
        "emotion_breakdown": {},
        "meta": {"curiosity_reflection": record},
    }
    fragment["importance"] = _estimate_importance(fragment)
    fragment["access_count"] = 0
    fragment["last_accessed"] = timestamp
    vector = _vectorize(summary)

    _authorize_legacy_mutation()
    created = False
    with _INDEX_LOCK, _vector_index_transaction():
        prior_records = [
            item for item in iter_curiosity_reflections()
            if item.get("reflection_id") == reflection_id
        ]
        if len(prior_records) > 1:
            raise MemorySidecarIncompleteError("curiosity_reflection_identity_conflict", 0)
        if prior_records:
            prior = prior_records[0]
            if prior.get("reflection_record_digest") is not None:
                unhashed = dict(prior)
                stored_digest = unhashed.pop("reflection_record_digest")
                if stored_digest != _observation_digest(unhashed):
                    raise MemorySidecarIncompleteError(
                        "curiosity_reflection_digest_mismatch", 0)
            if prior != record:
                raise MemorySidecarIncompleteError(
                    "curiosity_reflection_replay_conflict", 0)
            stored_fragment = _load_fragment(fragment_id)
            if stored_fragment is None:
                raise MemorySidecarIncompleteError(
                    "curiosity_reflection_fragment_missing", 0)
            meta = stored_fragment.get("meta")
            if (stored_fragment.get("text") != summary
                    or not isinstance(meta, dict)
                    or meta.get("curiosity_reflection") != prior):
                raise MemorySidecarIncompleteError(
                    "curiosity_reflection_fragment_conflict", 0)
            _update_vector_index_locked(stored_fragment, vector)
            persisted = prior
        else:
            stored_fragment = _load_fragment(fragment_id)
            if stored_fragment is not None:
                meta = stored_fragment.get("meta")
                if (stored_fragment != fragment or stored_fragment.get("text") != summary
                        or not isinstance(meta, dict)
                        or meta.get("curiosity_reflection") != record):
                    raise MemorySidecarIncompleteError(
                        "curiosity_reflection_orphan_conflict", 0)
            else:
                _write_fragment(fragment_id, fragment)
            _update_vector_index_locked(fragment, vector)
            with _open_legacy_memory_text(CURIOSITY_REFLECTIONS_PATH, "a") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            persisted = record
            created = True

    if created:
        em.add_emotion(fragment["emotions"])
    observation_id = persisted.get("observation_id")
    if observation_id:
        _authorize_legacy_mutation()
        with _observation_log_lock():
            obs_records = _load_observation_records()
            changed = False
            for obs in obs_records:
                if obs.get("observation_id") != observation_id:
                    continue
                reflections = obs.setdefault("reflections", [])
                link = {
                    "reflection_id": reflection_id,
                    "summary": summary,
                    "timestamp": timestamp,
                }
                existing = [item for item in reflections
                    if isinstance(item, dict)
                    and item.get("reflection_id") == reflection_id]
                if existing and any(item != link for item in existing):
                    raise MemorySidecarIncompleteError(
                        "perception_reflection_link_conflict", 0)
                if not existing:
                    reflections.append(link)
                    obs.pop("observation_record_digest", None)
                    obs["observation_record_digest"] = _observation_digest(obs)
                    changed = True
                break
            if changed:
                _rewrite_observation_records(obs_records)
    return dict(persisted)


def iter_curiosity_reflections(limit: int | None = None) -> List[Dict[str, Any]]:
    payload = _read_legacy_memory_file(CURIOSITY_REFLECTIONS_PATH)
    if payload is None:
        return []
    lines = payload.decode("utf-8").splitlines()
    entries: List[Dict[str, Any]] = []
    parsed: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MemorySidecarIncompleteError("curiosity_reflections", line_number) from exc
        if not isinstance(value, dict):
            raise MemorySidecarIncompleteError("curiosity_reflections", line_number)
        stored_digest = value.get("reflection_record_digest")
        if stored_digest is not None:
            unhashed = dict(value)
            unhashed.pop("reflection_record_digest", None)
            if stored_digest != _observation_digest(unhashed):
                raise MemorySidecarIncompleteError(
                    "curiosity_reflection_digest_mismatch", line_number)
        parsed.append(value)
    if limit is not None:
        parsed = parsed[-max(0, limit):] if limit else []
    return parsed


def summarise_daily_insights(date: str | None = None) -> Dict[str, Any]:
    date = date or datetime.datetime.utcnow().date().isoformat()
    reflections = [
        entry
        for entry in iter_curiosity_reflections()
        if str(entry.get("timestamp", "")).startswith(date)
    ]
    if reflections:
        summary_text = " \n".join(
            f"- {entry.get('insight_summary', '')}" for entry in reflections
        )
    else:
        summary_text = "No new insights."
    digest = {"date": date, "count": len(reflections), "summary": summary_text}
    append_memory(
        f"Curiosity digest for {date}: {summary_text}",
        tags=["curiosity", "digest"],
        source="curiosity_loop",
        meta={"curiosity_digest": digest},
    )
    return digest


def latest_observation(*, include_embedding: bool = False) -> Dict[str, Any] | None:
    observations = recent_observations(limit=1, include_embeddings=include_embedding)
    return observations[0] if observations else None


REFLECTION_PHRASES = [
    "logsxt",
    "og.txt",
    "iogs",
    "telegram lumos logsxt",
    "as a helpful assistant",
    "please provide more context",
    "i will always be honest",
    "i do have access to that file",
    "likely in reference to",
    "conversation history",
    "united, and curl",
    "it looks like you're asking",
    "how can i assist you today",
    "1:38 pm",
    "re-confirming their ability",
    "smart quotes",
    "write(memory_manager_pat",
    "mnt/de",
    "with open(memory_manager_path",
]


def is_reflection_loop(snippet: str) -> bool:
    lowered = snippet.lower()
    return any(p in lowered for p in REFLECTION_PHRASES)


def _reconcile_vector_index_unlocked(
) -> tuple[list[dict], dict[str, dict], int, int, int]:
    """Reconcile derived retrieval rows from bounded owner raw fragments."""
    index = _load_index_records()
    index_by_id: dict[str, dict] = {}
    for row in index:
        fragment_id = row.get("id")
        if not isinstance(fragment_id, str) or not fragment_id:
            raise MemorySidecarIncompleteError("vector_index_identity_missing", 0)
        if fragment_id in index_by_id:
            raise MemorySidecarIncompleteError("vector_index_identity_conflict", 0)
        index_by_id[fragment_id] = row

    purged_ids: set[str] = set()
    pending_ids: set[str] = set()
    for entry in list_tomb():
        fragment = entry.get("fragment")
        fragment_id = fragment.get("id") if isinstance(fragment, dict) else None
        if not isinstance(fragment_id, str) or not fragment_id:
            continue
        state = entry.get("operation_state")
        if state == "incomplete":
            pending_ids.add(fragment_id)
        elif state == "deleted" or not entry.get("event_type"):
            purged_ids.add(fragment_id)

    raw_fragments: dict[str, dict] = {}
    for path in _legacy_fragment_paths():
        fragment = _load_fragment(path.stem)
        if fragment is None:
            raise MemorySidecarIncompleteError("legacy_raw_fragment_disappeared", 0)
        fragment_id = fragment["id"]
        if fragment_id in raw_fragments:
            raise MemorySidecarIncompleteError("legacy_raw_fragment_identity_conflict", 0)
        if fragment_id in purged_ids:
            raise MemorySidecarIncompleteError("purged_fragment_reappeared", 0)
        raw_fragments[fragment_id] = fragment

    reconciled: list[dict] = []
    sources: dict[str, dict] = {}
    added = 0
    removed = 0
    changed = False
    for fragment_id, source in raw_fragments.items():
        if fragment_id in pending_ids:
            if fragment_id in index_by_id:
                removed += 1
                changed = True
            continue
        source_text = source.get("text")
        if not isinstance(source_text, str):
            raise MemorySidecarIncompleteError("legacy_raw_fragment_text_invalid", 0)
        row = index_by_id.pop(fragment_id, None)
        if row is None:
            row = {
                "id": fragment_id,
                "vector": _vectorize(source_text),
                "snippet": source_text[:400],
                "importance": source.get("importance", 0.3),
                "tags": source.get("tags", []),
                "last_accessed": source.get("last_accessed"),
                "access_count": source.get("access_count", 0),
                "category": source.get("category"),
                "summary": source.get("summary"),
            }
            added += 1
            changed = True
        else:
            if row.get("snippet") != source_text[:400]:
                raise MemorySidecarIncompleteError("vector_index_fragment_payload_conflict", 0)
            if "tags" in row and row.get("tags") != source.get("tags", []):
                raise MemorySidecarIncompleteError("vector_index_fragment_tags_conflict", 0)
            for key, default in (
                ("importance", 0.3), ("access_count", 0),
                ("last_accessed", None), ("tags", []),
                ("category", None), ("summary", None),
            ):
                value = source.get(key, default)
                if row.get(key, default) != value:
                    row[key] = value
                    changed = True
        reconciled.append(row)
        sources[fragment_id] = source

    for fragment_id in index_by_id:
        if fragment_id in purged_ids or fragment_id in pending_ids:
            removed += 1
            changed = True
            continue
        raise MemorySidecarIncompleteError("vector_index_fragment_missing", 0)

    if len(reconciled) > 4096:
        raise MemorySidecarIncompleteError("vector_index_entry_bound_exceeded", 0)
    if changed:
        _save_index_records(reconciled)
    return reconciled, sources, added, removed, len(pending_ids)


def reconcile_vector_index() -> dict[str, int | str]:
    """Reconstruct derived vector metadata from authorized raw memory custody."""
    _authorize_legacy_mutation()
    with _INDEX_LOCK, _vector_index_transaction():
        _index, _sources, added, removed, pending = _reconcile_vector_index_unlocked()
    status = "reconciled" if pending == 0 else "reconciled_with_pending_purge"
    return {
        "status": status,
        "entries_added": added,
        "entries_removed": removed,
        "pending_purge_identities": pending,
    }


def _get_context_unlocked(query: str, k: int = 6) -> List[str]:
    index, source_fragments, _added, _removed, _pending = (
        _reconcile_vector_index_unlocked()
    )
    q_vec = _vectorize(query)
    now = datetime.datetime.utcnow().replace(tzinfo=timezone.utc)
    scored: List[tuple[float, dict]] = []
    for row in index:
        snippet = row.get("snippet", "")
        if not snippet or is_reflection_loop(snippet):
            continue
        score = _cosine(q_vec, row.get("vector", {}))
        if score <= 0:
            continue
        importance = float(row.get("importance", 0.3))
        access_count = int(row.get("access_count", 0))
        last_access = _parse_ts(row.get("last_accessed"))
        freshness = _decay_factor(last_access, importance, now)
        vote = score * (0.6 + 0.4 * freshness) * (1.0 + min(access_count, 10) * 0.05)
        scored.append((vote, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    top_rows = [row for _, row in scored[:k]]
    if not top_rows:
        return []

    snippets: List[str] = []
    seen: set[str] = set()
    for row in top_rows:
        frag_id = row.get("id")
        if not isinstance(frag_id, str) or not frag_id or frag_id in seen:
            continue
        seen.add(frag_id)
        source = source_fragments[frag_id]
        accessed_count = int(source.get("access_count", 0)) + 1
        accessed_at = now.isoformat()
        source["access_count"] = accessed_count
        source["last_accessed"] = accessed_at
        row["access_count"] = accessed_count
        row["last_accessed"] = accessed_at
        _write_fragment(frag_id, source)
        snippets.append(str(source.get("text", ""))[:400])

    if index:
        _save_index_records(index)

    return [snippet for snippet in snippets if snippet][:k]



def get_context(query: str, k: int = 6) -> List[str]:
    _authorize_legacy_mutation()
    with _INDEX_LOCK, _vector_index_transaction():
        return _get_context_unlocked(query, k)

def search_by_tags(tags: List[str], limit: int = 5) -> list[dict]:
    """Return recent memory fragments matching all ``tags``.

    Results are ordered from newest to oldest and truncated to ``limit``.
    """
    files = list(_legacy_fragment_paths())
    entries = []
    for fp in files:
        data = _load_fragment(fp.stem)
        if data is None:
            continue
        ts = data.get("timestamp")
        entries.append((ts, data))
    entries.sort(key=lambda x: x[0] or "", reverse=True)
    results: list[dict] = []
    wanted = set(tags)
    for _, data in entries:
        entry_tags = set(data.get("tags", []))
        if not wanted.issubset(entry_tags):
            continue
        results.append(data)
        if len(results) >= limit:
            break
    return results


# Compatibility alias for legacy bridges
write_mem = append_memory


def _purge_memory_unlocked(
    max_age_days: Optional[int] = None,
    max_files: Optional[int] = None,
    *,
    requestor: str = "system",
    reason: str = "",
) -> None:
    """Delete old fragments by age or limit total count.

    Purged fragments are archived in the memory tomb.
    """
    # Validate the derived index before any deletion.  The caller holds the
    # shared index transaction across this complete raw/index mutation.
    index_records = _load_index_records()
    removed_ids: set[str] = set()
    tomb_records = list_tomb()
    pending_purge_ids = {
        str(fragment.get("id"))
        for record in tomb_records
        if record.get("operation_state") == "incomplete"
        and isinstance((fragment := record.get("fragment")), dict)
        and fragment.get("id")
    }
    files = list(_legacy_fragment_paths())
    entries: List[tuple[datetime.datetime, Path, dict]] = []
    for f in files:
        data = _load_fragment(f.stem)
        if data is None:
            continue
        ts = _parse_ts(data.get("timestamp")).astimezone(timezone.utc)
        entries.append((ts, f, data))
    entries.sort(key=lambda x: x[0])

    now = datetime.datetime.utcnow()
    removed = 0
    removed_names: set[str] = set()
    if max_age_days is not None:
        cutoff = now - datetime.timedelta(days=max_age_days)
        for ts, fp, data in entries:
            if ts < cutoff and str(data.get("id", "")) not in pending_purge_ids:
                operation_id = "purge-" + secrets.token_hex(16)
                _append_tomb({"event_type": "purge_intent", "operation_id": operation_id,
                    "fragment": data, "requestor": requestor,
                    "time": datetime.datetime.utcnow().isoformat(), "reason": reason})
                deleted = _unlink_legacy_raw_fragment(fp.stem)
                _append_tomb({"event_type": "purge_result", "operation_id": operation_id,
                    "operation_state": "deleted" if deleted else "not_deleted",
                    "time": datetime.datetime.utcnow().isoformat()})
                if deleted:
                    removed_names.add(fp.name)
                    removed_ids.add(str(data.get("id", "")))
                    removed += 1
    if max_files is not None and len(entries) - removed > max_files:
        remaining = [e for e in entries if e[1].name not in removed_names]
        excess = len(remaining) - max_files
        candidates = [e for e in remaining
            if str(e[2].get("id", "")) not in pending_purge_ids]
        for ts, fp, data in candidates[:excess]:
            operation_id = "purge-" + secrets.token_hex(16)
            _append_tomb({"event_type": "purge_intent", "operation_id": operation_id,
                "fragment": data, "requestor": requestor,
                "time": datetime.datetime.utcnow().isoformat(), "reason": reason})
            deleted = _unlink_legacy_raw_fragment(fp.stem)
            _append_tomb({"event_type": "purge_result", "operation_id": operation_id,
                "operation_state": "deleted" if deleted else "not_deleted",
                "time": datetime.datetime.utcnow().isoformat()})
            if deleted:
                removed_names.add(fp.name)
                removed_ids.add(str(data.get("id", "")))
                removed += 1
    if removed_ids:
        _save_index_records([
            record for record in index_records
            if str(record.get("id", "")) not in removed_ids
        ])
    if removed:
        print(f"[PURGE] Removed {removed} old memory fragments")

@_legacy_mutation_operation
def purge_memory(
    max_age_days: Optional[int] = None,
    max_files: Optional[int] = None,
    *,
    requestor: str = "system",
    reason: str = "",
) -> None:
    """Purge memory under the same cross-process lock as index consumers."""
    _authorize_legacy_mutation()
    with _INDEX_LOCK, _vector_index_transaction():
        _purge_memory_unlocked(
            max_age_days=max_age_days, max_files=max_files,
            requestor=requestor, reason=reason,
        )



def _write_topic_summaries(entries: Sequence[dict]) -> None:
    topics: Dict[str, List[str]] = {}
    for data in entries:
        tags = data.get("tags", []) or []
        if not tags:
            continue
        ts = data.get("timestamp", "")
        snippet = data.get("text", "").strip().replace("\n", " ")
        for tag in tags:
            topics.setdefault(tag, []).append(f"[{ts}] {snippet}")

    for tag, lines in topics.items():
        if not tag:
            continue
        out = TOPIC_PATH / f"{tag}.md"
        with _open_legacy_memory_text(out, "w") as f:
            f.write(f"# {tag} memory capsule\n\n")
            for line in lines[-200:]:  # keep recent history manageable
                f.write(f"- {line}\n")
        print(f"[SUMMARY] Topic capsule updated → {out}")


def _extract_session_id(entry: dict) -> str | None:
    meta = entry.get("meta")
    if isinstance(meta, dict):
        for key in ("session", "conversation", "thread", "goal"):
            value = meta.get(key)
            if value:
                return str(value)
    for tag in entry.get("tags", []) or []:
        if ":" in tag:
            prefix, value = tag.split(":", 1)
            if prefix in {"session", "conversation", "goal"} and value:
                return value
    goal_id = entry.get("goal_id")
    if goal_id:
        return str(goal_id)
    return None


def _write_session_digest(session_id: str, entries: Sequence[dict]) -> None:
    if not session_id or not entries:
        return
    entries = sorted(entries, key=lambda item: item.get("timestamp", ""))
    start = entries[0].get("timestamp", "")
    end = entries[-1].get("timestamp", "")
    tags = collections.Counter()
    highlights: list[str] = []
    for entry in entries[-10:]:
        tags.update(entry.get("tags", []) or [])
        text = (entry.get("summary") or entry.get("text", "")).strip().replace("\n", " ")
        if text:
            highlights.append(text[:240])

    common_tags = ", ".join(tag for tag, _ in tags.most_common(6)) or "(none)"
    out = SESSION_PATH / f"{session_id}.md"
    with _open_legacy_memory_text(out, "w") as handle:
        handle.write(f"# Session {session_id}\n\n")
        handle.write(f"* timeframe: {start} → {end}\n")
        handle.write(f"* entries: {len(entries)}\n")
        handle.write(f"* dominant tags: {common_tags}\n\n")
        handle.write("## Highlights\n")
        for bullet in highlights:
            handle.write(f"- {bullet}\n")
    print(f"[SUMMARY] Session digest updated → {out}")


def _write_turn_summaries(entries: Sequence[dict]) -> None:
    sessions: dict[str, list[dict]] = {}
    for entry in entries:
        session_id = _extract_session_id(entry)
        if not session_id:
            continue
        sessions.setdefault(session_id, []).append(entry)

    for session_id, session_entries in sessions.items():
        session_entries.sort(key=lambda item: item.get("timestamp", ""))
        turns: list[dict] = []
        for item in session_entries[-50:]:
            text = (item.get("summary") or item.get("text", "")).strip().replace("\n", " ")
            turns.append(
                {
                    "timestamp": item.get("timestamp"),
                    "summary": text[:280],
                    "importance": item.get("importance"),
                    "tags": item.get("tags", []),
                }
            )
        out = TURN_PATH / f"{session_id}.json"
        with _open_legacy_memory_text(out, "w") as handle:
            handle.write(json.dumps(turns, ensure_ascii=False, indent=2))
        _write_session_digest(session_id, session_entries)
        print(f"[SUMMARY] Turn capsule updated → {out}")


@_legacy_mutation_operation
def summarize_memory() -> None:
    """Concatenate daily fragments into summary files and topic capsules."""

    summaries: Dict[str, List[str]] = {}
    entries: List[dict] = []
    for fp in _legacy_fragment_paths():
        data = _load_fragment(fp.stem)
        if data is None:
            continue
        ts = data.get("timestamp")
        if not ts:
            continue
        entries.append(data)
        day = ts.split("T")[0]
        snippet = data.get("text", "").strip().replace("\n", " ")
        summaries.setdefault(day, []).append(f"[{ts}] {snippet}")

    for day, lines in summaries.items():
        out = DAY_PATH / f"{day}.txt"
        with _open_legacy_memory_text(out, "a") as f:
            for line in lines:
                f.write(line + "\n")
        print(f"[SUMMARY] Updated {out}")

    _write_topic_summaries(entries)
    _write_turn_summaries(entries)


def _apply_forgetting_curve_unlocked(
    *, requestor: str = "curator", reason: str = "forgetting_curve"
) -> int:
    """Apply decay with recoverable, non-replayed deletion custody."""
    now = datetime.datetime.utcnow().replace(tzinfo=timezone.utc)
    removed = 0
    kept_records: list[dict] = []
    pending_purge_ids = {
        str(fragment.get("id"))
        for entry in list_tomb()
        if entry.get("operation_state") == "incomplete"
        and isinstance((fragment := entry.get("fragment")), dict)
        and fragment.get("id")
    }

    for record in _load_index_records():
        fragment_id = record.get("id")
        if not fragment_id:
            continue
        if str(fragment_id) in pending_purge_ids:
            # An interrupted deletion remains visible as incomplete custody.
            # Do not issue a second deletion under a new operation identity.
            kept_records.append(record)
            continue
        data = _load_fragment(fragment_id)
        if not data:
            continue
        if data.get("pinned"):
            kept_records.append(record)
            continue

        importance = float(data.get("importance", 0.3))
        access_count = int(data.get("access_count", 0))
        importance = max(importance, min(0.6, access_count * 0.05))
        last_access = _parse_ts(data.get("last_accessed"))
        retention = _decay_factor(last_access, importance, now)

        if retention < IMPORTANCE_FLOOR:
            operation_id = "purge-" + secrets.token_hex(16)
            _append_tomb({
                "event_type": "purge_intent", "operation_id": operation_id,
                "fragment": data, "requestor": requestor,
                "time": now.isoformat(), "reason": reason,
            })
            deleted = _unlink_legacy_raw_fragment(fragment_id)
            _append_tomb({
                "event_type": "purge_result", "operation_id": operation_id,
                "operation_state": "deleted" if deleted else "not_deleted",
                "time": datetime.datetime.utcnow().isoformat(),
            })
            if deleted:
                removed += 1
        else:
            data["importance"] = min(1.0, retention + 0.05 * importance)
            _write_fragment(fragment_id, data)
            record["importance"] = data["importance"]
            record["last_accessed"] = data.get("last_accessed")
            record["access_count"] = data.get("access_count", 0)
            kept_records.append(record)

    # Publish through the held-root owner even when empty; avoid ambient exists
    # checks and Path.unlink against the replaceable index path.
    _save_index_records(kept_records)

    if removed:
        print(f"[FORGET] Archived {removed} stale fragments")
    return removed



@_legacy_mutation_operation
def apply_forgetting_curve(*, requestor: str = "curator",
                           reason: str = "forgetting_curve") -> int:
    _authorize_legacy_mutation()
    with _INDEX_LOCK, _vector_index_transaction():
        return _apply_forgetting_curve_unlocked(requestor=requestor, reason=reason)

@_legacy_mutation_operation
def curate_memory() -> dict[str, Any]:
    """Run summarisation and forgetting maintenance cycle."""

    removed = apply_forgetting_curve()
    summarize_memory()
    return {"removed": removed}


def _reflection_headline(summary: Mapping[str, object]) -> str:
    reason = str(summary.get("reason") or "").strip()
    if reason:
        base = reason
    else:
        status = str(summary.get("status") or "").strip()
        base = f"Status: {status}" if status else "Reflection recorded"
    plugin = str(summary.get("plugin") or "").strip()
    if plugin and not base.lower().startswith(plugin.lower()):
        return f"[{plugin}] {base}"
    return base


def _reflection_importance(status: str) -> float:
    status = status.lower()
    if status == "completed":
        return 0.7
    if status in {"failed", "blocked"}:
        return 0.45
    if status in {"needs_review", "stuck"}:
        return 0.5
    if status:
        return 0.4
    return 0.35


@_legacy_mutation_operation
def save_reflection(
    *,
    parent: str,
    intent: dict,
    result: dict | None,
    reason: str,
    next_step: str | None = None,
    user: str = "",
    plugin: str = "",
) -> str:
    """Persist a structured reflection entry.

    Parameters
    ----------
    parent: id of the action log this reflection relates to
    intent: the original action intent
    result: action result if any
    reason: why the action was attempted or failed
    next_step: optional proposed follow-up
    """

    reflection = {
        "parent": parent,
        "intent": intent,
        "result": result,
        "reason": reason,
        "next": next_step,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "user": user,
        "plugin": plugin,
    }
    fragment_id = append_memory(
        json.dumps(reflection, ensure_ascii=False),
        tags=["reflection", plugin],
        source="reflector",
    )

    status = ""
    result_summary: dict[str, object] | str | None = None
    if isinstance(result, Mapping):
        status = str(result.get("status") or "")
        result_summary = {
            key: result.get(key)
            for key in ("status", "error", "critique_step", "details")
            if key in result and result.get(key) is not None
        }
    elif result is not None:
        result_summary = str(result)[:160]

    intent_summary: dict[str, object] | str | None = None
    if isinstance(intent, Mapping):
        subset = {
            key: intent.get(key)
            for key in ("type", "summary", "action", "skill")
            if intent.get(key)
        }
        text_hint = intent.get("text") or intent.get("description")
        if text_hint and "text" not in subset:
            subset["text"] = str(text_hint)[:160]
        if subset:
            intent_summary = subset
    elif intent:
        intent_summary = str(intent)[:160]

    summary_payload: dict[str, object] = {
        "reflection_id": fragment_id,
        "parent": parent,
        "plugin": plugin or "core",
        "user": user or None,
        "timestamp": reflection["timestamp"],
        "reason": reason,
        "status": status or None,
    }
    if next_step:
        summary_payload["next"] = next_step
    if intent_summary:
        summary_payload["intent"] = intent_summary
    if result_summary:
        summary_payload["result"] = result_summary

    summary_payload["importance"] = _reflection_importance(status)
    summary_payload["headline"] = _reflection_headline(summary_payload)

    if fragment_id != "incognito":
        _notify_reflection_listeners(summary_payload)

    return fragment_id


def recent_reflections(
    limit: int = 10,
    *,
    plugin: str | None = None,
    user: str | None = None,
    failures_only: bool = False,
) -> list[dict]:
    """Return recent reflection entries with optional filters."""

    files = sorted(_legacy_fragment_paths(), reverse=True)
    out: list[dict] = []
    for fp in files:
        data = _load_fragment(fp.stem)
        if data is None:
            continue
        if "reflection" not in data.get("tags", []):
            continue
        try:
            entry = json.loads(data.get("text", "{}"))
        except Exception:
            continue
        if plugin and entry.get("plugin") != plugin:
            continue
        if user and entry.get("user") != user:
            continue
        if failures_only and entry.get("result") is not None:
            continue
        entry["id"] = data.get("id")
        out.append(entry)
        if len(out) >= limit:
            break
    return out


def recent_patches(limit: int = 5) -> list[str]:
    """Return recent self-improvement patch notes."""
    files = sorted(_legacy_fragment_paths(), reverse=True)
    out: list[str] = []
    for fp in files:
        data = _load_fragment(fp.stem)
        if data is None:
            continue
        if "self_patch" not in data.get("tags", []):
            continue
        out.append(data.get("text", ""))
        if len(out) >= limit:
            break
    return out


def recent_escalations(limit: int = 5) -> list[str]:
    """Return recent escalation log snippets."""
    files = sorted(_legacy_fragment_paths(), reverse=True)
    out: list[str] = []
    for fp in files:
        data = _load_fragment(fp.stem)
        if data is None:
            continue
        if "escalation" not in data.get("tags", []):
            continue
        out.append(data.get("text", ""))
        if len(out) >= limit:
            break
    return out


# --- Goal management -------------------------------------------------------

def _load_goals() -> list[dict]:
    payload = _read_legacy_memory_file(GOALS_PATH)
    if payload is not None:
        try:
            return json.loads(payload.decode("utf-8"))
        except Exception:
            return []
    return []


def _save_goals(goals: list[dict]) -> None:
    with _open_legacy_memory_text(GOALS_PATH, "w") as handle:
        handle.write(json.dumps(goals, ensure_ascii=False, indent=2))


@_legacy_mutation_operation
def add_goal(
    text: str,
    *,
    intent: dict | None = None,
    user: str = "",
    priority: int = 1,
    deadline: str | None = None,
    schedule_at: str | None = None,
) -> dict:
    """Create and persist a new goal entry."""

    goal_id = _hash(text + datetime.datetime.utcnow().isoformat())
    goal = {
        "id": goal_id,
        "text": text,
        "intent": intent or {},
        "created": datetime.datetime.utcnow().isoformat(),
        "status": "open",
        "user": user,
        "priority": priority,
        "deadline": deadline,
        "schedule_at": schedule_at,
    }
    goals = _load_goals()
    goals.append(goal)
    _save_goals(goals)
    from notification import send as notify  # local import to avoid cycle
    notify("goal_created", {"id": goal_id, "text": text})
    return goal


@_legacy_mutation_operation
def save_goal(goal: dict) -> None:
    goals = _load_goals()
    for i, g in enumerate(goals):
        if g.get("id") == goal.get("id"):
            goals[i] = goal
            break
    else:
        goals.append(goal)
    _save_goals(goals)


@_legacy_mutation_operation
def delete_goal(goal_id: str) -> None:
    """Remove a goal by id."""
    goals = [g for g in _load_goals() if g.get("id") != goal_id]
    _save_goals(goals)


def get_goal(goal_id: str) -> dict | None:
    for g in _load_goals():
        if g.get("id") == goal_id:
            return g
    return None


def next_goal() -> dict | None:
    """Return the next due goal by priority and schedule."""
    goals = get_goals(open_only=False)
    now = datetime.datetime.utcnow()
    due: list[dict] = []
    for g in goals:
        if g.get("status") in {"completed", "stuck"}:
            continue
        at = g.get("schedule_at")
        if at:
            try:
                if datetime.datetime.fromisoformat(at) > now:
                    continue
            except Exception:
                pass
        due.append(g)
    due.sort(
        key=lambda x: (
            -int(x.get("priority", 1)),
            x.get("deadline") or x.get("created"),
        )
    )
    return due[0] if due else None


def get_goals(*, open_only: bool = False) -> list[dict]:
    goals = _load_goals()
    if open_only:
        goals = [g for g in goals if g.get("status") == "open"]
    goals.sort(
        key=lambda x: (
            -int(x.get("priority", 1)),
            x.get("created", ""),
        )
    )
    return goals
