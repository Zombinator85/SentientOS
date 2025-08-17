"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from typing import Dict, Literal
Decision = Literal["deny","respond","initiate"]

def should_talk(context: Dict, cfg: Dict) -> Decision:
    if not cfg.get("enabled", True):
        return "deny"
    if context.get("incoming_request", False):
        return "respond"
    triggers = set(cfg.get("initiation", {}).get("triggers", []))
    hit = any(context.get(t, False) for t in triggers)
    return "initiate" if hit else "deny"
