from __future__ import annotations

import importlib


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
