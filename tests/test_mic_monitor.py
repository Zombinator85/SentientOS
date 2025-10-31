from datetime import datetime, timedelta
from pathlib import Path

from mic_monitor import MicMonitor
from perception_journal import PerceptionJournal


def test_mic_monitor_detects_and_logs(tmp_path):
    journal_path = tmp_path / "journal.jsonl"
    monitor = MicMonitor(
        threshold_db=80.0,
        min_duration=0.2,
        window_seconds=0.05,
        log_path=tmp_path / "loudness.jsonl",
        journal=PerceptionJournal(journal_path),
    )
    start = datetime(2024, 1, 1, 0, 0, 0)
    loud_block = [0.5] * 8000
    quiet_block = [0.0] * 8000
    for i in range(6):
        monitor.process_block(loud_block, timestamp=start + timedelta(seconds=0.05 * i))
    finished = None
    for i in range(6, 14):
        result = monitor.process_block(
            quiet_block,
            timestamp=start + timedelta(seconds=0.05 * i),
        )
        if result is not None:
            finished = result
    assert finished is not None
    assert finished.peak_db >= 80.0
    log_text = Path(monitor.log_path).read_text(encoding="utf-8")
    assert "peak_db" in log_text
    events = monitor.events_between(start, start + timedelta(seconds=1))
    assert events and events[0].duration >= 0.2
