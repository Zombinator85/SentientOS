import random
from pathlib import Path

import daily_theme


def random_theme() -> str:
    theme = random.choice(daily_theme.THEMES)
    print(theme)
    return theme


if __name__ == "__main__":
    random_theme()
