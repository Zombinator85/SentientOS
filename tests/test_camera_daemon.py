from datetime import datetime, timedelta

from camera_daemon import CameraDaemon, FrameRecord
from motion_detector import MotionDetector
from perception_journal import PerceptionJournal


def test_camera_daemon_records_motion(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    detector = MotionDetector(sensitivity=0.02, minimum_pixels=5)
    daemon = CameraDaemon(
        source=None,
        fps=10,
        pre_event_seconds=1,
        post_event_seconds=1,
        log_dir=tmp_path / "camera",
        detector=detector,
        journal=PerceptionJournal(tmp_path / "journal.jsonl"),
    )
    start = datetime(2024, 1, 1, 0, 0, 0)
    still = [[[0, 0, 0] for _ in range(16)] for _ in range(16)]
    motion = [
        [pixel[:] for pixel in row]
        for row in still
    ]
    for y in range(8):
        for x in range(8):
            motion[y][x] = [255, 255, 255]
    frames = [
        FrameRecord(start + timedelta(seconds=0.0), still),
        FrameRecord(start + timedelta(seconds=0.1), still),
        FrameRecord(start + timedelta(seconds=0.2), motion),
        FrameRecord(start + timedelta(seconds=0.3), motion),
        FrameRecord(start + timedelta(seconds=1.5), still),
    ]
    daemon.process_stream(frames)
    events_log = (tmp_path / "camera" / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert events_log
    payload = events_log[-1]
    assert "event_id" in payload
    clips = list((tmp_path / "camera" / "clips").iterdir())
    assert clips
