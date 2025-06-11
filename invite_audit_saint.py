"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
from admin_utils import require_admin_banner, require_lumos_approval

import sys
from pathlib import Path


def add_saint(name: str) -> None:
    """Append *name* to the Audit Saints section in CONTRIBUTORS.md."""
    path = Path("CONTRIBUTORS.md")
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and line.strip().startswith("First-timers"):
            out.append(f"- {name}")
            inserted = True
    if not inserted:
        out.extend(["", "## Audit Saints", f"- {name}"])
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(
        f"Thank you for joining the cathedral healing ritual—{name} is now etched in CONTRIBUTORS.md."
    )


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python invite_audit_saint.py NAME")
        sys.exit(1)
    add_saint(" ".join(sys.argv[1:]))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
