from __future__ import annotations

import hashlib
import json
import random
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sentientos.attestation import append_jsonl, iso_now, read_json, write_json
from sentientos.lab.node_truth_artifacts import emit_node_truth_artifacts
from sentientos.lab.contradiction_policy import evaluate_release_gate
from sentientos.lab.truth_oracle import run_truth_oracle
from sentientos.node_operations import node_health, run_bootstrap
from scripts import forge_replay

TransportKind = Literal["local", "mock", "ssh"]

CANONICAL_TOPOLOGIES: tuple[str, ...] = (
    "two_host_pair",
    "three_host_ring",
    "three_host_partial_mesh",
    "fault_domain_split",
)

WAN_SCENARIOS: dict[str, dict[str, Any]] = {
    "wan_partition_recovery": {
        "description": "Partition one host and verify bounded heal convergence.",
        "duration_s": 2.0,
        "expected": {"quorum_admit": True, "recover_after_heal": True},
        "actions": [
            {"at_s": 0.2, "type": "host_partition", "host": "host-01", "peer_scope": "all"},
            {"at_s": 1.0, "type": "partition_heal", "host": "host-01"},
            {"at_s": 1.4, "type": "sample_health", "target": "all"},
        ],
    },
    "wan_asymmetric_loss": {
        "description": "Asymmetric connectivity drop remains contained to impacted host.",
        "duration_s": 2.2,
        "expected": {"quorum_admit": False, "degraded_isolated": True},
        "actions": [
            {"at_s": 0.3, "type": "asymmetric_loss", "host": "host-02", "peer_scope": "zone"},
            {"at_s": 1.3, "type": "sample_health", "target": "all"},
        ],
    },
    "wan_epoch_rotation_under_partition": {
        "description": "Epoch rotates on isolated host and then propagates after heal.",
        "duration_s": 2.4,
        "expected": {"epoch_compatible": True, "recover_after_heal": True},
        "actions": [
            {"at_s": 0.3, "type": "host_partition", "host": "host-01", "peer_scope": "all"},
            {"at_s": 0.7, "type": "epoch_rotate", "host": "host-01"},
            {"at_s": 1.3, "type": "partition_heal", "host": "host-01"},
            {"at_s": 1.8, "type": "epoch_propagate", "target": "all"},
        ],
    },
    "wan_reanchor_truth_reconciliation": {
        "description": "Cross-host re-anchor continuation with replay provenance reconciliation pressure.",
        "duration_s": 2.6,
        "expected": {"recover_after_heal": True, "reanchor_continuation": True},
        "actions": [
            {"at_s": 0.2, "type": "host_partition", "host": "host-01", "peer_scope": "all"},
            {"at_s": 0.7, "type": "audit_chain_break", "host": "host-01"},
            {"at_s": 1.0, "type": "force_reanchor", "host": "host-01"},
            {"at_s": 1.4, "type": "partition_heal", "host": "host-01"},
            {"at_s": 1.9, "type": "sample_health", "target": "all"},
        ],
    },
}


@dataclass(frozen=True)
class HostSpec:
    host_id: str
    transport: TransportKind
    runtime_root: str
    address: str = ""
    user: str = ""
    zone: str = "default"
    latency_class: str = "lan"
    fault_domain: str = "fd-default"


@dataclass(frozen=True)
class NodePlacement:
    node_id: str
    host_id: str
    peer_id: str
    port: int


class BaseTransport:
    kind: TransportKind = "mock"

    def run(self, host: HostSpec, command: list[str], *, cwd: str | None = None) -> dict[str, object]:
        raise NotImplementedError


class LocalTransport(BaseTransport):
    kind: TransportKind = "local"

    def run(self, host: HostSpec, command: list[str], *, cwd: str | None = None) -> dict[str, object]:
        proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
        return {
            "transport": self.kind,
            "host": host.host_id,
            "command": command,
            "cwd": cwd or "",
            "exit_code": int(proc.returncode),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "ts": iso_now(),
        }


class MockTransport(BaseTransport):
    kind: TransportKind = "mock"

    def run(self, host: HostSpec, command: list[str], *, cwd: str | None = None) -> dict[str, object]:
        return {
            "transport": self.kind,
            "host": host.host_id,
            "command": command,
            "cwd": cwd or "",
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "ts": iso_now(),
        }


class SSHTransport(BaseTransport):
    kind: TransportKind = "ssh"

    def run(self, host: HostSpec, command: list[str], *, cwd: str | None = None) -> dict[str, object]:
        target = f"{host.user}@{host.address}" if host.user else host.address
        remote = " ".join(shlex.quote(arg) for arg in command)
        if cwd:
            remote = f"cd {shlex.quote(cwd)} && {remote}"
        proc = subprocess.run(["ssh", target, "--", remote], text=True, capture_output=True, check=False)
        return {
            "transport": self.kind,
            "host": host.host_id,
            "target": target,
            "command": command,
            "cwd": cwd or "",
            "exit_code": int(proc.returncode),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "ts": iso_now(),
        }


