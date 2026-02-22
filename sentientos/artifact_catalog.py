from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

from sentientos.schema_registry import SchemaCompatibilityError, SchemaName, normalize
from sentientos.artifact_retention import resolve_redirect

CATALOG_PATH = Path("pulse/artifact_catalog.jsonl")
REBUILD_REPORTS_DIR = Path("glow/forge/reports")
CATALOG_SCHEMA_VERSION = 1

_KIND_TO_SCHEMA: dict[str, str] = {
    "incident": SchemaName.INCIDENT,
    "trace": SchemaName.GOVERNANCE_TRACE,
    "remediation_pack": SchemaName.REMEDIATION_PACK,
    "remediation_run": SchemaName.REMEDIATION_RUN,
    "orchestrator_tick": SchemaName.ORCHESTRATOR_TICK,
    "receipt": SchemaName.RECEIPT,
    "anchor": SchemaName.ANCHOR,
    "audit_report": SchemaName.AUDIT_CHAIN_REPORT,
    "federation_snapshot": SchemaName.INTEGRITY_SNAPSHOT,
}


def append_catalog_entry(
    repo_root: Path,
    *,
    kind: str,
    artifact_id: str,
    relative_path: str,
    schema_name: str,
    schema_version: int,
    links: dict[str, object] | None = None,
    summary: dict[str, object] | None = None,
    ts: str | None = None,
) -> dict[str, object]:
    root = repo_root.resolve()
    row = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "ts": ts or _iso_now(),
        "kind": kind,
        "id": artifact_id,
        "path": relative_path,
        "schema_name": schema_name,
        "schema_version_artifact": schema_version,
        "links": _normalize_links(links or {}),
        "summary": _deterministic_summary(summary or {}),
    }
    path = root / CATALOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def recent(repo_root: Path, kind: str, *, limit: int = 25) -> list[dict[str, object]]:
    rows = [row for row in _entries(repo_root) if str(row.get("kind")) == kind]
    rows.sort(key=_sort_key)
    return rows[-max(1, limit) :]


def latest(repo_root: Path, kind: str) -> dict[str, object] | None:
    rows = recent(repo_root, kind, limit=1)
    return rows[-1] if rows else None


def latest_for_incident(repo_root: Path, incident_id: str, *, kind: str) -> dict[str, object] | None:
    return _latest_by_link(repo_root, kind, "incident_id", incident_id)


def latest_for_trace(repo_root: Path, trace_id: str, *, kind: str) -> dict[str, object] | None:
    return _latest_by_link(repo_root, kind, "trace_id", trace_id)


def latest_quarantine_incident(repo_root: Path) -> dict[str, object] | None:
    rows = [row for row in _entries(repo_root) if str(row.get("kind")) == "incident"]
    rows.sort(key=_sort_key)
    for row in reversed(rows):
        links = row.get("links") if isinstance(row.get("links"), dict) else {}
        if bool(links.get("quarantine_activated")):
            return row
    return None


def latest_successful_remediation_run(repo_root: Path, pack_id: str) -> dict[str, object] | None:
    rows = [row for row in _entries(repo_root) if str(row.get("kind")) == "remediation_run"]
    rows.sort(key=_sort_key)
    for row in reversed(rows):
        links = row.get("links") if isinstance(row.get("links"), dict) else {}
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        if str(links.get("pack_id") or "") == pack_id and str(summary.get("status") or "") == "completed":
            return row
    return None


def latest_anchor(repo_root: Path) -> dict[str, object] | None:
    return latest(repo_root, "anchor")


def latest_witness_status(repo_root: Path) -> dict[str, object] | None:
    entry = latest(repo_root, "witness_publish")
    return load_catalog_artifact(repo_root, entry) if entry is not None else None


def rebuild_catalog_from_disk(repo_root: Path, *, root_dirs: list[Path] | None = None, include_archives: bool = False) -> dict[str, object]:
    root = repo_root.resolve()
    directories = [Path("glow/forge"), Path("glow/federation"), Path("pulse")] if root_dirs is None else list(root_dirs)
    existing = _entries(root)
    seen = {_entry_key(row) for row in existing}
    discovered = _discover_entries(root, include_archives=include_archives)
    appended = 0
    for row in discovered:
        key = _entry_key(row)
        if key in seen:
            continue
        append_catalog_entry(
            root,
            kind=str(row["kind"]),
            artifact_id=str(row["id"]),
            relative_path=str(row["path"]),
            schema_name=str(row["schema_name"]),
            schema_version=int(row["schema_version_artifact"]),
            links=row.get("links") if isinstance(row.get("links"), dict) else {},
            summary=row.get("summary") if isinstance(row.get("summary"), dict) else {},
            ts=str(row.get("ts") or _iso_now()),
        )
        seen.add(key)
        appended += 1
    report = {
        "schema_version": 1,
        "generated_at": _iso_now(),
        "catalog_path": str(CATALOG_PATH),
        "root_dirs": [str(item) for item in directories],
        "include_archives": include_archives,
        "existing_entries": len(existing),
        "discovered_entries": len(discovered),
        "appended_entries": appended,
    }
    report_path = root / REBUILD_REPORTS_DIR / f"artifact_catalog_rebuild_{_safe_ts(report['generated_at'])}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path.relative_to(root))
    return report


