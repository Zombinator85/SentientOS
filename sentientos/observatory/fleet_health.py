from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from sentientos.attestation import iso_now, read_json, read_jsonl, write_json
from sentientos.observatory.artifact_index import build_artifact_provenance_index

FleetDimensionStatus = Literal[
    "healthy",
    "degraded",
    "restricted",
    "warning",
    "blocking",
    "missing_evidence",
    "unavailable",
]
ReleaseReadiness = Literal[
    "ready",
    "ready_with_degradation",
    "not_ready",
    "indeterminate_due_to_evidence",
    "blocked_by_policy",
]

DIMENSIONS: tuple[str, ...] = (
    "constitution_health",
    "corridor_health",
    "simulation_health",
    "formal_health",
    "federation_health",
    "wan_gate_health",
    "remote_smoke_health",
    "preflight_drift_health",
    "evidence_density_health",
    "release_readiness",
)


def _stable_digest(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _read_json_if_exists(root: Path, rel: str) -> dict[str, Any]:
    path = root / rel
    return read_json(path) if path.exists() else {}


def _find_latest_run(root: Path, rel_dir: str) -> Path | None:
    run_root = root / rel_dir
    if not run_root.exists() or not run_root.is_dir():
        return None
    candidates = [path for path in run_root.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.name)[-1]


def _dimension_status(rank: int) -> FleetDimensionStatus:
    return {
        0: "healthy",
        1: "degraded",
        2: "warning",
        3: "restricted",
        4: "blocking",
        5: "missing_evidence",
    }.get(rank, "unavailable")


def _status_rank(status: str) -> int:
    return {
        "healthy": 0,
        "degraded": 1,
        "warning": 2,
        "restricted": 3,
        "blocking": 4,
        "missing_evidence": 5,
        "unavailable": 6,
    }.get(status, 6)


def _path_or_none(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _constitution_health(root: Path) -> tuple[FleetDimensionStatus, dict[str, Any], list[dict[str, Any]]]:
    payload = _read_json_if_exists(root, "glow/constitution/constitution_summary.json")
    state = str(payload.get("constitution_state") or "")
    missing = payload.get("missing_required_artifacts") if isinstance(payload.get("missing_required_artifacts"), list) else []
    degradations: list[dict[str, Any]] = []
    if not payload:
        return "missing_evidence", {"source": "glow/constitution/constitution_summary.json", "state": "missing"}, [
            {"kind": "constitutional_restriction", "severity": "missing_evidence", "message": "constitution summary missing"}
        ]
    if state in {"healthy", "passed"}:
        status: FleetDimensionStatus = "healthy"
    elif state in {"restricted", "degraded"}:
        status = "restricted"
        degradations.append({"kind": "constitutional_restriction", "severity": "restricted", "message": f"constitution state={state}"})
    else:
        status = "warning"
        degradations.append({"kind": "constitutional_restriction", "severity": "warning", "message": f"constitution state={state or 'unknown'}"})
    if missing:
        degradations.append({"kind": "constitutional_missing_required_artifacts", "severity": "blocking", "message": f"missing_required_artifacts={len(missing)}"})
        status = "blocking"
    return status, {"source": "glow/constitution/constitution_summary.json", "constitution_state": state, "missing_required_artifacts": missing}, degradations


def _corridor_health(root: Path) -> tuple[FleetDimensionStatus, dict[str, Any], list[dict[str, Any]]]:
    report = _read_json_if_exists(root, "glow/contracts/protected_corridor_report.json")
    if not report:
        return "missing_evidence", {"source": "glow/contracts/protected_corridor_report.json", "profiles": []}, [
            {"kind": "protected_corridor_missing", "severity": "missing_evidence", "message": "protected corridor report missing"}
        ]
    profiles = report.get("profiles") if isinstance(report.get("profiles"), list) else []
    block = 0
    provisioning = 0
    non_blocking = 0
    for row in profiles:
        if not isinstance(row, dict):
            continue
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        block += int(summary.get("blocking_failure_count") or 0)
        provisioning += int(summary.get("provisioning_failure_count") or 0)
        non_blocking += int(summary.get("non_blocking_failure_count") or 0)
    degradations: list[dict[str, Any]] = []
    if block > 0:
        degradations.append({"kind": "protected_corridor_blockers", "severity": "blocking", "message": f"blocking_failure_count={block}"})
        status: FleetDimensionStatus = "blocking"
    elif provisioning > 0:
        degradations.append({"kind": "protected_corridor_provisioning", "severity": "restricted", "message": f"provisioning_failure_count={provisioning}"})
        status = "restricted"
    elif non_blocking > 0:
        degradations.append({"kind": "protected_corridor_non_blocking", "severity": "degraded", "message": f"non_blocking_failure_count={non_blocking}"})
        status = "degraded"
    else:
        status = "healthy"
    return status, {
        "source": "glow/contracts/protected_corridor_report.json",
        "profile_count": len(profiles),
        "blocking_failure_count": block,
        "provisioning_failure_count": provisioning,
        "non_blocking_failure_count": non_blocking,
    }, degradations


def _simulation_health(root: Path) -> tuple[FleetDimensionStatus, dict[str, Any], list[dict[str, Any]]]:
    report = _read_json_if_exists(root, "glow/simulation/baseline_report.json")
    if not report:
        return "missing_evidence", {"source": "glow/simulation/baseline_report.json", "status": "missing"}, [
            {"kind": "simulation_baseline_missing", "severity": "missing_evidence", "message": "simulation baseline report missing"}
        ]
    status = str(report.get("status") or "")
    gating_failures = report.get("gating_failures") if isinstance(report.get("gating_failures"), list) else []
    degradations: list[dict[str, Any]] = []
    if status == "passed":
        dim: FleetDimensionStatus = "healthy"
    else:
        dim = "blocking"
        degradations.append({"kind": "simulation_baseline_failures", "severity": "blocking", "message": f"gating_failures={gating_failures}"})
    return dim, {
        "source": "glow/simulation/baseline_report.json",
        "status": status,
        "gating_failure_count": len(gating_failures),
    }, degradations


def _formal_health(root: Path) -> tuple[FleetDimensionStatus, dict[str, Any], list[dict[str, Any]]]:
    report = _read_json_if_exists(root, "glow/formal/formal_check_summary.json")
    if not report:
        return "missing_evidence", {"source": "glow/formal/formal_check_summary.json", "status": "missing"}, [
            {"kind": "formal_summary_missing", "severity": "missing_evidence", "message": "formal verification summary missing"}
        ]
    status = str(report.get("status") or "")
    specs = report.get("specs") if isinstance(report.get("specs"), list) else []
    failed_specs = [row.get("spec_id") for row in specs if isinstance(row, dict) and not bool(row.get("passed"))]
    degradations: list[dict[str, Any]] = []
    if status == "passed":
        dim: FleetDimensionStatus = "healthy"
    else:
        dim = "blocking"
        degradations.append({"kind": "formal_spec_failures", "severity": "blocking", "message": f"failed_specs={failed_specs}"})
    return dim, {
        "source": "glow/formal/formal_check_summary.json",
        "status": status,
        "spec_count": len(specs),
        "failed_spec_count": len(failed_specs),
    }, degradations


def _wan_gate_health(root: Path) -> tuple[FleetDimensionStatus, dict[str, Any], list[dict[str, Any]]]:
    report = _read_json_if_exists(root, "glow/lab/wan_gate/wan_gate_report.json")
    if not report:
        return "missing_evidence", {"source": "glow/lab/wan_gate/wan_gate_report.json", "status": "missing"}, [
            {"kind": "wan_gate_report_missing", "severity": "missing_evidence", "message": "WAN release gate report missing"}
        ]
    outcome = str(report.get("aggregate_outcome") or "")
    contradictions = int(report.get("contradiction_count") or 0)
    degraded = int(report.get("degraded_scenario_count") or 0)
    degradations: list[dict[str, Any]] = []
    if outcome == "pass":
        dim: FleetDimensionStatus = "healthy"
    elif outcome == "pass_with_degradation":
        dim = "degraded"
        degradations.append({"kind": "wan_gate_degraded", "severity": "degraded", "message": f"degraded_scenario_count={degraded}"})
    elif outcome == "warning":
        dim = "warning"
        degradations.append({"kind": "wan_gate_warning", "severity": "warning", "message": f"contradiction_count={contradictions}"})
    elif outcome == "indeterminate":
        dim = "missing_evidence"
        degradations.append({"kind": "wan_gate_indeterminate", "severity": "missing_evidence", "message": "release gate indeterminate"})
    else:
        dim = "blocking"
        degradations.append({"kind": "wan_gate_blocking", "severity": "blocking", "message": f"aggregate_outcome={outcome or 'unknown'}"})
    return dim, {
        "source": "glow/lab/wan_gate/wan_gate_report.json",
        "aggregate_outcome": outcome,
        "contradiction_count": contradictions,
        "degraded_scenario_count": degraded,
    }, degradations


def _federation_health(root: Path) -> tuple[FleetDimensionStatus, dict[str, Any], list[dict[str, Any]]]:
    latest = _find_latest_run(root, "glow/lab/wan")
    if latest is None:
        return "missing_evidence", {"source": "glow/lab/wan/<latest>/run_summary.json", "status": "missing"}, [
            {"kind": "wan_run_missing", "severity": "missing_evidence", "message": "no WAN run found"}
        ]
    summary = read_json(latest / "run_summary.json")
    truth = summary.get("truth_oracle") if isinstance(summary.get("truth_oracle"), dict) else {}
    truth_summary = truth.get("summary") if isinstance(truth.get("summary"), dict) else {}
    cluster_truth = str(truth_summary.get("cluster_truth") or "")
    contradictions = truth_summary.get("contradictions") if isinstance(truth_summary.get("contradictions"), list) else []
    if cluster_truth == "consistent":
        dim: FleetDimensionStatus = "healthy"
        degradations: list[dict[str, Any]] = []
    elif cluster_truth == "degraded_but_explained":
        dim = "degraded"
        degradations = [{"kind": "wan_truth_degraded", "severity": "degraded", "message": f"contradictions={len(contradictions)}"}]
    elif cluster_truth:
        dim = "blocking"
        degradations = [{"kind": "wan_truth_inconsistent", "severity": "blocking", "message": f"cluster_truth={cluster_truth}"}]
    else:
        dim = "missing_evidence"
        degradations = [{"kind": "wan_truth_missing", "severity": "missing_evidence", "message": "truth oracle summary unavailable"}]
    return dim, {
        "source": _path_or_none(root, latest / "run_summary.json"),
        "cluster_truth": cluster_truth,
        "contradiction_count": len(contradictions),
        "run_id": summary.get("run_id"),
    }, degradations


def _remote_smoke_health(root: Path) -> tuple[FleetDimensionStatus, dict[str, Any], list[dict[str, Any]]]:
    gate = _read_json_if_exists(root, "glow/lab/wan_gate/wan_gate_report.json")
    scenarios = gate.get("scenario_results") if isinstance(gate.get("scenario_results"), list) else []
    remote = [row for row in scenarios if isinstance(row, dict) and bool(row.get("remote_smoke"))]
    if not scenarios:
        return "missing_evidence", {"source": "glow/lab/wan_gate/wan_gate_report.json", "remote_smoke_count": 0}, [
            {"kind": "remote_smoke_missing", "severity": "missing_evidence", "message": "WAN gate scenario results unavailable"}
        ]
    if not remote:
        return "warning", {"source": "glow/lab/wan_gate/wan_gate_report.json", "remote_smoke_count": 0}, [
            {"kind": "remote_smoke_not_executed", "severity": "warning", "message": "no remote smoke scenarios marked"}
        ]
    outcomes = {str(row.get("gate_outcome") or "") for row in remote}
    degradations: list[dict[str, Any]] = []
    if outcomes.issubset({"pass"}):
        dim: FleetDimensionStatus = "healthy"
    elif outcomes.intersection({"blocking_failure", "warning"}):
        dim = "blocking"
        degradations.append({"kind": "remote_smoke_failures", "severity": "blocking", "message": f"outcomes={sorted(outcomes)}"})
    else:
        dim = "degraded"
        degradations.append({"kind": "remote_smoke_degraded", "severity": "degraded", "message": f"outcomes={sorted(outcomes)}"})
    return dim, {
        "source": "glow/lab/wan_gate/wan_gate_report.json",
        "remote_smoke_count": len(remote),
        "outcomes": sorted(outcomes),
    }, degradations


def _preflight_drift_health(root: Path) -> tuple[FleetDimensionStatus, dict[str, Any], list[dict[str, Any]]]:
    trend = _read_json_if_exists(root, "glow/lab/remote_preflight/remote_preflight_trend_report.json")
    if not trend:
        return "missing_evidence", {"source": "glow/lab/remote_preflight/remote_preflight_trend_report.json"}, [
            {"kind": "remote_preflight_missing", "severity": "missing_evidence", "message": "remote preflight trend report missing"}
        ]
    worsening = int(trend.get("worsening_total") or 0)
    improved = int(trend.get("improved_total") or 0)
    pass_rate = trend.get("pass_rate")
    degradations: list[dict[str, Any]] = []
    if worsening > 0:
        dim: FleetDimensionStatus = "warning"
        degradations.append({"kind": "remote_preflight_worsening", "severity": "warning", "message": f"worsening_total={worsening}"})
    elif isinstance(pass_rate, (int, float)) and float(pass_rate) < 0.95:
        dim = "degraded"
        degradations.append({"kind": "remote_preflight_low_pass_rate", "severity": "degraded", "message": f"pass_rate={pass_rate}"})
    elif improved > 0:
        dim = "healthy"
    else:
        dim = "healthy"
    return dim, {
        "source": "glow/lab/remote_preflight/remote_preflight_trend_report.json",
        "worsening_total": worsening,
        "improved_total": improved,
        "pass_rate": pass_rate,
    }, degradations


def _evidence_density_health(root: Path) -> tuple[FleetDimensionStatus, dict[str, Any], list[dict[str, Any]]]:
    density = _read_json_if_exists(root, "glow/lab/wan_gate/evidence_density_report.json")
    if not density:
        latest = _find_latest_run(root, "glow/lab/wan")
        if latest is not None:
            density = read_json(latest / "wan_truth" / "evidence_density_report.json")
    if not density:
        return "missing_evidence", {"source": "glow/lab/wan_gate/evidence_density_report.json"}, [
            {"kind": "evidence_density_missing", "severity": "missing_evidence", "message": "evidence density report missing"}
        ]
    sparse = int(density.get("evidence_sparse_scenario_count") or 0)
    partial = int(density.get("partially_evidenced_scenario_count") or 0)
    full = int(density.get("fully_evidenced_scenario_count") or 0)
    degradations: list[dict[str, Any]] = []
    if sparse > 0:
        dim: FleetDimensionStatus = "missing_evidence"
        degradations.append({"kind": "evidence_sparse_scenarios", "severity": "missing_evidence", "message": f"evidence_sparse_scenario_count={sparse}"})
    elif partial > 0:
        dim = "degraded"
        degradations.append({"kind": "evidence_partial_scenarios", "severity": "degraded", "message": f"partially_evidenced_scenario_count={partial}"})
    elif full > 0:
        dim = "healthy"
    else:
        dim = "warning"
    return dim, {
        "source": density.get("source") or "glow/lab/wan_gate/evidence_density_report.json",
        "evidence_sparse_scenario_count": sparse,
        "partially_evidenced_scenario_count": partial,
        "fully_evidenced_scenario_count": full,
    }, degradations


def _contract_drift_health(root: Path) -> dict[str, Any]:
    status = _read_json_if_exists(root, "glow/contracts/contract_status.json")
    rows = status.get("contracts") if isinstance(status.get("contracts"), list) else []
    drifted = []
    missing = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        domain = str(row.get("domain_name") or "unknown")
        drift_type = str(row.get("drift_type") or "")
        drifted_value = row.get("drifted")
        if drifted_value is True and drift_type not in {"none", ""}:
            drifted.append({"domain": domain, "drift_type": drift_type, "drift_explanation": row.get("drift_explanation")})
        if drift_type in {"baseline_missing", "artifact_missing", "preflight_required"}:
            missing.append({"domain": domain, "drift_type": drift_type})
    return {
        "source": "glow/contracts/contract_status.json",
        "contract_count": len(rows),
        "drifted_domains": drifted,
        "missing_domains": missing,
    }


def _incident_snapshot(root: Path) -> dict[str, Any]:
    bundles = sorted((root / "glow/incidents").glob("bundle_*.json")) if (root / "glow/incidents").exists() else []
    latest = bundles[-1] if bundles else None
    payload = read_json(latest) if latest else {}
    return {
        "bundle_count": len(bundles),
        "latest_bundle": _path_or_none(root, latest) if latest else None,
        "latest_bundle_reason": payload.get("reason") if isinstance(payload, dict) else None,
    }


def _release_readiness(dimensions: dict[str, FleetDimensionStatus]) -> tuple[ReleaseReadiness, list[str]]:
    reasons: list[str] = []
    blocking_dims = [name for name, status in dimensions.items() if status == "blocking"]
    policy_block = any(name in {"constitution_health", "wan_gate_health"} and dimensions[name] in {"blocking", "restricted"} for name in dimensions)
    evidence_missing = any(status in {"missing_evidence", "unavailable"} for status in dimensions.values())

    if policy_block:
        reasons.append("policy or constitutional restriction present")
        if "wan_gate_health" in blocking_dims or dimensions.get("constitution_health") == "restricted":
            return "blocked_by_policy", reasons
    if blocking_dims:
        reasons.append(f"blocking dimensions: {blocking_dims}")
        return "not_ready", reasons
    if evidence_missing:
        reasons.append("insufficient evidence across required dimensions")
        return "indeterminate_due_to_evidence", reasons
    degraded = [name for name, status in dimensions.items() if status in {"degraded", "warning", "restricted"}]
    if degraded:
        reasons.append(f"degraded dimensions: {degraded}")
        return "ready_with_degradation", reasons
    reasons.append("all required dimensions healthy")
    return "ready", reasons


def build_fleet_health_observatory(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    out_root = root / "glow" / "observatory"
    out_root.mkdir(parents=True, exist_ok=True)

    constitution_status, constitution_detail, constitution_degradations = _constitution_health(root)
    corridor_status, corridor_detail, corridor_degradations = _corridor_health(root)
    simulation_status, simulation_detail, simulation_degradations = _simulation_health(root)
    formal_status, formal_detail, formal_degradations = _formal_health(root)
    federation_status, federation_detail, federation_degradations = _federation_health(root)
    wan_gate_status, wan_gate_detail, wan_gate_degradations = _wan_gate_health(root)
    remote_smoke_status, remote_smoke_detail, remote_smoke_degradations = _remote_smoke_health(root)
    preflight_status, preflight_detail, preflight_degradations = _preflight_drift_health(root)
    evidence_status, evidence_detail, evidence_degradations = _evidence_density_health(root)

    dimensions: dict[str, FleetDimensionStatus] = {
        "constitution_health": constitution_status,
        "corridor_health": corridor_status,
        "simulation_health": simulation_status,
        "formal_health": formal_status,
        "federation_health": federation_status,
        "wan_gate_health": wan_gate_status,
        "remote_smoke_health": remote_smoke_status,
        "preflight_drift_health": preflight_status,
        "evidence_density_health": evidence_status,
    }

    readiness, readiness_reasons = _release_readiness(dimensions)
    dimensions["release_readiness"] = "healthy" if readiness == "ready" else "degraded" if readiness == "ready_with_degradation" else "blocking" if readiness in {"not_ready", "blocked_by_policy"} else "missing_evidence"

    degradations: list[dict[str, Any]] = [
        *constitution_degradations,
        *corridor_degradations,
        *simulation_degradations,
        *formal_degradations,
        *federation_degradations,
        *wan_gate_degradations,
        *remote_smoke_degradations,
        *preflight_degradations,
        *evidence_degradations,
    ]

    degradations_sorted = sorted(degradations, key=lambda row: (_status_rank(str(row.get("severity") or "unavailable")), str(row.get("kind") or "")))

    contract_drift = _contract_drift_health(root)
    incidents = _incident_snapshot(root)

    summary = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "fleet_dimensions": dimensions,
        "release_readiness": readiness,
        "release_readiness_reasons": readiness_reasons,
        "degradation_count": len(degradations_sorted),
        "blocking_count": sum(1 for row in degradations_sorted if str(row.get("severity") or "") == "blocking"),
        "missing_evidence_count": sum(1 for row in degradations_sorted if str(row.get("severity") or "") == "missing_evidence"),
    }

    dashboard = {
        "schema_version": 1,
        "generated_at": summary["generated_at"],
        "dimensions": {
            "constitution_health": constitution_detail,
            "corridor_health": corridor_detail,
            "simulation_health": simulation_detail,
            "formal_health": formal_detail,
            "federation_health": federation_detail,
            "wan_gate_health": wan_gate_detail,
            "remote_smoke_health": remote_smoke_detail,
            "preflight_drift_health": preflight_detail,
            "evidence_density_health": evidence_detail,
            "release_readiness": {
                "status": readiness,
                "reasons": readiness_reasons,
            },
        },
        "contract_drift_rollup": contract_drift,
        "incident_rollup": incidents,
    }

    release = {
        "schema_version": 1,
        "generated_at": summary["generated_at"],
        "status": readiness,
        "reasons": readiness_reasons,
        "inputs": {
            "constitution_health": constitution_status,
            "corridor_health": corridor_status,
            "simulation_health": simulation_status,
            "formal_health": formal_status,
            "wan_gate_health": wan_gate_status,
            "remote_smoke_health": remote_smoke_status,
            "evidence_density_health": evidence_status,
        },
    }

    degradations_payload = {
        "schema_version": 1,
        "generated_at": summary["generated_at"],
        "degradations": degradations_sorted,
    }

    write_json(out_root / "fleet_health_summary.json", summary)
    artifact_index_payload = build_artifact_provenance_index(root)
    latest_pointers_payload = read_json(root / "glow/observatory/latest_pointers.json")
    links_payload = read_json(root / "glow/observatory/artifact_provenance_links.json")
    dashboard["artifact_latest_pointers"] = latest_pointers_payload.get("surfaces", {})
    dashboard["artifact_provenance_links"] = links_payload.get("links", [])

    write_json(out_root / "fleet_health_dashboard.json", dashboard)
    write_json(out_root / "fleet_degradations.json", degradations_payload)
    write_json(out_root / "fleet_release_readiness.json", release)

    manifest = {
        "schema_version": 1,
        "suite": "fleet_health_observatory",
        "generated_at": summary["generated_at"],
        "artifacts": {
            "fleet_health_summary": "glow/observatory/fleet_health_summary.json",
            "fleet_health_dashboard": "glow/observatory/fleet_health_dashboard.json",
            "fleet_degradations": "glow/observatory/fleet_degradations.json",
            "fleet_release_readiness": "glow/observatory/fleet_release_readiness.json",
        },
        "source_artifacts": {
            "contract_status": "glow/contracts/contract_status.json",
            "protected_corridor": "glow/contracts/protected_corridor_report.json",
            "simulation_baseline": "glow/simulation/baseline_report.json",
            "formal_summary": "glow/formal/formal_check_summary.json",
            "wan_gate_report": "glow/lab/wan_gate/wan_gate_report.json",
            "remote_preflight_trend": "glow/lab/remote_preflight/remote_preflight_trend_report.json",
            "artifact_index_latest_pointers": "glow/observatory/latest_pointers.json",
            "artifact_index_links": "glow/observatory/artifact_provenance_links.json",
        },
    }
    write_json(out_root / "fleet_observatory_manifest.json", manifest)

    digest_payload = {
        "schema_version": 1,
        "generated_at": summary["generated_at"],
        "summary_digest": _stable_digest(summary),
        "dashboard_digest": _stable_digest(dashboard),
        "degradations_digest": _stable_digest(degradations_payload),
        "release_digest": _stable_digest(release),
        "manifest_digest": _stable_digest(manifest),
    }
    digest_payload["fleet_digest"] = _stable_digest(digest_payload)
    write_json(out_root / "final_fleet_health_digest.json", digest_payload)

    history_path = out_root / "fleet_health_history.jsonl"
    history_row = {
        "generated_at": summary["generated_at"],
        "fleet_dimensions": dimensions,
        "release_readiness": readiness,
        "fleet_digest": digest_payload["fleet_digest"],
    }
    rows = read_jsonl(history_path)
    rows.append(history_row)
    rows = rows[-400:]
    history_path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in rows), encoding="utf-8")

    return {
        "schema_version": 1,
        "suite": "fleet_health_observatory",
        "status": "passed",
        "ok": True,
        "exit_code": 0,
        "fleet_dimensions": dimensions,
        "release_readiness": readiness,
        "artifact_paths": {
            "fleet_health_summary": "glow/observatory/fleet_health_summary.json",
            "fleet_health_dashboard": "glow/observatory/fleet_health_dashboard.json",
            "fleet_degradations": "glow/observatory/fleet_degradations.json",
            "fleet_release_readiness": "glow/observatory/fleet_release_readiness.json",
            "fleet_observatory_manifest": "glow/observatory/fleet_observatory_manifest.json",
            "final_fleet_health_digest": "glow/observatory/final_fleet_health_digest.json",
            "fleet_health_history": "glow/observatory/fleet_health_history.jsonl",
            "artifact_index": "glow/observatory/artifact_index.json",
            "latest_pointers": "glow/observatory/latest_pointers.json",
            "artifact_provenance_links": "glow/observatory/artifact_provenance_links.json",
            "artifact_index_manifest": "glow/observatory/artifact_index_manifest.json",
            "final_artifact_index_digest": "glow/observatory/final_artifact_index_digest.json",
        },
        "artifact_index": {
            "suite": artifact_index_payload.get("suite"),
            "surface_states": artifact_index_payload.get("surface_states"),
        },
    }
