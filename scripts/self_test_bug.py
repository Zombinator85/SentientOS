"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details.

Introduce a trivial bug into the repository for Codex dry-run testing.

This script flips the admin check in ``admin_utils.is_admin`` so that it always
reports lack of privilege. The failing tests should trigger the Codex daemon to
attempt self-repair on the next cycle.
"""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "admin_utils.py"
MARKER = "geteuid() == 0"
BUGGED = "geteuid() != 0"


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    if BUGGED in text:
        print("Bug already injected.")
        return
    if MARKER not in text:
        raise SystemExit("Marker not found; admin_utils implementation changed.")
    TARGET.write_text(text.replace(MARKER, BUGGED), encoding="utf-8")
    print("Injected self-test bug into admin_utils.is_admin")


if __name__ == "__main__":
    main()
