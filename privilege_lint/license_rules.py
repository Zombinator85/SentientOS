from __future__ import annotations

from pathlib import Path

DEFAULT_HEADER = "# SPDX-License-Identifier: MIT"


def validate_license_header(lines: list[str], path: Path, header: str) -> list[str]:
    idx = 0
    if lines and lines[0].startswith("#!"):
        idx = 1
    if len(lines) <= idx or lines[idx].strip() != header:
        return [f"{path}: missing license header"]
    return []


def apply_fix_license_header(lines: list[str], path: Path, header: str) -> bool:
    if not header:
        return False
    idx = 0
    if lines and lines[0].startswith("#!"):
        idx = 1
    if len(lines) <= idx or lines[idx].strip() != header:
        lines.insert(idx, header)
        return True
    return False
