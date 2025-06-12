"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Custom feedback rule helpers."""
from __future__ import annotations
from typing import Dict, Any


def stress_confirmed(value: float, emotions: Dict[str, float], ctx: Dict[str, Any]) -> bool:
    """Return True if EEG or biosignal data also indicates stress."""
    eeg_beta = ctx.get("eeg", {}).get("beta", 0.0)
    heart = ctx.get("biosignals", {}).get("heart_rate", 0.0)
    return eeg_beta > ctx.get("beta_threshold", 0.6) or heart > ctx.get("hr_threshold", 100)
