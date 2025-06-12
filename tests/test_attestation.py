"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import importlib
import love_treasury as lt
import treasury_attestation as ta


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVE_SUBMISSIONS_LOG", str(tmp_path / "sub.jsonl"))
    monkeypatch.setenv("LOVE_REVIEW_LOG", str(tmp_path / "rev.jsonl"))
    monkeypatch.setenv("LOVE_TREASURY_LOG", str(tmp_path / "tre.jsonl"))
    monkeypatch.setenv("LOVE_FEDERATED_LOG", str(tmp_path / "fed.jsonl"))
    importlib.reload(lt)
    importlib.reload(ta)


def test_attest(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    lid = lt.submit_log("Test", ["alice"], "2024", "demo", "text")
    lt.review_log(lid, "cur", "affirm")
    att = ta.add_attestation(lid, "bob", "remote", note="nice")
    hist = ta.history(lid)
    assert hist and hist[0]["id"] == att