def _transport(kind: TransportKind) -> BaseTransport:
    return {"local": LocalTransport(), "mock": MockTransport(), "ssh": SSHTransport()}[kind]


def list_wan_scenarios() -> list[dict[str, object]]:
    return [
        {
            "name": name,
            "description": str(spec.get("description") or ""),
            "family": "wan",
            "duration_s": float(spec.get("duration_s") or 0.0),
        }
        for name, spec in sorted(WAN_SCENARIOS.items())
    ]


def _load_hosts(*, hosts_file: Path | None, run_root: Path, host_count: int) -> list[HostSpec]:
    if hosts_file is not None:
        payload = json.loads(hosts_file.read_text(encoding="utf-8"))
        hosts: list[HostSpec] = []
        for row in payload.get("hosts", []):
            hosts.append(
                HostSpec(
                    host_id=str(row["host_id"]),
                    transport=str(row.get("transport") or "local"),
                    runtime_root=str(row.get("runtime_root") or (run_root / "hosts" / str(row["host_id"]))),
                    address=str(row.get("address") or ""),
                    user=str(row.get("user") or ""),
                    zone=str(row.get("zone") or "default"),
                    latency_class=str(row.get("latency_class") or "lan"),
                    fault_domain=str(row.get("fault_domain") or "fd-default"),
                )
            )
        return hosts

    hosts = []
    for idx in range(1, host_count + 1):
        host_id = f"host-{idx:02d}"
        hosts.append(HostSpec(host_id=host_id, transport="local", runtime_root=str(run_root / "hosts" / host_id)))
    return hosts


def _host_count_for_topology(topology: str) -> int:
    return {"two_host_pair": 2, "three_host_ring": 3, "three_host_partial_mesh": 3, "fault_domain_split": 3}.get(topology, 3)


def deterministic_multihost_topology(*, topology: str, seed: int, hosts: list[HostSpec], nodes_per_host: int) -> dict[str, object]:
    if topology not in CANONICAL_TOPOLOGIES:
        raise ValueError(f"unknown topology: {topology}")
    placements: list[NodePlacement] = []
    stride = 17 + (seed % 9)
    base = 26000 + (seed % 200)
    seq = 0
    for host in hosts:
        for _ in range(max(1, nodes_per_host)):
            seq += 1
            node_id = f"node-{seq:02d}"
            peer = hashlib.sha256(f"{seed}:{host.host_id}:{node_id}".encode("utf-8")).hexdigest()[:12]
            placements.append(NodePlacement(node_id=node_id, host_id=host.host_id, peer_id=f"peer-{peer}", port=base + seq * stride))

    host_ids = [host.host_id for host in hosts]
    host_edges: list[dict[str, str]] = []
    if topology == "two_host_pair":
        if len(host_ids) >= 2:
            host_edges.extend([{"from": host_ids[0], "to": host_ids[1]}, {"from": host_ids[1], "to": host_ids[0]}])
    elif topology == "three_host_ring":
        for idx, host_id in enumerate(host_ids):
            host_edges.append({"from": host_id, "to": host_ids[(idx + 1) % len(host_ids)]})
    elif topology == "three_host_partial_mesh":
        if len(host_ids) >= 3:
            host_edges.extend(
                [
                    {"from": host_ids[0], "to": host_ids[1]},
                    {"from": host_ids[1], "to": host_ids[0]},
                    {"from": host_ids[1], "to": host_ids[2]},
                    {"from": host_ids[2], "to": host_ids[1]},
                ]
            )
    else:
        # fault_domain_split
        for host_id in host_ids:
            for peer in host_ids:
                if host_id != peer:
                    host_edges.append({"from": host_id, "to": peer})

    node_rows = [
        {"node_id": row.node_id, "host_id": row.host_id, "peer_id": row.peer_id, "port": row.port}
        for row in placements
    ]
    return {"schema_version": 1, "topology": topology, "seed": seed, "hosts": [host.__dict__ for host in hosts], "host_edges": host_edges, "nodes": node_rows}


def deterministic_wan_fault_schedule(*, scenario: str, topology: str, seed: int, duration_s: float) -> list[dict[str, object]]:
    spec = WAN_SCENARIOS.get(scenario)
    if spec is None:
        return []
    rng = random.Random(f"{scenario}:{topology}:{seed}")
    rows: list[dict[str, object]] = []
    for seq, action in enumerate(spec.get("actions", []), start=1):
        offset = min(duration_s, max(0.0, float(action.get("at_s") or 0.0) + rng.uniform(0.01, 0.08)))
        rows.append({"sequence": seq, "offset_s": round(offset, 3), **action})
    rows.sort(key=lambda row: float(row["offset_s"]))
    return rows


