import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip


def test_epistemic_cli_distinguishes_pass_failure_and_incomplete(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE", str(tmp_path / "private"))
    module = importlib.import_module(
        "scripts.run_rootless_ollama_epistemic_series")

    assert module._exit_code_for_status("series_passed") == 0
    assert module._exit_code_for_status("series_failed") == 2
    assert module._exit_code_for_status("unknown_or_incomplete") == 3
    assert module._exit_code_for_status(None) == 3



def test_epistemic_cli_help_does_not_create_experiment_workspace(tmp_path):
    repository = Path(__file__).resolve().parents[1]
    script = repository / "scripts" / "run_rootless_ollama_epistemic_series.py"
    workspace = tmp_path / "must-remain-absent"
    environment = os.environ.copy()
    environment["SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE"] = str(workspace)

    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "usage:" in completed.stdout
    assert not workspace.exists()



def test_main_returns_scored_failure_exit_code(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(
        "SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE", str(tmp_path / "private"))
    module = importlib.import_module(
        "scripts.run_rootless_ollama_epistemic_series")
    result = {
        "run_root": "private/run",
        "result": {
            "held_out_key_path": "private/key",
            "preregistration": {"preregistration_digest": "a" * 64},
            "capture_index": {"capture_index_digest": "b" * 64},
            "scores": {"result": {"status": "series_failed"}},
        },
        "model_name": "sentientos-hermes4:14b-q4km",
        "model_manifest_digest": "c" * 64,
        "runtime": {"backend": "ollama-loopback"},
        "gpu_before": None,
        "gpu_after_inference": None,
    }
    monkeypatch.setattr(module, "run", lambda **_: result)
    monkeypatch.setattr(module.sys, "argv", ["runner", "--model", "fake-hermes"])

    assert module.main() == 2
    assert '"process_exit_code": 2' in capsys.readouterr().out
