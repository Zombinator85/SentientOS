"""Forge environment bootstrap for isolated, deterministic runs."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import venv


@dataclass(slots=True)
class ForgeEnv:
    python: str
    pip: str
    venv_path: str
    created: bool
    install_summary: str


def bootstrap_env(session_root: Path) -> ForgeEnv:
    forge_dir = session_root / ".forge"
    preferred = forge_dir / "venv"
    fallback = session_root / ".venv_forge"
    venv_path = preferred if forge_dir.exists() or not fallback.exists() else fallback
    marker = venv_path / ".forge_env_ok"

    python_path = _venv_python(venv_path)
    pip_path = _venv_pip(venv_path)

    if marker.exists() and python_path.exists():
        return ForgeEnv(
            python=str(python_path),
            pip=str(pip_path),
            venv_path=str(venv_path),
            created=False,
            install_summary=_read_marker(marker),
        )

    venv_path.parent.mkdir(parents=True, exist_ok=True)
    builder = venv.EnvBuilder(with_pip=True, clear=False)
    builder.create(venv_path)

    summary: list[str] = []
    summary.append(_run_best_effort([str(python_path), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], session_root, "upgrade"))

    install_args = ["-e", ".[test]"] if _has_test_extra(session_root) else ["-e", "."]
    summary.append(
        _run_best_effort([str(python_path), "-m", "pip", "install", *install_args], session_root, "install")
    )

    import_check = subprocess.run(
        [str(python_path), "-c", "import sentientos"],
        cwd=session_root,
        capture_output=True,
        text=True,
        check=False,
    )
    summary.append(f"import_sentientos:rc={import_check.returncode}")

    marker.write_text(json.dumps({"summary": " | ".join(summary)}, sort_keys=True), encoding="utf-8")

    return ForgeEnv(
        python=str(python_path),
        pip=str(pip_path),
        venv_path=str(venv_path),
        created=True,
        install_summary=" | ".join(summary),
    )


def _venv_python(venv_path: Path) -> Path:
    if (venv_path / "Scripts" / "python.exe").exists():
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _venv_pip(venv_path: Path) -> Path:
    if (venv_path / "Scripts" / "pip.exe").exists():
        return venv_path / "Scripts" / "pip.exe"
    return venv_path / "bin" / "pip"


def _has_test_extra(repo_root: Path) -> bool:
    pyproject = repo_root / "pyproject.toml"
    try:
        content = pyproject.read_text(encoding="utf-8")
    except OSError:
        return False
    return "[project.optional-dependencies]" in content and "test" in content


def _run_best_effort(argv: list[str], cwd: Path, label: str) -> str:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    return f"{label}:rc={result.returncode}"


def _read_marker(marker: Path) -> str:
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "reused"
    summary = payload.get("summary")
    return str(summary) if isinstance(summary, str) and summary else "reused"
