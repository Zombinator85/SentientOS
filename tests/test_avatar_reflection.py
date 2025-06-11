import importlib
from pathlib import Path
import os
import sys



def test_reflection_log(tmp_path, monkeypatch):
    log = tmp_path / "reflection.jsonl"
    monkeypatch.setenv("AVATAR_REFLECTION_LOG", str(log))
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    import sentientos.avatar_reflection as ar
    importlib.reload(ar)
    img = tmp_path / "img.png"
    img.write_text("data")
    ar.log_reflection(str(img), "happy")
    assert log.exists()
    assert len(log.read_text().splitlines()) == 1


def test_analyze_image(tmp_path, monkeypatch):
    log = tmp_path / "reflection.jsonl"
    monkeypatch.setenv("AVATAR_REFLECTION_LOG", str(log))
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    import sentientos.avatar_reflection as ar
    importlib.reload(ar)

    img = tmp_path / "smile.png"
    img.write_text("data")

    mood = ar.analyze_image(img)
    assert mood == "happy"


def test_analyze_image_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("AVATAR_REFLECTION_LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    import sentientos.avatar_reflection as ar
    importlib.reload(ar)

    def boom(path: str):
        raise RuntimeError("fail")

    monkeypatch.setattr(ar.eu, "detect_image", boom)
    img = tmp_path / "whatever.png"
    img.write_text("data")
    mood = ar.analyze_image(img)
    assert mood == "serene"
