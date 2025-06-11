"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import audit_immutability as ai


def _make_log(tmp_path: Path) -> Path:
    log = tmp_path / "log.jsonl"
    ai.append_entry(log, {"x": 1})
    return log


def test_cli_env_auto(tmp_path: Path) -> None:
    _make_log(tmp_path)
    env = os.environ.copy()
    env["LUMOS_AUTO_APPROVE"] = "1"
    env["PYTHONPATH"] = "."
    cp = subprocess.run([sys.executable, "verify_audits.py", str(tmp_path)], env=env)
    assert cp.returncode == 0


def test_cli_flag_auto(tmp_path: Path) -> None:
    _make_log(tmp_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    cp = subprocess.run([sys.executable, "verify_audits.py", str(tmp_path), "--auto-approve"], env=env)
    assert cp.returncode == 0
