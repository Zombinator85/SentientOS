from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List

from logging_config import get_log_dir

AGENTS_FILE = Path(__file__).resolve().parent.parent / "AGENTS.md"


@dataclass(slots=True)
class ThreatAgent:
    name: str
    type: str
    roles: List[str]
    privileges: List[str]
    origin: str
    logs: str
    risk_score: int
    scenarios: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": self.type,
            "roles": self.roles,
            "privileges": self.privileges,
            "origin": self.origin,
            "logs": self.logs,
            "risk_score": self.risk_score,
            "scenarios": self.scenarios,
        }


@dataclass(slots=True)
class ThreatModel:
    agents: List[ThreatAgent]
    generated_from: Path

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_from": str(self.generated_from),
            "agent_count": len(self.agents),
            "agents": [agent.to_dict() for agent in self.agents],
        }

    def write(self, path: Path | None = None) -> Path:
        target = path or get_log_dir() / "security_threat_model.json"
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return target


_PRIVILEGE_WEIGHTS = {
    "control": 4,
    "write": 3,
    "update": 3,
    "federate": 3,
    "merge": 3,
    "broadcast": 2,
    "vote": 2,
    "bless": 2,
    "animate": 2,
    "export": 1,
    "log": 1,
    "display": 1,
    "compare": 1,
    "inspect": 2,
}


_ROLE_HINTS = {
    "Quarantine": "Can isolate or suspend other presences if compromised.",
    "Federation": "Able to bridge external networks; monitor for credential drift.",
    "Dashboard": "Surfaces privileged data to humans; review access throttles.",
    "Compiler": "Builds doctrine artifacts; verify supply chain integrity.",
    "Daemon": "Runs unattended; ensure watchdogs monitor long-lived behavior.",
    "Service": "Likely interacts with memory stores; enforce strict logging.",
    "CLI": "Human-invoked but powerful; ensure privilege rituals remain enforced.",
}


def _extract_blocks(text: str) -> Iterable[dict[str, str]]:
    block: dict[str, str] = {}
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if inside and block:
                yield block
                block = {}
            inside = not inside
            continue
        if not inside or not stripped:
            continue
        if stripped.startswith("- Name:"):
            key, value = stripped.split(":", 1)
            block["Name"] = value.strip()
            continue
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            block[key.strip()] = value.strip()
    if inside and block:
        yield block


def _split_csv(value: str) -> List[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _score_privileges(privileges: Iterable[str]) -> int:
    score = 0
    for privilege in privileges:
        score += _PRIVILEGE_WEIGHTS.get(privilege.lower(), 1)
    return score


def _synthesize_scenarios(name: str, roles: Iterable[str], privileges: Iterable[str]) -> List[str]:
    scenarios: List[str] = []
    for role in roles:
        for hint_key, hint in _ROLE_HINTS.items():
            if hint_key.lower() in role.lower():
                scenarios.append(f"Role insight — {hint}")
                break
    privs = [p.lower() for p in privileges]
    if {"control", "federate"} & set(privs):
        scenarios.append(
            "High leverage privileges detected. Ensure changes to external systems are double-signed in audit logs."
        )
    if "log" not in privs:
        scenarios.append("Agent lacks explicit logging privilege; confirm secondary witnesses exist.")
    if "export" in privs and "federate" in privs:
        scenarios.append("Exports combined with federation could leak private lore; enforce consent banners.")
    if not scenarios:
        scenarios.append("No elevated threat beyond standard logging detected.")
    return scenarios


def build_threat_model(path: Path | None = None) -> ThreatModel:
    agents_path = path or AGENTS_FILE
    text = agents_path.read_text(encoding="utf-8")
    agents: List[ThreatAgent] = []
    for block in _extract_blocks(text):
        name = block.get("Name")
        if not name:
            continue
        roles = _split_csv(block.get("Roles", ""))
        privileges = _split_csv(block.get("Privileges", ""))
        agent = ThreatAgent(
            name=name,
            type=block.get("Type", "unknown"),
            roles=roles,
            privileges=privileges,
            origin=block.get("Origin", "unknown"),
            logs=block.get("Logs", ""),
            risk_score=_score_privileges(privileges),
            scenarios=_synthesize_scenarios(name, roles, privileges),
        )
        agents.append(agent)
    return ThreatModel(agents=agents, generated_from=Path(agents_path))
