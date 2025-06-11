import random
from pathlib import Path

import daily_theme


from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
def random_theme() -> str:
    theme = random.choice(daily_theme.THEMES)
    print(theme)
    return theme


if __name__ == "__main__":
    random_theme()
