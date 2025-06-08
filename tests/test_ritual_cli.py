from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import os
import sys
import json
import threading
import importlib
from pathlib import Path

import ritual
import doctrine
import ledger


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCTRINE_CONSENT_LOG", str(tmp_path / "consent.jsonl"))
    monkeypatch.setenv("DOCTRINE_STATUS_LOG", str(tmp_path / "status.jsonl"))
    monkeypatch.setenv("DOCTRINE_AMEND_LOG", str(tmp_path / "amend.jsonl"))
    monkeypatch.setenv("PUBLIC_RITUAL_LOG", str(tmp_path / "public.jsonl"))
    monkeypatch.setenv("DOCTRINE_SIGNATURE_LOG", str(tmp_path / "sig.jsonl"))

    def log_support(name, message, amount=""):
        entry = {
            "timestamp": "now",
            "supporter": name,
            "message": message,
            "amount": amount,
            "ritual": "Sanctuary blessing acknowledged and remembered.",
        }
        p = tmp_path / "support_log.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    monkeypatch.setattr(ledger, "log_support", log_support)
    importlib.reload(doctrine)
    importlib.reload(ritual)
    return tmp_path


def test_concurrent_affirm_bless(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)

    def affirm():
        doctrine.affirm("alice")

    def bless():
        ledger.log_support("alice", "hi")

    threads = [threading.Thread(target=affirm) for _ in range(3)]
    threads += [threading.Thread(target=bless) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    cons = Path(os.environ["DOCTRINE_CONSENT_LOG"]).read_text().splitlines()
    sup = (tmp_path / "support_log.jsonl").read_text().splitlines()
    assert len(cons) == 3
    assert len(sup) == 3


def test_cli_edge_cases(tmp_path, monkeypatch, capsys):
    setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["ritual", "affirm", "--signature", "☯️", "--user", "bob"])
    ritual.main()
    long_msg = "x" * 512
    monkeypatch.setattr(sys, "argv", ["ritual", "bless", "--name", "bob", "--message", long_msg, "--amount", "1"])
    ritual.main()
    monkeypatch.setattr(sys, "argv", ["ritual", "recap", "--highlight", "--last", "5"])
    ritual.main()
    out = capsys.readouterr().out
    assert "Affirmations:" in out and "Blessings:" in out
