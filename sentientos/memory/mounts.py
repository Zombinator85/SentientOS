"""Memory mount management for Dream Loop storage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict

__all__ = [
    "MemoryMounts",
    "ensure_memory_mounts",
    "resolve_memory_mounts",
    "validate_memory_mounts",
]


@dataclass(frozen=True)
class MemoryMounts:
    """Paths anchoring the persistent memory mounts."""

    vow: Path
    glow: Path
    pulse: Path
    daemon: Path


_MEMORY_ROOT_NAME = "memory"
_MOUNT_NAMES = ("vow", "glow", "pulse", "daemon")


def _memory_root(base_dir: Path) -> Path:
    return Path(base_dir).expanduser().resolve(strict=False) / _MEMORY_ROOT_NAME


def resolve_memory_mounts(base_dir: Path) -> MemoryMounts:
    """Return mount paths under ``base_dir`` without touching the filesystem."""

    root = _memory_root(base_dir)
    return MemoryMounts(*(root / name for name in _MOUNT_NAMES))


def ensure_memory_mounts(base_dir: Path) -> MemoryMounts:
    """Create mount directories if they do not exist and return their paths."""

    mounts = resolve_memory_mounts(base_dir)
    for path in asdict(mounts).values():
        Path(path).mkdir(parents=True, exist_ok=True)
    return mounts


def validate_memory_mounts(mounts: MemoryMounts, base_dir: Path) -> None:
    """Ensure all mounts are rooted under ``base_dir``/memory."""

    root = _memory_root(base_dir).resolve(strict=False)
    for name, path in _iter_mount_paths(mounts).items():
        resolved = path.resolve(strict=False)
        if not resolved.is_relative_to(root):
            raise ValueError(f"Mount '{name}' escapes memory root: {resolved}")


def _iter_mount_paths(mounts: MemoryMounts) -> Dict[str, Path]:
    mapping: Dict[str, Path] = {}
    for key, value in asdict(mounts).items():
        mapping[str(key)] = Path(value)
    return mapping
