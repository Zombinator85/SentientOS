from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping


@dataclass
class BeliefVerificationResult:
    claim_id: str
    origin: str | None
    witness_score: float
    peer_agreement: float
    contradiction_penalty: float
    decay_factor: float
    confidence: float
    generated_at: str
    evidence_summary: dict[str, int]


class BeliefVerifier:
    """Validate knowledge claims or persistent beliefs across evidence sources."""

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.report_path = self.workspace / "belief_verification_report.jsonl"

    def verify(
        self,
        claim_id: str,
        claim: Mapping[str, object],
        *,
        witness_records: Iterable[Mapping[str, object]] = (),
        federation_agreements: Iterable[Mapping[str, object]] = (),
        contradictions: Iterable[Mapping[str, object]] = (),
        ttl_seconds: int | None = None,
        observed_at: datetime | None = None,
    ) -> BeliefVerificationResult:
        witness_list = list(witness_records)
        peer_list = list(federation_agreements)
        contradiction_list = list(contradictions)

        origin = claim.get("origin") if isinstance(claim, Mapping) else None
        witness_score = self._score_witness(witness_list)
        peer_agreement = self._score_peer_agreement(peer_list)
        contradiction_penalty = self._score_contradictions(contradiction_list, witness_list)
        decay_factor = self._score_decay(ttl_seconds, observed_at or claim.get("observed_at"))

        confidence = round(
            0.4 * witness_score
            + 0.3 * peer_agreement
            + 0.2 * (1 - contradiction_penalty)
            + 0.1 * decay_factor,
            3,
        )

        evidence_summary = {
            "witness_records": len(witness_list),
            "federation_peers": len(peer_list),
            "contradictions": len(contradiction_list),
        }

        result = BeliefVerificationResult(
            claim_id=claim_id,
            origin=str(origin) if origin is not None else None,
            witness_score=round(witness_score, 3),
            peer_agreement=round(peer_agreement, 3),
            contradiction_penalty=round(contradiction_penalty, 3),
            decay_factor=round(decay_factor, 3),
            confidence=confidence,
            generated_at=datetime.utcnow().isoformat() + "Z",
            evidence_summary=evidence_summary,
        )
        self._write_report(result)
        return result

    def _write_report(self, result: BeliefVerificationResult) -> None:
        entry = {
            "claim_id": result.claim_id,
            "origin": result.origin,
            "witness_score": result.witness_score,
            "peer_agreement": result.peer_agreement,
            "contradiction_penalty": result.contradiction_penalty,
            "decay_factor": result.decay_factor,
            "confidence": result.confidence,
            "generated_at": result.generated_at,
            "evidence_summary": result.evidence_summary,
        }
        with self.report_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def _score_witness(self, witness_records: Iterable[Mapping[str, object]]) -> float:
        records = list(witness_records)
        if not records:
            return 0.0
        support = sum(1 for record in records if str(record.get("verdict", "")).lower() == "support")
        return support / len(records)

    def _score_peer_agreement(self, federation_agreements: Iterable[Mapping[str, object]]) -> float:
        peers = list(federation_agreements)
        if not peers:
            return 0.0
        aligned = sum(1 for peer in peers if bool(peer.get("agree", False)))
        return aligned / len(peers)

    def _score_contradictions(
        self,
        contradictions: Iterable[Mapping[str, object]],
        witness_records: Iterable[Mapping[str, object]],
    ) -> float:
        contradiction_list = list(contradictions)
        evidence_pool = len(list(witness_records)) + len(contradiction_list)
        if evidence_pool == 0:
            return 0.0
        return min(1.0, len(contradiction_list) / evidence_pool)

    def _score_decay(self, ttl_seconds: int | None, observed_at: datetime | object | None) -> float:
        if not ttl_seconds:
            return 1.0
        observed_dt: datetime | None = None
        if isinstance(observed_at, datetime):
            observed_dt = observed_at
        elif isinstance(observed_at, str):
            try:
                observed_dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            except ValueError:
                observed_dt = None
        if not observed_dt:
            return 1.0
        elapsed = datetime.utcnow() - observed_dt
        remaining = max(0.0, ttl_seconds - elapsed.total_seconds())
        return max(0.0, min(1.0, remaining / ttl_seconds))


__all__ = ["BeliefVerifier", "BeliefVerificationResult"]
