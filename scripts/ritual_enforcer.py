from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()
require_lumos_approval()

import argparse
import os
import re
import shutil
from pathlib import Path
from typing import Iterable, List

DOCSTRING = "Sanctuary Privilege Ritual: Do not remove. See doctrine for details."
IMPORT_LINE = (
    "from admin_utils import require_admin_banner, require_lumos_approval"
)
AUTO_APPROVE_IMPORT = "from scripts.auto_approve import prompt_yes_no"
PROMPT_RE = re.compile(r"\binput\(")


class FileReport:
    """Keep track of issues and modifications for a file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.issues: List[str] = []
        self.modified = False


def _has_banner(path: Path) -> bool:
    """Return True if the file contains the ritual banner."""
    lines = path.read_text(encoding="utf-8").splitlines()
    header = "\n".join(lines[:20])
    return (
        DOCSTRING in header
        and "require_admin_banner()" in header
        and "require_lumos_approval()" in header
    )


def _fix_banner(lines: List[str]) -> List[str]:
    shebang = ""
    if lines and lines[0].startswith("#!"):
        shebang = lines.pop(0)
    lines = [
        l
        for l in lines
        if l.strip() not in {
            DOCSTRING,
            "require_admin_banner()",
            "require_lumos_approval()",
            IMPORT_LINE,
        }
    ]
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from ") or line.strip().startswith("\"\"\""):
            break
        if line.strip():
            break
        insert_idx = i + 1
    new_lines: List[str] = []
    if shebang:
        new_lines.append(shebang)
    new_lines.extend(lines[:insert_idx])
    new_lines.append(IMPORT_LINE)
    new_lines.append(DOCSTRING if DOCSTRING.startswith('"') else f'"{DOCSTRING}"')
    new_lines.append("require_admin_banner()")
    new_lines.append("require_lumos_approval()")
    new_lines.extend(lines[insert_idx:])
    return new_lines


def _replace_prompts(lines: List[str]) -> List[str]:
    has_import = any(AUTO_APPROVE_IMPORT in l for l in lines)
    new_lines: List[str] = []
    changed = False
    for line in lines:
        if PROMPT_RE.search(line):
            line = PROMPT_RE.sub("prompt_yes_no(", line)
            changed = True
        new_lines.append(line)
    if changed and not has_import:
        # insert auto_approve import after banner if present else at top
        insert_at = 0
        for i, line in enumerate(new_lines):
            if IMPORT_LINE in line:
                insert_at = i + 1
                break
        new_lines.insert(insert_at, AUTO_APPROVE_IMPORT)
    return new_lines


def process_file(path: Path, mode: str, backup_dir: Path | None) -> FileReport:
    report = FileReport(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    original = lines[:]

    if not _has_banner(path):
        report.issues.append("missing banner")
        if mode == "fix":
            lines = _fix_banner(lines)
            report.modified = True

    if any(PROMPT_RE.search(l) for l in lines):
        report.issues.append("interactive prompt")
        if mode == "fix":
            lines = _replace_prompts(lines)
            report.modified = True

    if report.modified:
        if backup_dir:
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"{path.name}.bak"
            shutil.copy2(path, backup_path)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return report


def expand_files(patterns: Iterable[str]) -> List[Path]:
    files: List[Path] = []
    for pat in patterns:
        files.extend(Path().glob(pat))
    return [p for p in files if p.is_file()]


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enforce ritual privilege headers and auto-approval prompts",
    )
    parser.add_argument(
        "--mode",
        choices=["check", "fix"],
        default="check",
        help="Check or fix files",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=["**/*.py"],
        help="Glob patterns of files to process",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help="Directory for backups when fixing files",
    )
    args = parser.parse_args(argv)

    files = expand_files(args.files)
    reports = [process_file(f, args.mode, args.backup_dir) for f in files]

    issues = sum(len(r.issues) > 0 for r in reports)
    modified = sum(r.modified for r in reports)

    print(f"Checked {len(files)} files, found {issues} with issues.")
    if args.mode == "fix":
        print(f"Modified {modified} files.")

    return 1 if issues and args.mode == "check" else 0


if __name__ == "__main__":
    raise SystemExit(main())
