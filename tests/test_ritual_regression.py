import os
from pathlib import Path

FORBIDDEN = ["secret_memory_deletion", "silent_sensor_access", "unblessed_action"]


def test_no_forbidden_patterns(tmp_path):
    root = Path(__file__).resolve().parent.parent
    issues = []
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for patt in FORBIDDEN:
            if patt in text:
                issues.append(f"{path}:{patt}")
    assert not issues, "Heresy detected in code. Presence denied."
