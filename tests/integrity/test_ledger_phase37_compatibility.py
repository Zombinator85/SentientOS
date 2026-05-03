from __future__ import annotations

import importlib
import json


def test_presence_api_recent_privilege_attempts_compatible(tmp_path, monkeypatch) -> None:
    ledger_path = tmp_path / "presence.jsonl"
    ledger_path.write_text(
        '\n'.join([
            '{"event":"other","user":"a"}',
            '{"event":"admin_privilege_check","user":"u1","status":"ok"}',
            '{"event":"admin_privilege_check","user":"u2","status":"denied"}',
        ]) + '\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("USER_PRESENCE_LOG", str(ledger_path))
    module = importlib.import_module("sentientos.presence_api")

    recent = module.recent_privilege_attempts(limit=1)
    assert len(recent) == 1
    assert recent[0]["user"] == "u2"
    assert recent[0]["event"] == "admin_privilege_check"


def test_presence_api_append_presence_event_delegates_to_canonical_log(tmp_path, monkeypatch) -> None:
    ledger_path = tmp_path / "presence.jsonl"
    canonical_presence_log = tmp_path / "presence_log.jsonl"
    monkeypatch.setenv("USER_PRESENCE_LOG", str(ledger_path))
    monkeypatch.setenv("PRESENCE_LOG", str(canonical_presence_log))

    module = importlib.import_module("sentientos.presence_api")
    module.append_presence_event("consent_wizard", "feedback", "alice")

    entries = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line]
    assert entries
    assert entries[-1]["user"] == "consent_wizard"
    assert entries[-1]["event"] == "feedback"
    assert entries[-1]["note"] == "alice"
