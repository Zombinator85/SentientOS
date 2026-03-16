from __future__ import annotations

import hashlib
import random
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from scripts import forge_replay
from sentientos.attestation import append_jsonl, iso_now, read_json, read_jsonl, write_json
from sentientos.node_operations import build_incident_bundle, node_health, run_bootstrap

RuntimeMode = Literal["worker", "daemon", "auto"]
ProcessState = Literal["planned", "starting", "running", "stopping", "stopped", "failed", "timeout", "restarting"]
ConvergenceClass = Literal[
    "converged_expected",
    "converged_with_degradation",
    "failed_to_converge",
    "blocked_by_policy",
    "indeterminate_due_to_lab_limitations",
]

LIVE_SCENARIOS: dict[str, dict[str, Any]] = {
    "healthy_3node": {
        "description": "Healthy three-node local federation lab run.",
        "node_count": 3,
        "live_capable": True,
        "simulated_only": False,
        "expected": {"quorum_admit": True},
        "injections": [],
    },
    "quorum_failure": {
        "description": "Digest+epoch mismatches should block quorum-gated actions.",
        "node_count": 3,
        "live_capable": True,
        "simulated_only": False,
        "expected": {"quorum_admit": False},
        "injections": [
            {"target": "node-02", "type": "peer_digest_mismatch"},
            {"target": "node-03", "type": "trust_epoch_mismatch"},
        ],
    },
    "replay_storm": {
        "description": "Replay duplication flood remains bounded and classified.",
        "node_count": 3,
        "live_capable": True,
        "simulated_only": False,
        "expected": {"duplicate_events_min": 12},
        "injections": [{"target": "all", "type": "replay_duplication", "count": 4}],
    },
    "reanchor_continuation": {
        "description": "Audit break + explicit re-anchor continuation on one node.",
        "node_count": 3,
        "live_capable": True,
        "simulated_only": False,
        "expected": {"continuation_recognized": True},
        "injections": [
            {"target": "node-02", "type": "audit_chain_break"},
            {"target": "node-02", "type": "force_reanchor"},
        ],
    },
    "pressure_local_safety": {
        "description": "Governor pressure escalation cannot overrule local safety.",
        "node_count": 4,
        "live_capable": True,
        "simulated_only": False,
        "expected": {"local_safety_dominant": True},
        "injections": [
            {"target": "node-01", "type": "governor_pressure_escalation", "level": "critical"},
            {"target": "node-01", "type": "local_safety_override"},
            {"target": "node-02", "type": "restart_storm", "count": 2},
        ],
    },
}

ENDURANCE_SCENARIOS: dict[str, dict[str, Any]] = {
    "daemon_endurance_steady_state": {
        "description": "Longer daemon run with bounded replay and pressure pulses.",
        "node_count": 3,
        "duration_s": 4.0,
        "phases": [
            {"name": "warmup", "at_s": 0.4, "actions": [{"target": "all", "type": "sample_health"}]},
            {"name": "load", "at_s": 1.2, "actions": [{"target": "all", "type": "replay_duplication", "count": 2}]},
            {"name": "settle", "at_s": 2.8, "actions": [{"target": "all", "type": "pressure_escalation", "level": "medium"}]},
            {"name": "normalize", "at_s": 3.4, "actions": [{"target": "all", "type": "pressure_normalize"}]},
        ],
        "expected": {"quorum_admit": True, "state_allow": ["healthy", "degraded"]},
    },
    "daemon_restart_storm_recovery": {
        "description": "Staged restart storms should recover to quorum and bounded degradation.",
        "node_count": 4,
        "duration_s": 5.0,
        "phases": [
            {"name": "warmup", "at_s": 0.5, "actions": [{"target": "all", "type": "sample_health"}]},
            {"name": "storm_one", "at_s": 1.1, "actions": [{"target": "node-02", "type": "restart_storm", "count": 2}]},
            {"name": "storm_two", "at_s": 2.0, "actions": [{"target": "node-03", "type": "restart_storm", "count": 2}]},
            {"name": "verify", "at_s": 3.4, "actions": [{"target": "all", "type": "sample_health"}]},
        ],
        "expected": {"quorum_admit": True, "state_allow": ["healthy", "degraded"]},
    },
    "daemon_reanchor_recovery_chain": {
        "description": "Forced audit chain break and re-anchor continuation over restart.",
        "node_count": 3,
        "duration_s": 4.8,
        "phases": [
            {"name": "break", "at_s": 0.8, "actions": [{"target": "node-02", "type": "audit_chain_break"}]},
            {"name": "reanchor", "at_s": 1.4, "actions": [{"target": "node-02", "type": "force_reanchor"}]},
            {"name": "restart", "at_s": 2.2, "actions": [{"target": "node-02", "type": "restart_storm", "count": 1}]},
            {"name": "verify", "at_s": 3.4, "actions": [{"target": "all", "type": "sample_health"}]},
        ],
        "expected": {"quorum_admit": True, "continuation_recognized": True, "state_allow": ["healthy", "degraded"]},
    },
    "daemon_digest_mismatch_containment": {
        "description": "Digest mismatch introduced, policy blocks quorum, then cleanup restores admit.",
        "node_count": 3,
        "duration_s": 5.2,
        "phases": [
            {"name": "inject", "at_s": 0.9, "actions": [{"target": "node-03", "type": "peer_digest_mismatch"}]},
            {"name": "contain", "at_s": 1.8, "actions": [{"target": "all", "type": "sample_health"}]},
            {"name": "cleanup", "at_s": 2.8, "actions": [{"target": "node-03", "type": "peer_digest_cleanup"}]},
            {"name": "verify", "at_s": 4.0, "actions": [{"target": "all", "type": "sample_health"}]},
        ],
        "expected": {"quorum_admit": True, "state_allow": ["healthy", "degraded", "restricted"]},
    },
    "daemon_epoch_rotation_propagation": {
        "description": "Single-node epoch rotation with deterministic propagation convergence.",
        "node_count": 4,
        "duration_s": 5.0,
        "phases": [
            {"name": "rotate", "at_s": 0.9, "actions": [{"target": "node-01", "type": "trust_epoch_rotate"}]},
            {"name": "peer_interaction", "at_s": 1.7, "actions": [{"target": "all", "type": "replay_duplication", "count": 1}]},
            {"name": "propagate", "at_s": 2.7, "actions": [{"target": "all", "type": "trust_epoch_propagate"}]},
            {"name": "verify", "at_s": 3.8, "actions": [{"target": "all", "type": "sample_health"}]},
        ],
        "expected": {"quorum_admit": True, "epoch_compatible": True, "state_allow": ["healthy", "degraded"]},
    },
    "daemon_pressure_fairness_endurance": {
        "description": "Pressure/noisy-subject bursts remain bounded and stabilize counters.",
        "node_count": 4,
        "duration_s": 5.2,
        "phases": [
            {"name": "escalate", "at_s": 0.8, "actions": [{"target": "all", "type": "pressure_escalation", "level": "critical"}]},
            {"name": "noise", "at_s": 1.7, "actions": [{"target": "node-02", "type": "noisy_subject_pressure", "count": 6}]},
            {"name": "noise_more", "at_s": 2.4, "actions": [{"target": "node-03", "type": "noisy_subject_pressure", "count": 6}]},
            {"name": "normalize", "at_s": 3.3, "actions": [{"target": "all", "type": "pressure_normalize"}]},
            {"name": "verify", "at_s": 4.2, "actions": [{"target": "all", "type": "sample_health"}]},
        ],
        "expected": {"quorum_admit": True, "fairness_stable": True, "state_allow": ["healthy", "degraded"]},
    },
}


