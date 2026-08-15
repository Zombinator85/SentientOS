from __future__ import annotations

import multiprocessing
import os
from pathlib import Path

import pytest

from api import actuator
from scripts.verify_actuator_file_descriptor_custody import verify


pytestmark = [
    pytest.mark.no_legacy_skip,
    pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody proofs"),
]


@pytest.fixture(autouse=True)
def _sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actuator, "SANDBOX_DIR", tmp_path / "sandbox")


def test_nested_descriptor_relative_create_and_write(tmp_path: Path) -> None:
    result = actuator.file_write("new/nested/out.txt", "data")
    target = tmp_path / "sandbox/new/nested/out.txt"
    assert target.read_text() == "data"
    assert result == {"written": str(target)}


def test_regular_file_overwrite() -> None:
    actuator.file_write("existing.txt", "first")
    actuator.file_write("existing.txt", "second")
    assert (actuator.SANDBOX_DIR / "existing.txt").read_text() == "second"


def test_deterministic_old_parent_swap_witness_is_bound_after_repair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox = tmp_path / "sandbox"
    admitted = sandbox / "safe"
    outside = tmp_path / "outside"
    admitted.mkdir(parents=True)
    outside.mkdir()

    def swap(event: str, _fd: int, leaf: str) -> None:
        if event == "parent_bound" and leaf == "marker.txt":
            admitted.rename(sandbox / "descriptor-bound-original")
            admitted.symlink_to(outside, target_is_directory=True)

    monkeypatch.setattr(actuator, "_file_custody_checkpoint", swap)
    actuator.file_write("safe/marker.txt", "bound")
    assert not (outside / "marker.txt").exists()
    assert (sandbox / "descriptor-bound-original/marker.txt").read_text() == "bound"


def _process_parent_swap(root: str, ready: multiprocessing.synchronize.Event) -> None:
    from api import actuator as child_actuator

    base = Path(root)
    child_actuator.SANDBOX_DIR = base / "sandbox"

    def swap(event: str, _fd: int, leaf: str) -> None:
        if event == "parent_bound" and leaf == "process.txt":
            (base / "sandbox/safe").rename(base / "sandbox/original")
            (base / "sandbox/safe").symlink_to(base / "outside", target_is_directory=True)
            ready.set()

    child_actuator._file_custody_checkpoint = swap
    child_actuator.file_write("safe/process.txt", "process-real")


def test_process_real_parent_replacement_cannot_escape(tmp_path: Path) -> None:
    (tmp_path / "sandbox/safe").mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    process = context.Process(target=_process_parent_swap, args=(str(tmp_path), ready))
    process.start()
    process.join(10)
    assert process.exitcode == 0
    assert ready.is_set()
    assert not (tmp_path / "outside/process.txt").exists()
    assert (tmp_path / "sandbox/original/process.txt").read_text() == "process-real"


@pytest.mark.parametrize("inward", [False, True])
def test_directory_symlinks_are_denied_with_zero_target_effect(tmp_path: Path, inward: bool) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    target = sandbox / "inside" if inward else tmp_path / "outside"
    target.mkdir()
    (sandbox / "link").symlink_to(target, target_is_directory=True)
    with pytest.raises((PermissionError, OSError)):
        actuator.file_write("link/marker.txt", "escape")
    assert not (target / "marker.txt").exists()


def test_final_symlink_is_denied_without_modifying_target(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("sentinel")
    (sandbox / "leaf.txt").symlink_to(outside)
    with pytest.raises(PermissionError, match="leaf rejected"):
        actuator.file_write("leaf.txt", "changed")
    assert outside.read_text() == "sentinel"


def test_final_leaf_swap_after_open_mutates_only_bound_object(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    leaf = sandbox / "leaf.txt"
    leaf.write_text("old")
    outside = tmp_path / "outside.txt"
    outside.write_text("sentinel")

    def swap(event: str, _fd: int, component: str) -> None:
        if event == "leaf_bound" and component == "leaf.txt":
            leaf.unlink()
            leaf.symlink_to(outside)

    monkeypatch.setattr(actuator, "_file_custody_checkpoint", swap)
    actuator.file_write("leaf.txt", "new")
    assert outside.read_text() == "sentinel"
    assert leaf.is_symlink()


def test_hardlink_alias_is_denied_before_truncation(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("sentinel")
    os.link(outside, sandbox / "alias.txt")
    with pytest.raises(PermissionError, match="hardlink alias"):
        actuator.file_write("alias.txt", "changed")
    assert outside.read_text() == "sentinel"


@pytest.mark.parametrize("path", [None, 3, "", "bad\x00name", "/absolute", "../escape", "a/../../escape"])
def test_malformed_and_escape_paths_have_zero_effect(tmp_path: Path, path: object) -> None:
    with pytest.raises((ValueError, PermissionError)):
        actuator.file_write(path, "data")  # type: ignore[arg-type]
    assert not (tmp_path / "sandbox").exists()


def test_literal_names_and_repeated_separators_are_not_expanded(tmp_path: Path) -> None:
    actuator.file_write("~//$HOME/out.txt", "literal")
    assert (tmp_path / "sandbox/~/$HOME/out.txt").read_text() == "literal"


def test_unsupported_platform_fails_closed_without_pathname_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actuator, "_descriptor_file_write_supported", lambda: False)
    with pytest.raises(RuntimeError, match="unsupported"):
        actuator.file_write("out.txt", "data")
    assert not (tmp_path / "sandbox").exists()


def test_static_descriptor_custody_verifier_passes() -> None:
    assert verify()["status"] == "actuator_file_descriptor_custody_ready"
