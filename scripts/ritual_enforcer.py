"""CLI to enforce the Sanctuary privilege banner and migrate interactive prompts.

This tool can check Python files for compliance with the ritual banner and
replace interactive prompts with the auto-approval helper. In fix mode,
non-compliant files are patched and backups are written to the chosen directory.
"""

from __future__ import annotations

from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import argparse
import re
import shutil
from pathlib import Path
from typing import Iterable, List

# Canonical banner lines inserted before any imports or docstrings
BANNER_DOCSTRING = (
    """Sanctuary Privilege Banner: This script requires admin & Lumos approval."""
)
BANNER_IMPORT = "from admin_utils import require_admin_banner, require_lumos_approval"
BANNER_CALLS = ["require_admin_banner()", "require_lumos_approval()"]
AUTO_APPROVE_IMPORT = "from scripts.auto_approve import prompt_yes_no"

PROMPT_PATTERN = re.compile(r"\b(?:input|click\.confirm|prompt)\(")


class FileReport:
    """Collect information about a processed file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.issues: List[str] = []
        self.modified = False


def _has_banner(lines: List[str]) -> bool:
    """Return ``True`` if the canonical banner appears within the first few lines."""
    header = "\n".join(lines[:8])
    return (
        BANNER_DOCSTRING in header
        and BANNER_IMPORT in header
        and all(call in header for call in BANNER_CALLS)
    )


def _insert_banner(lines: List[str]) -> List[str]:
    """Insert the canonical banner if missing."""
    if _has_banner(lines):
        return lines

    shebang = []
    if lines and lines[0].startswith("#!"):
        shebang = [lines.pop(0)]

    # Remove existing misplaced banner pieces
    banner_elems = {BANNER_DOCSTRING, BANNER_IMPORT, *BANNER_CALLS}
    lines = [l for l in lines if l.strip() not in banner_elems]

    insert_at = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (
            stripped.startswith("from ")
            or stripped.startswith("import ")
            or stripped.startswith('"""')
            or stripped.startswith("'''")
        ):
            break
        if stripped:
            break
        insert_at = i + 1

    new_lines = []
    new_lines.extend(shebang)
    new_lines.extend(lines[:insert_at])
    new_lines.append(BANNER_DOCSTRING)
    new_lines.append(BANNER_IMPORT)
    new_lines.extend(BANNER_CALLS)
    new_lines.extend(lines[insert_at:])
    return new_lines


def _replace_prompts(lines: List[str]) -> List[str]:
    """Replace interactive prompts with ``prompt_yes_no``."""
    changed = False
    new_lines: List[str] = []
    for line in lines:
        if PROMPT_PATTERN.search(line):
            line = PROMPT_PATTERN.sub("prompt_yes_no(", line)
            changed = True
        new_lines.append(line)

    if changed and all(AUTO_APPROVE_IMPORT not in l for l in new_lines):
        # insert after banner calls
        idx = 0
        for i, l in enumerate(new_lines):
            if BANNER_CALLS[-1] in l:
                idx = i + 1
                break
        new_lines.insert(idx, AUTO_APPROVE_IMPORT)
    return new_lines


def process_file(path: Path, mode: str, backup_dir: Path | None) -> FileReport:
    """Check or fix a single file."""
    report = FileReport(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        report.issues.append("unreadable file")
        return report

    if "__init__.py" == path.name:
        return report

    if not _has_banner(lines):
        report.issues.append("missing banner")
        if mode == "fix":
            lines = _insert_banner(lines)
            report.modified = True

    if any(PROMPT_PATTERN.search(l) for l in lines):
        report.issues.append("interactive prompt")
        if mode == "fix":
            lines = _replace_prompts(lines)
            report.modified = True

    if report.modified:
        if backup_dir:
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / (path.name + ".bak")
            shutil.copy2(path, backup_path)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return report


def expand_files(patterns: Iterable[str]) -> List[Path]:
    """Resolve glob patterns to a list of files."""
    files: List[Path] = []
    for pat in patterns:
        files.extend(Path().rglob(pat))
    return [p for p in files if p.is_file()]


def main(argv: List[str] | None = None) -> int:
    """Entry point for the ritual enforcer CLI."""
    parser = argparse.ArgumentParser(
        description="Enforce privilege banners and migrate interactive prompts",
    )
    parser.add_argument(
        "--mode",
        choices=["check", "fix"],
        default="check",
        help="Run in check or fix mode",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=["**/*.py"],
        help="Glob patterns to scan",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path("backups"),
        help="Directory to store .bak files when fixing",
    )
    args = parser.parse_args(argv)

    files = expand_files(args.files)
    results = [process_file(f, args.mode, args.backup_dir) for f in files]

    total_issues = sum(bool(r.issues) for r in results)
    fixed = sum(r.modified for r in results)

    print(f"Scanned {len(files)} files; {total_issues} files need attention.")
    if args.mode == "fix":
        print(f"Patched {fixed} files.")

    return 1 if args.mode == "check" and total_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
