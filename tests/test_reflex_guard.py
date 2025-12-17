from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from integration_memory import IntegrationMemory
from sentientos.daemons.reflex_guard import ReflexGuard


def _write_trials(path: Path, records: list[dict]) -> None:
    lines = [json.dumps(record) for record in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture()
def fixed_now() -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc)


@pytest.mark.no_legacy_skip
def test_recovered_reflex_not_suppressed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_now: datetime) -> None:
    ledger = tmp_path / "reflex_trials.jsonl"
    blacklist = tmp_path / "blacklist.json"
    digest = tmp_path / "digest.jsonl"
    config_path = tmp_path / "reflex_config.json"
    config_path.write_text(
        json.dumps(
            {
                "max_firings_per_window": 10,
                "failure_threshold": 5,
                "saturation_window_seconds": 300,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    entries = []
    for idx in range(3):
        entries.append(
            {
                "rule_id": "reflex.alpha",
                "status": "failure" if idx < 2 else "success",
                "timestamp": (fixed_now - timedelta(seconds=200 - 20 * idx)).isoformat(),
            }
        )
    _write_trials(ledger, entries)

    guard = ReflexGuard(
        ledger_path=ledger,
        blacklist_path=blacklist,
        config_path=config_path,
        digest_path=digest,
        now_fn=lambda: fixed_now,
    )
    result = guard.scan_and_suppress()

    assert result["scanned_rules"] == 1
    assert result["suppressed"] == []
    assert not blacklist.exists() or blacklist.read_text(encoding="utf-8").strip() == ""


@pytest.mark.no_legacy_skip
def test_persistently_failing_and_saturated_reflexes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_now: datetime) -> None:
    ledger = tmp_path / "reflex_trials.jsonl"
    blacklist = tmp_path / "blacklist.json"
    digest = tmp_path / "digest.jsonl"
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))

    config_path = tmp_path / "reflex_config.json"
    config_path.write_text(
        json.dumps(
            {
                "max_firings_per_window": 5,
                "failure_threshold": 5,
                "saturation_window_seconds": 300,
            }
        ),
        encoding="utf-8",
    )

    failing_entries = [
        {
            "rule_id": "reflex.beta",
            "status": "failure",
            "timestamp": (fixed_now - timedelta(seconds=30 * idx)).isoformat(),
        }
        for idx in range(6)
    ]
    saturated_entries = [
        {
            "rule_id": "reflex.gamma",
            "status": "success",
            "timestamp": (fixed_now - timedelta(seconds=10 * idx)).isoformat(),
        }
        for idx in range(7)
    ]
    _write_trials(ledger, failing_entries + saturated_entries)

    integration = IntegrationMemory(root=tmp_path / "integration")
    guard = ReflexGuard(
        ledger_path=ledger,
        blacklist_path=blacklist,
        config_path=config_path,
        digest_path=digest,
        integration_memory=integration,
        now_fn=lambda: fixed_now,
    )

    result = guard.scan_and_suppress()

    assert result["scanned_rules"] == 2
    suppressed = {entry["rule_id"]: entry for entry in result["suppressed"]}
    assert set(suppressed) == {"reflex.beta", "reflex.gamma"}
    assert suppressed["reflex.beta"]["failure_count"] >= 5
    assert suppressed["reflex.gamma"]["firing_count"] > 5

    persisted = json.loads(blacklist.read_text(encoding="utf-8"))
    assert "reflex.beta" in persisted and "reflex.gamma" in persisted

    digest_lines = [line for line in digest.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(digest_lines) == 1
    digest_entry = json.loads(digest_lines[0])
    assert {item["rule_id"] for item in digest_entry["suppressed"]} == {"reflex.beta", "reflex.gamma"}

    ledger_events = integration.load_events(limit=None)
    assert any(event.source == "ReflexGuard" for event in ledger_events)

