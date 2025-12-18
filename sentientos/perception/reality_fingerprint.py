"""Reality fingerprint generation and comparison."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping


class RealityFingerprinter:
    """Create and compare lightweight reality fingerprints."""

    def __init__(self, output_dir: Path | str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.fingerprint_path = self.output_dir / "reality_fingerprint.jsonl"
        self.divergence_path = self.output_dir / "reality_divergence_event.jsonl"

    def fingerprint_batch(self, perceptions: Iterable[Mapping[str, object]]) -> dict:
        summary = self._summary_vector(perceptions)
        digest = self._hash(summary)
        fingerprint = {"summary": summary, "hash": digest}
        self._write_jsonl(self.fingerprint_path, [fingerprint])
        return fingerprint

    def compare_fingerprints(self, local: Mapping[str, object], peer: Mapping[str, object], margin: float = 0.1) -> dict:
        local_summary = local.get("summary", {}) if isinstance(local, Mapping) else {}
        peer_summary = peer.get("summary", {}) if isinstance(peer, Mapping) else {}

        overlap = self._keyword_overlap(local_summary, peer_summary)
        match = local.get("hash") == peer.get("hash")
        divergence_score = 1.0 - overlap

        triggered = divergence_score > margin or not match
        if triggered:
            event = {
                "divergence_score": round(divergence_score, 3),
                "match": match,
                "local": local_summary,
                "peer": peer_summary,
            }
            self._write_jsonl(self.divergence_path, [event])

        return {"match": match, "overlap": overlap, "divergence_score": divergence_score, "triggered": triggered}

    def _summary_vector(self, perceptions: Iterable[Mapping[str, object]]) -> dict:
        keywords: set[str] = set()
        timestamp = None
        identities: set[str] = set()
        for entry in perceptions:
            entry_keywords = entry.get("keywords") if isinstance(entry, Mapping) else None
            if isinstance(entry_keywords, (list, tuple)):
                keywords.update(str(item) for item in entry_keywords if item)
            if timestamp is None and entry.get("timestamp"):
                timestamp = entry.get("timestamp")
            identity = entry.get("identity")
            if identity:
                identities.add(str(identity))
        return {
            "keywords": sorted(keywords),
            "timestamp": timestamp,
            "identity": sorted(identities),
        }

    def _hash(self, summary: Mapping[str, object]) -> str:
        encoded = json.dumps(summary, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _keyword_overlap(self, local: Mapping[str, object], peer: Mapping[str, object]) -> float:
        local_keywords = set(local.get("keywords", [])) if isinstance(local, Mapping) else set()
        peer_keywords = set(peer.get("keywords", [])) if isinstance(peer, Mapping) else set()
        if not local_keywords and not peer_keywords:
            return 1.0
        shared = local_keywords & peer_keywords
        total = local_keywords | peer_keywords
        return len(shared) / len(total) if total else 1.0

    def _write_jsonl(self, path: Path, entries: Iterable[Mapping[str, object]]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


__all__ = ["RealityFingerprinter"]
