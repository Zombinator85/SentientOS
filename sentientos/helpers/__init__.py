"""Helper utilities for orchestrating SentientOS routines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from agents.forms.ssa_disability_agent import SSADisabilityAgent
from agents.forms.ssa_disability_agent import SSA827Prefill  # re-export typing aid
from drift_report import generate_drift_report
from sentientos.consciousness.integration import cycle_gate_status
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


def compute_system_diagnostics() -> Dict[str, Any]:
    digest = canonical_vow_digest()
    vc = VersionConsensus(digest)
    drift = generate_drift_report(digest, digest)
    cycle_gate = cycle_gate_status()

    ssa_summary = {
        "ssa_agent": SSADisabilityAgent.__name__,
        "pdf_prefill": SSA827Prefill.__name__,
        "review_bundle": True,
    }

    return {
        "canonical_vow_digest": digest,
        "drift_report": drift,
        "cycle_gate": cycle_gate,
        "ssa_subsystems": ssa_summary,
    }


__all__ = [
    "load_profile_json",
    "save_bundle_json",
    "compute_system_diagnostics",
    "SSADisabilityAgent",
    "SSA827Prefill",
]
