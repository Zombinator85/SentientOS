from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
from typing import Any

from sentientos import artifact_catalog
from sentientos.attestation import canonical_json_bytes, read_json, read_jsonl, write_json
from sentientos.attestation_snapshot import SIGNATURE_DIR as SNAPSHOT_SIG_DIR
from sentientos.attestation_snapshot import SIGNATURE_INDEX_PATH as SNAPSHOT_SIG_INDEX
from sentientos.operator_report_attestation import SIGNATURE_DIR as OPERATOR_SIG_DIR
from sentientos.operator_report_attestation import SIGNATURE_INDEX_PATH as OPERATOR_SIG_INDEX

MANIFEST_NAME = "manifest.json"
ARTIFACTS_DIR = "artifacts"
SIGNATURES_DIR = "signatures"


@dataclass(frozen=True)
class LoadedBundle:
    root: Path
    cleanup_dir: Path | None
    source: str

    def close(self) -> None:
        if self.cleanup_dir is not None:
            for path in sorted(self.cleanup_dir.glob("**/*"), reverse=True):
                if path.is_file() or path.is_symlink():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()


def load_bundle(path: Path) -> LoadedBundle:
    resolved = path.resolve()
    if resolved.is_dir():
        return LoadedBundle(root=resolved, cleanup_dir=None, source="dir")
    if resolved.is_file() and resolved.name.endswith(".tar.gz"):
        temp = Path(tempfile.mkdtemp(prefix="sentientos-remote-bundle-"))
        with tarfile.open(resolved, "r:gz") as tar:
            members = sorted((m for m in tar.getmembers() if m.isfile()), key=lambda item: item.name)
            for member in members:
                target = temp / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = tar.extractfile(member)
                if extracted is None:
                    continue
                target.write_bytes(extracted.read())
        bundle_root = temp / "remote_bundle"
        return LoadedBundle(root=bundle_root if bundle_root.exists() else temp, cleanup_dir=temp, source="tar")
    raise ValueError(f"unsupported_bundle:{path}")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_payload(payload: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def load_manifest(bundle_root: Path) -> dict[str, object]:
    return read_json(bundle_root / MANIFEST_NAME)


def resolve_latest_artifact(repo_root: Path, *, kind: str, disk_glob: str) -> tuple[dict[str, object], str | None]:
    entry = artifact_catalog.latest(repo_root, kind)
    if entry is not None:
        payload = artifact_catalog.load_catalog_artifact(repo_root, entry)
        if payload:
            path = artifact_catalog.resolve_entry_path(repo_root, entry)
            return payload, path
    rows = sorted(repo_root.glob(disk_glob), key=lambda item: item.name)
    if not rows:
        return {}, None
    latest = rows[-1]
    return read_json(latest), str(latest.relative_to(repo_root))


def _tail_rows(path: Path, *, last_n: int) -> list[dict[str, object]]:
    rows = read_jsonl(path)
    return rows[-max(1, last_n) :] if rows else []


def export_bundle(repo_root: Path, out_dir: Path, *, last_n: int = 25) -> Path:
    root = repo_root.resolve()
    bundle_root = out_dir.resolve() / "remote_bundle"
    (bundle_root / ARTIFACTS_DIR).mkdir(parents=True, exist_ok=True)
    (bundle_root / SIGNATURES_DIR / "attestation_snapshots").mkdir(parents=True, exist_ok=True)
    (bundle_root / SIGNATURES_DIR / "operator_reports").mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, dict[str, str]] = {}
    include = {
        "attestation_snapshot.json": resolve_latest_artifact(root, kind="attestation_snapshot", disk_glob="glow/forge/attestation/snapshots/snapshot_*.json"),
        "integrity_status.json": resolve_latest_artifact(root, kind="integrity_status", disk_glob="glow/forge/integrity/status_*.json"),
        "operator_status_report.json": resolve_latest_artifact(root, kind="operator_status", disk_glob="glow/forge/operator/status/status_*.json"),
        "operator_replay_report.json": resolve_latest_artifact(root, kind="operator_replay", disk_glob="glow/forge/replay/replay_*.json"),
    }
    for name, (payload, _src_path) in include.items():
        if not payload:
            continue
        rel = Path(ARTIFACTS_DIR) / name
        write_json(bundle_root / rel, payload)
        artifacts[name] = {"path": str(rel), "sha256": sha256_file(bundle_root / rel)}

    snapshot_rows = _tail_rows(root / SNAPSHOT_SIG_INDEX, last_n=last_n)
    operator_rows = _tail_rows(root / OPERATOR_SIG_INDEX, last_n=last_n)
    _write_sig_rows(root, bundle_root, "attestation_snapshots", snapshot_rows, SNAPSHOT_SIG_DIR)
    _write_sig_rows(root, bundle_root, "operator_reports", operator_rows, OPERATOR_SIG_DIR)

    manifest = {
        "schema_version": 1,
        "node_id": _node_id(root),
        "exported_at": _iso_now(),
        "artifacts": artifacts,
        "signature_stream_tips": {
            "attestation_snapshots": (snapshot_rows[-1].get("sig_hash") if snapshot_rows else None),
            "operator_reports": (operator_rows[-1].get("sig_hash") if operator_rows else None),
        },
        "witness_summaries": {},
    }
    write_json(bundle_root / MANIFEST_NAME, manifest)
    return bundle_root


def _write_sig_rows(repo_root: Path, bundle_root: Path, stream_name: str, rows: list[dict[str, object]], sig_dir: Path) -> None:
    stream_dir = bundle_root / SIGNATURES_DIR / stream_name
    for index, row in enumerate(rows):
        write_json(stream_dir / f"sig_{index:03d}.json", row)
    index_rows = [json.loads(canonical_json_bytes(row).decode("utf-8")) for row in rows]
    with (stream_dir / "signatures_index.jsonl").open("w", encoding="utf-8") as handle:
        for row in index_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _node_id(repo_root: Path) -> str:
    baseline = read_json(repo_root / "glow/federation/baseline/federation_identity_baseline.json")
    value = baseline.get("identity_digest")
    return str(value) if isinstance(value, str) and value else "unknown-node"


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = ["LoadedBundle", "export_bundle", "load_bundle", "load_manifest", "sha256_file", "sha256_payload"]
