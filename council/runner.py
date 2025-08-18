"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from typing import List
from .bus import Bus
from .schema import Message
from .referee import Referee
from .adapters.openai_adapter import OpenAIAdapter
from .adapters.deepseek_adapter import DeepSeekAdapter
from .adapters.mistral_adapter import MistralAdapter

def run(seed: str, rounds: int = 2) -> List[Message]:
    bus = Bus()
    ref = Referee(bus, max_rounds=rounds)
    agents = [OpenAIAdapter(), DeepSeekAdapter(), MistralAdapter()]

    bus.publish(Message(agent="referee", role="referee", content=seed, round=0, kind="seed"))

    for r in range(1, rounds + 1):
        for a in agents:
            bus.publish(Message(agent=a.name, role="agent", content=a.answer(seed), round=r, kind="answer"))
        last = [m for m in bus.history() if m.round == r and m.kind == "answer"]
        for a in agents:
            for m in last:
                if m.agent != a.name:
                    bus.publish(Message(agent=a.name, role="agent", content=a.critique(m.content), round=r, kind="critique"))
        if ref.stable(last):
            break

    return bus.history()
