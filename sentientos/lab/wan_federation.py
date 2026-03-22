from __future__ import annotations

import hashlib
import json
import os
import random
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, cast

import yaml

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

REMOTE_SMOKE_SCENARIOS: dict[str, str] = {
    "remote_partition_recovery_smoke": "wan_partition_recovery",
    "remote_epoch_rotation_smoke": "wan_epoch_rotation_under_partition",
    "remote_reanchor_truth_smoke": "wan_reanchor_truth_reconciliation",
}

REMOTE_PREFLIGHT_HISTORY_LIMIT = 400


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
    tags: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()


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

    def build_ssh_command(self, host: HostSpec, command: list[str], *, cwd: str | None = None) -> list[str]:
        target = f"{host.user}@{host.address}" if host.user else host.address
        remote = " ".join(shlex.quote(arg) for arg in command)
        if cwd:
            remote = f"cd {shlex.quote(cwd)} && {remote}"
        return ["ssh", target, "--", remote]

    def run(self, host: HostSpec, command: list[str], *, cwd: str | None = None) -> dict[str, object]:
        target = f"{host.user}@{host.address}" if host.user else host.address
        proc = subprocess.run(self.build_ssh_command(host, command, cwd=cwd), text=True, capture_output=True, check=False)
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


def _as_transport(value: object) -> TransportKind:
    text = str(value or "local")
    return cast(TransportKind, text if text in {"local", "mock", "ssh"} else "local")


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _as_rows(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _to_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _to_float(value: object, *, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


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
        suffix = hosts_file.suffix.lower()
        payload = (
            yaml.safe_load(hosts_file.read_text(encoding="utf-8"))
            if suffix in {".yaml", ".yml"}
            else json.loads(hosts_file.read_text(encoding="utf-8"))
        )
        if not isinstance(payload, dict):
            raise ValueError("host inventory payload must be a mapping with hosts")
        hosts: list[HostSpec] = []
        for row in payload.get("hosts", []):
            if not isinstance(row, dict):
                raise ValueError("host inventory rows must be mappings")
            hosts.append(
                HostSpec(
                    host_id=str(row["host_id"]),
                    transport=_as_transport(row.get("transport")),
                    runtime_root=str(row.get("runtime_root") or (run_root / "hosts" / str(row["host_id"]))),
                    address=str(row.get("address") or ""),
                    user=str(row.get("user") or ""),
                    zone=str(row.get("zone") or "default"),
                    latency_class=str(row.get("latency_class") or "lan"),
                    fault_domain=str(row.get("fault_domain") or "fd-default"),
                    tags=tuple(sorted(str(item) for item in (row.get("tags") or []) if str(item))),
                    capabilities=tuple(sorted(str(item) for item in (row.get("capabilities") or []) if str(item))),
                )
            )
        deduped = sorted(hosts, key=lambda host: host.host_id)
        ids = [host.host_id for host in deduped]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate host_id values in host inventory")
        return deduped

    hosts = []
    for idx in range(1, host_count + 1):
        host_id = f"host-{idx:02d}"
        hosts.append(HostSpec(host_id=host_id, transport="local", runtime_root=str(run_root / "hosts" / host_id)))
    return hosts


def _scenario_for_remote_smoke(scenario_name: str) -> str:
    return REMOTE_SMOKE_SCENARIOS.get(scenario_name, scenario_name)


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
        offset = min(duration_s, max(0.0, _to_float(action.get("at_s"), default=0.0) + rng.uniform(0.01, 0.08)))
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



def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)

def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _classify_ssh_step(step: dict[str, object]) -> str:
    exit_code = _to_int(step.get("exit_code"), default=1)
    stderr = str(step.get("stderr") or "").lower()
    if exit_code == 0:
        return "ok"
    if "permission denied" in stderr or "authentication" in stderr:
        return "transport_auth_failure"
    if "no route to host" in stderr or "name or service not known" in stderr or "could not resolve" in stderr:
        return "host_unreachable"
    if "connection refused" in stderr or "connection timed out" in stderr:
        return "transport_auth_failure"
    if "not found" in stderr:
        return "command_availability_failure"
    return "transport_failure"


def classify_remote_preflight(*, check: dict[str, object], mkdir: dict[str, object], cleanup_failures: int = 0) -> tuple[str, list[str]]:
    check_class = _classify_ssh_step(check)
    mkdir_class = _classify_ssh_step(mkdir)
    classes: list[str] = []
    if check_class != "ok":
        classes.append(check_class)
    elif _to_int(check.get("exit_code"), default=1) != 0:
        classes.append("command_availability_failure")
    if mkdir_class != "ok":
        if mkdir_class in {"host_unreachable", "transport_auth_failure", "transport_failure"}:
            classes.append(mkdir_class)
        else:
            classes.append("runtime_root_provisioning_failure")
    elif _to_int(mkdir.get("exit_code"), default=1) != 0:
        classes.append("runtime_root_provisioning_failure")
    if cleanup_failures > 0:
        classes.append("cleanup_failure")
    deduped = sorted(set(classes))
    if not deduped:
        return "ok", ["preflight_success"]
    if any(cls in {"host_unreachable", "transport_auth_failure", "transport_failure"} for cls in deduped):
        return "transport_auth_failure", deduped
    if "command_availability_failure" in deduped:
        return "provisioning_failure", deduped
    if "runtime_root_provisioning_failure" in deduped:
        return "provisioning_failure", deduped
    return "provisioning_failure", deduped


def _update_remote_preflight_observatory(
    *,
    repo_root: Path,
    lane: str,
    scenario: str,
    topology: str,
    seed: int,
    rows: list[dict[str, object]],
) -> dict[str, str]:
    obs_root = repo_root / "glow/lab/remote_preflight"
    obs_root.mkdir(parents=True, exist_ok=True)
    history_path = obs_root / "remote_preflight_history.jsonl"
    history_path.touch(exist_ok=True)

    now = iso_now()
    for row in rows:
        append_jsonl(
            history_path,
            {
                "schema_version": 1,
                "ts": now,
                "lane": lane,
                "scenario": scenario,
                "topology": topology,
                "seed": seed,
                "host_id": row.get("host_id"),
                "transport": row.get("transport"),
                "status": row.get("status"),
                "classification": row.get("classification"),
                "labels": row.get("labels", []),
                "reachable": bool(row.get("reachable", False)),
                "cleanup_failures": _to_int(row.get("cleanup_failures"), default=0),
            },
        )

    lines = [line for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) > REMOTE_PREFLIGHT_HISTORY_LIMIT:
        lines = lines[-REMOTE_PREFLIGHT_HISTORY_LIMIT:]
        history_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    records = [json.loads(line) for line in lines]

    by_host: dict[str, dict[str, object]] = {}
    by_scenario: dict[str, dict[str, object]] = {}
    by_lane: dict[str, dict[str, object]] = {}
    classification_counts: dict[str, int] = {}
    for rec in records:
        host = str(rec.get("host_id") or "unknown")
        scen = str(rec.get("scenario") or "unknown")
        lane_name = str(rec.get("lane") or "unknown")
        for bucket, key in ((by_host, host), (by_scenario, scen), (by_lane, lane_name)):
            row = bucket.setdefault(key, {"total": 0, "success": 0})
            row["total"] = int(row["total"]) + 1
            if str(rec.get("status") or "") == "ok":
                row["success"] = int(row["success"]) + 1
        classification = str(rec.get("classification") or "unknown")
        classification_counts[classification] = classification_counts.get(classification, 0) + 1

    def _with_rate(rows: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
        out: dict[str, dict[str, object]] = {}
        for key, row in sorted(rows.items()):
            total = max(1, int(row.get("total", 0)))
            out[key] = {
                "total": int(row.get("total", 0)),
                "success": int(row.get("success", 0)),
                "success_rate": round(float(int(row.get("success", 0)) / total), 4),
            }
        return out

    rollup = {
        "schema_version": 1,
        "history_entries": len(records),
        "classification_counts": dict(sorted(classification_counts.items())),
        "by_host": _with_rate(by_host),
        "by_scenario": _with_rate(by_scenario),
        "by_lane": _with_rate(by_lane),
        "generated_at": iso_now(),
    }
    trend = {
        "schema_version": 1,
        "window_entries": len(records),
        "host_reachable": sum(1 for rec in records if bool(rec.get("reachable", False))),
        "host_unreachable": sum(1 for rec in records if not bool(rec.get("reachable", False))),
        "command_availability_failures": classification_counts.get("command_availability_failure", 0),
        "runtime_root_provisioning_failures": classification_counts.get("runtime_root_provisioning_failure", 0),
        "cleanup_failures": classification_counts.get("cleanup_failure", 0),
        "transport_or_auth_failures": sum(
            classification_counts.get(name, 0) for name in ("transport_auth_failure", "transport_failure", "host_unreachable")
        ),
        "preflight_success_count": classification_counts.get("preflight_success", 0),
        "generated_at": iso_now(),
    }
    write_json(obs_root / "remote_preflight_rollup.json", rollup)
    write_json(obs_root / "remote_preflight_trend_report.json", trend)
    return {
        "history": str(history_path.relative_to(repo_root)),
        "rollup": str((obs_root / "remote_preflight_rollup.json").relative_to(repo_root)),
        "trend": str((obs_root / "remote_preflight_trend_report.json").relative_to(repo_root)),
    }


def remote_preflight_observatory_report(repo_root: Path) -> dict[str, object]:
    root = repo_root.resolve()
    obs_root = root / "glow/lab/remote_preflight"
    rollup = read_json(obs_root / "remote_preflight_rollup.json") if (obs_root / "remote_preflight_rollup.json").exists() else {}
    trend = read_json(obs_root / "remote_preflight_trend_report.json") if (obs_root / "remote_preflight_trend_report.json").exists() else {}
    return {
        "schema_version": 1,
        "suite": "remote_preflight_observatory",
        "status": "passed",
        "ok": True,
        "exit_code": 0,
        "rollup": rollup,
        "trend": trend,
        "artifact_paths": {
            "history": _relative_or_absolute(obs_root / "remote_preflight_history.jsonl", root),
            "rollup": _relative_or_absolute(obs_root / "remote_preflight_rollup.json", root),
            "trend": _relative_or_absolute(obs_root / "remote_preflight_trend_report.json", root),
        },
    }


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
    remote_smoke: bool = False,
) -> dict[str, object]:
    root = repo_root.resolve()
    scenario_name = _scenario_for_remote_smoke(scenario_name)
    if scenario_name not in WAN_SCENARIOS:
        raise ValueError(f"unknown WAN scenario: {scenario_name}")
    if remote_smoke and hosts_file is None:
        raise ValueError("remote smoke mode requires --hosts inventory")
    run_id = f"federation_wan_{scenario_name}_{topology_name}_seed{seed}"
    run_root = root / "glow/lab/wan" / run_id
    if clean and run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True, exist_ok=True)

    hosts = _load_hosts(hosts_file=hosts_file, run_root=run_root, host_count=_host_count_for_topology(topology_name))
    if remote_smoke:
        runtime_s = min(runtime_s, 2.8)
        nodes_per_host = 1
    topology = deterministic_multihost_topology(topology=topology_name, seed=seed, hosts=hosts, nodes_per_host=nodes_per_host)
    write_json(run_root / "host_manifest.json", {"schema_version": 1, "hosts": [host.__dict__ for host in hosts]})
    write_json(run_root / "topology_manifest.json", topology)

    transitions = run_root / "host_process_transitions.jsonl"
    transitions.write_text("", encoding="utf-8")
    remote_dispatch = run_root / "remote_dispatch_log.jsonl"
    remote_dispatch.write_text("", encoding="utf-8")
    preflight_rows: list[dict[str, object]] = []
    for host in hosts:
        if host.transport != "ssh":
            preflight_rows.append(
                cast(
                    dict[str, object],
                    {
                    "host_id": host.host_id,
                    "transport": host.transport,
                    "status": "skipped",
                    "classification": "not_remote_transport",
                    "labels": ["not_remote_transport"],
                    "reachable": True,
                    "cleanup_failures": 0,
                    },
                )
            )
            continue
        adapter = _transport("ssh")
        check = adapter.run(host, ["sh", "-lc", "command -v sh && command -v mkdir"], cwd=None)
        mkdir = adapter.run(host, ["mkdir", "-p", host.runtime_root], cwd=None)
        status, labels = classify_remote_preflight(check=check, mkdir=mkdir)
        row: dict[str, object] = {
            "host_id": host.host_id,
            "transport": host.transport,
            "status": "ok" if status == "ok" else "failed",
            "classification": status,
            "labels": labels,
            "reachable": status in {"ok", "provisioning_failure"},
            "cleanup_failures": 0,
            "check": check,
            "mkdir": mkdir,
        }
        preflight_rows.append(row)
        append_jsonl(remote_dispatch, {"ts": iso_now(), "phase": "preflight", "host_id": host.host_id, "status": row["status"], "classification": status, "labels": labels})
    write_json(run_root / "remote_preflight_report.json", {"schema_version": 1, "rows": preflight_rows})

    host_by_id = {host.host_id: host for host in hosts}
    nodes = _as_rows(topology.get("nodes"))
    active: list[dict[str, object]] = []
    for row in nodes:
        node_id = str(row.get("node_id") or "")
        host_id = str(row.get("host_id") or "")
        host = host_by_id[host_id]
        if remote_smoke and host.transport != "local":
            node_root = run_root / "remote_collected" / host.host_id / "nodes" / node_id
        else:
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
            remote_cmd = [
                "sh",
                "-lc",
                f"mkdir -p {shlex.quote(host.runtime_root)}/nodes/{shlex.quote(node_id)}/glow/lab && "
                f"printf '%s\n' {shlex.quote(json.dumps({'node_id': node_id, 'host_id': host_id, 'scenario': scenario_name, 'seed': seed}, sort_keys=True))} > "
                f"{shlex.quote(host.runtime_root)}/nodes/{shlex.quote(node_id)}/glow/lab/remote_dispatch.json",
            ]
            result = adapter.run(host, remote_cmd, cwd=None)
            append_jsonl(transitions, {"ts": iso_now(), "state": "remote_dispatch", "host_id": host_id, "node_id": node_id, "transport": host.transport, "result": result})
            append_jsonl(remote_dispatch, {"ts": iso_now(), "phase": "dispatch", "host_id": host_id, "node_id": node_id, "transport": host.transport, "result": result})

    schedule = deterministic_wan_fault_schedule(
        scenario=scenario_name,
        topology=topology_name,
        seed=seed,
        duration_s=min(runtime_s, _to_float(WAN_SCENARIOS[scenario_name].get("duration_s"), default=runtime_s)),
    )
    write_json(run_root / "fault_timeline.json", {"schema_version": 1, "scenario": scenario_name, "timeline": schedule})

    start = time.monotonic()
    timeline_log = run_root / "wan_faults.jsonl"
    timeline_log.write_text("", encoding="utf-8")
    for action in schedule:
        deadline = start + _to_float(action.get("offset_s"), default=0.0)
        if deadline > time.monotonic():
            time.sleep(deadline - time.monotonic())
        host_filter = str(action.get("host") or "")
        for node in nodes:
            if host_filter and str(node.get("host_id") or "") != host_filter:
                continue
            node_root = Path(host_by_id[str(node.get("host_id") or "")].runtime_root) / "nodes" / str(node.get("node_id") or "")
            _apply_wan_fault(node_root, action)
            emit_node_truth_artifacts(node_root, node_id=str(node.get("node_id") or ""), host_id=str(node.get("host_id") or ""))
            append_jsonl(timeline_log, {"ts": iso_now(), "node_id": node.get("node_id"), "host_id": node.get("host_id"), **action})

    time.sleep(0.2)
    exit_codes: dict[str, int] = {}
    for row in active:
        proc = row.get("proc")
        if not isinstance(proc, subprocess.Popen):
            continue
        proc.terminate()
        code = int(proc.wait(timeout=5))
        exit_codes[str(row["node_id"])] = code
        append_jsonl(transitions, {"ts": iso_now(), "state": "stopped", "host_id": row["host_id"], "node_id": row["node_id"], "exit_code": code})

    remote_collection_rows: list[dict[str, object]] = []
    cleanup_failures_by_host: dict[str, int] = {}
    for host in hosts:
        if host.transport != "ssh":
            continue
        adapter = _transport("ssh")
        for node in [node for node in nodes if str(node.get("host_id") or "") == host.host_id]:
            node_id = str(node.get("node_id") or "")
            target_root = run_root / "remote_collected" / host.host_id / "nodes" / node_id / "glow/lab"
            target_root.mkdir(parents=True, exist_ok=True)
            cat = adapter.run(
                host,
                ["sh", "-lc", f"cat {shlex.quote(host.runtime_root)}/nodes/{shlex.quote(node_id)}/glow/lab/remote_dispatch.json"],
                cwd=None,
            )
            remote_path = target_root / "remote_dispatch_collected.json"
            if _to_int(cat.get("exit_code"), default=1) == 0:
                remote_path.write_text(str(cat.get("stdout") or "{}"), encoding="utf-8")
            remote_collection_rows.append(
                {
                    "host_id": host.host_id,
                    "node_id": node_id,
                    "transport": host.transport,
                    "collection_exit_code": _to_int(cat.get("exit_code"), default=1),
                    "remote_runtime_root": host.runtime_root,
                    "collected_path": str(remote_path.relative_to(root)),
                }
            )
            append_jsonl(remote_dispatch, {"ts": iso_now(), "phase": "collect", "host_id": host.host_id, "node_id": node_id, "result": cat})
            cleanup = adapter.run(host, ["rm", "-rf", f"{host.runtime_root}/nodes/{node_id}"], cwd=None)
            if _to_int(cleanup.get("exit_code"), default=1) != 0:
                cleanup_failures_by_host[host.host_id] = cleanup_failures_by_host.get(host.host_id, 0) + 1
            append_jsonl(remote_dispatch, {"ts": iso_now(), "phase": "cleanup", "host_id": host.host_id, "node_id": node_id, "result": cleanup})
    for row in preflight_rows:
        host_id = str(row.get("host_id") or "")
        cleanup_failures = _to_int(cleanup_failures_by_host.get(host_id), default=0)
        row["cleanup_failures"] = cleanup_failures
        if row.get("transport") == "ssh":
            status, labels = classify_remote_preflight(
                check=row.get("check") if isinstance(row.get("check"), dict) else {},
                mkdir=row.get("mkdir") if isinstance(row.get("mkdir"), dict) else {},
                cleanup_failures=cleanup_failures,
            )
            row["classification"] = status
            row["labels"] = labels
            row["status"] = "ok" if status == "ok" else "failed"
            row["reachable"] = status in {"ok", "provisioning_failure"}
    write_json(run_root / "remote_preflight_report.json", {"schema_version": 1, "rows": preflight_rows})
    write_json(run_root / "remote_artifact_collection.json", {"schema_version": 1, "rows": remote_collection_rows, "count": len(remote_collection_rows)})

    per_host: dict[str, dict[str, object]] = {}
    digest_rows: list[str] = []
    for host in hosts:
        host_nodes = [node for node in nodes if str(node.get("host_id") or "") == host.host_id]
        node_rows: dict[str, object] = {}
        for node in host_nodes:
            node_id = str(node.get("node_id") or "")
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
            trust_payload = read_json(node_root / "glow/pulse_trust/epoch_state.json")
            node_rows[node_id]["trust"] = trust_payload
            digest_rows.append(json.dumps(trust_payload, sort_keys=True))
        per_host[host.host_id] = {"host": host.__dict__, "nodes": node_rows}

    replay_rows: dict[str, dict[str, object]] = {}
    if emit_replay:
        for host in hosts:
            host_nodes = [node for node in nodes if str(node.get("host_id") or "") == host.host_id]
            for node in host_nodes:
                node_id = str(node.get("node_id") or "")
                node_root = Path(host.runtime_root) / "nodes" / node_id
                previous = Path.cwd()
                try:
                    os.chdir(node_root)
                    rc = int(forge_replay.main(["--verify", "--last-n", "3", "--emit-snapshot", "0"]))
                finally:
                    os.chdir(previous)
                replay_files = sorted((node_root / "glow/forge/replay").glob("replay_*.json"), key=lambda path: path.name)
                latest = replay_files[-1] if replay_files else None
                emit_node_truth_artifacts(node_root, node_id=node_id, host_id=host.host_id)
                replay_rows[node_id] = {
                    "emit_rc": rc,
                    "replay_path": _relative_or_absolute(latest, root) if latest else None,
                    "replay_present": bool(latest),
                }


    completeness_rows: list[dict[str, object]] = []
    for host in hosts:
        host_nodes = [node for node in nodes if str(node.get("host_id") or "") == host.host_id]
        for node in host_nodes:
            node_id = str(node.get("node_id") or "")
            node_root = Path(host.runtime_root) / "nodes" / node_id
            node_truth_payload = read_json(node_root / "glow/lab/node_truth_artifacts.json")
            completeness = node_truth_payload.get("completeness") if isinstance(node_truth_payload.get("completeness"), dict) else {}
            completeness_rows.append(
                {
                    "host_id": host.host_id,
                    "node_id": node_id,
                    "truth_artifact_path": _relative_or_absolute(node_root / "glow/lab/node_truth_artifacts.json", root),
                    "required_present": completeness.get("required_present") if isinstance(completeness.get("required_present"), list) else [],
                    "required_missing": completeness.get("required_missing") if isinstance(completeness.get("required_missing"), list) else [],
                    "optional_present": completeness.get("optional_present") if isinstance(completeness.get("optional_present"), list) else [],
                }
            )
    write_json(run_root / "node_truth_manifest.json", {"schema_version": 1, "rows": completeness_rows, "node_count": len(completeness_rows)})

    node_evidence_summary_rows: list[dict[str, object]] = []
    for host in hosts:
        host_nodes = [node for node in nodes if str(node.get("host_id") or "") == host.host_id]
        for node in host_nodes:
            node_id = str(node.get("node_id") or "")
            node_root = Path(host.runtime_root) / "nodes" / node_id
            node_truth_payload = read_json(node_root / "glow/lab/node_truth_artifacts.json")
            quorum = _as_mapping(node_truth_payload.get("quorum_state"))
            digest = _as_mapping(node_truth_payload.get("digest_state"))
            epoch = _as_mapping(node_truth_payload.get("epoch_state"))
            reanchor = _as_mapping(node_truth_payload.get("reanchor_state"))
            fairness = _as_mapping(node_truth_payload.get("fairness_state"))
            replay = _as_mapping(node_truth_payload.get("replay_state"))
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
    checks = {
        key: bool(observed.get(key) == value)
        for key, value in cast(dict[str, object], expected).items()
    }
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
    inventory_digest = hashlib.sha256(json.dumps([host.__dict__ for host in hosts], sort_keys=True).encode("utf-8")).hexdigest()
    write_json(
        run_root / "remote_run_metadata.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "remote_smoke": remote_smoke,
            "scenario": scenario_name,
            "inventory_digest": inventory_digest,
            "host_count": len(hosts),
            "dispatch_log": str(remote_dispatch.relative_to(root)),
        },
    )
    preflight_rows_for_obs = [row for row in preflight_rows if isinstance(row, dict) and str(row.get("transport")) == "ssh"]
    preflight_observatory = _update_remote_preflight_observatory(
        repo_root=root,
        lane=("ci_ephemeral_remote_smoke" if remote_smoke and bool(os.environ.get("GITHUB_ACTIONS")) else "operator_remote_smoke"),
        scenario=scenario_name,
        topology=topology_name,
        seed=seed,
        rows=preflight_rows_for_obs,
    ) if remote_smoke else {}

    payload: dict[str, object] = {
        "schema_version": 1,
        "mode": "wan_lab",
        "family": "wan",
        "remote_smoke": remote_smoke,
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
        "preflight_rows": preflight_rows,
        "preflight_observatory": preflight_observatory,
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
            "remote_dispatch_log": str(remote_dispatch.relative_to(root)),
            "remote_preflight_report": str((run_root / "remote_preflight_report.json").relative_to(root)),
            "remote_artifact_collection": str((run_root / "remote_artifact_collection.json").relative_to(root)),
            "remote_run_metadata": str((run_root / "remote_run_metadata.json").relative_to(root)),
            **({
                "remote_preflight_history": preflight_observatory.get("history"),
                "remote_preflight_rollup": preflight_observatory.get("rollup"),
                "remote_preflight_trend_report": preflight_observatory.get("trend"),
            } if preflight_observatory else {}),
        },
    }
    artifact_paths = _as_mapping(payload.get("artifact_paths"))
    truth_artifact_paths = _as_mapping(truth_payload.get("artifact_paths"))
    if truth_artifact_paths:
        merged_paths = dict(artifact_paths)
        for key, path in truth_artifact_paths.items():
            if isinstance(path, str):
                merged_paths[str(key)] = str(Path(path).relative_to(root))
        payload["artifact_paths"] = merged_paths
        artifact_paths = merged_paths
    payload["failure_classification"] = classify_wan_failure_surface(payload=payload)
    oracle_payload = _as_mapping(payload.get("oracle"))
    oracle_passed = bool(oracle_payload.get("passed"))
    payload["status"] = "passed" if oracle_passed else "failed"
    payload["ok"] = oracle_passed
    payload["exit_code"] = 0 if oracle_passed else 1
    write_json(run_root / "run_summary.json", payload)
    return payload



