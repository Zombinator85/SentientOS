from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, Mapping

from sentientos.storage import ensure_mounts

logger = logging.getLogger(__name__)

DEFAULT_SELF_STATE: Dict[str, object] = {
    "identity": "SentientOS",
    "mood": "stable",
    "confidence": 0.5,
    "last_focus": None,
    "last_cycle_result": None,
    "novelty_score": 0.0,
    "last_generated_goal": None,
    "goal_context": {},
    "attention_hint": None,
    "internal_goal": None,
    "introspection_flag": False,
    "last_reflection_summary": "",
    "attention_level": "baseline",
}


def _default_self_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    mounts = ensure_mounts()
    repo_glow = Path("glow")
    if repo_glow.exists() and os.environ.get("SENTIENTOS_DATA_DIR") is None:
        return repo_glow / "self.json"
    glow_root = mounts.get("glow", Path.cwd() / "glow")
    glow_root.mkdir(parents=True, exist_ok=True)
    return glow_root / "self.json"


def validate(state: Mapping[str, object]) -> Dict[str, object]:
    expected_keys = set(DEFAULT_SELF_STATE.keys())
    missing = expected_keys - set(state.keys())
    if missing:
        raise ValueError(f"Missing self state fields: {', '.join(sorted(missing))}")
    validated = dict(DEFAULT_SELF_STATE)
    for key in expected_keys:
        validated[key] = state.get(key)
    if not isinstance(validated["identity"], str):
        raise TypeError("Self identity must be a string")
    if not isinstance(validated["mood"], str):
        raise TypeError("Self mood must be a string")
    confidence = validated["confidence"]
    if not isinstance(confidence, (int, float)):
        raise TypeError("Self confidence must be numeric")
    validated["confidence"] = float(confidence)
    novelty_score = validated.get("novelty_score", 0.0)
    if not isinstance(novelty_score, (int, float)):
        raise TypeError("Self novelty_score must be numeric")
    validated["novelty_score"] = float(novelty_score)
    if not isinstance(validated.get("goal_context", {}), dict):
        raise TypeError("Self goal_context must be a dictionary")
    if validated.get("attention_hint") is not None and not isinstance(
        validated.get("attention_hint"), str
    ):
        raise TypeError("Attention hint must be a string or null")
    if validated.get("last_generated_goal") is not None and not isinstance(
        validated.get("last_generated_goal"), dict
    ):
        raise TypeError("Last generated goal must be a dictionary or null")
    if validated.get("last_cycle_result") is not None and not isinstance(
        validated.get("last_cycle_result"), str
    ):
        raise TypeError("Last cycle result must be a string or null")
    if not isinstance(validated["introspection_flag"], bool):
        raise TypeError("Introspection flag must be a boolean")
    if validated.get("last_reflection_summary") is not None and not isinstance(
        validated.get("last_reflection_summary"), str
    ):
        raise TypeError("Last reflection summary must be a string or null")
    if validated.get("attention_level") is not None and not isinstance(
        validated.get("attention_level"), str
    ):
        raise TypeError("Attention level must be a string or null")
    if validated.get("last_focus") is not None and not isinstance(validated.get("last_focus"), str):
        raise TypeError("Last focus must be a string or null")
    return validated


def load(path: Path | None = None) -> Dict[str, object]:
    target = _default_self_path(path)
    try:
        data = json.loads(target.read_text())
    except FileNotFoundError:
        logger.info("Self model missing at %s; writing defaults", target)
        save(DEFAULT_SELF_STATE, path=target)
        return dict(DEFAULT_SELF_STATE)
    if not isinstance(data, dict):
        raise ValueError("Self model must be a JSON object")
    validated = validate({**DEFAULT_SELF_STATE, **data})
    return validated


def save(state: Mapping[str, object], path: Path | None = None) -> None:
    target = _default_self_path(path)
    validated = validate(state)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(validated, indent=2))


def update(partial: Mapping[str, object], path: Path | None = None) -> Dict[str, object]:
    current = load(path)
    merged = {**current, **partial}
    save(merged, path=path)
    return merged


__all__ = ["DEFAULT_SELF_STATE", "load", "save", "update", "validate"]
