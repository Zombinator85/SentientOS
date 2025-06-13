"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from pathlib import Path
from typing import Dict
import yaml


def get_fallback_emotion_weights(profile_name: str) -> Dict[str, float]:
    """Return fallback emotion weights for ``profile_name``."""
    path = Path("profiles") / profile_name / "fallback_emotion.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): float(v) for k, v in data.items()}
    except Exception:
        pass
    return {}
