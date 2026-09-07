"""Authenticated, installation-scoped durable state filesystem substrate.

This module supplies storage mechanics only.  An installation identity and a state
handle are not capabilities and confer no model-catalog deployment authority.

The strong implementation currently requires POSIX descriptor-relative opens,
``O_NOFOLLOW``, kernel ``flock``, ``fsync``, and same-directory ``os.replace``.
Other platforms fail closed rather than silently weakening the durability promise.
"""
from __future__ import annotations

import os
import re
import stat
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised by platform-contract tests
    fcntl = None  # type: ignore[assignment]

INSTALLATION_STATE_SCHEMA = "sentientos.installation_state:v1"
INSTALLATIONS_DIRECTORY = "installations"
STATE_DIRECTORY = "state"
_IDENTITY_RE = re.compile(r"[a-z][a-z0-9-]{0,62}\Z")
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
)


class InstallationStateError(RuntimeError):
    """A state security, type, lock, or durability invariant was not met."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, order=True)
class InstallationIdentity:
    """Normalized installation identity; identity alone grants no authority."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.lower()
        if (
            normalized != self.value
            or not _IDENTITY_RE.fullmatch(normalized)
            or normalized in {".", ".."}
            or normalized.rstrip(" .").split(".", 1)[0] in _WINDOWS_RESERVED
        ):
            raise ValueError("invalid_installation_identity")

    @classmethod
    def parse(cls, value: str) -> "InstallationIdentity":
        if not isinstance(value, str):
            raise ValueError("invalid_installation_identity")
        return cls(value.lower())

    def to_json(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class StateRelativePath:
    """Validated platform-independent relative identity beneath a state handle."""

    parts: tuple[str, ...]

    @classmethod
    def parse(cls, value: str) -> "StateRelativePath":
        if not isinstance(value, str) or not value or "\\" in value:
            raise ValueError("invalid_state_relative_path")
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("invalid_state_relative_path")
        if str(path) != value or any("\x00" in part for part in path.parts):
            raise ValueError("invalid_state_relative_path")
        return cls(tuple(path.parts))

    def __str__(self) -> str:
        return "/".join(self.parts)


@dataclass(frozen=True)
class InstallationStateObject:
    """An object identity bound to one authenticated installation handle."""

    _handle: "InstallationStateHandle"
    relative: StateRelativePath

    @property
    def path(self) -> Path:
        return self._handle.root.joinpath(*self.relative.parts)

    def child(self, name: str) -> "InstallationStateObject":
        child = StateRelativePath.parse(name)
        if len(child.parts) != 1:
            raise ValueError("state_child_must_be_one_component")
        return InstallationStateObject(self._handle, StateRelativePath(self.relative.parts + child.parts))


def _canonical_machine_state_base() -> Path:
    """Return the fixed machine-state base; never consult cwd or environment."""
    if sys.platform == "win32":
        return Path(r"C:\ProgramData\SentientOS\durable-state")
    if sys.platform == "darwin":
        return Path("/Library/Application Support/SentientOS/durable-state")
    return Path("/var/lib/sentientos/durable-state")


class InstallationStateRegistry:
    """Trusted installation machinery mapping identities to derived state roots.

    Production callers can only obtain the machine registry.  The private test
    constructor is deliberately unavailable from catalog custody APIs.
    """

    __slots__ = ("_base", "_test_only")

    def __init__(self, base: Path, *, _test_only: bool = False) -> None:
        if not _test_only or not base.is_absolute():
            raise InstallationStateError("registry_construction_forbidden")
        self._base = base
        self._test_only = True

    @classmethod
    def system(cls) -> "InstallationStateRegistry":
        instance = object.__new__(cls)
        instance._base = _canonical_machine_state_base()
        instance._test_only = False
        return instance

    @classmethod
    def _for_testing(cls, base: Path) -> "InstallationStateRegistry":
        return cls(base, _test_only=True)

    def state_root_for(self, identity: InstallationIdentity) -> Path:
        return self._base / INSTALLATIONS_DIRECTORY / identity.value / STATE_DIRECTORY

    def open(self, identity: InstallationIdentity, *, create: bool = False) -> "InstallationStateHandle":
        _require_platform_contract()
        root = self.state_root_for(identity)
        if create:
            _secure_mkdir_chain(self._base, (INSTALLATIONS_DIRECTORY, identity.value, STATE_DIRECTORY))
        _verify_absolute_directory_chain(root)
        return InstallationStateHandle._authenticated(identity, root, self)


@dataclass(frozen=True, init=False)
class InstallationStateHandle:
    """Authenticated identity/root binding issued only by a canonical registry."""

    identity: InstallationIdentity
    root: Path
    _registry: InstallationStateRegistry

    @classmethod
    def _authenticated(cls, identity: InstallationIdentity, root: Path,
                       registry: InstallationStateRegistry) -> "InstallationStateHandle":
        if root != registry.state_root_for(identity):
            raise InstallationStateError("installation_state_binding_mismatch")
        value = object.__new__(cls)
        object.__setattr__(value, "identity", identity)
        object.__setattr__(value, "root", root)
        object.__setattr__(value, "_registry", registry)
        return value

    def fixed_object(self, relative: str) -> InstallationStateObject:
        return InstallationStateObject(self, StateRelativePath.parse(relative))

    def ensure_directory(self, obj: InstallationStateObject) -> None:
        self._require_bound(obj)
        _secure_mkdir_chain(self.root, obj.relative.parts)

    def exclusive_lock(self, obj: InstallationStateObject, *, blocking: bool = True) -> "ExclusiveStateLock":
        self._require_bound(obj)
        return ExclusiveStateLock(obj, blocking=blocking)

    def durable_create(self, obj: InstallationStateObject, data: bytes,
                       *, verify: Callable[[bytes], None] | None = None) -> None:
        self._require_bound(obj)
        parent_fd, name = _open_parent(self.root, obj.relative.parts)
        fd = -1
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=parent_fd)
            _write_all(fd, data)
            os.fsync(fd)
            _require_regular_fd(fd)
            os.close(fd); fd = -1
            os.fsync(parent_fd)
            observed = _read_regular_at(parent_fd, name)
            if observed != data:
                raise InstallationStateError("durable_create_verification_failed")
            if verify is not None:
                verify(observed)
        except FileExistsError as exc:
            raise InstallationStateError("state_object_already_exists") from exc
        except OSError as exc:
            raise InstallationStateError("durable_create_failed") from exc
        finally:
            if fd >= 0:
                os.close(fd)
            os.close(parent_fd)

    def durable_replace(self, obj: InstallationStateObject, data: bytes,
                        *, verify: Callable[[bytes], None] | None = None) -> None:
        self._require_bound(obj)
        parent_fd, name = _open_parent(self.root, obj.relative.parts)
        stage = f".{name}.stage-{uuid.uuid4().hex}"
        stage_fd = -1
        published = False
        try:
            _reject_nonregular_existing(parent_fd, name)
            stage_fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                               0o600, dir_fd=parent_fd)
            _write_all(stage_fd, data)
            os.fsync(stage_fd)
            _require_regular_fd(stage_fd)
            os.close(stage_fd); stage_fd = -1
            os.replace(stage, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            published = True
            os.fsync(parent_fd)
            observed = _read_regular_at(parent_fd, name)
            if observed != data:
                raise InstallationStateError("durable_replace_verification_failed")
            if verify is not None:
                verify(observed)
        except InstallationStateError:
            raise
        except OSError as exc:
            raise InstallationStateError("durable_replace_failed") from exc
        finally:
            if stage_fd >= 0:
                os.close(stage_fd)
            if not published:
                try:
                    os.unlink(stage, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
            os.close(parent_fd)

    def read_regular(self, obj: InstallationStateObject) -> bytes:
        self._require_bound(obj)
        parent_fd, name = _open_parent(self.root, obj.relative.parts)
        try:
            return _read_regular_at(parent_fd, name)
        finally:
            os.close(parent_fd)

    def _require_bound(self, obj: InstallationStateObject) -> None:
        if not isinstance(obj, InstallationStateObject) or obj._handle is not self:
            raise InstallationStateError("state_object_binding_mismatch")


class ExclusiveStateLock:
    """Kernel-backed exclusive lock whose pathname is only an identity anchor."""

    def __init__(self, obj: InstallationStateObject, *, blocking: bool) -> None:
        self._obj = obj
        self._blocking = blocking
        self._fd = -1

    def __enter__(self) -> "ExclusiveStateLock":
        parent_fd, name = _open_parent(self._obj._handle.root, self._obj.relative.parts)
        try:
            try:
                fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=parent_fd)
            except OSError as exc:
                raise InstallationStateError("lock_open_failed") from exc
            _require_regular_fd(fd)
            flags = fcntl.LOCK_EX | (0 if self._blocking else fcntl.LOCK_NB)
            try:
                fcntl.flock(fd, flags)
            except BlockingIOError as exc:
                os.close(fd)
                raise InstallationStateError("lock_contended") from exc
            except OSError as exc:
                os.close(fd)
                raise InstallationStateError("lock_acquisition_failed") from exc
            self._fd = fd
            return self
        finally:
            os.close(parent_fd)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._fd >= 0:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = -1


def _require_platform_contract() -> None:
    required = ("O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC")
    if os.name != "posix" or fcntl is None or any(not hasattr(os, item) for item in required):
        raise InstallationStateError("durable_state_platform_unsupported")
    if os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd or os.unlink not in os.supports_dir_fd:
        raise InstallationStateError("durable_state_platform_unsupported")


def _verify_absolute_directory_chain(path: Path) -> None:
    if not path.is_absolute():
        raise InstallationStateError("installation_state_root_not_absolute")
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                              dir_fd=fd)
            os.close(fd); fd = next_fd
    except OSError as exc:
        raise InstallationStateError("installation_state_root_unsafe") from exc
    finally:
        os.close(fd)


