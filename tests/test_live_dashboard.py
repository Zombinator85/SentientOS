from __future__ import annotations

import pytest

from sentientos.dashboard import live_dashboard
from sentientos.cli import dashboard_cli


pytestmark = pytest.mark.no_legacy_skip


def test_collect_snapshot_with_missing_sources(monkeypatch, tmp_path):
    pulse_path = tmp_path / "pulse.json"
    self_path = tmp_path / "self.json"
    admission_log = tmp_path / "task_admission.jsonl"
    executor_log = tmp_path / "task_executor.jsonl"

    monkeypatch.setattr(live_dashboard, "ADMISSION_LOG_PATH", admission_log)
    monkeypatch.setattr(live_dashboard, "EXECUTOR_LOG_PATH", executor_log)

    snapshot = live_dashboard.collect_snapshot(
        log_dir=tmp_path,
        pulse_path=pulse_path,
        self_path=self_path,
    )

    assert snapshot.health.pulse_level == live_dashboard.UNKNOWN_VALUE
    assert snapshot.mind.mood is not None  # defaults applied
    assert snapshot.activity.executor_steps == []


def test_avatar_mapping_returns_emoji():
    mind_happy = live_dashboard.MindSnapshot(mood="happy", confidence=0.9)
    mind_warning = live_dashboard.MindSnapshot(tension=0.8)
    mind_tired = live_dashboard.MindSnapshot(mood="tired")

    assert live_dashboard.build_avatar("STABLE", mind_happy).emoji in {"😊", "🙂"}
    assert live_dashboard.build_avatar("WARNING", mind_warning).emoji in {"😕", "😟"}
    assert live_dashboard.build_avatar("DEGRADED", mind_tired).emoji == "😠"


def test_dashboard_cli_single_frame(monkeypatch, tmp_path, capsys):
    pulse_path = tmp_path / "pulse.json"
    self_path = tmp_path / "self.json"
    admission_log = tmp_path / "task_admission.jsonl"
    executor_log = tmp_path / "task_executor.jsonl"

    monkeypatch.setattr(live_dashboard, "ADMISSION_LOG_PATH", admission_log)
    monkeypatch.setattr(live_dashboard, "EXECUTOR_LOG_PATH", executor_log)

    exit_code = dashboard_cli.main(
        [
            "--once",
            "--refresh-interval",
            "0.5",
            "--pulse-path",
            str(pulse_path),
            "--self-path",
            str(self_path),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "SentientOS Live Dashboard" in output
