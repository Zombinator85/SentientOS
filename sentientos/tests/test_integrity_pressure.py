from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sentientos.forge_merge_train import ForgeMergeTrain
from sentientos.integrity_pressure import apply_escalation, compute_integrity_pressure


def _write_incidents(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(body, encoding="utf-8")


def test_compute_pressure_from_synthetic_incidents(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _write_incidents(
        tmp_path / "pulse/integrity_incidents.jsonl",
        [
            {
                "created_at": "2026-01-01T00:00:00Z",
                "enforcement_mode": "warn",
                "triggers": ["receipt_chain_broken"],
                "quarantine_activated": False,
            },
            {
                "created_at": "2026-01-01T00:30:00Z",
                "enforcement_mode": "enforce",
                "triggers": ["audit_chain_broken", "receipt_chain_broken"],
                "quarantine_activated": True,
            },
            {
                "created_at": "2025-12-31T00:30:00Z",
                "enforcement_mode": "enforce",
                "triggers": ["old"],
                "quarantine_activated": True,
            },
        ],
    )
    monkeypatch.setenv("SENTIENTOS_PRESSURE_WARN_THRESHOLD", "2")
    monkeypatch.setenv("SENTIENTOS_PRESSURE_ENFORCE_THRESHOLD", "4")
    monkeypatch.setenv("SENTIENTOS_PRESSURE_CRITICAL_THRESHOLD", "7")

    snapshot = compute_integrity_pressure(tmp_path, now=datetime.fromisoformat("2026-01-01T01:00:00+00:00"))

    assert snapshot.metrics.incidents_last_1h == 2
    assert snapshot.metrics.incidents_last_24h == 2
    assert snapshot.metrics.enforced_failures_last_24h == 1
    assert snapshot.metrics.unique_trigger_types_last_24h == 2
    assert snapshot.metrics.quarantine_activations_last_24h == 1
    assert snapshot.level == 2


def test_escalation_and_disable_flag(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    enforce, warn = apply_escalation(2, gate_name="receipt_chain", base_enforce=False, base_warn=False, high_severity=True)
    assert enforce is True
    assert warn is True

    monkeypatch.setenv("SENTIENTOS_PRESSURE_DISABLE_ESCALATION", "1")
    enforce_off, warn_off = apply_escalation(3, gate_name="receipt_chain", base_enforce=False, base_warn=False, high_severity=True)
    assert enforce_off is False
    assert warn_off is False


def test_critical_pressure_forces_quarantine_activation(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_QUARANTINE_AUTO", "0")
    train = ForgeMergeTrain(repo_root=tmp_path)
    train._record_integrity_incident(  # noqa: SLF001
        triggers=["receipt_chain_broken"],
        enforcement_mode="warn",
        severity="critical",
        context={"test": True},
        evidence_paths=["glow/forge/receipts/receipts_index.jsonl"],
        pressure_level=3,
    )

    quarantine = json.loads((tmp_path / "glow/forge/quarantine.json").read_text(encoding="utf-8"))
    assert quarantine["active"] is True
