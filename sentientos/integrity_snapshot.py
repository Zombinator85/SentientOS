from __future__ import annotations

from dataclasses import dataclass
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
from typing import Any, Mapping

from sentientos.receipt_anchors import ANCHORS_DIR
from sentientos.artifact_catalog import append_catalog_entry
from sentientos.receipt_chain import latest_receipt
from sentientos.schema_registry import SchemaCompatibilityError, SchemaName, latest_version, normalize
from sentientos.signed_rollups import latest_catalog_checkpoint_hash, latest_rollup_signature_hashes
from sentientos.signed_strategic import latest_sig_hash_short

SNAPSHOT_PATH = Path("glow/federation/integrity_snapshot.json")
PEER_SNAPSHOTS_DIR = Path("glow/federation/peers")
BASELINE_PATH = Path("glow/federation/baseline/federation_identity_baseline.json")


@dataclass(slots=True)
class IntegritySnapshot:
    schema_version: int
    created_at: str
    node_id: str
    repo_head_sha: str | None
    doctrine_bundle_sha256: str | None
    last_merge_receipt_id: str | None
    last_merge_receipt_hash: str | None
    last_receipt_chain_tip_hash: str | None
    last_anchor_id: str | None
    last_anchor_tip_hash: str | None
    last_anchor_payload_sha256: str | None
    anchor_public_key_id: str | None
    anchor_algorithm: str | None
    latest_rollup_sig_hashes: dict[str, str]
    latest_catalog_checkpoint_hash: str | None
    latest_strategic_sig_hash: str | None
    latest_goal_graph_hash: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "node_id": self.node_id,
            "repo_head_sha": self.repo_head_sha,
            "doctrine_bundle_sha256": self.doctrine_bundle_sha256,
            "last_merge_receipt_id": self.last_merge_receipt_id,
            "last_merge_receipt_hash": self.last_merge_receipt_hash,
            "last_receipt_chain_tip_hash": self.last_receipt_chain_tip_hash,
            "last_anchor_id": self.last_anchor_id,
            "last_anchor_tip_hash": self.last_anchor_tip_hash,
            "last_anchor_payload_sha256": self.last_anchor_payload_sha256,
            "anchor_public_key_id": self.anchor_public_key_id,
            "anchor_algorithm": self.anchor_algorithm,
            "latest_rollup_sig_hashes": dict(sorted(self.latest_rollup_sig_hashes.items())),
            "latest_catalog_checkpoint_hash": self.latest_catalog_checkpoint_hash,
            "latest_strategic_sig_hash": self.latest_strategic_sig_hash,
            "latest_goal_graph_hash": self.latest_goal_graph_hash,
        }


@dataclass(slots=True)
class IntegrityComparison:
    doctrine_match: bool
    receipt_chain_match: bool
    anchor_match: bool
    overall_status: str
    divergence_reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "doctrine_match": self.doctrine_match,
            "receipt_chain_match": self.receipt_chain_match,
            "anchor_match": self.anchor_match,
            "overall_status": self.overall_status,
            "divergence_reasons": list(self.divergence_reasons),
        }


def emit_integrity_snapshot(repo_root: Path, path: Path = SNAPSHOT_PATH) -> IntegritySnapshot:
    root = repo_root.resolve()
    local_receipt = latest_receipt(root) or {}
    latest_anchor = _latest_anchor_record(root)
    snapshot = IntegritySnapshot(
        schema_version=latest_version(SchemaName.INTEGRITY_SNAPSHOT),
        created_at=_iso_now(),
        node_id=_node_id(root),
        repo_head_sha=_git_head_sha(root),
        doctrine_bundle_sha256=_local_bundle_sha(root),
        last_merge_receipt_id=_as_str(local_receipt.get("receipt_id")),
        last_merge_receipt_hash=_as_str(local_receipt.get("receipt_hash")),
        last_receipt_chain_tip_hash=_as_str(local_receipt.get("receipt_hash")),
        last_anchor_id=_as_str(latest_anchor.get("anchor_id")),
        last_anchor_tip_hash=_as_str(latest_anchor.get("receipt_chain_tip_hash")),
        last_anchor_payload_sha256=_as_str(latest_anchor.get("anchor_payload_sha256")),
        anchor_public_key_id=_as_str(latest_anchor.get("public_key_id")),
        anchor_algorithm=_as_str(latest_anchor.get("algorithm")),
        latest_rollup_sig_hashes=latest_rollup_signature_hashes(root),
        latest_catalog_checkpoint_hash=latest_catalog_checkpoint_hash(root),
        latest_strategic_sig_hash=latest_sig_hash_short(root),
        latest_goal_graph_hash=_latest_goal_graph_hash(root),
    )
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_catalog_entry(
        root,
        kind="federation_snapshot",
        artifact_id=snapshot.node_id,
        relative_path=str(target.relative_to(root)),
        schema_name="integrity_snapshot",
        schema_version=snapshot.schema_version,
        links={"peer_id": snapshot.node_id, "head_sha": snapshot.repo_head_sha, "anchor_id": snapshot.last_anchor_id},
        summary={"status": "emitted"},
        ts=snapshot.created_at,
    )
    return snapshot


