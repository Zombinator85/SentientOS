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
