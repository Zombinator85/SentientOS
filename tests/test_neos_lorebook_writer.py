import importlib
import json
import sys
import os
from pathlib import Path


import sentientos.neos_lorebook_writer as nlw


def setup_logs(tmp_path):
    origin = tmp_path / "origin.jsonl"
    ceremony = tmp_path / "ceremony.jsonl"
    teach = tmp_path / "teach.jsonl"
    council = tmp_path / "council.jsonl"
    for p in (origin, ceremony, teach, council):
        p.write_text("{}\n")
    return origin, ceremony, teach, council


def test_compile_and_gallery(tmp_path, monkeypatch, capsys):
    origin, ceremony, teach, council = setup_logs(tmp_path)
    out = tmp_path / "out.json"
    log = tmp_path / "log.jsonl"

    monkeypatch.setenv("NEOS_ORIGIN_LOG", str(origin))
    monkeypatch.setenv("AVATAR_CEREMONY_LOG", str(ceremony))
    monkeypatch.setenv("NEOS_TEACH_CONTENT_LOG", str(teach))
    monkeypatch.setenv("NEOS_PERMISSION_COUNCIL_LOG", str(council))
    monkeypatch.setenv("NEOS_LOREBOOK_LOG", str(log))

    importlib.reload(nlw)
    monkeypatch.setattr(nlw, "require_admin_banner", lambda: None)

    # compile lorebook
    monkeypatch.setattr(sys, "argv", ["nlw", "compile", str(out)])
    nlw.main()
    capsys.readouterr()  # clear path output
    assert out.exists()
    data = json.loads(out.read_text())
    assert len(data) == 4
    assert log.exists()

    # gallery output
    monkeypatch.setattr(sys, "argv", ["nlw", "gallery"])
    nlw.main()
    gallery = json.loads(capsys.readouterr().out)
    assert len(gallery) == 4
