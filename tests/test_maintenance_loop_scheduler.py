import fcntl
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sentientos import maintenance_loop_scheduler as scheduler
from sentientos import maintenance_loop_watchdog as watchdog
from tests.test_maintenance_watchdog_scan import config as watchdog_config

pytestmark = pytest.mark.no_legacy_skip


def configured(tmp_path: Path, **overrides):
    wcfg = watchdog.validate_config(watchdog_config(tmp_path))
    wp = tmp_path / "watchdog.json"; wp.write_bytes(watchdog.canonical_json_bytes(wcfg) + b"\n")
    state = tmp_path / "scheduler"; state.mkdir()
    value = {"schema_version": scheduler.CONFIG_SCHEMA, "watchdog_config_path": str(wp),
             "watchdog_config_digest": wcfg["config_digest"], "scheduler_state_root": str(state),
             "cadence_interval_seconds": 60, "initial_run_posture": "immediate",
             "schedule_anchor_utc": "2026-01-01T00:00:00Z", "maximum_cycles": 2,
             "maximum_scheduler_wall_clock_seconds": 300, "consecutive_failure_threshold": 2,
             "stop_marker": str(state / "SCHEDULER_STOP"), "journal_path": str(state / "scheduler_events.jsonl")}
    value.update(overrides)
    return scheduler.validate_config(value), wp


def result(status="idle"):
    return {"status": status, "ticks": [], "action_count": 0}


def test_exact_profile_binding_due_invocation_and_durable_receipt(tmp_path):
    cfg, _ = configured(tmp_path); calls = []
    out = scheduler.run_once(cfg, evaluation_time="2026-01-01T00:00:00Z", watchdog_runner=lambda c, **k: calls.append((c, k)) or result())
    assert out["status"] == "maintenance_scheduler_continue" and len(calls) == 1
    state = scheduler.inspect(cfg)
    assert state["event_count"] == 2 and state["next_due_utc"] == "2026-01-01T00:01:00Z"


def test_not_due_is_non_sleeping_and_does_not_invoke(tmp_path):
    cfg, _ = configured(tmp_path, initial_run_posture="after_interval"); calls = []
    out = scheduler.run_once(cfg, evaluation_time="2026-01-01T00:00:59Z", watchdog_runner=lambda *a, **k: calls.append(1) or result())
    assert out["status"] == "maintenance_scheduler_not_due" and calls == [] and scheduler.inspect(cfg)["event_count"] == 0


def test_watchdog_config_drift_blocks(tmp_path):
    cfg, wp = configured(tmp_path); changed = json.loads(wp.read_text()); changed["maximum_actions"] = 2; changed.pop("config_digest")
    wp.write_bytes(watchdog.canonical_json_bytes(watchdog.validate_config(changed)))
    with pytest.raises(ValueError, match="maintenance_scheduler_watchdog_config_drift"):
        scheduler.run_once(cfg, evaluation_time="2026-01-01T00:00:00Z", watchdog_runner=lambda *a, **k: result())


