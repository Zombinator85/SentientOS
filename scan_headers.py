#!/usr/bin/env python3
"""Scan Python files for missing __future__ annotations import."""
from __future__ import annotations

from pathlib import Path


def first_non_shebang_line(path: Path) -> str:
    """Return the first line after an optional shebang."""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not lines:
        return ""
    idx = 1 if lines[0].startswith("#!") else 0
    return lines[idx] if idx < len(lines) else ""


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    for py_file in sorted(repo_root.rglob("*.py")):
        line = first_non_shebang_line(py_file).strip()
        if line != "from __future__ import annotations":
            rel_path = py_file.relative_to(repo_root).as_posix()
            print(f"- [ ] {rel_path}")


if __name__ == "__main__":
    main()
