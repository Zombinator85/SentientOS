"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import admin_utils


def test_is_admin_true():
    assert admin_utils.is_admin()


    logs = []
    monkeypatch.setattr(admin_utils, "is_admin", lambda: True)
    monkeypatch.setattr(admin_utils, "getpass", type("gp", (), {"getuser": lambda: "tester"}))
    monkeypatch.setattr(admin_utils.platform, "system", lambda: "Linux")
    monkeypatch.setattr(admin_utils.pl, "log_privilege", lambda u, p, t, s: logs.append({"user": u, "platform": p, "tool": t, "status": s}))
    out = capsys.readouterr().out
    assert "Sanctuary Privilege Status: [🛡️ Privileged]" in out
    assert logs and logs[0] == {"user": "tester", "platform": "Linux", "tool": "pytest", "status": "success"}


def test_require_admin_failure(monkeypatch):
    logs = []
    monkeypatch.setattr(admin_utils, "is_admin", lambda: False)
    monkeypatch.setattr(admin_utils, "getpass", type("gp", (), {"getuser": lambda: "tester"}))
    monkeypatch.setattr(admin_utils.platform, "system", lambda: "Linux")
    monkeypatch.setattr(admin_utils.pl, "log_privilege", lambda u, p, t, s: logs.append({"user": u, "platform": p, "tool": t, "status": s}))
    with pytest.raises(SystemExit), pytest.warns(DeprecationWarning):
        admin_utils.require_admin()
    assert logs and logs[0] == {"user": "tester", "platform": "Linux", "tool": "pytest", "status": "failed"}


def test_require_admin_wrapper(monkeypatch):
    with pytest.raises(SystemExit), pytest.warns(DeprecationWarning):
        admin_utils.require_admin()


@pytest.mark.parametrize(
    "platform_name,is_admin,expected",
    [
        ("Linux", True, "success"),
        ("Linux", False, "failed"),
        ("Windows", True, "success"),
        ("Windows", False, "failed"),
        ("Darwin", True, "success"),
        ("Darwin", False, "failed"),
    ],
)
def test_privilege_logging(monkeypatch, platform_name, is_admin, expected):
    logs = []
    monkeypatch.setattr(admin_utils, "is_admin", lambda: is_admin)
    monkeypatch.setattr(admin_utils.platform, "system", lambda: platform_name)
    monkeypatch.setattr(admin_utils, "getpass", type("gp", (), {"getuser": lambda: "tester"}))
    monkeypatch.setattr(admin_utils.pl, "log_privilege", lambda u, p, t, s: logs.append({"user": u, "platform": p, "tool": t, "status": s}))
    if is_admin:
    else:
        with pytest.raises(SystemExit):
    assert logs and logs[0]["status"] == expected
    assert logs[0]["platform"] == platform_name
