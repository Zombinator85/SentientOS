from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def find_llama_server() -> Optional[str]:
    """Return the path to the llama.cpp server executable if present."""

    default_path = Path("C:/SentientOS/bin/llama-server.exe")
    if default_path.exists():
        return str(default_path)

    search_root = Path.home() / "AppData" / "Local"
    if search_root.exists():
        for root, _dirs, files in os.walk(search_root):
            if "llama-server.exe" in files:
                return str(Path(root) / "llama-server.exe")
    return None
