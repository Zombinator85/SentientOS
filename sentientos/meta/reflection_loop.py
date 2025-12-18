from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


class ReflectionLoop:
    """Aggregate mood, digests, and patches into self-reflection summaries."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        misalignment_threshold: float = 0.6,
        queue_replan: Callable[[dict], None] | None = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.summary_path = self.workspace / "self_reflection_summary.jsonl"
        self.misalignment_threshold = misalignment_threshold
        self.queue_replan = queue_replan

    def run(
        self,
        *,
        daily_digests: Sequence[Mapping[str, object]] | Path | str | None = None,
        codex_patches: Sequence[Mapping[str, object]] | Path | str | None = None,
        mood_history: Sequence[Mapping[str, object]] | Path | str | None = None,
        conflict_resolutions: Sequence[Mapping[str, object]] | Path | str | None = None,
    ) -> dict:
        digests = self._load_jsonl(daily_digests)
        patches = self._load_jsonl(codex_patches)
        moods = self._load_jsonl(mood_history)
        conflicts = self._load_jsonl(conflict_resolutions)

        tensions = self._detect_tensions(conflicts, moods)
        inefficiencies = self._planning_inefficiencies(digests, patches)
        corrections = self._correction_patterns(patches)
        coherence = self._behavioural_coherence(moods, conflicts)

        summary = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "detected_tensions": tensions,
            "planning_inefficiencies": inefficiencies,
            "correction_patterns": corrections,
            "behavioral_coherence": coherence,
        }

        misalignment_score = 1 - coherence.get("coherence_rating", 1.0)
        if misalignment_score > self.misalignment_threshold and self.queue_replan:
            replan_task = {
                "reason": "misalignment_detected",
                "misalignment_score": misalignment_score,
                "tensions": tensions,
                "inefficiencies": inefficiencies,
            }
            self.queue_replan(replan_task)
            summary["replan_queued"] = True
            summary["replan_task"] = replan_task

        self._append_jsonl(self.summary_path, summary)
        return summary

    def _detect_tensions(
        self,
        conflicts: Sequence[Mapping[str, object]],
        moods: Sequence[Mapping[str, object]],
    ) -> list[dict]:
        tensions: list[dict] = []
        for conflict in conflicts:
            if conflict.get("status") == "unresolved":
                tensions.append({"type": "unresolved_conflict", "context": conflict})
        negative_moods = [m for m in moods if str(m.get("valence", "")).startswith("neg")]
        if negative_moods:
            tensions.append({"type": "mood_dip", "count": len(negative_moods)})
        return tensions

    def _planning_inefficiencies(
        self,
        digests: Sequence[Mapping[str, object]],
        patches: Sequence[Mapping[str, object]],
    ) -> list[str]:
        inefficiencies: list[str] = []
        for digest in digests:
            if digest.get("delays"):
                inefficiencies.append("delayed_deliverables")
            if digest.get("blocked"):
                inefficiencies.append("blocked_tasks")
        for patch in patches:
            if patch.get("reverts", 0):
                inefficiencies.append("rework_detected")
        return sorted(set(inefficiencies))

    def _correction_patterns(self, patches: Sequence[Mapping[str, object]]) -> list[dict]:
        patterns: list[dict] = []
        over_corrections = [p for p in patches if p.get("over_correction")]
        under_corrections = [p for p in patches if p.get("under_correction")]
        if over_corrections:
            patterns.append({"type": "over_correction", "count": len(over_corrections)})
        if under_corrections:
            patterns.append({"type": "under_correction", "count": len(under_corrections)})
        return patterns

    def _behavioural_coherence(
        self,
        moods: Sequence[Mapping[str, object]],
        conflicts: Sequence[Mapping[str, object]],
    ) -> dict:
        calm_periods = sum(1 for mood in moods if mood.get("stability") == "steady")
        turbulence = sum(1 for conflict in conflicts if conflict.get("status") != "resolved")
        total = calm_periods + turbulence or 1
        coherence_rating = max(0.0, min(1.0, calm_periods / total))
        return {"coherence_rating": coherence_rating, "turbulence": turbulence}

    def _load_jsonl(self, source: Sequence[Mapping[str, object]] | Path | str | None) -> list[dict]:
        if source is None:
            return []
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                return []
            entries: list[dict] = []
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, Mapping):
                        entries.append(dict(parsed))
            return entries
        return [dict(item) for item in source]

    def _append_jsonl(self, path: Path, row: Mapping[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


__all__ = ["ReflectionLoop"]
