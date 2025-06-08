"""Sanctuary Privilege Banner: This script requires admin & Lumos approval."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import argparse
import re
import shutil
from pathlib import Path
from typing import Iterable, List

DOCSTRING = "Sanctuary Privilege Banner: This script requires admin & Lumos approval."
OLD_DOCSTRING = "Sanctuary Privilege Ritual: Do not remove. See doctrine for details."
IMPORT_LINE = "from admin_utils import require_admin_banner, require_lumos_approval"
AUTO_APPROVE_IMPORT = "from scripts.auto_approve import prompt_yes_no"
PROMPT_RE = re.compile(r"(?<!prompt_yes_no)\b(?:input|click\.confirm|prompt)\(")

"""CLI tool to enforce privilege banners and migrate interactive prompts."""


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
    """Return file lines with the privilege banner inserted."""
    shebang = ""
    if lines and lines[0].startswith("#!"):
        shebang = lines.pop(0)
    # remove existing banners or related imports
    cleaned = [
        l
        for l in lines
        if l.strip() not in {
            DOCSTRING,
            OLD_DOCSTRING,
            "require_admin_banner()",
            "require_lumos_approval()",
            IMPORT_LINE,
        }
    ]
    new_lines: List[str] = []
    if shebang:
        new_lines.append(shebang)
    # insert banner at the very top
    new_lines.append(DOCSTRING)
    new_lines.append(IMPORT_LINE)
    new_lines.append("require_admin_banner()")
    new_lines.append("require_lumos_approval()")
    new_lines.extend(cleaned)
    return new_lines


def _replace_prompts(lines: List[str]) -> List[str]:
    """Replace interactive prompts with ``prompt_yes_no``."""
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
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        report.issues.append(f"read error: {exc}")
        return report

    if not _has_banner(path):
        report.issues.append("missing banner at line 1")
        if mode == "fix":
            lines = _fix_banner(lines)
            report.modified = True

    prompt_lines = [i + 1 for i, l in enumerate(lines) if PROMPT_RE.search(l)]
    if prompt_lines:
        report.issues.append("interactive prompts at lines " + ", ".join(map(str, prompt_lines)))
        if mode == "fix":
            lines = _replace_prompts(lines)
            report.modified = True

    if report.modified:
        if backup_dir:
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"{path.name}.bak"
            if not backup_path.exists():
                shutil.copy2(path, backup_path)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return report


def expand_files(patterns: Iterable[str]) -> List[Path]:
    files: List[Path] = []
    for pat in patterns:
        files.extend(Path().glob(pat))
    return [p for p in files if p.is_file() and p.name != "__init__.py"]


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
        default=Path("backups"),
        help="Directory for backups when fixing files",
    )
    args = parser.parse_args(argv)

    files = expand_files(args.files)
    backup_dir = args.backup_dir if args.mode == "fix" else None
    reports = [process_file(f, args.mode, backup_dir) for f in files]

    issue_count = sum(bool(r.issues) for r in reports)
    modified = sum(r.modified for r in reports)

    for r in reports:
        if r.issues and args.mode == "check":
            print(f"{r.path}: {'; '.join(r.issues)}")

    print(
        f"Scanned {len(files)} files. Issues found: {issue_count}. Files fixed: {modified}."
    )

    return 0 if (args.mode == "fix" or issue_count == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
