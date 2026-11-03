from __future__ import annotations

from pathlib import Path

import pytest

from tests.godot_runtime import godot_executable


def test_explicit_portable_godot_path_is_used(tmp_path: Path, monkeypatch) -> None:
    executable = tmp_path / "Godot_console.exe"
    executable.touch()
    monkeypatch.setenv("SENTIENTOS_GODOT_EXECUTABLE", str(executable))

    assert godot_executable() == str(executable)


def test_invalid_explicit_godot_path_fails_instead_of_skipping(monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_GODOT_EXECUTABLE", "/missing/godot")

    with pytest.raises(FileNotFoundError, match="SENTIENTOS_GODOT_EXECUTABLE"):
        godot_executable()
