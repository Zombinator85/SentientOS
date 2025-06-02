from logging_config import get_log_path
import sys
import json
import datetime
import os
from pathlib import Path

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
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


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


def _has_banner_call(text: str) -> bool:
    return "require_admin_banner()" in text


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    issues = []
    if not _has_header(path):
        issues.append(f"{path}: missing privilege docstring after imports")
    if not _has_banner_call(text):
        issues.append(f"{path}: missing require_admin_banner() call")
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


def main() -> int:
    root = Path(__file__).resolve().parent
    files = find_entrypoints(root)
    issues = []
    for path in files:
        issues.extend(check_file(path))
    if issues:
        print("\n".join(sorted(issues)))
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
