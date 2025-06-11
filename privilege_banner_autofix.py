from __future__ import annotations
from logging_config import get_log_path

import argparse
import datetime
import json
import os
from pathlib import Path
from typing import Dict, List

from sentientos.privilege import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

DOCSTRING = "Sanctuary Privilege Ritual: Do not remove. See doctrine for details."
IMPORT_LINE = "from sentientos.privilege import require_admin_banner"
CALL_LINE = (
    "require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine."
)

LOG_PATH = get_log_path("privilege_audit.jsonl", "PRIVILEGE_AUDIT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


# Helpers ------------------------------------------------------------

def _insert_lines(lines: List[str], idx: int, new_lines: List[str]) -> None:
    for offset, line in enumerate(new_lines):
        lines.insert(idx + offset, line)


def _detect_insert_index(lines: List[str]) -> int:
    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if stripped.startswith("#") or stripped.startswith("from __future__"):
            idx += 1
            continue
        if stripped.startswith("import ") or stripped.startswith("from "):
            idx += 1
            continue
        break
    return idx


def autofix(path: Path) -> str:
    """Autofix privilege banner issues for a single file."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    changed = False
    idx = _detect_insert_index(lines)
    search_block = "\n".join(lines[idx : idx + 20])

    if DOCSTRING not in search_block:
        _insert_lines(lines, idx, [f'"""{DOCSTRING}"""'])
        changed = True
        idx += 1

    if IMPORT_LINE not in text:
        _insert_lines(lines, idx, [IMPORT_LINE])
        changed = True
        idx += 1

    if "require_admin_banner()" not in text:
        _insert_lines(lines, idx + 1, [CALL_LINE])
        changed = True

    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "fixed" if changed else "skipped"


def log_result(file: Path, result: str) -> None:
    entry: Dict[str, str] = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "file": str(file),
        "result": result,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# CLI ----------------------------------------------------------------

def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Privilege Banner Auto Fixer")
    ap.add_argument("paths", nargs="*", help="Files to check")
    ap.add_argument("--all", action="store_true", help="Process all Python files")
    ap.add_argument("--report", action="store_true", help="Print summary report")
    args = ap.parse_args()


    root = Path(__file__).resolve().parent
    files: List[Path] = []
    if args.all:
        files = list(root.glob("*.py"))
    files.extend(Path(p) for p in args.paths)

    results: Dict[str, int] = {"fixed": 0, "skipped": 0}
    for fp in files:
        if not fp.is_file() or fp.name == Path(__file__).name:
            continue
        try:
            res = autofix(fp)
        except Exception:
            res = "error"
        log_result(fp, res)
        if res in results:
            results[res] += 1

    if args.report:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
