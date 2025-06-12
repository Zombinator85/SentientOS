"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import asyncio
import os
import sys
from importlib import reload
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import telegram_bot as tb


class DummyMsg:
    def __init__(self) -> None:
        self.document = None
        self.text = ""

    async def reply_text(self, text: str) -> None:
        self.text = text

    async def reply_document(self, f, filename=None) -> None:
        self.document = f.read()


class DummyUpdate:
    def __init__(self) -> None:
        self.message = DummyMsg()
        self.effective_chat = type("Chat", (), {"id": 1})()


class DummyContext:
    def __init__(self):
        self.args = []


def test_export_ocr(tmp_path, monkeypatch):
    log = tmp_path / "ocr.jsonl"
    log.write_text("{}\n")
    monkeypatch.setenv("OCR_RELAY_LOG", str(log))
    reload(tb)

    def fake_export(path=log):
        out = tmp_path / "out.csv"
        out.write_text("ok")
        return str(out)

    monkeypatch.setattr(tb.oe, "export_last_day_csv", fake_export)
    upd = DummyUpdate()
    ctx = DummyContext()
    asyncio.run(tb.export_ocr(upd, ctx))
    assert upd.message.document == b"ok"