def classify_wan_failure_surface(*, payload: dict[str, object]) -> str:
    preflight_rows = payload.get("preflight_rows") if isinstance(payload.get("preflight_rows"), list) else []
    if any(str(row.get("classification") or "") in {"transport_auth_failure"} for row in preflight_rows if isinstance(row, dict)):
        return "remote_transport_or_auth_failure"
    if any(str(row.get("classification") or "") == "provisioning_failure" for row in preflight_rows if isinstance(row, dict)):
        return "remote_environment_drift_or_provisioning_failure"
    truth = payload.get("truth_oracle") if isinstance(payload.get("truth_oracle"), dict) else {}
    policy = truth.get("contradiction_policy") if isinstance(truth.get("contradiction_policy"), dict) else {}
    if str(policy.get("outcome") or "") in {"warning", "blocking_failure", "indeterminate"}:
        return "truth_or_gate_contradiction_failure"
    oracle = payload.get("oracle") if isinstance(payload.get("oracle"), dict) else {}
    if not bool(oracle.get("passed", False)):
        return "scenario_or_runtime_regression"
    return "passed"


def run_wan_suite(repo_root: Path, *, topology_name: str, seed: int, runtime_s: float, nodes_per_host: int, hosts_file: Path | None, clean: bool, remote_smoke: bool = False) -> dict[str, object]:
    rows = []
    selected = [REMOTE_SMOKE_SCENARIOS[name] for name in sorted(REMOTE_SMOKE_SCENARIOS)] if remote_smoke else sorted(WAN_SCENARIOS)
    for idx, scenario in enumerate(selected, start=1):
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
                remote_smoke=remote_smoke,
            )
        )
    passed = sum(1 for row in rows if row.get("ok"))
    return {
        "schema_version": 1,
        "suite": "federation_wan",
        "remote_smoke": remote_smoke,
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
    remote_smoke: bool = False,
) -> dict[str, object]:
    if remote_smoke:
        selected = [REMOTE_SMOKE_SCENARIOS[name] for name in sorted(REMOTE_SMOKE_SCENARIOS)] if scenario is None else [_scenario_for_remote_smoke(scenario)]
    else:
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
            remote_smoke=remote_smoke,
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
