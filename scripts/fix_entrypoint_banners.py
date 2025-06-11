#!/usr/bin/env python3
"""Rewrite CLI/daemon entry points to standard banner format."""
from __future__ import annotations

import pathlib
import re
import sys

DOCSTRING = '"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""'
FUTURE_LINE = "from __future__ import annotations"
REQUIRE_ADMIN = "require_admin_banner()"
REQUIRE_LUMOS = "require_lumos_approval()"

REMOVE_LINES = {
    DOCSTRING,
    "\"\"\"Privilege Banner: requires admin & Lumos approval.\"\"\"",
    REQUIRE_ADMIN,
    REQUIRE_LUMOS,
    "# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.",
    "#  _____  _             _",
    "# |  __ \\| |           (_)",
    "# | |__) | |_   _  __ _ _ _ __   __ _",
    "# |  ___/| | | | |/ _` | | '_ \\ / _` |",
    "# | |    | | |_| | (_| | | | | | (_| |",
    "# |_|    |_\\__,_|\\__, |_|_| |_|\\__, |",
    "#                  __/ |         __/ |",
    "#                 |___/         |___/",
}

DOCSTRING_RE = re.compile(r'^"""Sanctuary Privilege Ritual: Do not remove\. See doctrine for details\."""')
IMPORT_RE = re.compile(r"^(?:from\s+\S+\s+import|import)\b")
HEADER = [DOCSTRING, FUTURE_LINE, REQUIRE_ADMIN, REQUIRE_LUMOS]


def process_file(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8").splitlines()
    imports: list[str] = []
    body: list[str] = []
    i = 0
    while i < len(text):
        line = text[i]
        stripped = line.strip()
        if stripped == FUTURE_LINE or stripped in REMOVE_LINES or DOCSTRING_RE.match(stripped):
            i += 1
            continue
        if IMPORT_RE.match(line):
            block = [line.rstrip()]
            open_paren = line.count("(") - line.count(")")
            continued = line.rstrip().endswith("\\")
            i += 1
            while i < len(text) and (open_paren > 0 or continued):
                l2 = text[i]
                l2_stripped = l2.strip()
                if l2_stripped == FUTURE_LINE or l2_stripped in REMOVE_LINES or DOCSTRING_RE.match(l2_stripped):
                    i += 1
                    continue
                block.append(l2.rstrip())
                open_paren += l2.count("(") - l2.count(")")
                continued = l2.rstrip().endswith("\\")
                i += 1
            imports.extend(block)
            continue
        body.append(line.rstrip())
        i += 1
    new_lines = HEADER + imports + body
    if new_lines != text:
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        entry_list = pathlib.Path("entrypoints.txt").read_text().splitlines()
    else:
        entry_list = argv
    for p in entry_list:
        path = pathlib.Path(p.strip())
        if path.is_file():
            process_file(path)


if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) > 1:
        main(sys.argv[1:])
    else:
        main()
