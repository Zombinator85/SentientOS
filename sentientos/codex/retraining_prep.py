from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping, Sequence

DEFAULT_DATASET_NAME = "retraining_dataset.jsonl"
DEFAULT_PLAN_NAME = "retraining_plan.md"


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


def _collect_patterns(scorecard: Iterable[Mapping[str, object]], failures: Iterable[Mapping[str, object]]):
    pattern_counter: Counter[str] = Counter()
    rejection_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()

    for entry in list(scorecard) + list(failures):
        reason = str(entry.get("failure_reason") or entry.get("reason") or entry.get("failure", "")).strip()
        if reason:
            pattern_counter[reason] += 1
        rejection = entry.get("rejection_reason")
        if rejection:
            rejection_counter[str(rejection)] += 1
        category = entry.get("category") or entry.get("diff_category")
        if category:
            category_counter[str(category)] += 1
    return pattern_counter, rejection_counter, category_counter


def prepare_retraining(
    scorecard_path: str | Path,
    failure_log_path: str | Path,
    *,
    output_dataset_path: str | Path | None = None,
    output_plan_path: str | Path | None = None,
) -> dict:
    """Extract failure patterns and assemble retraining artifacts."""

    scorecard = _load_jsonl(scorecard_path)
    failures = _load_jsonl(failure_log_path)

    dataset_path = Path(output_dataset_path) if output_dataset_path else Path(scorecard_path).parent / DEFAULT_DATASET_NAME
    plan_path = Path(output_plan_path) if output_plan_path else Path(scorecard_path).parent / DEFAULT_PLAN_NAME

    dataset_entries: list[dict] = []
    for entry in scorecard + failures:
        prompt = entry.get("prompt") or entry.get("input")
        failure = entry.get("failure_reason") or entry.get("failure") or entry.get("rejection_reason")
        result = entry.get("result") or entry.get("output")
        if entry.get("score") is not None and float(entry.get("score", 1.0)) >= 0.85 and not failure:
            continue
        if prompt is None or result is None:
            continue
        dataset_entries.append(
            {
                "prompt": prompt,
                "failure": failure or "unspecified",
                "result": result,
            }
        )

    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    with dataset_path.open("w", encoding="utf-8") as handle:
        for row in dataset_entries:
            handle.write(json.dumps(row) + "\n")

    pattern_counter, rejection_counter, category_counter = _collect_patterns(scorecard, failures)

    def _top(counter: Counter[str]) -> list[tuple[str, int]]:
        return counter.most_common()

    plan_lines = [
        "# Codex Retraining Plan",
        "",
        "## Persistent failure patterns",
    ]
    for reason, count in _top(pattern_counter):
        plan_lines.append(f"- {reason} (x{count})")
    if not pattern_counter:
        plan_lines.append("- No repeated failures detected")

    plan_lines.extend(["", "## Common rejection reasons"])
    for reason, count in _top(rejection_counter):
        plan_lines.append(f"- {reason} (x{count})")
    if not rejection_counter:
        plan_lines.append("- Rejections not observed")

    plan_lines.extend(["", "## Problematic diff categories"])
    for category, count in _top(category_counter):
        plan_lines.append(f"- {category} (x{count})")
    if not category_counter:
        plan_lines.append("- No diff categories flagged")

    plan_lines.extend([
        "",
        "## Module focus",
        "Prioritize self-finetuning on clusters above and refresh retrieval baselines with compressed exemplars.",
    ])

    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("\n".join(plan_lines), encoding="utf-8")

    return {
        "dataset_path": dataset_path,
        "plan_path": plan_path,
        "patterns": dict(pattern_counter),
        "rejections": dict(rejection_counter),
        "diff_categories": dict(category_counter),
    }


__all__ = ["prepare_retraining"]
