"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from typing import List
from .schema import Message
from .bus import Bus

class Referee:
    def __init__(self, bus: Bus, max_rounds: int = 2) -> None:
        self.bus = bus
        self.max_rounds = max_rounds

    def stable(self, last_round_msgs: List[Message]) -> bool:
        if not last_round_msgs:
            return True
        tokens = [m.content.split(" ", 1)[0] for m in last_round_msgs if m.content]
        return len(set(tokens)) == 1
