"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import importlib
import love_treasury as lt
import treasury_federation as tf
import pytest

import sentient_banner as sb


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVE_SUBMISSIONS_LOG", str(tmp_path / "sub.jsonl"))
    monkeypatch.setenv("LOVE_REVIEW_LOG", str(tmp_path / "rev.jsonl"))
    monkeypatch.setenv("LOVE_TREASURY_LOG", str(tmp_path / "tre.jsonl"))
    monkeypatch.setenv("LOVE_FEDERATED_LOG", str(tmp_path / "fed.jsonl"))
    monkeypatch.setattr(sb, "print_banner", lambda: None)
    monkeypatch.setattr(sb, "print_closing", lambda: None)
    importlib.reload(lt)
    importlib.reload(tf)


def test_import_payload(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    lid = lt.submit_log("Loc", ["a"], "now", "demo", "text", user="a")
    lt.review_log(lid, "cur", "affirm")
    payload = lt.list_treasury()
    imported = tf.import_payload(payload, origin="remote")
    assert imported and imported[0] == lid
    fed = lt.list_federated()
    assert fed and fed[0]["id"] == lid

