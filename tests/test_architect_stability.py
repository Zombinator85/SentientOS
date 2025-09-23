import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pytest

import architect_daemon
from sentientos.daemons import pulse_bus
from sentientos.shell import SentientShell, ShellConfig, ShellEventLogger


class SequenceRNG:
    def __init__(self, values: Iterable[float]):
        self._values = list(values)

    def uniform(self, _a: float, _b: float) -> float:
        if not self._values:
            return 0.0
        return self._values.pop(0)


class TestClock:
    def __init__(self, current: datetime):
        self._current = current

    def now(self) -> datetime:
        return self._current

    def set(self, new_time: datetime) -> None:
        self._current = new_time


class StubFirstBootWizard:
    def should_run(self) -> bool:
        return False

    def run(self, decisions=None, force: bool = False):  # pragma: no cover - stub
        return {"status": "skipped"}

    def reset(self) -> None:  # pragma: no cover - stub
        return None


@pytest.fixture(autouse=True)
def reset_pulse_bus() -> None:
    pulse_bus.reset()
    yield
    pulse_bus.reset()


def _create_daemon(
    tmp_path: Path,
    *,
    interval: float = 3600,
    jitter: float = 0.0,
    reflection_frequency: int = 10,
    rng: SequenceRNG | None = None,
    max_failures: int = 3,
    cooldown_period: float = 24 * 3600,
    anomaly_threshold: int = 3,
    clock: TestClock | None = None,
    reflections_dir: Path | None = None,
    ledger_events: list[dict[str, object]] | None = None,
) -> architect_daemon.ArchitectDaemon:
    request_dir = tmp_path / "requests"
    session_file = tmp_path / "session.json"
    ledger_path = tmp_path / "ledger.jsonl"
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}", encoding="utf-8")
    completion_path = tmp_path / "vow" / "first_boot_complete"
    completion_path.parent.mkdir(parents=True, exist_ok=True)
    completion_path.write_text("done", encoding="utf-8")
    clock = clock or TestClock(datetime(2025, 1, 1, tzinfo=timezone.utc))
    ledger_sink = ledger_events.append if ledger_events is not None else lambda entry: entry
    reflections_dir = reflections_dir or (tmp_path / "reflections")
    reflections_dir.mkdir(parents=True, exist_ok=True)
    daemon = architect_daemon.ArchitectDaemon(
        request_dir=request_dir,
        session_file=session_file,
        ledger_path=ledger_path,
        config_path=config_path,
        completion_path=completion_path,
        interval=interval,
        jitter=jitter,
        reflection_frequency=reflection_frequency,
        reflection_dir=reflections_dir,
        rng=rng,
        max_failures=max_failures,
        cooldown_period=cooldown_period,
        anomaly_threshold=anomaly_threshold,
        ledger_sink=ledger_sink,
        pulse_publisher=lambda event: event,
        clock=clock.now,
        ci_commands=[["true"]],
        immutability_command=["true"],
    )
    daemon.start()
    return daemon


def test_cadence_respects_interval_and_jitter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")
    ledger_events: list[dict[str, object]] = []
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    clock = TestClock(base_time)
    rng = SequenceRNG([-300.0, 300.0, 0.0])
    daemon = _create_daemon(
        tmp_path,
        interval=3600,
        jitter=600,
        reflection_frequency=5,
        rng=rng,
        clock=clock,
        ledger_events=ledger_events,
    )

    first_due = daemon._next_cycle_due
    assert first_due is not None
    assert pytest.approx(first_due - base_time.timestamp(), abs=1.0) == 3300

    early_time = base_time + timedelta(seconds=3200)
    clock.set(early_time)
    assert daemon.tick(now=early_time) is None

    cycle_time = base_time + timedelta(seconds=3300)
    clock.set(cycle_time)
    request = daemon.tick(now=cycle_time)
    assert request is not None
    assert request.mode == "expand"
    assert request.cycle_number == 1
    assert daemon._cycle_counter == 1

    next_due = daemon._next_cycle_due
    assert next_due is not None
    assert pytest.approx(next_due - cycle_time.timestamp(), abs=1.0) == 3900


