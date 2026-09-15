"""Fail-closed, exact process-image adoption for the maintenance resident.

This is deliberately not a service manager.  Its sole effectful primitive is an
``execve`` of the interpreter and module fixed by a digest-bound configuration.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from sentientos import maintenance_successor_generation_adoption as successor

CONFIG_SCHEMA = "sentientos.maintenance_resident_runtime_adoption_config:v1"
PROVENANCE_SCHEMA = "sentientos.maintenance_resident_runtime_launch_provenance:v1"
EVENT_SCHEMA = "sentientos.maintenance_resident_runtime_transition_event:v1"
RECEIPT_SCHEMA = "sentientos.maintenance_resident_runtime_adoption_receipt:v1"
TRANSITION_ENV = "SENTIENTOS_MAINTENANCE_RESIDENT_RUNTIME_TRANSITION_ID"
CONFIG_ENV = "SENTIENTOS_MAINTENANCE_RESIDENT_RUNTIME_ADOPTION_CONFIG"
ZERO_DIGEST = "sha256:" + "0" * 64
PHASES = ("resident_adoption_intent_recorded", "predecessor_resident_provenance_verified",
          "maintenance_runtime_quiescence_confirmed", "self_exec_requested",
          "successor_launch_provenance_verified", "successor_resident_readiness_recorded",
          "resident_adoption_completed")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Mapping[str, Any], omitted: str | None = None) -> str:
    body = {k: v for k, v in value.items() if k != omitted} if omitted else dict(value)
    return "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()


_FIELDS = {"schema_version", "enabled", "continuity_policy_path", "continuity_policy_digest",
    "successor_adoption_config_path", "successor_adoption_config_digest",
    "automatic_continuity_config_path", "automatic_continuity_config_digest",
    "repository_identity", "repository_root", "python_executable", "daemon_module",
    "daemon_entrypoint", "working_directory", "inherited_environment_allowlist",
    "required_environment", "state_root", "transition_journal_path", "provenance_root",
    "receipt_root", "stop_marker", "quiescence_timeout_seconds", "readiness_timeout_seconds",
    "maximum_successful_transitions", "maximum_wall_clock_seconds", "config_digest"}


def validate_config(value: Mapping[str, Any]) -> dict[str, Any]:
    cfg = dict(value)
    if set(cfg) != _FIELDS or cfg.get("schema_version") != CONFIG_SCHEMA or type(cfg.get("enabled")) is not bool:
        raise ValueError("invalid_resident_adoption_config")
    if cfg.get("config_digest") != digest(cfg, "config_digest"):
        raise ValueError("resident_adoption_config_digest_invalid")
    for key in ("repository_root", "python_executable", "daemon_entrypoint", "working_directory",
                "state_root", "transition_journal_path", "provenance_root", "receipt_root", "stop_marker",
                "continuity_policy_path", "successor_adoption_config_path"):
        if not Path(str(cfg[key])).is_absolute():
            raise ValueError(key + "_must_be_absolute")
    if os.path.realpath(str(cfg["python_executable"])) != str(cfg["python_executable"]):
        raise ValueError("python_executable_not_realpath")
    if cfg["daemon_module"] != "sentientosd" or not isinstance(cfg["inherited_environment_allowlist"], list):
        raise ValueError("resident_launch_contract_invalid")
    if any(k in {"PYTHONPATH", "PYTHONHOME", TRANSITION_ENV} for k in cfg["inherited_environment_allowlist"]):
        raise ValueError("unbound_interpreter_environment")
    if not isinstance(cfg["required_environment"], dict) or any(k in {"PYTHONPATH", "PYTHONHOME", TRANSITION_ENV} for k in cfg["required_environment"]):
        raise ValueError("invalid_required_environment")
    for key in ("quiescence_timeout_seconds", "readiness_timeout_seconds", "maximum_wall_clock_seconds"):
        if type(cfg[key]) not in (int, float) or cfg[key] <= 0: raise ValueError("invalid_resident_bound")
    if type(cfg["maximum_successful_transitions"]) is not int or cfg["maximum_successful_transitions"] < 1:
        raise ValueError("invalid_resident_bound")
    return cfg


def load_config(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.is_symlink() or not p.is_file(): raise ValueError("resident_config_not_regular")
    return validate_config(json.loads(p.read_text(encoding="utf-8")))


def _write_exact(path: Path, value: Mapping[str, Any]) -> None:
    data = canonical_bytes(value) + b"\n"; path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data: raise ValueError("resident_custody_conflict")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())


def _rows(cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = Path(str(cfg["transition_journal_path"])); rows: list[dict[str, Any]] = []
    if not path.exists(): return rows
    prior = ZERO_DIGEST
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("schema_version") != EVENT_SCHEMA or row.get("prior_event_digest") != prior or row.get("event_digest") != digest(row, "event_digest"):
            raise ValueError("resident_transition_journal_corrupt")
        prior = row["event_digest"]; rows.append(row)
    return rows


def _append(cfg: Mapping[str, Any], phase: str, transition_id: str, handoff: Mapping[str, Any]) -> dict[str, Any]:
    rows = _rows(cfg); row = {"schema_version": EVENT_SCHEMA, "config_digest": cfg["config_digest"],
        "transition_id": transition_id, "phase": phase, "lineage_id": handoff["lineage_id"],
        "predecessor_generation_digest": handoff["predecessor_generation_digest"],
        "successor_generation_digest": handoff["successor_generation_digest"],
        "pending_handoff_event_digest": handoff["pending_handoff_event_digest"],
        "prior_event_digest": rows[-1]["event_digest"] if rows else ZERO_DIGEST}
    row["event_digest"] = digest(row, "event_digest")
    path = Path(str(cfg["transition_journal_path"])); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "ab") as handle: handle.write(canonical_bytes(row) + b"\n"); handle.flush(); os.fsync(handle.fileno())
    return row


def transition_id(cfg: Mapping[str, Any], handoff: Mapping[str, Any]) -> str:
    return digest({"config_digest": cfg["config_digest"], "lineage_id": handoff["lineage_id"],
        "predecessor_generation_digest": handoff["predecessor_generation_digest"],
        "successor_generation_digest": handoff["successor_generation_digest"],
        "continuity_receipt_digest": handoff["continuity_receipt_digest"],
        "pending_handoff_event_digest": handoff["pending_handoff_event_digest"]})


class MaintenanceResidentRuntimeAdoptionController:
    def __init__(self, config: Mapping[str, Any], *, execve: Callable[[str, list[str], Mapping[str, str]], Any] = os.execve) -> None:
        self.config = validate_config(config); self._execve = execve; self._health: dict[str, Any] = {
            "status": "configured" if self.config["enabled"] else "disabled", "read_only": True}

    def health(self) -> dict[str, Any]: return dict(self._health)

    def _environment(self, tid: str | None = None) -> dict[str, str]:
        env = {key: os.environ[key] for key in self.config["inherited_environment_allowlist"] if key in os.environ}
        env.update({str(k): str(v) for k, v in self.config["required_environment"].items()})
        if tid is not None: env[TRANSITION_ENV] = tid
        return env

    def capture_baseline(self, generation: Mapping[str, Any], *, argv: list[str] | None = None) -> dict[str, Any]:
        if not self.config["enabled"]: raise ValueError("resident_adoption_disabled")
        observed_argv = list(sys.argv if argv is None else argv)
        expected = [str(self.config["daemon_entrypoint"])]
        if observed_argv != expected or os.path.realpath(sys.executable) != self.config["python_executable"] or Path.cwd().resolve() != Path(self.config["working_directory"]):
            raise ValueError("resident_launch_provenance_mismatch")
        env_digest = "sha256:" + hashlib.sha256(canonical_bytes(self._environment())).hexdigest()
        record = {"schema_version": PROVENANCE_SCHEMA, "config_digest": self.config["config_digest"],
            "repository_identity": self.config["repository_identity"], "repository_root": self.config["repository_root"],
            "lineage_id": generation["lineage_id"], "represented_generation_ordinal": generation["ordinal"],
            "represented_generation_digest": generation["generation_digest"], "represented_generation_base_sha": generation["base_sha"],
            "repository_commit": generation["base_sha"], "python_executable": self.config["python_executable"],
            "daemon_entrypoint": self.config["daemon_entrypoint"], "cwd": self.config["working_directory"],
            "argv": expected, "environment_identity_digest": env_digest, "pid": os.getpid(),
            "process_instance_id": f"baseline:{generation['generation_digest']}",
            "startup_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        record["provenance_digest"] = digest(record)
        _write_exact(Path(self.config["provenance_root"]) / f"generation-{generation['ordinal']}.json", record)
        self._health = {"status": "baseline_provenance_ready", "read_only": True,
                        "resident_ordinal": generation["ordinal"], "resident_generation_digest": generation["generation_digest"]}
        return record

    def readiness_guard(self, handoff: Mapping[str, Any]) -> bool:
        receipt = Path(self.config["receipt_root"]) / (transition_id(self.config, handoff).removeprefix("sha256:") + ".json")
        if not receipt.is_file(): return False
        value = json.loads(receipt.read_text(encoding="utf-8"))
        return value.get("schema_version") == RECEIPT_SCHEMA and value.get("receipt_digest") == digest(value, "receipt_digest") and value.get("successor_generation_digest") == handoff["successor_generation_digest"]

    def request_replacement(self, handoff: Mapping[str, Any]) -> dict[str, Any]:
        if not self.config["enabled"] or os.name != "posix": raise ValueError("resident_adoption_unsupported_or_disabled")
        if Path(self.config["stop_marker"]).exists(): raise ValueError("resident_adoption_paused")
        if not handoff.get("predecessor_quiescence_confirmed") or handoff.get("successor_start_attempted"):
            raise ValueError("resident_handoff_not_eligible")
        tid = transition_id(self.config, handoff)
        for phase in PHASES[:4]: _append(self.config, phase, tid, handoff)
        argv = [self.config["python_executable"], "-m", self.config["daemon_module"]]
        env = self._environment(tid); self._health = {"status": "self_exec_requested", "read_only": True, "transition_id": tid}
        try: self._execve(self.config["python_executable"], argv, env)
        except Exception as exc:
            self._health = {"status": "blocked", "reason": "self_exec_failed", "detail": str(exc), "terminal": True, "read_only": True}
            raise
        return {"status": "self_exec_requested", "transition_id": tid, "executable": argv[0], "argv": argv,
                "environment_identity_digest": "sha256:" + hashlib.sha256(canonical_bytes(env)).hexdigest()}

    def complete_post_exec(self, handoff: Mapping[str, Any], marker: str) -> dict[str, Any]:
        tid = transition_id(self.config, handoff)
        if marker != tid: raise ValueError("resident_transition_marker_mismatch")
        rows = _rows(self.config)
        if [r["phase"] for r in rows[-4:]] != list(PHASES[:4]) or any(r["transition_id"] != tid for r in rows[-4:]):
            raise ValueError("resident_transition_intent_mismatch")
        for phase in PHASES[4:6]: _append(self.config, phase, tid, handoff)
        receipt = {"schema_version": RECEIPT_SCHEMA, "config_digest": self.config["config_digest"], "transition_id": tid,
            "lineage_id": handoff["lineage_id"], "predecessor_generation_digest": handoff["predecessor_generation_digest"],
            "successor_generation_digest": handoff["successor_generation_digest"], "continuity_receipt_digest": handoff["continuity_receipt_digest"],
            "pending_handoff_event_digest": handoff["pending_handoff_event_digest"], "status": "resident_ready"}
        receipt["receipt_digest"] = digest(receipt, "receipt_digest")
        _write_exact(Path(self.config["receipt_root"]) / (tid.removeprefix("sha256:") + ".json"), receipt)
        _append(self.config, PHASES[6], tid, handoff)
        self._health = {"status": "resident_ready", "read_only": True, "transition_id": tid,
                        "resident_ordinal": handoff["successor_ordinal"]}
        return receipt


def inspect(config: Mapping[str, Any]) -> dict[str, Any]:
    cfg = validate_config(config); rows = _rows(cfg)
    return {"status": "disabled" if not cfg["enabled"] else (rows[-1]["phase"] if rows else "configured"),
            "read_only": True, "transition_event_count": len(rows), "config_digest": cfg["config_digest"]}


__all__ = ["CONFIG_SCHEMA", "PROVENANCE_SCHEMA", "EVENT_SCHEMA", "RECEIPT_SCHEMA", "TRANSITION_ENV", "CONFIG_ENV",
           "PHASES", "MaintenanceResidentRuntimeAdoptionController", "validate_config", "load_config", "transition_id", "inspect"]
