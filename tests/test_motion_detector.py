from datetime import datetime

from motion_detector import MotionDetector


def test_motion_detector_detects_change():
    detector = MotionDetector(sensitivity=0.05, minimum_pixels=5)
    frame_static = [[[0, 0, 0] for _ in range(12)] for _ in range(12)]
    frame_motion = [
        [pixel[:] for pixel in row]
        for row in frame_static
    ]
    for y in range(6):
        for x in range(6):
            frame_motion[y][x] = [255, 255, 255]

    assert detector.update(frame_static) is None
    result = detector.update(frame_motion, timestamp=datetime(2024, 1, 1))
    assert result is not None
    assert result.score > 0
    assert result.timestamp == datetime(2024, 1, 1)


def test_motion_detector_invalid_args():
    for sensitivity in (0, 1, -0.1, 1.1):
        try:
            MotionDetector(sensitivity=sensitivity)
        except ValueError:
            continue
        raise AssertionError("invalid sensitivity accepted")
