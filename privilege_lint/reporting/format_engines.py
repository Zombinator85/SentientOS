from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

import yaml

from .models import PrivilegeReport


class FormatEngine(Protocol):
    format_name: str
    extension: str

    def render(self, report: PrivilegeReport) -> str:
        ...


@dataclass
class JSONFormatEngine:
    format_name: str = "json"
    extension: str = "json"

    def render(self, report: PrivilegeReport) -> str:
        payload = {
            "status": report.status,
            "summary": report.summary(),
            "timestamp": report.timestamp.isoformat(),
            "issues": report.issues,
            "metrics": report.metrics,
            "checked_files": report.checked_files,
        }
        return json.dumps(payload, indent=2, sort_keys=True)


@dataclass
class YAMLFormatEngine:
    format_name: str = "yaml"
    extension: str = "yaml"

    def render(self, report: PrivilegeReport) -> str:
        payload = {
            "status": report.status,
            "summary": report.summary(),
            "timestamp": report.timestamp.isoformat(),
            "issues": report.issues,
            "metrics": report.metrics,
            "checked_files": report.checked_files,
        }
        return yaml.safe_dump(payload, sort_keys=True)


@dataclass
class MarkdownFormatEngine:
    format_name: str = "markdown"
    extension: str = "md"

    def render(self, report: PrivilegeReport) -> str:
        status_icon = "✅" if report.passed else "❌"
        lines = [
            f"# Sanctuary Privilege Report — {report.timestamp.isoformat()}",
            "",
            f"* **Status:** {status_icon} {'Clean' if report.passed else 'Violation detected'}",
            f"* **Summary:** {report.summary()}",
            f"* **Files Checked:** {len(report.checked_files)}",
            f"* **Issues:** {report.issue_count}",
            f"* **Runtime:** {report.metrics.get('runtime', 0)}s",
            "",
        ]
        if report.issues:
            lines.append("## Findings")
            for entry in report.issues:
                lines.append(f"- {entry}")
        else:
            lines.append("All sanctuaries honour the privilege alignment_contract. No issues detected.")
        return "\n".join(lines)