@dataclass(frozen=True)
class NodeLayout:
    node_id: str
    peer_id: str
    port: int
    runtime_dir: str


@dataclass
class NodeRuntimeProcess:
    node_id: str
    mode: RuntimeMode
    proc: subprocess.Popen[str]
    command: list[str]
    cwd: Path
    stdout_path: Path
    stderr_path: Path


def list_federation_lab_scenarios() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name, spec in sorted(LIVE_SCENARIOS.items()):
        rows.append(
            {
                "name": name,
                "description": str(spec.get("description") or ""),
                "node_count": int(spec.get("node_count") or 0),
                "live_capable": True,
                "simulated_only": False,
                "daemon_parity": True,
                "family": "live",
            }
        )
    for name, spec in sorted(ENDURANCE_SCENARIOS.items()):
        rows.append(
            {
                "name": name,
                "description": str(spec.get("description") or ""),
                "node_count": int(spec.get("node_count") or 0),
                "live_capable": True,
                "simulated_only": False,
                "daemon_parity": True,
                "family": "endurance",
                "duration_s": float(spec.get("duration_s") or 0.0),
            }
        )
    return rows


def _nodes_for_target(target: str, node_ids: list[str]) -> list[str]:
    if target == "all":
        return list(node_ids)
    if target in node_ids:
        return [target]
    return []


def deterministic_node_layout(*, nodes: int, seed: int, base_port: int = 24000) -> list[NodeLayout]:
    resolved = max(1, nodes)
    stride = 11 + (seed % 7)
    start = base_port + (seed % 100) * 20
    rows: list[NodeLayout] = []
    for idx in range(1, resolved + 1):
        node_id = f"node-{idx:02d}"
        peer_hash = hashlib.sha256(f"{seed}:{node_id}".encode("utf-8")).hexdigest()[:12]
        rows.append(NodeLayout(node_id=node_id, peer_id=f"peer-{peer_hash}", port=start + idx * stride, runtime_dir=f"nodes/{node_id}"))
    return rows


def deterministic_fault_schedule(*, scenario_name: str, seed: int, node_ids: list[str], duration_s: float) -> list[dict[str, object]]:
    spec = ENDURANCE_SCENARIOS.get(scenario_name)
    if spec is None:
        return []
    phases = spec.get("phases") if isinstance(spec.get("phases"), list) else []
    rng = random.Random(f"{scenario_name}:{seed}:{','.join(node_ids)}")
    rows: list[dict[str, object]] = []
    seq = 0
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        at_s = min(max(0.0, float(phase.get("at_s") or 0.0)), duration_s)
        actions = phase.get("actions") if isinstance(phase.get("actions"), list) else []
        for action in actions:
            if not isinstance(action, dict):
                continue
            for node_id in _nodes_for_target(str(action.get("target") or ""), node_ids):
                count = max(1, int(action.get("count") or 1)) if str(action.get("type")) in {"restart_storm", "replay_duplication"} else 1
                for burst in range(count):
                    seq += 1
                    rows.append(
                        {
                            "sequence": seq,
                            "phase": str(phase.get("name") or "phase"),
                            "offset_s": round(min(duration_s, at_s + rng.uniform(0.01, 0.12) + burst * 0.02), 3),
                            "target": node_id,
                            "type": str(action.get("type") or ""),
                            "params": {k: v for k, v in action.items() if k not in {"target", "type", "count"}},
                        }
                    )
    rows.sort(key=lambda row: (float(row.get("offset_s", 0.0)), int(row.get("sequence", 0))))
    return rows


