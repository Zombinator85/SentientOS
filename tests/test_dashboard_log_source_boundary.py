from __future__ import annotations

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.dashboard.console import LogBuffer
from sentientos.dashboard.status_source import make_log_stream_source


def test_dashboard_log_source_returns_a_replayable_sequence() -> None:
    source = make_log_stream_source(LogBuffer(), lambda: (line for line in ["first", "second"]))

    lines = source()

    assert isinstance(lines, list)
    assert len(lines) == 2
    assert lines[0].endswith("first")
    assert lines[1].endswith("second")
