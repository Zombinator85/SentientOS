"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import json
import os
from pathlib import Path

EMOTION_LOG = get_log_path("emotions.jsonl", "EMOTION_LOG")
EEG_LOG = get_log_path("eeg_features.jsonl", "EEG_FEATURE_LOG")
HAPTIC_LOG = get_log_path("haptics_events.jsonl", "HAPTIC_LOG")


def _last_value(path: Path, field: str) -> float:
    if not path.exists():
        return 0.0
    try:
        line = path.read_text(encoding="utf-8").splitlines()[-1]
        data = json.loads(line)
        return float(data.get(field, 0.0))
    except Exception:
        return 0.0


def stress_warning_check() -> bool:
    fear = _last_value(EMOTION_LOG, "Fear")
    beta = _last_value(EEG_LOG, "focus")
    agitation = _last_value(HAPTIC_LOG, "value")
    return fear > 0.7 and (beta > 0.5 or agitation > 0.5)


def fatigue_alert_check() -> bool:
    drowsy = _last_value(EEG_LOG, "drowsiness")
    agitation = _last_value(HAPTIC_LOG, "value")
    return drowsy > 0.6 and agitation < 0.3


def focus_prompt_check() -> bool:
    focus = _last_value(EEG_LOG, "focus")
    return focus < 0.3
