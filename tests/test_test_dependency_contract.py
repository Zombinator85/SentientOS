"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib
from pathlib import Path


def test_test_extras_include_httpx_dependency_contract() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    config = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    optional = config["project"]["optional-dependencies"]
    test_extra = optional.get("test", [])

    assert any(dep.startswith("httpx") for dep in test_extra), (
        "project.optional-dependencies.test must explicitly include httpx so "
        "FastAPI/Starlette TestClient has a deterministic runtime contract."
    )
