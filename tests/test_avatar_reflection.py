import importlib
from pathlib import Path

import avatar_reflection as ar


def test_reflection_log(tmp_path, monkeypatch):
    log = tmp_path / "reflection.jsonl"
    monkeypatch.setenv("AVATAR_REFLECTION_LOG", str(log))
    importlib.reload(ar)
    img = tmp_path / "img.png"
    img.write_text("data")
    ar.log_reflection(str(img), "happy")
    assert log.exists()
    assert len(log.read_text().splitlines()) == 1


def test_analyze_image(tmp_path, monkeypatch):
    log = tmp_path / "reflection.jsonl"
    monkeypatch.setenv("AVATAR_REFLECTION_LOG", str(log))
    importlib.reload(ar)

    img = tmp_path / "smile.png"
    img.write_text("data")

    mood = ar.analyze_image(img)
    assert mood == "happy"

