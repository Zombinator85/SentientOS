from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.runtime_supervisor import (
    RuntimeServiceRecord,
    build_runtime_supervisor_readiness_report,
    build_runtime_supervisor_snapshot,
    runtime_supervisor_readiness_digest,
    runtime_supervisor_snapshot_digest,
    summarize_runtime_supervisor_readiness_report,
    summarize_runtime_supervisor_snapshot,
    validate_runtime_service_record,
    validate_runtime_supervisor_readiness_report,
    validate_runtime_supervisor_snapshot,
)

pytestmark = pytest.mark.no_legacy_skip


def _record(service_id: str = "svc", status: str = "service_status_nominal") -> RuntimeServiceRecord:
    return RuntimeServiceRecord(service_id, service_id, "daemon", status, "desired_nominal", ("healthy",), (), ())


def test_clean_supplied_service_records_produce_snapshot_and_readiness() -> None:
    snapshot = build_runtime_supervisor_snapshot(service_records=(_record(),), snapshot_id="snap")
    report = build_runtime_supervisor_readiness_report(snapshot)
    assert report.supervisor_status == "runtime_supervisor_readiness_ready_for_review"
    assert report.restart_authorized is False
    assert report.kill_authorized is False
    assert validate_runtime_supervisor_snapshot(snapshot).ok
    assert validate_runtime_supervisor_readiness_report(report).ok


def test_degraded_service_produces_conditions_not_restart() -> None:
    snapshot = build_runtime_supervisor_snapshot(service_records=(_record("svc-deg", "service_status_degraded"),))
    report = build_runtime_supervisor_readiness_report(snapshot)
    assert report.supervisor_status == "runtime_supervisor_readiness_ready_with_conditions"
    assert report.degraded_service_ids == ("svc-deg",)
    assert report.restart_authorized is False


def test_unavailable_and_unknown_services_warn_or_block() -> None:
    unknown = build_runtime_supervisor_readiness_report(build_runtime_supervisor_snapshot(service_records=(_record("svc-u", "service_status_unknown"),)))
    unavailable = build_runtime_supervisor_readiness_report(build_runtime_supervisor_snapshot(service_records=(_record("svc-x", "service_status_unavailable"),)))
    assert unknown.supervisor_status == "runtime_supervisor_readiness_ready_with_conditions"
    assert any("unknown" in code for code in unknown.warning_codes)
    assert unavailable.supervisor_status == "runtime_supervisor_readiness_blocked"


def test_service_record_claiming_restart_or_kill_authorization_is_contradicted() -> None:
    restart = replace(_record(), restart_authorized=True)
    kill = replace(_record("kill"), kill_authorized=True)
    assert not validate_runtime_service_record(restart).ok
    assert not validate_runtime_service_record(kill).ok
    report = build_runtime_supervisor_readiness_report(build_runtime_supervisor_snapshot(service_records=(restart, kill)))
    assert report.supervisor_status == "runtime_supervisor_readiness_contradicted"


def test_snapshot_and_report_claiming_mutation_are_rejected() -> None:
    snapshot = replace(build_runtime_supervisor_snapshot(service_records=(_record(),)), host_mutation_performed=True)
    assert not validate_runtime_supervisor_snapshot(snapshot).ok
    report = replace(build_runtime_supervisor_readiness_report(build_runtime_supervisor_snapshot(service_records=(_record(),))), restart_authorized=True)
    assert not validate_runtime_supervisor_readiness_report(report).ok


def test_supervisor_report_can_be_referenced_by_execution_readiness_manifest() -> None:
    from sentientos.effect_proof import build_execution_proof_wing_for_rehearsal_receipt
    from tests.test_actuation_fulfillment import _broker_receipt_for
    from sentientos.actuation_fulfillment import build_actuation_fulfillment_plan, build_actuation_fulfillment_rehearsal_receipt

    rehearsal = build_actuation_fulfillment_rehearsal_receipt(build_actuation_fulfillment_plan(_broker_receipt_for("inspect_service_health_candidate", service_health_labels=("daemon_degraded",))))
    report = build_runtime_supervisor_readiness_report(build_runtime_supervisor_snapshot(service_records=(_record(),)))
    wing = build_execution_proof_wing_for_rehearsal_receipt(rehearsal, runtime_supervisor_report=report)
    assert wing.execution_readiness_manifest.runtime_supervisor_report_id == report.report_id
    assert wing.execution_readiness_manifest.authorization_granted is False


def test_runtime_supervisor_digests_are_deterministic_and_summaries_metadata_only() -> None:
    snapshot = build_runtime_supervisor_snapshot(service_records=(_record(),), snapshot_id="snap")
    report = build_runtime_supervisor_readiness_report(snapshot)
    assert runtime_supervisor_snapshot_digest(snapshot) == runtime_supervisor_snapshot_digest(snapshot)
    assert runtime_supervisor_readiness_digest(report) == runtime_supervisor_readiness_digest(report)
    assert summarize_runtime_supervisor_snapshot(snapshot)["metadata_only"] is True
    summary = summarize_runtime_supervisor_readiness_report(report)
    assert summary["metadata_only"] is True
    assert summary["restart_authorized"] is False
