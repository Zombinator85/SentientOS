from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Mapping


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, Mapping):
                records.append(dict(parsed))
    return records


def default_generate_training_batch(entries: Iterable[Mapping[str, object]]) -> list[dict]:
    batch: list[dict] = []
    for entry in entries:
        module = entry.get("module") or entry.get("component") or "unknown"
        prompt = entry.get("prompt") or entry.get("input") or f"Investigate degradation in {module}"
        failure = entry.get("failure_reason") or entry.get("failure") or "unspecified"
        batch.append(
            {
                "prompt": str(prompt),
                "target": f"Correct behaviour for {module}",
                "metadata": {"failure": str(failure), "source": "self_training_daemon"},
            }
        )
    return batch


class SelfTrainingDaemon:
    """Assemble Codex self-training corpora from degradation signals."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        threshold: float = 0.1,
        autonomy_limiter: bool = False,
        generator: Callable[[Iterable[Mapping[str, object]]], list[dict]] | None = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.threshold = threshold
        self.autonomy_limiter = autonomy_limiter
        self.generate_training_batch = generator or default_generate_training_batch
        self.scorecard_path = self.workspace / "codex_scorecard.jsonl"
        self.dataset_path = self.workspace / "retraining_dataset.jsonl"
        self.training_corpus_path = self.workspace / "codex_training_corpus.jsonl"
        self.event_log_path = self.workspace / "self_train_event.jsonl"

    def run(self) -> dict:
        scorecard_entries = _load_jsonl(self.scorecard_path)
        dataset_entries = _load_jsonl(self.dataset_path)

        degraded_entries = [entry for entry in scorecard_entries if self._is_degraded(entry)]
        degraded_entries.extend(entry for entry in dataset_entries if self._is_degraded(entry))

        synthetic_batch = self.generate_training_batch(degraded_entries)

        corpus_entries = [self._to_corpus_row(entry) for entry in degraded_entries] + synthetic_batch
        self._write_jsonl(self.training_corpus_path, corpus_entries)

        failure_types = sorted({self._failure_label(entry) for entry in degraded_entries if self._failure_label(entry)})
        affected_modules = sorted({str(entry.get("module") or entry.get("component") or "unknown") for entry in degraded_entries})
        dangerous_gaps = [entry for entry in degraded_entries if self._is_dangerous(entry)]

        event = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "corpus_size": len(corpus_entries),
            "failure_types": failure_types,
            "affected_modules": affected_modules,
            "dangerous_gaps": dangerous_gaps,
        }
        if self.autonomy_limiter and dangerous_gaps:
            event["requires_human_approval"] = True
        self._append_jsonl(self.event_log_path, event)

        return {
            "corpus_path": self.training_corpus_path,
            "event_path": self.event_log_path,
            "generated": corpus_entries,
            "event": event,
        }

    def _to_corpus_row(self, entry: Mapping[str, object]) -> dict:
        return {
            "module": entry.get("module") or entry.get("component"),
            "prompt": entry.get("prompt") or entry.get("input"),
            "failure": self._failure_label(entry),
            "metadata": {
                "degradation": self._degradation_amount(entry),
                "source": "scorecard",
            },
        }

    def _degradation_amount(self, entry: Mapping[str, object]) -> float:
        if "accuracy_drop" in entry:
            try:
                return float(entry.get("accuracy_drop", 0.0))
            except (TypeError, ValueError):
                return 0.0
        if "degradation" in entry:
            try:
                return float(entry.get("degradation", 0.0))
            except (TypeError, ValueError):
                return 0.0
        baseline = entry.get("baseline_accuracy")
        current = entry.get("current_accuracy")
        if baseline is not None and current is not None:
            try:
                return float(baseline) - float(current)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    def _failure_label(self, entry: Mapping[str, object]) -> str:
        failure = entry.get("failure_reason") or entry.get("failure") or entry.get("reason") or ""
        return str(failure).strip()

    def _is_degraded(self, entry: Mapping[str, object]) -> bool:
        return self._degradation_amount(entry) >= self.threshold

    def _is_dangerous(self, entry: Mapping[str, object]) -> bool:
        if entry.get("dangerous") or entry.get("safety_hazard"):
            return True
        return self._degradation_amount(entry) >= max(self.threshold * 2, 0.2)

    def _write_jsonl(self, path: Path, rows: Iterable[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _append_jsonl(self, path: Path, row: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


__all__ = ["SelfTrainingDaemon", "default_generate_training_batch"]
