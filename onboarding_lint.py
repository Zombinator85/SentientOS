from __future__ import annotations
import subprocess
from pathlib import Path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner


def _changed_files() -> list[str]:
    try:
        out = subprocess.check_output(["git", "diff", "--name-only", "--cached"])
        return out.decode().splitlines()
    except Exception:
        return []


def main() -> int:
    require_admin_banner()
    changed = _changed_files()
    issues: list[str] = []
    if "tags.py" in changed and "docs/TAGS_GLOSSARY.md" not in changed:
        issues.append("tags.py changed without docs/TAGS_GLOSSARY.md update")
    if issues:
        print("\n".join(issues))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
