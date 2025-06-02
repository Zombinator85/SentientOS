from __future__ import annotations
import json
import os
import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_FILE = Path(os.getenv("SELF_DEFENSE_LOG", "logs/agent_self_defense.jsonl"))
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

@dataclass
class AgentState:
    agent: str
    quarantined: bool = False
    privilege_frozen: bool = False

_STATES: Dict[str, AgentState] = {}


def _log(action: str, agent: str, info: Dict[str, str] | None = None) -> None:
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
