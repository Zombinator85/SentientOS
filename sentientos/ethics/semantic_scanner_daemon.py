from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence


def _tokenize(text: str) -> list[str]:
    return [token for token in text.lower().replace("/", " ").split() if token]


class SemanticScannerDaemon:
    """Guard memory ingestion against toxic or destabilizing symbols."""

    def __init__(
        self,
        toxic_registry: Iterable[str],
        *,
        escalation_threshold: float = 0.2,
        repeat_threshold: int = 3,
        alert_log: str | Path | None = None,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.registry = {motif.lower() for motif in toxic_registry}
        self.escalation_threshold = max(0.0, float(escalation_threshold))
        self.repeat_threshold = max(1, int(repeat_threshold))
        self.alert_log = Path(alert_log) if alert_log else repo_root / "logs" / "semantic_scanner_alerts.jsonl"
        self.alert_log.parent.mkdir(parents=True, exist_ok=True)
        self.alert_log.touch(exist_ok=True)

    def scan(self, entries: Sequence[str]) -> dict[str, object]:
        risks: list[dict[str, object]] = []
        motif_counters: MutableMapping[str, int] = defaultdict(int)

        for index, entry in enumerate(entries):
            tokens = _tokenize(entry)
            hits = [token for token in tokens if token in self.registry]
            for token in hits:
                motif_counters[token] += 1
            risk_score = (len(hits) / max(len(tokens), 1)) if tokens else 0.0
            risks.append(
                {
                    "index": index,
                    "risk": round(risk_score, 3),
                    "motifs": sorted(set(hits)),
                    "text": entry,
                }
            )

        cascade_alerts = [motif for motif, count in motif_counters.items() if count >= self.repeat_threshold]
        max_risk = max((row["risk"] for row in risks), default=0.0)
        covenant_alert = bool(max_risk >= self.escalation_threshold or cascade_alerts)

        report = {
            "risks": risks,
            "max_risk": round(max_risk, 3),
            "cascade_alerts": sorted(cascade_alerts),
            "covenant_alert": covenant_alert,
        }
        if covenant_alert:
            self._log_alert(report)
        return report

    def _log_alert(self, payload: Mapping[str, object]) -> None:
        with self.alert_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


__all__ = ["SemanticScannerDaemon"]