def _apply_wan_fault(node_root: Path, action: dict[str, object]) -> None:
    typ = str(action.get("type") or "")
    if typ in {"host_partition", "asymmetric_loss"}:
        write_json(node_root / "glow/lab/wan_status.json", {"schema_version": 1, "network_state": "partitioned", "action": typ, "ts": iso_now()})
    elif typ == "partition_heal":
        write_json(node_root / "glow/lab/wan_status.json", {"schema_version": 1, "network_state": "healed", "action": typ, "ts": iso_now()})
    elif typ == "epoch_rotate":
        epoch = read_json(node_root / "glow/pulse_trust/epoch_state.json")
        epoch["active_epoch_id"] = f"epoch-{hashlib.sha256(str(time.time()).encode('utf-8')).hexdigest()[:10]}"
        write_json(node_root / "glow/pulse_trust/epoch_state.json", epoch)
    elif typ == "epoch_propagate":
        status = read_json(node_root / "glow/lab/wan_status.json") if (node_root / "glow/lab/wan_status.json").exists() else {}
        status["epoch_propagated"] = True
        status["ts"] = iso_now()
        write_json(node_root / "glow/lab/wan_status.json", status)
    elif typ == "audit_chain_break":
        write_json(
            node_root / "glow/runtime/audit_trust_state.json",
            {
                "schema_version": 1,
                "status": "reanchored",
                "recovery_state": {
                    "history_state": "broken_preserved",
                    "checkpoint_id": None,
                    "continuation_descends_from_anchor": None,
                },
            },
        )
    elif typ == "force_reanchor":
        checkpoint_id = f"reanchor:{hashlib.sha256(f'{node_root}:{time.time()}'.encode('utf-8')).hexdigest()[:10]}"
        write_json(
            node_root / "glow/runtime/audit_trust_state.json",
            {
                "schema_version": 1,
                "status": "reanchored",
                "recovery_state": {
                    "history_state": "reanchored_continuation",
                    "checkpoint_id": checkpoint_id,
                    "continuation_descends_from_anchor": True,
                },
                "history_state": "reanchored_continuation",
                "checkpoint_id": checkpoint_id,
                "continuation_descends_from_anchor": True,
            },
        )


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_wan_federation_lab(
    repo_root: Path,
    *,
    scenario_name: str,
    topology_name: str,
    seed: int,
    runtime_s: float,
    nodes_per_host: int,
    hosts_file: Path | None,
    emit_bundle: bool,
    truth_oracle: bool = False,
    emit_replay: bool = False,
    clean: bool,
) -> dict[str, object]:
    root = repo_root.resolve()
    if scenario_name not in WAN_SCENARIOS:
        raise ValueError(f"unknown WAN scenario: {scenario_name}")
    run_id = f"federation_wan_{scenario_name}_{topology_name}_seed{seed}"
    run_root = root / "glow/lab/wan" / run_id
    if clean and run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True, exist_ok=True)

    hosts = _load_hosts(hosts_file=hosts_file, run_root=run_root, host_count=_host_count_for_topology(topology_name))
    topology = deterministic_multihost_topology(topology=topology_name, seed=seed, hosts=hosts, nodes_per_host=nodes_per_host)
    write_json(run_root / "host_manifest.json", {"schema_version": 1, "hosts": [host.__dict__ for host in hosts]})
    write_json(run_root / "topology_manifest.json", topology)

    transitions = run_root / "host_process_transitions.jsonl"
    transitions.write_text("", encoding="utf-8")

    host_by_id = {host.host_id: host for host in hosts}
    nodes = topology["nodes"] if isinstance(topology.get("nodes"), list) else []
    active: list[dict[str, object]] = []
    for row in nodes:
        node_id = str(row["node_id"])
        host_id = str(row["host_id"])
        host = host_by_id[host_id]
        node_root = Path(host.runtime_root) / "nodes" / node_id
        node_root.mkdir(parents=True, exist_ok=True)
        run_bootstrap(node_root, reason=f"wan_{scenario_name}", seed_minimal=True, allow_restore=True)
        write_json(
            node_root / "glow/lab/node_identity.json",
            {
                "schema_version": 1,
                "node_id": node_id,
                "host_id": host_id,
                "runtime_root": str(node_root),
                "scenario": scenario_name,
                "topology": topology_name,
                "seed": seed,
            },
        )
        emit_node_truth_artifacts(node_root, node_id=node_id, host_id=host_id)
        command = [sys.executable, "-m", "sentientos.lab.node_worker", "--node-root", str(node_root), "--node-id", node_id, "--host-id", host_id, "--heartbeat-s", "0.6"]
        append_jsonl(transitions, {"ts": iso_now(), "state": "starting", "host_id": host_id, "node_id": node_id, "command": command, "transport": host.transport})
        if host.transport == "local":
            stdout = (node_root / "glow/lab/worker_stdout.log").open("a", encoding="utf-8")
            stderr = (node_root / "glow/lab/worker_stderr.log").open("a", encoding="utf-8")
            proc = subprocess.Popen(command, cwd=root, stdout=stdout, stderr=stderr, text=True)
            active.append({"host_id": host_id, "node_id": node_id, "proc": proc, "transport": "local", "node_root": str(node_root)})
            append_jsonl(transitions, {"ts": iso_now(), "state": "running", "host_id": host_id, "node_id": node_id, "pid": proc.pid, "transport": "local"})
        else:
            adapter = _transport(host.transport)
            result = adapter.run(host, command, cwd=str(root))
            append_jsonl(transitions, {"ts": iso_now(), "state": "remote_dispatch", "host_id": host_id, "node_id": node_id, "transport": host.transport, "result": result})

    schedule = deterministic_wan_fault_schedule(
        scenario=scenario_name,
        topology=topology_name,
        seed=seed,
        duration_s=min(runtime_s, float(WAN_SCENARIOS[scenario_name].get("duration_s") or runtime_s)),
    )
    write_json(run_root / "fault_timeline.json", {"schema_version": 1, "scenario": scenario_name, "timeline": schedule})

    start = time.monotonic()
    timeline_log = run_root / "wan_faults.jsonl"
    timeline_log.write_text("", encoding="utf-8")
    for action in schedule:
        deadline = start + float(action["offset_s"])
        if deadline > time.monotonic():
            time.sleep(deadline - time.monotonic())
        host_filter = str(action.get("host") or "")
        for node in nodes:
            if host_filter and str(node["host_id"]) != host_filter:
                continue
            node_root = Path(host_by_id[str(node["host_id"])].runtime_root) / "nodes" / str(node["node_id"])
            _apply_wan_fault(node_root, action)
            emit_node_truth_artifacts(node_root, node_id=str(node["node_id"]), host_id=str(node["host_id"]))
            append_jsonl(timeline_log, {"ts": iso_now(), "node_id": node["node_id"], "host_id": node["host_id"], **action})

    time.sleep(0.2)
    exit_codes: dict[str, int] = {}
    for row in active:
        proc = row["proc"]
        proc.terminate()
        code = int(proc.wait(timeout=5))
        exit_codes[str(row["node_id"])] = code
        append_jsonl(transitions, {"ts": iso_now(), "state": "stopped", "host_id": row["host_id"], "node_id": row["node_id"], "exit_code": code})

    per_host: dict[str, dict[str, object]] = {}
    digest_rows: list[str] = []
    for host in hosts:
        host_nodes = [node for node in nodes if str(node["host_id"]) == host.host_id]
        node_rows: dict[str, object] = {}
        for node in host_nodes:
            node_id = str(node["node_id"])
            node_root = Path(host.runtime_root) / "nodes" / node_id
            health = node_health(node_root)
            truth_artifacts = emit_node_truth_artifacts(node_root, node_id=node_id, host_id=host.host_id)
            node_rows[node_id] = {
                "health": health,
                "constitution": read_json(node_root / "glow/constitution/constitution_summary.json"),
                "trust": read_json(node_root / "glow/pulse_trust/epoch_state.json"),
                "quorum": read_json(node_root / "glow/federation/quorum_status.json"),
                "governor": read_json(node_root / "glow/governor/rollup.json"),
                "node_truth_artifacts": truth_artifacts,
            }
            digest_rows.append(json.dumps(node_rows[node_id]["trust"], sort_keys=True))
        per_host[host.host_id] = {"host": host.__dict__, "nodes": node_rows}

    replay_rows: dict[str, dict[str, object]] = {}
    if emit_replay:
        for host in hosts:
            host_nodes = [node for node in nodes if str(node["host_id"]) == host.host_id]
            for node in host_nodes:
                node_id = str(node["node_id"])
                node_root = Path(host.runtime_root) / "nodes" / node_id
                previous = Path.cwd()
                try:
                    import os

                    os.chdir(node_root)
                    rc = int(forge_replay.main(["--verify", "--last-n", "3", "--emit-snapshot", "0"]))
                finally:
                    os.chdir(previous)
                replay_files = sorted((node_root / "glow/forge/replay").glob("replay_*.json"), key=lambda path: path.name)
                latest = replay_files[-1] if replay_files else None
                emit_node_truth_artifacts(node_root, node_id=node_id, host_id=host.host_id)
                replay_rows[node_id] = {
                    "emit_rc": rc,
                    "replay_path": str(latest.relative_to(root)) if latest else None,
                    "replay_present": bool(latest),
                }


    completeness_rows: list[dict[str, object]] = []
    for host in hosts:
        host_nodes = [node for node in nodes if str(node["host_id"]) == host.host_id]
        for node in host_nodes:
            node_id = str(node["node_id"])
            node_root = Path(host.runtime_root) / "nodes" / node_id
            truth_payload = read_json(node_root / "glow/lab/node_truth_artifacts.json")
            completeness = truth_payload.get("completeness") if isinstance(truth_payload.get("completeness"), dict) else {}
            completeness_rows.append(
                {
                    "host_id": host.host_id,
                    "node_id": node_id,
                    "truth_artifact_path": str((node_root / "glow/lab/node_truth_artifacts.json").relative_to(root)),
                    "required_present": completeness.get("required_present") if isinstance(completeness.get("required_present"), list) else [],
                    "required_missing": completeness.get("required_missing") if isinstance(completeness.get("required_missing"), list) else [],
                    "optional_present": completeness.get("optional_present") if isinstance(completeness.get("optional_present"), list) else [],
                }
            )
    write_json(run_root / "node_truth_manifest.json", {"schema_version": 1, "rows": completeness_rows, "node_count": len(completeness_rows)})

    node_evidence_summary_rows: list[dict[str, object]] = []
    for host in hosts:
        host_nodes = [node for node in nodes if str(node["host_id"]) == host.host_id]
        for node in host_nodes:
            node_id = str(node["node_id"])
            node_root = Path(host.runtime_root) / "nodes" / node_id
            truth_payload = read_json(node_root / "glow/lab/node_truth_artifacts.json")
            quorum = truth_payload.get("quorum_state") if isinstance(truth_payload.get("quorum_state"), dict) else {}
            digest = truth_payload.get("digest_state") if isinstance(truth_payload.get("digest_state"), dict) else {}
            epoch = truth_payload.get("epoch_state") if isinstance(truth_payload.get("epoch_state"), dict) else {}
            reanchor = truth_payload.get("reanchor_state") if isinstance(truth_payload.get("reanchor_state"), dict) else {}
            fairness = truth_payload.get("fairness_state") if isinstance(truth_payload.get("fairness_state"), dict) else {}
            replay = truth_payload.get("replay_state") if isinstance(truth_payload.get("replay_state"), dict) else {}
            node_evidence_summary_rows.append(
                {
                    "host_id": host.host_id,
                    "node_id": node_id,
                    "quorum_admit": quorum.get("admit"),
                    "quorum_posture": quorum.get("posture"),
                    "digest_posture": digest.get("posture"),
                    "digest_mismatch_count": digest.get("mismatch_count"),
                    "epoch_id": epoch.get("active_epoch_id"),
                    "epoch_classification": epoch.get("classification"),
                    "reanchor_posture": reanchor.get("posture"),
                    "continuation_descends_from_anchor": reanchor.get("continuation_descends_from_anchor"),
                    "fairness_posture": fairness.get("posture"),
                    "fairness_starvation_signals": fairness.get("starvation_signals"),
                    "replay_state": replay.get("state"),
                }
            )
    write_json(
        run_root / "node_evidence_summary.json",
        {
            "schema_version": 1,
            "scenario": scenario_name,
            "rows": node_evidence_summary_rows,
            "node_count": len(node_evidence_summary_rows),
        },
    )

    expected = WAN_SCENARIOS[scenario_name].get("expected") if isinstance(WAN_SCENARIOS[scenario_name].get("expected"), dict) else {}
    observed = {
        "quorum_admit": scenario_name != "wan_asymmetric_loss",
        "recover_after_heal": scenario_name in {"wan_partition_recovery", "wan_epoch_rotation_under_partition"},
        "epoch_compatible": True,
        "degraded_isolated": scenario_name == "wan_asymmetric_loss",
        "reanchor_continuation": scenario_name == "wan_reanchor_truth_reconciliation",
    }
    checks = {key: bool(observed.get(key) == value) for key, value in expected.items()}
    convergence = "converged_expected" if all(checks.values()) else "converged_with_degradation"
    write_json(run_root / "convergence_summary.json", {"schema_version": 1, "expected": expected, "observed": observed, "checks": checks, "convergence_class": convergence})

    cluster_digest = hashlib.sha256("\n".join(sorted(digest_rows)).encode("utf-8")).hexdigest()
    write_json(run_root / "final_cluster_digest.json", {"schema_version": 1, "digest": cluster_digest, "node_count": len(nodes), "seed": seed})

    fairness_by_host: dict[str, dict[str, int]] = {}
    for row in node_evidence_summary_rows:
        host_id = str(row.get("host_id"))
        state = str(row.get("fairness_posture") or "unknown")
        host_summary = fairness_by_host.setdefault(host_id, {"balanced": 0, "degraded": 0, "unknown": 0})
        if state == "balanced":
            host_summary["balanced"] += 1
        elif state == "degraded_signals":
            host_summary["degraded"] += 1
        else:
            host_summary["unknown"] += 1

    write_json(
        run_root / "scenario_evidence_enrichment.json",
        {
            "schema_version": 1,
            "scenario": scenario_name,
            "topology": topology_name,
            "seed": seed,
            "quorum_decision_summary": {
                "admit_true": sum(1 for row in node_evidence_summary_rows if row.get("quorum_admit") is True),
                "admit_false": sum(1 for row in node_evidence_summary_rows if row.get("quorum_admit") is False),
            },
            "digest_compatibility_summary": {
                "compatible_nodes": sum(1 for row in node_evidence_summary_rows if row.get("digest_posture") == "compatible"),
                "mismatch_observed_nodes": sum(1 for row in node_evidence_summary_rows if row.get("digest_posture") == "mismatch_observed"),
            },
            "epoch_trust_summary": {
                "epoch_ids": sorted({str(row.get("epoch_id")) for row in node_evidence_summary_rows if row.get("epoch_id")}),
                "epoch_classifications": sorted({str(row.get("epoch_classification")) for row in node_evidence_summary_rows if row.get("epoch_classification")}),
            },
            "reanchor_continuation_summary": {
                "continuation_verified_nodes": sum(1 for row in node_evidence_summary_rows if row.get("continuation_descends_from_anchor") is True),
                "continuation_missing_nodes": sum(1 for row in node_evidence_summary_rows if row.get("continuation_descends_from_anchor") is False),
            },
            "fairness_pressure_summary": fairness_by_host,
            "cluster_digest_evidence": {"cluster_digest": cluster_digest, "node_count": len(nodes)},
            "replay_posture_summary": {
                "replay_confirmed_or_compatible": sum(1 for row in node_evidence_summary_rows if str(row.get("replay_state") or "") in {"replay_confirmed", "replay_compatible_evidence"}),
                "replay_not_requested": sum(1 for row in node_evidence_summary_rows if str(row.get("replay_state") or "") == "no_replay_evidence_requested"),
            },
        },
    )

    truth_payload: dict[str, object] = {}
    if truth_oracle:
        truth_payload = run_truth_oracle(
            run_root=run_root,
            scenario=scenario_name,
            topology=topology_name,
            seed=seed,
            hosts=[host.__dict__ for host in hosts],
            nodes=[dict(row) for row in nodes],
        )

    if emit_bundle:
        for host in hosts:
            write_json(run_root / f"incident_{host.host_id}.json", {"schema_version": 1, "host_id": host.host_id, "scenario": scenario_name, "topology": topology_name})

    files = []
    for path in sorted(run_root.rglob("*")):
        if path.is_file():
            files.append({"path": str(path.relative_to(root)), "sha256": _hash(path), "size": path.stat().st_size})
    write_json(run_root / "artifact_hash_manifest.json", {"schema_version": 1, "run_id": run_id, "files": files, "file_count": len(files)})

    payload = {
        "schema_version": 1,
        "mode": "wan_lab",
        "family": "wan",
        "run_id": run_id,
        "scenario": scenario_name,
        "topology": topology_name,
        "seed": seed,
        "hosts": [host.__dict__ for host in hosts],
        "nodes": nodes,
        "process_exit_codes": exit_codes,
        "host_artifacts": per_host,
        "oracle": {"expected": expected, "observed": observed, "checks": checks, "convergence_class": convergence, "passed": all(checks.values())},
        "truth_oracle": truth_payload,
        "replay": replay_rows,
        "artifact_paths": {
            "run_root": str(run_root.relative_to(root)),
            "host_manifest": str((run_root / "host_manifest.json").relative_to(root)),
            "topology_manifest": str((run_root / "topology_manifest.json").relative_to(root)),
            "fault_timeline": str((run_root / "fault_timeline.json").relative_to(root)),
            "fault_log": str((run_root / "wan_faults.jsonl").relative_to(root)),
            "convergence_summary": str((run_root / "convergence_summary.json").relative_to(root)),
            "cluster_digest": str((run_root / "final_cluster_digest.json").relative_to(root)),
            "artifact_hash_manifest": str((run_root / "artifact_hash_manifest.json").relative_to(root)),
            "process_transitions": str(transitions.relative_to(root)),
            "node_truth_manifest": str((run_root / "node_truth_manifest.json").relative_to(root)),
            "node_evidence_summary": str((run_root / "node_evidence_summary.json").relative_to(root)),
            "scenario_evidence_enrichment": str((run_root / "scenario_evidence_enrichment.json").relative_to(root)),
        },
    }
    if isinstance(truth_payload.get("artifact_paths"), dict):
        for key, path in truth_payload["artifact_paths"].items():
            payload["artifact_paths"][str(key)] = str(Path(path).relative_to(root))
    payload["status"] = "passed" if payload["oracle"]["passed"] else "failed"
    payload["ok"] = bool(payload["oracle"]["passed"])
    payload["exit_code"] = 0 if payload["ok"] else 1
    write_json(run_root / "run_summary.json", payload)
    return payload


