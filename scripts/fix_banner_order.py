import argparse
import re
from pathlib import Path

HEADER_DOCSTRING = "\"\"\"Sanctuary Privilege Ritual: Do not remove. See doctrine for details.\"\"\""
ADMIN_IMPORT = "from admin_utils import require_admin_banner, require_lumos_approval"
ANNOTATIONS_IMPORT = "from __future__ import annotations"

REMOVE_PATTERNS = [
    re.compile(r'^#\s*_+'),
    re.compile(r'🕯️'),
    re.compile(r'Privilege ritual migrated'),
]
REDUNDANT_LINES = {
    '"""Privilege Banner: requires admin & Lumos approval."""',
    HEADER_DOCSTRING,
    "require_admin_banner()",
    "require_lumos_approval()",
    ADMIN_IMPORT,
}


def read_entrypoints() -> list[Path]:
    with open("entrypoints.txt", encoding="utf-8") as f:
        return [Path(line.strip()) for line in f if line.strip()]


def should_remove(line: str) -> bool:
    if line.strip() in REDUNDANT_LINES:
        return True
    return any(p.search(line) for p in REMOVE_PATTERNS)


def fix_file(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()

    shebang = ""
    if lines and lines[0].startswith("#!"):
        shebang = lines.pop(0)

    encoding = ""
    if lines and re.match(r"#.*coding[:=]", lines[0]):
        encoding = lines.pop(0)

    cleaned = [ln for ln in lines if not should_remove(ln)]

    idx = 0
    while idx < len(cleaned) and cleaned[idx].strip() == "":
        idx += 1

    future_imports: list[str] = []
    while idx < len(cleaned) and cleaned[idx].startswith("from __future__"):
        future_imports.append(cleaned[idx])
        idx += 1

    imports: list[str] = []
    while idx < len(cleaned) and (
        cleaned[idx].startswith("import ") or cleaned[idx].startswith("from ")
    ):
        imports.append(cleaned[idx])
        idx += 1

    rest = cleaned[idx:]

    future_imports = [ln for ln in future_imports if ln.strip() != ANNOTATIONS_IMPORT]
    future_imports.insert(0, ANNOTATIONS_IMPORT)

    result: list[str] = []
    if shebang:
        result.append(shebang)
    if encoding:
        result.append(encoding)
    result.append(HEADER_DOCSTRING)
    result.extend(future_imports)
    result.extend(imports)
    result.append("require_admin_banner()")
    result.append("require_lumos_approval()")
    result.extend(rest)

    path.write_text("\n".join(result) + "\n", encoding="utf-8")
    print(f"Fixed {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix privilege banner order")
    args = parser.parse_args()

    for file in read_entrypoints():
        fix_file(file)


if __name__ == "__main__":
    main()
