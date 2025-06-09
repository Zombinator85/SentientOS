import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import admin_utils


def test_banner_unicode(monkeypatch, capsys):
    monkeypatch.setattr(admin_utils, "is_admin", lambda: True)
    class Dummy:
        def __init__(self) -> None:
            self.encoding = "cp1252"
        def write(self, s: str) -> None:
            pass
        def flush(self) -> None:
            pass

    dummy = Dummy()
    monkeypatch.setattr(sys, "stdout", dummy)
    admin_utils.print_privilege_banner_safe()
    capsys.readouterr()

