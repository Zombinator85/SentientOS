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
    monkeypatch.setattr(admin_utils.pl, "log_privilege", lambda u, p, t, s: logs.append((u, p, t, s)))
    admin_utils.require_admin_banner()
    out = capsys.readouterr().out
    assert "Sanctuary Privilege Status: [🛡️ Privileged]" in out
    assert logs and logs[0][3] == "success"


def test_require_admin_failure(monkeypatch):
    logs = []
    monkeypatch.setattr(admin_utils, "is_admin", lambda: False)
    monkeypatch.setattr(admin_utils.pl, "log_privilege", lambda u, p, t, s: logs.append((u, p, t, s)))
    with pytest.raises(SystemExit):
        admin_utils.require_admin()
    assert logs and logs[0][3] == "failed"


def test_require_admin_wrapper(monkeypatch):
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: (_ for _ in ()).throw(SystemExit))
    with pytest.raises(SystemExit):
        admin_utils.require_admin()