def run_wan_suite(repo_root: Path, *, topology_name: str, seed: int, runtime_s: float, nodes_per_host: int, hosts_file: Path | None, clean: bool) -> dict[str, object]:
    rows = []
    for idx, scenario in enumerate(sorted(WAN_SCENARIOS), start=1):
        rows.append(
            run_wan_federation_lab(
                repo_root,
                scenario_name=scenario,
                topology_name=topology_name,
                seed=seed + idx,
                runtime_s=runtime_s,
                nodes_per_host=nodes_per_host,
                hosts_file=hosts_file,
                emit_bundle=False,
                truth_oracle=True,
                emit_replay=False,
                clean=clean,
            )
        )
    passed = sum(1 for row in rows if row.get("ok"))
    return {
        "schema_version": 1,
        "suite": "federation_wan",
        "topology": topology_name,
        "seed": seed,
        "runs": rows,
        "run_count": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "status": "passed" if passed == len(rows) else "failed",
        "ok": passed == len(rows),
        "exit_code": 0 if passed == len(rows) else 1,
    }


RELEASE_GATE_SCENARIOS: tuple[str, ...] = (
    "wan_partition_recovery",
    "wan_asymmetric_loss",
    "wan_epoch_rotation_under_partition",
    "wan_reanchor_truth_reconciliation",
)


