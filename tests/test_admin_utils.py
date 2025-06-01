import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import admin_utils


def test_is_admin_true():
    assert admin_utils.is_admin()


def test_require_admin_banner(capsys, monkeypatch):
    logs = []
    monkeypatch.setattr(admin_utils, "is_admin", lambda: True)
    monkeypatch.setattr(admin_utils.pl, "log", lambda u, e, n: logs.append((u, e, n)))
    admin_utils.require_admin()
    out = capsys.readouterr().out
    assert "Sanctuary Privilege Check: PASSED" in out
    assert logs and logs[0][1] == "admin_privilege_check" and logs[0][2] == "success"


def test_require_admin_failure(monkeypatch):
    logs = []
    monkeypatch.setattr(admin_utils, "is_admin", lambda: False)
    monkeypatch.setattr(admin_utils.pl, "log", lambda u, e, n: logs.append((u, e, n)))
    with pytest.raises(SystemExit):
        admin_utils.require_admin()
    assert logs and logs[0][2] == "failed"
