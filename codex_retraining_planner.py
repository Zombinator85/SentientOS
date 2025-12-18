from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence


@dataclass
class CodexRetrainingPlanner:
    """Assemble retraining artifacts from long-running Codex rejection logs."""

    rejection_logs: list[Mapping[str, object]] = field(default_factory=list)
    diffs: list[Mapping[str, object]] = field(default_factory=list)

    def __init__(
        self,
        rejection_logs: str | Path | Sequence[Mapping[str, object]] | None = None,
        diffs: str | Path | Sequence[Mapping[str, object]] | None = None,
    ) -> None:
        self.rejection_logs = self._load_jsonl(rejection_logs)
        self.diffs = self._load_jsonl(diffs)

    @staticmethod
    def _load_jsonl(source: str | Path | Sequence[Mapping[str, object]] | None) -> list[dict]:
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
                    if isinstance(parsed, dict):
                        entries.append(parsed)
            return entries
        return [dict(item) for item in source]

    def cluster_failure_reasons(self) -> dict[str, list[Mapping[str, object]]]:
        clusters: dict[str, list[Mapping[str, object]]] = defaultdict(list)
        for entry in self.rejection_logs:
            reason = str(
                entry.get("failure_reason")
                or entry.get("rejection_reason")
                or entry.get("reason")
                or "unspecified"
            ).strip() or "unspecified"
            clusters[reason].append(entry)
        return dict(clusters)

    def sample_representative_diffs(self, per_reason: int = 1) -> list[dict]:
        clusters = self.cluster_failure_reasons()
        representative: list[dict] = []
        by_reason: dict[str, list[Mapping[str, object]]] = defaultdict(list)
        for diff in self.diffs:
            key = str(diff.get("failure_reason") or diff.get("reason") or "unspecified")
            by_reason[key].append(diff)

        for reason in sorted(clusters):
            samples = by_reason.get(reason) or by_reason.get("unspecified") or []
            selected = samples[:per_reason]
            for sample in selected:
                representative.append({"reason": reason, "diff": dict(sample)})
        return representative

    def build_dataset(
        self,
        output_dir: str | Path,
        *,
        plan_filename: str = "retraining_plan.md",
        dataset_filename: str = "retraining_dataset.jsonl",
    ) -> dict:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        clusters = self.cluster_failure_reasons()
        total_failures = sum(len(entries) for entries in clusters.values()) or 1

        dataset_entries: list[dict] = []
        weights: dict[str, float] = {}

        for reason, entries in clusters.items():
            weight = len(entries) / total_failures
            weights[reason] = round(weight, 3)
            for entry in entries:
                prompt = entry.get("prompt") or entry.get("input")
                target = entry.get("expected") or entry.get("output") or entry.get("result")
                if not prompt or target is None:
                    continue
                dataset_entries.append(
                    {
                        "prompt": prompt,
                        "target": target,
                        "failure_reason": reason,
                        "weight": weights[reason],
                    }
                )

        dataset_path = output_dir / dataset_filename
        with dataset_path.open("w", encoding="utf-8") as handle:
            for row in dataset_entries:
                handle.write(json.dumps(row) + "\n")

        representative_diffs = self.sample_representative_diffs()
        pattern_counter = Counter({reason: len(entries) for reason, entries in clusters.items()})

        plan_lines: list[str] = ["# Codex Retraining Plan", "", "## Failure clusters"]
        if pattern_counter:
            for reason, count in pattern_counter.most_common():
                plan_lines.append(f"- {reason} (x{count}, weight={weights.get(reason, 0):.3f})")
        else:
            plan_lines.append("- No failures observed")

        plan_lines.extend(["", "## Representative diffs"])
        if representative_diffs:
            for sample in representative_diffs:
                summary = sample.get("diff", {})
                descriptor = summary.get("description") or summary.get("summary") or "diff"  # type: ignore[arg-type]
                plan_lines.append(f"- {sample['reason']}: {descriptor}")
        else:
            plan_lines.append("- No diffs available")

        plan_lines.extend(
            [
                "", "## Guidance",
                "Prioritize heavily weighted clusters and ensure updated prompts include counter-examples for each failure pattern.",
            ]
        )

        plan_path = output_dir / plan_filename
        plan_path.write_text("\n".join(plan_lines), encoding="utf-8")

        return {
            "dataset_path": dataset_path,
            "plan_path": plan_path,
            "weights": weights,
            "representative_diffs": representative_diffs,
        }


__all__ = ["CodexRetrainingPlanner"]
