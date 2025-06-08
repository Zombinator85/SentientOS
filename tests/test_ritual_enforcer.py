import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import ritual_enforcer

def test_check_and_fix(tmp_path, monkeypatch):
    src = tmp_path / "demo.py"
    src.write_text("import os\nif __name__ == '__main__':\n    val = input('q?')\n", encoding="utf-8")
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
    fixed = src.read_text().splitlines()
    assert fixed[:3] == [
        '"""Privilege Banner: requires admin & Lumos approval."""',
        'require_admin_banner()',
        'require_lumos_approval()',
    ]
    assert fixed[3].startswith('from admin_utils')
    assert "prompt_yes_no(" in "\n".join(fixed)
    assert (backups / f"{src.name}.bak").exists()

