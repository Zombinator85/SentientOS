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
    def __init__(self, args):
        self.args = args


def test_search_reflect(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "2025-01-01.log").write_text("hello keyword world\n")
    monkeypatch.setenv("REFLECTION_LOG_DIR", str(log_dir))
    reload(tb)
    reload(tb.rlc)
    upd = DummyUpdate()
    ctx = DummyContext(["keyword"])
    asyncio.run(tb.search_reflect(upd, ctx))
    assert "keyword" in upd.message.text
