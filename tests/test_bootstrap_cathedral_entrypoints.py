from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import bootstrap_cathedral


pytestmark = pytest.mark.no_legacy_skip


def _isolated_bootstrap_tree(tmp_path: Path) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    shutil.copy2(Path(bootstrap_cathedral.__file__), scripts / "bootstrap_cathedral.py")
    (scripts / "env_sync_autofill.py").write_text(
        "from pathlib import Path\n"
        "def autofill_env():\n"
        "    Path('environment-synchronized').write_text('yes', encoding='utf-8')\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pip = bin_dir / "pip"
    pip.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    pip.chmod(0o755)
    return bin_dir


def _run_bootstrap(tmp_path: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    bin_dir = _isolated_bootstrap_tree(tmp_path)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(
        [sys.executable, *argv], cwd=tmp_path, env=env, text=True,
        capture_output=True, check=False,
    )


def test_documented_direct_file_entrypoint_imports_sibling(tmp_path: Path) -> None:
    result = _run_bootstrap(tmp_path, "scripts/bootstrap_cathedral.py")

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "environment-synchronized").read_text(encoding="utf-8") == "yes"
    assert "[bootstrap] COMPLETED: Bootstrap complete." in result.stdout


def test_module_entrypoint_imports_sibling(tmp_path: Path) -> None:
    result = _run_bootstrap(tmp_path, "-m", "scripts.bootstrap_cathedral")

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "environment-synchronized").read_text(encoding="utf-8") == "yes"
    assert "[bootstrap] COMPLETED: Bootstrap complete." in result.stdout
