from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

DEFAULT_REFERRAL_PATH = Path("council_case_referral.jsonl")


def _load_jsonl(source: str | Path | Sequence[Mapping[str, object]] | None) -> list[dict]:
    if source is None:
        return []
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            return []
        records: list[dict] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    records.append(payload)
        return records
    return [dict(entry) for entry in source]


def _witness_factor(entry: Mapping[str, object]) -> float:
    approvals = float(entry.get("witness_approvals", 0) or 0)
    rejections = float(entry.get("witness_rejections", 0) or 0)
    total = approvals + rejections
    if total == 0:
        return 0.5
    return approvals / total


def _integration_factor(
    entry: Mapping[str, object], perception_snapshots: Iterable[Mapping[str, object]]
) -> float:
    hits = float(entry.get("integration_memory_hits", 0) or 0)
    claim = str(entry.get("claim", ""))
    for snapshot in perception_snapshots:
        if snapshot.get("claim") == claim:
            hits += float(snapshot.get("frequency", 0) or 0)
    return min(1.0, hits / 5.0) if hits else 0.0


def _federation_weight(
    claim: str, peer_logs: Iterable[Mapping[str, object]]
) -> tuple[float, list[str]]:
    stance_by_peer: dict[str, str] = {}
    for entry in peer_logs:
        if entry.get("claim") != claim:
            continue
        peer = str(entry.get("peer", "")) or "peer"
        stance_by_peer[peer] = str(entry.get("stance", "")).lower()
    if not stance_by_peer:
        return 0.0, []
    supporters = [
        peer
        for peer, stance in stance_by_peer.items()
        if stance in {"agree", "support", "true", "affirm"}
    ]
    weight = len(supporters) / len(stance_by_peer)
    return weight, supporters


def _confidence_score(witness: float, memory: float, federation: float) -> float:
    return round(min(1.0, (witness * 0.5) + (memory * 0.3) + (federation * 0.2)), 2)


def adjudicate_conflicts(
    conflict_path: str | Path,
    peer_logs: str | Path | Sequence[Mapping[str, object]],
    perception_snapshots: str | Path | Sequence[Mapping[str, object]],
    *,
    referrals_path: str | Path | None = None,
) -> list[dict]:
    """Evaluate contested claims using witness, memory, and federation signals."""

    conflicts = _load_jsonl(conflict_path)
    peers = _load_jsonl(peer_logs)
    snapshots = _load_jsonl(perception_snapshots)
    referrals_destination = Path(referrals_path) if referrals_path else DEFAULT_REFERRAL_PATH

    verdicts: list[dict] = []
    referrals: list[dict] = []

    for conflict in conflicts:
        claim = str(conflict.get("claim", "")).strip()
        if not claim:
            continue

        witness = _witness_factor(conflict)
        memory = _integration_factor(conflict, snapshots)
        federation, supporters = _federation_weight(claim, peers)
        confidence = _confidence_score(witness, memory, federation)

        verdict: str
        if confidence >= 0.65:
            verdict = "true"
        elif confidence <= 0.35:
            verdict = "false"
        else:
            verdict = "inconclusive"

        sources = set(supporters)
        if conflict.get("witness_signatures"):
            sources.add("witness-signatures")
        elif conflict.get("witness_checksum"):
            sources.add("witness-checksum")
        if memory:
            sources.add("memory-pattern")

        record = {
            "claim": claim,
            "verdict": verdict,
            "confidence": confidence,
            "sources": sorted(sources) if sources else [],
        }
        verdicts.append(record)

        if verdict == "inconclusive":
            referrals.append({
                "claim": claim,
                "reason": "insufficient consensus",
                "witness_factor": witness,
                "integration_factor": memory,
                "federation_weight": federation,
            })

    if referrals:
        referrals_destination.parent.mkdir(parents=True, exist_ok=True)
        with referrals_destination.open("a", encoding="utf-8") as handle:
            for entry in referrals:
                handle.write(json.dumps(entry) + "\n")

    return verdicts


__all__ = ["adjudicate_conflicts"]
