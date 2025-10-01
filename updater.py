from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def update(repo_root: str | Path | None = None) -> int:
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent
    pull = subprocess.run(["git", "pull"], cwd=root)
    if pull.returncode != 0:
        return pull.returncode
    return subprocess.run([sys.executable, "sentientosd.py"], cwd=root).returncode


if __name__ == "__main__":
    raise SystemExit(update())
