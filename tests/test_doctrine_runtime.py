"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import importlib
import os
import sys
import json
import hashlib
from pathlib import Path
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCTRINE_CONSENT_LOG", str(tmp_path / "consent.jsonl"))
    monkeypatch.setenv("DOCTRINE_STATUS_LOG", str(tmp_path / "status.jsonl"))
    monkeypatch.setenv("DOCTRINE_AMEND_LOG", str(tmp_path / "amend.jsonl"))
    monkeypatch.setenv("PUBLIC_RITUAL_LOG", str(tmp_path / "public.jsonl"))
    monkeypatch.setenv("DOCTRINE_SIGNATURE_LOG", str(tmp_path / "sig.jsonl"))
    monkeypatch.setenv("MASTER_CONFIG", str(tmp_path / "master.json"))
    import doctrine
    importlib.reload(doctrine)
    return doctrine


def create_master(tmp_path, text="hi"):
    file = tmp_path / "m.txt"
    file.write_text(text)
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    return file, digest


def test_verify_file_corruption(tmp_path, monkeypatch):
    doctrine = setup_env(tmp_path, monkeypatch)
    f, digest = create_master(tmp_path)
    os.chmod(f, 0o444)
    assert doctrine.verify_file(f, digest)
    os.chmod(f, 0o644)
    f.write_text("bad")
    assert not doctrine.verify_file(f, digest)


def test_consent_history_handles_corrupt(tmp_path, monkeypatch):
    doctrine = setup_env(tmp_path, monkeypatch)
    log = Path(os.environ["DOCTRINE_CONSENT_LOG"])
    log.write_text("bad{\n")
    assert doctrine.consent_history() == []


def test_capture_signature(tmp_path, monkeypatch):
    doctrine = setup_env(tmp_path, monkeypatch)
    doctrine.capture_signature("alice", "sig")
    data = Path(os.environ["DOCTRINE_SIGNATURE_LOG"]).read_text().splitlines()
    assert json.loads(data[0])["signature"] == "sig"


def test_enforce_runtime_raises(tmp_path, monkeypatch):
    doctrine = setup_env(tmp_path, monkeypatch)
    f, digest = create_master(tmp_path)
    cfg = Path(os.environ["MASTER_CONFIG"])
    cfg.write_text(json.dumps({str(f): digest}))
    os.chmod(f, 0o444)
    doctrine.enforce_runtime()  # should pass
    f.write_text("bad")
    with pytest.raises(SystemExit):
        doctrine.enforce_runtime()


def test_watch_flag_invokes_daemon(tmp_path, monkeypatch, capsys):
    doctrine = setup_env(tmp_path, monkeypatch)
    called = {}
    monkeypatch.setattr(doctrine, "watch_daemon", lambda: called.setdefault("w", True))
    monkeypatch.setattr(sys, "argv", ["doc", "--watch", "report"])
    doctrine.main()
    assert called.get("w")
