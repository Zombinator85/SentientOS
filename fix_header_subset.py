#!/usr/bin/env python3
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

import argparse
import re
from pathlib import Path

HEADER_LINES = [
    "from __future__ import annotations",
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


def process_file(path: Path) -> None:
    ascii_lines = {
        line.strip()
        for line in Path("BANNER_ASCII.txt").read_text(encoding="utf-8").splitlines()
    }
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
        if stripped in ascii_lines:
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

    require_admin_banner()
    require_lumos_approval()
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix header for a subset of files")
    parser.add_argument("--filelist", required=True, help="File containing list of files to process")
    args = parser.parse_args()

    paths = [Path(p.strip()) for p in Path(args.filelist).read_text().splitlines() if p.strip()]
    for p in paths:
        if p.is_file():
            process_file(p)


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
