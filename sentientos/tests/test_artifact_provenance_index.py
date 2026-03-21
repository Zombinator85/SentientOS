from __future__ import annotations

import json
from pathlib import Path

from sentientos.attestation import iso_now
from sentientos.observatory import build_artifact_provenance_index


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_sources(root: Path) -> None:
    now = iso_now()
    _write_json(root / "glow/contracts/contract_status.json", {"schema_version": 1, "generated_at": now, "contracts": []})
    _write_json(
        root / "glow/contracts/strict_audit_status.json",
        {
            "schema_version": 1,
            "generated_at": now,
            "bucket": "healthy_strict",
            "readiness_class": "acceptable",
            "blocking": False,
            "degraded": False,
        },
    )
    _write_json(root / "glow/contracts/protected_corridor_report.json", {"schema_version": 1, "generated_at": now, "profiles": []})
    _write_json(root / "glow/simulation/baseline_report.json", {"schema_version": 1, "generated_at": now, "status": "passed"})
    _write_json(root / "glow/formal/formal_check_summary.json", {"schema_version": 1, "generated_at": now, "status": "passed", "specs": []})
    _write_json(
        root / "glow/lab/wan_gate/wan_gate_report.json",
        {
            "schema_version": 1,
            "generated_at": now,
            "profile": "default",
            "aggregate_outcome": "pass",
            "artifact_paths": {
                "contradiction_policy_report": "glow/lab/wan_gate/contradiction_policy_report.json",
                "evidence_density_report": "glow/lab/wan_gate/evidence_density_report.json",
                "release_gate_manifest": "glow/lab/wan_gate/release_gate_manifest.json",
            },
        },
    )
    _write_json(root / "glow/lab/wan_gate/contradiction_policy_report.json", {"schema_version": 1})
    _write_json(root / "glow/lab/wan_gate/evidence_density_report.json", {"schema_version": 1})
    _write_json(root / "glow/lab/wan_gate/release_gate_manifest.json", {"schema_version": 1})
    _write_json(root / "glow/lab/remote_preflight/remote_preflight_trend_report.json", {"schema_version": 1, "generated_at": now, "window_entries": 3})
    (root / "glow/lab/remote_preflight/remote_preflight_history.jsonl").write_text(
        "\n".join(
            json.dumps({"scenario": "wan_partition_recovery", "seed": idx, "topology": "three_host_ring", "host_id": f"h{idx}"}) for idx in range(3)
        )
        + "\n",
        encoding="utf-8",
    )
    _write_json(root / "glow/lab/remote_preflight/remote_preflight_rollup.json", {"schema_version": 1})

    _write_json(root / "glow/lab/wan/run-old/wan_truth/truth_oracle_summary.json", {"schema_version": 1, "generated_at": now, "run_id": "run-001", "cluster_truth": "consistent"})
    _write_json(root / "glow/lab/wan/run-new/wan_truth/truth_oracle_summary.json", {"schema_version": 1, "generated_at": now, "run_id": "run-002", "cluster_truth": "consistent"})
    _write_json(
        root / "glow/lab/wan/run-new/wan_truth/evidence_manifest.json",
        {
            "schema_version": 1,
            "node_evidence": [
                {"node_id": "node-a", "node_truth_path": str(root / "glow/lab/wan/run-new/node-a/glow/lab/node_truth_artifacts.json")}
            ],
        },
    )
    _write_json(root / "glow/lab/wan/run-new/node-a/glow/lab/node_truth_artifacts.json", {"schema_version": 1, "node": "node-a"})

    _write_json(root / "glow/observatory/fleet_health_summary.json", {"schema_version": 1, "generated_at": now, "release_readiness": "ready"})


def test_artifact_index_emits_family_and_latest_selection(tmp_path: Path) -> None:
    _seed_sources(tmp_path)

    payload = build_artifact_provenance_index(tmp_path)

    assert payload["suite"] == "artifact_provenance_index"
    latest = json.loads((tmp_path / "glow/observatory/latest_pointers.json").read_text(encoding="utf-8"))
    assert latest["surfaces"]["wan_truth_oracle"]["artifact_path"] == "glow/lab/wan/run-new/wan_truth/truth_oracle_summary.json"

    index = json.loads((tmp_path / "glow/observatory/artifact_index.json").read_text(encoding="utf-8"))
    states = {(row["surface"], row["artifact_path"]): row["pointer_state"] for row in index["artifacts"]}
    assert states[("wan_truth_oracle", "glow/lab/wan/run-new/wan_truth/truth_oracle_summary.json")] == "current"
    assert states[("wan_truth_oracle", "glow/lab/wan/run-old/wan_truth/truth_oracle_summary.json")] == "superseded"


def test_artifact_index_marks_missing_and_stale(tmp_path: Path) -> None:
    _seed_sources(tmp_path)
    (tmp_path / "glow/lab/wan_gate/wan_gate_report.json").unlink()
    _write_json(
        tmp_path / "glow/contracts/contract_status.json",
        {"schema_version": 1, "generated_at": "2020-01-01T00:00:00Z", "contracts": []},
    )

    build_artifact_provenance_index(tmp_path)

    latest = json.loads((tmp_path / "glow/observatory/latest_pointers.json").read_text(encoding="utf-8"))
    assert latest["surfaces"]["wan_gate"]["pointer_state"] == "missing"
    assert latest["surfaces"]["contract_status"]["pointer_state"] == "stale"


