import os
import sys
import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import privilege_lint as pl


def test_exit_zero(monkeypatch):
    monkeypatch.setattr(pl, "find_entrypoints", lambda root: [])
    monkeypatch.setattr(sys, "argv", ["privilege_lint.py"])
    with pytest.raises(SystemExit) as exc:
        sys.exit(pl.main())
    assert exc.value.code == 0
