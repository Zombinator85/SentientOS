"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import sys
import os
from pathlib import Path
from importlib import reload

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import github_bridge as gb


class DummyApi:
    def __init__(self) -> None:
        self.called: list[tuple[str, tuple, dict]] = []
        self.search = type("S", (), {"code": self._search})()
        self.issues = type("I", (), {"create": self._create_issue})()
        self.pulls = type("P", (), {"create": self._create_pr})()

    def _search(self, *args, **kwargs):
        self.called.append(("search", args, kwargs))
        return {"items": []}

    def _create_issue(self, *args, **kwargs):
        self.called.append(("issue", args, kwargs))
        return {"html_url": "http://example.com/i/1"}

    def _create_pr(self, *args, **kwargs):
        self.called.append(("pr", args, kwargs))
        return {"html_url": "http://example.com/p/1"}


def test_token_persist(tmp_path, monkeypatch):
    key = tmp_path / "k.key"
    tok = tmp_path / "t.enc"
    monkeypatch.setattr(gb, "KEY_FILE", key)
    monkeypatch.setattr(gb, "TOKEN_FILE", tok)
    reload(gb)
    bridge = gb.GitHubBridge(token_file=tok, key_file=key)
    bridge.set_token("model", "abc")
    assert tok.exists()
    b2 = gb.GitHubBridge(token_file=tok, key_file=key)
    assert b2.tokens["model"] == "abc"


def test_api_calls(monkeypatch, tmp_path):
    key = tmp_path / "k.key"
    tok = tmp_path / "t.enc"
    monkeypatch.setattr(gb, "KEY_FILE", key)
    monkeypatch.setattr(gb, "TOKEN_FILE", tok)
    dummy = DummyApi()
    monkeypatch.setitem(sys.modules, "ghapi.all", type("M", (), {"GhApi": lambda token=None: dummy}))
    reload(gb)
    bridge = gb.GitHubBridge(token_file=tok, key_file=key)
    bridge.set_token("default", "tok")
    bridge.search_code("foo")
    bridge.create_issue("o/r", "t", "b")
    bridge.create_pr("o/r", "t", "b", "h", "base")
    kinds = [c[0] for c in dummy.called]
    assert kinds == ["search", "issue", "pr"]
