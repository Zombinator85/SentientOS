import importlib
import json
import sys
from pathlib import Path

import avatar_artifact_gallery as aag


def test_gallery_filter(tmp_path, monkeypatch, capsys):
    dream = tmp_path / "dream.jsonl"
    gift = tmp_path / "gift.jsonl"
    artifact = tmp_path / "artifact.jsonl"
    gallery = tmp_path / "gallery.jsonl"

    dream.write_text(json.dumps({"creator": "ava", "seed": "sun"}) + "\n")
    gift.write_text(json.dumps({"avatar": "ava", "description": "poem"}) + "\n")
    artifact.write_text(json.dumps({"creator": "bob", "kind": "icon"}) + "\n")

    monkeypatch.setenv("AVATAR_DREAM_LOG", str(dream))
    monkeypatch.setenv("AVATAR_GIFT_LOG", str(gift))
    monkeypatch.setenv("AVATAR_ARTIFACT_LOG", str(artifact))
    monkeypatch.setenv("ARTIFACT_GALLERY_LOG", str(gallery))

    importlib.reload(aag)

    monkeypatch.setattr(sys, "argv", ["gallery", "--creator", "ava"])
    aag.main()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert len(data) == 2
    assert gallery.exists()
