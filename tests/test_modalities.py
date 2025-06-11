import os
import sys
import json
from importlib import reload
import pytest
from pathlib import Path

import sentientos.admin_utils as admin_utils

import sentientos.epu as epu


def test_eeg_emulator(tmp_path, monkeypatch):
    eeg_log = tmp_path / "eeg.jsonl"
    feat_log = tmp_path / "feat.jsonl"
    monkeypatch.setenv("EEG_LOG", str(eeg_log))
    monkeypatch.setenv("EEG_FEATURE_LOG", str(feat_log))
    import sentientos.eeg_emulator as eeg_emulator
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: None)
    reload(eeg_emulator)
    eeg_emulator.run(duration=0.1, interval=0.05)
    assert eeg_log.exists() and feat_log.exists()
    assert eeg_log.read_text().strip() != ""
    assert feat_log.read_text().strip() != ""


def test_haptics_and_bio(tmp_path, monkeypatch):
    h_log = tmp_path / "h.jsonl"
    b_log = tmp_path / "b.jsonl"
    monkeypatch.setenv("HAPTIC_LOG", str(h_log))
    monkeypatch.setenv("BIO_LOG", str(b_log))
    import sentientos.haptics_bridge as haptics_bridge
    import sentientos.bio_bridge as bio_bridge
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: None)
    reload(haptics_bridge)
    reload(bio_bridge)
    haptics_bridge.HapticsBridge().read_event()
    bio_bridge.read_biosignals()
    assert h_log.exists() and b_log.exists()


def test_epu_modalities():
    e = epu.EmotionProcessingUnit()
    out = e.update(eeg={"Joy": 1.0}, haptics={"Anger": 0.5}, bio={"Joy": 0.2})
    assert isinstance(out, dict)


def test_relay_extra_endpoints(tmp_path, monkeypatch):
    from tests.test_relay import setup_app
    mood_log = tmp_path / "m.jsonl"
    mood_log.write_text(json.dumps({"timestamp": 0, "mood": {"Joy": 1}}) + "\n")
    monkeypatch.setenv("EPU_MOOD_LOG", str(mood_log))
    monkeypatch.setenv("RELAY_SECRET", "secret123")
    import sentientos.epu as epu
    epu.MOOD_LOG = mood_log
    client = setup_app(tmp_path, monkeypatch)
    resp = client.post("/mood")
    assert resp.status_code == 200
    assert resp.get_json().get("Joy") == 1

