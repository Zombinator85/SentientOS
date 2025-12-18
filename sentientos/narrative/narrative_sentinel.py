from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set


STOPWORDS = {"the", "and", "of", "a", "an", "to", "in", "on", "for", "with", "by"}


def tokenize(text: str) -> List[str]:
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", text.lower())
    return [token for token in cleaned.split() if token]


@dataclass
class NarrativeHealth:
    digest: str
    symbol_creep: bool
    verbosity: str
    motif_density: float
    escalated: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {
            "digest": self.digest,
            "symbol_creep": self.symbol_creep,
            "verbosity": self.verbosity,
            "motif_density": round(self.motif_density, 2),
            "escalated": self.escalated,
        }


class NarrativeSentinel:
    def __init__(
        self,
        digests_dir: Path,
        vetted_symbols: Optional[Set[str]] = None,
        verbosity_thresholds: tuple[int, int] = (80, 150),
        motif_threshold: float = 0.3,
    ) -> None:
        self.digests_dir = Path(digests_dir)
        self.vetted_symbols = {symbol.lower() for symbol in vetted_symbols} if vetted_symbols else set()
        self.verbosity_thresholds = verbosity_thresholds
        self.motif_threshold = motif_threshold

    def _symbol_creep(self, tokens: Iterable[str]) -> bool:
        if not self.vetted_symbols:
            return False
        novel = [token for token in tokens if token not in self.vetted_symbols]
        return bool(novel)

    def _verbosity(self, tokens: List[str]) -> str:
        token_count = len(tokens)
        if token_count >= self.verbosity_thresholds[1]:
            return "high"
        if token_count >= self.verbosity_thresholds[0]:
            return "medium"
        return "low"

    def _motif_density(self, tokens: List[str]) -> float:
        filtered = [token for token in tokens if token not in STOPWORDS]
        if not filtered:
            return 0.0
        counts = Counter(filtered)
        most_common = counts.most_common(1)[0][1]
        return most_common / len(filtered)

    def analyze_digest(self, digest_path: Path) -> NarrativeHealth:
        content = digest_path.read_text(encoding="utf-8") if digest_path.exists() else ""
        tokens = tokenize(content)
        creep = self._symbol_creep(tokens)
        verbosity = self._verbosity(tokens)
        motif_density = self._motif_density(tokens)
        escalated = creep and (verbosity == "high" or motif_density > self.motif_threshold)
        return NarrativeHealth(
            digest=digest_path.name,
            symbol_creep=creep,
            verbosity=verbosity,
            motif_density=motif_density,
            escalated=escalated,
        )

    def scan(self) -> List[NarrativeHealth]:
        reports: List[NarrativeHealth] = []
        if not self.digests_dir.exists():
            return reports
        for path in sorted(self.digests_dir.glob("*.md")):
            reports.append(self.analyze_digest(path))
        return reports

    def write_report(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8") as handle:
            for report in self.scan():
                handle.write(json.dumps(report.to_dict()) + "\n")

    def escalate(self, reports: Iterable[NarrativeHealth]) -> List[Dict[str, str]]:
        actions: List[Dict[str, str]] = []
        for report in reports:
            if report.escalated:
                actions.append(
                    {
                        "digest": report.digest,
                        "action": "notify_governance_council",
                        "reason": "severe narrative drift",
                    }
                )
        return actions
