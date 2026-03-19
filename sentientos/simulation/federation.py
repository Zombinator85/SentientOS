from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from sentientos.attestation import append_jsonl, read_json, write_json
from sentientos.node_operations import build_incident_bundle, node_health, run_bootstrap


BASELINE_MANIFEST_PATH = Path(__file__).with_name("federation_baseline_manifest.json")

SCENARIOS: dict[str, dict[str, Any]] = {
    "healthy_3node": {
        "description": "Healthy deterministic three-node federation steady state.",
        "node_count": 3,
        "expected": {"quorum_admit": True, "restricted_nodes": 0},
        "phases": [{"name": "steady_state", "inject": []}],
    },
    "quorum_failure": {
        "description": "Two peers become incompatible and high-impact quorum must fail.",
        "node_count": 3,
        "expected": {"quorum_admit": False},
        "phases": [
            {
                "name": "faults",
                "inject": [
                    {"node": "node-02", "type": "digest_mismatch"},
                    {"node": "node-03", "type": "epoch_mismatch"},
                ],
            }
        ],
    },
    "replay_storm": {
        "description": "Replay flood duplicates are injected and bounded suppression remains observable.",
        "node_count": 3,
        "expected": {"quorum_admit": True, "duplicate_events": 12},
        "phases": [{"name": "storm", "inject": [{"node": "all", "type": "replay_duplicate", "count": 4}]}],
    },
    "reanchor_continuation": {
        "description": "One node degrades audit trust then performs deterministic re-anchor continuation.",
        "node_count": 3,
        "expected": {"quorum_admit": True, "continuation_recognized": True},
        "phases": [
            {
                "name": "degrade_then_recover",
                "inject": [
                    {"node": "node-02", "type": "audit_chain_break"},
                    {"node": "node-02", "type": "reanchor"},
                ],
            }
        ],
    },
    "pressure_local_safety": {
        "description": "Governor pressure storm cannot crowd out local safety restrictions.",
        "node_count": 4,
        "expected": {"quorum_admit": False, "local_safety_dominant": True},
        "phases": [
            {
                "name": "pressure_and_safety",
                "inject": [
                    {"node": "node-01", "type": "governor_pressure", "level": "critical"},
                    {"node": "node-01", "type": "local_safety_override"},
                    {"node": "all", "type": "control_storm", "count": 5},
                ],
            }
        ],
    },
}


def load_federation_baseline_manifest() -> dict[str, Any]:
    payload = read_json(BASELINE_MANIFEST_PATH)
    return payload if payload else {}


