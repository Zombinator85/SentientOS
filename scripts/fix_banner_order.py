#!/usr/bin/env python3
"""Normalize privilege banners in CLI entrypoints."""
from __future__ import annotations

import argparse
import pathlib
import re
from typing import List

DOCSTRING = '"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""'
FUTURE_LINE = "from __future__ import annotations"
ADMIN_IMPORT = "from admin_utils import require_admin_banner, require_lumos_approval"
REQUIRE_ADMIN = "require_admin_banner()"
REQUIRE_LUMOS = "require_lumos_approval()"
OLD_DOCSTRING = '"""Privilege Banner: requires admin & Lumos approval."""'

ASCII_LINES = {
    line.strip() for line in pathlib.Path("BANNER_ASCII.txt").read_text().splitlines()
}
REMOVE_PREFIX = re.compile(r"# Privilege ritual migrated")
IMPORT_RE = re.compile(r"^(?:from\s+\S+\s+import|import)\b")


def read_entrypoints() -> List[pathlib.Path]:
    with open("entrypoints.txt", encoding="utf-8") as f:
        return [pathlib.Path(line.strip()) for line in f if line.strip()]


def _should_remove(line: str) -> bool:
    stripped = line.strip()
    if stripped in ASCII_LINES:
        return True
    if stripped in {DOCSTRING, OLD_DOCSTRING, REQUIRE_ADMIN, REQUIRE_LUMOS}:
        return True
    if "🕯️" in stripped:
        return True
    if REMOVE_PREFIX.search(stripped):
        return True
    if stripped.startswith("#  _____"):
        return True
    return False


def process_file(path: pathlib.Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()

    shebang = ""
    if lines and lines[0].startswith("#!"):
        shebang = lines.pop(0)

    encoding = ""
    if lines and re.match(r"#.*coding[:=]", lines[0]):
        encoding = lines.pop(0)

    imports: List[str] = []
    body: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped == FUTURE_LINE or _should_remove(line):
            i += 1
            continue
        if IMPORT_RE.match(line):
            block = [line.rstrip()]
            open_paren = line.count("(") - line.count(")")
            continued = line.rstrip().endswith("\\")
            i += 1
            while i < len(lines) and (open_paren > 0 or continued):
                nxt = lines[i]
                nxt_stripped = nxt.strip()
                if nxt_stripped == FUTURE_LINE or _should_remove(nxt):
                    i += 1
                    continue
                block.append(nxt.rstrip())
                open_paren += nxt.count("(") - nxt.count(")")
                continued = nxt.rstrip().endswith("\\")
                i += 1
            imports.extend(block)
            continue
        body = lines[i:]
        break

    body = [ln for ln in body if ln.strip() != FUTURE_LINE]

    new_lines: List[str] = []
    if shebang:
        new_lines.append(shebang)
    if encoding:
        new_lines.append(encoding)
    new_lines.append(DOCSTRING)
    new_lines.append(FUTURE_LINE)
    new_lines.extend(imports)
    new_lines.append(REQUIRE_ADMIN)
    new_lines.append(REQUIRE_LUMOS)
    new_lines.extend(body)

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"Fixed {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix privilege banner order")
    parser.parse_args()
    for file_path in read_entrypoints():
        if file_path.is_file():
            process_file(file_path)


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
