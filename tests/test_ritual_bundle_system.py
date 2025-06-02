import importlib
import json
from pathlib import Path

import ritual_bundle_system as rbs


def test_create_and_verify(tmp_path, monkeypatch):
    monkeypatch.setenv("RITUAL_BUNDLE_DIR", str(tmp_path))
    monkeypatch.setenv("RITUAL_BUNDLE_LOG", str(tmp_path / "log.jsonl"))
    importlib.reload(rbs)

    asset = tmp_path / "a.txt"
    asset.write_text("hello", encoding="utf-8")

    bundle = rbs.create_bundle("demo", [str(asset)], "print('hi')", ["bless"])
    assert (tmp_path / "demo.json").exists()
    assert bundle["name"] == "demo"

    result = rbs.verify_bundle(str(tmp_path / "demo.json"))
    assert result["valid"]

    history = rbs.history()
    assert len(history) >= 2
