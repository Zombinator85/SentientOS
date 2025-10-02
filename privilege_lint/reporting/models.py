from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from privilege_lint.metrics import MetricsCollector


@dataclass
class PrivilegeReport:
    """Normalized privilege lint result for downstream consumers."""

    status: str
    timestamp: datetime
    issues: List[str]
    metrics: dict[str, object]
    checked_files: List[str]

    @property
    def passed(self) -> bool:
        return self.status == "clean"

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def summary(self) -> str:
        if self.passed:
            return "Sanctuary Privilege: intact"
        suffix = "issue" if self.issue_count == 1 else "issues"
        return f"Sanctuary Privilege: compromised ({self.issue_count} {suffix})"


@dataclass
class LintExecution:
    """Raw lint execution details captured from privilege_lint_cli."""

    metrics: MetricsCollector
    issues: List[str]
    timestamp: datetime
    checked_files: List[Path]
    project_root: Path
    config_hash: str
    report_json_enabled: bool
    sarif_enabled: bool
    fixed_count: int = 0

    def to_privilege_report(self) -> PrivilegeReport:
        timestamp = self.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        checked: List[str] = []
        for path in self.checked_files:
            try:
                checked.append(str(path.relative_to(self.project_root)))
            except ValueError:
                checked.append(str(path))
        payload = PrivilegeReport(
            status="clean" if not self.issues else "violation",
            timestamp=timestamp,
            issues=sorted(self.issues),
            metrics=self.metrics.to_dict(),
            checked_files=sorted(checked),
        )
        return payload
