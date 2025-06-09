from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path

from logging_config import get_log_path
from sentient_banner import BANNER_LINES

# These are runtime-only; in CI they may be absent, so we fall back gracefully.
try:
    from admin_utils import require_admin_banner, require_lumos_approval
except Exception:  # pragma: no cover
    def require_admin_banner() -> None: ...
    def require_lumos_approval() -> None: ...

# ──────────────────────────────────────────────────────────────────────────────
# Constants & Regex helpers
# ──────────────────────────────────────────────────────────────────────────────
DOCSTRING = BANNER_LINES[0].strip('"')
DOCSTRING_SEARCH_LINES = 60

_IMPORT_RE = re.compile(r"^(from|import)\s+[A-Za-z0-9_. ,]+")


def _first_code_line(lines: list[str]) -> int:
    """Return the index of the first *real* line of code."""
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if (
            not line                        # blank
            or line.startswith("#")         # comment
            or line.startswith(("#!", "# -*-"))  # she-bang / encoding
            or _IMPORT_RE.match(line)       # import stmt
        ):
            idx += 1
            continue
        break
    return idx


def _has_header(path: Path) -> bool:
    """True if the privilege banner docstring appears shortly after the imports."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = _first_code_line(lines)
    search_block = "\n".join(lines[start : start + DOCSTRING_SEARCH_LINES])
    return DOCSTRING in search_block


def _has_banner_call(path: Path) -> bool:
    """True if require_admin_banner() then require_lumos_approval() follow the docstring."""
    lines = path.read_text(encoding="utf-8").splitlines()

    doc_line = next((i for i, ln in enumerate(lines) if DOCSTRING in ln), None)
    if doc_line is None:
        return False

    end_doc = doc_line
    if lines[doc_line].count('"""') < 2:
        for j in range(doc_line + 1, len(lines)):
            if '"""' in lines[j]:
                end_doc = j
                break

    i = end_doc + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or not lines[i].strip().startswith("require_admin_banner("):
        return False

    i += 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    return i < len(lines) and lines[i].strip().startswith("require_lumos_approval(")


ENTRY_PATTERNS = [
    "*_cli.py",
    "*_dashboard.py",
    "*_daemon.py",
    "*_engine.py",
    "collab_server.py",
    "autonomous_ops.py",
    "replay.py",
    "experiments_api.py",
]

MAIN_BLOCK_RE = re.compile(r"if __name__ == ['\"]__main__['\"]")
ARGPARSE_RE = re.compile(r"\bargparse\b")

AUDIT_FILE = get_log_path("privileged_audit.jsonl", "PRIVILEGED_AUDIT_FILE")
AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)


def append_json(path: Path, obj: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        json.dump(obj, fh)
        fh.write("\n")


def audit_use(tool: str, command: str) -> None:
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "tool": tool,
        "command": command,
    }
    append_json(AUDIT_FILE, entry)


def check_file(path: Path) -> list[str]:
    issues: list[str] = []
    if not _has_header(path):
        issues.append(f"{path}: missing privilege docstring after imports")
    if not _has_banner_call(path):
        issues.append(
            f"{path}: require_admin_banner() and require_lumos_approval() not found in order"
        )
    return issues


def find_entrypoints(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in ENTRY_PATTERNS:
        files.update(root.rglob(pattern))
    for path in root.rglob("*.py"):
        if path in files:
            continue
        text = path.read_text(encoding="utf-8")
        if MAIN_BLOCK_RE.search(text) or ARGPARSE_RE.search(text):
            files.add(path)
    return sorted(files)


def main() -> int:
    root = Path(__file__).resolve().parent
    files = find_entrypoints(root)
    issues: list[str] = []
    for p in files:
        issues.extend(check_file(p))

    if issues:
        print("\n".join(sorted(issues)))
        return 1
    print("✅ privilege_lint: all entrypoints have correct banners")
    return 0


if __name__ == "__main__":
    sys.exit(main())
