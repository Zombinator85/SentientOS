import os
import sys
import json
from pathlib import Path
import argparse
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import ledger
import ledger_cli


def test_log_and_summary(tmp_path, monkeypatch):
    # patch internal append to write under tmp_path
    def fake_append(path: Path, entry: dict):
        target = tmp_path / path.name
        with target.open('a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + "\n")
        return entry
    monkeypatch.setattr(ledger, "_append", fake_append)

    ledger.log_support("Alice", "hello", "$1")
    ledger.log_federation("peer1", "", "hi")

    sup = ledger.summarize_log(tmp_path / "support_log.jsonl")
    fed = ledger.summarize_log(tmp_path / "federation_log.jsonl")

    assert sup["count"] == 1
    assert sup["recent"][0]["supporter"] == "Alice"
    assert fed["count"] == 1
    assert fed["recent"][0]["peer"] == "peer1"


def test_cli_open(tmp_path, capsys, monkeypatch):
    sup = tmp_path / "support_log.jsonl"
    fed = tmp_path / "federation_log.jsonl"
    sup.write_text(json.dumps({"supporter": "Bob"}) + "\n", encoding="utf-8")
    fed.write_text(json.dumps({"peer": "site"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(ledger_cli, "SUPPORT_LOG", sup)
    monkeypatch.setattr(ledger_cli, "FED_LOG", fed)
    ledger_cli.cmd_open(argparse.Namespace())
    out = capsys.readouterr().out
    assert "Bob" in out and "site" in out
