from __future__ import annotations
from pathlib import Path
import shutil
import argparse
from datetime import datetime

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()
require_lumos_approval()


HEADER_TEMPLATE = (
    '"""Privilege Banner: This script requires admin and Lumos approval."""\n'
    'require_admin_banner()\n'
    'require_lumos_approval()\n'
    '# \U0001f56f\ufe0f Privilege ritual migrated {today} by Cathedral decree.\n'
)

ADMIN_IMPORT = (
    "from admin_utils import require_admin_banner, require_lumos_approval\n"
)


def inject_banner(file_path: Path) -> None:
    if not file_path.exists():
        print(f"File not found: {file_path}")
        return
    backup_path = file_path.with_suffix(file_path.suffix + ".bak")
    shutil.copy2(file_path, backup_path)

    text = file_path.read_text(encoding="utf-8").splitlines()
    shebang = ""
    if text and text[0].startswith("#!"):
        shebang = text.pop(0) + "\n"

    imports = []
    remaining = []
    for line in text:
        stripped = line.lstrip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            imports.append(line)
        else:
            remaining.append(line)

    if ADMIN_IMPORT.strip() not in [imp.strip() for imp in imports]:
        imports.insert(0, ADMIN_IMPORT.rstrip("\n"))

    header = HEADER_TEMPLATE.format(today=datetime.utcnow().date().isoformat())
    new_lines = []
    if shebang:
        new_lines.append(shebang.rstrip("\n"))
    new_lines.append(header.rstrip("\n"))
    new_lines.extend(imports)
    new_lines.extend(remaining)

    file_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"Updated {file_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inject privilege banner into multiple Python scripts"
    )
    parser.add_argument(
        "file_list",
        help="Text file containing newline separated file paths to process",
    )
    args = parser.parse_args()
    file_list_path = Path(args.file_list)
    if not file_list_path.exists():
        print(f"List file not found: {file_list_path}")
        return
    for line in file_list_path.read_text(encoding="utf-8").splitlines():
        path = Path(line.strip())
        if path.suffix == "":
            continue
        inject_banner(path)


if __name__ == "__main__":
    main()
