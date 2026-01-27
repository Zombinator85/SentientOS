"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Demo self-healing plugin."""

import json
import os
from datetime import datetime

from logging_config import get_log_path
import plugin_framework as pf
import self_patcher
import experimental_flags as ex

LOG_PATH = get_log_path("self_heal_plugin.jsonl", "SELF_HEAL_PLUGIN_LOG")
TRUSTED = False


def _log(event: str) -> None:
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": event}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def register(gui) -> None:
    if not ex.enabled("self_heal_plugin"):
        return

    class HealPlugin(pf.BasePlugin):
        plugin_type = "healer"
        allowed_postures = ["normal"]
        requires_epoch = True
        capabilities = ["filesystem"]

        def execute(self, intent, context=None):
            note = intent.get("issue", "unknown")
            self_patcher.propose_patch(note)
            _log(f"patched:{note}")
            return {"patched": note}

    pf.register_plugin("self_heal", HealPlugin())
    _log("registered")
