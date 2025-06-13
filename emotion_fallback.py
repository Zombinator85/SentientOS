"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from pathlib import Path
from typing import Dict
import yaml

DEFAULT_WEIGHTS: Dict[str, Dict[str, float]] = {
    "default": {"Joy": 0.6, "Optimism": 0.4},
    "template": {"Joy": 0.6, "Optimism": 0.4},
}


def get_fallback_emotion_weights(profile_name: str) -> Dict[str, float]:
    """Return fallback emotion weights for ``profile_name``."""
    path = Path("profiles") / profile_name / "fallback_emotion.yaml"
    if not path.exists():
        return dict(DEFAULT_WEIGHTS.get(profile_name, DEFAULT_WEIGHTS.get("default", {})))
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return dict(DEFAULT_WEIGHTS.get(profile_name, DEFAULT_WEIGHTS.get("default", {})))
    return {str(k): float(v) for k, v in data.items()}
