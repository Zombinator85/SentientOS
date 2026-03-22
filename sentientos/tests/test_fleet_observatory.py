from __future__ import annotations

import json
from pathlib import Path

from sentientos.observatory import build_fleet_health_observatory


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_minimal_sources(root: Path) -> None:
    _write_json(root / "glow/constitution/constitution_summary.json", {"schema_version": 1, "constitution_state": "healthy", "missing_required_artifacts": []})
    _write_json(
        root / "glow/contracts/protected_corridor_report.json",
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile": "federation-enforce",
                    "summary": {
                        "blocking_failure_count": 0,
                        "provisioning_failure_count": 0,
                        "non_blocking_failure_count": 0,
                    },
                }
            ],
        },
    )
    _write_json(root / "glow/contracts/contract_status.json", {"schema_version": 1, "contracts": []})
    _write_json(
        root / "glow/contracts/strict_audit_status.json",
        {
            "schema_version": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "bucket": "healthy_strict",
            "readiness_class": "acceptable",
            "blocking": False,
            "degraded": False,
        },
    )
    _write_json(root / "glow/simulation/baseline_report.json", {"schema_version": 1, "status": "passed", "gating_failures": []})
    _write_json(root / "glow/formal/formal_check_summary.json", {"schema_version": 1, "status": "passed", "specs": []})
    _write_json(
        root / "glow/lab/wan_gate/wan_gate_report.json",
        {
            "schema_version": 1,
            "aggregate_outcome": "pass",
            "contradiction_count": 0,
            "degraded_scenario_count": 0,
            "scenario_results": [{"scenario": "wan_partition_recovery", "gate_outcome": "pass", "remote_smoke": True}],
        },
    )
    _write_json(
        root / "glow/lab/remote_preflight/remote_preflight_trend_report.json",
        {"schema_version": 1, "worsening_total": 0, "improved_total": 1, "pass_rate": 1.0},
    )
    _write_json(
        root / "glow/lab/wan/run-001/run_summary.json",
        {
            "schema_version": 1,
            "run_id": "run-001",
            "truth_oracle": {"summary": {"cluster_truth": "consistent", "contradictions": []}},
        },
    )
    _write_json(
        root / "glow/lab/wan_gate/evidence_density_report.json",
        {
            "schema_version": 1,
            "evidence_sparse_scenario_count": 0,
            "partially_evidenced_scenario_count": 0,
            "fully_evidenced_scenario_count": 1,
        },
    )


def test_observatory_emits_artifact_family(tmp_path: Path) -> None:
    _seed_minimal_sources(tmp_path)

    payload = build_fleet_health_observatory(tmp_path)

    assert payload["suite"] == "fleet_health_observatory"
    assert payload["release_readiness"] == "ready"
    for rel in payload["artifact_paths"].values():
        assert (tmp_path / str(rel)).exists()


def test_observatory_release_readiness_not_ready_on_blocking(tmp_path: Path) -> None:
    _seed_minimal_sources(tmp_path)
    _write_json(tmp_path / "glow/simulation/baseline_report.json", {"schema_version": 1, "status": "failed", "gating_failures": ["quorum_failure"]})

    payload = build_fleet_health_observatory(tmp_path)

    assert payload["release_readiness"] == "not_ready"
    summary = json.loads((tmp_path / "glow/observatory/fleet_health_summary.json").read_text(encoding="utf-8"))
    assert summary["fleet_dimensions"]["simulation_health"] == "blocking"


def test_observatory_release_readiness_not_ready_on_strict_audit_blocking(tmp_path: Path) -> None:
    _seed_minimal_sources(tmp_path)
    _write_json(
        tmp_path / "glow/contracts/strict_audit_status.json",
        {
            "schema_version": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "bucket": "blocking_chain_break",
            "readiness_class": "blocking",
            "blocking": True,
            "degraded": False,
        },
    )
    payload = build_fleet_health_observatory(tmp_path)
    assert payload["release_readiness"] == "not_ready"


def test_observatory_release_readiness_indeterminate_when_missing_evidence(tmp_path: Path) -> None:
    _seed_minimal_sources(tmp_path)
    (tmp_path / "glow/formal/formal_check_summary.json").unlink()

    payload = build_fleet_health_observatory(tmp_path)

    assert payload["release_readiness"] == "indeterminate_due_to_evidence"


def test_observatory_degradation_rollup_contains_wan_gate_warnings(tmp_path: Path) -> None:
    _seed_minimal_sources(tmp_path)
    _write_json(
        tmp_path / "glow/lab/wan_gate/wan_gate_report.json",
        {
            "schema_version": 1,
            "aggregate_outcome": "warning",
            "contradiction_count": 2,
            "degraded_scenario_count": 0,
            "scenario_results": [{"scenario": "wan_reanchor_truth_reconciliation", "gate_outcome": "warning", "remote_smoke": True}],
        },
    )

    build_fleet_health_observatory(tmp_path)
    degradations = json.loads((tmp_path / "glow/observatory/fleet_degradations.json").read_text(encoding="utf-8"))

    assert any(str(row.get("kind")) == "wan_gate_warning" for row in degradations["degradations"])


def test_observatory_history_is_bounded_append_only(tmp_path: Path) -> None:
    _seed_minimal_sources(tmp_path)
    history = tmp_path / "glow/observatory/fleet_health_history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text("".join(json.dumps({"i": idx}) + "\n" for idx in range(405)), encoding="utf-8")

    build_fleet_health_observatory(tmp_path)

    lines = history.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 400


