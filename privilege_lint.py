import sys
from pathlib import Path

DOCSTRING = "Sanctuary Privilege Ritual: Do not remove. See doctrine for details."

ENTRY_PATTERNS = ["*_cli.py", "*_dashboard.py", "collab_server.py", "autonomous_ops.py", "replay.py", "experiments_api.py"]


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    issues = []
    if DOCSTRING not in text:
        issues.append(f"{path}: missing privilege docstring")
    if "require_admin_banner()" not in text:
        issues.append(f"{path}: missing require_admin_banner() call")
    return issues


def main() -> int:
    root = Path(__file__).resolve().parent
    files = []
    for pattern in ENTRY_PATTERNS:
        files.extend(root.glob(pattern))
    issues = []
    for path in files:
        issues.extend(check_file(path))
    if issues:
        print("\n".join(sorted(issues)))
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
