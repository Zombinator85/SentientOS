"""Coverage analysis and adaptive gap detection for Codex."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping

import json

from .testcycles import TestSynthesizer


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CoverageGap:
    """Represents a coverage gap discovered during analysis."""

    module: str
    item_type: str
    name: str
    reason: str
    spec_id: str | None = None
    scaffold: str | None = None
    metadata: MutableMapping[str, Any] = field(default_factory=dict)

    @property
    def gap_id(self) -> str:
        return f"{self.module}::{self.item_type}::{self.name}"

    @property
    def coverage_target(self) -> str:
        return f"{self.item_type}:{self.module}:{self.name}"

    def to_event(self, timestamp: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "event_type": "coverage_gap_detected",
            "module": self.module,
            "item_type": self.item_type,
            "name": self.name,
            "reason": self.reason,
            "gap_id": self.gap_id,
            "coverage_target": self.coverage_target,
        }
        if self.spec_id:
            payload["spec_id"] = self.spec_id
        if self.scaffold:
            payload["scaffold_id"] = self.scaffold
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    def to_dict(self, feedback: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "module": self.module,
            "item_type": self.item_type,
            "name": self.name,
            "reason": self.reason,
            "gap_id": self.gap_id,
            "coverage_target": self.coverage_target,
        }
        if self.spec_id:
            payload["spec_id"] = self.spec_id
        if self.scaffold:
            payload["scaffold_id"] = self.scaffold
        if feedback:
            payload["feedback"] = dict(feedback)
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


class CoverageAnalyzer:
    """Builds coverage maps and synthesizes remediation strategies."""

    __test__ = False

    def __init__(
        self,
        *,
        repo_root: Path | str = Path("."),
        integration_root: Path | str | None = None,
        pulse_root: Path | str | None = None,
        synthesizer: TestSynthesizer | None = None,
        now: Callable[[], datetime] = _default_now,
    ) -> None:
        self._repo_root = Path(repo_root)
        self._integration_root = (
            Path(integration_root)
            if integration_root is not None
            else self._repo_root / "integration"
        )
        self._pulse_root = (
            Path(pulse_root)
            if pulse_root is not None
            else self._repo_root / "pulse" / "anomalies"
        )
        self._coverage_map_path = self._integration_root / "coverage_map.json"
        self._coverage_log_path = self._integration_root / "coverage_log.jsonl"
        self._feedback_path = self._integration_root / "coverage_feedback.json"
        self._pulse_log_path = self._pulse_root / "coverage_gaps.jsonl"
        self._now = now
        self._synthesizer = synthesizer or TestSynthesizer(
            repo_root=self._repo_root,
            integration_root=self._integration_root,
            now=now,
        )

        self._integration_root.mkdir(parents=True, exist_ok=True)
        self._pulse_root.mkdir(parents=True, exist_ok=True)
        self._pulse_log_path.touch(exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    @property
    def synthesizer(self) -> TestSynthesizer:
        return self._synthesizer

    def analyze(
        self,
        test_results: Mapping[str, Mapping[str, Iterable[str]]],
        source_index: Mapping[str, Mapping[str, Iterable[str]]],
        *,
        link_index: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyze coverage and persist the resulting map."""

        timestamp = self._now().isoformat()
        previous_map = self._load_map()
        feedback = self.feedback_summary()

        modules_payload: list[dict[str, Any]] = []
        gaps: list[CoverageGap] = []

        totals = {
            "functions": {"covered": 0, "total": 0},
            "branches": {"covered": 0, "total": 0},
            "integration_flows": {"covered": 0, "total": 0},
        }

        for module in sorted(source_index):
            definitions = source_index[module]
            functions = set(definitions.get("functions", []) or [])
            branches = set(definitions.get("branches", []) or [])
            flows = set(definitions.get("integration_flows", []) or [])

            results = test_results.get(module, {})
            tested_functions = set(results.get("functions", []) or []) & functions
            tested_branches = set(results.get("branches", []) or []) & branches
            tested_flows = set(results.get("integration_flows", []) or []) & flows

            totals["functions"]["covered"] += len(tested_functions)
            totals["functions"]["total"] += len(functions)
            totals["branches"]["covered"] += len(tested_branches)
            totals["branches"]["total"] += len(branches)
            totals["integration_flows"]["covered"] += len(tested_flows)
            totals["integration_flows"]["total"] += len(flows)

            missing_functions = sorted(functions - tested_functions)
            missing_branches = sorted(branches - tested_branches)
            missing_flows = sorted(flows - tested_flows)

            modules_payload.append(
                {
                    "module": module,
                    "functions": {
                        "tested": sorted(tested_functions),
                        "untested": missing_functions,
                        "coverage": self._coverage_ratio(len(tested_functions), len(functions)),
                    },
                    "branches": {
                        "covered": sorted(tested_branches),
                        "missing": missing_branches,
                        "coverage": self._coverage_ratio(len(tested_branches), len(branches)),
                    },
                    "integration_flows": {
                        "covered": sorted(tested_flows),
                        "missing": missing_flows,
                        "coverage": self._coverage_ratio(len(tested_flows), len(flows)),
                    },
                }
            )

            gaps.extend(
                self._build_gaps(
                    module,
                    "function",
                    missing_functions,
                    link_index,
                )
            )
            gaps.extend(
                self._build_gaps(
                    module,
                    "branch",
                    missing_branches,
                    link_index,
                )
            )
            gaps.extend(
                self._build_gaps(
                    module,
                    "integration_flow",
                    missing_flows,
                    link_index,
                )
            )

        coverage_map = {
            "generated_at": timestamp,
            "modules": modules_payload,
            "overall": self._overall_summary(totals),
            "gaps": [gap.to_dict(feedback.get(gap.gap_id)) for gap in gaps],
        }

        self._save_map(coverage_map)
        self._log_delta(previous_map, coverage_map)

        if gaps:
            self._emit_gaps(gaps, timestamp)
            self._propose_gap_tests(gaps)

        return coverage_map

    def load_map(self) -> dict[str, Any]:
        return self._load_map()

    def record_feedback(self, gap_id: str, classification: str, *, operator: str) -> dict[str, Any]:
        """Record operator sentiment about a coverage gap."""

        classification_key = classification.lower()
        if classification_key not in {"critical", "acceptable"}:
            raise ValueError("classification must be 'critical' or 'acceptable'")

        feedback = self.feedback_summary()
        entry = feedback.setdefault(
            gap_id,
            {
                "critical": 0,
                "acceptable": 0,
            },
        )
        entry[classification_key] = entry.get(classification_key, 0) + 1
        entry["_last_decision"] = classification_key
        entry["_last_operator"] = operator
        entry["_updated_at"] = self._now().isoformat()

        self._feedback_path.write_text(
            json.dumps(feedback, sort_keys=True, indent=2), encoding="utf-8"
        )

        self._append_log(
            {
                "timestamp": self._now().isoformat(),
                "event": "coverage_feedback_recorded",
                "gap_id": gap_id,
                "classification": classification_key,
                "operator": operator,
            }
        )
        return dict(entry)

    def feedback_summary(self) -> dict[str, dict[str, Any]]:
        if not self._feedback_path.exists():
            return {}
        data = json.loads(self._feedback_path.read_text(encoding="utf-8"))
        return {key: dict(value) for key, value in data.items()}

    # ------------------------------------------------------------------
    # Internal helpers
    def _coverage_ratio(self, covered: int, total: int) -> float:
        if total == 0:
            return 1.0
        return round(covered / total, 4)

    def _overall_summary(self, totals: Mapping[str, Mapping[str, int]]) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        for key, data in totals.items():
            summary[key] = {
                "covered": data["covered"],
                "total": data["total"],
                "coverage": self._coverage_ratio(data["covered"], data["total"]),
            }
        return summary

    def _load_map(self) -> dict[str, Any]:
        if not self._coverage_map_path.exists():
            return {
                "generated_at": None,
                "modules": [],
                "overall": {
                    "functions": {"covered": 0, "total": 0, "coverage": 0.0},
                    "branches": {"covered": 0, "total": 0, "coverage": 0.0},
                    "integration_flows": {
                        "covered": 0,
                        "total": 0,
                        "coverage": 0.0,
                    },
                },
                "gaps": [],
            }
        return json.loads(self._coverage_map_path.read_text(encoding="utf-8"))

    def _save_map(self, payload: Mapping[str, Any]) -> None:
        self._coverage_map_path.write_text(
            json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8"
        )

    def _append_log(self, entry: Mapping[str, Any]) -> None:
        with self._coverage_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(entry), sort_keys=True) + "\n")

    def _log_delta(
        self, previous: Mapping[str, Any], current: Mapping[str, Any]
    ) -> None:
        prev_overall = previous.get("overall") if previous else None
        curr_overall = current.get("overall", {})
        delta: dict[str, Any] = {
            "timestamp": current.get("generated_at", self._now().isoformat()),
            "event": "coverage_delta",
            "overall": curr_overall,
        }
        if prev_overall:
            changes: dict[str, Any] = {}
            for key in ("functions", "branches", "integration_flows"):
                prev_cov = (
                    prev_overall.get(key, {}).get("coverage")
                    if isinstance(prev_overall, Mapping)
                    else None
                )
                curr_cov = curr_overall.get(key, {}).get("coverage")
                if prev_cov is not None and curr_cov is not None:
                    changes[key] = round(curr_cov - prev_cov, 4)
            if changes:
                delta["delta"] = changes
        self._append_log(delta)

    def _emit_gaps(self, gaps: Iterable[CoverageGap], timestamp: str) -> None:
        lines = [json.dumps(gap.to_event(timestamp), sort_keys=True) for gap in gaps]
        if not lines:
            return
        with self._pulse_log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    def _propose_gap_tests(self, gaps: Iterable[CoverageGap]) -> None:
        existing_targets: set[str] = set()
        for proposal in self._synthesizer.pending():
            existing_targets.add(proposal.coverage_target)
        for proposal in self._synthesizer.approved():
            existing_targets.add(proposal.coverage_target)

        for gap in gaps:
            if gap.coverage_target in existing_targets:
                continue
            spec_id = gap.spec_id or gap.scaffold or f"coverage::{gap.module}"
            proposals = self._synthesizer.propose_tests(
                spec_id,
                failure_context=gap.reason,
                feedback="Coverage gap detected; operator review required.",
                implementation_paths=[gap.module],
                coverage_target=gap.coverage_target,
            )
            for proposal in proposals:
                existing_targets.add(proposal.coverage_target)

    def _build_gaps(
        self,
        module: str,
        item_type: str,
        missing: Iterable[str],
        link_index: Mapping[str, Any] | None,
    ) -> list[CoverageGap]:
        gaps: list[CoverageGap] = []
        for name in missing:
            spec_id: str | None = None
            scaffold: str | None = None
            metadata: dict[str, Any] = {}
            if link_index:
                spec_id, scaffold, metadata = self._resolve_link(
                    link_index, module, name
                )
            reason = f"Uncovered {item_type.replace('_', ' ')}"
            gaps.append(
                CoverageGap(
                    module=module,
                    item_type=item_type,
                    name=name,
                    reason=reason,
                    spec_id=spec_id,
                    scaffold=scaffold,
                    metadata=metadata,
                )
            )
        return gaps

    def _resolve_link(
        self,
        link_index: Mapping[str, Any],
        module: str,
        name: str,
    ) -> tuple[str | None, str | None, dict[str, Any]]:
        key_variants = [f"{module}:{name}", module]
        for key in key_variants:
            if key not in link_index:
                continue
            value = link_index[key]
            if isinstance(value, str):
                return value, None, {}
            if isinstance(value, Mapping):
                metadata = {
                    k: v
                    for k, v in value.items()
                    if k not in {"spec_id", "scaffold", "scaffold_id"}
                }
                spec_id = value.get("spec_id") or value.get("spec")
                scaffold = value.get("scaffold") or value.get("scaffold_id")
                return spec_id, scaffold, metadata
        return None, None, {}


__all__ = ["CoverageAnalyzer", "CoverageGap"]
