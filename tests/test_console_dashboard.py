from __future__ import annotations

import io
from datetime import datetime
from unittest.mock import MagicMock, patch

from sentientos.dashboard.console import ConsoleDashboard, DashboardStatus, LogBuffer
from sentientos.cli.dashboard_cli import _run_demo
from sentientos.experiments.demo_gallery import DemoRun
from sentientos.experiments.runner import ChainRunResult


def _sample_status(**overrides):
    base = dict(
        node_name="APRIL-PC01",
        model_name="Mixtral-8x7B",
        model_status="online",
        persona_enabled=True,
        persona_mood="calm",
        last_persona_msg="All systems steady.",
        experiments_run=5,
        experiments_success=4,
        experiments_failed=1,
        last_experiment_desc="temp >= 20°C",
        last_experiment_result="success",
        consensus_mode="single-node",
        last_update_ts=datetime(2024, 5, 20, 12, 0, 0),
        cathedral_accepted=2,
        cathedral_applied=1,
        cathedral_quarantined=1,
        last_applied_id="amend-122",
        last_quarantined_id="amend-123",
        last_quarantine_error="Invariant breach",
    )
    base.update(overrides)
    return DashboardStatus(**base)


def test_console_dashboard_render_includes_status():
    buffer = LogBuffer()
    output = io.StringIO()
    status = _sample_status()

    def status_source() -> DashboardStatus:
        return status

    def log_source():
        return ["Demo step started"]

    dashboard = ConsoleDashboard(
        status_source,
        log_stream_source=log_source,
        refresh_interval=0.5,
        log_buffer=buffer,
        output_stream=output,
        recent_event_limit=5,
    )
    dashboard.run_once()
    rendered = output.getvalue()
    assert "APRIL-PC01" in rendered
    assert "Mixtral-8x7B" in rendered
    assert "mood: calm" in rendered
    assert "Demo step started" in rendered
    assert "Cathedral: Accepted: 2" in rendered
    assert "Applied: 1" in rendered
    assert "Last Applied: amend-122" in rendered
    assert "Last Quarantined: amend-123" in rendered


def test_console_dashboard_deterministic_render():
    buffer = LogBuffer()
    output = io.StringIO()
    status = _sample_status()

    dashboard = ConsoleDashboard(
        lambda: status,
        log_stream_source=lambda: [],
        refresh_interval=0.5,
        log_buffer=buffer,
        output_stream=output,
    )
    first_frame = dashboard.run_once()
    second_frame = dashboard.run_once()
    assert first_frame == second_frame


def test_log_buffer_caps_entries():
    buffer = LogBuffer(max_lines=3)
    for index in range(5):
        buffer.add(f"line {index}")
    recent = buffer.get_recent()
    assert len(recent) == 3
    assert recent[0].endswith("line 2")
    assert recent[-1].endswith("line 4")


@patch("sentientos.cli.dashboard_cli.demo_gallery.run_demo")
def test_cli_run_demo_streams_to_buffer(mock_run_demo):
    buffer = LogBuffer()
    chain_result = ChainRunResult(
        chain_id="demo_simple_success",
        outcome="success",
        final_experiment_id="step1",
        steps=[],
    )
    demo_run = DemoRun(spec={}, chain=MagicMock(), result=chain_result)

    def fake_run(name, stream):
        stream("Step 1 complete")
        return demo_run

    mock_run_demo.side_effect = fake_run

    result = _run_demo("demo_simple_success", buffer)
    assert result is demo_run
    mock_run_demo.assert_called_once()
    lines = buffer.get_recent()
    assert any(entry.endswith("Demo 'demo_simple_success' starting.") for entry in lines)
    assert any("Step 1 complete" in entry for entry in lines)
    assert any(entry.endswith("Demo 'demo_simple_success' completed successfully.") for entry in lines)


@patch("sentientos.start.ConsoleDashboard")
@patch("sentientos.start.RuntimeShell")
@patch("sentientos.start.load_config")
@patch("sentientos.start.threading.Event")
@patch("sentientos.start.signal.signal")
def test_start_respects_disabled_dashboard(mock_signal, mock_event, mock_load_config, mock_runtime_shell, mock_console_dashboard):
    config = {
        "runtime": {"watchdog_interval": 2.0},
        "dashboard": {"enabled": False},
    }
    mock_load_config.return_value = config
    event_instance = MagicMock()
    event_instance.wait.side_effect = [True]
    mock_event.return_value = event_instance
    shell_instance = mock_runtime_shell.return_value

    result = __import__("sentientos.start", fromlist=["run"]).run()

    assert result == 0
    shell_instance.start.assert_called_once()
    shell_instance.shutdown.assert_called_once()
    mock_console_dashboard.assert_not_called()
