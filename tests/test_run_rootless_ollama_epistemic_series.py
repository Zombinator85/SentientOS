import importlib

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
