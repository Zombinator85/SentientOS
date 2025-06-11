"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import asyncio
import os
import sys
from importlib import reload
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import telegram_bot as tb


class DummyMsg:
    def __init__(self) -> None:
        self.text = ""

    async def reply_text(self, text: str) -> None:
        self.text = text


class DummyUpdate:
    def __init__(self) -> None:
        self.message = DummyMsg()
        self.effective_chat = type("Chat", (), {"id": 1})()


class DummyContext:
    def __init__(self):
        self.args = []


def test_digest(tmp_path, monkeypatch):
    digest = tmp_path / "digest.txt"
    digest.write_text("hello")

    def fake_generate():
        return str(digest)

    monkeypatch.setattr(tb.rd, "generate_digest", fake_generate)
    reload(tb)
    upd = DummyUpdate()
    ctx = DummyContext()
    asyncio.run(tb.digest(upd, ctx))
    assert "hello" in upd.message.text
