from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sentientos.diagnostics import DiagnosticError
from sentientos.embodiment.consent import ConsentLedger, OperatorRole
from sentientos.embodiment.contracts import SignalDirection, SignalType
from sentientos.embodiment.simulation import simulate_signal
from sentientos.introspection.spine import load_events


def _egress_payload() -> dict[str, object]:
    return {
        "action": "simulate",
        "target": "sandbox",
        "expected_effect": "none",
        "confidence": 0.42,
        "timestamp": "2025-01-01T00:00:00Z",
        "metadata": {"note": "test"},
        "frequency_hz": 0.1,
        "tags": ["test"],
    }


def _status_payload() -> dict[str, object]:
    return {
        "component": "sim",
        "status": "ok",
        "summary": "status report",
        "confidence": 0.75,
        "timestamp": "2025-01-01T00:00:00Z",
        "metadata": {"note": "test"},
        "frequency_hz": 0.1,
        "tags": ["test"],
    }


def test_missing_consent_refuses_simulated_egress(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    introspection_path = tmp_path / "introspection.jsonl"

    with pytest.raises(DiagnosticError) as exc:
        simulate_signal(
            SignalDirection.EGRESS,
            SignalType.SIMULATED_ACTUATION,
            _egress_payload(),
            context="cli",
            introspection_path=str(introspection_path),
        )

    assert exc.value.frame.error_code == "CONSENT_REQUIRED"
    events = load_events(str(introspection_path))
    assert any(
        event.phase == "consent_gate" and event.metadata.get("result") == "refused"
        for event in events
    )


def test_scope_enforcement_blocks_unapproved_signal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    ledger = ConsentLedger()
    ledger.grant_contract(
        operator_role=OperatorRole.OPERATOR,
        signal_types=(SignalType.STATUS_REPORT,),
        context="cli",
        duration_seconds=120,
    )

    simulate_signal(
        SignalDirection.EGRESS,
        SignalType.STATUS_REPORT,
        _status_payload(),
        context="cli",
        introspection_path=str(tmp_path / "introspection.jsonl"),
    )

    with pytest.raises(DiagnosticError):
        simulate_signal(
            SignalDirection.EGRESS,
            SignalType.SIMULATED_ACTUATION,
            _egress_payload(),
            context="cli",
            introspection_path=str(tmp_path / "introspection.jsonl"),
        )


def test_expired_consent_is_not_usable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    ledger = ConsentLedger()
    issued_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    ledger.grant_contract(
        operator_role=OperatorRole.OPERATOR,
        signal_types=(SignalType.SIMULATED_ACTUATION,),
        context="cli",
        duration_seconds=1,
        issued_at=issued_at,
    )

    with pytest.raises(DiagnosticError):
        simulate_signal(
            SignalDirection.EGRESS,
            SignalType.SIMULATED_ACTUATION,
            _egress_payload(),
            context="cli",
            introspection_path=str(tmp_path / "introspection.jsonl"),
        )

    records = ledger.list_records()
    assert records[0].status == "expired"


def test_revoked_consent_refuses_egress(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    ledger = ConsentLedger()
    contract = ledger.grant_contract(
        operator_role=OperatorRole.OPERATOR,
        signal_types=(SignalType.SIMULATED_ACTUATION,),
        context="cli",
        duration_seconds=120,
    )
    ledger.revoke_contract(contract.contract_id, reason="test")

    with pytest.raises(DiagnosticError):
        simulate_signal(
            SignalDirection.EGRESS,
            SignalType.SIMULATED_ACTUATION,
            _egress_payload(),
            context="cli",
            introspection_path=str(tmp_path / "introspection.jsonl"),
        )


def test_introspection_records_consent_gate(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    ledger = ConsentLedger()
    contract = ledger.grant_contract(
        operator_role=OperatorRole.OPERATOR,
        signal_types=(SignalType.SIMULATED_ACTUATION,),
        context="cli",
        duration_seconds=120,
    )
    introspection_path = tmp_path / "introspection.jsonl"

    result = simulate_signal(
        SignalDirection.EGRESS,
        SignalType.SIMULATED_ACTUATION,
        _egress_payload(),
        context="cli",
        introspection_path=str(introspection_path),
    )

    assert result.consent_contract_id == contract.contract_id
    events = load_events(str(introspection_path))
    assert any(
        event.phase == "consent_gate"
        and event.metadata.get("result") == "approved"
        and event.metadata.get("contract_id") == contract.contract_id
        for event in events
    )
