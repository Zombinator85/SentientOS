from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import sys
import os
from importlib import reload
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import reflection_log_cli as rlc


def test_load_entries(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "2025-01-01.log").write_text("first\nsecond\n")
    monkeypatch.setenv("REFLECTION_LOG_DIR", str(log_dir))
    reload(rlc)
    entries = list(rlc.load_entries())
    assert entries[0][1] == "second"
    assert entries[1][1] == "first"


def test_cli_main(tmp_path, monkeypatch, capsys):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "2025-01-01.log").write_text("hi there\n")
    monkeypatch.setenv("REFLECTION_LOG_DIR", str(log_dir))
    from importlib import reload
    reload(rlc)
    monkeypatch.setattr(rlc, "require_admin_banner", lambda: None)
    monkeypatch.setattr(sys, "argv", ["rlc", "--last", "1"])
    rlc.main()
    out = capsys.readouterr().out
    assert "[" in out

