from __future__ import annotations

import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.always_on_integrity


def _run_import_check(
    module: str,
    *,
    env_overrides: dict[str, str] | None = None,
    env_unset: tuple[str, ...] = (),
    extra_asserts: str = "",
) -> None:
    lines = [
        "import importlib",
        "import logging",
        "import os",
        "",
        "root = logging.getLogger()",
        "before = len(root.handlers)",
        f"module = importlib.import_module({module!r})",
        "after = len(root.handlers)",
        'assert before == after == 0, "logging handlers added during import"',
    ]
    if extra_asserts:
        lines.extend(extra_asserts.splitlines())
    code = "\n".join(lines) + "\n"
    env = os.environ.copy()
    for key in env_unset:
        env.pop(key, None)
    if env_overrides:
        env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.returncode == 0


def test_core_imports_are_pure() -> None:
    _run_import_check(
        "policy_engine",
        env_overrides={"SENTIENTOS_ALLOW_UNSAFE": "1"},
        extra_asserts="assert module._ALLOW_UNSAFE_GRADIENT is False",
    )
    _run_import_check(
        "sentientos.codex_startup_guard",
        env_overrides={
            "CODEX_STARTUP_ROOT_PID": "12345",
            "CODEX_STARTUP_FINALIZED": "12345",
        },
        extra_asserts=(
            "assert module._STARTUP_OWNER_PID is None\n"
            "assert module._STARTUP_FINALIZED is False\n"
            "assert os.environ.get('CODEX_STARTUP_ROOT_PID') == '12345'\n"
            "assert os.environ.get('CODEX_STARTUP_FINALIZED') == '12345'"
        ),
    )
    _run_import_check(
        "task_admission",
        extra_asserts="assert module._ADMISSION_LOG_PATH is None",
    )
    _run_import_check("sentientos.federation")
