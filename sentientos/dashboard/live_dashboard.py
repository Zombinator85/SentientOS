"""Live terminal dashboard for SentientOS runtime state."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from sentientos.dashboard.dashboard_snapshot import (
    AvatarSnapshot,
    DashboardSnapshot,
    MindSnapshot,
    UNKNOWN_VALUE,
    collect_snapshot,
)
from sentientos.pulse.pulse_observer import DEFAULT_PULSE_PATH


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
        f" Mood: {mind.mood or UNKNOWN_VALUE} | Confidence: {mind.confidence if mind.confidence is not None else UNKNOWN_VALUE}"
        f" | Tension: {mind.tension if mind.tension is not None else UNKNOWN_VALUE} | "
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
    speaking_status = "speaking" if avatar.speaking else "silent"
    if avatar.muted and avatar.phrase:
        speaking_status = "muted"
    if avatar.phrase:
        lines.append(f" {avatar.emoji}  ({avatar.label}) – {speaking_status}: {avatar.phrase}")
    else:
        lines.append(f" {avatar.emoji}  ({avatar.label}) – {speaking_status}")
    lines.append(f" Visemes: {avatar.viseme_count}")
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
