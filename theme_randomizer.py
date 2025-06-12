"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import random
from pathlib import Path

import daily_theme


def random_theme() -> str:
    theme = random.choice(daily_theme.THEMES)
    print(theme)
    return theme


if __name__ == "__main__":
    random_theme()
