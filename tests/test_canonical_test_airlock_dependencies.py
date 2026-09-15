from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

from scripts import run_tests

pytestmark = pytest.mark.no_legacy_skip

ROOT = Path(__file__).resolve().parents[1]


def _requirements(path: Path) -> list[Requirement]:
    return [
        Requirement(line)
        for raw in path.read_text(encoding="utf-8").splitlines()
        if (line := raw.strip()) and not line.startswith("#")
    ]


def test_jinja2_is_bound_to_the_canonical_minimal_airlock_and_lock() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    codex = _requirements(ROOT / "requirements-codex.txt")
    extra = [Requirement(value) for value in project["project"]["optional-dependencies"]["codex"]]
    assert Requirement("Jinja2>=3.1,<4") in codex
    assert Requirement("Jinja2>=3.1,<4") in extra
    assert any(requirement.name.lower() == "jinja2" for requirement in codex)
    lock = (ROOT / "requirements-lock.txt").read_text(encoding="utf-8").lower()
    assert "jinja2==" in lock
    subprocess.run([run_tests.sys.executable, "-m", "scripts.lock", "check"], cwd=ROOT, check=True)


def test_minimal_airlock_excludes_full_capability_dependencies() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["dependencies"] == []
    codex_names = {item.name.lower() for item in _requirements(ROOT / "requirements-codex.txt")}
    assert "playsound" not in codex_names
    assert "playsound" not in {
        Requirement(value).name.lower()
        for value in project["project"]["optional-dependencies"]["codex"]
    }


def test_runner_probes_jinja2_and_keeps_full_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    assert ("jinja2", None) in run_tests.TEST_INFRA_IMPORTS
    assert run_tests.CANONICAL_REQUIREMENTS_PATH == "requirements-codex.txt"
    calls: list[list[str]] = []
    monkeypatch.delenv(run_tests.FULL_INSTALL_ENV, raising=False)
    monkeypatch.setattr(run_tests, "_run_pip_install", lambda args: calls.append(args) or True)
    result = run_tests._bootstrap_missing_editable("default")
    assert result.install_mode == run_tests.INSTALL_MODE_TEST_AIRLOCK_MINIMAL
    assert calls == [["--no-deps", "-e", "."], ["--only-binary=:all:", "-r", "requirements-codex.txt"]]
    assert all(".[full]" not in value for call in calls for value in call)
    monkeypatch.setenv(run_tests.FULL_INSTALL_ENV, "full")
    calls.clear()
    assert run_tests._bootstrap_missing_editable("default").install_mode == run_tests.INSTALL_MODE_FULL
    assert calls == [["-e", ".[full]"]]


def test_minimal_install_failure_never_falls_back_to_full(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.delenv(run_tests.FULL_INSTALL_ENV, raising=False)
    monkeypatch.setattr(run_tests, "_run_pip_install", lambda args: calls.append(args) or False)
    result = run_tests._bootstrap_missing_editable("default")
    assert not result.ok
    assert result.attempted_modes == (run_tests.INSTALL_MODE_TEST_AIRLOCK_MINIMAL,)
    assert calls == [["--no-deps", "-e", "."]]


def test_missing_jinja2_is_reported_as_incomplete_infrastructure(monkeypatch: pytest.MonkeyPatch) -> None:
    class Completed:
        def __init__(self, returncode: int, stderr: str = "") -> None:
            self.returncode = returncode
            self.stderr = stderr
            self.stdout = ""

    observed: list[str] = []

    def missing_jinja(command: list[str], **_: object) -> Completed:
        module = command[-1].removeprefix("import ")
        observed.append(module)
        return Completed(1, "No module named 'jinja2'") if module == "jinja2" else Completed(0)

    monkeypatch.setattr(run_tests.subprocess, "run", missing_jinja)
    assert run_tests._imports_ok() == (False, "jinja2 import failed: No module named 'jinja2'")
    assert observed == ["fastapi", "from starlette.testclient import TestClient", "httpx", "jinja2"]

    monkeypatch.setattr(run_tests.subprocess, "run", lambda *_args, **_kwargs: Completed(0))
    assert run_tests._imports_ok() == (True, None)
