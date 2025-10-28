from __future__ import annotations

from datetime import datetime, timezone

import json
from pathlib import Path

from sentientos.daemons.hungry_eyes import (
    HungryEyesDatasetBuilder,
    HungryEyesSentinel,
    extract_features,
)
from sentientos.daemons.integrity_daemon import IntegrityDaemon


def _ledger_event(
    *,
    status: str,
    violations: list[dict[str, object]],
    probe_report: dict[str, object] | None = None,
) -> dict[str, object]:
    proof_report = {
        "valid": not violations,
        "violations": violations,
        "trace": [{"invariant": item.get("invariant", "structural_integrity")} for item in violations]
        or [{"invariant": "structural_integrity"} for _ in range(4)],
    }
    if not proof_report["trace"]:
        proof_report["trace"] = [{"invariant": "structural_integrity"}]
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "summary": "Maintain covenant integrity.",
        "proof_report": proof_report,
        "probe_report": probe_report or {},
    }
    return event


def test_dataset_builder_labels_and_features(tmp_path: Path) -> None:
    valid_event = _ledger_event(status="VALID", violations=[], probe_report={})
    invalid_event = _ledger_event(
        status="QUARANTINED",
        violations=[
            {"invariant": "forbidden_status", "severity": "high"},
            {"invariant": "structural_integrity", "severity": "critical"},
        ],
        probe_report={"removed_keys": ["ledger"], "ledger_removed": True},
    )

    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(
        "\n".join(json.dumps(event) for event in (valid_event, invalid_event)),
        encoding="utf-8",
    )

    builder = HungryEyesDatasetBuilder()
    builder.load_jsonl(ledger_path)
    examples = builder.build()
    assert [example.label for example in examples] == [0, 1]

    features_valid = examples[0].features
    features_invalid = examples[1].features
    assert features_valid["proof_valid"] == 1.0
    assert features_invalid["forbidden_status_flag"] == 1.0
    assert features_invalid["probe_ledger_removed"] == 1.0


def test_hungry_eyes_sentinel_trains_and_scores() -> None:
    valid_event = _ledger_event(status="VALID", violations=[], probe_report={})
    invalid_event = _ledger_event(
        status="QUARANTINED",
        violations=[
            {"invariant": "audit_continuity", "severity": "high"},
            {"invariant": "structural_integrity", "severity": "critical"},
        ],
        probe_report={"ledger_removed": True, "recursion_break": True},
    )

    builder = HungryEyesDatasetBuilder()
    builder.add_many([valid_event, invalid_event])
    sentinel = HungryEyesSentinel()
    sentinel.fit(builder.build())

    assert sentinel.fitted

    risk_valid = sentinel.assess(valid_event)["risk"]
    risk_invalid = sentinel.assess(invalid_event)["risk"]
    assert 0 <= risk_valid < risk_invalid <= 1


def test_integrity_daemon_dual_control_integration() -> None:
    valid_event = _ledger_event(status="VALID", violations=[], probe_report={})
    invalid_event = _ledger_event(
        status="QUARANTINED",
        violations=[
            {"invariant": "forbidden_status", "severity": "high"},
            {"invariant": "structural_integrity", "severity": "critical"},
        ],
        probe_report={"removed_keys": ["ledger"], "ledger_removed": True},
    )

    builder = HungryEyesDatasetBuilder()
    builder.add_many([valid_event, invalid_event])
    sentinel = HungryEyesSentinel(threshold=0.6)
    sentinel.fit(builder.build())

    daemon = IntegrityDaemon(hungry_eyes=sentinel, hungry_threshold=0.6)
    try:
        daemon._integrate_hungry_eyes(valid_event)
        dual_valid = valid_event["proof_report"]["dual_control"]
        assert dual_valid["auto_commit"] is True

        daemon._integrate_hungry_eyes(invalid_event)
        dual_invalid = invalid_event["proof_report"]["dual_control"]
        assert dual_invalid["auto_commit"] is False
    finally:
        daemon.stop()


def test_feature_extraction_handles_missing_sections() -> None:
    event = {
        "proof_report": {"valid": True},
        "probe_report": {"summary_blank": True},
    }
    features = extract_features(event)
    assert features["violation_count"] == 0.0
    assert features["probe_summary_blank"] == 1.0