def test_artifact_index_links_include_cross_surface_provenance(tmp_path: Path) -> None:
    _seed_sources(tmp_path)

    build_artifact_provenance_index(tmp_path)

    links = json.loads((tmp_path / "glow/observatory/artifact_provenance_links.json").read_text(encoding="utf-8"))
    rels = {(row["from_surface"], row["to_surface"], row["relation"]) for row in links["links"]}
    assert ("fleet_observatory", "wan_gate", "summarizes") in rels
    assert ("fleet_observatory", "strict_audit_status", "summarizes") in rels
    assert ("wan_gate", "wan_truth_oracle", "depends_on_truth") in rels
    assert ("remote_preflight_trend", "remote_preflight_history", "rolls_up") in rels


def test_artifact_index_digest_is_deterministic(tmp_path: Path) -> None:
    _seed_sources(tmp_path)

    build_artifact_provenance_index(tmp_path)
    first = json.loads((tmp_path / "glow/observatory/final_artifact_index_digest.json").read_text(encoding="utf-8"))
    build_artifact_provenance_index(tmp_path)
    second = json.loads((tmp_path / "glow/observatory/final_artifact_index_digest.json").read_text(encoding="utf-8"))

    assert first["artifact_provenance_digest"] == second["artifact_provenance_digest"]

def test_artifact_index_embeds_broad_lane_latest_surfaces(tmp_path: Path) -> None:
    _seed_sources(tmp_path)
    _write_json(
        tmp_path / "glow/test_runs/test_run_provenance.json",
        {"timestamp": iso_now(), "execution_mode": "execute", "metrics_status": "ok", "pytest_exit_code": 0},
    )
    _write_json(
        tmp_path / "glow/contracts/typing_ratchet_status.json",
        {"generated_at": iso_now(), "status": "ok", "deferred_debt_error_count": 0},
    )

    build_artifact_provenance_index(tmp_path)

    latest = json.loads((tmp_path / "glow/observatory/latest_pointers.json").read_text(encoding="utf-8"))
    assert latest["surfaces"]["run_tests_broad_lane"]["pointer_state"] in {"current", "stale", "unavailable", "incomplete"}
    assert latest["surfaces"]["mypy_broad_lane"]["pointer_state"] in {"current", "stale", "unavailable", "incomplete"}
    assert latest["surfaces"]["broad_lane_latest_summary"]["artifact_path"] == "glow/observatory/broad_lane/broad_lane_latest_summary.json"
    broad_metadata = latest["surfaces"]["broad_lane_latest_summary"]["metadata"]
    lane_rows = {row["lane"]: row for row in broad_metadata["lane_rows"]}
    assert lane_rows["run_tests"]["pointer_state"] in {"current", "stale", "unavailable", "incomplete", "missing"}
    assert lane_rows["run_tests"]["lane_state"]
    assert lane_rows["run_tests"]["policy_meaning"]
    assert lane_rows["run_tests"]["summary_reason"].startswith("pointer=")


def test_artifact_index_selected_surfaces_embed_summary_rows(tmp_path: Path) -> None:
    _seed_sources(tmp_path)
    _write_json(
        tmp_path / "glow/contracts/protected_corridor_report.json",
        {
            "schema_version": 1,
            "generated_at": iso_now(),
            "global_summary": {
                "status": "amber",
                "repo_health": "amber",
                "corridor_blocking": False,
                "blocking_profiles": [],
                "advisory_profiles": ["ci-advisory"],
                "debt_profiles": [],
            },
            "profiles": [],
        },
    )

    build_artifact_provenance_index(tmp_path)

    latest = json.loads((tmp_path / "glow/observatory/latest_pointers.json").read_text(encoding="utf-8"))
    for surface in ("fleet_observatory", "strict_audit_status", "protected_corridor", "wan_gate", "remote_preflight_trend"):
        row = latest["surfaces"][surface]
        summary_rows = row["metadata"]["summary_rows"]
        assert isinstance(summary_rows, list)
        assert len(summary_rows) == 1
        first = summary_rows[0]
        assert first["pointer_state"] == row["pointer_state"]
        assert first["summary_reason"]
        assert first["primary_artifact_path"] == row["artifact_path"]


def test_selected_surface_summary_rows_keep_pointer_state_separate_from_health(tmp_path: Path) -> None:
    _seed_sources(tmp_path)
    _write_json(
        tmp_path / "glow/contracts/strict_audit_status.json",
        {
            "schema_version": 1,
            "generated_at": "2020-01-01T00:00:00Z",
            "bucket": "healthy_strict",
            "readiness_class": "acceptable",
            "blocking": False,
            "degraded": False,
            "status_hint": "all good",
        },
    )

    build_artifact_provenance_index(tmp_path)
    latest = json.loads((tmp_path / "glow/observatory/latest_pointers.json").read_text(encoding="utf-8"))
    strict = latest["surfaces"]["strict_audit_status"]
    summary = strict["metadata"]["summary_rows"][0]

    assert strict["pointer_state"] == "stale"
    assert summary["pointer_state"] == "stale"
    assert summary["health_state"] == "healthy"
    assert summary["status"] == "healthy_strict"
