import json
from pathlib import Path

import sentientos.audit_immutability as ai
import sentientos.cleanup_audit as ca


def test_cleanup_directory(tmp_path: Path) -> None:
    d = tmp_path / "logs"
    d.mkdir()
    log = d / "log.jsonl"
    ai.append_entry(log, {"x": 1})
    log.write_text(log.read_text() + "{bad}\n", encoding="utf-8")
    results, percent = ca.cleanup_directory(d)
    assert list(results.keys()) == [str(log)]
    assert results[str(log)] == [2]
    assert percent == 50.0
