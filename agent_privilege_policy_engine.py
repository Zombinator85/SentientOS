from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

"""Agent Privilege Policy Engine

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
# Templates and code patterns co-developed with OpenAI support
"""

require_admin_banner()
require_lumos_approval()

from logging_config import get_log_path

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from cathedral_const import log_json

LOG_PATH = get_log_path("privilege_policy.jsonl", "PRIVILEGE_POLICY_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
AGENTS_FILE = Path("AGENTS.md")


class PrivilegePolicyEngine:
    """Parse AGENTS.md and enforce privilege rules."""

    def __init__(self, agents_path: Path = AGENTS_FILE) -> None:
        self.agents_path = agents_path
        self.privileges: Dict[str, List[str]] = {}
        self.load()

    def load(self) -> None:
        text = self.agents_path.read_text(encoding="utf-8")
        blocks = re.findall(r"```(.*?)```", text, re.DOTALL)
        privs: Dict[str, List[str]] = {}
        for block in blocks:
            name_match = re.search(r"Name:\s*(.+)", block)
            priv_match = re.search(r"Privileges:\s*(.+)", block)
            if name_match and priv_match:
                name = name_match.group(1).strip()
                priv = [p.strip() for p in priv_match.group(1).split(',')]
                privs[name] = priv
        self.privileges = privs

    def check(self, agent: str, action: str) -> bool:
        allowed = action in self.privileges.get(agent, [])
        self._log(agent, action, allowed)
        return allowed

    def _log(self, agent: str, action: str, allowed: bool) -> None:
        data = {
            "agent": agent,
            "action": action,
            "result": "allowed" if allowed else "denied",
        }
        log_json(LOG_PATH, {"timestamp": datetime.utcnow().isoformat(), "data": data})


def cli() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Privilege Policy Engine")
    ap.add_argument("agent")
    ap.add_argument("action")
    ap.add_argument("--reload", action="store_true")
    args = ap.parse_args()
    engine = PrivilegePolicyEngine()
    if args.reload:
        engine.load()
    ok = engine.check(args.agent, args.action)
    print(json.dumps({"allowed": ok}, indent=2))


if __name__ == "__main__":  # pragma: no cover
    cli()
