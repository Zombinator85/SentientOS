"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import os

import love_treasury as lt


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVE_SUBMISSIONS_LOG", str(tmp_path / "sub.jsonl"))
    monkeypatch.setenv("LOVE_REVIEW_LOG", str(tmp_path / "rev.jsonl"))
    monkeypatch.setenv("LOVE_TREASURY_LOG", str(tmp_path / "tre.jsonl"))
    monkeypatch.setenv("LOVE_FEDERATED_LOG", str(tmp_path / "fed.jsonl"))
    importlib.reload(lt)


def test_submit_and_affirm(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    sid = lt.submit_log("Test", ["alice", "bob"], "2024", "demo", "hello", user="alice")
    subs = lt.list_submissions()
    assert subs and subs[0]["id"] == sid
    ok = lt.review_log(sid, "curator", "affirm")
    assert ok
    tres = lt.list_treasury()
    assert tres and tres[0]["id"] == sid