def test_observatory_dashboard_embeds_artifact_index_links(tmp_path: Path) -> None:
    _seed_minimal_sources(tmp_path)

    build_fleet_health_observatory(tmp_path)

    dashboard = json.loads((tmp_path / "glow/observatory/fleet_health_dashboard.json").read_text(encoding="utf-8"))
    assert "artifact_latest_pointers" in dashboard
    assert "broad_lane_rows" in dashboard
    assert "artifact_provenance_links" in dashboard
    assert (tmp_path / "glow/observatory/latest_pointers.json").exists()


def test_observatory_federation_health_includes_protocol_posture(tmp_path: Path) -> None:
    _seed_minimal_sources(tmp_path)
    _write_json(
        tmp_path / "glow/federation/pulse_protocol_posture.json",
        {
            "schema_version": 1,
            "peers": [
                {
                    "peer_name": "peer-a",
                    "protocol_compatibility": "incompatible_protocol",
                    "replay_horizon_classification": "incompatible_replay_policy",
                    "equivocation_classification": "confirmed_equivocation",
                }
            ],
        },
    )

    payload = build_fleet_health_observatory(tmp_path)
    assert payload["fleet_dimensions"]["federation_health"] == "blocking"


def test_observatory_broad_lane_rows_show_pointer_and_lane_state_together(tmp_path: Path) -> None:
    _seed_minimal_sources(tmp_path)
    _write_json(
        tmp_path / "glow/test_runs/test_run_provenance.json",
        {
            "timestamp": "2026-03-18T00:00:00Z",
            "execution_mode": "execute",
            "metrics_status": "ok",
            "pytest_exit_code": 0,
            "run_id": "run-tests-1",
        },
    )
    _write_json(
        tmp_path / "glow/contracts/typing_ratchet_status.json",
        {
            "generated_at": "2026-03-21T00:00:00Z",
            "status": "ok",
            "deferred_debt_error_count": 4,
            "ratcheted_new_error_count": 0,
        },
    )

    payload = build_fleet_health_observatory(tmp_path)
    by_lane = {row["lane"]: row for row in payload["broad_lane_rows"]}
    assert by_lane["run_tests"]["pointer_state"] == "stale"
    assert by_lane["run_tests"]["lane_state"] == "lane_completed_with_advisories"
    assert by_lane["mypy"]["pointer_state"] == "current"
    assert by_lane["mypy"]["lane_state"] == "lane_completed_with_deferred_debt"


def test_observatory_broad_lane_rows_distinguish_missing_and_unavailable(tmp_path: Path) -> None:
    _seed_minimal_sources(tmp_path)
    _write_json(
        tmp_path / "glow/test_runs/test_run_provenance.json",
        {
            "timestamp": "2026-03-21T00:00:00Z",
            "execution_mode": "execute",
            "exit_reason": "airlock-failed",
            "metrics_status": "unavailable",
        },
    )

    payload = build_fleet_health_observatory(tmp_path)
    by_lane = {row["lane"]: row for row in payload["broad_lane_rows"]}
    assert by_lane["run_tests"]["pointer_state"] == "unavailable"
    assert by_lane["run_tests"]["lane_state"] == "lane_unavailable_in_environment"
    assert by_lane["mypy"]["pointer_state"] == "missing"
    assert by_lane["mypy"]["lane_state"] == "lane_not_run"


def test_observatory_contract_rollup_keeps_freshness_and_drift_distinct(tmp_path: Path) -> None:
    _seed_minimal_sources(tmp_path)
    _write_json(
        tmp_path / "glow/contracts/contract_status.json",
        {
            "schema_version": 1,
            "generated_at": "2020-01-01T00:00:00Z",
            "contracts": [
                {
                    "domain_name": "audits",
                    "baseline_present": True,
                    "drifted": False,
                    "drift_type": "none",
                    "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_AUDIT_DRIFT",
                },
                {
                    "domain_name": "perception",
                    "baseline_present": True,
                    "drifted": True,
                    "drift_type": "required_keys_changed",
                    "drift_explanation": "required keys diverged from baseline",
                    "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_PERCEPTION_SCHEMA_DRIFT",
                },
                {
                    "domain_name": "federation_identity",
                    "baseline_present": False,
                    "drifted": None,
                    "drift_type": "baseline_missing",
                    "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_FEDERATION_IDENTITY_DRIFT",
                },
            ],
        },
    )

    build_fleet_health_observatory(tmp_path)
    dashboard = json.loads((tmp_path / "glow/observatory/fleet_health_dashboard.json").read_text(encoding="utf-8"))
    rollup = dashboard["contract_drift_rollup"]
    rows = {row["domain"]: row for row in rollup["contract_rows"]}

    assert rows["audits"]["status"] == "healthy"
    assert rows["audits"]["pointer_state"] == "stale"
    assert rows["audits"]["alert_kind"] == "freshness_issue"
    assert rows["perception"]["status"] == "drifted"
    assert rows["perception"]["alert_kind"] == "domain_drift"
    assert rows["federation_identity"]["status"] == "baseline_missing"
    assert rows["federation_identity"]["alert_kind"] == "baseline_absent"
    summary = rollup["contract_row_summary"]
    assert summary["alert_counts"]["freshness_issue"] == 1
    assert summary["alert_counts"]["domain_drift"] == 1
    assert summary["alert_counts"]["baseline_absent"] == 1
    assert rollup["contract_alert_badge"] == "domain_drift"
    assert rollup["contract_alert_reason"] == "domain_drift_rows_present"
