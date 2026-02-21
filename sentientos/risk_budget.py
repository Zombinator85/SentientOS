from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Literal

from sentientos.event_stream import record_forge_event

Posture = Literal["stability", "balanced", "velocity"]
OperatingMode = Literal["normal", "cautious", "recovery", "lockdown"]


@dataclass(slots=True)
class RiskBudget:
    schema_version: int = 1
    created_at: str = ""
    posture: Posture = "balanced"
    pressure_level: int = 0
    operating_mode: OperatingMode = "normal"
    quarantine_active: bool = False
    router_k_max: int = 4
    router_m_max: int = 2
    router_allow_escalation: bool = True
    forge_max_files_changed: int = 160
    forge_max_runs_per_hour: int = 2
    forge_max_runs_per_day: int = 4
    forge_max_retries: int = 1
    allow_automerge: bool = False
    allow_publish: bool = True
    allow_federation_adopt: bool = True
    notes: list[str] | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["notes"] = list(self.notes or [])
        return payload


def derive_risk_budget(*, posture: Posture, pressure_level: int, operating_mode: str, quarantine_active: bool) -> RiskBudget:
    mode = _normalize_mode(operating_mode)
    notes: list[str] = []
    budget = RiskBudget(
        created_at=_iso_now(),
        posture=posture,
        pressure_level=max(0, min(int(pressure_level), 3)),
        operating_mode=mode,
        quarantine_active=bool(quarantine_active),
        notes=notes,
    )

    if mode == "normal":
        if posture == "stability":
            budget.router_k_max = 3
            budget.router_m_max = 1
            budget.router_allow_escalation = False
            budget.forge_max_files_changed = 80
            budget.forge_max_runs_per_hour = 1
            budget.forge_max_runs_per_day = 2
            budget.forge_max_retries = 0
            budget.allow_automerge = False
        elif posture == "velocity":
            budget.router_k_max = 6
            budget.router_m_max = 3
            budget.router_allow_escalation = True
            budget.forge_max_files_changed = 260
            budget.forge_max_runs_per_hour = 3
            budget.forge_max_runs_per_day = 8
            budget.forge_max_retries = 2
            budget.allow_automerge = True
        else:
            budget.router_k_max = 4
            budget.router_m_max = 2
            budget.router_allow_escalation = True
            budget.forge_max_files_changed = 160
            budget.forge_max_runs_per_hour = 2
            budget.forge_max_runs_per_day = 4
            budget.forge_max_retries = 1
            budget.allow_automerge = True
        budget.allow_publish = True
        budget.allow_federation_adopt = True
    elif mode == "cautious":
        budget.router_k_max = 3
        budget.router_m_max = 1
        budget.router_allow_escalation = posture == "velocity" and budget.pressure_level == 0
        budget.forge_max_files_changed = 60
        budget.forge_max_runs_per_hour = 1
        budget.forge_max_runs_per_day = 2
        budget.forge_max_retries = 1
        budget.allow_automerge = False
        budget.allow_publish = False
        budget.allow_federation_adopt = True
        notes.append("cautious_mode_clamps")
    elif mode == "recovery":
        budget.router_k_max = 2
        budget.router_m_max = 1
        budget.router_allow_escalation = False
        budget.forge_max_files_changed = 20
        budget.forge_max_runs_per_hour = 1
        budget.forge_max_runs_per_day = 1
        budget.forge_max_retries = 0
        budget.allow_automerge = False
        budget.allow_publish = False
        budget.allow_federation_adopt = False
        notes.append("recovery_mode_clamps")
    else:
        budget.router_k_max = 1
        budget.router_m_max = 0
        budget.router_allow_escalation = False
        budget.forge_max_files_changed = 0
        budget.forge_max_runs_per_hour = 0
        budget.forge_max_runs_per_day = 0
        budget.forge_max_retries = 0
        budget.allow_automerge = False
        budget.allow_publish = False
        budget.allow_federation_adopt = False
        notes.append("lockdown_mode_clamps")

    if quarantine_active:
        budget.router_k_max = 1
        budget.router_m_max = 0
        budget.router_allow_escalation = False
        budget.forge_max_files_changed = 0
        budget.forge_max_runs_per_hour = 0
        budget.forge_max_runs_per_day = 0
        budget.forge_max_retries = 0
        budget.allow_automerge = False
        budget.allow_publish = False
        budget.allow_federation_adopt = False
        notes.append("quarantine_override_clamps")

    return budget


def compute_risk_budget(*, repo_root: Path, posture: Posture, pressure_level: int, operating_mode: str, quarantine_active: bool) -> RiskBudget:
    budget = derive_risk_budget(
        posture=posture,
        pressure_level=pressure_level,
        operating_mode=operating_mode,
        quarantine_active=quarantine_active,
    )
    force_path = os.getenv("SENTIENTOS_RISK_BUDGET_FORCE_JSON")
    if force_path:
        allow = os.getenv("SENTIENTOS_RISK_BUDGET_ALLOW_OVERRIDE") == "1"
        if not allow:
            note = f"override_rejected:{force_path}"
            budget.notes = [*list(budget.notes or []), note]
            record_forge_event({"event": "risk_budget_override_rejected", "level": "warning", "path": force_path})
        else:
            override = _load_override(Path(force_path), base=budget)
            override.notes = [*list(override.notes or []), f"override_applied:{force_path}"]
            budget = override
            record_forge_event({"event": "risk_budget_override_applied", "level": "warning", "path": force_path})
    persist_risk_budget(repo_root=repo_root, budget=budget)
    return budget


def persist_risk_budget(*, repo_root: Path, budget: RiskBudget) -> None:
    root = repo_root.resolve()
    latest = root / "glow/forge/risk_budget.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    payload = budget.to_dict()
    latest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    pulse_path = root / "pulse/risk_budgets.jsonl"
    pulse_path.parent.mkdir(parents=True, exist_ok=True)
    with pulse_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def risk_budget_summary(budget: RiskBudget) -> dict[str, object]:
    return {
        "router_k_max": budget.router_k_max,
        "router_m_max": budget.router_m_max,
        "allow_escalation": budget.router_allow_escalation,
        "allow_automerge": budget.allow_automerge,
        "allow_publish": budget.allow_publish,
    }


def _load_override(path: Path, *, base: RiskBudget) -> RiskBudget:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base
    if not isinstance(payload, dict):
        return base
    merged = base.to_dict()
    merged.update({k: v for k, v in payload.items() if k in merged})
    merged["notes"] = [str(item) for item in merged.get("notes", []) if isinstance(item, str)]
    try:
        return RiskBudget(**merged)
    except TypeError:
        return base


def _normalize_mode(mode: str) -> OperatingMode:
    lowered = str(mode).strip().lower()
    if lowered in {"normal", "cautious", "recovery", "lockdown"}:
        return lowered  # type: ignore[return-value]
    return "normal"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
