from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def find_ollama() -> Optional[str]:
    """Return the path to the Ollama executable if present."""

    default_path = Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"
    if default_path.exists():
        return str(default_path)

    search_root = Path.home() / "AppData" / "Local"
    if search_root.exists():
        for root, _dirs, files in os.walk(search_root):
            if "ollama.exe" in files:
                return str(Path(root) / "ollama.exe")
    return None
