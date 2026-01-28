from __future__ import annotations

import datetime as _dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from logging_config import get_log_path
from log_utils import append_json
from sentientos.pulse import PulseSignal, emit_pulse
from sentientos.toml_compat import tomllib


_DEFAULT_CONFIG_PATH = Path("glow") / "config" / "drift_config.toml"
_SILHOUETTE_ENV = "SENTIENTOS_SILHOUETTE_DIR"
_DATA_ROOT_ENV = "SENTIENTOS_DATA_DIR"


@dataclass(frozen=True, slots=True)
class DriftConfig:
    window_days: int = 7
    posture_repeat_max: int = 5
    motion_starvation_days: int = 3
    plugin_dominance_percent: float = 80.0
    anomaly_min_severity: int = 2
    anomaly_streak_days: int = 3
    emit_pulse: bool = False


def load_drift_config(path: Path | None = None) -> DriftConfig:
    config_path = path or Path(os.getenv("SENTIENTOS_DRIFT_CONFIG", str(_DEFAULT_CONFIG_PATH)))
    if not config_path.exists():
        return DriftConfig()
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DriftConfig()
    if not isinstance(payload, dict):
        return DriftConfig()
    return DriftConfig(
        window_days=_coerce_int(payload.get("window_days"), DriftConfig.window_days),
        posture_repeat_max=_coerce_int(payload.get("posture_repeat_max"), DriftConfig.posture_repeat_max),
        motion_starvation_days=_coerce_int(
            payload.get("motion_starvation_days"), DriftConfig.motion_starvation_days
        ),
        plugin_dominance_percent=_coerce_float(
            payload.get("plugin_dominance_percent"), DriftConfig.plugin_dominance_percent
        ),
        anomaly_min_severity=_coerce_int(payload.get("anomaly_min_severity"), DriftConfig.anomaly_min_severity),
        anomaly_streak_days=_coerce_int(payload.get("anomaly_streak_days"), DriftConfig.anomaly_streak_days),
        emit_pulse=_coerce_bool(payload.get("emit_pulse"), DriftConfig.emit_pulse),
    )


def detect_drift(
    silhouettes: list[Mapping[str, object]] | None = None,
    config: DriftConfig | None = None,
) -> dict[str, object]:
    config = config or load_drift_config()
    window_days = max(1, config.window_days)
    if silhouettes is None:
        silhouettes = _load_recent_silhouettes(window_days)

    events: list[dict[str, object]] = []
    dates = [str(entry.get("date")) for entry in silhouettes if entry.get("date") is not None]

    posture_event = _detect_posture_stuck(silhouettes, config)
    if posture_event:
        events.append(posture_event)

    motion_event = _detect_motion_starvation(silhouettes, config)
    if motion_event:
        events.append(motion_event)

    plugin_event = _detect_plugin_dominance(silhouettes, config)
    if plugin_event:
        events.append(plugin_event)

    anomaly_event = _detect_anomaly_trend(silhouettes, config)
    if anomaly_event:
        events.append(anomaly_event)

    if events:
        _log_drift_events(events, dates, config)
        if config.emit_pulse:
            _emit_drift_pulse(events, len(silhouettes))

    return {
        "drift_detected": bool(events),
        "window_days": window_days,
        "checked": len(silhouettes),
        "drift_events": events,
        "silhouette_dates": dates,
    }


def _log_drift_events(
    events: list[dict[str, object]],
    dates: list[str],
    config: DriftConfig,
) -> None:
    log_path = get_log_path("drift_detector.jsonl", "DRIFT_DETECTOR_LOG")
    timestamp = _dt.datetime.utcnow().isoformat()
    for event in events:
        entry = {
            "timestamp": timestamp,
            "type": "drift_detected",
            "drift_type": event.get("type"),
            "details": event.get("details", {}),
            "window_days": config.window_days,
            "dates": dates,
        }
        append_json(log_path, entry)


def _emit_drift_pulse(events: list[dict[str, object]], window: int) -> None:
    drift_types = [event.get("type") for event in events if event.get("type")]
    signal = PulseSignal(
        level="WARNING",
        reason="DRIFT_DETECTED",
        metrics={"drift_types": drift_types, "count": len(drift_types)},
        window=window,
    )
    emit_pulse(signal)


def _load_recent_silhouettes(n: int) -> list[dict[str, object]]:
    if not isinstance(n, int) or n <= 0:
        return []
    silhouettes: list[dict[str, object]] = []
    for path in _iter_silhouette_paths():
        payload = _load_payload(path)
        if payload is None:
            continue
        wrapped = dict(payload)
        wrapped["source"] = "embodiment_silhouette"
        silhouettes.append(wrapped)
        if len(silhouettes) >= n:
            break
    return silhouettes


