from __future__ import annotations

import hashlib
import io
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from sentientos.attestation import append_jsonl, canonical_json_bytes, iso_now, read_json, read_jsonl, write_json
from sentientos.system_constitution import compose_system_constitution, write_constitution_artifacts
from scripts import bootstrap_trust_restore, forge_replay, forge_status

ARTIFACT_DIR = Path("glow/operators")
BOOTSTRAP_HISTORY = ARTIFACT_DIR / "restoration_history.jsonl"
HEALTH_STATES = {"healthy", "degraded", "restricted", "missing"}

@contextmanager
def _chdir(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    try:
        import os

        os.chdir(path)
        yield
    finally:
        os.chdir(previous)



def _safe_ts(ts: str) -> str:
    return ts.replace(":", "-").replace(".", "-")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _latest_json(root: Path, pattern: str) -> tuple[dict[str, object], str | None]:
    items = sorted(root.glob(pattern), key=lambda item: item.name)
    if not items:
        return {}, None
    selected = items[-1]
    return read_json(selected), str(selected.relative_to(root))


def _bounded_jsonl(root: Path, rel: str, *, limit: int) -> list[dict[str, object]]:
    rows = read_jsonl(root / rel)
    if len(rows) <= limit:
        return rows
    return rows[-limit:]


def _health_from_surfaces(constitution: dict[str, object], status: dict[str, object]) -> str:
    constitution_state = str(constitution.get("constitution_state") or "missing")
    if constitution_state in HEALTH_STATES:
        if constitution_state == "healthy":
            integrity = str(status.get("integrity_overall") or "missing")
            runtime_data = ((status.get("health_domain") if isinstance(status.get("health_domain"), dict) else {}).get("runtime_data") or "unknown")
            if integrity == "ok" and runtime_data == "healthy":
                return "healthy"
            if integrity in {"warn", "fail"} or runtime_data in {"degraded", "missing_or_degraded"}:
                return "degraded"
        return constitution_state
    return "missing"


def _write_operator_rollups(root: Path, *, constitution: dict[str, object], status: dict[str, object], restoration: dict[str, object]) -> dict[str, str]:
    operator_root = root / ARTIFACT_DIR
    operator_root.mkdir(parents=True, exist_ok=True)

    trust_ledger = read_json(root / "glow/federation/trust_ledger_state.json")
    peers = trust_ledger.get("peer_states") if isinstance(trust_ledger.get("peer_states"), list) else []
    peer_summary = {
        "schema_version": 1,
        "peer_count": len(peers),
        "state_summary": trust_ledger.get("state_summary") if isinstance(trust_ledger.get("state_summary"), dict) else {},
        "peers": [
            {
                "peer_id": row.get("peer_id"),
                "trust_state": row.get("trust_state"),
                "reconciliation_needed": bool(row.get("reconciliation_needed", False)),
            }
            for row in peers[:128]
            if isinstance(row, dict)
        ],
    }
    peer_path = operator_root / "peer_health_summary.json"
    write_json(peer_path, peer_summary)

    restrictions = {
        "schema_version": 1,
        "constitution_state": constitution.get("constitution_state"),
        "degraded_modes": constitution.get("degraded_modes") if isinstance(constitution.get("degraded_modes"), list) else [],
        "restoration_hints": constitution.get("restoration_hints") if isinstance(constitution.get("restoration_hints"), list) else [],
        "mutation_allowed": status.get("mutation_allowed"),
        "publish_allowed": status.get("publish_allowed"),
        "automerge_allowed": status.get("automerge_allowed"),
    }
    restrictions_path = operator_root / "current_restrictions.json"
    write_json(restrictions_path, restrictions)

    summary = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "health_state": _health_from_surfaces(constitution, status),
        "constitution": {
            "state": constitution.get("constitution_state"),
            "digest": constitution.get("constitutional_digest"),
            "effective_posture": constitution.get("effective_posture"),
            "missing_required_artifacts": constitution.get("missing_required_artifacts", []),
        },
        "governor": status.get("governor") if isinstance(status.get("governor"), dict) else {},
        "audit_trust": status.get("audit_trust") if isinstance(status.get("audit_trust"), dict) else {},
        "audit_continuation": status.get("audit_continuation") if isinstance(status.get("audit_continuation"), dict) else {},
        "trust_epoch_refs": status.get("trust_epoch_refs") if isinstance(status.get("trust_epoch_refs"), dict) else {},
        "federation": {
            "governance_digest": read_json(root / "glow/federation/governance_digest.json"),
            "peer_health_summary_path": str(peer_path.relative_to(root)),
        },
        "recent_high_impact_actions": {
            "restoration": restoration,
            "recent_replay_runs": _bounded_jsonl(root, "pulse/replay_runs.jsonl", limit=10),
            "recent_repair_actions": _bounded_jsonl(root, "glow/forge/audit_reports/repair_actions.jsonl", limit=10),
        },
        "restrictions_path": str(restrictions_path.relative_to(root)),
        "sources": {
            "constitution_summary": "glow/constitution/constitution_summary.json",
            "forge_status": "glow/forge/operator/status",
            "governor_rollup": "glow/governor/rollup.json",
            "audit_trust_state": "glow/runtime/audit_trust_state.json",
            "pulse_trust_epoch": "glow/pulse_trust/epoch_state.json",
            "federation_governance_digest": "glow/federation/governance_digest.json",
            "trust_ledger_state": "glow/federation/trust_ledger_state.json",
            "node_truth_artifacts": "glow/lab/node_truth_artifacts.json",
        },
    }
    summary_path = operator_root / "operator_summary.json"
    write_json(summary_path, summary)

    md_lines = [
        "# SentientOS Operator Summary",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- health_state: {summary['health_state']}",
        f"- constitution_state: {summary['constitution']['state']}",
        f"- constitution_digest: {summary['constitution']['digest']}",
        f"- effective_posture: {summary['constitution']['effective_posture']}",
        f"- degraded_modes: {', '.join(constitution.get('degraded_modes', [])) if isinstance(constitution.get('degraded_modes'), list) else ''}",
        f"- restrictions_path: {summary['restrictions_path']}",
        "",
        "## Source Artifacts",
    ]
    for key, value in sorted(summary["sources"].items()):
        md_lines.append(f"- {key}: `{value}`")
    (operator_root / "operator_summary.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    history_path = root / BOOTSTRAP_HISTORY
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.touch(exist_ok=True)
    if restoration:
        append_jsonl(history_path, restoration)

    return {
        "operator_summary": str(summary_path.relative_to(root)),
        "operator_summary_md": str((operator_root / "operator_summary.md").relative_to(root)),
        "peer_health_summary": str(peer_path.relative_to(root)),
        "current_restrictions": str(restrictions_path.relative_to(root)),
        "restoration_history": str(BOOTSTRAP_HISTORY),
    }


def run_bootstrap(root: Path, *, reason: str, seed_minimal: bool, allow_restore: bool) -> dict[str, object]:
    root = root.resolve()
    phases: list[dict[str, object]] = []
    runtime_dirs = [
        "glow/operators",
        "glow/runtime",
        "glow/governor",
        "glow/pulse_trust",
        "glow/federation",
        "glow/forge/restoration",
        "pulse/audit",
    ]
    created_dirs: list[str] = []
    for rel in runtime_dirs:
        path = root / rel
        existed = path.exists()
        path.mkdir(parents=True, exist_ok=True)
        if not existed:
            created_dirs.append(rel)
    phases.append({"phase": "init_runtime_directories", "status": "ok", "created": created_dirs})

    seed_actions: list[str] = []
    manifest_path = root / "vow/immutable_manifest.json"
    if seed_minimal and not manifest_path.exists():
        from scripts.generate_immutable_manifest import generate_manifest

        generate_manifest(output=manifest_path, allow_missing_files=True)
        seed_actions.append("vow/immutable_manifest.json")
    phases.append({"phase": "seed_minimal_state", "status": "ok", "seeded": seed_actions})

    constitution = compose_system_constitution(root)
    constitution_paths = write_constitution_artifacts(root, payload=constitution)
    needs_restore = bool(constitution.get("missing_required_artifacts"))
    phases.append(
        {
            "phase": "constitution_snapshot",
            "status": "ok",
            "constitution_state": constitution.get("constitution_state"),
            "missing_required_artifacts": constitution.get("missing_required_artifacts", []),
            "constitution_paths": constitution_paths,
        }
    )

    restoration: dict[str, object] = {}
    if allow_restore and (needs_restore or constitution.get("constitution_state") in {"restricted", "degraded"}):
        restoration = bootstrap_trust_restore.run_bootstrap(root, reason=reason, create_checkpoint=True)
        phases.append(
            {
                "phase": "restore_and_reanchor",
                "status": "ok",
                "report_path": restoration.get("report_path"),
                "still_missing_artifacts": restoration.get("still_missing_artifacts", []),
            }
        )
    else:
        phases.append({"phase": "restore_and_reanchor", "status": "skipped", "reason": "not_required_or_disabled"})

    constitution = compose_system_constitution(root)
    write_constitution_artifacts(root, payload=constitution)
    status = forge_status.build_status_payload(root)
    status["exit_code"] = 0
    cockpit_paths = _write_operator_rollups(root, constitution=constitution, status=status, restoration=restoration)

    health_state = _health_from_surfaces(constitution, status)
    exit_code = 0 if health_state == "healthy" else 1 if health_state == "degraded" else 2 if health_state == "restricted" else 3

    payload = {
        "schema_version": 1,
        "ts": iso_now(),
        "reason": reason,
        "seed_minimal": seed_minimal,
        "allow_restore": allow_restore,
        "phases": phases,
        "health_state": health_state,
        "constitution_state": constitution.get("constitution_state"),
        "integrity_overall": status.get("integrity_overall"),
        "runtime_data_state": (status.get("health_domain") if isinstance(status.get("health_domain"), dict) else {}).get("runtime_data"),
        "cockpit_paths": cockpit_paths,
        "exit_code": exit_code,
    }

    out_rel = ARTIFACT_DIR / f"bootstrap_report_{_safe_ts(str(payload['ts']))}.json"
    write_json(root / out_rel, payload)
    payload["report_path"] = str(out_rel)
    return payload


def node_health(root: Path) -> dict[str, object]:
    root = root.resolve()
    constitution = compose_system_constitution(root)
    write_constitution_artifacts(root, payload=constitution)
    status = forge_status.build_status_payload(root)
    state = _health_from_surfaces(constitution, status)
    report = {
        "schema_version": 1,
        "ts": iso_now(),
        "health_state": state,
        "constitution_state": constitution.get("constitution_state"),
        "integrity_overall": status.get("integrity_overall"),
        "runtime_data_state": (status.get("health_domain") if isinstance(status.get("health_domain"), dict) else {}).get("runtime_data"),
        "degraded_modes": constitution.get("degraded_modes", []),
        "missing_required_artifacts": constitution.get("missing_required_artifacts", []),
        "exit_code": 0 if state == "healthy" else 1 if state == "degraded" else 2 if state == "restricted" else 3,
    }
    out_rel = ARTIFACT_DIR / "node_health.json"
    write_json(root / out_rel, report)
    report["report_path"] = str(out_rel)
    return report


def build_incident_bundle(root: Path, *, reason: str, window: int) -> dict[str, object]:
    root = root.resolve()
    bundle_ts = _safe_ts(iso_now())
    bundle_root = root / ARTIFACT_DIR / "incident_bundles" / f"bundle_{bundle_ts}"
    include_root = bundle_root / "included"
    include_root.mkdir(parents=True, exist_ok=True)

    with _chdir(root):
        import contextlib

        with contextlib.redirect_stdout(io.StringIO()):
            forge_replay.main(["--verify", "--last-n", str(max(1, window)), "--emit-snapshot", "0"])
    status_payload = forge_status.build_status_payload(root)
    health_payload = node_health(root)

    include_patterns = [
        "glow/constitution/system_constitution.json",
        "glow/constitution/constitution_summary.json",
        "glow/forge/replay/replay_*.json",
        "glow/forge/operator/status/status_*.json",
        "glow/governor/rollup.json",
        "glow/runtime/audit_trust_state.json",
        "glow/pulse_trust/epoch_state.json",
        "glow/federation/governance_digest.json",
        "glow/federation/trust_ledger_state.json",
        "glow/operators/operator_summary.json",
        "glow/operators/current_restrictions.json",
        "glow/lab/node_truth_artifacts.json",
    ]
    bounded_jsonl = [
        ("pulse/replay_runs.jsonl", window),
        ("glow/federation/trust_ledger_events.jsonl", window),
        ("glow/governor/observability.jsonl", window),
        ("glow/operators/restoration_history.jsonl", window),
    ]

    copied: list[dict[str, object]] = []
    for pattern in include_patterns:
        matches = sorted(root.glob(pattern), key=lambda item: item.name)
        if not matches:
            continue
        selected = matches[-1]
        rel = selected.relative_to(root)
        target = include_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(selected.read_bytes())
        copied.append({"path": str(rel), "sha256": _sha256(target), "size": target.stat().st_size})

    for rel, limit in bounded_jsonl:
        rows = _bounded_jsonl(root, rel, limit=limit)
        if not rows:
            continue
        target = include_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        copied.append({"path": rel, "sha256": _sha256(target), "size": target.stat().st_size, "bounded_rows": len(rows)})

    manifest = {
        "schema_version": 1,
        "bundle_id": f"bundle_{bundle_ts}",
        "created_at": iso_now(),
        "reason": reason,
        "collection_window": window,
        "redaction_rules": {
            "full_log_copy": False,
            "bounded_jsonl_rows": window,
            "include_latest_per_glob": True,
        },
        "included_files": sorted(copied, key=lambda item: str(item["path"])),
        "status": {
            "health_state": health_payload.get("health_state"),
            "constitution_state": health_payload.get("constitution_state"),
            "integrity_overall": status_payload.get("integrity_overall"),
        },
    }
    write_json(bundle_root / "manifest.json", manifest)

    digest = hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()
    report = {
        "schema_version": 1,
        "bundle_path": str(bundle_root.relative_to(root)),
        "manifest_path": str((bundle_root / "manifest.json").relative_to(root)),
        "manifest_sha256": digest,
        "included_count": len(copied),
        "exit_code": 0,
    }
    write_json(bundle_root / "bundle_report.json", report)
    return report
