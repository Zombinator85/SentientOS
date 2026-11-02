from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from sentientos.avatar_renderer_report_ingress import renderer_report_world_state_record

pytestmark = pytest.mark.no_legacy_skip


def test_real_godot_demo_emits_bounded_renderer_self_report(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        pytest.skip("Godot is not installed in this validation environment")
    repository_root = Path(__file__).resolve().parents[1]
    project = repository_root / "godot_avatar_demo"
    probe = "res://tests/renderer_report_probe.gd"
    environment = dict(os.environ)
    environment.update({
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
    })

    result = subprocess.run(
        [godot, "--headless", "--path", str(project), "--script", probe],
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "godot_renderer_report_probe_passed" in result.stdout
    assert "SCRIPT ERROR" not in result.stdout + result.stderr
    report_lines = [line for line in result.stdout.splitlines()
                    if line.startswith("sentientos_renderer_report_json:")]
    assert len(report_lines) == 1, result.stdout + result.stderr
    renderer_report = json.loads(report_lines[0].split(":", 1)[1])
    record = renderer_report_world_state_record(renderer_report)
    assert record["payload"]["renderer_report"]["renderer_state"]["motion"]["active_motion"] == "wave"
    assert record["effect_proven"] is False
    assert record["payload"]["observer_issuer_posture"] == "unverified_caller_assertion"
