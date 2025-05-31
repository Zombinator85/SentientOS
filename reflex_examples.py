import json
import os
from pathlib import Path

EMOTION_LOG = Path(os.getenv("EMOTION_LOG", "logs/emotions.jsonl"))
EEG_LOG = Path(os.getenv("EEG_FEATURE_LOG", "logs/eeg_features.jsonl"))
HAPTIC_LOG = Path(os.getenv("HAPTIC_LOG", "logs/haptics_events.jsonl"))


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
