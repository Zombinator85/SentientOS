# ── privilege_lint.py ──────────────────────────────────────────────
from __future__ import annotations

import ast

import datetime
import json
import os
import re
import sys
from pathlib import Path

from logging_config import get_log_path

BANNER_ASCII = [
    "#  _____  _             _",
    "# |  __ \\| |           (_)",
    "# | |__) | |_   _  __ _ _ _ __   __ _",
    "# |  ___/| | | | |/ _` | | '_ \\ / _` |",
    "# | |    | | |_| | (_| | | | | | (_| |",
    "# |_|    |_\\__,_|\\__, |_|_| |_|\\__, |",
    "#                  __/ |         __/ |",
    "#                 |___/         |___/ ",
]

FUTURE_IMPORT = "from __future__ import annotations"

# Optional real helpers (stubbed in CI)
try:
    from admin_utils import require_admin_banner, require_lumos_approval  # noqa: F401
except Exception:  # pragma: no cover
    def require_admin_banner() -> None: ...
    def require_lumos_approval() -> None: ...

# --------------------------------------------------------------------------- #
_IMPORT_RE = re.compile(r"^(from|import)\s+[A-Za-z0-9_. ,]+")


def get_banner(lines: list[str]) -> int | None:
    """Return end index of ASCII banner or None if not present."""
    idx = 0
    while idx < len(lines) and lines[idx].startswith(("#!", "# -*-")):
        idx += 1
    if len(lines) - idx < len(BANNER_ASCII):
        return None
    for off, text in enumerate(BANNER_ASCII):
        if lines[idx + off].rstrip() != text.rstrip():
            return None
    return idx + len(BANNER_ASCII) - 1


def validate_banner_order(lines: list[str], path: Path) -> list[str]:
    """Ensure banner→future→docstring→imports order."""
    errors: list[str] = []
    idx = 0
    banner_end = get_banner(lines)
    if banner_end is not None:
        idx = banner_end + 1

    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    if idx >= len(lines) or lines[idx].strip() != FUTURE_IMPORT:
        return [f"{path}: Banner and __future__ import must be first."]

    idx += 1

    # Determine end of module docstring, if any
    doc_end = None
    try:
        mod = ast.parse("\n".join(lines))
        doc = ast.get_docstring(mod)
        if doc is None:
            raise IndexError
        for node in mod.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Str):
                doc_end = node.end_lineno - 1
                break
    except IndexError:
        doc_end = None
    except Exception:
        doc_end = None

    if doc_end is None:
        for i in range(idx, len(lines)):
            s = lines[i].lstrip()
            if s.startswith(('"""', "'''")):
                quote = s[:3]
                if s.count(quote) >= 2 and s.rstrip().endswith(quote):
                    doc_end = i
                else:
                    for j in range(i + 1, len(lines)):
                        if lines[j].rstrip().endswith(quote):
                            doc_end = j
                            break
                if doc_end is None:
                    doc_end = len(lines) - 1
                break

    if doc_end is None:
        doc_end = idx - 1

    for i in range(idx, len(lines)):
        s = lines[i].strip()
        if _IMPORT_RE.match(s) and s != FUTURE_IMPORT:
            if i < doc_end + 1:
                errors.append(f"{path}: imports must follow module docstring")
            break

    return errors


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
    lines = path.read_text(encoding="utf-8").splitlines()
    return validate_banner_order(lines, path)


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
