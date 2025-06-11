"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import os
import sys
import json
from pathlib import Path
import argparse
import sentientos.ledger as ledger
import sentientos.ledger_cli as ledger_cli


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


def test_print_summary_expansion(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir()
    sup = tmp_path / "logs" / "support_log.jsonl"
    fed = tmp_path / "logs" / "federation_log.jsonl"
    mus = tmp_path / "logs" / "music_log.jsonl"
    att = tmp_path / "logs" / "ritual_attestations.jsonl"
    sup.write_text(json.dumps({"supporter": "A"}) + "\n", encoding="utf-8")
    with sup.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"supporter": "B"}) + "\n")
    fed.write_text(json.dumps({"peer": "P"}) + "\n", encoding="utf-8")
    mus.write_text(json.dumps({"event": "generated"}) + "\n", encoding="utf-8")
    att.write_text(json.dumps({"user": "W"}) + "\n", encoding="utf-8")
    ledger.print_summary(limit=2)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["unique_supporters"] == 2
    assert data["unique_witnesses"] == 1
    assert data["music_count"] == 1


def test_snapshot_banner(monkeypatch, capsys):
    def fake_sum(path: Path, limit: int = 3):
        return {"count": 1, "recent": []}

    monkeypatch.setattr(ledger, "summarize_log", fake_sum)
    monkeypatch.setattr(ledger, "_unique_values", lambda p, f: 1)
    ledger.print_snapshot_banner()
    out = capsys.readouterr().out
    assert "Ledger snapshot" in out