def test_scheduler_lock_contention_does_not_advance(tmp_path):
    cfg, _ = configured(tmp_path); lock_path = Path(cfg["scheduler_state_root"]) / "scheduler.lock"; lock_path.touch()
    with lock_path.open("r+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert scheduler.run_once(cfg, evaluation_time="2026-01-01T00:00:00Z")["status"] == "maintenance_scheduler_lock_busy"
    assert scheduler.inspect(cfg)["event_count"] == 0


@pytest.mark.parametrize("status,expected", [("waiting", "maintenance_scheduler_continue"), ("paused", "maintenance_scheduler_stop")])
def test_waiting_advances_once_and_pause_stops(tmp_path, status, expected):
    cfg, _ = configured(tmp_path)
    out = scheduler.run_once(cfg, evaluation_time="2026-01-01T00:00:00Z", watchdog_runner=lambda *a, **k: result(status))
    assert out["status"] == expected and scheduler.inspect(cfg)["next_cycle_ordinal"] == 2


def test_blocked_failure_threshold_and_stop_marker(tmp_path):
    cfg, _ = configured(tmp_path)
    first = scheduler.run_once(cfg, evaluation_time="2026-01-01T00:00:00Z", watchdog_runner=lambda *a, **k: result("blocked"))
    second = scheduler.run_once(cfg, evaluation_time="2026-01-01T00:01:00Z", watchdog_runner=lambda *a, **k: result("blocked"))
    assert first["status"] == "maintenance_scheduler_continue"
    assert second["status"] == "maintenance_scheduler_failure_threshold"
    Path(cfg["stop_marker"]).touch(); calls = []
    assert scheduler.run_once(cfg, evaluation_time="2026-01-01T00:02:00Z", watchdog_runner=lambda *a, **k: calls.append(1))["status"] == "maintenance_scheduler_stopped"
    assert not calls


def test_missed_intervals_collapse_without_catch_up_and_restart_reconstructs(tmp_path):
    cfg, _ = configured(tmp_path)
    scheduler.run_once(cfg, evaluation_time="2026-01-01T01:00:00Z", watchdog_runner=lambda *a, **k: result())
    state = scheduler.inspect(cfg)
    assert state["next_cycle_ordinal"] == 2 and state["next_due_utc"] == "2026-01-01T01:01:00Z"



def test_bounded_repeated_cadence_honors_cycle_limit(tmp_path):
    cfg, _ = configured(tmp_path, cadence_interval_seconds=1)
    wall = [datetime(2026, 1, 1, tzinfo=timezone.utc)]; ticks = [0.0]
    def sleep(seconds): wall[0] += timedelta(seconds=seconds); ticks[0] += seconds
    out = scheduler.run_bounded(cfg, wall_clock=lambda: wall[0], monotonic=lambda: ticks[0], sleeper=sleep,
                                watchdog_runner=lambda *a, **k: result("idle"))
    assert out["status"] == "maintenance_scheduler_cycle_limit" and out["cycle_count"] == 2


def test_bounded_scheduler_wall_clock_limit_prevents_sleep(tmp_path):
    cfg, _ = configured(tmp_path, initial_run_posture="after_interval", cadence_interval_seconds=60,
                        maximum_scheduler_wall_clock_seconds=10)
    slept = []
    out = scheduler.run_bounded(cfg, wall_clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
                                monotonic=lambda: 0.0, sleeper=lambda seconds: slept.append(seconds),
                                watchdog_runner=lambda *a, **k: result())
    assert out["status"] == "maintenance_scheduler_time_limit" and slept == []


def test_corrupt_or_tampered_journal_fails_closed(tmp_path):
    cfg, _ = configured(tmp_path); path = Path(cfg["journal_path"]); path.write_text("not-json\n")
    with pytest.raises(ValueError, match="scheduler_journal_malformed"): scheduler.inspect(cfg)
    path.unlink(); scheduler.run_once(cfg, evaluation_time="2026-01-01T00:00:00Z", watchdog_runner=lambda *a, **k: result())
    records = path.read_text().splitlines(); item = json.loads(records[-1]); item["next_due_utc"] = "2027-01-01T00:00:00Z"; records[-1] = json.dumps(item)
    path.write_text("\n".join(records) + "\n")
    with pytest.raises(ValueError, match="scheduler_journal_chain_invalid"): scheduler.inspect(cfg)


def test_bounded_repeated_cadence_and_cycle_bound(tmp_path):
    cfg, _ = configured(tmp_path); wall = [datetime(2026, 1, 1, tzinfo=timezone.utc)]; mono = [0.0]; calls = []
    def sleep(seconds): wall[0] += timedelta(seconds=seconds); mono[0] += seconds
    out = scheduler.run_bounded(cfg, wall_clock=lambda: wall[0], monotonic=lambda: mono[0], sleeper=sleep,
                                watchdog_runner=lambda *a, **k: calls.append(1) or result())
    assert out["status"] == "maintenance_scheduler_cycle_limit" and out["cycle_count"] == 2 and len(calls) == 2


def test_wall_clock_bound_never_sleeps_past_limit(tmp_path):
    cfg, _ = configured(tmp_path, initial_run_posture="after_interval", maximum_scheduler_wall_clock_seconds=30); sleeps = []
    out = scheduler.run_bounded(cfg, wall_clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc), monotonic=lambda: 0.0, sleeper=sleeps.append)
    assert out["status"] == "maintenance_scheduler_time_limit" and sleeps == []


def test_config_rejects_unknown_naive_and_first_boot_fields(tmp_path):
    cfg, _ = configured(tmp_path)
    for key, value in (("architect_autonomy", True), ("codex_interval", 1)):
        broken = dict(cfg); broken[key] = value
        with pytest.raises(ValueError, match="unknown_scheduler_config_field"): scheduler.validate_config(broken)
    broken = dict(cfg); broken.pop("config_digest"); broken["schedule_anchor_utc"] = "2026-01-01T00:00:00"
    with pytest.raises(ValueError, match="not_timezone_aware"): scheduler.validate_config(broken)
