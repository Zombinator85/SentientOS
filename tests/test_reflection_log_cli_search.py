import os
import sys
from importlib import reload
from pathlib import Path


import sentientos.reflection_log_cli as rlc


def test_search_entries(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "2025-01-01.log").write_text("one keyword here\nsecond line\n")
    monkeypatch.setenv("REFLECTION_LOG_DIR", str(log_dir))
    reload(rlc)
    results = list(rlc.search_entries("keyword"))
    assert results and "keyword" in results[0][1]
