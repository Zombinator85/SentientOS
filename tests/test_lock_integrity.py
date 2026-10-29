"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations



from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip


def test_lock_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ("requirements-lock.txt", "requirements-src-lock.txt"):
        path = root / name
        assert path.exists(), f"missing {name}"
        lines = path.read_text().splitlines()
        assert lines[0].startswith('#')
        assert any("--hash=" in l for l in lines)


def test_default_lock_install_uses_one_lock_and_no_deps_project_install() -> None:
    source = (Path(__file__).resolve().parents[1] / "scripts/lock.py").read_text()
    install_body = source.split("def install()", 1)[1].split("def check()", 1)[0]
    assert '"-r", LOCKS[0]' in install_body
    assert '"--no-deps", "."' in install_body
    assert "for lock in LOCKS" not in install_body


def test_documented_mypy_lock_satisfies_pinned_runtime_requirements() -> None:
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.utils import canonicalize_name
    from packaging.version import Version

    root = Path(__file__).resolve().parents[1]
    pins: dict[str, Version] = {}
    for line in (root / "requirements.lock").read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        requirement = Requirement(stripped)
        name = canonicalize_name(requirement.name)
        if name not in {"mypy", "pathspec", "librt"}:
            continue
        exact_pins = [item for item in requirement.specifier if item.operator == "=="]
        assert len(exact_pins) == 1, f"{name} must have one exact lock pin"
        pins[name] = Version(exact_pins[0].version)

    assert pins["mypy"] == Version("1.20.2")
    assert pins["pathspec"] in SpecifierSet(">=1.0.0")
    assert pins["librt"] in SpecifierSet(">=0.8.0")
