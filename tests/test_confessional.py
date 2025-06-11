"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import sys
import importlib
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import confessional_log as clog
import confessional_review as crev
import confessional_cli
import forgiveness_ledger as fledge


def test_log_and_tail(tmp_path, monkeypatch):
    path = tmp_path / "confessional_log.jsonl"
    monkeypatch.setenv("CONFESSIONAL_LOG", str(path))
    importlib.reload(clog)
    clog.log_confession("core", "violation", "detail", tags=["anger"], severity="warning")
    data = clog.tail()[0]
    assert data["subsystem"] == "core"
    assert data["severity"] == "warning"
    assert data["tags"] == ["anger"]


def test_cli_review(tmp_path, monkeypatch, capsys):
    log = tmp_path / "confessional_log.jsonl"
    rev = tmp_path / "confessional_review.jsonl"
    monkeypatch.setenv("CONFESSIONAL_LOG", str(log))
    monkeypatch.setenv("CONFESSIONAL_REVIEW_LOG", str(rev))
    importlib.reload(clog)
    importlib.reload(crev)
    clog.log_confession("core", "violation", "detail")
    monkeypatch.setattr("builtins.input", lambda prompt='': "note")
    monkeypatch.setattr(sys, "argv", ["confess", "review", "--user", "me"])
    importlib.reload(confessional_cli)
    confessional_cli.main()
    out = capsys.readouterr().out
    assert "Confession reflected" in out
    lines = rev.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_council_vote_quorum(tmp_path, monkeypatch):
    log = tmp_path / "confessional_log.jsonl"
    led = tmp_path / "forgiveness_ledger.jsonl"
    monkeypatch.setenv("CONFESSIONAL_LOG", str(log))
    monkeypatch.setenv("FORGIVENESS_LEDGER", str(led))
    importlib.reload(clog)
    importlib.reload(crev)
    entry = clog.log_confession("core", "failure", "detail", severity="critical")
    ts = entry["timestamp"]
    crev.log_council_vote(ts, "u1", "approve", "ok")
    assert crev.council_status(ts) == "pending"
    crev.log_council_vote(ts, "u2", "approve", "ok")
    assert crev.council_status(ts) == "resolved"
    votes = fledge.council_votes(ts)
    assert len(votes) == 2
