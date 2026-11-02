from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip


def test_godot_avatar_demo_scripts_parse_in_supported_engine(tmp_path: Path) -> None:
    executable = shutil.which("godot")
    if executable is None:
        executable = next((str(candidate) for candidate in (
            Path("/usr/local/bin/godot"), Path("/usr/bin/godot"), Path("/usr/bin/godot4"),
        ) if candidate.is_file() and os.access(candidate, os.X_OK)), None)
    if executable is None:
        pytest.skip("Godot is unavailable in this validation environment")

    source = Path(__file__).parents[1] / "godot_avatar_demo"
    project = tmp_path / "godot_avatar_demo"
    shutil.copytree(source, project, ignore=shutil.ignore_patterns(".godot", "*.uid"))
    home = tmp_path / "godot-home"
    cache = tmp_path / "godot-cache"
    font_cache = tmp_path / "font-cache"
    for directory in (home, cache, font_cache):
        directory.mkdir()

    result = subprocess.run(
        [executable, "--headless", "--path", str(project), "--editor", "--quit"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": os.defpath,
            "HOME": str(home),
            "XDG_CACHE_HOME": str(cache),
            "FONTCONFIG_CACHE_DIR": str(font_cache),
        },
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "Failed to load script" not in output, output
