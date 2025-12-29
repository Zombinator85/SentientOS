"""Helper utilities for orchestrating SentientOS routines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from agents.forms.ssa_disability_agent import SSADisabilityAgent, SSA827Prefill
from drift_report import generate_drift_report
from sentientos.consciousness.integration import cycle_gate_status
from sentientos.optional_deps import optional_dependency_report
from version_consensus import VersionConsensus
from vow_digest import canonical_vow_digest


def load_profile_json(path: str) -> dict:
    with open(Path(path), "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_bundle_json(bundle_dict: dict, path: str, *, approved: bool = False) -> dict:
    if not approved:
        return {"status": "approval_required"}

    with open(Path(path), "w", encoding="utf-8") as handle:
        json.dump(bundle_dict, handle, indent=2, sort_keys=True)
    return {"status": "saved", "path": str(path)}


def _load_ssa_symbols():
    from agents.forms.ssa_disability_agent import SSA827Prefill, SSADisabilityAgent

    return SSADisabilityAgent, SSA827Prefill


def compute_system_diagnostics() -> Dict[str, Any]:
    digest = canonical_vow_digest()
    vc = VersionConsensus(digest)
    drift = generate_drift_report(digest, digest)
    cycle_gate = cycle_gate_status()

    try:
        SSADisabilityAgent, SSA827Prefill = _load_ssa_symbols()
        ssa_summary = {
            "ssa_agent": SSADisabilityAgent.__name__,
            "pdf_prefill": SSA827Prefill.__name__,
            "review_bundle": True,
        }
    except ModuleNotFoundError as exc:
        ssa_summary = {
            "available": False,
            "error": "missing_optional_module",
            "module": exc.name,
        }

    return {
        "canonical_vow_digest": digest,
        "drift_report": drift,
        "cycle_gate": cycle_gate,
        "ssa_subsystems": ssa_summary,
        "optional_dependencies": optional_dependency_report(),
    }


__all__ = [
    "load_profile_json",
    "save_bundle_json",
    "compute_system_diagnostics",
    "SSADisabilityAgent",
    "SSA827Prefill",
]


def __getattr__(name: str):
    if name in {"SSADisabilityAgent", "SSA827Prefill"}:
        SSADisabilityAgent, SSA827Prefill = _load_ssa_symbols()
        return SSADisabilityAgent if name == "SSADisabilityAgent" else SSA827Prefill
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