def list_federation_scenarios() -> list[dict[str, object]]:
    return [
        {"name": name, "description": str(payload.get("description") or ""), "node_count": int(payload.get("node_count") or 0)}
        for name, payload in sorted(SCENARIOS.items())
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _seed_node(node_root: Path, *, node_id: str, seed: int) -> None:
    (node_root / "vow").mkdir(parents=True, exist_ok=True)
    write_json(node_root / "vow/immutable_manifest.json", {"schema_version": 1, "files": {}, "seed": seed, "node_id": node_id})
    (node_root / "vow/invariants.yaml").write_text("version: 1\n", encoding="utf-8")

    write_json(
        node_root / "glow/federation/governance_digest.json",
        {
            "schema_version": 1,
            "digest": f"digest-{seed}-{node_id}",
            "components": {"node_id": node_id, "seed": seed, "mode": "deterministic"},
        },
    )
    write_json(
        node_root / "glow/pulse_trust/epoch_state.json",
        {"schema_version": 1, "active_epoch_id": f"epoch-{seed}", "revoked_epochs": [], "compromise_response_mode": False},
    )
    write_json(
        node_root / "glow/federation/trust_ledger_state.json",
        {
            "schema_version": 1,
            "state_summary": {"trusted": 0, "degraded": 0, "restricted": 0},
            "peer_states": [],
        },
    )
    write_json(
        node_root / "glow/governor/rollup.json",
        {"schema_version": 1, "restriction_level": "none", "pressure_state": "normal", "local_safety_override": False},
    )


def _nodes_for_target(target: str, node_ids: list[str]) -> list[str]:
    if target == "all":
        return list(node_ids)
    if target in node_ids:
        return [target]
    return []


def _inject(node_root: Path, *, node_id: str, injection: dict[str, Any], seed: int) -> dict[str, object]:
    typ = str(injection.get("type") or "")
    record: dict[str, object] = {"node": node_id, "type": typ, "status": "applied"}

    if typ == "digest_mismatch":
        payload = read_json(node_root / "glow/federation/governance_digest.json")
        payload["digest"] = f"mismatch-{seed}-{node_id}"
        write_json(node_root / "glow/federation/governance_digest.json", payload)
    elif typ == "epoch_mismatch":
        payload = read_json(node_root / "glow/pulse_trust/epoch_state.json")
        payload["active_epoch_id"] = f"revoked-{seed}-{node_id}"
        payload["revoked_epochs"] = [f"epoch-{seed}"]
        write_json(node_root / "glow/pulse_trust/epoch_state.json", payload)
    elif typ == "replay_duplicate":
        count = max(1, _as_int(injection.get("count"), 1))
        base = {"schema_version": 1, "event_id": f"evt-{seed}-{node_id}", "kind": "federated_control", "result": "accepted"}
        for _ in range(count):
            append_jsonl(node_root / "pulse/replay_runs.jsonl", base)
        record["count"] = count
    elif typ == "audit_chain_break":
        write_json(node_root / "glow/runtime/audit_trust_state.json", {"schema_version": 1, "degraded_audit_trust": True, "history_state": "broken"})
    elif typ == "reanchor":
        write_json(node_root / "glow/forge/restoration/reanchor_status.json", {"schema_version": 1, "status": "continued", "reason": "simulation_reanchor"})
        write_json(node_root / "glow/runtime/audit_trust_state.json", {"schema_version": 1, "degraded_audit_trust": False, "history_state": "healthy_continuation"})
    elif typ == "governor_pressure":
        level = str(injection.get("level") or "high")
        write_json(node_root / "glow/governor/rollup.json", {"schema_version": 1, "restriction_level": "restricted", "pressure_state": level, "local_safety_override": False})
        record["level"] = level
    elif typ == "local_safety_override":
        payload = read_json(node_root / "glow/governor/rollup.json")
        payload["local_safety_override"] = True
        payload["restriction_level"] = "restricted"
        payload["restriction_cause"] = "local_safety"
        write_json(node_root / "glow/governor/rollup.json", payload)
    elif typ == "control_storm":
        count = max(1, _as_int(injection.get("count"), 1))
        for idx in range(count):
            append_jsonl(node_root / "glow/governor/observability.jsonl", {"schema_version": 1, "event": "federated_control", "event_id": f"storm-{seed}-{node_id}-{idx}"})
        record["count"] = count
    else:
        record["status"] = "ignored"
    return record


def run_federation_simulation(
    repo_root: Path,
    *,
    scenario_name: str,
    seed: int,
    node_count: int | None = None,
    emit_bundle: bool = False,
) -> dict[str, object]:
    root = repo_root.resolve()
    scenario = SCENARIOS.get(scenario_name)
    if scenario is None:
        return {"ok": False, "status": "failed", "error": f"unknown_scenario:{scenario_name}", "available": [item["name"] for item in list_federation_scenarios()], "exit_code": 2}

    resolved_nodes = max(1, int(node_count or int(scenario.get("node_count") or 1)))
    run_id = f"{scenario_name}_seed{seed}_nodes{resolved_nodes}"
    run_root = root / "glow/simulation" / run_id
    if run_root.exists():
        shutil.rmtree(run_root)
    (run_root / "nodes").mkdir(parents=True, exist_ok=True)

    node_ids = [f"node-{idx:02d}" for idx in range(1, resolved_nodes + 1)]
    bootstrap: list[dict[str, object]] = []
    for node_id in node_ids:
        node_root = run_root / "nodes" / node_id
        _seed_node(node_root, node_id=node_id, seed=seed)
        bootstrap.append(run_bootstrap(node_root, reason="simulation_bootstrap", seed_minimal=True, allow_restore=False))

    injections: list[dict[str, object]] = []
    for phase in _as_list(scenario.get("phases")):
        if not isinstance(phase, dict):
            continue
        for step in _as_list(phase.get("inject")):
            if not isinstance(step, dict):
                continue
            targets = _nodes_for_target(str(step.get("node") or ""), node_ids)
            for node_id in targets:
                node_root = run_root / "nodes" / node_id
                rec = _inject(node_root, node_id=node_id, injection=step, seed=seed)
                rec["phase"] = str(phase.get("name") or "")
                injections.append(rec)

    statuses: dict[str, dict[str, object]] = {}
    for node_id in node_ids:
        node_root = run_root / "nodes" / node_id
        snapshot = node_health(node_root)
        write_json(node_root / "glow/simulation/status_snapshot.json", snapshot)
        statuses[node_id] = snapshot

    mismatch_nodes = {item["node"] for item in injections if item.get("type") in {"digest_mismatch", "epoch_mismatch"}}
    local_safety = any(item.get("type") == "local_safety_override" for item in injections)
    quorum_required = max(2, resolved_nodes // 2 + 1)
    quorum_present = resolved_nodes - len(mismatch_nodes)
    quorum_admit = quorum_present >= quorum_required and not local_safety

    duplicate_events = sum(_as_int(item.get("count")) for item in injections if item.get("type") == "replay_duplicate")
    restricted_nodes = sum(1 for _node, payload in statuses.items() if str(payload.get("health_state")) == "restricted")
    continuation_recognized = any(read_json(run_root / "nodes" / node_id / "glow/runtime/audit_trust_state.json").get("history_state") == "healthy_continuation" for node_id in node_ids)

    expected = _as_dict(scenario.get("expected"))
    oracle_checks = {
        "quorum_admit": quorum_admit == expected.get("quorum_admit", quorum_admit),
        "restricted_nodes": restricted_nodes == expected.get("restricted_nodes", restricted_nodes),
        "duplicate_events": duplicate_events == expected.get("duplicate_events", duplicate_events),
        "continuation_recognized": continuation_recognized == expected.get("continuation_recognized", continuation_recognized),
        "local_safety_dominant": (not quorum_admit) == expected.get("local_safety_dominant", (not quorum_admit)) if local_safety else True,
    }

    injection_log = run_root / "event_injection_log.jsonl"
    injection_log.parent.mkdir(parents=True, exist_ok=True)
    injection_log.write_text("", encoding="utf-8")
    for record in injections:
        append_jsonl(injection_log, record)

    bundles: list[dict[str, object]] = []
    if emit_bundle:
        for node_id in node_ids:
            if node_id in mismatch_nodes or local_safety:
                bundles.append({"node": node_id, "bundle": build_incident_bundle(run_root / "nodes" / node_id, reason=f"simulation_{scenario_name}", window=25)})

    report: dict[str, object] = {
        "schema_version": 1,
        "run_id": run_id,
        "scenario": scenario_name,
        "description": scenario.get("description"),
        "seed": seed,
        "node_count": resolved_nodes,
        "created_at": f"seed:{seed}",
        "node_ids": node_ids,
        "bootstrap": bootstrap,
        "statuses": statuses,
        "quorum": {"required": quorum_required, "present": quorum_present, "admit": quorum_admit, "mismatch_nodes": sorted(str(node) for node in mismatch_nodes)},
        "oracle": {
            "expected": expected,
            "observed": {
                "quorum_admit": quorum_admit,
                "restricted_nodes": restricted_nodes,
                "duplicate_events": duplicate_events,
                "continuation_recognized": continuation_recognized,
                "local_safety_active": local_safety,
            },
            "checks": oracle_checks,
            "passed": all(oracle_checks.values()),
        },
        "artifact_paths": {
            "run_root": str(run_root.relative_to(root)),
            "injection_log": str(injection_log.relative_to(root)),
        },
        "injections": injections,
        "incident_bundles": bundles,
    }
    report_path = run_root / "scenario_report.json"
    write_json(report_path, report)

    manifest_files: list[dict[str, object]] = []
    for path in sorted(run_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        manifest_files.append({"path": str(rel), "sha256": _sha256(path), "size": path.stat().st_size})
    manifest = {"schema_version": 1, "run_id": run_id, "file_count": len(manifest_files), "files": manifest_files}
    write_json(run_root / "bundle_manifest.json", manifest)

    artifact_paths = _as_dict(report.get("artifact_paths"))
    artifact_paths["report_path"] = str(report_path.relative_to(root))
    artifact_paths["bundle_manifest"] = str((run_root / "bundle_manifest.json").relative_to(root))
    report["artifact_paths"] = artifact_paths
    oracle = _as_dict(report.get("oracle"))
    report["ok"] = bool(oracle.get("passed"))
    report["status"] = "passed" if bool(report.get("ok")) else "failed"
    report["exit_code"] = 0 if bool(report.get("ok")) else 1
    write_json(report_path, report)
    return report


def _artifact_expectations_met(run_root: Path, *, node_count: int, expectations: dict[str, Any]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for rel in _as_list(expectations.get("required_run_artifacts")):
        if not (run_root / str(rel)).is_file():
            missing.append(str(rel))
    node_rel = str(expectations.get("required_node_artifact") or "")
    if node_rel:
        for idx in range(1, node_count + 1):
            node_id = f"node-{idx:02d}"
            if not (run_root / "nodes" / node_id / node_rel).is_file():
                missing.append(f"nodes/{node_id}/{node_rel}")
    return (len(missing) == 0, missing)


def run_federation_baseline_suite(repo_root: Path, *, emit_bundle: bool = True) -> dict[str, object]:
    root = repo_root.resolve()
    manifest = load_federation_baseline_manifest()
    scenarios = _as_list(manifest.get("scenarios"))
    deterministic_seed = _as_int(manifest.get("deterministic_seed"), 7)

    suite_rows: list[dict[str, object]] = []
    gating_failures: list[str] = []

    for row in scenarios:
        if not isinstance(row, dict):
            continue
        scenario_name = str(row.get("name") or "")
        release_gating = bool(row.get("release_gating"))
        scenario_seed = _as_int(row.get("seed"), deterministic_seed)
        expected_oracle = _as_dict(row.get("expected_oracle"))
        artifact_expectations = _as_dict(row.get("artifact_expectations"))

        result = run_federation_simulation(root, scenario_name=scenario_name, seed=scenario_seed, emit_bundle=emit_bundle)
        run_rel = str(_as_dict(result.get("artifact_paths")).get("run_root") or "")
        run_root = root / run_rel if run_rel else root / "glow/simulation"
        artifact_ok, missing = _artifact_expectations_met(
            run_root,
            node_count=_as_int(result.get("node_count")),
            expectations=artifact_expectations,
        )

        observed_oracle = _as_dict(_as_dict(result.get("oracle")).get("observed"))
        oracle_expected_matches = {key: observed_oracle.get(key) == expected_oracle.get(key) for key in expected_oracle}
        oracle_expected_ok = all(oracle_expected_matches.values())
        scenario_ok = bool(result.get("ok")) and artifact_ok and oracle_expected_ok

        incident_bundles = _as_list(result.get("incident_bundles"))
        incident_bundle_for_failure: dict[str, object] | None = None
        if not scenario_ok and not incident_bundles:
            incident_bundle_for_failure = build_incident_bundle(
                run_root / "nodes" / "node-01",
                reason=f"simulation_baseline_gate_{scenario_name}",
                window=25,
            )

        if release_gating and not scenario_ok:
            gating_failures.append(scenario_name)

        suite_rows.append(
            {
                "scenario": scenario_name,
                "seed": scenario_seed,
                "release_gating": release_gating,
                "status": "passed" if scenario_ok else "failed",
                "oracle_passed": bool(result.get("ok")),
                "oracle_expected_matches": oracle_expected_matches,
                "artifact_expectations_passed": artifact_ok,
                "missing_artifacts": missing,
                "artifact_paths": result.get("artifact_paths"),
                "incident_bundle_for_failure": incident_bundle_for_failure,
            }
        )

    baseline_report = {
        "schema_version": 1,
        "suite": str(manifest.get("suite") or "federation_baseline"),
        "deterministic_seed": deterministic_seed,
        "manifest_path": "sentientos/simulation/federation_baseline_manifest.json",
        "scenarios": suite_rows,
        "gating_failures": gating_failures,
        "status": "passed" if not gating_failures else "failed",
        "ok": not gating_failures,
        "exit_code": 0 if not gating_failures else 1,
    }

    report_path = root / "glow/simulation/baseline_report.json"
    write_json(report_path, baseline_report)
    baseline_report["report_path"] = str(report_path.relative_to(root))
    return baseline_report


__all__ = [
    "BASELINE_MANIFEST_PATH",
    "SCENARIOS",
    "list_federation_scenarios",
    "load_federation_baseline_manifest",
    "run_federation_baseline_suite",
    "run_federation_simulation",
]
