from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip


def test_pulse_modules_do_not_import_task_execution_stack():
    pulse_dir = Path("sentientos") / "pulse"
    assert pulse_dir.is_dir(), "pulse package missing"
    forbidden_tokens = ("task_admission", "task_executor")
    offenders: list[str] = []

    for path in pulse_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if f"import {token}" in text or f"from {token} " in text:
                offenders.append(f"{path}: {token}")

    assert not offenders, f"pulse modules import execution stack: {offenders}"