def _secure_mkdir_chain(base: Path, relative: tuple[str, ...]) -> None:
    if not base.is_absolute():
        raise InstallationStateError("installation_state_root_not_absolute")
    fd = os.open(base.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for part in (*base.parts[1:], *relative):
            try:
                os.mkdir(part, 0o700, dir_fd=fd)
                os.fsync(fd)
            except FileExistsError:
                pass
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                              dir_fd=fd)
            os.close(fd); fd = next_fd
    except OSError as exc:
        raise InstallationStateError("state_directory_unsafe") from exc
    finally:
        os.close(fd)


def _open_parent(root: Path, parts: tuple[str, ...]) -> tuple[int, str]:
    _require_platform_contract()
    if not parts:
        raise InstallationStateError("state_file_identity_required")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                              dir_fd=fd)
            os.close(fd); fd = next_fd
        return fd, parts[-1]
    except OSError as exc:
        os.close(fd)
        raise InstallationStateError("state_parent_unsafe") from exc


def _require_regular_fd(fd: int) -> None:
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        raise InstallationStateError("state_object_not_regular")


def _reject_nonregular_existing(parent_fd: int, name: str) -> None:
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode):
        raise InstallationStateError("state_object_not_regular")


def _read_regular_at(parent_fd: int, name: str) -> bytes:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
        try:
            _require_regular_fd(fd)
            chunks: list[bytes] = []
            while True:
                block = os.read(fd, 1024 * 1024)
                if not block:
                    return b"".join(chunks)
                chunks.append(block)
        finally:
            os.close(fd)
    except OSError as exc:
        raise InstallationStateError("state_object_read_failed") from exc


def _write_all(fd: int, data: bytes) -> None:
    if not isinstance(data, bytes):
        raise TypeError("durable state content must be bytes")
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise InstallationStateError("state_object_short_write")
        view = view[written:]
