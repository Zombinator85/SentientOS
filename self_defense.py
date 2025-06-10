from __future__ import annotations
from logging_config import get_log_path
import json
import os
import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Record quarantine actions and privilege freezes.

Entries are written to ``logs/agent_self_defense.jsonl`` or the path
provided by the ``SELF_DEFENSE_LOG`` environment variable. See
``docs/ENVIRONMENT.md`` for details.
"""

# uses SELF_DEFENSE_LOG if set, otherwise logs/agent_self_defense.jsonl
LOG_FILE = get_log_path("agent_self_defense.jsonl", "SELF_DEFENSE_LOG")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

@dataclass
class AgentState:
    agent: str
    quarantined: bool = False
    privilege_frozen: bool = False

_STATES: Dict[str, AgentState] = {}


def _log(action: str, agent: str, info: Dict[str, Any] | None = None) -> None:
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "action": action,
        "agent": agent,
        "info": info or {},
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def self_quarantine(agent: str, reason: str) -> AgentState:
    state = _STATES.setdefault(agent, AgentState(agent))
    state.quarantined = True
    _log("self_quarantine", agent, {"reason": reason})
    return state


def peer_quarantine(agent: str, sentinel: str, reason: str) -> AgentState:
    state = _STATES.setdefault(agent, AgentState(agent))
    state.quarantined = True
    _log("peer_quarantine", agent, {"sentinel": sentinel, "reason": reason})
    return state


def nullify_privilege(agent: str, sentinel: str) -> AgentState:
    state = _STATES.setdefault(agent, AgentState(agent))
    state.privilege_frozen = True
    _log("privilege_nullified", agent, {"sentinel": sentinel})
    return state


def broadcast_counterritual(signatories: List[str], message: str) -> None:
    if len(signatories) < 2:
        raise ValueError("counterritual requires quorum")
    _log("counterritual", "*", {"signatories": signatories, "message": message})


def status(agent: str) -> AgentState:
    return _STATES.setdefault(agent, AgentState(agent))


def cli() -> None:
    require_admin_banner()
    print("Self defense actions logged to", LOG_FILE)

if __name__ == "__main__":
    cli()
