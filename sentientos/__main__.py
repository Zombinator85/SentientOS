"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
from typing import TYPE_CHECKING
from . import __version__
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

if TYPE_CHECKING:
    from admin_utils import require_admin_banner, require_lumos_approval
else:
    from admin_utils import require_admin_banner, require_lumos_approval


def main() -> None:
    print(f"SentientOS {__version__}\nRun 'support' or 'ritual' for CLI tools.")


if __name__ == "__main__":
    main()
