from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def terminate_owned_process_tree(process: Any, *,
                                 taskkill_executable: Path | None = None) -> None:
    """Stop a supervised process and descendants that it created."""
    if process.poll() is not None:
        return

    if taskkill_executable is not None and taskkill_executable.is_file():
        try:
            subprocess.run(
                [str(taskkill_executable), "/T", "/F", "/PID", str(process.pid)],
                check=False, capture_output=True, timeout=8,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
