"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
from pathlib import Path
from typing import List
import json

OCR_LOG = get_log_path("ocr_relay.jsonl")


def last_messages(n: int = 3) -> List[str]:
    if not OCR_LOG.exists():
        return []
    lines = OCR_LOG.read_text(encoding="utf-8").splitlines()
    msgs = []
    for line in reversed(lines):
        try:
            data = json.loads(line)
            msg = data.get("message")
            if msg:
                msgs.append(msg)
                if len(msgs) >= n:
                    break
        except Exception:
            continue
    return list(reversed(msgs))


def inject_prompt(prompt: str) -> str:
    msgs = last_messages(3)
    if not msgs:
        return prompt
    preamble = "VISUAL CONTEXT:\n" + "\n".join(msgs) + "\n\n"
    return preamble + prompt
