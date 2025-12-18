from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping


class DoctrineSynthesizer:
    """Highlight drift across peer doctrines and propose a canonical median."""

    def __init__(self, *, candidate_log: str | Path | None = None) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.candidate_log = Path(candidate_log) if candidate_log else repo_root / "council" / "doctrine_candidates.jsonl"
        self.candidate_log.parent.mkdir(parents=True, exist_ok=True)
        self.candidate_log.touch(exist_ok=True)

    def synthesize(self, peer_doctrines: Iterable[Mapping[str, str]]) -> dict[str, object]:
        frequencies: MutableMapping[str, Counter[str]] = {}
        peer_doctrine_list = list(peer_doctrines)
        for doctrine in peer_doctrine_list:
            for concept, value in doctrine.items():
                counter = frequencies.setdefault(concept, Counter())
                counter[str(value).strip().lower()] += 1

        divergences: list[dict[str, object]] = []
        canonical: dict[str, str] = {}
        for concept, counter in sorted(frequencies.items()):
            most_common = counter.most_common()
            canonical_value = most_common[0][0] if most_common else ""
            canonical[concept] = canonical_value
            if len(counter) > 1:
                divergences.append(
                    {
                        "concept": concept,
                        "variants": {variant: count for variant, count in most_common},
                    }
                )

        candidate = {
            "canonical": canonical,
            "divergences": divergences,
            "peer_count": len(peer_doctrine_list),
            "rationale": self._rationale(divergences),
        }
        self._log_candidate(candidate)
        return candidate

    def _rationale(self, divergences: Iterable[Mapping[str, object]]) -> str:
        divergence_list = list(divergences)
        if not divergence_list:
            return "Peers agree; canonical doctrine chosen by majority vote."
        concepts = ", ".join(sorted({str(entry.get("concept")) for entry in divergence_list}))
        return f"Divergence detected for: {concepts}. Selected majority-backed values."

    def _log_candidate(self, payload: Mapping[str, object]) -> None:
        with self.candidate_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


__all__ = ["DoctrineSynthesizer"]
