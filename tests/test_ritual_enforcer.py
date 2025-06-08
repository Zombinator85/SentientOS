import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import ritual_enforcer

def test_check_and_fix(tmp_path, monkeypatch):
    src = tmp_path / "demo.py"
    src.write_text("import os\nval = input('q?')\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    # check mode should report issues and return non-zero
    ret = ritual_enforcer.main(["--mode", "check", "--files", src.name])
    assert ret == 1

    backups = tmp_path / "backups"
    ret = ritual_enforcer.main([
        "--mode",
        "fix",
        "--files",
        src.name,
        "--backup-dir",
        str(backups),
    ])
    assert ret == 0
    fixed = src.read_text()
    assert "Sanctuary Privilege Banner" in fixed
    assert "prompt_yes_no(" in fixed
    assert (backups / f"{src.name}.bak").exists()

