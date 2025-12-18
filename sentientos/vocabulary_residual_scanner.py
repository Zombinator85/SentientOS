"""Non-invasive vocabulary residual scanner."""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping, Sequence

from sentientos.symbols import SymbolSnapshot


class VocabularyResidualScanner:
    """Count deprecated symbolic residues without altering sources."""

    def scan(
        self,
        payloads: Iterable[str],
        glossary_entries: Sequence[Mapping[str, object]],
        symbol_snapshots: Sequence[SymbolSnapshot],
    ) -> dict[str, object]:
        deprecated_terms = self._deprecated_terms(glossary_entries, symbol_snapshots)
        counts = Counter()
        for payload in payloads:
            text = str(payload).lower()
            for term in deprecated_terms:
                occurrences = text.count(term.lower())
                if occurrences:
                    counts[term] += occurrences

        return {
            "deprecated_terms": sorted(deprecated_terms),
            "residual_counts": dict(counts),
            "lint_failure": False,
        }

    def _deprecated_terms(
        self, glossary_entries: Sequence[Mapping[str, object]], symbol_snapshots: Sequence[SymbolSnapshot]
    ) -> set[str]:
        terms: set[str] = set()
        for entry in glossary_entries:
            term = str(entry.get("term") or entry.get("symbol") or "").strip()
            if not term:
                continue
            status = str(entry.get("status", "")).lower()
            if status in {"deprecated", "forbidden"}:
                terms.add(term)
        for snapshot in symbol_snapshots:
            terms.update(snapshot.deprecated)
        return terms


__all__ = ["VocabularyResidualScanner"]
