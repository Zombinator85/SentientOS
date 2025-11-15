"""Experiment chain execution engine."""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import experiment_tracker
from logging_config import get_log_path

from .chain import ExperimentChain, ChainStep
from .federation_guard import current_window, emit_guard_event, should_run_experiment
from sentientos.verify.sentient_verify_loop import execute_experiment_with_adapter


ChainProgressCallback = Callable[["ChainStepResult"], None]


@dataclass
class ChainStepResult:
    """Result of executing a single step within a chain."""

    chain_id: str
    step_index: int
    experiment_id: str
    success: Optional[bool]
    context: Dict[str, Any]
    error: Optional[str] = None


@dataclass
class ChainRunResult:
    """Aggregate information about a completed chain execution."""

    chain_id: str
    outcome: str
    final_experiment_id: Optional[str]
    steps: List[ChainStepResult]


CHAIN_LOG_PATH = get_log_path("experiment_chain_log.jsonl", "EXPERIMENT_CHAIN_LOG")
CHAIN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return _dt.datetime.utcnow().isoformat()


def _snapshot_context(context: Dict[str, Any]) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {}
    for key, value in context.items():
        if isinstance(value, (int, float, str, bool)) or value is None:
            snapshot[key] = value
        else:
            snapshot[key] = repr(value)
    return snapshot


def _log_entry(entry: Dict[str, Any]) -> None:
    record = dict(entry)
    record.setdefault("timestamp", _now())
    with CHAIN_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _log_guard_decision(
    chain_id: str,
    experiment_id: str,
    decision: str,
    risk_level: str,
) -> None:
    _log_entry(
        {
            "chain_id": chain_id,
            "experiment_id": experiment_id,
            "event": "federation_guard",
            "decision": decision,
            "risk_level": risk_level,
        }
    )


def execute_experiment(exp: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a single experiment returning a DSL context."""

    context = execute_experiment_with_adapter(exp)
    return dict(context)


def _log_step_result(result: ChainStepResult) -> None:
    context_snapshot = _snapshot_context(result.context)
    payload = {
        "chain_id": result.chain_id,
        "step_index": result.step_index,
        "experiment_id": result.experiment_id,
        "success": result.success,
        "context": context_snapshot,
    }
    if "adapter_name" in context_snapshot:
        payload["adapter_name"] = context_snapshot["adapter_name"]
    if "adapter_deterministic" in context_snapshot:
        payload["adapter_deterministic"] = context_snapshot["adapter_deterministic"]
    if result.error:
        payload["error"] = result.error
    _log_entry(payload)


def _finalize_run(result: ChainRunResult) -> None:
    _log_entry(
        {
            "chain_id": result.chain_id,
            "event": "chain_complete",
            "outcome": result.outcome,
            "final_experiment_id": result.final_experiment_id,
        }
    )


def _validate_step(chain: ExperimentChain, step_id: str) -> ChainStep:
    try:
        return chain.steps[step_id]
    except KeyError as exc:
        raise ValueError(f"Chain '{chain.chain_id}' references unknown step '{step_id}'") from exc


def run_chain(
    chain: ExperimentChain,
    *,
    progress_callback: Optional[ChainProgressCallback] = None,
) -> ChainRunResult:
    """Run an :class:`ExperimentChain` deterministically."""

    current_id = chain.start
    history: List[ChainStepResult] = []
    outcome = "aborted_limit"
    final_experiment_id: Optional[str] = None

    for step_index in range(chain.max_steps):
        step = _validate_step(chain, current_id)
        experiment = experiment_tracker.get_experiment(step.id)
        if experiment is None:
            result = ChainStepResult(
                chain_id=chain.chain_id,
                step_index=step_index,
                experiment_id=step.id,
                success=None,
                context={},
                error="missing_experiment",
            )
            history.append(result)
            _log_step_result(result)
            if progress_callback:
                progress_callback(result)
            outcome = "failure"
            final_experiment_id = step.id
            break

        if experiment.get("requires_consensus") and experiment.get("status") != "active":
            result = ChainStepResult(
                chain_id=chain.chain_id,
                step_index=step_index,
                experiment_id=step.id,
                success=None,
                context={},
                error="pending_consensus",
            )
            history.append(result)
            _log_step_result(result)
            if progress_callback:
                progress_callback(result)
            outcome = "pending_consensus"
            final_experiment_id = step.id
            break

        risk_level = str(experiment.get("risk_level") or "medium")
        window = current_window()
        guard_decision = should_run_experiment(window, risk_level)
        if guard_decision in {"warn", "hold"}:
            emit_guard_event(
                guard_decision,
                {
                    "chain_id": chain.chain_id,
                    "experiment_id": step.id,
                    "risk_level": risk_level,
                    "window_unstable": bool(window.is_cluster_unstable) if window else False,
                },
            )
            _log_guard_decision(chain.chain_id, step.id, guard_decision, risk_level)
            if guard_decision == "hold":
                result = ChainStepResult(
                    chain_id=chain.chain_id,
                    step_index=step_index,
                    experiment_id=step.id,
                    success=None,
                    context={},
                    error="held_due_to_federation",
                )
                history.append(result)
                _log_step_result(result)
                if progress_callback:
                    progress_callback(result)
                outcome = "held_federation"
                final_experiment_id = step.id
                break

        try:
            context = execute_experiment(experiment)
        except Exception as exc:
            result = ChainStepResult(
                chain_id=chain.chain_id,
                step_index=step_index,
                experiment_id=step.id,
                success=None,
                context={},
                error=f"execution_error: {exc}",
            )
            history.append(result)
            _log_step_result(result)
            if progress_callback:
                progress_callback(result)
            outcome = "failure"
            final_experiment_id = step.id
            break

        try:
            success = bool(experiment_tracker.evaluate_experiment_success(step.id, context))
        except Exception as exc:
            result = ChainStepResult(
                chain_id=chain.chain_id,
                step_index=step_index,
                experiment_id=step.id,
                success=None,
                context=_snapshot_context(context if isinstance(context, dict) else {}),
                error=f"evaluation_error: {exc}",
            )
            history.append(result)
            _log_step_result(result)
            if progress_callback:
                progress_callback(result)
            outcome = "failure"
            final_experiment_id = step.id
            break

        experiment_tracker.record_result(step.id, success)

        if not isinstance(context, dict):
            context_snapshot: Dict[str, Any] = {"__repr__": repr(context)}
        else:
            context_snapshot = dict(context)

        result = ChainStepResult(
            chain_id=chain.chain_id,
            step_index=step_index,
            experiment_id=step.id,
            success=success,
            context=context_snapshot,
        )
        history.append(result)
        _log_step_result(result)
        if progress_callback:
            progress_callback(result)

        next_step = step.on_success if success else step.on_failure
        if next_step is None:
            outcome = "success" if success else "failure"
            final_experiment_id = step.id
            break

        current_id = next_step
    else:
        final_experiment_id = history[-1].experiment_id if history else current_id

    run_result = ChainRunResult(
        chain_id=chain.chain_id,
        outcome=outcome,
        final_experiment_id=final_experiment_id,
        steps=history,
    )
    _finalize_run(run_result)
    return run_result
