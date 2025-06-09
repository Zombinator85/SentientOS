import os
import sys
import pytest
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import privilege_lint as pl


def test_strict_exit_one(tmp_path, monkeypatch):
    bad = tmp_path / "tool_cli.py"
    bad.write_text("print('hi')\n", encoding="utf-8")
    monkeypatch.setattr(pl, "find_entrypoints", lambda root: [bad])
    monkeypatch.setenv("SENTIENTOS_LINT_STRICT", "1")
    monkeypatch.setattr(sys, "argv", ["privilege_lint.py"])
    with pytest.raises(SystemExit) as exc:
        sys.exit(pl.main())
    assert exc.value.code == 1