def compare_integrity_snapshots(local: Mapping[str, object], peer: Mapping[str, object]) -> IntegrityComparison:
    reasons: list[str] = []
    doctrine_match = _match_key(local, peer, "doctrine_bundle_sha256")
    receipt_match = _match_key(local, peer, "last_receipt_chain_tip_hash")
    anchor_match = _match_key(local, peer, "last_anchor_tip_hash")
    rollup_sig_match = _match_key(local, peer, "latest_rollup_sig_hashes")
    strategic_sig_match = _match_key(local, peer, "latest_strategic_sig_hash")
    goal_graph_match = _match_key(local, peer, "latest_goal_graph_hash")

    if not doctrine_match:
        reasons.append("doctrine_bundle_sha_mismatch")
    if not receipt_match:
        reasons.append("receipt_tip_mismatch")
    if not anchor_match:
        reasons.append("anchor_tip_mismatch")
    if not rollup_sig_match:
        reasons.append("rollup_signature_tip_mismatch")
    if not strategic_sig_match:
        reasons.append("strategic_signature_tip_mismatch")
    if strategic_sig_match and not goal_graph_match:
        reasons.append("goal_graph_hash_mismatch")

    comparable = any(
        _present(local.get(key)) and _present(peer.get(key))
        for key in ("doctrine_bundle_sha256", "last_receipt_chain_tip_hash", "last_anchor_tip_hash", "latest_rollup_sig_hashes", "latest_strategic_sig_hash", "latest_goal_graph_hash")
    )
    if reasons:
        status = "diverged"
    elif comparable:
        status = "ok"
    else:
        status = "unknown"
    return IntegrityComparison(
        doctrine_match=doctrine_match,
        receipt_chain_match=receipt_match,
        anchor_match=anchor_match,
        overall_status=status,
        divergence_reasons=reasons,
    )


def evaluate_peer_integrity(repo_root: Path) -> dict[str, object]:
    root = repo_root.resolve()
    local = _read_json(root / SNAPSHOT_PATH)
    if not local:
        local = emit_integrity_snapshot(root).to_dict()

    peers_dir = root / PEER_SNAPSHOTS_DIR
    summaries: list[dict[str, object]] = []
    for path in sorted(peers_dir.glob("*/integrity_snapshot.json"), key=lambda item: item.as_posix()):
        peer_payload = _read_json(path)
        if not peer_payload:
            continue
        try:
            peer_payload, _warnings = normalize(peer_payload, SchemaName.INTEGRITY_SNAPSHOT)
        except SchemaCompatibilityError:
            continue
        comparison = compare_integrity_snapshots(local, peer_payload)
        summaries.append(
            {
                "node_id": _as_str(peer_payload.get("node_id")) or path.parent.name,
                "status": comparison.overall_status,
                "divergence_reasons": comparison.divergence_reasons,
                "anchor_tip_hash": _as_str(peer_payload.get("last_anchor_tip_hash")),
            }
        )

    diverged = [row for row in summaries if row.get("status") == "diverged"]
    reasons = sorted({reason for row in diverged for reason in row.get("divergence_reasons", []) if isinstance(reason, str)})
    overall = "diverged" if diverged else ("ok" if summaries else "unknown")
    return {
        "status": overall,
        "divergence_reasons": reasons,
        "peer_summaries": summaries,
    }


def _latest_anchor_record(repo_root: Path) -> dict[str, object]:
    anchors = sorted((repo_root / ANCHORS_DIR).glob("anchor_*.json"), key=lambda item: item.name)
    if not anchors:
        return {}
    return _read_json(anchors[-1])


def _local_bundle_sha(repo_root: Path) -> str | None:
    payload = _read_json(repo_root / "glow/contracts/contract_manifest.json")
    return _as_str(payload.get("bundle_sha256"))


def _node_id(repo_root: Path) -> str:
    env = os.getenv("SENTIENTOS_NODE_ID")
    if env:
        return env
    baseline = _read_json(repo_root / BASELINE_PATH)
    baseline_digest = _as_str(baseline.get("identity_digest"))
    if baseline_digest:
        return baseline_digest
    return socket.gethostname()


def _git_head_sha(repo_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    sha = completed.stdout.strip()
    return sha or None


def _match_key(local: Mapping[str, object], peer: Mapping[str, object], key: str) -> bool:
    left_raw = local.get(key)
    right_raw = peer.get(key)
    if isinstance(left_raw, dict) and isinstance(right_raw, dict):
        left = json.dumps(left_raw, sort_keys=True, separators=(",", ":"))
        right = json.dumps(right_raw, sort_keys=True, separators=(",", ":"))
    else:
        left = _as_str(left_raw)
        right = _as_str(right_raw)
    if not left or not right:
        return True
    return left == right


def _present(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    try:
        normalized, _warnings = normalize(payload, SchemaName.INTEGRITY_SNAPSHOT)
    except SchemaCompatibilityError:
        return payload
    return normalized


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _latest_goal_graph_hash(repo_root: Path) -> str | None:
    payload = _read_json(repo_root / "glow/forge/goals/goal_graph.json")
    if not payload:
        return None
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
