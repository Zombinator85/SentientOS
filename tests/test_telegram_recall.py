import asyncio
import os
import sys

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


def test_recall(monkeypatch):
    called = []

    def fake_search(tags, limit=3):
        called.append(tags)
        return [{"text": "one"}, {"text": "two"}]

    monkeypatch.setattr(tb.mm, "search_by_tags", fake_search)
    upd = DummyUpdate()
    ctx = DummyContext(["demo"])
    asyncio.run(tb.recall(upd, ctx))
    assert called and called[0] == ["demo"]
    assert "one" in upd.message.text

