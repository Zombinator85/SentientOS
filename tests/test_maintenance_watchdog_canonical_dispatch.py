import pytest

from sentientos import maintenance_loop_watchdog as watchdog
from tests.test_maintenance_watchdog_scan import config

pytestmark = pytest.mark.no_legacy_skip


def test_tick_dispatches_existing_component_without_injected_handler(tmp_path):
    result = watchdog.tick(config(tmp_path), evaluation_time="2026-08-06T00:00:00Z")
    assert result["transition"] == "idle"
    assert "canonical_component_not_configured" not in str(result)


def test_cli_tick_performs_configured_transition(tmp_path, capsys):
    import json
    from scripts.maintenance_loop_watchdog import main

    path = tmp_path / "watchdog.json"
    path.write_text(json.dumps(config(tmp_path)))
    assert main(["--config", str(path), "--evaluation-time", "2026-08-06T00:00:00Z", "tick"]) == 0
    assert json.loads(capsys.readouterr().out)["transition"] == "idle"
