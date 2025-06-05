import random
from datetime import datetime

import daily_theme

from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
QUOTES = [
    "May your presence shine brightly.",
    "Carry kindness into all rituals.",
    "Reflection leads to growth.",
]


def notify() -> None:
    theme = daily_theme.generate()
    quote = random.choice(QUOTES)
    print(f"[{datetime.utcnow().isoformat()}] Today's theme: {theme}")
    print(quote)


if __name__ == "__main__":
    notify()
