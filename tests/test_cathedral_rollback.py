from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sentientos.cathedral import Amendment
from sentientos.cathedral.apply import AmendmentApplicator
from sentientos.runtime import bootstrap


def _prepare_config(tmp_path: Path) -> dict[str, object]:
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


def test_rollback_snapshot_contains_original_and_applied(tmp_path: Path) -> None:
    config = _prepare_config(tmp_path)
    applicator = AmendmentApplicator(config)
    amendment = Amendment(
        id="rollback-1",
        created_at=datetime(2024, 7, 1, 9, 0, tzinfo=timezone.utc),
        proposer="rollback-test",
        summary="Persona cadence",
        changes={"persona": {"tick_interval_seconds": 42}},
        reason="Tuning persona loop.",
    )

    result = applicator.apply(amendment)
    assert result.status == "applied"

    rollback_dir = Path(config["cathedral"]["rollback_dir"])  # type: ignore[index]
    snapshot_path = rollback_dir / "rollback-1.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert snapshot["original"]["persona"]["tick_interval_seconds"] == 60
    applied_block = snapshot["applied"]["persona"]["tick_interval_seconds"]
    assert applied_block["previous"] == 60
    assert applied_block["value"] == 42
