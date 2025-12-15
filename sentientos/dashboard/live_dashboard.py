"""Live terminal dashboard for SentientOS runtime state."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Optional

from logging_config import get_log_dir
from runtime_mode import SENTIENTOS_MODE
from task_admission import ADMISSION_LOG_PATH
from task_executor import LOG_PATH as EXECUTOR_LOG_PATH

from sentientos.glow import self_state
from sentientos.pulse.pulse_observer import DEFAULT_PULSE_PATH
from sentientos.pulse.signals import PulseLevel

UNKNOWN_VALUE = "UNKNOWN"


@dataclass
class HealthSnapshot:
    mode: str = SENTIENTOS_MODE
    pulse_level: str = UNKNOWN_VALUE
    pulse_reason: str | None = None
    executor_status: str = UNKNOWN_VALUE
    recent_error_count: int = 0
    last_event_age: str = UNKNOWN_VALUE
    daemons_running: list[str] = field(default_factory=list)


@dataclass
class MindSnapshot:
    mood: Optional[str] = None
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


def _load_self_state(path: Path | None = None) -> MindSnapshot:
    try:
        state = self_state.load(path)
    except Exception:
        state = dict(self_state.DEFAULT_SELF_STATE)
    mood = state.get("mood") if isinstance(state, Mapping) else None
    confidence = state.get("confidence") if isinstance(state, Mapping) else None
    novelty = state.get("novelty_score") if isinstance(state, Mapping) else None
    tension = state.get("tension") if isinstance(state, Mapping) else state.get("attention_level")
    satisfaction = state.get("satisfaction") if isinstance(state, Mapping) else None
    safety_flag = state.get("safety_flag") if isinstance(state, Mapping) else None
    last_reflection_summary = state.get("last_reflection_summary") if isinstance(state, Mapping) else None
    current_focus = state.get("last_focus") if isinstance(state, Mapping) else None
    return MindSnapshot(
        mood=str(mood) if mood is not None else None,
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
    last_task = task_id if status.lower() == "completed" else None
    return marker, failed, last_task


def _compute_executor_status(entries: Sequence[Mapping[str, object]]) -> tuple[str, list[str], int, Optional[str]]:
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
        pulse_level=pulse_level,
        pulse_reason=pulse_reason,
        executor_status=executor_status,
        recent_error_count=error_count,
        last_event_age=last_event_age,
        daemons_running=_detect_daemons(log_root),
    )

    avatar = build_avatar(pulse_level, mind)

    return DashboardSnapshot(health=health, mind=mind, thoughts=thoughts, activity=activity, avatar=avatar)


def _detect_daemons(log_root: Path) -> list[str]:
    expected = ("heartbeat", "ledger", "pulse", "codex")
    found: list[str] = []
    for name in expected:
        candidate = log_root / f"{name}.log"
        if candidate.exists():
            found.append(name)
    return found or [UNKNOWN_VALUE]


def build_avatar(pulse_level: str | PulseLevel, mind: MindSnapshot) -> AvatarSnapshot:
    level = str(pulse_level or "").upper()
    mood = (mind.mood or "").lower()
    tension = mind.tension or 0.0
    confidence = mind.confidence or 0.0

    if level == "DEGRADED":
        return AvatarSnapshot("😠", "degraded")
    if level == "WARNING":
        if tension and tension > 0.6:
            return AvatarSnapshot("😕", "strained")
        return AvatarSnapshot("😟", "warning")
    if mood in {"happy", "joy", "excited"}:
        return AvatarSnapshot("😊", "bright")
    if confidence > 0.7:
        return AvatarSnapshot("🙂", "confident")
    if mood in {"tired", "sleepy"}:
        return AvatarSnapshot("😴", "resting")
    return AvatarSnapshot("😐", "steady")


def render_snapshot(snapshot: DashboardSnapshot, *, refresh_interval: float) -> str:
    lines: list[str] = []
    lines.append("\x1b[2J\x1b[H")  # clear screen
    lines.append("======== SentientOS Live Dashboard ========")

    health = snapshot.health
    lines.append("[System Health]")
    lines.append(
        f" Mode: {health.mode} | Pulse: {health.pulse_level} ({health.pulse_reason or 'n/a'}) | "
        f"Executor: {health.executor_status} | Errors: {health.recent_error_count} | "
        f"Last Event: {health.last_event_age}"
    )
    lines.append(f" Daemons: {', '.join(health.daemons_running)}")
    lines.append("")

    mind = snapshot.mind
    lines.append("[Mind State]")
    lines.append(
        f" Mood: {mind.mood or UNKNOWN_VALUE} | Confidence: {mind.confidence if mind.confidence is not None else UNKNOWN_VALUE} | "
        f"Tension: {mind.tension if mind.tension is not None else UNKNOWN_VALUE} | "
        f"Novelty: {mind.novelty if mind.novelty is not None else UNKNOWN_VALUE} | "
        f"Satisfaction: {mind.satisfaction if mind.satisfaction is not None else UNKNOWN_VALUE}"
    )
    lines.append(f" Focus: {mind.current_focus or UNKNOWN_VALUE} | Safety: {mind.safety_flag or 'clear'}")
    lines.append(f" Last reflection: {mind.last_reflection_summary or '(none)'}")
    lines.append("")

    thoughts = snapshot.thoughts
    lines.append("[Current Thoughts / Reflections]")
    lines.append(f" Reflection: {thoughts.recent_reflection or '(no recent reflection)'}")
    lines.append(f" Narrator: {thoughts.narrator_output or '(no active internal narration)'}")
    lines.append(f" Kernel proposal: {thoughts.last_kernel_proposal or '(none)'}")
    lines.append("")

    activity = snapshot.activity
    lines.append("[Current Doings]")
    lines.append(f" Active tasks: {', '.join(activity.active_tasks) if activity.active_tasks else 'none'}")
    lines.append(" Recent admissions:")
    if activity.recent_admissions:
        for item in activity.recent_admissions[-5:]:
            lines.append(f"  - {item}")
    else:
        lines.append("  (none)")
    lines.append(" Executor steps:")
    if activity.executor_steps:
        for step in activity.executor_steps[-5:]:
            lines.append(f"  - {step}")
    else:
        lines.append("  (idle)")
    lines.append(f" Last completed task: {activity.last_completed_task or 'none'}")
    lines.append("")

    avatar = snapshot.avatar
    lines.append("[Avatar]")
    lines.append(f" {avatar.emoji}  ({avatar.label})")
    lines.append("")

    lines.append(f"(Read-only; updates every ~{refresh_interval:.1f}s)")
    return "\n".join(lines)


def run_dashboard(
    *,
    refresh_interval: float = 1.5,
    pulse_path: Path = DEFAULT_PULSE_PATH,
    self_path: Path | None = None,
) -> None:
    interval = max(0.5, float(refresh_interval))
    try:
        while True:
            snapshot = collect_snapshot(pulse_path=pulse_path, self_path=self_path, refresh_interval=interval)
            frame = render_snapshot(snapshot, refresh_interval=interval)
            sys.stdout.write(frame)
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        return
