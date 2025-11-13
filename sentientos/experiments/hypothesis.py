"""Deterministic hypothesis generation for automated experiments."""
from __future__ import annotations

import json
import logging
import os
import time
from copy import deepcopy
from hashlib import sha256
from typing import Any, Dict, Iterable, Tuple

from logging_config import get_log_path

LOGGER = logging.getLogger(__name__)

CACHE_PATH = get_log_path("hypothesis_cache.jsonl")
STATE_PATH = get_log_path("hypothesis_state.json")
RATE_LIMIT_ENV = "SENTIENTOS_HYPOTHESIS_RATE_MINUTES"

_CACHE: Dict[str, Dict[str, Any]] = {}
_STATE: Dict[str, Any] = {}


def _ensure_paths() -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_cache() -> None:
    if _CACHE:
        return
    _ensure_paths()
    if not CACHE_PATH.exists():
        return
    try:
        with CACHE_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                signature = payload.get("signature")
                spec = payload.get("spec")
                if isinstance(signature, str) and isinstance(spec, dict):
                    _CACHE[signature] = spec
    except Exception:  # pragma: no cover - defensive
        LOGGER.exception("Failed to load hypothesis cache")


def _load_state() -> None:
    if _STATE:
        return
    _ensure_paths()
    if not STATE_PATH.exists():
        _STATE.update({"last_timestamp": 0.0, "last_signature": None})
        return
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    _STATE.update(
        {
            "last_timestamp": float(data.get("last_timestamp", 0.0)),
            "last_signature": data.get("last_signature"),
        }
    )


def _save_state() -> None:
    _ensure_paths()
    try:
        STATE_PATH.write_text(json.dumps(_STATE), encoding="utf-8")
    except Exception:  # pragma: no cover - defensive
        LOGGER.exception("Failed to persist hypothesis state")


def _append_cache(signature: str, spec: Dict[str, Any]) -> None:
    _ensure_paths()
    record = {"signature": signature, "spec": spec}
    try:
        with CACHE_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except Exception:  # pragma: no cover - defensive
        LOGGER.exception("Failed to append hypothesis cache entry")


def _stable_form(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stable_form(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_stable_form(item) for item in value]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return repr(value)


def hypothesis_signature(event: Dict[str, Any]) -> str:
    stable_event = _stable_form(event)
    payload = json.dumps(stable_event, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _get_rate_limit_seconds() -> float:
    minutes = os.getenv(RATE_LIMIT_ENV)
    if not minutes:
        return 20.0 * 60.0
    try:
        value = float(minutes)
    except ValueError:
        LOGGER.warning("Invalid rate limit value %s, defaulting to 20 minutes", minutes)
        return 20.0 * 60.0
    return max(0.0, value * 60.0)


def _is_proposal_event(event: Dict[str, Any]) -> bool:
    markers = {"experiment", "experiment_id", "proposal", "proposed_experiment"}
    if any(key in event for key in markers):
        return True
    event_type = str(event.get("type") or event.get("event_type") or "")
    return event_type.lower() in {"experiment_proposal", "hypothesis_proposal"}


def _numeric_metrics(event: Dict[str, Any]) -> Iterable[Tuple[str, float]]:
    metrics: list[Tuple[str, float]] = []
    for key, value in event.items():
        if isinstance(value, (int, float)):
            metrics.append((str(key), float(value)))
    metrics.sort(key=lambda item: item[0])
    return metrics


def _primary_label(event: Dict[str, Any]) -> str:
    for key in ("event", "event_type", "type", "signal", "metric", "name", "source"):
        if key in event and event[key]:
            return str(event[key])
    return "event"


def _format_float(value: float) -> str:
    if abs(value) >= 1:
        return f"{value:.2f}"
    return f"{value:.4f}"


def _build_spec(event: Dict[str, Any], signature: str) -> Dict[str, Any]:
    label = _primary_label(event)
    metrics = list(_numeric_metrics(event))
    description = f"Investigate {label} stability"
    conditions = f"trigger: signature={signature}"
    if metrics:
        top_name, top_value = metrics[0]
        if top_value >= 0:
            target = min(top_value - max(0.05, abs(top_value) * 0.1), top_value)
            comparator = "<="
        else:
            target = max(top_value + max(0.05, abs(top_value) * 0.1), top_value)
            comparator = ">="
        expected = f"{top_name} returns to {_format_float(target)}"
        criteria = f"{top_name} {comparator} {_format_float(target)}"
    else:
        expected = "System metrics remain stable"
        criteria = "1 == 1"
    spec = {
        "description": description,
        "conditions": conditions,
        "expected": expected,
        "criteria": criteria,
        "proposer": "auto",
    }
    return spec


def _cache_hit(signature: str) -> Dict[str, Any] | None:
    _load_cache()
    spec = _CACHE.get(signature)
    if spec is None:
        return None
    return deepcopy(spec)


def _cache_store(signature: str, spec: Dict[str, Any]) -> None:
    if signature in _CACHE:
        return
    _CACHE[signature] = deepcopy(spec)
    _append_cache(signature, _CACHE[signature])


def _update_state(signature: str, timestamp: float) -> None:
    _load_state()
    _STATE["last_timestamp"] = float(timestamp)
    _STATE["last_signature"] = signature
    _save_state()


def _rate_limited(signature: str, now: float) -> bool:
    _load_state()
    if _STATE.get("last_signature") == signature:
        return False
    rate_limit = _get_rate_limit_seconds()
    last_ts = float(_STATE.get("last_timestamp", 0.0))
    if rate_limit <= 0:
        return False
    if now - last_ts < rate_limit:
        return True
    return False


def generate_hypothesis(event: Dict[str, Any]) -> Dict[str, Any] | None:
    """Deterministically produce an experiment spec based on an input event."""
    if not isinstance(event, dict):
        LOGGER.debug("Hypothesis generator received non-dict event: %s", type(event).__name__)
        return None
    if _is_proposal_event(event):
        LOGGER.info("Skipping proposal-looking event to avoid recursion: %s", event)
        return None

    signature = hypothesis_signature(event)

    cached = _cache_hit(signature)
    if cached is not None:
        return cached

    now = time.time()
    if _rate_limited(signature, now):
        LOGGER.info("Hypothesis generator rate limited for signature %s", signature)
        return None

    spec = _build_spec(event, signature)
    _cache_store(signature, spec)
    _update_state(signature, now)
    return deepcopy(spec)
