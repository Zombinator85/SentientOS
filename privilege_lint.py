# ── privilege_lint.py ──────────────────────────────────────────────
from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path

from logging_config import get_log_path
from sentient_banner import BANNER_LINES  # single source of truth ✨

# Optional real helpers (stubbed in CI)
try:
    from admin_utils import require_admin_banner, require_lumos_approval  # noqa: F401
except Exception:  # pragma: no cover
    def require_admin_banner() -> None: ...
    def require_lumos_approval() -> None: ...

# --------------------------------------------------------------------------- #
DOCSTRING               = BANNER_LINES[0].strip('"')
DOCSTRING_SEARCH_LINES  = 60
_IMPORT_RE              = re.compile(r"^(from|import)\s+[A-Za-z0-9_. ,]+")

def _first_code_line(lines: list[str]) -> int:
    """
    Return the index of the first *real* line after she-bang / encoding,
    comments, blank lines, **and import statements**.
    """
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if (
            not line                             # blank
            or line.startswith("#")              # comment
            or line.startswith(("#!", "# -*-"))  # shebang / coding
            or _IMPORT_RE.match(line)            # import
        ):
            i += 1
            continue
        break
    return i
# --------------------------------------------------------------------------- #

def _has_header(path: Path) -> bool:
    """True iff the ritual docstring appears shortly after initial imports."""
    lines  = path.read_text(encoding="utf-8").splitlines()
    start  = _first_code_line(lines)
    block  = "\n".join(lines[start : start + DOCSTRING_SEARCH_LINES])
    return DOCSTRING in block


def _has_banner_call(path: Path) -> bool:
    """True if the two require_* calls follow the docstring in order."""
    lines, loc = path.read_text(encoding="utf-8").splitlines(), None
    for idx, line in enumerate(lines):
        if DOCSTRING in line:
            loc = idx
            break
    if loc is None:
        return False

    # Skip to the line after the closing triple-quote
    while loc + 1 < len(lines) and '"""' not in lines[loc + 1]:
        loc += 1
    if loc + 1 >= len(lines):
        return False
    loc += 2  # first line *after* docstring

    # Skip blanks
    while loc < len(lines) and not lines[loc].strip():
        loc += 1
    if loc >= len(lines) or not lines[loc].strip().startswith("require_admin_banner("):
        return False

    loc += 1
    while loc < len(lines) and not lines[loc].strip():
        loc += 1
    return loc < len(lines) and lines[loc].strip().startswith("require_lumos_approval(")


def _has_lumos_call(path: Path) -> bool:
    """Redundant now, but kept for backward-compat w/ older tooling."""
    return _has_banner_call(path)


# ----------------------------- lint driver ---------------------------------- #
ENTRY_PATTERNS = [
    "*_cli.py", "*_dashboard.py", "*_daemon.py", "*_engine.py",
    "collab_server.py", "autonomous_ops.py", "replay.py", "experiments_api.py",
]
MAIN_BLOCK_RE  = re.compile(r"if __name__ == ['\"]__main__['\"]")
ARGPARSE_RE    = re.compile(r"\bargparse\b")

AUDIT_FILE     = get_log_path("privileged_audit.jsonl", "PRIVILEGED_AUDIT_FILE")
AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)


def audit_use(tool: str, cmd: str) -> None:
    record = {"timestamp": datetime.datetime.utcnow().isoformat(), "tool": tool, "command": cmd}
    with open(AUDIT_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def find_entrypoints(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pat in ENTRY_PATTERNS:
        files.update(root.rglob(pat))
    for p in root.rglob("*.py"):
        if p in files:
            continue
        txt = p.read_text(encoding="utf-8")
        if MAIN_BLOCK_RE.search(txt) or ARGPARSE_RE.search(txt):
            files.add(p)
    return sorted(files)


def check_file(path: Path) -> list[str]:
    errs: list[str] = []
    if not _has_header(path):
        errs.append(f"{path}: missing privilege docstring near top")
    if not _has_banner_call(path):
        errs.append(f"{path}: banner calls not in correct order")
    return errs


def main() -> int:
    root   = Path(__file__).resolve().parent
    issues = [e for f in find_entrypoints(root) for e in check_file(f)]
    if issues:
        print("\n".join(sorted(issues)))
        return 1
    return 0


if __name__ == "__main__":
    require_admin_banner()
    require_lumos_approval()
    sys.exit(main())
# ────────────────────────────────────────────────────────────
