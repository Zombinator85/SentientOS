from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from pathlib import Path
from typing import Dict, Optional
import yaml

DEFAULT_PROFILES: Dict[str, Dict[str, float]] = {
    "hopeful": {"Joy": 0.6, "Optimism": 0.4},
    "analytical": {"Curiosity": 0.5, "Confident": 0.5},
    "fiery": {"Anger": 0.7, "Enthusiasm": 0.3},
}


def load_persona_config(path: str | Path | None = None) -> Dict[str, Dict[str, float]]:
    """Load persona emotion weights from ``path`` or return defaults."""
    if path is None:
        return dict(DEFAULT_PROFILES)
    fp = Path(path)
    if not fp.exists():
        return dict(DEFAULT_PROFILES)
    data = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return dict(DEFAULT_PROFILES)
    merged = dict(DEFAULT_PROFILES)
    for key, val in data.items():
        if isinstance(val, dict):
            merged[key] = {str(k): float(v) for k, v in val.items()}
    return merged
