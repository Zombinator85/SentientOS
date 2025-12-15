"""Snapshot builder for live dashboard rendering.

This module centralises collection of system introspection, audit logs,
pulse metrics, and task queue activity into a single DashboardSnapshot
structure that can be rendered by live_dashboard.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Optional

from logging_config import get_log_dir
from runtime_mode import SENTIENTOS_MODE
from sentientos.storage import get_state_file
from speech_log import get_recent_speech
from task_admission import ADMISSION_LOG_PATH
from task_executor import LOG_PATH as EXECUTOR_LOG_PATH

from sentientos.glow import self_state
from sentientos.pulse.pulse_observer import DEFAULT_PULSE_PATH
from sentientos.pulse.signals import PulseLevel

UNKNOWN_VALUE = "UNKNOWN"


@dataclass
class HealthSnapshot:
    mode: str = UNKNOWN_VALUE
    pulse_level: str = UNKNOWN_VALUE
    pulse_reason: str | None = None
    executor_status: str = UNKNOWN_VALUE
    recent_error_count: int = 0
    last_event_age: str = UNKNOWN_VALUE
    daemons_running: list[str] = field(default_factory=list)


@dataclass
class MindSnapshot:
    mood: Optional[str] = "neutral"
    confidence: Optional[float] = None
    tension: Optional[float] = None
    novelty: Optional[float] = None
    satisfaction: Optional[float] = None
    safety_flag: Optional[str] = None
    last_reflection_summary: Optional[str] = None
    current_focus: Optional[str] = None


@dataclass
class ThoughtSnapshot:
    recent_reflection: Optional[str] = None
    narrator_output: Optional[str] = None
    last_kernel_proposal: Optional[str] = None


@dataclass
class ActivitySnapshot:
    active_tasks: list[str] = field(default_factory=list)
    recent_admissions: list[str] = field(default_factory=list)
    executor_steps: list[str] = field(default_factory=list)
    last_completed_task: Optional[str] = None


@dataclass
class AvatarSnapshot:
    emoji: str = "😐"
    label: str = "neutral"
    speaking: bool = False
    phrase: Optional[str] = None
    muted: bool = False
    viseme_count: int = 0
    active_viseme: Optional[str] = None
    viseme_weight: float = 0.0
    viseme_progress: float = 0.0
    phrase_position: float = 0.0
    speaking_duration: float = 0.0
    blendshape_hint: str = "neutral"
    last_phrase: Optional[str] = None
    last_duration: Optional[float] = None


@dataclass
class DashboardSnapshot:
    health: HealthSnapshot
    mind: MindSnapshot
    thoughts: ThoughtSnapshot
    activity: ActivitySnapshot
    avatar: AvatarSnapshot


def _load_json_lines(path: Path, *, limit: int = 50) -> list[MutableMapping[str, object]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    items: list[MutableMapping[str, object]] = []
    for raw in lines[-limit:]:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, MutableMapping):
            items.append(data)
    return items


def _format_age(timestamp: float) -> str:
    if timestamp <= 0:
        return UNKNOWN_VALUE
    delta = max(0.0, time.time() - timestamp)
    if delta < 1:
        return "<1s"
    if delta < 60:
        return f"{int(delta)}s"
    minutes = int(delta // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = int(minutes // 60)
    return f"{hours}h"


def _pick_last_timestamp(paths: Iterable[Path]) -> float:
    newest = 0.0
    for path in paths:
        try:
            stats = path.stat()
        except OSError:
            continue
        newest = max(newest, stats.st_mtime)
    return newest


def _smoothstep(value: float) -> float:
    clamped = max(0.0, min(1.0, value))
    return clamped * clamped * (3.0 - 2.0 * clamped)


def _normalize_viseme_timeline(timeline: object) -> list[MutableMapping[str, object]]:
    if not isinstance(timeline, list):
        return []
    cues: list[MutableMapping[str, object]] = []
    for cue in timeline:
        if not isinstance(cue, Mapping):
            continue
        try:
            start = float(cue.get("time", 0.0) or 0.0)
            duration = float(cue.get("duration", 0.0) or 0.0)
        except Exception:
            continue
        label = str(cue.get("viseme", cue.get("value", cue.get("mouth", "neutral")))) or "neutral"
        cues.append({
            "time": start,
            "duration": duration,
            "viseme": label,
        })
    cues.sort(key=lambda cue: float(cue.get("time", 0.0)))
    return cues


def _resolve_phrase_start(phrase_block: Mapping[str, object], avatar_state: Mapping[str, object]) -> Optional[float]:
    start_value = phrase_block.get("started_at")
    if isinstance(start_value, (int, float)):
        return float(start_value)
    state_start = avatar_state.get("phrase_started_at")
    if isinstance(state_start, (int, float)):
        return float(state_start)
    timestamp = avatar_state.get("timestamp")
    if isinstance(timestamp, (int, float)):
        return float(timestamp)
    return None


def _compute_viseme_frame(
    *,
    timeline: list[MutableMapping[str, object]],
    phrase_block: Mapping[str, object],
    speaking: bool,
    avatar_state: Mapping[str, object],
    now: float | None = None,
) -> tuple[str, float, float, float]:
    if not timeline:
        return "neutral", 0.1, 0.0, 0.0

    start_at = _resolve_phrase_start(phrase_block, avatar_state)
    if start_at is None:
        return "neutral", 0.1, 0.0, 0.0

    current_time = now or time.time()
    elapsed = max(0.0, current_time - start_at)

    active_viseme = "neutral"
    weight = 0.1
    viseme_progress = 0.0

    total_duration = 0.0
    for cue in timeline:
        start = float(cue.get("time", 0.0) or 0.0)
        duration = float(cue.get("duration", 0.0) or 0.0)
        duration = duration if duration > 0 else 0.08
        end = start + duration
        total_duration = max(total_duration, end)
        if elapsed < start:
            continue
        if elapsed <= end:
            active_viseme = str(cue.get("viseme", "neutral")) or "neutral"
            raw_progress = (elapsed - start) / duration
            viseme_progress = _smoothstep(raw_progress)
            weight = 0.2 + 0.8 * viseme_progress if speaking else 0.15
            break
    phrase_position = 0.0
    if total_duration > 0:
        phrase_position = max(0.0, min(1.0, elapsed / total_duration))
    return active_viseme, weight, viseme_progress, phrase_position


def _load_pulse(path: Path = DEFAULT_PULSE_PATH) -> tuple[str, str | None]:
    if not path.exists():
        return UNKNOWN_VALUE, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return UNKNOWN_VALUE, None
    level = str(data.get("level") or UNKNOWN_VALUE)
    reason = data.get("reason")
    return level.upper(), reason if isinstance(reason, str) else None


def _load_avatar_state(path: Path | None = None) -> MutableMapping[str, object]:
    state_path = path or get_state_file("avatar_state.json")
    try:
        data = json.loads(Path(state_path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, MutableMapping) else {}


def _load_self_state(path: Path | None = None) -> MindSnapshot:
    try:
        state = self_state.load(path)
    except Exception:
        state = dict(self_state.DEFAULT_SELF_STATE)
    mood = state.get("mood") if isinstance(state, Mapping) else "neutral"
    confidence = state.get("confidence") if isinstance(state, Mapping) else None
    novelty = state.get("novelty_score") if isinstance(state, Mapping) else None
    tension = state.get("tension") if isinstance(state, Mapping) else state.get("attention_level")
    satisfaction = state.get("satisfaction") if isinstance(state, Mapping) else None
    safety_flag = state.get("safety_flag") if isinstance(state, Mapping) else None
    last_reflection_summary = state.get("last_reflection_summary") if isinstance(state, Mapping) else None
    current_focus = state.get("last_focus") if isinstance(state, Mapping) else None
    return MindSnapshot(
        mood=str(mood) if mood is not None else "neutral",
        confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
        tension=float(tension) if isinstance(tension, (int, float)) else None,
        novelty=float(novelty) if isinstance(novelty, (int, float)) else None,
        satisfaction=float(satisfaction) if isinstance(satisfaction, (int, float)) else None,
        safety_flag=str(safety_flag) if safety_flag else None,
        last_reflection_summary=str(last_reflection_summary) if last_reflection_summary else None,
        current_focus=str(current_focus) if current_focus else None,
    )


def _load_recent_reflection(log_dir: Path) -> Optional[str]:
    reflection_dir = log_dir / "self_reflections"
    if not reflection_dir.exists():
        return None
    files = sorted(reflection_dir.glob("*.log"))
    if not files:
        return None
    latest = files[-1]
    try:
        lines = latest.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None
    for line in reversed(lines):
        if line.strip():
            return line.strip()
    return None


def _load_admissions(path: Path = ADMISSION_LOG_PATH, *, limit: int = 10) -> list[MutableMapping[str, object]]:
    return _load_json_lines(path, limit=limit)


def _load_executor(path: Path = EXECUTOR_LOG_PATH, *, limit: int = 20) -> list[MutableMapping[str, object]]:
    return _load_json_lines(path, limit=limit)


def _summarise_admission(entry: Mapping[str, object]) -> str:
    task_id = entry.get("task_id")
    reason = entry.get("reason")
    allowed = entry.get("allowed")
    verb = "ALLOW" if allowed else "DENY"
    task_text = str(task_id or "task")
    reason_text = str(reason or "")
    return f"{verb} {task_text} {reason_text}".strip()


def _summarise_executor(entry: Mapping[str, object]) -> tuple[str, bool, str | None]:
    task_id = str(entry.get("task_id") or "task")
    step_id = str(entry.get("step_id") or "?")
    status = str(entry.get("status") or "unknown")
    marker = f"{task_id} step {step_id}: {status}"
    if entry.get("error"):
        marker += f" ({entry.get('error')})"
    failed = status.lower() == "failed"
    completed = entry.get("completed")
    if isinstance(completed, bool) and completed:
        return marker, failed, task_id
    return marker, failed, None


def _compute_executor_status(entries: list[Mapping[str, object]]) -> tuple[str, list[str], int, str | None]:
    if not entries:
        return "idle", [], 0, None
    recent_failures = 0
    active_steps: list[str] = []
    last_completed: Optional[str] = None
    for entry in entries[-5:]:
        marker, failed, maybe_completed = _summarise_executor(entry)
        if failed:
            recent_failures += 1
        active_steps.append(marker)
        if maybe_completed:
            last_completed = maybe_completed
    status = "failed" if recent_failures else "running"
    return status, active_steps, recent_failures, last_completed


_MOOD_EMOJI_MAP: dict[str, AvatarSnapshot] = {
    "joy": AvatarSnapshot("😊", "bright"),
    "happy": AvatarSnapshot("😊", "bright"),
    "excited": AvatarSnapshot("😊", "bright"),
    "confident": AvatarSnapshot("🙂", "confident"),
    "calm": AvatarSnapshot("😌", "calm"),
    "tired": AvatarSnapshot("😴", "resting"),
    "sleepy": AvatarSnapshot("😴", "resting"),
    "anxious": AvatarSnapshot("😟", "concerned"),
    "focused": AvatarSnapshot("😐", "steady"),
}


def _select_avatar_from_mood(mood: str | None) -> AvatarSnapshot:
    if not mood:
        return AvatarSnapshot("😐", "steady")
    key = mood.lower().strip()
    return _MOOD_EMOJI_MAP.get(key, AvatarSnapshot("😐", key or "steady"))


def build_avatar(pulse_level: str | PulseLevel, mind: MindSnapshot) -> AvatarSnapshot:
    level = str(pulse_level or "").upper()
    base = _select_avatar_from_mood(mind.mood)
    tension = mind.tension if mind.tension is not None else 0.0
    confidence = mind.confidence if mind.confidence is not None else 0.0

    if level == "DEGRADED":
        return AvatarSnapshot("😠", "degraded")
    if level == "WARNING":
        if tension > 0.6:
            return AvatarSnapshot("😕", "strained")
        return AvatarSnapshot("😟", "warning")
    if confidence > 0.7 and base.emoji == "😐":
        return AvatarSnapshot("🙂", "confident")
    return base


def _detect_daemons(log_root: Path) -> list[str]:
    expected = ("heartbeat", "ledger", "pulse", "codex")
    found: list[str] = []
    for name in expected:
        candidate = log_root / f"{name}.log"
        if candidate.exists():
            found.append(name)
    return found or [UNKNOWN_VALUE]


def collect_snapshot(
    *,
    log_dir: Path | None = None,
    pulse_path: Path = DEFAULT_PULSE_PATH,
    self_path: Path | None = None,
    refresh_interval: float = 1.5,
) -> DashboardSnapshot:
    log_root = log_dir or get_log_dir()

    pulse_level, pulse_reason = _load_pulse(pulse_path)
    mind = _load_self_state(self_path)

    admission_entries = _load_admissions(path=ADMISSION_LOG_PATH)
    executor_entries = _load_executor(path=EXECUTOR_LOG_PATH)

    executor_status, executor_steps, error_count, last_completed = _compute_executor_status(executor_entries)

    recent_admissions = [_summarise_admission(entry) for entry in admission_entries[-5:]]
    active_tasks = list({entry.get("task_id") for entry in executor_entries[-5:] if entry.get("status") != "failed"})
    active_tasks = [str(item) for item in active_tasks if item]

    latest_timestamp = _pick_last_timestamp([pulse_path, ADMISSION_LOG_PATH, EXECUTOR_LOG_PATH])
    last_event_age = _format_age(latest_timestamp)

    thoughts = ThoughtSnapshot(
        recent_reflection=_load_recent_reflection(log_root),
        narrator_output=None,
        last_kernel_proposal=None,
    )

    activity = ActivitySnapshot(
        active_tasks=active_tasks,
        recent_admissions=recent_admissions,
        executor_steps=executor_steps[-5:],
        last_completed_task=last_completed,
    )

    health = HealthSnapshot(
        mode=SENTIENTOS_MODE,
        pulse_level=pulse_level,
        pulse_reason=pulse_reason,
        executor_status=executor_status,
        recent_error_count=error_count,
        last_event_age=last_event_age,
        daemons_running=_detect_daemons(log_root),
    )

    avatar_state = _load_avatar_state()
    phrase_block = avatar_state.get("phrase") if isinstance(avatar_state.get("phrase"), Mapping) else {}
    phrase_text = phrase_block.get("text", avatar_state.get("current_phrase", ""))
    viseme_timeline = _normalize_viseme_timeline(avatar_state.get("viseme_timeline"))
    speaking = bool(avatar_state.get("speaking", avatar_state.get("is_speaking", False)))
    muted = bool(phrase_block.get("muted", avatar_state.get("muted", False)))
    viseme_count = int(phrase_block.get("viseme_count", len(viseme_timeline)))

    recent_speech = get_recent_speech()
    last_phrase = None
    last_duration = None
    if recent_speech:
        recent_text = recent_speech.get("text")
        if isinstance(recent_text, str) and recent_text.strip():
            last_phrase = recent_text
        duration_value = recent_speech.get("duration")
        if isinstance(duration_value, (int, float)):
            last_duration = float(duration_value)
        if not viseme_count:
            try:
                viseme_count = int(recent_speech.get("viseme_count", 0) or 0)
            except Exception:
                viseme_count = 0
        if recent_speech.get("muted"):
            muted = True
        if not speaking and recent_speech.get("speaking"):
            speaking = bool(recent_speech.get("speaking"))

    active_viseme, viseme_weight, viseme_progress, phrase_position = _compute_viseme_frame(
        timeline=viseme_timeline,
        phrase_block=phrase_block,
        speaking=speaking,
        avatar_state=avatar_state,
    )
    speech_started_at = _resolve_phrase_start(phrase_block, avatar_state)
    speaking_duration = 0.0
    if speaking and speech_started_at is not None:
        speaking_duration = max(0.0, time.time() - speech_started_at)

    if not speaking:
        active_viseme = "neutral"
        viseme_weight = 0.08
        viseme_progress = 0.0
        phrase_position = 0.0

    display_phrase = phrase_text or last_phrase
    base_avatar = build_avatar(pulse_level, mind)
    avatar = AvatarSnapshot(
        emoji=base_avatar.emoji,
        label=str(avatar_state.get("expression") or base_avatar.label),
        speaking=speaking,
        phrase=str(display_phrase) if display_phrase else None,
        muted=muted,
        viseme_count=viseme_count,
        active_viseme=active_viseme,
        viseme_weight=viseme_weight,
        viseme_progress=viseme_progress,
        phrase_position=phrase_position,
        speaking_duration=speaking_duration,
        blendshape_hint=active_viseme if speaking else "breathing",
        last_phrase=last_phrase,
        last_duration=last_duration,
    )

    return DashboardSnapshot(health=health, mind=mind, thoughts=thoughts, activity=activity, avatar=avatar)
