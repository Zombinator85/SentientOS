"""SentientOS package entrypoint."""
from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from . import __version__  # noqa: E402

if TYPE_CHECKING:
    # Place type-only imports here in the future
    pass


def main() -> None:
    """Entry point for the SentientOS package."""

    if len(sys.argv) > 1 and sys.argv[1] == "dashboard":
        from sentientos.cli.dashboard_cli import main as dashboard_main

        raise SystemExit(dashboard_main(sys.argv[2:]))

    print(f"SentientOS {__version__}\nRun 'support' or 'ritual' for CLI tools.")


if __name__ == "__main__":  # pragma: no cover - CLI invocation
    main()