def load_catalog_artifact(repo_root: Path, entry: dict[str, object]) -> dict[str, object] | None:
    path = _entry_path(repo_root, entry)
    if path is None:
        return None
    payload = _load_json(path)
    if not payload:
        return None
    schema_name = _optional_str(entry.get("schema_name"))
    if schema_name in _KIND_TO_SCHEMA.values():
        try:
            payload, _warnings = normalize(payload, schema_name)
        except SchemaCompatibilityError:
            return payload
    payload["_catalog_path"] = str(path.relative_to(repo_root.resolve()))
    return payload


def resolve_entry_path(repo_root: Path, entry: dict[str, object]) -> str | None:
    path = _entry_path(repo_root, entry)
    if path is None:
        return None
    if path.exists():
        return str(path.relative_to(repo_root.resolve()))
    rel = _optional_str(entry.get("path"))
    if not rel:
        return None
    return resolve_redirect(repo_root, rel)


def _discover_entries(repo_root: Path, *, include_archives: bool = False) -> list[dict[str, object]]:
    root = repo_root.resolve()
    entries: list[dict[str, object]] = []
    entries.extend(_discover_json_entries(root, root / "glow/forge/incidents", "incident", "incident_id"))
    entries.extend(_discover_json_entries(root, root / "glow/forge/traces", "trace", "trace_id"))
    entries.extend(_discover_json_entries(root, root / "glow/forge/remediation/packs", "remediation_pack", "pack_id"))
    entries.extend(_discover_json_entries(root, root / "glow/forge/remediation/runs", "remediation_run", "run_id"))
    entries.extend(_discover_json_entries(root, root / "glow/forge/orchestrator/ticks", "orchestrator_tick", "generated_at"))
    entries.extend(_discover_json_entries(root, root / "glow/forge/sweeps", "sweep", "generated_at"))
    entries.extend(_discover_json_entries(root, root / "glow/forge/receipts", "receipt", "receipt_id"))
    entries.extend(_discover_json_entries(root, root / "glow/forge/receipts/anchors", "anchor", "anchor_id"))
    entries.extend(_discover_json_entries(root, root / "glow/forge/audit_reports", "audit_report", "created_at"))

    if include_archives:
        entries.extend(_discover_json_entries(root, root / "glow/forge/archive/tick", "archive_tick", "generated_at"))
        entries.extend(_discover_json_entries(root, root / "glow/forge/archive/sweep", "archive_sweep", "generated_at"))
        entries.extend(_discover_json_entries(root, root / "glow/forge/archive/run", "archive_run", "generated_at"))
    for fixed in (root / "glow/federation/integrity_snapshot.json", root / "glow/federation/anchor_witness_status.json"):
        payload = _load_json(fixed)
        if not payload:
            continue
        kind = "federation_snapshot" if fixed.name == "integrity_snapshot.json" else "witness_publish"
        entries.append(_build_entry_from_payload(root, kind, payload, fixed))
    for peer in sorted((root / "glow/federation/peers").glob("*/integrity_snapshot.json"), key=lambda item: item.as_posix()):
        payload = _load_json(peer)
        if payload:
            entries.append(_build_entry_from_payload(root, "federation_snapshot", payload, peer))
    entries.sort(key=_sort_key)
    return entries


def _discover_json_entries(repo_root: Path, base_dir: Path, kind: str, id_field: str) -> list[dict[str, object]]:
    if not base_dir.exists():
        return []
    rows: list[dict[str, object]] = []
    for path in sorted(base_dir.glob("*.json"), key=lambda item: item.name):
        payload = _load_json(path)
        if not payload:
            continue
        if id_field not in payload and id_field == "generated_at":
            payload[id_field] = payload.get("generated_at")
        rows.append(_build_entry_from_payload(repo_root, kind, payload, path))
    return rows


