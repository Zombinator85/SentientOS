"""Independent critic that audits autonomous actions."""

from __future__ import annotations

import json
from typing import Any, Dict

import memory_manager as mm
from notification import send as notify


def review_action(goal: Dict[str, Any], result: Dict[str, Any], consensus: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Analyse the outcome of an autonomous step and log feedback."""

    issues: list[str] = []
    status = str(result.get("status", "")).lower()
    if consensus and not consensus.get("approved", True):
        issues.append("council rejected intent")
    if status not in {"finished", "success"}:
        issues.append(result.get("error") or result.get("critique") or status or "unknown failure")
    warnings = result.get("warnings")
    if warnings:
        if isinstance(warnings, str):
            issues.append(warnings)
        elif isinstance(warnings, list):
            issues.extend(str(w) for w in warnings)

    severity = "ok"
    if issues:
        severity = "critical" if status == "failed" or "blocked" in status else "warning"

    record = {
        "goal": goal.get("id"),
        "status": status,
        "issues": issues,
        "severity": severity,
        "consensus": consensus or {},
    }

    mm.append_memory(
        json.dumps({"critic_review": record}, ensure_ascii=False),
        tags=["critic", severity, goal.get("id", "")],
        source="critic_daemon",
    )
    if severity != "ok":
        notify("critic_alert", {"goal": goal.get("id"), "severity": severity, "issues": issues})
    return record


__all__ = ["review_action"]
