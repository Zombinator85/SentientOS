#!/usr/bin/env python3
from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()


import re
from pathlib import Path

HEADER_LINES = [
    "from __future__ import annotations",
    "",
    '"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""',
    "from sentientos.privilege import require_admin_banner, require_lumos_approval",
    "",
    "require_admin_banner()",
    "require_lumos_approval()",
    "",
]

FUTURE_RE = re.compile(r"^from __future__ import annotations")
BAN_RE = re.compile(r"^require_admin_banner\(\)")
LUMOS_RE = re.compile(r"^require_lumos_approval\(\)")

DOCSTRING = '"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""'
IMPORT_LINE = "from sentientos.privilege import require_admin_banner, require_lumos_approval"


def fix_file(path: Path) -> None:
    text = path.read_text().splitlines()
    shebang = None
    if text and text[0].startswith("#!"):
        shebang = text.pop(0)
    filtered = []
    for line in text:
        stripped = line.strip()
        if FUTURE_RE.match(stripped):
            continue
        if stripped == DOCSTRING:
            continue
        if stripped == IMPORT_LINE:
            continue
        if BAN_RE.match(stripped):
            continue
        if LUMOS_RE.match(stripped):
            continue
        filtered.append(line)

    new_lines = []
    if shebang:
        new_lines.append(shebang)
    new_lines.extend(HEADER_LINES)
    new_lines.extend(filtered)
    path.write_text("\n".join(new_lines) + "\n")


def main() -> None:
    for path in Path('.').rglob('*.py'):
        if path.is_file():
            fix_file(path)
    Path('tests/__init__.py').touch()


if __name__ == '__main__':
    main()
