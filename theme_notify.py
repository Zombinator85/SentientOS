import random
from datetime import datetime

import daily_theme

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
