from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Mapping

STOPWORDS = {
    "the",
    "and",
    "of",
    "a",
    "an",
    "to",
    "in",
    "on",
    "for",
    "with",
    "by",
}


def _normalize(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", text.lower())
    tokens = [token for token in cleaned.split() if token]
    return " ".join(tokens)


class NarrativeCompressor:
    """Compress diary-style entries into motifs with anchor traceability."""

    def __init__(self, motif_threshold: int = 2) -> None:
        self.motif_threshold = max(1, motif_threshold)

    def compress(self, entries: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        canonical: List[Dict[str, Any]] = []
        anchors: Dict[str, List[str]] = defaultdict(list)
        motifs: Counter[str] = Counter()
        seen_fragments: Dict[str, str] = {}
        omitted: List[str] = []

        for index, entry in enumerate(entries):
            anchor = str(entry.get("id", index))
            text = str(entry.get("text", ""))
            tags = entry.get("tags") if isinstance(entry.get("tags"), list) else []
            normalized = _normalize(text)

            if normalized in seen_fragments:
                omitted.append(anchor)
                anchors[seen_fragments[normalized]].append(anchor)
                continue

            seen_fragments[normalized] = anchor
            canonical.append({"anchor": anchor, "text": text, "tags": list(tags)})
            for token in normalized.split():
                if token not in STOPWORDS:
                    motifs[token] += 1
                    anchors[token].append(anchor)

        motif_report = [
            {"motif": motif, "anchors": sorted(set(anchor_ids))}
            for motif, count in motifs.items()
            if count >= self.motif_threshold
            for anchor_ids in (anchors[motif],)
        ]
        motif_report.sort(key=lambda item: item["motif"])

        return {
            "canonical_entries": canonical,
            "motifs": motif_report,
            "anchor_index": {key: sorted(set(value)) for key, value in anchors.items()},
            "omitted": omitted,
        }


__all__ = ["NarrativeCompressor"]
