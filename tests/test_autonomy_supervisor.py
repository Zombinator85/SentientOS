from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from curiosity_goal_helper import CuriosityGoalHelper
from daemon_autonomy_supervisor import DaemonAutonomySupervisor
from sentientos.autonomy.state import ContinuitySnapshot, ContinuityStateManager


class FakeProcess:
    def __init__(self, name: str) -> None:
        self.name = name
        self.alive = True
        self.terminated = False

    def poll(self) -> int | None:
        return None if self.alive else 1

    def terminate(self) -> None:
        self.terminated = True
        self.alive = False

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:  # pragma: no cover - defensive path
        self.alive = False


def _build_supervisor(tmp_path: Path, *, now) -> tuple[DaemonAutonomySupervisor, list[FakeProcess]]:
    processes: list[FakeProcess] = []

    def factory(name: str, spec):
        _ = spec
        proc = FakeProcess(name)
        processes.append(proc)
        return proc

    supervisor = DaemonAutonomySupervisor(
        runtime=None,
        log_path=tmp_path / "logs" / "watchdog.jsonl",
        heartbeat_path=tmp_path / "pulse" / "heartbeat.snap",
        process_factory=factory,
        check_interval=0.1,
        heartbeat_interval=10.0,
        readiness_interval=3600.0,
        auto_start=False,
        now=now,
    )
    return supervisor, processes


def test_supervisor_restarts_dead_process(tmp_path: Path) -> None:
    current = {"value": 0.0}

    def now() -> float:
        return current["value"]

    supervisor, processes = _build_supervisor(tmp_path, now=now)
    supervisor.register_daemon("asr", ["echo", "asr"], start_immediately=True)
    assert len(processes) == 1
    processes[0].alive = False
    supervisor.run_iteration()
    assert len(processes) == 2  # restarted
    log_entries = [
        json.loads(line)
        for line in (tmp_path / "logs" / "watchdog.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    events = {entry["event"] for entry in log_entries}
    assert "daemon_exit" in events
    assert "daemon_started" in events


def test_session_state_roundtrip(tmp_path: Path) -> None:
    manager = ContinuityStateManager(tmp_path / "session.json")
    queue_entry: Mapping[str, object] = {
        "goal": {"id": "goal-1", "text": "Investigate"},
        "observation": {"summary": "Novel object"},
        "created_at": 12.34,
        "source": "ocr",
    }
    inflight_entry: Mapping[str, object] = {
        "goal": {"id": "goal-2", "text": "Follow up"},
        "observation": {"summary": "Second cue"},
        "created_at": 56.78,
        "source": "asr",
    }
    snapshot = ContinuitySnapshot(
        mood="curious",
        readiness={"summary": {"healthy": True}},
        curiosity_queue=[queue_entry],
        curiosity_inflight=[inflight_entry],
        last_readiness_ts="2024-01-01T00:00:00+00:00",
    )
    manager.save(snapshot)
    restored = manager.load()
    assert restored.mood == "curious"
    helper = CuriosityGoalHelper()
    helper.restore_state(
        {
            "queue": restored.curiosity_queue,
            "inflight": restored.curiosity_inflight,
        }
    )
    state = helper.dump_state()
    assert len(state["queue"]) == 2
    goal_ids = {entry["goal"]["id"] for entry in state["queue"]}
    assert goal_ids == {"goal-1", "goal-2"}


def test_heartbeat_updates_on_schedule(tmp_path: Path) -> None:
    current = {"value": 0.0}

    def now() -> float:
        return current["value"]

    supervisor, processes = _build_supervisor(tmp_path, now=now)
    supervisor.register_daemon("tts", ["echo", "tts"], start_immediately=True)
    assert len(processes) == 1
    supervisor.run_iteration()
    heartbeat_path = tmp_path / "pulse" / "heartbeat.snap"
    first = heartbeat_path.read_text(encoding="utf-8")
    current["value"] = 5.0
    supervisor.run_iteration()
    assert heartbeat_path.read_text(encoding="utf-8") == first
    current["value"] = 12.0
    supervisor.run_iteration()
    assert heartbeat_path.read_text(encoding="utf-8") != first

