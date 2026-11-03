"""Locate the Godot executable used by optional integration probes."""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def godot_executable() -> str | None:
    """Use an explicit portable binary when configured, then common PATH names."""
    configured = os.environ.get("SENTIENTOS_GODOT_EXECUTABLE")
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_file():
            raise FileNotFoundError("SENTIENTOS_GODOT_EXECUTABLE does not name a file")
        return str(candidate)
    executable = shutil.which("godot") or shutil.which("godot4")
    if executable is not None:
        return executable
    for candidate in (Path("/usr/local/bin/godot"), Path("/usr/bin/godot"),
                      Path("/usr/bin/godot4")):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None
