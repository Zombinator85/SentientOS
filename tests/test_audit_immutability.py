"""Privilege checks for immutable audit flows."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_covenant_alignment

require_admin_banner()
require_covenant_alignment()

import json
import threading
import time
from pathlib import Path

import pytest

from scripts import audit_immutability_verifier as aiv
from sentientos import immutability


def _make_manifest(path: Path, target: Path) -> None:
    immutability.reset_key_cache()
    immutability.update_manifest([target], manifest_path=path)


def test_emotion_pump_verified_file(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("hello", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    _make_manifest(manifest, target)
    events: list[dict] = []
    outcome = aiv.verify_once(manifest_path=manifest, logger=events.append)
    status = [e for e in events if e["event"] == "immutability_check"][0]["status"]
    assert status == "verified"
    assert outcome.status == "passed"


def test_emotion_pump_tampered_file(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("hello", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    _make_manifest(manifest, target)
    target.write_text("bye", encoding="utf-8")
    events: list[dict] = []
    outcome = aiv.verify_once(manifest_path=manifest, logger=events.append)
    statuses = [e for e in events if e["event"] == "immutability_check"]
    assert statuses[0]["status"] == "tampered"
    assert any(e["event"] == "tamper_detected" for e in events)
    assert outcome.status == "failed"


def test_emotion_pump_manifest_update_requires_confirm(tmp_path: Path, monkeypatch) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("data", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    with pytest.raises(PermissionError):
        aiv.update_manifest([file_path], manifest)
    monkeypatch.setenv("LUMOS_VEIL_CONFIRM", "1")
    immutability.reset_key_cache()
    aiv.update_manifest([file_path], manifest)
    data = json.loads(manifest.read_text())
    assert str(file_path) in data["files"]
    assert data.get("signature")
    assert immutability.verify_manifest_signature(data)


def test_emotion_pump_run_loop(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("hello", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    _make_manifest(manifest, target)
    events: list[dict] = []
    stop = threading.Event()
    t = threading.Thread(
        target=aiv.run_loop,
        args=(stop, events.append),
        kwargs={"interval": 0.1, "manifest_path": manifest},
        daemon=True,
    )
    t.start()
    time.sleep(0.25)
    stop.set()
    t.join()
    checks = [e for e in events if e["event"] == "immutability_check"]
    assert len(checks) >= 2


def test_emotion_pump_cli_invocation(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "file.txt"
    target.write_text("hello", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    _make_manifest(manifest, target)
    events: list[dict] = []
    import scripts.run_audit as run_audit

    monkeypatch.setattr(
        run_audit,
        "verify_once",
        lambda: aiv.verify_once(manifest_path=manifest, logger=events.append),
    )
    result = run_audit.main([])
    assert result == 0
    assert any(e["event"] == "immutability_check" for e in events)


def test_emotion_pump_fails_without_manifest_by_default(tmp_path: Path) -> None:
    missing_manifest = tmp_path / "missing.json"
    events: list[dict] = []
    outcome = aiv.verify_once(manifest_path=missing_manifest, logger=events.append)
    assert outcome.status == "failed"
    assert outcome.reason == "manifest_missing"
    statuses = [e for e in events if e["event"] == "immutability_check"]
    assert statuses and statuses[0]["status"] == "failed"


def test_emotion_pump_allows_missing_manifest_in_degraded_mode(tmp_path: Path) -> None:
    missing_manifest = tmp_path / "missing.json"
    events: list[dict] = []
    outcome = aiv.verify_once(
        manifest_path=missing_manifest,
        allow_missing_manifest=True,
        logger=events.append,
    )
    assert outcome.status == "skipped"
    assert outcome.reason == "manifest_missing_allowed"
    statuses = [e for e in events if e["event"] == "immutability_check"]
    assert statuses and statuses[0]["status"] == "skipped"
