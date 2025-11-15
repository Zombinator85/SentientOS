"""Adapters that collect runtime status for the console dashboard."""

from __future__ import annotations

import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

import experiment_tracker

from sentientos.persona.state import PersonaState
from sentientos.cathedral.federation_guard import should_accept_amendment
from sentientos.experiments.federation_guard import should_run_experiment

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


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed
    return None


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
    federation_cfg = _coerce_mapping(config_mapping.get("federation"))
    dream_cfg = _coerce_mapping(config_mapping.get("dream_loop"))

    node_name = runtime.get("node_name")
    if not isinstance(node_name, str) or not node_name:
        node_name = platform.node() or "SentientOS"

    model_name = _detect_model_name(config_mapping)

    persona_enabled = bool(persona_cfg.get("enabled", True))

    def _status() -> DashboardStatus:
        persona_state = _resolve_persona_state(persona_state_getter)
        experiments = _collect_experiment_summary()
        model_status = _detect_model_status(shell, config_mapping)

        federation_enabled = bool(federation_cfg.get("enabled", False))
        federation_node: Optional[str] = None
        federation_fp: Optional[str] = None
        federation_peer_total = 0
        federation_healthy = 0
        federation_drift = 0
        federation_incompatible = 0
        federation_peers: Dict[str, str] = {}
        federation_cluster_unstable = False
        guard_cathedral = "ALLOW_HIGH"
        guard_experiments = "ALLOW_HIGH"
        window = None
        federation_sync: Dict[str, Dict[str, object]] = {}

        if shell is not None:
            config_obj = getattr(shell, "federation_config", None)
            if config_obj is not None:
                federation_enabled = bool(getattr(config_obj, "enabled", False))
                node_id = getattr(config_obj, "node_id", None)
                if node_id is not None:
                    federation_node = getattr(node_id, "name", None)
                    federation_fp = getattr(node_id, "fingerprint", None)
                peers = getattr(config_obj, "peers", []) or []
                federation_peer_total = len(peers)
                if hasattr(shell, "get_federation_state"):
                    state = shell.get_federation_state()
                    counts = state.counts()
                    federation_healthy = counts.get("healthy", 0)
                    federation_drift = counts.get("drift", 0)
                    federation_incompatible = counts.get("incompatible", 0)
                    federation_peers = {name: report.level for name, report in state.peer_reports.items()}
                window_fn = getattr(shell, "federation_window", None)
                if callable(window_fn):
                    try:
                        window = window_fn()
                    except Exception:
                        window = None
                sync_getter = getattr(shell, "get_peer_sync_views", None)
                if callable(sync_getter):
                    try:
                        sync_views = sync_getter()
                    except Exception:
                        sync_views = {}
                    if isinstance(sync_views, Mapping):
                        for peer_name, view in sync_views.items():
                            cathedral = getattr(view, "cathedral", None)
                            experiments = getattr(view, "experiments", None)
                            federation_sync[str(peer_name)] = {
                                "cathedral": {
                                    "status": getattr(cathedral, "status", "unknown"),
                                    "missing_local": list(getattr(cathedral, "missing_local_ids", []) or []),
                                    "missing_peer": list(getattr(cathedral, "missing_peer_ids", []) or []),
                                },
                                "experiments": {
                                    "status": getattr(experiments, "status", "unknown"),
                                    "missing_local": list(getattr(experiments, "missing_local_ids", []) or []),
                                    "missing_peer": list(getattr(experiments, "missing_peer_ids", []) or []),
                                },
                            }
        if federation_node is None:
            candidate = federation_cfg.get("node_name")
            if isinstance(candidate, str) and candidate:
                federation_node = candidate
        if not federation_peer_total:
            peers_cfg = federation_cfg.get("peers")
            if isinstance(peers_cfg, list):
                federation_peer_total = len(peers_cfg)

        if window is not None:
            federation_cluster_unstable = bool(getattr(window, "is_cluster_unstable", False))
        guard_cathedral = f"{should_accept_amendment(window, 'high').upper()}_HIGH"
        guard_experiments = f"{should_run_experiment(window, 'high').upper()}_HIGH"

        mood: Optional[str] = None
        last_msg: Optional[str] = None
        recent_reflection: Optional[str] = None
        if persona_enabled and persona_state is not None:
            mood = persona_state.mood
            last_msg = persona_state.last_reflection
            recent_reflection = getattr(persona_state, "recent_reflection", None)

        digest = getattr(shell, "cathedral_digest", None) if shell is not None else None
        cathedral_cfg = _coerce_mapping(config_mapping.get("cathedral"))
        accepted = int(getattr(digest, "accepted", cathedral_cfg.get("accepted", 0)) or 0)
        applied = int(getattr(digest, "applied", cathedral_cfg.get("applied", 0)) or 0)
        quarantined = int(getattr(digest, "quarantined", cathedral_cfg.get("quarantined", 0)) or 0)
        rollbacks = int(getattr(digest, "rollbacks", cathedral_cfg.get("rollbacks", 0)) or 0)
        auto_reverts = int(getattr(digest, "auto_reverts", cathedral_cfg.get("auto_reverts", 0)) or 0)
        pending_federation = int(getattr(digest, "pending_federation", 0) or 0)
        held_federation = int(getattr(digest, "held_federation", 0) or 0)
        last_applied_id = getattr(digest, "last_applied_id", cathedral_cfg.get("last_applied_id"))
        last_q_id = getattr(digest, "last_quarantined_id", cathedral_cfg.get("last_quarantined_id"))
        last_q_error = getattr(digest, "last_quarantine_error", cathedral_cfg.get("last_quarantine_error"))
        last_reverted_id = getattr(
            digest,
            "last_reverted_id",
            cathedral_cfg.get("last_reverted_id"),
        )
        last_pending_id = getattr(digest, "last_pending_id", cathedral_cfg.get("last_pending_id"))

        experiments_held_total = 0
        if shell is not None:
            experiments_held_total = int(getattr(shell, "_experiment_guard_hold_total", 0) or 0)

        dream_loop_enabled = bool(dream_cfg.get("enabled", False))
        dream_loop_running = False
        dream_loop_focus: Optional[str] = None
        dream_loop_ts: Optional[datetime] = None
        glow_journal_size = 0
        glow_summary: Optional[str] = None

        if shell is not None:
            status_callable = getattr(shell, "dream_loop_status", None)
            status_info = None
            if callable(status_callable):
                try:
                    status_info = status_callable()
                except Exception:
                    status_info = None
            elif isinstance(status_callable, Mapping):
                status_info = status_callable
            if isinstance(status_info, Mapping):
                dream_loop_enabled = bool(status_info.get("enabled", dream_loop_enabled))
                dream_loop_running = bool(status_info.get("running", False))
                focus_value = status_info.get("last_focus")
                if isinstance(focus_value, str) and focus_value:
                    dream_loop_focus = focus_value
                ts_value = status_info.get("last_created_at")
                parsed_ts = _parse_datetime(ts_value)
                if parsed_ts is not None:
                    dream_loop_ts = parsed_ts
                elif isinstance(ts_value, datetime):
                    dream_loop_ts = ts_value
                glow_journal_size = int(status_info.get("shard_count", 0) or 0)
                summary_value = status_info.get("last_summary")
                if isinstance(summary_value, str) and summary_value:
                    glow_summary = summary_value
                shard_id = status_info.get("last_shard_id")
                if glow_summary is None and isinstance(shard_id, str) and shard_id:
                    glow_summary = shard_id
        else:
            glow_journal_size = int(dream_cfg.get("journal_size", 0) or 0)

        return DashboardStatus(
            node_name=node_name,
            model_name=model_name,
            model_status=model_status,
            persona_enabled=persona_enabled,
            persona_mood=mood,
            last_persona_msg=last_msg,
            persona_recent_reflection=recent_reflection,
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
            cathedral_rollbacks=rollbacks,
            cathedral_auto_reverts=auto_reverts,
            cathedral_pending_federation=pending_federation,
            cathedral_held_federation=held_federation,
            last_applied_id=last_applied_id if isinstance(last_applied_id, str) and last_applied_id else None,
            last_quarantined_id=last_q_id if isinstance(last_q_id, str) and last_q_id else None,
            last_quarantine_error=last_q_error if isinstance(last_q_error, str) else None,
            last_reverted_id=last_reverted_id if isinstance(last_reverted_id, str) and last_reverted_id else None,
            last_pending_id=last_pending_id if isinstance(last_pending_id, str) and last_pending_id else None,
            federation_enabled=federation_enabled,
            federation_node=federation_node,
            federation_fingerprint=federation_fp,
            federation_peer_total=federation_peer_total,
            federation_healthy=federation_healthy,
            federation_drift=federation_drift,
            federation_incompatible=federation_incompatible,
            federation_peers=federation_peers,
            federation_cluster_unstable=federation_cluster_unstable,
            federation_guard_cathedral=guard_cathedral,
            federation_guard_experiments=guard_experiments,
            federation_sync=federation_sync,
            experiments_held_federation=experiments_held_total,
            dream_loop_enabled=dream_loop_enabled,
            dream_loop_running=dream_loop_running,
            dream_loop_last_focus=dream_loop_focus,
            dream_loop_last_shard_ts=dream_loop_ts,
            glow_journal_size=glow_journal_size,
            glow_last_summary=glow_summary,
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
