from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sentientos.cathedral import Amendment, amendment_digest
from sentientos.cathedral.apply import AmendmentApplicator
from sentientos.runtime import bootstrap


def _make_config(tmp_path: Path) -> dict[str, object]:
    base_dir = tmp_path / "SentientOS"
    config = bootstrap.build_default_config(base_dir)
    runtime_section = config["runtime"]  # type: ignore[index]
    runtime_section["root"] = str(base_dir)
    runtime_section["config_dir"] = str(base_dir / "sentientos_data" / "config")
    cathedral_section = config.setdefault("cathedral", {})  # type: ignore[assignment]
    cathedral_section["ledger_path"] = str(base_dir / "cathedral" / "ledger.jsonl")
    cathedral_section["rollback_dir"] = str(base_dir / "cathedral" / "rollback")
    config_dir = Path(runtime_section["config_dir"])
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "runtime.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def _amendment(identifier: str, value: int) -> Amendment:
    return Amendment(
        id=identifier,
        created_at=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
        proposer="ledger-test",
        summary="Adjust watchdog",
        changes={"config": {"runtime": {"watchdog_interval": value}}},
        reason="Synchronise watchdog interval",
    )


def test_ledger_appends_entries(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    applicator = AmendmentApplicator(config)

    first = _amendment("ledger-1", 5)
    second = _amendment("ledger-2", 7)

    applicator.apply(first)
    applicator.apply(second)

    ledger_path = Path(config["cathedral"]["ledger_path"])  # type: ignore[index]
    lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    first_entry = json.loads(lines[0])
    second_entry = json.loads(lines[1])

    assert first_entry["amendment_id"] == "ledger-1"
    assert second_entry["amendment_id"] == "ledger-2"
    assert first_entry["digest"] == amendment_digest(first)
    assert second_entry["digest"] == amendment_digest(second)
    assert json.dumps(first_entry, sort_keys=True, separators=(",", ":")) == lines[0]
    assert json.dumps(second_entry, sort_keys=True, separators=(",", ":")) == lines[1]
