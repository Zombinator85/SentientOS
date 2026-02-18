"""Forge environment bootstrap for isolated, deterministic runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib
from sentientos.forge_env_cache import resolve_cached_env


@dataclass(slots=True)
class ForgeEnv:
    python: str
    pip: str
    venv_path: str
    created: bool
    install_summary: str
    cache_key: str = ""


def bootstrap_env(session_root: Path) -> ForgeEnv:
    extras = "test" if _has_test_extra(session_root) else "base"
    return resolve_cached_env(session_root, extras)


def _has_test_extra(repo_root: Path) -> bool:
    pyproject = repo_root / "pyproject.toml"
    try:
        payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    optional = payload.get("project", {}).get("optional-dependencies", {})
    return isinstance(optional, dict) and "test" in optional
