from __future__ import annotations
import types
from pathlib import Path

import cathedral_launcher as cl


def run_case(tmp_path: Path, monkeypatch, gpg_ok: bool):
    monkeypatch.chdir(tmp_path)
    release = {
        "tag_name": "1.0",
        "assets": [
            {"name": "SentientOS.tar.gz", "browser_download_url": "a"},
            {"name": "SentientOS.tar.gz.asc", "browser_download_url": "b"},
        ],
    }

    class Resp:
        def __init__(self, data=b""):
            self.data = data
            self.status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return release

        @property
        def content(self):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

    def fake_get(url: str, *a, **k):
        if url.endswith("latest"):
            return Resp()
        return Resp(b"data")

    monkeypatch.setattr(cl.requests, "get", fake_get)
    monkeypatch.setattr(cl, "_download", lambda u, d: d.write_bytes(b"data"))
    monkeypatch.setattr(cl.shutil, "unpack_archive", lambda *a, **k: None)
    monkeypatch.setattr(cl.subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0 if gpg_ok else 1))
    prompts = iter([True, False])
    monkeypatch.setattr(cl.messagebox, "askyesno", lambda *a, **k: next(prompts))
    logs = []
    monkeypatch.setattr(cl, "log_json", lambda p, obj: logs.append(obj))
    cl.check_updates()
    return logs


def test_placeholder(tmp_path, monkeypatch):
    logs = run_case(tmp_path, monkeypatch, True)
    assert any(l["event"] == "update_installed" for l in logs)

    logs = run_case(tmp_path, monkeypatch, False)
    assert any(l["event"] == "update_verify_failed" for l in logs)
