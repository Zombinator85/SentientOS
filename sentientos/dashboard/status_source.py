"""Adapters that collect runtime status for the console dashboard."""

from __future__ import annotations

import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, List, Mapping, Optional

import experiment_tracker

from sentientos.persona.state import PersonaState

from .console import DashboardStatus, LogBuffer

try:  # pragma: no cover - optional typing import
    from sentientos.runtime.shell import RuntimeShell
except Exception:  # pragma: no cover - fallback for minimal environments
    RuntimeShell = None  # type: ignore

from sentientos.experiments import runner


class _ExperimentSummary:
    def __init__(
        self,
        total: int,
        success: int,
        failure: int,
        last_description: Optional[str],
        last_result: Optional[str],
    ) -> None:
        self.total = total
        self.success = success
        self.failure = failure
        self.last_description = last_description
        self.last_result = last_result


def _coerce_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _detect_model_name(config: Mapping[str, Any]) -> str:
    runtime = _coerce_mapping(config.get("runtime"))
    model_path = runtime.get("model_path")
    if isinstance(model_path, str) and model_path:
        return Path(model_path).name
    model = runtime.get("model_name")
    if isinstance(model, str) and model:
        return model
    return "Unknown model"


def _detect_model_status(shell: Optional[RuntimeShell], config: Mapping[str, Any]) -> str:
    if shell is not None:
        processes = getattr(shell, "_processes", {})
        llama = None
        if isinstance(processes, Mapping):
            llama = processes.get("llama")
        if llama is not None:
            try:
                running = llama.poll() is None  # type: ignore[call-arg]
            except Exception:  # pragma: no cover - defensive
                running = False
            if running:
                return "online"
            return "error"
        running_flag = getattr(shell, "_running", False)
        return "online" if running_flag else "starting"

    runtime = _coerce_mapping(config.get("runtime"))
    model_path = runtime.get("model_path")
    if isinstance(model_path, str) and model_path:
        if Path(model_path).exists():
            return "online"
    return "starting"


def _collect_experiment_summary() -> _ExperimentSummary:
    try:
        experiments = experiment_tracker.list_experiments()
    except Exception:
        experiments = []

    total_runs = 0
    successes = 0
    for record in experiments:
        triggers = int(record.get("triggers", 0) or 0)
        total_runs += max(0, triggers)
        success_count = int(record.get("success", 0) or 0)
        successes += max(0, success_count)
    failures = max(0, total_runs - successes)

    last_description: Optional[str] = None
    last_result: Optional[str] = None
    log_path = runner.CHAIN_LOG_PATH
    if log_path.exists():
        last_entry: Optional[Mapping[str, Any]] = None
        try:
            for raw in log_path.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                entry = json.loads(raw)
                if isinstance(entry, Mapping) and "experiment_id" in entry:
                    last_entry = entry
        except Exception:
            last_entry = None
        if last_entry:
            exp_id = str(last_entry.get("experiment_id") or "")
            if exp_id:
                try:
                    experiment = experiment_tracker.get_experiment(exp_id)
                except Exception:
                    experiment = None
                if isinstance(experiment, Mapping):
                    last_description = str(experiment.get("description") or exp_id)
                else:
                    last_description = exp_id
            success_flag = last_entry.get("success")
            if isinstance(success_flag, bool):
                last_result = "success" if success_flag else "failure"
            elif last_entry.get("error"):
                last_result = "failure"

    return _ExperimentSummary(total_runs, successes, failures, last_description, last_result)


def _resolve_persona_state(
    persona_state_getter: Optional[Callable[[], Optional[PersonaState]]],
) -> Optional[PersonaState]:
    if persona_state_getter is None:
        return None
    try:
        return persona_state_getter()
    except Exception:
        return None


def make_status_source(
    *,
    config: Optional[Mapping[str, Any]] = None,
    shell: Optional[RuntimeShell] = None,
    persona_state_getter: Optional[Callable[[], Optional[PersonaState]]] = None,
    consensus_mode: str = "single-node",
    now: Callable[[], datetime] = datetime.utcnow,
) -> Callable[[], DashboardStatus]:
    """Build a callable that returns :class:`DashboardStatus` snapshots."""

    config_mapping: Mapping[str, Any] = config or {}
    runtime = _coerce_mapping(config_mapping.get("runtime"))
    persona_cfg = _coerce_mapping(config_mapping.get("persona"))

    node_name = runtime.get("node_name")
    if not isinstance(node_name, str) or not node_name:
        node_name = platform.node() or "SentientOS"

    model_name = _detect_model_name(config_mapping)

    persona_enabled = bool(persona_cfg.get("enabled", True))

    def _status() -> DashboardStatus:
        persona_state = _resolve_persona_state(persona_state_getter)
        experiments = _collect_experiment_summary()
        model_status = _detect_model_status(shell, config_mapping)

        mood: Optional[str] = None
        last_msg: Optional[str] = None
        if persona_enabled and persona_state is not None:
            mood = persona_state.mood
            last_msg = persona_state.last_reflection

        digest = getattr(shell, "cathedral_digest", None) if shell is not None else None
        cathedral_cfg = _coerce_mapping(config_mapping.get("cathedral"))
        accepted = int(getattr(digest, "accepted", cathedral_cfg.get("accepted", 0)) or 0)
        applied = int(getattr(digest, "applied", cathedral_cfg.get("applied", 0)) or 0)
        quarantined = int(getattr(digest, "quarantined", cathedral_cfg.get("quarantined", 0)) or 0)
        last_applied_id = getattr(digest, "last_applied_id", cathedral_cfg.get("last_applied_id"))
        last_q_id = getattr(digest, "last_quarantined_id", cathedral_cfg.get("last_quarantined_id"))
        last_q_error = getattr(digest, "last_quarantine_error", cathedral_cfg.get("last_quarantine_error"))

        return DashboardStatus(
            node_name=node_name,
            model_name=model_name,
            model_status=model_status,
            persona_enabled=persona_enabled,
            persona_mood=mood,
            last_persona_msg=last_msg,
            experiments_run=experiments.total,
            experiments_success=experiments.success,
            experiments_failed=experiments.failure,
            last_experiment_desc=experiments.last_description,
            last_experiment_result=experiments.last_result,
            consensus_mode=consensus_mode,
            last_update_ts=now(),
            cathedral_accepted=accepted,
            cathedral_applied=applied,
            cathedral_quarantined=quarantined,
            last_applied_id=last_applied_id if isinstance(last_applied_id, str) and last_applied_id else None,
            last_quarantined_id=last_q_id if isinstance(last_q_id, str) and last_q_id else None,
            last_quarantine_error=last_q_error if isinstance(last_q_error, str) else None,
        )

    return _status


def make_log_stream_source(
    log_buffer: LogBuffer,
    *sources: Callable[[], Iterable[str]],
) -> Callable[[], Iterable[str]]:
    """Create a polling function that forwards events into ``log_buffer``."""

    def _poll() -> Iterable[str]:
        collected: List[str] = []
        for source in sources:
            try:
                produced = source()
            except Exception:
                continue
            for line in produced:
                text = str(line)
                collected.append(text)
                log_buffer.add(text)
        collected.extend(log_buffer.consume_pending())
        return collected

    setattr(_poll, "_log_buffer", log_buffer)
    return _poll