def test_failure_streak_triggers_cooldown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")
    ledger_events: list[dict[str, object]] = []
    clock = TestClock(datetime(2025, 1, 1, tzinfo=timezone.utc))
    daemon = _create_daemon(
        tmp_path,
        interval=1800,
        jitter=0,
        rng=SequenceRNG([0.0, 0.0, 0.0]),
        max_failures=2,
        cooldown_period=3600,
        clock=clock,
        ledger_events=ledger_events,
    )

    request = daemon.request_expand("scheduled", None)
    first_entry = {
        "event": "self_expand_rejected",
        "request_id": request.codex_prefix + "001",
        "reason": "tests",
    }
    daemon.handle_ledger_entry(first_entry)
    assert daemon._failure_streak == 1

    second_entry = {
        "event": "self_expand_rejected",
        "request_id": request.codex_prefix + "002",
        "reason": "tests",
    }
    daemon.handle_ledger_entry(second_entry)
    assert daemon._failure_streak == 2
    assert daemon._cooldown_until > clock.now().timestamp()
    assert any(evt["event"] == "architect_cooldown" for evt in ledger_events)

    blocked = daemon.tick(now=clock.now())
    assert blocked is None


def test_cooldown_reset_pulse_clears_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")
    ledger_events: list[dict[str, object]] = []
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    clock = TestClock(base_time)
    daemon = _create_daemon(
        tmp_path,
        interval=1200,
        jitter=0,
        rng=SequenceRNG([0.0, 0.0, 0.0]),
        cooldown_period=3600,
        clock=clock,
        ledger_events=ledger_events,
    )

    daemon._failure_streak = 2
    daemon._enter_cooldown("tests", timestamp=base_time.timestamp())
    assert daemon._cooldown_until > base_time.timestamp()

    reset_event = {
        "timestamp": base_time.isoformat(),
        "source_daemon": "SentientShell",
        "event_type": "architect_reset_cooldown",
        "priority": "info",
        "payload": {"reason": "manual"},
    }
    daemon.handle_pulse(reset_event)

    assert daemon._cooldown_until == 0.0
    assert daemon._failure_streak == 0
    assert daemon._next_cycle_due is not None
    assert daemon._next_cycle_due >= base_time.timestamp()

    reset_entries = [
        entry for entry in ledger_events if entry.get("event") == "architect_cooldown_reset"
    ]
    assert reset_entries and reset_entries[0]["actor"] == "SentientShell"

    completion_entries = [
        entry
        for entry in ledger_events
        if entry.get("event") == "architect_cooldown_complete"
        and entry.get("trigger") == "manual_reset"
    ]
    assert completion_entries


def test_reflection_cycle_emitted_every_frequency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")
    reflections_dir = tmp_path / "reflections"
    reflections_dir.mkdir(parents=True, exist_ok=True)
    ledger_events: list[dict[str, object]] = []
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    clock = TestClock(base_time)
    rng = SequenceRNG([0.0] * 10)
    daemon = _create_daemon(
        tmp_path,
        interval=600,
        jitter=0,
        reflection_frequency=3,
        rng=rng,
        clock=clock,
        reflections_dir=reflections_dir,
        ledger_events=ledger_events,
    )

    for cycle in range(1, 4):
        due = daemon._next_cycle_due
        assert due is not None
        cycle_time = datetime.fromtimestamp(due, tz=timezone.utc)
        clock.set(cycle_time)
        request = daemon.tick(now=cycle_time)
        assert request is not None
        if cycle < 3:
            assert request.mode == "expand"
        else:
            assert request.mode == "reflect"
            assert request.prompt_path is not None
            assert reflections_dir in request.prompt_path.parents
            assert any(
                evt["event"] == "architect_reflection_start" for evt in ledger_events
            )


