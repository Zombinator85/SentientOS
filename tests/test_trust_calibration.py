from __future__ import annotations

from pathlib import Path

import pytest

from sentientos.daemons.witness_daemon import WitnessDaemon
from tools.simulate_spoof_events import simulate_spoof_events
from witness.witness_rules import WitnessRules

pytestmark = pytest.mark.no_legacy_skip


def test_spoof_simulation_reports_precision_and_recall(tmp_path: Path) -> None:
    report_path = tmp_path / "witness_calibration.jsonl"
    witness = WitnessDaemon(
        base_dir=tmp_path / "perception",
        audit_log=tmp_path / "witness_log.jsonl",
        rules=WitnessRules(),
    )
    report = simulate_spoof_events(batch_size=5, output_path=report_path, witness_daemon=witness)

    assert report["precision"] >= 0.6
    assert report["recall"] >= 0.6
    saved = report_path.read_text(encoding="utf-8").strip().splitlines()
    assert saved and "precision" in saved[0]
