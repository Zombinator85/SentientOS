import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import admin_utils


def test_is_admin_true():
    assert admin_utils.is_admin()


def test_require_admin_banner(capsys, monkeypatch):
    monkeypatch.setattr(admin_utils, "is_admin", lambda: True)
    admin_utils.require_admin()
    out = capsys.readouterr().out
    assert "runs as Administrator" in out
