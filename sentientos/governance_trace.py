from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = 1
_CURRENT_TRACE: ContextVar[GovernanceTraceRecorder | None] = ContextVar("governance_trace", default=None)


@dataclass(slots=True)
class GovernanceTraceRecorder:
    repo_root: Path
    context: str
    created_at: str
    strategic_posture: str
    integrity_pressure_level: int
    integrity_metrics_summary: dict[str, object]
    operating_mode: str
    mode_toggles_summary: dict[str, object]
    quarantine_state_summary: dict[str, object]
    risk_budget_summary: dict[str, object]
    risk_budget_notes: list[str] = field(default_factory=list)
    gates_evaluated: list[dict[str, object]] = field(default_factory=list)
    clamps_applied: list[dict[str, object]] = field(default_factory=list)

    def record_gate(
        self,
        *,
        name: str,
        mode: str,
        result: str,
        reason: str,
        evidence_paths: list[str] | None = None,
    ) -> None:
        row: dict[str, object] = {
            "name": name,
            "mode": mode,
            "result": result,
            "reason": reason,
        }
        if evidence_paths:
            row["evidence_paths"] = list(evidence_paths)
        self.gates_evaluated.append(row)

    def record_clamp(self, *, name: str, before: Mapping[str, object], after: Mapping[str, object], notes: str = "") -> None:
        self.clamps_applied.append(
            {
                "name": name,
                "before": {str(k): v for k, v in before.items()},
                "after": {str(k): v for k, v in after.items()},
                "notes": notes,
            }
        )

    def finalize(
        self,
        *,
        final_decision: str,
        final_reason: str,
        reason_stack: list[str],
        suggested_actions: list[str] | None = None,
    ) -> dict[str, object]:
        stamp = self.created_at.replace(":", "-").replace(".", "-")
        trace_id = f"trace_{stamp}_{self.context}"
        rel_path = Path("glow/forge/traces") / f"{trace_id}.json"
        abs_path = self.repo_root / rel_path
        payload = {
            "schema_version": SCHEMA_VERSION,
            "trace_id": trace_id,
            "context": self.context,
            "created_at": self.created_at,
            "strategic_posture": self.strategic_posture,
            "integrity_pressure_level": self.integrity_pressure_level,
            "integrity_metrics_summary": self.integrity_metrics_summary,
            "operating_mode": self.operating_mode,
            "mode_toggles_summary": self.mode_toggles_summary,
            "quarantine_state_summary": self.quarantine_state_summary,
            "risk_budget_summary": self.risk_budget_summary,
            "risk_budget_notes": self.risk_budget_notes,
            "gates_evaluated": self.gates_evaluated,
            "clamps_applied": self.clamps_applied,
            "final_decision": final_decision,
            "final_reason": final_reason,
            "reason_stack": reason_stack,
            "suggested_actions": list(suggested_actions or []),
        }
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pulse_path = self.repo_root / "pulse/governance_traces.jsonl"
        pulse_path.parent.mkdir(parents=True, exist_ok=True)
        line = {
            "trace_id": trace_id,
            "context": self.context,
            "created_at": self.created_at,
            "final_decision": final_decision,
            "final_reason": final_reason,
            "reason_stack": reason_stack[:6],
            "trace_path": str(rel_path),
        }
        with pulse_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, sort_keys=True) + "\n")
        return {
            "trace_id": trace_id,
            "trace_path": str(rel_path),
            "trace_summary": {
                "final_decision": final_decision,
                "final_reason": final_reason,
                "reason_stack": reason_stack[:6],
            },
        }


def start_governance_trace(
    *,
    repo_root: Path,
    context: str,
    strategic_posture: str,
    integrity_pressure_level: int,
    integrity_metrics_summary: Mapping[str, object],
    operating_mode: str,
    mode_toggles_summary: Mapping[str, object],
    quarantine_state_summary: Mapping[str, object],
    risk_budget_summary: Mapping[str, object],
    risk_budget_notes: list[str] | None = None,
) -> GovernanceTraceRecorder:
    return GovernanceTraceRecorder(
        repo_root=repo_root.resolve(),
        context=context,
        created_at=_iso_now(),
        strategic_posture=strategic_posture,
        integrity_pressure_level=integrity_pressure_level,
        integrity_metrics_summary={str(k): v for k, v in integrity_metrics_summary.items()},
        operating_mode=operating_mode,
        mode_toggles_summary={str(k): v for k, v in mode_toggles_summary.items()},
        quarantine_state_summary={str(k): v for k, v in quarantine_state_summary.items()},
        risk_budget_summary={str(k): v for k, v in risk_budget_summary.items()},
        risk_budget_notes=list(risk_budget_notes or []),
    )


def set_current_trace(trace: GovernanceTraceRecorder | None) -> Token[GovernanceTraceRecorder | None]:
    return _CURRENT_TRACE.set(trace)


def reset_current_trace(token: Token[GovernanceTraceRecorder | None]) -> None:
    _CURRENT_TRACE.reset(token)


def record_clamp_for_current(*, name: str, before: Mapping[str, object], after: Mapping[str, object], notes: str = "") -> None:
    trace = _CURRENT_TRACE.get()
    if trace is None:
        return
    trace.record_clamp(name=name, before=before, after=after, notes=notes)


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
