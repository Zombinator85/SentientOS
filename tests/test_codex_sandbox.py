from __future__ import annotations

from pathlib import Path

import pytest

from codex.sandbox import CodexSandbox, SandboxViolation


def test_write_outside_sandbox_fails(tmp_path: Path) -> None:
    sandbox = CodexSandbox(root=tmp_path)

    with pytest.raises(SandboxViolation):
        sandbox.commit_text(tmp_path / "outside" / "escape.txt", "nope", approved=True)


def test_forbidden_command_rejected() -> None:
    sandbox = CodexSandbox()

    with pytest.raises(SandboxViolation):
        sandbox.run_command(["pip", "install", "something"])


def test_non_allowlisted_command_denied_before_runner() -> None:
    sandbox = CodexSandbox()
    runner_called = False

    def runner(_: list[str]) -> None:
        nonlocal runner_called
        runner_called = True
        raise AssertionError("runner should not be called for forbidden commands")

    with pytest.raises(SandboxViolation):
        sandbox.run_command(["bash", "-c", "echo hi"], runner=runner)

    assert runner_called is False


def test_mutation_requires_approval(tmp_path: Path) -> None:
    sandbox = CodexSandbox(root=tmp_path)
    target = tmp_path / "integration" / "note.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("baseline", encoding="utf-8")

    record = sandbox.stage_mutation(target, "updated")

    assert target.read_text(encoding="utf-8") == "baseline", "Stage should not apply directly"
    assert record.diff

    sandbox.apply_staged(record.stage_id, operator="tester")

    assert target.read_text(encoding="utf-8") == "updated", "Approval should apply staged change"


def test_relative_traversal_blocked(tmp_path: Path) -> None:
    sandbox = CodexSandbox(root=tmp_path)
    target = tmp_path.parent / "escape.txt"

    with pytest.raises(SandboxViolation):
        sandbox.commit_text(tmp_path / ".." / "escape.txt", "deny", approved=False)

    assert not target.exists()


def test_symlink_escape_blocked(tmp_path: Path) -> None:
    allowed_dir = tmp_path / "integration"
    allowed_dir.mkdir(parents=True, exist_ok=True)
    outside_target = tmp_path.parent / "outside.txt"
    symlink_path = allowed_dir / "link.txt"
    symlink_path.symlink_to(outside_target)

    sandbox = CodexSandbox(root=tmp_path)

    with pytest.raises(SandboxViolation):
        sandbox.commit_text(symlink_path, "blocked", approved=True)

    assert not outside_target.exists()


def test_invalid_jsonl_payload_rejected(tmp_path: Path) -> None:
    sandbox = CodexSandbox(root=tmp_path)
    log_path = tmp_path / "integration" / "log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with pytest.raises(SandboxViolation):
        sandbox.append_jsonl(log_path, {"value": float("nan")}, approved=False)

    assert not log_path.exists()


def test_oversized_jsonl_payload_rejected(tmp_path: Path) -> None:
    sandbox = CodexSandbox(root=tmp_path)
    log_path = tmp_path / "integration" / "log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"blob": "x" * (CodexSandbox._MAX_LOG_ENTRY_BYTES + 10)}

    with pytest.raises(SandboxViolation):
        sandbox.append_jsonl(log_path, payload, approved=False)

    assert not log_path.exists()


def test_reset_clears_staging(tmp_path: Path) -> None:
    sandbox = CodexSandbox(root=tmp_path)
    target = tmp_path / "integration" / "note.txt"
    target.parent.mkdir(parents=True, exist_ok=True)

    record = sandbox.stage_mutation(target, "content")

    assert record.staged_path.exists()

    sandbox.reset()

    assert not record.staged_path.exists()
    assert not any(sandbox._staging_dir.iterdir())
