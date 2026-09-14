from __future__ import annotations
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
import pytest
from sentientos import maintenance_wake_daemon_adoption as daemon
from sentientos import maintenance_wake_cycle as wake

pytestmark = pytest.mark.no_legacy_skip


def configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, enabled: bool = True):
    repo = tmp_path / "repo"; repo.mkdir(); (repo / ".git").mkdir()
    state = tmp_path / "state"; state.mkdir(mode=0o700)
    wake_path = tmp_path / "wake.json"; wake_path.write_text("{}")
    bound = {"schema_version": wake.CONFIG_SCHEMA, "repository_root": str(repo), "config_digest": "sha256:wake"}
    monkeypatch.setattr(daemon.wake, "load_config", lambda path: dict(bound))
    monkeypatch.setattr(daemon.wake, "doctor", lambda *a, **k: {"status": "maintenance_wake_ready"})
    value = {"schema_version": daemon.ADOPTION_SCHEMA, "enabled": enabled,
        "wake_config_path": str(wake_path), "wake_config_digest": "sha256:wake",
        "expected_wake_schema": wake.CONFIG_SCHEMA, "cadence_state_root": str(state),
        "journal_path": str(state / "cadence.jsonl"), "evidence_path": str(state / "owner.jsonl"),
        "stop_marker": str(state / "STOP"), "cadence_interval_seconds": 60,
        "schedule_anchor_utc": "2030-01-01T00:00:00Z", "initial_run_posture": "immediate",
        "maximum_cycles": 1, "maximum_daemon_wall_clock_seconds": 120, "shutdown_timeout_seconds": 1}
    return daemon.validate_adoption(value), bound, wake_path


def test_disabled_or_unselected_has_no_effect(tmp_path, monkeypatch):
    cfg, _, _ = configured(tmp_path, monkeypatch, enabled=False); calls = []
    owner = daemon.MaintenanceWakeOwner(cfg, runner=lambda *a, **k: calls.append(1))
    assert owner.start() is False and owner.health()["status"] == "disabled" and calls == []
    assert "SENTIENTOS_MAINTENANCE_WAKE_ADOPTION_CONFIG" not in os.environ


def test_exact_enabled_adoption_one_due_wake_intent_receipt_and_bound(tmp_path, monkeypatch):
    cfg, _, _ = configured(tmp_path, monkeypatch); seen = []
    def invoke(bound, *, evaluation_time):
        rows = Path(cfg["journal_path"]).read_text().splitlines()
        assert json.loads(rows[-1])["event_type"] == "invocation_intent"
        seen.append((bound, evaluation_time)); return {"status": "maintenance_wake_idle"}
    result = daemon.run_bounded(cfg, wall_clock=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc),
        monotonic=lambda: 0.0, wake_runner=invoke)
    assert result["status"] == "maintenance_wake_daemon_cycle_limit" and len(seen) == 1
    assert seen[0][1].endswith("Z") and "+" not in seen[0][1]
    assert [json.loads(x)["event_type"] for x in Path(cfg["journal_path"]).read_text().splitlines()] == ["invocation_intent", "invocation_completed"]


def test_not_due_and_missed_intervals_collapse(tmp_path, monkeypatch):
    cfg, _, _ = configured(tmp_path, monkeypatch); calls = []
    assert daemon.run_once(cfg, evaluation_time=datetime(2029, 1, 1, tzinfo=timezone.utc), wake_runner=lambda *a, **k: calls.append(1))["status"] == "maintenance_wake_daemon_not_due"
    result = daemon.run_once(cfg, evaluation_time=datetime(2030, 1, 1, 1, tzinfo=timezone.utc), wake_runner=lambda *a, **k: (calls.append(1) or {"status":"maintenance_wake_idle"}))
    assert result["event"]["next_due_utc"] == "2030-01-01T01:01:00Z" and calls == [1]


