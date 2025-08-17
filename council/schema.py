"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from dataclasses import dataclass
from typing import Optional, Literal
import time

Role = Literal["system", "user", "assistant", "agent", "referee"]

@dataclass
class Message:
    agent: str
    role: Role
    content: str
    round: int
    timestamp: float = time.time()
    kind: Literal["answer","critique","synthesis","seed"] = "answer"

def as_dict(m: Message) -> dict:
    return {
        "agent": m.agent,
        "role": m.role,
        "content": m.content,
        "round": m.round,
        "timestamp": m.timestamp,
        "kind": m.kind,
    }
