"""Descriptor-bound POSIX file custody for bounded runtime records.

These helpers provide filesystem integrity only. Callers retain semantic
validation, identity, authorization, and recovery policy.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path


class PrivateFileCustodyError(ValueError):
    """A path, file, or publication did not satisfy the private custody contract."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def open_private_directory(path: Path, *, create: bool) -> int:
    """Traverse an absolute directory path without following symlinks."""
    if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")
            or os.open not in os.supports_dir_fd or os.mkdir not in os.supports_dir_fd):
        raise PrivateFileCustodyError("directory_custody_unsupported")
    absolute = Path(os.path.abspath(os.fspath(path)))
    components = absolute.parts[1:]
    if not components:
        raise PrivateFileCustodyError("directory_root_invalid")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(os.sep, flags)
    except OSError as exc:
        raise PrivateFileCustodyError("directory_root_unavailable") from exc
    try:
        for index, component in enumerate(components):
            if component in {"", ".", ".."}:
                raise PrivateFileCustodyError("directory_root_invalid")
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(component, flags, dir_fd=descriptor)
            metadata = os.fstat(child)
            final = index == len(components) - 1
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(child)
                raise PrivateFileCustodyError("directory_root_invalid")
            if final:
                if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
                    os.close(child)
                    raise PrivateFileCustodyError("directory_permissions_invalid")
            elif metadata.st_mode & 0o022 and not metadata.st_mode & stat.S_ISVTX:
                os.close(child)
                raise PrivateFileCustodyError("directory_path_permissions_invalid")
            os.close(descriptor)
            descriptor = child
        result = descriptor
        descriptor = -1
        return result
    except PrivateFileCustodyError:
        raise
    except FileNotFoundError as exc:
        raise PrivateFileCustodyError("directory_root_missing") from exc
    except OSError as exc:
        raise PrivateFileCustodyError("directory_root_unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_private_file_at(directory_fd: int, name: str, *, max_bytes: int,
                         require_private_mode: bool = True) -> bytes:
    """Read one stable, bounded, owner-controlled file relative to a held directory."""
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise PrivateFileCustodyError("file_path_invalid")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
        before = os.fstat(descriptor)
        invalid_mode = bool(before.st_mode & (0o077 if require_private_mode else 0o022))
        if (not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes
                or before.st_nlink != 1 or before.st_uid != os.geteuid() or invalid_mode):
            raise PrivateFileCustodyError("file_unbounded_or_not_private")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        if (len(data) != before.st_size or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns
                or after.st_dev != before.st_dev or after.st_ino != before.st_ino):
            raise PrivateFileCustodyError("file_changed_during_read")
        return data
    except PrivateFileCustodyError:
        raise
    except FileNotFoundError as exc:
        raise PrivateFileCustodyError("file_missing") from exc
    except OSError as exc:
        raise PrivateFileCustodyError("file_unavailable") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def list_bounded_json_names_at(directory_fd: int, *, max_entries: int,
                                max_directory_entries: int | None = None) -> tuple[str, ...]:
    """Enumerate bounded JSON names from one already-held directory descriptor."""
    if (not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries < 1):
        raise PrivateFileCustodyError("directory_entry_bound_invalid")
    if max_directory_entries is None:
        max_directory_entries = max_entries + 1024
    if (not isinstance(max_directory_entries, int) or isinstance(max_directory_entries, bool)
            or max_directory_entries < max_entries):
        raise PrivateFileCustodyError("directory_entry_bound_invalid")
    names: list[str] = []
    total_entries = 0
    try:
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                total_entries += 1
                if total_entries > max_directory_entries:
                    raise PrivateFileCustodyError("directory_entry_limit_exceeded")
                name = entry.name
                if not isinstance(name, str) or name in {"", ".", ".."} or "/" in name or "\\" in name:
                    raise PrivateFileCustodyError("directory_entry_name_invalid")
                if name.endswith(".json"):
                    names.append(name)
                    if len(names) > max_entries:
                        raise PrivateFileCustodyError("directory_file_count_limit_exceeded")
    except PrivateFileCustodyError:
        raise
    except OSError as exc:
        raise PrivateFileCustodyError("directory_entries_unavailable") from exc
    return tuple(sorted(names))


def _write_bytes(path: Path, data: bytes, *, max_bytes: int, immutable: bool,
                 collision_code: str, report_replace_durability: bool = False) -> bool:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise PrivateFileCustodyError("publication_unsupported")
    if not isinstance(data, bytes) or len(data) > max_bytes:
        raise PrivateFileCustodyError("payload_size_limit_exceeded")
    directory_fd = open_private_directory(path.parent, create=True)
    temporary_name = ".pending-" + os.urandom(16).hex()
    descriptor: int | None = None
    created = False
    durability_uncertain = False
    replaced = False
    try:
        descriptor = os.open(temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            0o600, dir_fd=directory_fd)
        created = True
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise PrivateFileCustodyError("publication_short_write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        if immutable:
            try:
                os.link(temporary_name, path.name, src_dir_fd=directory_fd,
                        dst_dir_fd=directory_fd, follow_symlinks=False)
            except FileExistsError:
                existing = read_private_file_at(directory_fd, path.name,
                    max_bytes=max_bytes, require_private_mode=True)
                if existing != data:
                    raise PrivateFileCustodyError(collision_code)
        else:
            os.replace(temporary_name, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            replaced = True
        try:
            os.fsync(directory_fd)
        except OSError:
            if report_replace_durability and not immutable:
                # Atomic replacement is already visible. Tell the owner to
                # retain its candidate while reporting durability uncertainty.
                durability_uncertain = True
            else:
                raise
    except PrivateFileCustodyError:
        raise
    except OSError as exc:
        raise PrivateFileCustodyError("publication_unavailable") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except OSError:
                pass
        try:
            os.close(directory_fd)
        except OSError as exc:
            if report_replace_durability and not immutable and replaced:
                # close(2) can fail after replacement just like directory fsync.
                # The new bytes are already visible, so tell the owner to retain
                # the candidate and report durability uncertainty.
                durability_uncertain = True
            else:
                raise PrivateFileCustodyError("directory_close_unavailable") from exc
    return not durability_uncertain


def publish_immutable_bytes(path: Path, data: bytes, *, max_bytes: int,
                            collision_code: str = "immutable_content_conflict") -> None:
    """Create once; accept retries only if the existing bytes are identical."""
    _write_bytes(path, data, max_bytes=max_bytes, immutable=True, collision_code=collision_code)


def replace_private_bytes(path: Path, data: bytes, *, max_bytes: int) -> None:
    """Atomically replace a mutable snapshot using a held private directory."""
    _write_bytes(path, data, max_bytes=max_bytes, immutable=False,
                 collision_code="unused_mutable_collision")


def replace_private_bytes_with_status(path: Path, data: bytes, *, max_bytes: int) -> bool:
    """Return False only when replace succeeded but directory durability is uncertain."""
    return _write_bytes(path, data, max_bytes=max_bytes, immutable=False,
        collision_code="unused_mutable_collision", report_replace_durability=True)
