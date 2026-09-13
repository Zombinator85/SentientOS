import json
import os
import threading
from pathlib import Path

import pytest

from sentientos import maintenance_loop_scheduler as scheduler
from sentientos.maintenance_scheduler_daemon import (
    ADOPTION_SCHEMA,
    MaintenanceSchedulerOwner,
    validate_adoption,
)
from sentientos import maintenance_loop_activation as activation
from tests.test_maintenance_loop_scheduler import configured

pytestmark = pytest.mark.no_legacy_skip


def adoption(tmp_path: Path, *, enabled: bool = True):
    cfg, watchdog_path = configured(tmp_path)
    profile = tmp_path / "scheduler-profile.json"
    profile.write_bytes(scheduler.canonical_bytes(cfg) + b"\n")
    value = {"schema_version": ADOPTION_SCHEMA, "enabled": enabled,
             "scheduler_config_path": str(profile), "scheduler_config_digest": cfg["config_digest"],
             "expected_scheduler_schema": scheduler.CONFIG_SCHEMA,
             "evidence_path": str(Path(cfg["scheduler_state_root"]) / "daemon_events.jsonl"),
             "shutdown_timeout_seconds": 1, "reentry_delay_seconds": .01}
    return validate_adoption(value), cfg, profile, watchdog_path


def test_adoption_disabled_and_missing_environment_do_not_touch_scheduler(tmp_path, monkeypatch):
    value, cfg, _, _ = adoption(tmp_path, enabled=False)
    calls = []
    owner = MaintenanceSchedulerOwner(value, runner=lambda *a, **k: calls.append(1))
    assert owner.start() is False and calls == [] and owner.health()["status"] == "disabled"
    monkeypatch.delenv("SENTIENTOS_MAINTENANCE_SCHEDULER_ADOPTION_CONFIG", raising=False)
    assert not Path(cfg["journal_path"]).exists()


def test_explicit_exact_adoption_runs_one_lifetime_records_evidence_and_stops(tmp_path):
    value, _, _, _ = adoption(tmp_path); entered = threading.Event(); released = threading.Event()
    def run(_cfg, **kwargs):
        entered.set(); released.wait(1)
        return {"status": "maintenance_scheduler_stopped"}
    owner = MaintenanceSchedulerOwner(value, runner=run)
    assert owner.start() and not owner.start() and entered.wait(1)
    released.set(); assert owner.stop()
    events = [json.loads(line)["event_type"] for line in Path(value["evidence_path"]).read_text().splitlines()]
    assert {"scheduler_adoption_configured", "scheduler_lifetime_started", "scheduler_bounded_run_returned",
            "scheduler_terminal_disposition", "daemon_shutdown_requested", "scheduler_lifetime_stopped"} <= set(events)


def test_scheduler_config_digest_drift_blocks_before_invocation(tmp_path):
    value, _, profile, _ = adoption(tmp_path); calls = []
    owner = MaintenanceSchedulerOwner(value, runner=lambda *a, **k: calls.append(1))
    payload = json.loads(profile.read_text()); payload["cadence_interval_seconds"] = 61; payload.pop("config_digest")
    profile.write_bytes(scheduler.canonical_bytes(scheduler.validate_config(payload)))
    assert not owner.start() and calls == [] and owner.health()["status"] == "degraded"


def test_watchdog_drift_propagates_degraded_before_invocation(tmp_path):
    value, _, _, watchdog_path = adoption(tmp_path); calls = []
    owner = MaintenanceSchedulerOwner(value, runner=lambda *a, **k: calls.append(1))
    payload = json.loads(watchdog_path.read_text()); payload["maximum_actions"] += 1; payload.pop("config_digest")
    from sentientos import maintenance_loop_watchdog as watchdog
    watchdog_path.write_bytes(watchdog.canonical_json_bytes(watchdog.validate_config(payload)))
    assert not owner.start() and calls == [] and owner.health()["status"] == "degraded"


@pytest.mark.parametrize("scheduler_status,health", [
    ("maintenance_scheduler_lock_busy", "lock_contention"),
    ("maintenance_scheduler_stopped", "stopped"),
    ("maintenance_scheduler_stop", "paused"),
    ("maintenance_scheduler_failure_threshold", "failure_threshold_reached"),
    ("maintenance_scheduler_recovery_ambiguous", "degraded"),
])
def test_terminal_results_are_not_restarted(tmp_path, scheduler_status, health):
    value, _, _, _ = adoption(tmp_path); finished = threading.Event(); calls = []
    def run(*args, **kwargs):
        calls.append(1); finished.set(); return {"status": scheduler_status}
    owner = MaintenanceSchedulerOwner(value, runner=run)
    assert owner.start() and finished.wait(1)
    owner.stop()
    assert calls == [1] and owner.health()["status"] == health


def test_ordinary_bounded_completion_reenters_only_after_wait(tmp_path):
    value, _, _, _ = adoption(tmp_path); calls = []; waited = threading.Event()
    def run(*args, **kwargs):
        calls.append(1)
        return {"status": "maintenance_scheduler_cycle_limit" if len(calls) == 1 else "maintenance_scheduler_stopped"}
    def wait(event, seconds):
        assert seconds == value["reentry_delay_seconds"]; waited.set(); return False
    owner = MaintenanceSchedulerOwner(value, runner=run, waiter=wait)
    assert owner.start() and waited.wait(1)
    owner.stop()
    assert len(calls) == 2


def test_shutdown_is_bounded_and_requests_scheduler_stop(tmp_path):
    value, _, _, _ = adoption(tmp_path); entered = threading.Event()
    def run(_cfg, **kwargs):
        entered.set(); kwargs["stop_requested"]()
        while not kwargs["stop_requested"]():
            kwargs["sleeper"](.01)
        return {"status": "maintenance_scheduler_daemon_shutdown"}
    owner = MaintenanceSchedulerOwner(value, runner=run)
    assert owner.start() and entered.wait(1) and owner.stop()
    assert owner.health()["reason"] == "daemon_shutdown"


def test_first_boot_fields_are_not_adoption_or_cadence_authority(tmp_path):
    value, _, _, _ = adoption(tmp_path)
    for field, item in (("architect_autonomy", True), ("codex_interval", 1)):
        with pytest.raises(ValueError, match="invalid_scheduler_daemon_adoption"):
            validate_adoption({**value, field: item})


def test_activation_separately_renders_exact_daemon_adoption(tmp_path):
    value, cfg, profile, _ = adoption(tmp_path)
    output = tmp_path / "daemon-adoption.json"
    rendered = activation.render_daemon_adoption(output, scheduler_config_path=profile,
        evidence_path=value["evidence_path"], enabled=True, shutdown_timeout_seconds=2,
        reentry_delay_seconds=3)
    sealed = json.loads(output.read_text())
    assert rendered["status"] == "daemon_adoption_configuration_ready"
    assert sealed["scheduler_config_digest"] == cfg["config_digest"]
    assert sealed["expected_scheduler_schema"] == scheduler.CONFIG_SCHEMA and sealed["enabled"] is True


def test_scheduler_daemon_adoption_platform_truth_is_posix():
    assert os.name == "posix"
    assert "import fcntl" in Path("sentientos/maintenance_loop_scheduler.py").read_text()


def test_owner_surface_contains_no_candidate_lease_git_provider_or_network_authority():
    source = Path("sentientos/maintenance_scheduler_daemon.py").read_text()
    for forbidden in ("candidate_inbox", "issue_lease", "subprocess", "requests", "urllib", "git commit", "publish"):
        assert forbidden not in source
