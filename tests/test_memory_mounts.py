from pathlib import Path

import pytest

from sentientos.memory.mounts import (
    MemoryMounts,
    ensure_memory_mounts,
    resolve_memory_mounts,
    validate_memory_mounts,
)


def test_ensure_memory_mounts_creates_directories(tmp_path: Path) -> None:
    base = tmp_path / "SentientOS"
    mounts = ensure_memory_mounts(base)

    expected = {
        "vow": base / "memory" / "vow",
        "glow": base / "memory" / "glow",
        "pulse": base / "memory" / "pulse",
        "daemon": base / "memory" / "daemon",
    }
    for name, path in expected.items():
        assert getattr(mounts, name) == path
        assert path.exists()
        assert path.is_dir()

    # Calling again should be idempotent
    mounts_second = ensure_memory_mounts(base)
    assert mounts_second == mounts


def test_validate_memory_mounts_detects_escape(tmp_path: Path) -> None:
    base = tmp_path / "SentientOS"
    mounts = ensure_memory_mounts(base)
    validate_memory_mounts(mounts, base)

    invalid = MemoryMounts(
        vow=tmp_path / "outside" / "vow",
        glow=mounts.glow,
        pulse=mounts.pulse,
        daemon=mounts.daemon,
    )
    with pytest.raises(ValueError):
        validate_memory_mounts(invalid, base)


def test_resolve_memory_mounts_is_pure(tmp_path: Path) -> None:
    base = tmp_path / "SentientOS"
    result = resolve_memory_mounts(base)
    assert isinstance(result, MemoryMounts)
    assert (tmp_path / "SentientOS").exists() is False
