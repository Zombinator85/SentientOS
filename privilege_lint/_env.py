from __future__ import annotations

import importlib
import shutil
import subprocess
from dataclasses import dataclass

@dataclass
class Capability:
    available: bool
    info: str


def _probe(cmd: list[str]) -> Capability:
    exe = cmd[0]
    path = shutil.which(exe)
    if not path:
        return Capability(False, f"{exe} not found in PATH")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        out = proc.stdout.strip() or proc.stderr.strip()
        first_line = out.splitlines()[0] if out else ""
        return Capability(True, f"{path} ({first_line})")
    except Exception as exc:
        return Capability(False, f"{exe} invocation failed: {exc}")


def detect_pkg(name: str) -> Capability:
    try:
        importlib.import_module(name)
        return Capability(True, "available")
    except Exception as exc:
        return Capability(False, str(exc))


NODE = _probe(["node", "--version"])
GO = _probe(["go", "version"])
DMYPY = _probe(["dmypy", "--version"])
PYESPRIMA = detect_pkg("pyesprima")

HAS_NODE = NODE.available
HAS_GO = GO.available
HAS_DMYPY = DMYPY.available
HAS_PYESPRIMA = PYESPRIMA.available

__all__ = [
    "HAS_NODE",
    "HAS_GO",
    "HAS_DMYPY",
    "HAS_PYESPRIMA",
    "NODE",
    "GO",
    "DMYPY",
    "PYESPRIMA",
]
