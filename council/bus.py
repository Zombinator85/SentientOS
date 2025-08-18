"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from typing import List
from .schema import Message, as_dict
from pathlib import Path
import json

class Bus:
    def __init__(self) -> None:
        self._messages: List[Message] = []

    def publish(self, m: Message) -> None:
        self._messages.append(m)

    def history(self) -> List[Message]:
        return list(self._messages)

    def dump_jsonl(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for m in self._messages:
                f.write(json.dumps(as_dict(m), ensure_ascii=False) + "\n")