def test_naive_clock_and_exact_drift_fail_before_wake(tmp_path, monkeypatch):
    cfg, bound, _ = configured(tmp_path, monkeypatch); calls = []
    with pytest.raises(ValueError, match="not_timezone_aware"):
        daemon.run_once(cfg, evaluation_time=datetime(2030, 1, 1), wake_runner=lambda *a, **k: calls.append(1))
    monkeypatch.setattr(daemon.wake, "load_config", lambda path: {**bound, "config_digest":"sha256:changed"})
    with pytest.raises(ValueError, match="config_drift"):
        daemon.run_once(cfg, evaluation_time=datetime(2030, 1, 1, tzinfo=timezone.utc), wake_runner=lambda *a, **k: calls.append(1))
    assert calls == []


def test_nested_component_drift_and_unmatched_or_corrupt_evidence_block(tmp_path, monkeypatch):
    cfg, _, _ = configured(tmp_path, monkeypatch); monkeypatch.setattr(daemon.wake, "doctor", lambda *a, **k: {"status":"maintenance_wake_blocked", "reason_codes":["component_configuration_disagreement"]})
    with pytest.raises(ValueError, match="component_drift"): daemon.run_once(cfg, evaluation_time=datetime(2030,1,1,tzinfo=timezone.utc))
    monkeypatch.setattr(daemon.wake, "doctor", lambda *a, **k: {"status":"maintenance_wake_ready"})
    daemon._append(cfg, {"event_type":"invocation_intent", "invocation_ordinal":1, "evaluation_time":"2030-01-01T00:00:00Z", "wake_status":None, "disposition":"pending", "next_due_utc":"2030-01-01T00:00:00Z"}, daemon.ZERO_DIGEST)
    with pytest.raises(ValueError, match="recovery_ambiguous"): daemon.inspect(cfg)
    Path(cfg["journal_path"]).write_text("not-json\n")
    with pytest.raises(ValueError, match="journal_corrupt"): daemon.inspect(cfg)


def test_stop_and_blocked_unknown_results_are_terminal(tmp_path, monkeypatch):
    cfg, _, _ = configured(tmp_path, monkeypatch); Path(cfg["stop_marker"]).touch(); calls=[]
    assert daemon.run_once(cfg, evaluation_time=datetime(2030,1,1,tzinfo=timezone.utc), wake_runner=lambda *a,**k:calls.append(1))["status"] == "maintenance_wake_daemon_paused"
    Path(cfg["stop_marker"]).unlink()
    assert daemon.run_once(cfg, evaluation_time=datetime(2030,1,1,tzinfo=timezone.utc), wake_runner=lambda *a,**k:{"status":"surprise"})["status"] == "maintenance_wake_daemon_unknown_result"


def test_owner_cooperative_shutdown_and_bounded_timeout(tmp_path, monkeypatch):
    cfg, _, _ = configured(tmp_path, monkeypatch); entered=threading.Event()
    def run(_cfg, **kwargs): entered.set(); kwargs["stop_requested"]() or kwargs["waiter"](.1); return {"status":"maintenance_wake_daemon_shutdown"}
    owner=daemon.MaintenanceWakeOwner(cfg,runner=run); assert owner.start() and entered.wait(1) and owner.stop()
    events=[json.loads(x)["event_type"] for x in Path(cfg["evidence_path"]).read_text().splitlines()]
    assert "daemon_shutdown_requested" in events and owner.health()["status"] == "stopped"


def test_first_boot_and_downstream_authority_fields_are_closed(tmp_path, monkeypatch):
    cfg, _, _ = configured(tmp_path, monkeypatch)
    for field in ("architect_autonomy", "codex_interval", "codex_mode", "codex_max_iterations", "candidate_inbox", "lease", "provider"):
        with pytest.raises(ValueError, match="invalid_wake_daemon_adoption"): daemon.validate_adoption({**cfg, field: True})
    source=Path("sentientos/maintenance_wake_daemon_adoption.py").read_text()
    for forbidden in ("subprocess", "requests", "urllib", "git commit", "issue_lease", "candidate_inbox"):
        assert forbidden not in source


def test_platform_truth_is_posix_fcntl():
    assert os.name == "posix" and "import fcntl" in Path("sentientos/maintenance_wake_daemon_adoption.py").read_text()
