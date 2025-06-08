from __future__ import annotations

import argparse
import datetime as _dt
import re
import subprocess
from pathlib import Path

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
# Manage SentientOS releases.

require_admin_banner()
require_lumos_approval()


def update_version(version: str, project_file: Path) -> None:
    """Update the project version."""
    text = project_file.read_text(encoding="utf-8")
    new_text = re.sub(r'version\s*=\s*"[^"]+"', f'version = "{version}"', text, count=1)
    project_file.write_text(new_text, encoding="utf-8")


def prepend_changelog(version: str, changelog: Path) -> None:
    """Insert a new release section at the top of the changelog."""
    date = _dt.date.today().isoformat()
    header = f"## [{version}] - {date}"
    body = changelog.read_text(encoding="utf-8")
    changelog.write_text(f"{header}\n\n- Initial release.\n\n" + body, encoding="utf-8")


def commit_and_tag(version: str) -> None:
    """Commit the release and create a Git tag."""
    subprocess.run(["git", "add", "pyproject.toml", "docs/CHANGELOG.md"], check=True)
    subprocess.run(["git", "commit", "-m", f"Release {version}"], check=True)
    tag = f"v{version}"
    subprocess.run(["git", "tag", tag], check=True)
    print(tag)


def main() -> None:
    parser = argparse.ArgumentParser(description="SentientOS release manager")
    parser.add_argument("--version", required=True, help="Version number x.y.z")
    parser.add_argument("--changelog", default="docs/CHANGELOG.md", help="Changelog file")
    args = parser.parse_args()

    project_file = Path("pyproject.toml")
    if not project_file.exists():
        print("pyproject.toml not found")
        return

    changelog = Path(args.changelog)
    if not changelog.exists():
        print(f"Changelog not found: {changelog}")
        return

    update_version(args.version, project_file)
    prepend_changelog(args.version, changelog)
    commit_and_tag(args.version)


if __name__ == "__main__":
    main()
