"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
try:
    from colorama import init as _init, Fore, Style
    _init()
except Exception:  # colorama missing or failed
    def _init() -> None:
        pass

    class _Colors:
        BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = ""

    class _Style:
        RESET_ALL = ""

    Fore = _Colors()
    Style = _Style()

init = _init
__all__ = ["init", "Fore", "Style"]