def test_monitor_anomalies_trigger_throttling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")
    ledger_events: list[dict[str, object]] = []
    daemon = _create_daemon(
        tmp_path,
        interval=1200,
        jitter=0,
        rng=SequenceRNG([0.0] * 5),
        anomaly_threshold=2,
        ledger_events=ledger_events,
    )

    alert_event = {
        "timestamp": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
        "source_daemon": "MonitoringDaemon",
        "event_type": "monitor_alert",
        "priority": "critical",
        "payload": {"name": "cpu", "observed": 95},
    }
    daemon.handle_pulse(alert_event)
    daemon.handle_pulse(alert_event)
    assert daemon._throttled is True
    assert pytest.approx(daemon.interval) == 2400
    assert any(evt["event"] == "architect_throttled" for evt in ledger_events)

    summary_event = {
        "timestamp": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
        "source_daemon": "MonitoringDaemon",
        "event_type": "monitor_summary",
        "priority": "info",
        "payload": {"anomalies": []},
    }
    daemon.handle_pulse(summary_event)
    assert daemon._throttled is False


def test_shell_dashboard_reports_architect_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_file = tmp_path / "session.json"
    reflection_dir = tmp_path / "reflections"
    reflection_dir.mkdir(parents=True, exist_ok=True)
    summary_path = reflection_dir / "reflection_latest.json"
    summary_path.write_text(json.dumps({"summary": "All cycles healthy"}), encoding="utf-8")

    now_ts = datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()
    session_payload = {
        "runs": 0,
        "successes": 0,
        "failures": 0,
        "cycle_count": 5,
        "failure_streak": 0,
        "cooldown_until": now_ts + 7200,
        "next_cycle_due": now_ts + 3600,
        "last_cycle_started": now_ts,
        "cycle_history": [],
        "throttled": True,
        "throttle_multiplier": 2.0,
        "last_reflection_path": summary_path.as_posix().lstrip("/"),
        "last_reflection_summary": "",
        "anomaly_streak": 0,
        "autonomy_enabled": True,
    }
    session_file.write_text(json.dumps(session_payload), encoding="utf-8")

    monkeypatch.setattr(architect_daemon, "ARCHITECT_SESSION_FILE", session_file)
    monkeypatch.setattr(architect_daemon, "ARCHITECT_REFLECTION_DIR", reflection_dir)

    shell_logger = ShellEventLogger(
        ledger_path=tmp_path / "shell_ledger.jsonl",
        pulse_publisher=lambda event: event,
    )
    shell_config = ShellConfig(path=tmp_path / "shell_config.json")
    shell = SentientShell(
        user="tester",
        logger=shell_logger,
        config=shell_config,
        request_dir=tmp_path / "requests",
        trace_dir=tmp_path / "traces",
        pulse_publisher=lambda event: event,
        home_root=tmp_path,
        driver_manager=None,
        first_boot_wizard=StubFirstBootWizard(),
    )

    snapshot = shell.dashboard.refresh()
    architect_panel = snapshot["architect"]
    assert architect_panel["cooldown"]["active"] is True
    assert architect_panel["throttled"] is True
    assert architect_panel["autonomy_enabled"] is True
    assert architect_panel["last_reflection_summary"] == "All cycles healthy"
    reflections_panel = snapshot["reflections"]
    assert reflections_panel["latest"]["summary"] == "All cycles healthy"

    export_target = tmp_path / "shared"
    exported = shell.dashboard.export_latest_reflection(export_target)
    assert exported.exists()
    assert json.loads(exported.read_text(encoding="utf-8"))["summary"] == "All cycles healthy"

    run_event = shell.run_architect_now()
    assert run_event["event_type"] == "architect_run_now"
    reset_event = shell.reset_architect_cooldown()
    assert reset_event["event_type"] == "architect_reset_cooldown"
