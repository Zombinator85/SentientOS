"""Privilege validation sequence: do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import sys
from pathlib import Path
def add_contributor(name: str) -> None:
    """Append *name* to the Audit Contributors section in CONTRIBUTORS.md."""
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
        out.extend(["", "## Audit Contributors", f"- {name}"])
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(
        f"Contributor {name} recorded in CONTRIBUTORS.md as part of the audit support roster."
    )


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python invite_audit_saint.py NAME (adds audit contributor entry)")
        sys.exit(1)
    add_contributor(" ".join(sys.argv[1:]))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
