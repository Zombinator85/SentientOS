"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
from sentient_banner import BANNER_LINES


import argparse
import re
import shutil
from pathlib import Path
from typing import Iterable, List

ENTRYPOINTS_FILE = Path("entrypoints.txt")

DOCSTRING = BANNER_LINES[0].strip('"')
OLD_DOCSTRING = "Sanctuary Privilege Ritual: Do not remove. See doctrine for details."
HEADER_LINES = [BANNER_LINES[0], BANNER_LINES[1], BANNER_LINES[2]]
IMPORT_LINE = "from admin_utils import require_admin_banner, require_lumos_approval"
AUTO_APPROVE_IMPORT = "from scripts.auto_approve import prompt_yes_no"
PROMPT_RE = re.compile(r"(?<!prompt_yes_no)\b(?:input|click\.confirm|prompt)\(")
ENTRY_RE = re.compile(r"if __name__ == ['\"]__main__['\"]")

"""CLI tool to enforce privilege banners and migrate interactive prompts."""


class FileReport:
    """Keep track of issues and modifications for a file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.issues: List[str] = []
        self.modified = False


def _first_code_line(lines: List[str]) -> int:
    """Return index of the first non-import code line."""
    idx = 0
    if idx < len(lines) and lines[idx].startswith("#!"):
        idx += 1
    if idx < len(lines) and re.match(r"#.*coding[:=]", lines[idx]):
        idx += 1
    while idx < len(lines) and (not lines[idx].strip() or lines[idx].strip().startswith("#")):
        idx += 1
    while idx < len(lines) and (
        lines[idx].startswith("import ") or lines[idx].startswith("from ")
    ):
        idx += 1
    while idx < len(lines) and (not lines[idx].strip() or lines[idx].strip().startswith("#")):
        idx += 1
    return idx


def _has_banner(lines: List[str]) -> bool:
    """Return True if the banner appears at the first code line."""
    idx = _first_code_line(lines)
    for expected in HEADER_LINES:
        if idx >= len(lines) or lines[idx].strip() != expected:
            return False
        idx += 1
    return True


def _fix_banner(lines: List[str]) -> List[str]:
    """Return file lines with the privilege banner inserted."""
    shebang = ""
    if lines and lines[0].startswith("#!"):
        shebang = lines.pop(0)
    encoding = ""
    if lines and re.match(r"#.*coding[:=]", lines[0]):
        encoding = lines.pop(0)
    imports = [l for l in lines if l.startswith("import ") or l.startswith("from ")]
    body = [
        l
        for l in lines
        if l not in imports
        and l.strip() not in {
            DOCSTRING,
            OLD_DOCSTRING,
            "require_admin_banner()",
            "require_lumos_approval()",
            IMPORT_LINE,
            BANNER_LINES[3],
        }
    ]
    new_lines: List[str] = []
    if shebang:
        new_lines.append(shebang)
    if encoding:
        new_lines.append(encoding)
    if IMPORT_LINE in imports:
        imports.remove(IMPORT_LINE)
    new_lines.append(IMPORT_LINE)
    new_lines.extend(HEADER_LINES)
    new_lines.append(BANNER_LINES[3])
    new_lines.extend(imports)
    new_lines.extend(body)
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


def _is_entrypoint(lines: List[str]) -> bool:
    return any(ENTRY_RE.search(l) for l in lines)


def process_file(path: Path, mode: str, backup_dir: Path | None) -> FileReport:
    report = FileReport(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        report.issues.append(f"read error: {exc}")
        return report

    if not _has_banner(lines):
        report.issues.append("missing banner after imports")
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
    result: List[Path] = []
    for p in files:
        if not p.is_file() or p.name == "__init__.py":
            continue
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        if _is_entrypoint(lines):
            result.append(p)
    return result


def read_entrypoints() -> List[Path]:
    if ENTRYPOINTS_FILE.exists():
        return [Path(line.strip()) for line in ENTRYPOINTS_FILE.read_text().splitlines() if line.strip()]
    return []


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
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Run in fix mode (same as --mode fix)",
    )
    args = parser.parse_args(argv)

    if args.fix:
        args.mode = "fix"

    files = read_entrypoints()
    if not files:
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
