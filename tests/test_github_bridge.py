"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import sys
import os
from importlib import reload
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import github_bridge as gb


from typing import Any


class DummyApi:
    def __init__(self) -> None:
        self.called: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.search = type("S", (), {"code": self._search})()
        self.issues = type("I", (), {"create": self._create_issue})()
        self.pulls = type("P", (), {"create": self._create_pr})()
        self.users = type("U", (), {"get_authenticated": lambda self: None})()
        self.recv_hdrs = {"X-OAuth-Scopes": "repo"}

    def _search(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.called.append(("search", args, kwargs))
        return {"items": []}

    def _create_issue(self, *args: Any, **kwargs: Any) -> dict[str, str]:
        self.called.append(("issue", args, kwargs))
        return {"html_url": "http://example.com/i/1"}

    def _create_pr(self, *args: Any, **kwargs: Any) -> dict[str, str]:
        self.called.append(("pr", args, kwargs))
        return {"html_url": "http://example.com/p/1"}


def _mock_keyring(monkeypatch: pytest.MonkeyPatch, store: dict[str, str]) -> None:
    kr = type(
        "KR",
        (),
        {
            "set_password": lambda service, user, tok: store.__setitem__(user, tok),
            "get_password": lambda service, user: store.get(user),
        },
    )
    monkeypatch.setitem(sys.modules, "keyring", kr)


def test_token_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict[str, str] = {}
    _mock_keyring(monkeypatch, store)
    reload(gb)
    bridge = gb.GitHubBridge(service="svc")
    bridge.set_token("model", "abc")
    b2 = gb.GitHubBridge(service="svc")
    assert b2._token_for("model") == "abc"


def test_scope_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict[str, str] = {}
    _mock_keyring(monkeypatch, store)
    dummy = DummyApi()
    monkeypatch.setitem(sys.modules, "ghapi.all", type("M", (), {"GhApi": lambda token=None: dummy}))
    reload(gb)
    bridge = gb.GitHubBridge(service="svc")
    bridge.set_token("m", "tok", scopes=["repo"])
    with pytest.raises(ValueError):
        bridge.set_token("m", "tok", scopes=["write"])


def test_api_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict[str, str] = {}
    _mock_keyring(monkeypatch, store)
    dummy = DummyApi()
    monkeypatch.setitem(sys.modules, "ghapi.all", type("M", (), {"GhApi": lambda token=None: dummy}))
    reload(gb)
    bridge = gb.GitHubBridge(service="svc")
    bridge.set_token("default", "tok")
    bridge.search_code("foo")
    bridge.create_issue("o/r", "t", "b")
    bridge.create_pr("o/r", "t", "b", "h", "base")
    kinds = [c[0] for c in dummy.called]
    assert kinds == ["search", "issue", "pr"]
