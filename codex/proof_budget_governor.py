"""Deterministic proof-budget governor for staged routing flows."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Mapping, Sequence
import uuid

from scripts.provenance_hash_chain import HASH_ALGO, canonical_json_bytes

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

GOVERNOR_VERSION = "v1"
DEFAULT_PRESSURE_STATE_PATH = Path("glow/routing/pressure_state.json")
DEFAULT_PRESSURE_STATE_DIR = Path("glow/routing/pressure_state")
LOCK_ACQUIRE_TIMEOUT_SECONDS = 0.2
LOCK_POLL_SECONDS = 0.01
GENESIS_PREV_STATE_HASH = "GENESIS"


@dataclass(slots=True, frozen=True)
class BudgetDecision:
    k_effective: int
    m_effective: int
    allow_escalation: bool
    mode: str
    decision_reasons: list[str]
    governor_version: str = GOVERNOR_VERSION


@dataclass(slots=True, frozen=True)
class GovernorConfig:
    configured_k: int
    configured_m: int
    max_k: int
    escalation_enabled: bool
    mode: str
    admissible_collapse_runs: int
    min_m: int
    diagnostics_k: int
    pressure_window: int = 6
    proof_burn_spike_runs: int = 2
    escalation_cluster_runs: int = 2


@dataclass(slots=True)
class PressureState:
    consecutive_no_admissible: int = 0
    recent_runs: list[dict[str, Any]] | None = None
    state_hash: str | None = None
    prev_state_hash: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["recent_runs"] = list(self.recent_runs or [])
        payload.pop("state_hash", None)
        payload.pop("prev_state_hash", None)
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "PressureState":
        return cls(
            consecutive_no_admissible=max(0, int(payload.get("consecutive_no_admissible", 0))),
            recent_runs=[dict(item) for item in payload.get("recent_runs", []) if isinstance(item, Mapping)],
        )


@dataclass(slots=True, frozen=True)
class PressureStateWriteResult:
    state_update_skipped: bool
    pressure_state_prev_hash: str | None
    pressure_state_new_hash: str | None
    pressure_state_snapshot_path: str | None


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        tmp_path = Path(handle.name)
        handle.write(json.dumps(payload, sort_keys=True, indent=2))
        handle.flush()
        os.fsync(handle.fileno())
    tmp_path.replace(path)


def _state_paths(path: Path | None) -> tuple[Path, Path, Path, Path]:
    if path is None:
        return (
            DEFAULT_PRESSURE_STATE_DIR,
            DEFAULT_PRESSURE_STATE_DIR / "latest.json",
            DEFAULT_PRESSURE_STATE_DIR / "snapshots",
            DEFAULT_PRESSURE_STATE_DIR / ".lock",
        )
    if path.suffix.lower() == ".json":
        state_dir = path.parent
        return (state_dir, path, state_dir / "snapshots", state_dir / ".lock")
    return (path, path / "latest.json", path / "snapshots", path / ".lock")


def _compute_state_hash(snapshot_payload: Mapping[str, Any], prev_state_hash: str | None) -> str:
    material = {key: value for key, value in snapshot_payload.items() if key != "state_hash"}
    prev_marker = prev_state_hash or GENESIS_PREV_STATE_HASH
    digest = hashlib.sha256()
    digest.update(prev_marker.encode("utf-8"))
    digest.update(b"\n")
    digest.update(canonical_json_bytes(dict(material)))
    return digest.hexdigest()


def _parse_state_document(payload: Mapping[str, Any]) -> PressureState:
    if isinstance(payload.get("state"), Mapping):
        state = PressureState.from_payload(payload["state"])
        state.state_hash = str(payload.get("state_hash") or "") or None
        state.prev_state_hash = str(payload.get("prev_state_hash") or "") or None
        return state
    return PressureState.from_payload(payload)


def _lock_file(lock_path: Path, timeout_seconds: float) -> Any | None:
    if fcntl is None:
        return None
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except BlockingIOError:
            if time.monotonic() >= deadline:
                handle.close()
                return None
            time.sleep(LOCK_POLL_SECONDS)


def _unlock_file(handle: Any | None) -> None:
    if handle is None or fcntl is None:
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()


def _flag_enabled(value: str) -> bool:
    return value not in {"0", "false", "False"}


def governor_config_from_env(*, configured_k: int, configured_m: int) -> GovernorConfig:
    return GovernorConfig(
        configured_k=max(1, int(configured_k)),
        configured_m=max(1, int(configured_m)),
        max_k=max(int(os.getenv("SENTIENTOS_ROUTER_MAX_K", "9")), 1),
        escalation_enabled=_flag_enabled(os.getenv("SENTIENTOS_ROUTER_ESCALATE_ON_ALL_FAIL_A", "1")),
        mode=str(os.getenv("SENTIENTOS_GOVERNOR_MODE", "auto") or "auto"),
        admissible_collapse_runs=max(1, int(os.getenv("SENTIENTOS_GOVERNOR_ADMISSIBLE_COLLAPSE_RUNS", "3"))),
        min_m=max(1, int(os.getenv("SENTIENTOS_GOVERNOR_MIN_M", "1"))),
        diagnostics_k=max(1, int(os.getenv("SENTIENTOS_GOVERNOR_DIAGNOSTICS_K", "4"))),
    )


def load_pressure_state(path: Path | None = None) -> PressureState:
    _, latest_path, _, _ = _state_paths(path)
    if latest_path.exists():
        try:
            payload = json.loads(latest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return PressureState(recent_runs=[])
        if not isinstance(payload, Mapping):
            return PressureState(recent_runs=[])
        return _parse_state_document(payload)
    if path is None and DEFAULT_PRESSURE_STATE_PATH.exists():
        try:
            payload = json.loads(DEFAULT_PRESSURE_STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return PressureState(recent_runs=[])
        if not isinstance(payload, Mapping):
            return PressureState(recent_runs=[])
        return PressureState.from_payload(payload)
    if not latest_path.exists():
        return PressureState(recent_runs=[])
    return PressureState(recent_runs=[])


def save_pressure_state(state: PressureState, path: Path | None = None) -> PressureStateWriteResult:
    _, latest_path, snapshots_dir, lock_path = _state_paths(path)
    lock_handle = _lock_file(lock_path, timeout_seconds=LOCK_ACQUIRE_TIMEOUT_SECONDS)
    if lock_handle is None:
        return PressureStateWriteResult(
            state_update_skipped=True,
            pressure_state_prev_hash=state.state_hash,
            pressure_state_new_hash=None,
            pressure_state_snapshot_path=None,
        )
    try:
        prior = load_pressure_state(path)
        prev_state_hash = prior.state_hash
        snapshot_payload: dict[str, Any] = {
            "state": state.as_dict(),
            "hash_algo": HASH_ALGO,
            "prev_state_hash": prev_state_hash or GENESIS_PREV_STATE_HASH,
            "governor_version": GOVERNOR_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        state_hash = _compute_state_hash(snapshot_payload, prev_state_hash)
        snapshot_payload["state_hash"] = state_hash
        snapshot_name = (
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{state_hash[:12]}_{uuid.uuid4().hex}.json"
        )
        snapshot_path = snapshots_dir / snapshot_name
        _atomic_write_json(snapshot_path, snapshot_payload)
        _atomic_write_json(latest_path, snapshot_payload)
        state.state_hash = state_hash
        state.prev_state_hash = prev_state_hash
        return PressureStateWriteResult(
            state_update_skipped=False,
            pressure_state_prev_hash=prev_state_hash,
            pressure_state_new_hash=state_hash,
            pressure_state_snapshot_path=str(snapshot_path),
        )
    finally:
        _unlock_file(lock_handle)


def governor_config_fingerprint(config: GovernorConfig) -> str:
    return hashlib.sha256(canonical_json_bytes(asdict(config))).hexdigest()


def _recent_runs(state: PressureState, *, window: int) -> list[dict[str, Any]]:
    runs = list(state.recent_runs or [])
    if window <= 0:
        return runs
    return runs[-window:]


def decide_budget(
    *,
    config: GovernorConfig,
    pressure_state: PressureState,
    run_context: Mapping[str, Any],
) -> BudgetDecision:
    del run_context  # Explicitly accepted for deterministic context-keyed decisions.

    reasons: list[str] = []
    k_effective = config.configured_k
    m_effective = config.configured_m
    allow_escalation = bool(config.escalation_enabled)
    mode = "normal"

    recent = _recent_runs(pressure_state, window=config.pressure_window)
    burn_spikes = sum(
        1
        for item in recent
        if bool(item.get("proof_burn_spike"))
    )
    escalation_runs = sum(1 for item in recent if bool(item.get("escalated")))

    proof_burn_spike = burn_spikes >= config.proof_burn_spike_runs
    escalation_cluster = escalation_runs >= config.escalation_cluster_runs
    admissible_collapse = pressure_state.consecutive_no_admissible >= config.admissible_collapse_runs

    requested_mode = config.mode.strip().lower()
    if requested_mode == "diagnostics_only":
        admissible_collapse = True
        reasons.append("forced_mode")
    elif requested_mode == "constrained":
        proof_burn_spike = True
        reasons.append("forced_mode")
    elif requested_mode not in {"auto", "normal", ""}:
        reasons.append("invalid_mode_fallback")

    if proof_burn_spike:
        m_effective = max(config.min_m, config.configured_m - 1)
        allow_escalation = False
        mode = "constrained"
        reasons.append("proof_burn_spike")

    if escalation_cluster:
        k_effective = min(k_effective, 3)
        allow_escalation = False
        if mode == "normal":
            mode = "constrained"
        reasons.append("escalation_cluster")

    if admissible_collapse:
        k_effective = max(k_effective, min(config.max_k, config.diagnostics_k))
        m_effective = 0
        allow_escalation = False
        mode = "diagnostics_only"
        reasons.append("admissible_collapse")

    return BudgetDecision(
        k_effective=max(1, min(k_effective, config.max_k)),
        m_effective=max(0, m_effective),
        allow_escalation=allow_escalation,
        mode=mode,
        decision_reasons=sorted(set(reasons)),
    )


def update_pressure_state(
    *,
    prior: PressureState,
    decision: BudgetDecision,
    router_telemetry: Mapping[str, Any],
    router_status: str,
    run_context: Mapping[str, Any],
    config: GovernorConfig,
) -> PressureState:
    no_admissible = router_status != "selected"
    consecutive_no_admissible = prior.consecutive_no_admissible + 1 if no_admissible else 0
    event = {
        "pipeline": str(run_context.get("pipeline", "unknown")),
        "capability": str(run_context.get("capability") or run_context.get("spec_id") or "unknown"),
        "router_attempt": int(run_context.get("router_attempt", 1)),
        "router_status": router_status,
        "mode": decision.mode,
        "proof_burn_spike": "proof_burn_spike" in decision.decision_reasons,
        "escalated": bool(router_telemetry.get("escalated", False)),
        "stage_b_evaluations": int(router_telemetry.get("stage_b_evaluations", 0)),
    }
    recent = _recent_runs(prior, window=config.pressure_window - 1)
    recent.append(event)
    return PressureState(
        consecutive_no_admissible=consecutive_no_admissible,
        recent_runs=recent,
    )


def build_governor_event(
    *,
    decision: BudgetDecision,
    config: GovernorConfig,
    run_context: Mapping[str, Any],
    router_telemetry: Mapping[str, Any],
    pressure_state_write: PressureStateWriteResult,
) -> dict[str, Any]:
    return {
        "event_type": "proof_budget_governor",
        "pipeline": str(run_context.get("pipeline", "unknown")),
        "capability": str(run_context.get("capability") or run_context.get("spec_id") or "unknown"),
        "router_attempt": int(run_context.get("router_attempt", 1)),
        "governor": {
            "mode": decision.mode,
            "k_effective": decision.k_effective,
            "m_effective": decision.m_effective,
            "allow_escalation": decision.allow_escalation,
            "reasons": list(decision.decision_reasons),
            "governor_version": decision.governor_version,
            "config_fingerprint": governor_config_fingerprint(config),
            "pressure_state_prev_hash": pressure_state_write.pressure_state_prev_hash,
            "pressure_state_new_hash": pressure_state_write.pressure_state_new_hash,
            "pressure_state_snapshot_path": pressure_state_write.pressure_state_snapshot_path,
            "state_update_skipped": pressure_state_write.state_update_skipped,
        },
        "router_telemetry": dict(router_telemetry),
    }
