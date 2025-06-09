from __future__ import annotations

import os
from pathlib import Path

SHEBANG = "#!/usr/bin/env python3"


def validate_shebang(path: Path, require: bool) -> list[str]:
    """Ensure executable scripts have the correct shebang."""
    lines = path.read_text(encoding="utf-8").splitlines()
    has_shebang = bool(lines) and lines[0].startswith("#!")
    is_exec = os.access(path, os.X_OK)
    errors: list[str] = []
    if is_exec or has_shebang:
        if not has_shebang or lines[0].strip() != SHEBANG:
            if require:
                errors.append(f"{path}: invalid shebang")
        if require and not is_exec:
            errors.append(f"{path}: not executable")
    return errors


def apply_fix(path: Path, fix_mode: bool) -> bool:
    lines = path.read_text(encoding="utf-8").splitlines()
    changed = False
    if not lines or lines[0].strip() != SHEBANG:
        lines.insert(0, SHEBANG)
        changed = True
    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if fix_mode:
        mode = path.stat().st_mode
        if not (mode & 0o111):
            path.chmod(mode | 0o755)
    return changed
