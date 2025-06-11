"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from typing import TYPE_CHECKING

from . import __version__

if TYPE_CHECKING:  # pragma: no cover - placeholder for optional imports
    pass


def main() -> None:
    """Entry point for the SentientOS package."""
    print(f"SentientOS {__version__}\nRun 'support' or 'ritual' for CLI tools.")


if __name__ == "__main__":  # pragma: no cover - CLI invocation
    main()
