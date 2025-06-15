from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import scripts.package_launcher as package_launcher


def test_placeholder(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["package_launcher.py", "--platform", "auto"])

    def fake_call(cmd, *a, **k):
        dist.mkdir(exist_ok=True)
        (dist / "dummy").write_text("ok")
        return 0

    monkeypatch.setattr(subprocess, "check_call", fake_call)
    importlib.reload(package_launcher)
    assert package_launcher.main() == 0
    assert any(dist.iterdir())
