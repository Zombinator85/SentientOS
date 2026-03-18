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
    assert "artifact_provenance_links" in dashboard
    assert (tmp_path / "glow/observatory/latest_pointers.json").exists()
