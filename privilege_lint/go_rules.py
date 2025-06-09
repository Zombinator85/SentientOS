from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from ._compat import RuleSkippedError


def validate_go(path: Path, license_header: str | None = None) -> List[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    issues: List[str] = []
    if license_header and (not lines or license_header not in lines[0]):
        issues.append(f"{path}:1 missing license header")
    try:
        proc = subprocess.run(
            ["go", "vet", str(path)], capture_output=True, text=True, check=False
        )
        out = proc.stdout + proc.stderr
        for ln in out.strip().splitlines():
            parts = ln.split(":", 2)
            if len(parts) >= 2:
                issues.append(f"{parts[0]}:{parts[1]} {parts[-1].strip()}")
    except FileNotFoundError as exc:
        raise RuleSkippedError("missing dependency") from exc
    except Exception:
        pass
    if "package main" in lines[0] and not any(l.startswith("//") for l in lines[1:4]):
        issues.append(f"{path}:1 missing doc comment")
    return issues
