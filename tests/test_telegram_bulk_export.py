import asyncio
import os
import sys
from importlib import reload
from pathlib import Path
import zipfile


import sentientos.telegram_bot as tb


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
    def __init__(self, args):
        self.args = args


def test_bulk_export(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    csv1 = log_dir / "ocr_export_a.csv"
    csv1.write_text("a")
    monkeypatch.setattr(tb.oe, "OCR_LOG", log_dir / "ocr.jsonl")
    reload(tb)
    upd = DummyUpdate()
    ctx = DummyContext(["1"])
    asyncio.run(tb.bulk_export(upd, ctx))
    assert upd.message.document is not None
    with open(log_dir / "bulk_export.zip", "rb") as f:
        with zipfile.ZipFile(f) as z:
            assert "ocr_export_a.csv" in z.namelist()