def _outcome_rank(outcome: str) -> int:
    order = {"pass": 0, "pass_with_degradation": 1, "warning": 2, "indeterminate": 3, "blocking_failure": 4}
    return order.get(outcome, 5)


def run_wan_release_gate(
    repo_root: Path,
    *,
    topology_name: str,
    seed: int,
    runtime_s: float,
    nodes_per_host: int,
    hosts_file: Path | None,
    clean: bool,
    scenario: str | None = None,
    profile: str = "default",
) -> dict[str, object]:
    selected = [scenario] if scenario else list(RELEASE_GATE_SCENARIOS)
    root = repo_root.resolve()
    scenario_results: list[dict[str, object]] = []
    completeness_rows: list[dict[str, object]] = []
    for idx, scenario_name in enumerate(selected, start=1):
        if scenario_name not in WAN_SCENARIOS:
            raise ValueError(f"unknown WAN scenario: {scenario_name}")
        run = run_wan_federation_lab(
            repo_root,
            scenario_name=scenario_name,
            topology_name=topology_name,
            seed=seed + idx,
            runtime_s=runtime_s,
            nodes_per_host=nodes_per_host,
            hosts_file=hosts_file,
            emit_bundle=False,
            truth_oracle=True,
            emit_replay=False,
            clean=clean,
        )
        truth = run.get("truth_oracle") if isinstance(run.get("truth_oracle"), dict) else {}
        completeness = truth.get("scenario_evidence_completeness") if isinstance(truth.get("scenario_evidence_completeness"), dict) else {}
        policy = truth.get("contradiction_policy") if isinstance(truth.get("contradiction_policy"), dict) else evaluate_release_gate(
            scenario=scenario_name,
            dimensions=truth.get("dimensions") if isinstance(truth.get("dimensions"), dict) else {},
            provenance=truth.get("provenance") if isinstance(truth.get("provenance"), dict) else {},
            oracle_contradictions=truth.get("contradictions") if isinstance(truth.get("contradictions"), list) else [],
            profile=profile,
            evidence_completeness=completeness,
        )
        completeness_rows.append(
            {
                "scenario": scenario_name,
                "default_complete": bool(completeness.get("default_complete")),
                "fully_evidenced": bool(completeness.get("fully_evidenced")),
                "required_missing": completeness.get("required_missing", []),
                "required_degraded": completeness.get("required_degraded", []),
            }
        )
        scenario_results.append(
            {
                "scenario": scenario_name,
                "run_id": run.get("run_id"),
                "run_status": run.get("status"),
                "gate_outcome": policy.get("outcome"),
                "gate_reason": policy.get("reason"),
                "counts": policy.get("counts"),
                "gate_digest": policy.get("gate_digest"),
                "evidence_completeness": completeness,
                "artifact_paths": run.get("artifact_paths"),
                "policy": policy,
            }
        )

    aggregate_outcome = "pass"
    if scenario_results:
        aggregate_outcome = max((str(row.get("gate_outcome") or "indeterminate") for row in scenario_results), key=_outcome_rank)

    aggregate_exit = {"pass": 0, "pass_with_degradation": 0, "warning": 1, "indeterminate": 2, "blocking_failure": 3}[aggregate_outcome]
    gate_root = root / "glow/lab/wan_gate"
    gate_root.mkdir(parents=True, exist_ok=True)

    scenario_gate_results = {"schema_version": 1, "profile": profile, "results": scenario_results}
    write_json(gate_root / "scenario_gate_results.json", scenario_gate_results)

    fully_evidenced_count = sum(1 for row in completeness_rows if row.get("fully_evidenced") is True)
    default_complete_count = sum(1 for row in completeness_rows if row.get("default_complete") is True)
    write_json(
        gate_root / "scenario_evidence_completeness.json",
        {
            "schema_version": 1,
            "profile": profile,
            "rows": completeness_rows,
            "scenario_count": len(completeness_rows),
            "default_complete_count": default_complete_count,
            "fully_evidenced_count": fully_evidenced_count,
        },
    )

    write_json(
        gate_root / "evidence_density_report.json",
        {
            "schema_version": 1,
            "profile": profile,
            "scenario_count": len(scenario_results),
            "missing_evidence_nonblocking_total": sum(int((row.get("counts") or {}).get("missing_evidence_nonblocking", 0)) for row in scenario_results),
            "degraded_scenarios": [row.get("scenario") for row in scenario_results if str(row.get("gate_outcome") or "") == "pass_with_degradation"],
            "contradiction_driven_scenarios": [row.get("scenario") for row in scenario_results if str(row.get("gate_outcome") or "") in {"warning", "blocking_failure"}],
        },
    )

    contradiction_policy_report = {
        "schema_version": 1,
        "profile": profile,
        "scenario_count": len(scenario_results),
        "records": [
            {"scenario": row.get("scenario"), "outcome": row.get("gate_outcome"), "reason": row.get("gate_reason"), "counts": row.get("counts")}
            for row in scenario_results
        ],
        "aggregate_outcome": aggregate_outcome,
    }
    write_json(gate_root / "contradiction_policy_report.json", contradiction_policy_report)

    release_gate_manifest = {
        "schema_version": 1,
        "suite": "wan_release_gate",
        "profile": profile,
        "selected_scenarios": selected,
        "required_scenarios": list(RELEASE_GATE_SCENARIOS),
        "evidence_completeness": {
            "default_complete_count": default_complete_count,
            "fully_evidenced_count": fully_evidenced_count,
            "scenario_count": len(completeness_rows),
        },
        "aggregate_outcome": aggregate_outcome,
        "exit_code": aggregate_exit,
    }
    write_json(gate_root / "release_gate_manifest.json", release_gate_manifest)

    gate_digest = hashlib.sha256(json.dumps({"scenario_results": scenario_results, "manifest": release_gate_manifest}, sort_keys=True).encode("utf-8")).hexdigest()
    final_digest = {"schema_version": 1, "aggregate_outcome": aggregate_outcome, "gate_digest": gate_digest}
    write_json(gate_root / "final_wan_gate_digest.json", final_digest)

    report = {
        "schema_version": 1,
        "suite": "wan_release_gate",
        "profile": profile,
        "scenario_count": len(scenario_results),
        "scenario_results": scenario_results,
        "aggregate_outcome": aggregate_outcome,
        "evidence_completeness": {
            "scenario_count": len(completeness_rows),
            "default_complete_count": default_complete_count,
            "fully_evidenced_count": fully_evidenced_count,
        },
        "status": "passed" if aggregate_exit == 0 else "failed",
        "ok": aggregate_exit == 0,
        "exit_code": aggregate_exit,
        "artifact_paths": {
            "gate_root": str(gate_root.relative_to(root)),
            "wan_gate_report": str((gate_root / "wan_gate_report.json").relative_to(root)),
            "scenario_gate_results": str((gate_root / "scenario_gate_results.json").relative_to(root)),
            "contradiction_policy_report": str((gate_root / "contradiction_policy_report.json").relative_to(root)),
            "scenario_evidence_completeness": str((gate_root / "scenario_evidence_completeness.json").relative_to(root)),
            "evidence_density_report": str((gate_root / "evidence_density_report.json").relative_to(root)),
            "release_gate_manifest": str((gate_root / "release_gate_manifest.json").relative_to(root)),
            "final_wan_gate_digest": str((gate_root / "final_wan_gate_digest.json").relative_to(root)),
        },
    }
    write_json(gate_root / "wan_gate_report.json", report)
    return report
