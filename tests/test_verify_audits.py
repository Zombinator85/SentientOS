import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import audit_immutability as ai
import verify_audits as va


def test_verify_valid_log(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    ai.append_entry(log, {"x": 1})
    ai.append_entry(log, {"y": 2})
    ok, errors = va.check_file(log)
    assert ok
    assert errors == []


def test_verify_bad_line(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    log.write_text("{bad json}\n", encoding="utf-8")
    ok, errors = va.check_file(log)
    assert not ok
    assert errors
