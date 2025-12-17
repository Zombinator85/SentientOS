from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from integration_memory import IntegrationMemory
from sentientos.daemons.narrative_reaper import DEFAULT_POLICIES, NarrativeReaper


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


@pytest.mark.no_legacy_skip
def test_expired_context_archived(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    ttl_path = tmp_path / "config" / "narrative_ttl.json"
    _write_json(
        ttl_path,
        {
            "persona_contexts": 10,
            "mood_fragments": 20,
            "temporary_identities": 30,
            "session_scope": 5,
        },
    )

    context_path = tmp_path / "glow" / "contexts" / "alpha.json"
    _write_json(
        context_path,
        {"id": "alpha", "created_at": (now - timedelta(hours=2)).isoformat(), "epitaph": "faded persona"},
    )

    integration = IntegrationMemory(root=tmp_path / "integration")
    reaper = NarrativeReaper(
        root=tmp_path,
        integration_memory=integration,
        ttl_config_path=ttl_path,
        clock=lambda: now,
    )

    result = reaper.run_once()

    assert result.expired == 1
    assert result.active == 0

    archive_path = tmp_path / "glow" / "archive" / "expired" / "contexts" / "alpha.json"
    assert archive_path.exists()
    assert not context_path.exists()

    summary_log = tmp_path / "glow" / "expirations" / "expired_fragments.jsonl"
    entries = [json.loads(line) for line in summary_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert entries and entries[0]["id"] == "alpha"
    assert entries[0]["reason"] == "persona_contexts"
    assert entries[0]["archived_to"].endswith("contexts/alpha.json")

    audit_log = tmp_path / "logs" / "narrative_expiry_audit.jsonl"
    assert audit_log.exists()


@pytest.mark.no_legacy_skip
def test_near_expiry_warns_integration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    ttl_path = tmp_path / "config" / "narrative_ttl.json"
    _write_json(ttl_path, DEFAULT_POLICIES)

    created_at = now - (timedelta(seconds=DEFAULT_POLICIES["mood_fragments"]) - timedelta(minutes=30))
    fragment_path = tmp_path / "glow" / "fragments" / "beta.json"
    _write_json(fragment_path, {"id": "beta", "created_at": created_at.isoformat(), "fragment_type": "mood_fragments"})

    integration = IntegrationMemory(root=tmp_path / "integration")
    reaper = NarrativeReaper(
        root=tmp_path,
        integration_memory=integration,
        ttl_config_path=ttl_path,
        clock=lambda: now,
    )

    result = reaper.run_once()

    assert result.expired == 0
    assert result.active == 1

    events = integration.load_events(limit=None)
    assert events, "integration ledger should have received a ttl warning"
    last = events[-1]
    assert last.impact == "ttl_warning"
    assert last.payload.get("id") == "beta"
    assert last.payload.get("ttl_key") == "mood_fragments"



@pytest.mark.no_legacy_skip
def test_ledger_expiration_and_retention(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    ttl_path = tmp_path / "config" / "narrative_ttl.json"
    _write_json(ttl_path, {**DEFAULT_POLICIES, "temporary_identities": 5})

    ledger_path = tmp_path / "integration" / "ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    expired_entry = {"id": "old", "created_at": (now - timedelta(seconds=10)).isoformat(), "ttl_key": "temporary_identities", "epitaph": "identity faded"}
    active_entry = {"id": "fresh", "created_at": (now - timedelta(seconds=1)).isoformat(), "ttl_key": "temporary_identities"}
    ledger_path.write_text(json.dumps(expired_entry) + "\n" + json.dumps(active_entry) + "\n", encoding="utf-8")

    integration = IntegrationMemory(root=tmp_path / "integration")
    reaper = NarrativeReaper(
        root=tmp_path,
        integration_memory=integration,
        ttl_config_path=ttl_path,
        clock=lambda: now,
    )

    result = reaper.run_once()

    assert result.expired == 1
    assert result.active == 1
    assert "identity faded" in result.epitaphs

    remaining = [line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(remaining) == 1
    assert json.loads(remaining[0])["id"] == "fresh"

    archive_path = tmp_path / "glow" / "archive" / "expired" / "ledger" / "old.json"
    assert archive_path.exists()
    assert json.loads(archive_path.read_text(encoding="utf-8"))["id"] == "old"

    summary_log = tmp_path / "glow" / "expirations" / "expired_fragments.jsonl"
    entries = [json.loads(line) for line in summary_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    reasons = {entry["reason"] for entry in entries}
    assert "temporary_identities" in reasons
