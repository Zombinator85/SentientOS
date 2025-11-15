import io

from sentientos.dashboard.console import ConsoleDashboard, LogBuffer
from tests.test_console_dashboard import _sample_status


def test_dashboard_renders_federation_replay_section():
    buffer = LogBuffer()
    output = io.StringIO()
    replay = [
        {"peer": "peerA", "severity": "none", "missing": {}, "extra": {}, "details": {}},
        {"peer": "peerB", "severity": "medium", "missing": {"experiments": ["exp-2"]}, "extra": {}, "details": {}},
    ]
    status = _sample_status(federation_replay=replay)
    dashboard = ConsoleDashboard(
        lambda: status,
        log_stream_source=lambda: [],
        refresh_interval=0.5,
        log_buffer=buffer,
        output_stream=output,
    )
    dashboard.run_once()
    rendered = output.getvalue()
    assert "FEDERATION REPLAY" in rendered
    assert "peerB" in rendered
    assert "Δ drift (medium)" in rendered
    assert "missing experiments" in rendered
