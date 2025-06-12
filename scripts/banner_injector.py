"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()


import argparse
import ast
import shutil
from pathlib import Path

from sentient_banner import BANNER_LINES

IMPORT_LINE = "from sentientos.privilege import require_admin_banner, require_lumos_approval"

# CLI tool to inject the SentientOS privilege banner into Python files.





def inject_banner(path: Path) -> None:
    if not path.exists():
        print(f"File not found: {path}")
        return
    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)

    lines = path.read_text(encoding="utf-8").splitlines()
    shebang = ""
    if lines and lines[0].startswith("#!"):
        shebang = lines.pop(0)

    source = "\n".join(lines)
    tree = ast.parse(source)

    doc_line = None
    first_import_line = None
    import_ranges: list[int] = []
    for node in tree.body:
        if (
            doc_line is None
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            doc_line = node.lineno
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if first_import_line is None or node.lineno < first_import_line:
                first_import_line = node.lineno
            start = node.lineno
            end = getattr(node, "end_lineno", node.lineno)
            import_ranges.extend(range(start, end + 1))

    insertion_line = len(lines) + 1
    if doc_line is not None:
        insertion_line = doc_line
    if first_import_line is not None:
        insertion_line = min(insertion_line, first_import_line)

    imports = [
        lines[i - 1] for i in sorted(set(import_ranges)) if 0 <= i - 1 < len(lines)
    ]
    for i in sorted(set(import_ranges), reverse=True):
        if 0 <= i - 1 < len(lines):
            lines.pop(i - 1)

    removed_before = len([i for i in import_ranges if i <= insertion_line - 1])
    insertion_idx = max(0, insertion_line - 1 - removed_before)

    new_lines: list[str] = []
    if shebang:
        new_lines.append(shebang)
    new_lines.extend(lines[:insertion_idx])
    new_lines.append(IMPORT_LINE)
    new_lines.extend(BANNER_LINES)
    new_lines.extend(imports)
    new_lines.extend(lines[insertion_idx:])

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"Updated {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject privilege banner into files")
    parser.add_argument(
        "--files", nargs="+", required=True, help="Python files to modify"
    )
    args = parser.parse_args()

    for file_path in args.files:
        inject_banner(Path(file_path))


if __name__ == "__main__":
    main()
