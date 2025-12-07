"""Stage 6 SelfExpansionAgent implementation.

This agent produces deterministic self-audit summaries and structured upgrade
proposals. It is intentionally rule-based and avoids any execution or
side-effects.
"""

from __future__ import annotations

from typing import Any, Dict


class SelfExpansionAgent:
    """Plan and steward self-improvement activities."""

    def run_self_audit(self, observations: Dict[str, Any]) -> Dict[str, Any]:
        """Perform a deterministic self-audit and return diagnostic information.

        The audit mirrors the provided observations and adds lightweight derived
        fields that summarize whether additional attention is warranted.
        """

        audit_summary: Dict[str, Any] = dict(observations)

        error_count = float(audit_summary.get("error_count", 0))
        tension_avg = float(audit_summary.get("tension_avg", 0))
        low_confidence_events = float(audit_summary.get("low_confidence_events", 0))

        flags_triggered = 0
        if error_count > 0:
            flags_triggered += 1
        if tension_avg > 0.5:
            flags_triggered += 1
        if low_confidence_events > 0:
            flags_triggered += 1

        needs_improvement = flags_triggered > 0

        audit_summary["attention_flags"] = flags_triggered
        audit_summary["needs_improvement"] = needs_improvement
        audit_summary["status"] = "attention_needed" if needs_improvement else "stable"

        return audit_summary

    def propose_upgrades(self, observations: Dict[str, Any]) -> str:
        """Propose deterministic upgrades or experiments based on observations."""

        proposals = ["Proposal:"]

        error_count = float(observations.get("error_count", 0))
        tension_avg = float(observations.get("tension_avg", 0))
        low_confidence_events = float(observations.get("low_confidence_events", 0))

        if error_count > 0:
            proposals.append(
                "- Strengthen error handling pathways and add safeguards for repeating issues."
            )

        if tension_avg > 0.5:
            proposals.append(
                "- Tune inner experience integration to reduce tension and stabilize responses."
            )

        if low_confidence_events > 0:
            proposals.append(
                "- Enhance metacognition rules to detect and correct low-confidence states earlier."
            )

        if len(proposals) == 1:
            proposals.append("- Maintain current operations; no immediate upgrades required.")

        return "\n".join(proposals)
