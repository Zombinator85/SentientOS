from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping


class SymbolicHygieneMonitor:
    """Prevent slow reintroduction of deprecated or forbidden symbolic constructs."""

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.alert_path = self.workspace / "symbolic_hygiene_alerts.jsonl"

    def evaluate(
        self,
        glossary_freeze: Mapping[str, Iterable[str]],
        narrative_logs: Iterable[str],
        *,
        fragments: Iterable[str] | None = None,
        threshold: float = 0.2,
    ) -> dict[str, object]:
        forbidden_terms = set(glossary_freeze.get("forbidden", []))
        deprecated_terms = set(glossary_freeze.get("deprecated", []))
        watched_terms = forbidden_terms | deprecated_terms

        text_stream = list(narrative_logs) + list(fragments or [])
        violations = self._detect_violations(watched_terms, text_stream)
        total_tokens = max(1, sum(len(entry.split()) for entry in text_stream) or 1)
        hygiene_score = max(0.0, 1 - (len(violations) / total_tokens))

        notice_required = hygiene_score < (1 - threshold) and bool(violations)
        result = {
            "violations": violations,
            "hygiene_score": round(hygiene_score, 3),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "covenant_notice": notice_required,
        }
        if violations:
            self._write_alert(result)
        return result

    def _detect_violations(self, watched_terms: set[str], text_stream: Iterable[str]) -> list[dict[str, object]]:
        counter: Counter = Counter()
        for entry in text_stream:
            for term in watched_terms:
                if term.lower() in entry.lower():
                    counter[term] += 1
        return [
            {"term": term, "count": count}
            for term, count in sorted(counter.items(), key=lambda kv: kv[0])
        ]

    def _write_alert(self, payload: Mapping[str, object]) -> None:
        with self.alert_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")


__all__ = ["SymbolicHygieneMonitor"]
