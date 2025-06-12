#!/usr/bin/env python3
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import argparse
import re
from pathlib import Path

ASCII_LINES = {line.strip() for line in Path("BANNER_ASCII.txt").read_text(encoding="utf-8").splitlines()}

HEADER_LINES = [
    '"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""',
    "from __future__ import annotations",
    "from sentientos.privilege import require_admin_banner, require_lumos_approval",
    "",
    "require_admin_banner()",
    "require_lumos_approval()",
]

ENCODING_RE = re.compile(r"#.*coding[:=]")
REMOVE_PATTERNS = [
    re.compile(r"Sanctuary Privilege Ritual"),
    re.compile(r"Privilege Banner"),
    re.compile(r"require_admin_banner"),
    re.compile(r"require_lumos_approval"),
    re.compile(r"sentientos\.privilege"),
    re.compile(r"Privilege ritual migrated"),
]

CHECKBOX_RE = re.compile(r"^- \[[ xX]\] (.*)$")


def process_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8").splitlines()
    idx = 0
    shebang = ""
    if text and text[0].startswith("#!"):
        shebang = text[0]
        idx = 1
    encoding = ""
    if idx < len(text) and ENCODING_RE.match(text[idx]):
        encoding = text[idx]
        idx += 1
    lines = text[idx:]

    body: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped in ASCII_LINES:
            continue
        if any(p.search(stripped) for p in REMOVE_PATTERNS):
            continue
        body.append(line)

    new_lines: list[str] = []
    if shebang:
        new_lines.append(shebang)
    if encoding:
        new_lines.append(encoding)
    new_lines.extend(HEADER_LINES)
    new_lines.extend(body)

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def parse_filelist(path: Path) -> list[Path]:
    lines = path.read_text(encoding="utf-8").splitlines()
    results: list[Path] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = CHECKBOX_RE.match(line)
        if m:
            line = m.group(1).strip()
        results.append(Path(line))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix header for a subset of files")
    parser.add_argument("--filelist", required=True, help="Markdown file listing files to fix")
    args = parser.parse_args()

    paths = parse_filelist(Path(args.filelist))
    for p in paths:
        if p.is_file():
            process_file(p)


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
