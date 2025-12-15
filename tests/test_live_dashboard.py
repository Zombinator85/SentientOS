from __future__ import annotations

import time
from pathlib import Path

import pytest

from sentientos.cli import dashboard_cli
from sentientos.dashboard import dashboard_snapshot


pytestmark = pytest.mark.no_legacy_skip


def _prepare_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    admission_log = tmp_path / "task_admission.jsonl"
    executor_log = tmp_path / "task_executor.jsonl"
    monkeypatch.setattr(dashboard_snapshot, "ADMISSION_LOG_PATH", admission_log)
    monkeypatch.setattr(dashboard_snapshot, "EXECUTOR_LOG_PATH", executor_log)


def test_collect_snapshot_with_missing_sources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    pulse_path = tmp_path / "pulse.json"
    self_path = tmp_path / "self.json"
    _prepare_logs(tmp_path, monkeypatch)

    snapshot = dashboard_snapshot.collect_snapshot(
        log_dir=tmp_path,
        pulse_path=pulse_path,
        self_path=self_path,
    )

    assert snapshot.health.pulse_level == dashboard_snapshot.UNKNOWN_VALUE
    assert snapshot.mind.mood in {"neutral", "stable"}  # defaults applied
    assert snapshot.activity.executor_steps == []


def test_avatar_mapping_and_fallbacks():
    mind_happy = dashboard_snapshot.MindSnapshot(mood="happy", confidence=0.9)
    mind_warning = dashboard_snapshot.MindSnapshot(tension=0.8)
    mind_unknown = dashboard_snapshot.MindSnapshot(mood=None, confidence=0.2)

    assert dashboard_snapshot.build_avatar("STABLE", mind_happy).emoji in {"😊", "🙂"}
    assert dashboard_snapshot.build_avatar("WARNING", mind_warning).emoji in {"😕", "😟"}
    assert dashboard_snapshot.build_avatar("DEGRADED", mind_warning).emoji == "😠"
    neutral_avatar = dashboard_snapshot.build_avatar("STABLE", mind_unknown)
    assert neutral_avatar.emoji == "😐"
    assert neutral_avatar.label in {"steady", "neutral"}


def test_avatar_viseme_progression(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _prepare_logs(tmp_path, monkeypatch)
    now = time.time()
    timeline = [
        {"time": 0.0, "duration": 0.2, "viseme": "A"},
        {"time": 0.25, "duration": 0.15, "viseme": "B"},
    ]

    def _fake_state() -> dict:
        return {
            "phrase": {"text": "hello", "started_at": now - 0.12, "speaking": True, "viseme_count": 2},
            "viseme_timeline": timeline,
            "speaking": True,
            "timestamp": now - 0.05,
        }

    monkeypatch.setattr(dashboard_snapshot, "_load_avatar_state", lambda path=None: _fake_state())
    snapshot = dashboard_snapshot.collect_snapshot(log_dir=tmp_path)

    assert snapshot.avatar.active_viseme in {"A", "B"}
    assert snapshot.avatar.viseme_weight > 0.1
    assert 0.0 < snapshot.avatar.phrase_position <= 1.0
    assert snapshot.avatar.speaking_duration > 0


def test_avatar_viseme_fallbacks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _prepare_logs(tmp_path, monkeypatch)

    monkeypatch.setattr(dashboard_snapshot, "_load_avatar_state", lambda path=None: {"phrase": {"text": ""}})
    snapshot = dashboard_snapshot.collect_snapshot(log_dir=tmp_path)

    assert snapshot.avatar.active_viseme == "neutral"
    assert snapshot.avatar.blendshape_hint in {"breathing", "neutral"}
    assert snapshot.avatar.viseme_weight <= 0.1


def test_render_snapshot_handles_partial_avatar(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _prepare_logs(tmp_path, monkeypatch)
    now = time.time()

    def _fake_state() -> dict:
        return {
            "phrase": {"text": "testing", "started_at": now - 1.0, "speaking": True, "muted": True},
            "viseme_timeline": [{"time": 0.0, "viseme": "X"}],
            "speaking": True,
        }

    monkeypatch.setattr(dashboard_snapshot, "_load_avatar_state", lambda path=None: _fake_state())
    snapshot = dashboard_snapshot.collect_snapshot(log_dir=tmp_path)

    frame = dashboard_cli.render_snapshot(snapshot, refresh_interval=0.5)
    assert "Visemes" in frame
    assert "Active" in frame
    assert "muted" in frame or "speaking" in frame


def test_snapshot_respects_runtime_modes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    pulse_path = tmp_path / "pulse.json"
    self_path = tmp_path / "self.json"
    _prepare_logs(tmp_path, monkeypatch)

    import runtime_mode

    monkeypatch.setattr(runtime_mode, "SENTIENTOS_MODE", "LOCAL_OWNER")
    monkeypatch.setattr(dashboard_snapshot, "SENTIENTOS_MODE", "LOCAL_OWNER")
    local_snapshot = dashboard_snapshot.collect_snapshot(
        log_dir=tmp_path,
        pulse_path=pulse_path,
        self_path=self_path,
    )
    assert local_snapshot.health.mode == "LOCAL_OWNER"

    monkeypatch.setattr(runtime_mode, "SENTIENTOS_MODE", "DOCTRINE")
    monkeypatch.setattr(dashboard_snapshot, "SENTIENTOS_MODE", "DOCTRINE")
    doctrine_snapshot = dashboard_snapshot.collect_snapshot(
        log_dir=tmp_path,
        pulse_path=pulse_path,
        self_path=self_path,
    )
    assert doctrine_snapshot.health.mode == "DOCTRINE"


def test_snapshot_tolerates_degraded_inputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    pulse_path = tmp_path / "pulse.json"
    self_path = tmp_path / "self.json"
    pulse_path.write_text("{bad json", encoding="utf-8")
    self_path.write_text("{not a json", encoding="utf-8")
    _prepare_logs(tmp_path, monkeypatch)

    snapshot = dashboard_snapshot.collect_snapshot(
        log_dir=tmp_path,
        pulse_path=pulse_path,
        self_path=self_path,
    )

    assert snapshot.health.pulse_level == dashboard_snapshot.UNKNOWN_VALUE
    assert snapshot.mind.mood in {"neutral", "stable"}
    assert snapshot.avatar.emoji == "😐"


def test_dashboard_cli_single_frame(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    pulse_path = tmp_path / "pulse.json"
    self_path = tmp_path / "self.json"
    _prepare_logs(tmp_path, monkeypatch)

    exit_code = dashboard_cli.main(
        [
            "--single-frame",
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
    assert "Mood:" in output
    assert "Avatar" in output