def _build_entry_from_payload(repo_root: Path, kind: str, payload: dict[str, object], path: Path) -> dict[str, object]:
    root = repo_root.resolve()
    created_at = _optional_str(payload.get("created_at")) or _optional_str(payload.get("generated_at")) or _iso_now()
    artifact_id = _artifact_id(kind, payload, path)
    links = {
        "incident_id": payload.get("incident_id"),
        "trace_id": payload.get("governance_trace_id") or payload.get("trace_id"),
        "pack_id": payload.get("pack_id") or payload.get("remediation_pack_id"),
        "run_id": payload.get("run_id"),
        "pr_number": payload.get("pr_number"),
        "head_sha": payload.get("head_sha"),
        "receipt_hash": payload.get("receipt_hash"),
        "anchor_id": payload.get("anchor_id"),
        "peer_id": payload.get("node_id") or payload.get("peer_id"),
    }
    schema_name = _KIND_TO_SCHEMA.get(kind, kind)
    schema_version = payload.get("schema_version") if isinstance(payload.get("schema_version"), int) else 1
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "ts": created_at,
        "kind": kind,
        "id": artifact_id,
        "path": str(path.relative_to(root)),
        "schema_name": schema_name,
        "schema_version_artifact": schema_version,
        "links": _normalize_links(links),
        "summary": _deterministic_summary(_summary_from_payload(kind, payload)),
    }


def _artifact_id(kind: str, payload: dict[str, object], path: Path) -> str:
    for key in ("incident_id", "trace_id", "pack_id", "run_id", "anchor_id", "receipt_id", "node_id", "generated_at", "created_at"):
        value = _optional_str(payload.get(key))
        if value:
            return value
    return f"{kind}:{path.name}"


def _summary_from_payload(kind: str, payload: dict[str, object]) -> dict[str, object]:
    if kind in {"remediation_pack", "remediation_run"}:
        return {"status": payload.get("status"), "primary_reason": payload.get("primary_reason")}
    if kind == "trace":
        return {"final_decision": payload.get("final_decision"), "final_reason": payload.get("final_reason")}
    if kind == "incident":
        return {"severity": payload.get("severity"), "enforcement_mode": payload.get("enforcement_mode")}
    if kind == "witness_publish":
        return {"witness_status": payload.get("witness_status"), "witness_failure": payload.get("witness_failure")}
    return {"status": payload.get("status")}


def _latest_by_link(repo_root: Path, kind: str, link_key: str, link_value: str) -> dict[str, object] | None:
    rows = [row for row in _entries(repo_root) if str(row.get("kind")) == kind]
    rows.sort(key=_sort_key)
    for row in reversed(rows):
        links = row.get("links") if isinstance(row.get("links"), dict) else {}
        if str(links.get(link_key) or "") == link_value:
            return row
    return None


def _entries(repo_root: Path) -> list[dict[str, object]]:
    path = repo_root.resolve() / CATALOG_PATH
    rows = _read_jsonl(path)
    if rows:
        return rows
    return _discover_entries(repo_root)


def _entry_key(row: dict[str, object]) -> tuple[str, str, str]:
    return (str(row.get("kind") or ""), str(row.get("id") or ""), str(row.get("path") or ""))


def _entry_path(repo_root: Path, entry: dict[str, object]) -> Path | None:
    rel = _optional_str(entry.get("path"))
    if not rel:
        return None
    raw_path = repo_root.resolve() / rel
    if raw_path.exists():
        return raw_path
    redirected = resolve_redirect(repo_root, rel)
    return (repo_root.resolve() / redirected) if redirected else raw_path


def _sort_key(row: dict[str, object]) -> tuple[str, str, str]:
    return (str(row.get("ts") or ""), str(row.get("kind") or ""), str(row.get("id") or ""))


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_links(links: dict[str, object]) -> dict[str, object]:
    keep = {"incident_id", "trace_id", "pack_id", "run_id", "pr_number", "head_sha", "receipt_hash", "anchor_id", "peer_id", "quarantine_activated"}
    out: dict[str, object] = {}
    for key in sorted(keep):
        if key not in links:
            continue
        value = links.get(key)
        if isinstance(value, (str, int, bool)) and value != "":
            out[key] = value
    return out


def _deterministic_summary(summary: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key in sorted(summary):
        value = summary[key]
        if isinstance(value, str):
            normalized[key] = value[:120]
        elif isinstance(value, (int, bool)):
            normalized[key] = value
    return normalized


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _safe_ts(value: str) -> str:
    return value.replace(":", "-").replace(".", "-")


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