def _run_id(*, seed: int, scenario: str, family: str) -> str:
    return f"federation_{family}_{scenario}_seed{seed}"


def _node_root(run_root: Path, node_id: str) -> Path:
    return run_root / "nodes" / node_id


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_runtime_mode(mode: RuntimeMode, repo_root: Path) -> RuntimeMode:
    if mode in {"worker", "daemon"}:
        return mode
    daemon_entrypoint = repo_root / "scripts/orchestrator_daemon.py"
    return "daemon" if daemon_entrypoint.exists() else "worker"


def _append_transition(path: Path, *, node_id: str, mode: RuntimeMode, state: ProcessState, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {"schema_version": 1, "ts": iso_now(), "node": node_id, "mode": mode, "state": state}
    row.update(extra)
    append_jsonl(path, row)
    return row


def _daemon_command(repo_root: Path) -> list[str]:
    return [sys.executable, str((repo_root / "scripts/orchestrator_daemon.py").resolve()), "--interval", "5"]


def _worker_command(node_root: Path, node_id: str, heartbeat_s: float) -> list[str]:
    return [
        sys.executable,
        "-m",
        "sentientos.lab.node_worker",
        "--node-root",
        str(node_root),
        "--node-id",
        node_id,
        "--heartbeat-s",
        str(heartbeat_s),
    ]


def _launch_node(
    *,
    repo_root: Path,
    run_root: Path,
    row: NodeLayout,
    mode: RuntimeMode,
    heartbeat_s: float,
    transitions_path: Path,
) -> NodeRuntimeProcess:
    node_root = _node_root(run_root, row.node_id)
    mode_dir = node_root / "glow/lab"
    mode_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = mode_dir / f"{mode}_stdout.log"
    stderr_path = mode_dir / f"{mode}_stderr.log"

    if mode == "daemon":
        command = _daemon_command(repo_root)
        cwd = node_root
    else:
        command = _worker_command(node_root, row.node_id, heartbeat_s)
        cwd = repo_root

    _append_transition(transitions_path, node_id=row.node_id, mode=mode, state="starting", command=command, cwd=str(cwd))
    proc = subprocess.Popen(command, cwd=cwd, stdout=stdout_path.open("a", encoding="utf-8"), stderr=stderr_path.open("a", encoding="utf-8"), text=True)
    _append_transition(transitions_path, node_id=row.node_id, mode=mode, state="running", pid=proc.pid)
    return NodeRuntimeProcess(node_id=row.node_id, mode=mode, proc=proc, command=command, cwd=cwd, stdout_path=stdout_path, stderr_path=stderr_path)


def _start_nodes(
    layout: list[NodeLayout],
    run_root: Path,
    *,
    repo_root: Path,
    mode: RuntimeMode,
    heartbeat_s: float,
    transitions_path: Path,
) -> dict[str, NodeRuntimeProcess]:
    return {
        row.node_id: _launch_node(repo_root=repo_root, run_root=run_root, row=row, mode=mode, heartbeat_s=heartbeat_s, transitions_path=transitions_path)
        for row in layout
    }


def _stop_nodes(
    procs: dict[str, NodeRuntimeProcess],
    *,
    transitions_path: Path,
    stop_timeout_s: float,
) -> dict[str, int]:
    exit_codes: dict[str, int] = {}
    for node_id, process in procs.items():
        if process.proc.poll() is None:
            _append_transition(transitions_path, node_id=node_id, mode=process.mode, state="stopping", pid=process.proc.pid)
            process.proc.terminate()
    for node_id, process in procs.items():
        try:
            code = int(process.proc.wait(timeout=max(1.0, stop_timeout_s)))
            exit_codes[node_id] = code
            _append_transition(transitions_path, node_id=node_id, mode=process.mode, state="stopped", pid=process.proc.pid, exit_code=code)
        except subprocess.TimeoutExpired:
            process.proc.kill()
            code = int(process.proc.wait(timeout=5))
            exit_codes[node_id] = code
            _append_transition(transitions_path, node_id=node_id, mode=process.mode, state="timeout", pid=process.proc.pid, exit_code=code)
    return exit_codes


def _restart_node(
    node_id: str,
    layout_map: dict[str, NodeLayout],
    run_root: Path,
    procs: dict[str, NodeRuntimeProcess],
    *,
    repo_root: Path,
    mode: RuntimeMode,
    heartbeat_s: float,
    transitions_path: Path,
) -> dict[str, object]:
    existing = procs.get(node_id)
    if existing is not None and existing.proc.poll() is None:
        _append_transition(transitions_path, node_id=node_id, mode=existing.mode, state="restarting", pid=existing.proc.pid)
        existing.proc.terminate()
        existing.proc.wait(timeout=8)
    procs[node_id] = _launch_node(repo_root=repo_root, run_root=run_root, row=layout_map[node_id], mode=mode, heartbeat_s=heartbeat_s, transitions_path=transitions_path)
    return {"node": node_id, "event": "restarted", "pid": procs[node_id].proc.pid, "runtime_mode": mode, "ts": iso_now()}


def _topology(layout: list[NodeLayout]) -> dict[str, object]:
    nodes = [{"node_id": row.node_id, "peer_id": row.peer_id, "port": row.port, "runtime_dir": row.runtime_dir} for row in layout]
    edges: list[dict[str, str]] = []
    for idx, row in enumerate(layout):
        peers = [layout[(idx + 1) % len(layout)].node_id] if len(layout) > 1 else []
        for peer in peers:
            edges.append({"from": row.node_id, "to": peer, "kind": "gossip"})
    return {"schema_version": 1, "nodes": nodes, "edges": edges}


def _write_daemon_snapshot(node_root: Path, *, node_id: str, process: NodeRuntimeProcess | None) -> dict[str, object]:
    snapshot = {
        "schema_version": 1,
        "ts": iso_now(),
        "node": node_id,
        "runtime_mode": process.mode if process is not None else "worker",
        "pid": process.proc.pid if process is not None else None,
        "alive": bool(process is not None and process.proc.poll() is None),
        "command": process.command if process is not None else [],
        "cwd": str(process.cwd) if process is not None else "",
        "stdout": str(process.stdout_path.relative_to(node_root)) if process is not None else "",
        "stderr": str(process.stderr_path.relative_to(node_root)) if process is not None else "",
    }
    write_json(node_root / "glow/lab/runtime_process_snapshot.json", snapshot)
    return snapshot


def _baseline_digest(node_root: Path, *, seed: int, node_id: str) -> str:
    return f"lab-digest-{seed}-{node_id}"


def _baseline_epoch(*, seed: int) -> str:
    return f"epoch-{seed}"


def _apply_injection(node_root: Path, *, node_id: str, injection: dict[str, Any], seed: int) -> dict[str, object]:
    typ = str(injection.get("type") or "")
    record: dict[str, object] = {"schema_version": 1, "ts": iso_now(), "node": node_id, "type": typ, "status": "applied"}

    if typ == "peer_digest_mismatch":
        digest = read_json(node_root / "glow/federation/governance_digest.json")
        digest["digest"] = f"live-mismatch-{seed}-{node_id}"
        digest["lab_fault"] = "peer_digest_mismatch"
        write_json(node_root / "glow/federation/governance_digest.json", digest)
    elif typ == "peer_digest_cleanup":
        digest = read_json(node_root / "glow/federation/governance_digest.json")
        digest["digest"] = _baseline_digest(node_root, seed=seed, node_id=node_id)
        digest["lab_fault"] = "none"
        write_json(node_root / "glow/federation/governance_digest.json", digest)
    elif typ == "trust_epoch_mismatch":
        epoch = read_json(node_root / "glow/pulse_trust/epoch_state.json")
        epoch["active_epoch_id"] = f"epoch-mismatch-{seed}-{node_id}"
        epoch["revoked_epochs"] = [f"epoch-{seed}"]
        write_json(node_root / "glow/pulse_trust/epoch_state.json", epoch)
    elif typ == "trust_epoch_rotate":
        epoch = read_json(node_root / "glow/pulse_trust/epoch_state.json")
        epoch["active_epoch_id"] = f"epoch-rotated-{seed}-{node_id}"
        epoch["revoked_epochs"] = [f"epoch-{seed}"]
        write_json(node_root / "glow/pulse_trust/epoch_state.json", epoch)
    elif typ == "trust_epoch_propagate":
        epoch = read_json(node_root / "glow/pulse_trust/epoch_state.json")
        epoch["active_epoch_id"] = f"epoch-propagated-{seed}"
        write_json(node_root / "glow/pulse_trust/epoch_state.json", epoch)
    elif typ == "replay_duplication":
        count = max(1, int(injection.get("count") or 1))
        base = {"schema_version": 1, "event_id": f"lab-replay-{seed}-{node_id}", "kind": "federated_control", "result": "accepted"}
        for _ in range(count):
            append_jsonl(node_root / "pulse/replay_runs.jsonl", base)
        record["count"] = count
    elif typ == "audit_chain_break":
        write_json(
            node_root / "glow/runtime/audit_trust_state.json",
            {"schema_version": 1, "degraded_audit_trust": True, "status": "degraded", "reason": "lab_forced_break", "preserve_history": True},
        )
    elif typ == "force_reanchor":
        write_json(
            node_root / "glow/runtime/audit_reanchor_state.json",
            {
                "schema_version": 1,
                "continuation_recognized": True,
                "status": "continued",
                "reason": "lab_forced_reanchor",
                "reanchor_id": f"lab-reanchor-{seed}-{node_id}",
            },
        )
    elif typ in {"governor_pressure_escalation", "pressure_escalation"}:
        rollup = read_json(node_root / "glow/governor/rollup.json")
        rollup["pressure_state"] = str(injection.get("level") or "critical")
        rollup["restriction_level"] = "high"
        write_json(node_root / "glow/governor/rollup.json", rollup)
    elif typ == "pressure_normalize":
        rollup = read_json(node_root / "glow/governor/rollup.json")
        rollup["pressure_state"] = "normal"
        rollup["restriction_level"] = "low"
        write_json(node_root / "glow/governor/rollup.json", rollup)
    elif typ == "local_safety_override":
        rollup = read_json(node_root / "glow/governor/rollup.json")
        rollup["local_safety_override"] = True
        rollup["restriction_level"] = "critical"
        write_json(node_root / "glow/governor/rollup.json", rollup)
    elif typ == "noisy_subject_pressure":
        counters_path = node_root / "glow/lab/fairness_counters.json"
        counters = read_json(counters_path) if counters_path.exists() else {"schema_version": 1, "subject_events": 0, "blocked": 0}
        count = max(1, int(injection.get("count") or 1))
        counters["subject_events"] = int(counters.get("subject_events") or 0) + count
        counters["blocked"] = int(counters.get("blocked") or 0) + max(1, count // 2)
        counters["stabilized"] = False
        write_json(counters_path, counters)
        record["count"] = count
    elif typ == "sample_health":
        record["status"] = "observed"
    else:
        record["status"] = "skipped"
        record["reason"] = "unknown_fault"

    return record


def classify_convergence(*, expected: dict[str, object], observed: dict[str, object], checks: dict[str, bool]) -> ConvergenceClass:
    if not checks:
        return "indeterminate_due_to_lab_limitations"
    if not bool(observed.get("corridor_interpretable", False)):
        return "indeterminate_due_to_lab_limitations"
    if bool(expected.get("policy_block_expected", False)) and not bool(observed.get("quorum_admit", True)):
        return "blocked_by_policy"
    critical = ["runtime_boot_behavior", "quorum_behavior", "continuation_behavior", "epoch_behavior"]
    if any(not bool(checks.get(key, True)) for key in critical):
        return "failed_to_converge"
    if any(not bool(value) for value in checks.values()):
        return "converged_with_degradation"
    return "converged_expected"


def _run_schedule(
    *,
    schedule: list[dict[str, object]],
    start_monotonic: float,
    duration_s: float,
    run_root: Path,
    layout_map: dict[str, NodeLayout],
    procs: dict[str, NodeRuntimeProcess],
    root: Path,
    resolved_mode: RuntimeMode,
    heartbeat_s: float,
    transitions_path: Path,
    seed: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    events: list[dict[str, object]] = []
    health_series: list[dict[str, object]] = []
    for row in schedule:
        offset_s = float(row.get("offset_s") or 0.0)
        deadline = start_monotonic + offset_s
        now = time.monotonic()
        if deadline > now:
            time.sleep(min(max(0.0, deadline - now), max(0.0, duration_s)))
        node_id = str(row.get("target") or "")
        action = {"target": node_id, "type": str(row.get("type") or "")}
        params = row.get("params") if isinstance(row.get("params"), dict) else {}
        action.update(params)
        if action["type"] == "restart_storm":
            restart = _restart_node(
                node_id,
                layout_map,
                run_root,
                procs,
                repo_root=root,
                mode=resolved_mode,
                heartbeat_s=heartbeat_s,
                transitions_path=transitions_path,
            )
            restart.update({"phase": row.get("phase"), "offset_s": offset_s, "type": "restart_storm"})
            events.append(restart)
            continue
        event = _apply_injection(_node_root(run_root, node_id), node_id=node_id, injection=action, seed=seed)
        event.update({"phase": row.get("phase"), "offset_s": offset_s, "runtime_mode": resolved_mode, "sequence": row.get("sequence")})
        events.append(event)
        if action["type"] == "sample_health":
            health = node_health(_node_root(run_root, node_id))
            health_series.append({"ts": iso_now(), "offset_s": offset_s, "node": node_id, "health_state": health.get("health_state"), "constitution_state": health.get("constitution_state")})
    return events, health_series


def _capture_governor_fairness_quorum(layout: list[NodeLayout], run_root: Path) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for row in layout:
        node_root = _node_root(run_root, row.node_id)
        governor = read_json(node_root / "glow/governor/rollup.json")
        epoch = read_json(node_root / "glow/pulse_trust/epoch_state.json")
        digest = read_json(node_root / "glow/federation/governance_digest.json")
        fairness_path = node_root / "glow/lab/fairness_counters.json"
        fairness = read_json(fairness_path) if fairness_path.exists() else {"schema_version": 1, "subject_events": 0, "blocked": 0, "stabilized": True}
        rows[row.node_id] = {"governor": governor, "epoch": epoch, "digest": digest, "fairness": fairness}
    return rows


def run_live_federation_lab(
    repo_root: Path,
    *,
    scenario_name: str,
    seed: int,
    node_count: int | None = None,
    emit_bundle: bool = False,
    runtime_s: float = 2.0,
    heartbeat_s: float = 0.6,
    clean: bool = False,
    runtime_mode: RuntimeMode = "auto",
) -> dict[str, object]:
    root = repo_root.resolve()
    is_endurance = scenario_name in ENDURANCE_SCENARIOS
    scenario = ENDURANCE_SCENARIOS.get(scenario_name) if is_endurance else LIVE_SCENARIOS.get(scenario_name)
    if scenario is None:
        raise ValueError(f"unknown live lab scenario: {scenario_name}")

    resolved_nodes = int(node_count or int(scenario.get("node_count") or 1))
    resolved_mode = _resolve_runtime_mode(runtime_mode, root)
    family = "endurance" if is_endurance else "live"
    run_id = _run_id(seed=seed, scenario=scenario_name, family=family)
    root_dir = root / "glow/lab/endurance" if is_endurance else root / "glow/lab/federation"
    run_root = root_dir / run_id
    if clean and run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True, exist_ok=True)

    layout = deterministic_node_layout(nodes=resolved_nodes, seed=seed)
    layout_map = {row.node_id: row for row in layout}

    transitions_path = run_root / "process_transitions.jsonl"
    transitions_path.write_text("", encoding="utf-8")

    resolved_runtime = float(scenario.get("duration_s") or runtime_s) if is_endurance else runtime_s
    if runtime_s > 0 and is_endurance:
        resolved_runtime = min(resolved_runtime, runtime_s)

    write_json(
        run_root / "run_metadata.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "scenario": scenario_name,
            "seed": seed,
            "node_count": resolved_nodes,
            "runtime_mode_requested": runtime_mode,
            "runtime_mode_resolved": resolved_mode,
            "family": family,
            "runtime_window_s": resolved_runtime,
        },
    )
    write_json(run_root / "topology.json", _topology(layout))

    bootstrap_rows: list[dict[str, object]] = []
    peer_map = [{"node_id": row.node_id, "peer_id": row.peer_id, "port": row.port} for row in layout]
    for row in layout:
        node_root = _node_root(run_root, row.node_id)
        node_root.mkdir(parents=True, exist_ok=True)
        write_json(
            node_root / "glow/lab/node_identity.json",
            {
                "schema_version": 1,
                "node_id": row.node_id,
                "peer_id": row.peer_id,
                "port": row.port,
                "runtime_root": str(node_root),
                "runtime_mode": resolved_mode,
                "peers": [peer for peer in peer_map if peer["node_id"] != row.node_id],
            },
        )
        bootstrap_rows.append(run_bootstrap(node_root, reason=f"lab_{scenario_name}", seed_minimal=True, allow_restore=True))
        digest = read_json(node_root / "glow/federation/governance_digest.json")
        digest["digest"] = _baseline_digest(node_root, seed=seed, node_id=row.node_id)
        write_json(node_root / "glow/federation/governance_digest.json", digest)
        epoch = read_json(node_root / "glow/pulse_trust/epoch_state.json")
        epoch["active_epoch_id"] = _baseline_epoch(seed=seed)
        write_json(node_root / "glow/pulse_trust/epoch_state.json", epoch)

    procs = _start_nodes(layout, run_root, repo_root=root, mode=resolved_mode, heartbeat_s=heartbeat_s, transitions_path=transitions_path)
    time.sleep(max(0.2, resolved_runtime / 4))

    timeline_events: list[dict[str, object]] = []
    health_series: list[dict[str, object]] = []
    schedule = deterministic_fault_schedule(scenario_name=scenario_name, seed=seed, node_ids=[row.node_id for row in layout], duration_s=resolved_runtime) if is_endurance else []
    if schedule:
        write_json(run_root / "staged_timeline_report.json", {"schema_version": 1, "scenario": scenario_name, "seed": seed, "duration_s": resolved_runtime, "timeline": schedule})
        start = time.monotonic()
        timeline_events, health_series = _run_schedule(
            schedule=schedule,
            start_monotonic=start,
            duration_s=resolved_runtime,
            run_root=run_root,
            layout_map=layout_map,
            procs=procs,
            root=root,
            resolved_mode=resolved_mode,
            heartbeat_s=heartbeat_s,
            transitions_path=transitions_path,
            seed=seed,
        )
    else:
        for injection in scenario.get("injections", []):
            if not isinstance(injection, dict):
                continue
            target = str(injection.get("target") or "")
            typ = str(injection.get("type") or "")
            for node_id in _nodes_for_target(target, [row.node_id for row in layout]):
                if typ == "restart_storm":
                    count = max(1, int(injection.get("count") or 1))
                    for _ in range(count):
                        timeline_events.append(
                            _restart_node(
                                node_id,
                                layout_map,
                                run_root,
                                procs,
                                repo_root=root,
                                mode=resolved_mode,
                                heartbeat_s=heartbeat_s,
                                transitions_path=transitions_path,
                            )
                        )
                    continue
                record = _apply_injection(_node_root(run_root, node_id), node_id=node_id, injection=injection, seed=seed)
                record["runtime_mode"] = resolved_mode
                timeline_events.append(record)

    injection_log = run_root / "scenario_injection_log.jsonl"
    injection_log.write_text("", encoding="utf-8")
    for row in timeline_events:
        append_jsonl(injection_log, row)

    time.sleep(max(0.4, resolved_runtime / 3))

    process_snapshots: dict[str, dict[str, object]] = {}
    for row in layout:
        process_snapshots[row.node_id] = _write_daemon_snapshot(_node_root(run_root, row.node_id), node_id=row.node_id, process=procs.get(row.node_id))

    process_exit = _stop_nodes(procs, transitions_path=transitions_path, stop_timeout_s=max(2.0, resolved_runtime))

    node_health_rows: dict[str, dict[str, object]] = {}
    constitution_snapshots: dict[str, dict[str, object]] = {}
    trust_snapshots: dict[str, dict[str, object]] = {}
    governor_snapshots: dict[str, dict[str, object]] = {}
    for row in layout:
        node_root = _node_root(run_root, row.node_id)
        node_health_rows[row.node_id] = node_health(node_root)
        write_json(node_root / "glow/lab/health_snapshot.json", node_health_rows[row.node_id])
        constitution_snapshots[row.node_id] = read_json(node_root / "glow/constitution/constitution_summary.json")
        trust_snapshots[row.node_id] = read_json(node_root / "glow/pulse_trust/epoch_state.json")
        governor_snapshots[row.node_id] = read_json(node_root / "glow/governor/rollup.json")

    node_signals = _capture_governor_fairness_quorum(layout, run_root)
    write_json(run_root / "node_signal_timeseries.json", {"schema_version": 1, "samples": [{"ts": iso_now(), "nodes": node_signals}]})
    if health_series:
        write_json(run_root / "node_health_timeseries.json", {"schema_version": 1, "samples": health_series})

    duplicate_events = 0
    continuation_recognized = False
    quorum_present = 0
    local_safety_active = False
    daemon_ready_nodes = 0
    epoch_values: set[str] = set()
    fairness_peak = 0
    corridor_interpretable = True
    for row in layout:
        node_root = _node_root(run_root, row.node_id)
        replay_rows = read_jsonl(node_root / "pulse/replay_runs.jsonl")
        duplicate_events += len(replay_rows)
        reanchor = read_json(node_root / "glow/runtime/audit_reanchor_state.json")
        continuation_recognized = continuation_recognized or bool(reanchor.get("continuation_recognized", False))
        digest = read_json(node_root / "glow/federation/governance_digest.json")
        epoch = read_json(node_root / "glow/pulse_trust/epoch_state.json")
        epoch_values.add(str(epoch.get("active_epoch_id") or ""))
        fairness = node_signals[row.node_id].get("fairness") if isinstance(node_signals[row.node_id], dict) else {}
        if isinstance(fairness, dict):
            fairness_peak = max(fairness_peak, int(fairness.get("blocked") or 0))
        health_state = str(node_health_rows[row.node_id].get("health_state") or "missing")
        if health_state == "missing":
            corridor_interpretable = False
        if str(digest.get("digest", "")).startswith("live-mismatch-"):
            continue
        if str(epoch.get("active_epoch_id", "")).startswith("epoch-mismatch-"):
            continue
        quorum_present += 1
        governor = read_json(node_root / "glow/governor/rollup.json")
        local_safety_active = local_safety_active or bool(governor.get("local_safety_override", False))
        if process_snapshots[row.node_id].get("pid"):
            daemon_ready_nodes += 1

    quorum_required = (resolved_nodes // 2) + 1
    quorum_admit = quorum_present >= quorum_required

    expected = scenario.get("expected") if isinstance(scenario.get("expected"), dict) else {}
    allowed_states = set(str(v) for v in (expected.get("state_allow") if isinstance(expected.get("state_allow"), list) else ["healthy", "degraded", "restricted"]))
    checks = {
        "runtime_boot_behavior": daemon_ready_nodes == resolved_nodes,
        "quorum_behavior": quorum_admit == bool(expected.get("quorum_admit", quorum_admit)),
        "continuation_behavior": (not bool(expected.get("continuation_recognized", False))) or continuation_recognized,
        "replay_behavior": duplicate_events >= int(expected.get("duplicate_events_min", 0)),
        "local_safety_behavior": (not bool(expected.get("local_safety_dominant", False))) or local_safety_active,
        "state_behavior": all(str(node_health_rows[node].get("health_state") or "missing") in allowed_states for node in node_health_rows),
        "epoch_behavior": (not bool(expected.get("epoch_compatible", False))) or len(epoch_values) == 1,
        "fairness_behavior": (not bool(expected.get("fairness_stable", False))) or fairness_peak <= 12,
        "corridor_behavior": corridor_interpretable,
    }

    observed = {
        "quorum_required": quorum_required,
        "quorum_present": quorum_present,
        "quorum_admit": quorum_admit,
        "duplicate_events": duplicate_events,
        "continuation_recognized": continuation_recognized,
        "local_safety_active": local_safety_active,
        "daemon_ready_nodes": daemon_ready_nodes,
        "epoch_cardinality": len(epoch_values),
        "fairness_peak": fairness_peak,
        "corridor_interpretable": corridor_interpretable,
    }

    convergence: ConvergenceClass = classify_convergence(expected=expected, observed=observed, checks=checks)
    write_json(run_root / "convergence_summary.json", {"schema_version": 1, "scenario": scenario_name, "class": convergence, "checks": checks, "observed": observed})

    cluster_digest_payload = {
        "schema_version": 1,
        "scenario": scenario_name,
        "seed": seed,
        "node_count": resolved_nodes,
        "quorum_admit": quorum_admit,
        "epoch_values": sorted(epoch_values),
        "fairness_peak": fairness_peak,
        "convergence": convergence,
    }
    cluster_digest = hashlib.sha256(str(cluster_digest_payload).encode("utf-8")).hexdigest()
    write_json(run_root / "final_cluster_state_digest.json", {"cluster_state": cluster_digest_payload, "sha256": cluster_digest})

    manifest_rows: list[dict[str, object]] = []
    for path in sorted(run_root.rglob("*")):
        if not path.is_file():
            continue
        manifest_rows.append({"path": str(path.relative_to(root)), "sha256": _sha256(path), "size": path.stat().st_size})
    write_json(run_root / "artifact_manifest.json", {"schema_version": 1, "run_id": run_id, "file_count": len(manifest_rows), "files": manifest_rows})

    incident_bundles: list[dict[str, object]] = []
    replay_reports: list[dict[str, object]] = []
    should_bundle = emit_bundle or is_endurance and convergence in {"failed_to_converge", "converged_with_degradation", "indeterminate_due_to_lab_limitations"}
    if should_bundle:
        for row in layout:
            node_root = _node_root(run_root, row.node_id)
            if convergence != "converged_expected":
                incident_bundles.append(
                    {
                        "node": row.node_id,
                        "runtime_mode": resolved_mode,
                        "bundle": build_incident_bundle(node_root, reason=f"lab_{scenario_name}", window=30),
                    }
                )
            replay_rc = forge_replay.main(["--repo-root", str(node_root), "--verify", "--last-n", "20"])
            replay_reports.append({"node": row.node_id, "runtime_mode": resolved_mode, "exit_code": int(replay_rc)})

    timeline = [
        {"ts": iso_now(), "event": "bootstrap_completed", "node_count": resolved_nodes, "runtime_mode": resolved_mode},
        {"ts": iso_now(), "event": "processes_started", "node_count": len(procs), "runtime_mode": resolved_mode},
        {"ts": iso_now(), "event": "injections_applied", "count": len(timeline_events)},
        {"ts": iso_now(), "event": "processes_stopped", "runtime_mode": resolved_mode},
    ]
    write_json(run_root / "event_timeline.json", {"schema_version": 1, "events": timeline})

    payload = {
        "schema_version": 1,
        "mode": "live_lab",
        "family": family,
        "runtime_mode_requested": runtime_mode,
        "runtime_mode_resolved": resolved_mode,
        "run_id": run_id,
        "scenario": scenario_name,
        "scenario_parity": {"full_daemon": resolved_mode == "daemon", "worker_fallback_used": resolved_mode == "worker"},
        "seed": seed,
        "node_count": resolved_nodes,
        "scenario_support": {"live_capable": True, "simulated_only": False},
        "created_at": iso_now(),
        "topology": _topology(layout),
        "bootstrap": bootstrap_rows,
        "process_exit_codes": process_exit,
        "process_snapshots": process_snapshots,
        "node_health": node_health_rows,
        "observed": observed,
        "oracle": {"expected": expected, "checks": checks, "passed": all(checks.values()), "convergence_class": convergence},
        "injection_log": str(injection_log.relative_to(root)),
        "incident_bundles": incident_bundles,
        "replay_reports": replay_reports,
        "node_snapshots": {
            "constitution": constitution_snapshots,
            "trust_epoch": trust_snapshots,
            "governor": governor_snapshots,
            "signals": node_signals,
        },
        "artifact_paths": {
            "run_root": str(run_root.relative_to(root)),
            "metadata": str((run_root / "run_metadata.json").relative_to(root)),
            "topology": str((run_root / "topology.json").relative_to(root)),
            "timeline": str((run_root / "event_timeline.json").relative_to(root)),
            "staged_timeline": str((run_root / "staged_timeline_report.json").relative_to(root)) if is_endurance else "",
            "convergence_summary": str((run_root / "convergence_summary.json").relative_to(root)),
            "node_signals": str((run_root / "node_signal_timeseries.json").relative_to(root)),
            "cluster_state_digest": str((run_root / "final_cluster_state_digest.json").relative_to(root)),
            "injection_log": str(injection_log.relative_to(root)),
            "process_transitions": str(transitions_path.relative_to(root)),
            "artifact_manifest": str((run_root / "artifact_manifest.json").relative_to(root)),
        },
    }
    payload["status"] = "passed" if payload["oracle"]["passed"] else "failed"
    payload["ok"] = bool(payload["oracle"]["passed"])
    payload["exit_code"] = 0 if payload["ok"] else 1
    write_json(run_root / "run_summary.json", payload)
    return payload


def run_endurance_suite(repo_root: Path, *, seed: int, runtime_mode: RuntimeMode, clean: bool) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for idx, name in enumerate(sorted(ENDURANCE_SCENARIOS), start=1):
        rows.append(
            run_live_federation_lab(
                repo_root,
                scenario_name=name,
                seed=seed + idx,
                node_count=None,
                emit_bundle=False,
                runtime_s=float(ENDURANCE_SCENARIOS[name].get("duration_s") or 4.0),
                clean=clean,
                runtime_mode=runtime_mode,
            )
        )
    passed = sum(1 for row in rows if row.get("ok") is True)
    payload = {
        "schema_version": 1,
        "suite": "federation_endurance",
        "seed": seed,
        "runtime_mode": runtime_mode,
        "runs": rows,
        "run_count": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "status": "passed" if passed == len(rows) else "failed",
        "ok": passed == len(rows),
        "exit_code": 0 if passed == len(rows) else 1,
    }
    return payload


def clean_live_federation_runs(repo_root: Path) -> dict[str, object]:
    root = repo_root.resolve()
    removed = False
    for rel in ("glow/lab/federation", "glow/lab/endurance"):
        path = root / rel
        if path.exists():
            shutil.rmtree(path)
            removed = True
    return {"schema_version": 1, "removed": removed, "path": "glow/lab", "status": "passed", "ok": True, "exit_code": 0}
