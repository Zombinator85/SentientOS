"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
from __future__ import annotations

from admin_utils import require_admin_banner, require_lumos_approval
import sys

from privilege_lint_cli import main

if __name__ == "__main__":
    sys.exit(main())
