"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import admin_utils


def test_handshake_auditor_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    import resonite_federation_handshake_auditor as hsa
    importlib.reload(hsa)

    calls = []
    monkeypatch.setattr(hsa, "require_admin_banner", lambda: calls.append(True))
    monkeypatch.setattr(sys, "argv", ["hsa", "handshake", "A", "B", "success"])
    hsa.main()
    capsys.readouterr()
    assert calls
    log_file = tmp_path / "resonite_federation_handshake_auditor.jsonl"
    entry = json.loads(log_file.read_text().splitlines()[0])
    assert entry["action"] == "handshake" and entry["from"] == "A"

    calls.clear()
    monkeypatch.setattr(sys, "argv", ["hsa", "history", "--limit", "1"])
    hsa.main()
    out = json.loads(capsys.readouterr().out)
    assert out and out[0]["action"] == "handshake"


def test_handshake_verifier_cli(tmp_path, monkeypatch, capsys):
    log_path = tmp_path / "verify.jsonl"
    monkeypatch.setenv("RESONITE_HANDSHAKE_VERIFIER_LOG", str(log_path))
    import resonite_federation_handshake_verifier as hsv
    importlib.reload(hsv)

    calls = []
    monkeypatch.setattr(hsv, "require_admin_banner", lambda: calls.append(True))
    monkeypatch.setattr(sys, "argv", ["hsv", "verify", "A", "B", "sig"])
    hsv.main()
    capsys.readouterr()
    assert calls
    entry = json.loads(log_path.read_text().splitlines()[0])
    assert entry["action"] == "verify" and entry["status"] == "valid"

    calls.clear()
    monkeypatch.setattr(sys, "argv", ["hsv", "history", "--limit", "1"])
    hsv.main()
    out = json.loads(capsys.readouterr().out)
    assert out and out[0]["action"] == "verify"