def _iter_silhouette_paths() -> list[Path]:
    base = _resolve_silhouette_dir()
    if not base.exists():
        return []
    paths = [path for path in base.glob("*.json") if path.is_file()]
    paths.sort(key=lambda path: path.stem, reverse=True)
    return paths


def _resolve_silhouette_dir() -> Path:
    for candidate in _candidate_dirs():
        if candidate.exists():
            return candidate
    return _candidate_dirs()[0]


def _candidate_dirs() -> list[Path]:
    candidates: list[Path] = []
    env_dir = os.environ.get(_SILHOUETTE_ENV)
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path("glow") / "silhouettes")
    data_root = os.environ.get(_DATA_ROOT_ENV)
    if data_root:
        candidates.append(Path(data_root) / "glow" / "silhouettes")
    else:
        candidates.append(Path.cwd() / "sentientos_data" / "glow" / "silhouettes")
    return candidates


def _load_payload(path: Path) -> Mapping[str, object] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, Mapping):
        return payload
    return None


def _detect_posture_stuck(
    silhouettes: list[Mapping[str, object]],
    config: DriftConfig,
) -> dict[str, object] | None:
    max_repeat = max(1, config.posture_repeat_max)
    streak = 0
    posture = None
    for entry in silhouettes:
        dominant = _dominant_label(entry.get("posture_counts"))
        if dominant is None:
            break
        if posture is None:
            posture = dominant
            streak = 1
            continue
        if dominant != posture:
            break
        streak += 1
    if posture and streak >= max_repeat:
        return {
            "type": "POSTURE_STUCK",
            "details": {"posture": posture, "streak_days": streak},
        }
    return None


def _detect_motion_starvation(
    silhouettes: list[Mapping[str, object]],
    config: DriftConfig,
) -> dict[str, object] | None:
    threshold = max(1, config.motion_starvation_days)
    streak = 0
    for entry in silhouettes:
        totals = _sum_motion(entry.get("motion_deltas"))
        if totals is None:
            break
        if totals == 0:
            streak += 1
            continue
        break
    if streak >= threshold:
        return {
            "type": "MOTION_STARVATION",
            "details": {"streak_days": streak, "threshold": threshold},
        }
    return None


def _detect_plugin_dominance(
    silhouettes: list[Mapping[str, object]],
    config: DriftConfig,
) -> dict[str, object] | None:
    totals: dict[str, int] = {}
    for entry in silhouettes:
        usage = _count_map(entry.get("plugin_usage"))
        if not usage:
            continue
        for plugin, count in usage.items():
            totals[plugin] = totals.get(plugin, 0) + count
    if not totals:
        return None
    total_calls = sum(totals.values())
    if total_calls <= 0:
        return None
    top_plugin, top_count = max(totals.items(), key=lambda item: item[1])
    dominance = (top_count / total_calls) * 100
    if dominance >= config.plugin_dominance_percent:
        return {
            "type": "PLUGIN_DOMINANCE",
            "details": {
                "plugin": top_plugin,
                "dominance_percent": round(dominance, 2),
                "total_calls": total_calls,
            },
        }
    return None


def _detect_anomaly_trend(
    silhouettes: list[Mapping[str, object]],
    config: DriftConfig,
) -> dict[str, object] | None:
    min_severity = max(1, config.anomaly_min_severity)
    threshold = max(1, config.anomaly_streak_days)
    streak = 0
    for entry in silhouettes:
        severity = _severity_score(entry.get("anomalies"))
        if severity == 0:
            break
        if severity < min_severity:
            break
        streak += 1
    if streak >= threshold:
        return {
            "type": "ANOMALY_ESCALATION",
            "details": {"streak_days": streak, "min_severity": min_severity},
        }
    return None


def _dominant_label(posture_counts: object) -> str | None:
    counts = _count_map(posture_counts)
    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]


def _sum_motion(value: object) -> int | None:
    if not isinstance(value, Mapping):
        return None
    total = 0
    seen = 0
    for raw in value.values():
        if raw is None:
            continue
        try:
            count = int(raw)
        except (TypeError, ValueError):
            continue
        total += max(0, count)
        seen += 1
    if seen == 0:
        return None
    return total


def _severity_score(value: object) -> int:
    if not isinstance(value, Mapping):
        return 0
    counts = value.get("severity_counts")
    if not isinstance(counts, Mapping):
        return 0
    critical = _coerce_int(counts.get("critical"), 0)
    moderate = _coerce_int(counts.get("moderate"), 0)
    low = _coerce_int(counts.get("low"), 0)
    if critical > 0:
        return 3
    if moderate > 0:
        return 2
    if low > 0:
        return 1
    return 0


def _count_map(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not key:
            continue
        try:
            count = int(raw)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        counts[key] = counts.get(key, 0) + count
    return counts


def _coerce_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _coerce_float(value: object, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return default


__all__ = ["DriftConfig", "detect_drift", "load_drift_config"]
