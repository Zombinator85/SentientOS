from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentientos.cathedral import Amendment
from sentientos.cathedral.apply import AmendmentApplicator
from sentientos.runtime import bootstrap


@pytest.fixture()
def runtime_config(tmp_path: Path) -> dict[str, object]:
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


def _make_amendment(identifier: str, changes: dict[str, object]) -> Amendment:
    return Amendment(
        id=identifier,
        created_at=datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc),
        proposer="test",
        summary="Test amendment",
        changes=changes,
        reason="Routine configuration update.",
    )


def test_applicator_updates_runtime_config(runtime_config: dict[str, object]) -> None:
    applicator = AmendmentApplicator(runtime_config)
    amendment = _make_amendment(
        "cfg-1",
        {
            "config": {"runtime": {"watchdog_interval": 3}},
            "persona": {"tick_interval_seconds": 45},
            "world": {"enabled": False},
        },
    )
    result = applicator.apply(amendment)

    assert result.status == "applied"
    assert result.applied["config"]["runtime"]["watchdog_interval"]["value"] == 3
    assert result.applied["persona"]["tick_interval_seconds"]["value"] == 45
    config_path = Path(runtime_config["runtime"]["config_dir"]) / "runtime.json"  # type: ignore[index]
    stored = json.loads(config_path.read_text(encoding="utf-8"))
    assert stored["runtime"]["watchdog_interval"] == 3
    assert stored["persona"]["tick_interval_seconds"] == 45


def test_applicator_partial_when_skipping_entries(runtime_config: dict[str, object]) -> None:
    applicator = AmendmentApplicator(runtime_config)
    amendment = _make_amendment(
        "cfg-2",
        {
            "registry": {"demos": {"add": ["demo_new"], "remove": ["missing"]}},
        },
    )
    result = applicator.apply(amendment)

    assert result.status == "partial"
    assert "demo_new" in result.applied["registry"]["demos"]["added"]
    assert "registry.demos.missing" in result.skipped


def test_applicator_rejects_forbidden_domain(runtime_config: dict[str, object]) -> None:
    applicator = AmendmentApplicator(runtime_config)
    amendment = _make_amendment("cfg-3", {"source_code": {"update": "print('hi')"}})
    result = applicator.apply(amendment)

    assert result.status == "error"
    assert "source_code" in result.errors
    ledger_path = Path(runtime_config["cathedral"]["ledger_path"])  # type: ignore[index]
    assert not ledger_path.exists()
