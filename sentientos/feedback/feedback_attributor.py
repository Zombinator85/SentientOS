from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping


class FeedbackAttributor:
    """Attribute regressions and critiques to their causal subsystems."""

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.output_path = self.workspace / "feedback_trace.jsonl"

    def attribute_feedback(self, entries: Iterable[Mapping[str, object]]) -> list[dict]:
        attributed: list[dict] = []
        for entry in entries:
            attributed_entry = self._attribute_single(entry)
            attributed.append(attributed_entry)
            self._append_jsonl(attributed_entry)
        return attributed

    def _attribute_single(self, entry: Mapping[str, object]) -> dict:
        culprit = entry.get("culprit_daemon") or entry.get("daemon") or "unknown"
        patch = entry.get("responsible_patch") or entry.get("patch") or "unspecified"
        reflex = entry.get("trigger_reflex") or entry.get("reflex") or "undetermined"
        factors = entry.get("contributing_factors") or entry.get("factors") or []
        if isinstance(factors, (str, bytes)):
            factors = [str(factors)]
        links = entry.get("links") or entry.get("log_links") or []
        if isinstance(links, (str, bytes)):
            links = [str(links)]
        confidence = float(entry.get("confidence_score", 0.5))

        attributed_entry = {
            "source_type": entry.get("type", "feedback"),
            "description": entry.get("description") or entry.get("details"),
            "culprit_daemon": culprit,
            "responsible_patch": patch,
            "trigger_reflex": reflex,
            "contributing_factors": list(factors),
            "confidence_score": confidence,
            "links": list(links),
        }
        return attributed_entry

    def _append_jsonl(self, row: Mapping[str, object]) -> None:
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


__all__ = ["FeedbackAttributor"]
