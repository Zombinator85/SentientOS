from __future__ import annotations

from pathlib import Path

import pytest

from sentientos.codex_healer import Anomaly, RecoveryLedger, RepairAction, ReviewBoard
from sentientos.first_boot import FirstBootWizard, WizardDecisions

pytestmark = pytest.mark.no_legacy_skip


def test_recovery_ledger_ignores_malformed_nested_payloads() -> None:
    entry = RecoveryLedger().log(
        "observed",
        anomaly=Anomaly(kind="test", subject="subject"),
        details={"proof_report": object(), "kernel_admission": object()},
    )

    assert "proof_summary" not in entry
    assert "canonical_admission" not in entry


def test_review_board_quarantines_malformed_trust_value() -> None:
    action = RepairAction(
        kind="repair",
        subject="subject",
        description="test",
        execute=lambda: True,
        metadata={"trust": "not-a-number"},
    )

    decision = ReviewBoard().evaluate(action, Anomaly(kind="test", subject="subject"))

    assert decision.approved is False
    assert decision.quarantined is True
    assert decision.reason == "invalid_trust"


def test_first_boot_treats_noniterable_device_data_as_empty(tmp_path: Path) -> None:
    class DriverManagerStub:
        def refresh(self) -> dict[str, object]:
            return {"devices": object()}

    wizard = FirstBootWizard(
        driver_manager=DriverManagerStub(),  # type: ignore[arg-type]
        ledger_path=tmp_path / "ledger.jsonl",
        ledger_writer=lambda _path, _entry: None,
    )

    assert wizard._handle_driver_step(WizardDecisions()) == []
