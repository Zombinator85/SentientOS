from __future__ import annotations
import re
from pathlib import Path

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

# Generate a summary of known errors and how to resolve them.

require_admin_banner()
require_lumos_approval()

RITUAL_DOC = Path("RITUAL_FAILURES.md")
AUDIT_DOC = Path("AUDIT_LOG_FIXES.md")
OUTPUT = Path("docs/ERROR_RESOLUTION_SUMMARY.md")

SCAR_RE = re.compile(r"^##\s*(.+)")


def parse_doc(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if not path.exists():
        return entries
    current_section = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        m = SCAR_RE.match(line)
        if m:
            current_section = m.group(1).strip()
            continue
        if "mismatch" in line.lower() or "deprecated" in line.lower():
            entries.append((current_section or path.name, line.strip()))
    return entries


def build_table(rows: list[tuple[str, str]]) -> str:
    header = [
        "# Error Resolution Summary",
        "",
        "| Scar Location | Issue | Next Step |",
        "|--------------|-------|-----------|",
    ]
    for loc, desc in rows:
        if "deprecated" in desc.lower():
            step = "See test_import_fixer for path update"
        else:
            step = "Legacy mismatch – no action"
        header.append(f"| {loc} | {desc} | {step} |")
    return "\n".join(header) + "\n"


def main() -> None:
    rows = parse_doc(RITUAL_DOC) + parse_doc(AUDIT_DOC)
    OUTPUT.write_text(build_table(rows), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
