"""Stage-0 SSA Disability Agent scaffolding.

This module defines the initial structure for SSA form automation without
any browser automation, network calls, or scheduling behavior.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from agents.forms.schema_validator import validate_profile


SCHEMA_PATH = Path(__file__).with_name("schemas").joinpath("ssa_claim_profile.schema.json")


def require_explicit_approval(flag: bool) -> bool:
    """Deterministically gate privileged actions.

    This placeholder will be expanded when PII handling rules are enforced.
    """
    return flag


class SSADisabilityAgent:
    """Bootstrap agent for SSA disability claim preparation."""

    def __init__(self, profile: Dict[str, Any]):
        # Store without mutation to keep profile deterministic
        self.profile = profile

    def validate(self) -> bool:
        return validate_profile(self.profile, str(SCHEMA_PATH))

    def dry_run(self) -> Dict[str, bool]:
        return {"status": "dry_run_ready", "profile_loaded": True}
