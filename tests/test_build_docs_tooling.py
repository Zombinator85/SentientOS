from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import yaml

import pytest

from scripts import build_docs

pytestmark = pytest.mark.no_legacy_skip


class _Completed:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_docs_extra_declares_mkdocs() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    docs_deps = pyproject["project"]["optional-dependencies"]["docs"]

    assert any(dep.startswith("mkdocs") for dep in docs_deps)
    assert set(build_docs.DOCS_PIP_REQUIREMENTS) <= set(docs_deps)
    assert not any(dep.startswith("mkdocs") for dep in pyproject["project"]["dependencies"])


def test_mkdocs_config_does_not_require_undeclared_plugins_or_theme() -> None:
    config = yaml.safe_load(Path("mkdocs.yml").read_text(encoding="utf-8"))

    assert config.get("theme") == "readthedocs"
    assert config.get("plugins", []) in ([], None)


def test_missing_docs_dependency_fails_actionably(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mkdocs.yml").write_text("site_name: Test\n", encoding="utf-8")
    monkeypatch.setattr(build_docs.importlib.util, "find_spec", lambda name: None)

    code = build_docs.main(["--check-deps"])

    captured = capsys.readouterr()
    assert code == 2
    assert "ENVIRONMENT/BOOTSTRAP ERROR" in captured.err
    assert "Docs build dependencies missing. Run:" in captured.err
    assert "python scripts/build_docs.py --bootstrap-docs" in captured.err
    assert "pip install -e .[docs]" in captured.err
    assert "Missing Python import(s): mkdocs, watchdog.observers" in captured.err
    assert "Missing docs package requirement(s): mkdocs>=1.6,<2, watchdog>=2,<3" in captured.err


def test_bootstrap_docs_flag_installs_and_exits_without_building(monkeypatch, tmp_path, capsys) -> None:
    commands: list[list[str]] = []
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mkdocs.yml").write_text("site_name: Test\n", encoding="utf-8")

    missing_values = [["mkdocs"], []]

    def fake_missing() -> list[str]:
        return missing_values.pop(0)

    def fake_run(cmd, check=False):
        commands.append(cmd)
        return _Completed(0)

    monkeypatch.setattr(build_docs, "missing_docs_dependencies", fake_missing)
    monkeypatch.setattr(build_docs.subprocess, "run", fake_run)

    code = build_docs.main(["--bootstrap-docs"])

    captured = capsys.readouterr()
    assert code == 0
    assert commands == [
        [sys.executable, "-m", "pip", "install", *build_docs.DOCS_PIP_REQUIREMENTS]
    ]
    assert "Docs build dependencies bootstrapped and available." in captured.out


def test_build_docs_uses_current_python_mkdocs_module(monkeypatch, tmp_path, capsys) -> None:
    commands: list[list[str]] = []
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mkdocs.yml").write_text("site_name: Test\n", encoding="utf-8")
    monkeypatch.setattr(build_docs, "missing_docs_dependencies", lambda: [])

    def fake_run(cmd, capture_output=False, text=False):
        commands.append(cmd)
        return _Completed(0, "mkdocs ok\n")

    monkeypatch.setattr(build_docs.subprocess, "run", fake_run)

    code = build_docs.main([])

    captured = capsys.readouterr()
    assert code == 0
    assert commands == [[sys.executable, "-m", "mkdocs", "build", "--clean"]]
    assert "mkdocs ok" in captured.out
    assert "Generated 1 pages:" in captured.out


def test_bootstrap_docs_installs_minimal_docs_requirements(monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_run(cmd, check=False):
        commands.append(cmd)
        return _Completed(0)

    monkeypatch.setattr(build_docs.subprocess, "run", fake_run)

    assert build_docs.bootstrap_docs_dependencies() is True
    assert commands == [
        [sys.executable, "-m", "pip", "install", *build_docs.DOCS_PIP_REQUIREMENTS]
    ]
