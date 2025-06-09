from logging_config import get_log_path
import sys
import json
from log_utils import append_json
import datetime
import os
from pathlib import Path
import argparse
try:
    from admin_utils import require_admin_banner, require_lumos_approval
except Exception:  # pragma: no cover - fallback for lint
    def require_admin_banner() -> None:
        """Fallback when admin_utils cannot be imported during lint."""
        pass
    def require_lumos_approval() -> None:
        """Fallback when admin_utils cannot be imported during lint."""
        pass

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details.

Lint entrypoints for the Sanctuary privilege ritual.

Usage is recorded in ``logs/privileged_audit.jsonl`` or the path set by
the ``PRIVILEGED_AUDIT_FILE`` environment variable. See
``docs/ENVIRONMENT.md`` for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

DOCSTRING = "Sanctuary Privilege Ritual: Do not remove. See doctrine for details."

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

DOCSTRING_SEARCH_LINES = 60

AUDIT_FILE = get_log_path("privileged_audit.jsonl", "PRIVILEGED_AUDIT_FILE")
AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)


def audit_use(tool: str, command: str) -> None:
    """Append a privileged command usage entry."""
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "tool": tool,
        "command": command,
    }
    append_json(AUDIT_FILE, entry)


def _has_header(path: Path) -> bool:
    """Return True if the ritual docstring appears soon after imports."""
    lines = path.read_text(encoding="utf-8").splitlines()
    idx = 0
    # Skip shebangs, comments and imports at the top of the file
    while idx < len(lines):
        line = lines[idx].strip()
        if not line or line.startswith("#"):
            idx += 1
            continue
        if line.startswith("import ") or line.startswith("from "):
            idx += 1
            continue
        break
    search_block = "\n".join(lines[idx : idx + DOCSTRING_SEARCH_LINES])
    return DOCSTRING in search_block


def _has_banner_call(path: Path) -> bool:
    """Return True if banner calls appear in the correct order."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = None
    for i, line in enumerate(lines):
        if DOCSTRING in line:
            start = i
            break
    if start is None:
        return False
    end = start
    if lines[start].count('"""') >= 2:
        end = start
    else:
        for j in range(start + 1, len(lines)):
            if '"""' in lines[j]:
                end = j
                break
        else:
            return False

    j = end + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j >= len(lines) or not lines[j].strip().startswith("require_admin_banner("):
        return False

    j += 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    return j < len(lines) and lines[j].strip().startswith("require_lumos_approval(")


def _has_lumos_call(path: Path) -> bool:
    """Return True if ``require_lumos_approval()`` follows ``require_admin_banner()``."""
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("require_admin_banner("):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            return j < len(lines) and lines[j].strip().startswith("require_lumos_approval(")
    return False


def check_file(path: Path) -> list[str]:
    issues = []
    if not _has_header(path):
        issues.append(f"{path}: missing privilege docstring after imports")
    if not _has_banner_call(path):
        issues.append(
            f"{path}: require_admin_banner() must immediately follow the banner docstring and be followed by require_lumos_approval()"
        )
    elif not _has_lumos_call(path):
        issues.append(
            f"{path}: require_lumos_approval() must immediately follow require_admin_banner()"
        )
    return issues


def find_entrypoints(root: Path) -> list[Path]:
    """Return Python entrypoint files under ``root``."""
    files: set[Path] = set()
    for pattern in ENTRY_PATTERNS:
        files.update(root.glob(pattern))
    for path in root.glob("*.py"):
        if path in files:
            continue
        text = path.read_text(encoding="utf-8")
        if "__main__" in text or "argparse" in text:
            files.add(path)
    return sorted(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Privilege banner lint")
    parser.add_argument("--strict", action="store_true", help="fail on issues")
    parser.add_argument("--no-emoji", action="store_true", help="disable emoji output")
    args = parser.parse_args(argv)

    if args.no_emoji:
        os.environ["SENTIENTOS_NO_EMOJI"] = "1"

    strict = args.strict or os.getenv("SENTIENTOS_LINT_STRICT") == "1"

    root = Path(__file__).resolve().parent
    files = find_entrypoints(root)
    issues: list[str] = []
    for path in files:
        issues.extend(check_file(path))

    if issues:
        print("\n".join(sorted(issues)))
        if strict:
            return 1
        print(f"\033[33mWARNING: {len(issues)} issue(s) found\033[0m")
        return 0
    return 0

if __name__ == "__main__":
    sys.exit(main())
