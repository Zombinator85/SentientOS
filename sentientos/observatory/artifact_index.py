from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from sentientos.attestation import iso_now, read_json, read_jsonl, write_json
from .broad_lane_latest import emit_broad_lane_latest_pointers

PointerState = Literal["current", "superseded", "missing", "stale", "unavailable"]


@dataclass(frozen=True)
class SurfaceSpec:
    name: str
    domain: str
    kind: str
    latest_mode: Literal["single", "glob"]
    paths: tuple[str, ...]
    freshness_hours: int
    metadata_keys: tuple[str, ...]
    created_at_keys: tuple[str, ...]


SURFACE_SPECS: tuple[SurfaceSpec, ...] = (
    SurfaceSpec(
        name="contract_status",
        domain="contracts",
        kind="contract_status",
        latest_mode="single",
        paths=("glow/contracts/contract_status.json",),
        freshness_hours=24,
        metadata_keys=("generated_at", "git_sha"),
        created_at_keys=("generated_at",),
    ),
    SurfaceSpec(
        name="strict_audit_status",
        domain="contracts",
        kind="strict_audit_status",
        latest_mode="single",
        paths=("glow/contracts/strict_audit_status.json",),
        freshness_hours=24,
        metadata_keys=("generated_at", "bucket", "readiness_class", "blocking", "degraded"),
        created_at_keys=("generated_at",),
    ),
    SurfaceSpec(
        name="protected_corridor",
        domain="contracts",
        kind="protected_corridor_report",
        latest_mode="single",
        paths=("glow/contracts/protected_corridor_report.json",),
        freshness_hours=24,
        metadata_keys=("generated_at",),
        created_at_keys=("generated_at",),
    ),
    SurfaceSpec(
        name="simulation_baseline",
        domain="simulation",
        kind="simulation_baseline_report",
        latest_mode="single",
        paths=("glow/simulation/baseline_report.json",),
        freshness_hours=24,
        metadata_keys=("generated_at", "seed", "scenario", "profile"),
        created_at_keys=("generated_at",),
    ),
    SurfaceSpec(
        name="formal_verification",
        domain="formal",
        kind="formal_check_summary",
        latest_mode="single",
        paths=("glow/formal/formal_check_summary.json",),
        freshness_hours=24,
        metadata_keys=("generated_at", "specs"),
        created_at_keys=("generated_at",),
    ),
    SurfaceSpec(
        name="wan_gate",
        domain="wan",
        kind="wan_release_gate_report",
        latest_mode="single",
        paths=("glow/lab/wan_gate/wan_gate_report.json",),
        freshness_hours=24,
        metadata_keys=("generated_at", "profile", "aggregate_outcome", "scenario_count"),
        created_at_keys=("generated_at",),
    ),
    SurfaceSpec(
        name="wan_truth_oracle",
        domain="wan",
        kind="wan_truth_oracle_summary",
        latest_mode="glob",
        paths=("glow/lab/wan/*/wan_truth/truth_oracle_summary.json",),
        freshness_hours=24,
        metadata_keys=("cluster_truth", "truth_score"),
        created_at_keys=("generated_at",),
    ),
    SurfaceSpec(
        name="remote_preflight_trend",
        domain="wan",
        kind="remote_preflight_trend_report",
        latest_mode="single",
        paths=("glow/lab/remote_preflight/remote_preflight_trend_report.json",),
        freshness_hours=72,
        metadata_keys=("generated_at", "window_entries", "preflight_success_count"),
        created_at_keys=("generated_at",),
    ),
    SurfaceSpec(
        name="fleet_observatory",
        domain="observatory",
        kind="fleet_health_summary",
        latest_mode="single",
        paths=("glow/observatory/fleet_health_summary.json",),
        freshness_hours=24,
        metadata_keys=("generated_at", "release_readiness", "degradation_count"),
        created_at_keys=("generated_at",),
    ),
    SurfaceSpec(
        name="run_tests_broad_lane",
        domain="observatory",
        kind="broad_lane_run_tests_latest_pointer",
        latest_mode="single",
        paths=("glow/observatory/broad_lane/run_tests_latest_pointer.json",),
        freshness_hours=24,
        metadata_keys=("pointer_state", "lane_state", "status"),
        created_at_keys=("generated_at",),
    ),
    SurfaceSpec(
        name="mypy_broad_lane",
        domain="observatory",
        kind="broad_lane_mypy_latest_pointer",
        latest_mode="single",
        paths=("glow/observatory/broad_lane/mypy_latest_pointer.json",),
        freshness_hours=24,
        metadata_keys=("pointer_state", "lane_state", "status"),
        created_at_keys=("generated_at",),
    ),
    SurfaceSpec(
        name="broad_lane_latest_summary",
        domain="observatory",
        kind="broad_lane_latest_summary",
        latest_mode="single",
        paths=("glow/observatory/broad_lane/broad_lane_latest_summary.json",),
        freshness_hours=24,
        metadata_keys=("pointer_state", "broad_baseline_green"),
        created_at_keys=("generated_at",),
    ),
    SurfaceSpec(
        name="incident_summary",
        domain="incident",
        kind="incident_bundle",
        latest_mode="glob",
        paths=("glow/incidents/bundle_*.json",),
        freshness_hours=168,
        metadata_keys=("generated_at", "manifest_sha256", "bundle_path", "reason"),
        created_at_keys=("generated_at",),
    ),
)


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_digest(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _as_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_created_at(payload: dict[str, Any], keys: tuple[str, ...], *, fallback_path: Path) -> str | None:
    for key in keys:
        found = payload.get(key)
        if isinstance(found, str) and found:
            return found
    mtime = datetime.fromtimestamp(fallback_path.stat().st_mtime, tz=timezone.utc)
    return mtime.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _created_at_sort_key(created_at: str | None) -> tuple[int, str]:
    parsed = _as_datetime(created_at)
    if parsed is None:
        return (0, "")
    return (int(parsed.timestamp()), created_at or "")


def _status_for_latest(*, created_at: str | None, now: datetime, freshness_hours: int) -> PointerState:
    if created_at is None:
        return "unavailable"
    created_dt = _as_datetime(created_at)
    if created_dt is None:
        return "unavailable"
    age_hours = (now - created_dt).total_seconds() / 3600.0
    return "stale" if age_hours > float(freshness_hours) else "current"


def _artifact_record(root: Path, spec: SurfaceSpec, path: Path, *, is_latest: bool, latest_state: PointerState | None, now: datetime) -> dict[str, Any]:
    rel = _relative(root, path)
    payload = read_json(path)
    created_at = _extract_created_at(payload, spec.created_at_keys, fallback_path=path)
    digest = _hash_file(path)
    metadata = {key: payload.get(key) for key in spec.metadata_keys if key in payload}

    pointer_state: PointerState
    if is_latest:
        pointer_state = latest_state or _status_for_latest(created_at=created_at, now=now, freshness_hours=spec.freshness_hours)
    else:
        pointer_state = "superseded"

    return {
        "surface": spec.name,
        "domain": spec.domain,
        "artifact_type": spec.kind,
        "artifact_path": rel,
        "created_at": created_at,
        "run_id": payload.get("run_id"),
        "profile": payload.get("profile"),
        "mode": payload.get("mode"),
        "scenario": payload.get("scenario"),
        "topology": payload.get("topology"),
        "seed": payload.get("seed"),
        "digest_sha256": digest,
        "pointer_state": pointer_state,
        "metadata": metadata,
    }


def _surface_candidates(root: Path, spec: SurfaceSpec) -> list[Path]:
    paths: list[Path] = []
    if spec.latest_mode == "single":
        for rel in spec.paths:
            candidate = root / rel
            if candidate.exists() and candidate.is_file():
                paths.append(candidate)
    else:
        for pattern in spec.paths:
            paths.extend([path for path in root.glob(pattern) if path.is_file()])
    return sorted(paths, key=lambda p: _relative(root, p))


def _select_latest(root: Path, candidates: list[Path], spec: SurfaceSpec) -> Path | None:
    if not candidates:
        return None

    def _key(path: Path) -> tuple[tuple[int, str], str, str]:
        payload = read_json(path)
        created = _extract_created_at(payload, spec.created_at_keys, fallback_path=path)
        run_id = str(payload.get("run_id") or "")
        return (_created_at_sort_key(created), run_id, _relative(root, path))

    return sorted(candidates, key=_key)[-1]


def _artifact_links(root: Path, pointers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    links: list[dict[str, Any]] = []

    def _as_dict(value: object) -> dict[str, object]:
        return value if isinstance(value, dict) else {}

    def _as_list(value: object) -> list[object]:
        return value if isinstance(value, list) else []

    def _latest(surface: str) -> str | None:
        row = pointers.get(surface) if isinstance(pointers.get(surface), dict) else {}
        path = row.get("artifact_path") if isinstance(row, dict) else None
        return str(path) if isinstance(path, str) and path else None

    fleet = _latest("fleet_observatory")
    if fleet:
        for upstream in (
            "contract_status",
            "strict_audit_status",
            "protected_corridor",
            "simulation_baseline",
            "formal_verification",
            "wan_gate",
            "remote_preflight_trend",
            "wan_truth_oracle",
        ):
            up = _latest(upstream)
            if up:
                links.append({"from_surface": "fleet_observatory", "from_artifact": fleet, "to_surface": upstream, "to_artifact": up, "relation": "summarizes"})

    wan_gate = _latest("wan_gate")
    if wan_gate:
        gate_payload = read_json(root / wan_gate)
        artifacts = _as_dict(gate_payload.get("artifact_paths"))
        for key in ("contradiction_policy_report", "evidence_density_report", "release_gate_manifest"):
            value = artifacts.get(key)
            if isinstance(value, str) and value:
                links.append({"from_surface": "wan_gate", "from_artifact": wan_gate, "to_surface": "wan_gate", "to_artifact": value, "relation": "emits"})
        truth_upstream = _latest("wan_truth_oracle")
        if truth_upstream:
            links.append({"from_surface": "wan_gate", "from_artifact": wan_gate, "to_surface": "wan_truth_oracle", "to_artifact": truth_upstream, "relation": "depends_on_truth"})

    truth = _latest("wan_truth_oracle")
    if truth:
        truth_payload = read_json(root / truth)
        run_root = (root / truth).parents[2]
        evidence_manifest_path = run_root / "wan_truth" / "evidence_manifest.json"
        if evidence_manifest_path.exists():
            links.append({"from_surface": "wan_truth_oracle", "from_artifact": truth, "to_surface": "wan_truth_oracle", "to_artifact": _relative(root, evidence_manifest_path), "relation": "uses_evidence_manifest"})
            evidence_manifest = read_json(evidence_manifest_path)
            rows = _as_list(evidence_manifest.get("node_evidence"))
            for row in rows:
                if not isinstance(row, dict):
                    continue
                node_truth_path = row.get("node_truth_path")
                if isinstance(node_truth_path, str) and node_truth_path:
                    as_path = Path(node_truth_path)
                    if as_path.exists():
                        links.append({"from_surface": "wan_truth_oracle", "from_artifact": _relative(root, evidence_manifest_path), "to_surface": "wan_truth_node", "to_artifact": _relative(root, as_path), "relation": "aggregates"})

    preflight = _latest("remote_preflight_trend")
    if preflight:
        trend_payload = read_json(root / preflight)
        history = root / "glow/lab/remote_preflight/remote_preflight_history.jsonl"
        rollup = root / "glow/lab/remote_preflight/remote_preflight_rollup.json"
        if history.exists():
            lines = read_jsonl(history)
            latest_rows = lines[-20:]
            links.append({
                "from_surface": "remote_preflight_trend",
                "from_artifact": preflight,
                "to_surface": "remote_preflight_history",
                "to_artifact": _relative(root, history),
                "relation": "rolls_up",
                "contributing_runs": [
                    {
                        "scenario": row.get("scenario"),
                        "topology": row.get("topology"),
                        "seed": row.get("seed"),
                        "host_id": row.get("host_id"),
                    }
                    for row in latest_rows
                ],
            })
        if rollup.exists() and trend_payload:
            links.append({"from_surface": "remote_preflight_trend", "from_artifact": preflight, "to_surface": "remote_preflight_rollup", "to_artifact": _relative(root, rollup), "relation": "summarizes"})

    return {
        "schema_version": 1,
        "generated_at": iso_now(),
        "link_count": len(links),
        "links": links,
    }


def build_artifact_provenance_index(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    out_root = root / "glow" / "observatory"
    out_root.mkdir(parents=True, exist_ok=True)

    generated_at = iso_now()
    now = _as_datetime(generated_at) or datetime.now(timezone.utc)

    broad_lane_payload = emit_broad_lane_latest_pointers(root)

    artifact_rows: list[dict[str, Any]] = []
    latest_pointers: dict[str, dict[str, Any]] = {}

    for spec in SURFACE_SPECS:
        candidates = _surface_candidates(root, spec)
        latest = _select_latest(root, candidates, spec)

        if latest is None:
            latest_pointers[spec.name] = {
                "surface": spec.name,
                "domain": spec.domain,
                "artifact_type": spec.kind,
                "artifact_path": None,
                "created_at": None,
                "run_id": None,
                "profile": None,
                "mode": None,
                "scenario": None,
                "topology": None,
                "seed": None,
                "digest_sha256": None,
                "pointer_state": "missing",
                "freshness_hours": spec.freshness_hours,
                "latest_rule": {
                    "mode": spec.latest_mode,
                    "paths": list(spec.paths),
                    "ordering": ["created_at", "run_id", "artifact_path"],
                },
                "candidate_count": 0,
            }
            continue

        latest_payload = read_json(latest)
        latest_created = _extract_created_at(latest_payload, spec.created_at_keys, fallback_path=latest)
        latest_state = _status_for_latest(created_at=latest_created, now=now, freshness_hours=spec.freshness_hours)

        for candidate in candidates:
            artifact_rows.append(
                _artifact_record(root, spec, candidate, is_latest=(candidate == latest), latest_state=latest_state, now=now)
            )

        latest_row = next(row for row in artifact_rows if row["surface"] == spec.name and row["artifact_path"] == _relative(root, latest))
        latest_pointers[spec.name] = {
            **latest_row,
            "freshness_hours": spec.freshness_hours,
            "latest_rule": {
                "mode": spec.latest_mode,
                "paths": list(spec.paths),
                "ordering": ["created_at", "run_id", "artifact_path"],
            },
            "candidate_count": len(candidates),
        }

    index_payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "surface_count": len(SURFACE_SPECS),
        "artifact_count": len(artifact_rows),
        "artifacts": sorted(artifact_rows, key=lambda row: (str(row.get("surface") or ""), str(row.get("artifact_path") or ""))),
    }

    pointers_payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "surface_count": len(SURFACE_SPECS),
        "surfaces": dict(sorted(latest_pointers.items())),
    }

    links_payload = _artifact_links(root, latest_pointers)
    links_payload["generated_at"] = generated_at

    write_json(out_root / "artifact_index.json", index_payload)
    write_json(out_root / "latest_pointers.json", pointers_payload)
    write_json(out_root / "artifact_provenance_links.json", links_payload)

    manifest = {
        "schema_version": 1,
        "suite": "artifact_provenance_index",
        "generated_at": generated_at,
        "artifacts": {
            "artifact_index": "glow/observatory/artifact_index.json",
            "latest_pointers": "glow/observatory/latest_pointers.json",
            "artifact_provenance_links": "glow/observatory/artifact_provenance_links.json",
            "run_tests_broad_lane": "glow/observatory/broad_lane/run_tests_latest_pointer.json",
            "mypy_broad_lane": "glow/observatory/broad_lane/mypy_latest_pointer.json",
            "broad_lane_latest_summary": "glow/observatory/broad_lane/broad_lane_latest_summary.json",
        },
        "source_surface_specs": [
            {
                "surface": spec.name,
                "domain": spec.domain,
                "artifact_type": spec.kind,
                "latest_mode": spec.latest_mode,
                "paths": list(spec.paths),
                "freshness_hours": spec.freshness_hours,
            }
            for spec in SURFACE_SPECS
        ],
    }
    write_json(out_root / "artifact_index_manifest.json", manifest)

    digest_payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "artifact_index_digest": _stable_digest(index_payload),
        "latest_pointers_digest": _stable_digest(pointers_payload),
        "artifact_provenance_links_digest": _stable_digest(links_payload),
        "manifest_digest": _stable_digest(manifest),
    }
    digest_payload["artifact_provenance_digest"] = _stable_digest(digest_payload)
    write_json(out_root / "final_artifact_index_digest.json", digest_payload)

    history_path = out_root / "artifact_index_history.jsonl"
    history_rows = read_jsonl(history_path)
    history_rows.append(
        {
            "generated_at": generated_at,
            "artifact_provenance_digest": digest_payload["artifact_provenance_digest"],
            "surface_states": {name: row.get("pointer_state") for name, row in sorted(latest_pointers.items())},
        }
    )
    history_rows = history_rows[-400:]
    history_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in history_rows), encoding="utf-8")

    return {
        "schema_version": 1,
        "suite": "artifact_provenance_index",
        "status": "passed",
        "ok": True,
        "exit_code": 0,
        "artifact_paths": {
            "artifact_index": "glow/observatory/artifact_index.json",
            "latest_pointers": "glow/observatory/latest_pointers.json",
            "artifact_provenance_links": "glow/observatory/artifact_provenance_links.json",
            "run_tests_broad_lane": "glow/observatory/broad_lane/run_tests_latest_pointer.json",
            "mypy_broad_lane": "glow/observatory/broad_lane/mypy_latest_pointer.json",
            "broad_lane_latest_summary": "glow/observatory/broad_lane/broad_lane_latest_summary.json",
            "artifact_index_manifest": "glow/observatory/artifact_index_manifest.json",
            "final_artifact_index_digest": "glow/observatory/final_artifact_index_digest.json",
            "artifact_index_history": "glow/observatory/artifact_index_history.jsonl",
        },
        "surface_states": {name: row.get("pointer_state") for name, row in sorted(latest_pointers.items())},
        "broad_lane_contract": broad_lane_payload,
    }
