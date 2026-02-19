"""Outcome-based progress snapshots for forge baseline remediation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json

from sentientos.forge_failures import HarvestResult


NODEID_SAMPLE_LIMIT = 20


@dataclass(slots=True)
class ProgressSnapshot:
    failed_count: int
    cluster_digest: str
    nodeid_sample: list[str]
    captured_at: str


@dataclass(slots=True)
class ProgressDelta:
    failed_count_delta: int
    cluster_digest_changed: bool
    improved: bool
    notes: list[str]


def snapshot_from_harvest(harvest: HarvestResult) -> ProgressSnapshot:
    signatures = sorted(
        (
            cluster.signature.error_type,
            cluster.signature.nodeid,
            cluster.signature.message_digest,
        )
        for cluster in harvest.clusters
    )
    digest_payload = json.dumps(signatures, separators=(",", ":"), ensure_ascii=False)
    cluster_digest = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()[:16]
    nodeids = sorted({cluster.signature.nodeid for cluster in harvest.clusters if cluster.signature.nodeid and cluster.signature.nodeid != "unknown"})
    return ProgressSnapshot(
        failed_count=harvest.total_failed,
        cluster_digest=cluster_digest,
        nodeid_sample=nodeids[:NODEID_SAMPLE_LIMIT],
        captured_at=_iso_now(),
    )


def delta(prev: ProgressSnapshot, cur: ProgressSnapshot) -> ProgressDelta:
    failed_count_delta = cur.failed_count - prev.failed_count
    cluster_digest_changed = prev.cluster_digest != cur.cluster_digest
    nodeids_changed = prev.nodeid_sample != cur.nodeid_sample

    notes: list[str] = []
    improved = False
    if failed_count_delta < 0:
        improved = True
        notes.append(f"failed_count_decreased:{prev.failed_count}->{cur.failed_count}")
    elif failed_count_delta == 0 and cluster_digest_changed:
        improved = True
        notes.append("failure_landscape_shifted:cluster_digest_changed")
    elif nodeids_changed:
        improved = True
        notes.append("failure_landscape_shifted:nodeid_sample_changed")
    else:
        notes.append("no_outcome_improvement")

    return ProgressDelta(
        failed_count_delta=failed_count_delta,
        cluster_digest_changed=cluster_digest_changed,
        improved=improved,
        notes=notes,
    )


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
