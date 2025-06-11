#!/usr/bin/env python3
"""Rewrite CLI/daemon entry points to standard banner format."""
from __future__ import annotations

from pathlib import Path
import sys

BANNER = "\"\"\"Sanctuary Privilege Ritual: Do not remove. See doctrine for details.\"\"\""
CALL_ADMIN = (
    "require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine."
)
CALL_LUMOS = "require_lumos_approval()"


def rewrite_file(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    shebang = ""
    idx = 0
    if lines and lines[0].startswith("#!"):
        shebang = lines[0]
        idx = 1

    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    if idx < len(lines) and "Sanctuary Privilege Ritual" in lines[idx]:
        idx += 1

    # remove any header lines before the import block
    while idx < len(lines):
        stripped = lines[idx].strip()
        if (
            stripped.startswith("from __future__ import annotations")
            or stripped.startswith("require_admin_banner")
            or stripped.startswith("require_lumos_approval")
            or not stripped
        ):
            idx += 1
            continue
        break

    imports: list[str] = []
    start = idx
    while start < len(lines):
        stripped = lines[start].strip()
        if (
            stripped.startswith("import ")
            or stripped.startswith("from ")
            or not stripped
            or stripped.startswith("#")
        ):
            if stripped.startswith("from __future__ import annotations"):
                start += 1
                continue
            imports.append(lines[start])
            start += 1
            continue
        break

    idx = start
    rest = lines[idx:]
    while rest and not rest[0].strip():
        rest.pop(0)
    while rest and (
        rest[0].strip().startswith("require_admin_banner")
        or rest[0].strip().startswith("require_lumos_approval")
    ):
        rest.pop(0)

    out_lines: list[str] = []
    if shebang:
        out_lines.append(shebang)
    out_lines.append(BANNER)
    out_lines.append("from __future__ import annotations")
    out_lines.extend(imports)
    out_lines.append(CALL_ADMIN)
    out_lines.append(CALL_LUMOS)
    out_lines.extend(rest)
    text = "\n".join(out_lines)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def main(argv: list[str]) -> None:
    for p in argv:
        rewrite_file(Path(p))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: fix_entrypoint_banners.py <files>")
        raise SystemExit(1)
    main(sys.argv[1:])
