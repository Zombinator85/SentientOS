from __future__ import annotations

import sys

import pytest

from sentientos.sandbox_runner import run

pytestmark = pytest.mark.no_legacy_skip


def test_runner_captures_output_and_exit_status() -> None:
    result = run(
        [sys.executable, "-c", "print('sandbox-ok')"],
        timeout=5,
        cpu_seconds=2,
        memory_mb=256,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "sandbox-ok"
    assert result.stderr == ""
    assert result.timed_out is False


def test_runner_reports_timeout() -> None:
    result = run(
        [sys.executable, "-c", "import time; time.sleep(1)"],
        timeout=0.01,
        cpu_seconds=2,
        memory_mb=256,
    )

    assert result.timed_out is True
    assert result.returncode != 0


def test_runner_merges_requested_environment() -> None:
    result = run(
        [sys.executable, "-c", "import os; print(os.environ['SENTIENTOS_SANDBOX_TEST'])"],
        timeout=5,
        cpu_seconds=2,
        memory_mb=256,
        env={"SENTIENTOS_SANDBOX_TEST": "present"},
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "present"
