from __future__ import annotations

import pathlib
import re

DOCSTRING = '"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""'
FUTURE_LINE = "from __future__ import annotations"
REQUIRE_ADMIN = "require_admin_banner()"
REQUIRE_LUMOS = "require_lumos_approval()"

REMOVE_LINES = {
    DOCSTRING,
    "\"\"\"Privilege Banner: requires admin & Lumos approval.\"\"\"",
    REQUIRE_ADMIN,
    REQUIRE_LUMOS,
    "# \ud83d\udd17 Privilege ritual migrated 2025-06-07 by Cathedral decree.",
}

HEADER = [DOCSTRING, FUTURE_LINE, REQUIRE_ADMIN, REQUIRE_LUMOS]


IMPORT_RE = re.compile(r"^(?:from\s+\S+\s+import|import)\b")


def process_file(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8").splitlines()
    imports: list[str] = []
    body: list[str] = []
    i = 0
    while i < len(text):
        line = text[i]
        stripped = line.strip()
        if stripped in REMOVE_LINES or stripped == FUTURE_LINE:
            i += 1
            continue
        if IMPORT_RE.match(line):
            block = [line.rstrip()]
            open_paren = line.count("(") - line.count(")")
            continued = line.rstrip().endswith("\\")
            i += 1
            while i < len(text) and (open_paren > 0 or continued):
                l2 = text[i]
                if l2.strip() in REMOVE_LINES or l2.strip() == FUTURE_LINE:
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


def main() -> None:
    entry_list = pathlib.Path("entrypoints.txt").read_text().splitlines()
    for p in entry_list:
        path = pathlib.Path(p.strip())
        if path.is_file():
            process_file(path)


if __name__ == "__main__":  # pragma: no cover
    main()
