from __future__ import annotations

import shutil
import tomllib

import pytest
from pathlib import Path

from packaging.requirements import Requirement

from scripts.verify_dependency_bootstrap import FORBIDDEN_DEFAULT, verify

pytestmark = pytest.mark.no_legacy_skip

ROOT = Path(__file__).resolve().parents[1]


def _names(items: list[str]) -> set[str]:
    return {Requirement(item).name.lower().replace("_", "-") for item in items}


def _report():
    return verify(ROOT)


def test_root_requirements_delegates_only_to_minimal_bootstrap() -> None:
    assert _report()["root_delegates_to_canonical_minimal"] is True


def test_minimal_bootstrap_excludes_heavy_capabilities() -> None:
    assert _report()["forbidden_packages_found_in_default_surfaces"] == []


def test_project_core_dependencies_are_minimal() -> None:
    assert _report()["core_project_dependencies"] == []


def test_codex_extra_matches_canonical_minimal_requirements() -> None:
    assert _report()["codex_extra_parity"] is True


def test_legacy_dependencies_are_preserved_in_explicit_groups() -> None:
    assert _report()["legacy_dependencies_preserved"] is True


def test_windows_dependencies_are_platform_guarded() -> None:
    assert _report()["windows_marker_errors"] == []


def test_default_install_does_not_resolve_full_capabilities() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert not (_names(data["project"]["dependencies"]) & FORBIDDEN_DEFAULT)


def test_python_314_bootstrap_is_wheel_only() -> None:
    run_tests = (ROOT / "scripts/run_tests.py").read_text()
    workflow = (ROOT / ".github/workflows/required-quality-gate.yml").read_text()
    requirements = (ROOT / "requirements-codex.txt").read_text()
    assert "--only-binary=:all:" in run_tests and "--only-binary=:all:" in workflow
    assert "python_version >= \"3.14\"" in requirements


def test_dependency_contract_rejects_default_heavy_package(tmp_path: Path) -> None:
    for name in ("requirements.txt", "requirements-codex.txt", "requirements-full.txt", "pyproject.toml"):
        shutil.copy2(ROOT / name, tmp_path / name)
    with (tmp_path / "requirements-codex.txt").open("a") as stream:
        stream.write("pandas>=2\n")
    report = verify(tmp_path)
    assert report["status"] == "failed"
    assert "pandas" in report["forbidden_packages_found_in_default_surfaces"]
