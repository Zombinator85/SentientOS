"""Stage-1 SSA Disability Agent scaffolding.

This module defines deterministic structures for SSA form automation without
any browser automation, network calls, or scheduling behavior. Stage-1 adds
selector map loading and logical routing helpers while keeping interactions
purely structural.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from agents.forms.schema_validator import validate_profile
from agents.forms.selector_loader import get_page, load_selectors
from agents.forms import page_router


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
        selectors_path = Path(__file__).with_name("maps").joinpath("ssa_selectors.yaml")
        self.selectors = load_selectors(str(selectors_path))

    def validate(self) -> bool:
        return validate_profile(self.profile, str(SCHEMA_PATH))

    def dry_run(self) -> Dict[str, bool]:
        return {"status": "dry_run_ready", "profile_loaded": True}

    def get_page_structure(self, page: str) -> Dict[str, Any]:
        return get_page(page, self.selectors)

    def next_page(self, page: str) -> Optional[str]:
        return page_router.next_page(page)
