import importlib
import os
import sys
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import avatar_reflection as ar
from PIL import Image


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

    happy = tmp_path / "happy.png"
    Image.new("RGB", (2, 2), (0, 255, 0)).save(happy)
    sad = tmp_path / "sad.png"
    Image.new("RGB", (2, 2), (0, 0, 255)).save(sad)
    angry = tmp_path / "angry.png"
    Image.new("RGB", (2, 2), (255, 0, 0)).save(angry)

    assert ar.analyze_image(happy) == "happy"
    assert ar.analyze_image(sad) == "sad"
    assert ar.analyze_image(angry) == "angry"

