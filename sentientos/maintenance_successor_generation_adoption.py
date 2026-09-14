"""Bounded adoption of an already-derived maintenance authority successor.

This module deliberately has no derivation, Git, process-management, network, or
dynamic-code-loading surface.  It advances wake ownership only from immutable
continuity custody and a digest chained handoff journal.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from sentientos import maintenance_authority_continuity as continuity
from sentientos import maintenance_wake_daemon_adoption as wake_daemon
from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_loop_activation as activation
from sentientos import maintenance_loop_watchdog as watchdog
from sentientos import maintenance_candidate_collector as collector
from sentientos import maintenance_autonomy_cycle as autonomy
from sentientos import maintenance_health_probe as health
from sentientos import maintenance_wake_cycle as wake

CONFIG_SCHEMA = "sentientos.maintenance_successor_generation_adoption_config:v1"
HANDOFF_SCHEMA = "sentientos.maintenance_successor_generation_handoff_event:v1"
ZERO_DIGEST = "sha256:" + "0" * 64
PHASES = ("handoff_intent_recorded", "predecessor_quiescence_requested",
          "predecessor_confirmed_quiescent", "successor_start_attempted",
          "successor_confirmed_started", "handoff_completed")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any, omitted: str | None = None) -> str:
    body = {k: v for k, v in value.items() if k != omitted} if omitted else value
    return "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()


def _load(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("successor_adoption_input_not_regular")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("successor_adoption_input_not_object")
    return value


def validate_config(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "enabled", "continuity_policy_path", "continuity_policy_digest",
        "initial_generation_path", "initial_generation_digest", "initial_wake_adoption_path",
        "initial_wake_adoption_digest", "repository_identity", "repository_root", "state_root",
        "successor_configuration_root", "handoff_journal_path", "stop_marker",
        "observation_delay_seconds", "maximum_handoffs", "maximum_wall_clock_seconds",
        "shutdown_timeout_seconds"}
    allowed = required | {"config_digest"}
    if set(value) - allowed or not required.issubset(value) or value.get("schema_version") != CONFIG_SCHEMA:
        raise ValueError("invalid_successor_adoption_config")
    if type(value["enabled"]) is not bool:
        raise ValueError("invalid_successor_adoption_posture")
    for key in ("maximum_handoffs", "maximum_wall_clock_seconds"):
        if type(value[key]) is not int or value[key] < 1: raise ValueError("invalid_successor_adoption_bound")
    for key in ("observation_delay_seconds", "shutdown_timeout_seconds"):
        if type(value[key]) not in (int, float) or value[key] <= 0: raise ValueError("invalid_successor_adoption_bound")
    result = dict(value)
    expected = digest(result, "config_digest")
    if result.get("config_digest") not in (None, "", expected): raise ValueError("successor_adoption_config_digest_mismatch")
    result["config_digest"] = expected
    if not result["enabled"]: return result
    repo = Path(str(result["repository_root"])).resolve(strict=True)
    for key in ("state_root", "successor_configuration_root"):
        path = Path(str(result[key])).resolve(strict=True)
        if repo == path or repo in path.parents: raise ValueError("successor_adoption_custody_inside_repository")
    policy = continuity.validate_policy(_load(result["continuity_policy_path"]))
    if policy["policy_digest"] != result["continuity_policy_digest"]: raise ValueError("continuity_policy_digest_mismatch")
    generation = continuity.validate_generation(_load(result["initial_generation_path"]), policy)
    if generation["ordinal"] != 0 or generation["generation_digest"] != result["initial_generation_digest"]:
        raise ValueError("initial_generation_binding_mismatch")
    adoption = wake_daemon.load_adoption(result["initial_wake_adoption_path"])
    if adoption["adoption_config_digest"] != result["initial_wake_adoption_digest"]:
        raise ValueError("initial_wake_adoption_binding_mismatch")
    result.update(repository_root=str(repo), state_root=str(Path(result["state_root"]).resolve()),
                  successor_configuration_root=str(Path(result["successor_configuration_root"]).resolve()))
    return result


def load_config(path: str | Path) -> dict[str, Any]: return validate_config(_load(path))


def _journal(cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = Path(str(cfg["handoff_journal_path"])); rows: list[dict[str, Any]] = []; prior = ZERO_DIGEST
    if not path.exists(): return rows
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line); claimed = row.pop("event_digest")
            if row.get("schema_version") != HANDOFF_SCHEMA or row.get("config_digest") != cfg["config_digest"] or row.get("prior_event_digest") != prior or digest(row) != claimed:
                raise ValueError
            row["event_digest"] = claimed; rows.append(row); prior = claimed
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("successor_handoff_journal_corrupt") from exc
    # Completed transactions are six exact phases; only the last may be a prefix.
    for index, row in enumerate(rows):
        expected = PHASES[index % len(PHASES)]
        if row.get("event_type") != expected: raise ValueError("successor_handoff_recovery_ambiguous")
        start = index - index % len(PHASES)
        first = rows[start]
        for key in ("lineage_id", "predecessor_ordinal", "predecessor_generation_digest",
                    "successor_ordinal", "successor_generation_digest"):
            if row.get(key) != first.get(key): raise ValueError("successor_handoff_chain_branched")
    return rows


def _write_exact(path: Path, value: Mapping[str, Any]) -> None:
    data = canonical_bytes(value) + b"\n"; path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data: raise ValueError("successor_configuration_output_conflict")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())


def build_successor_adoption(config: Mapping[str, Any], current: Mapping[str, Any],
                             predecessor: Mapping[str, Any], successor: Mapping[str, Any]) -> dict[str, Any]:
    """Build the canonical, immutable N+1 component closure from N's schemas."""
    cfg = validate_config(config); root = Path(cfg["successor_configuration_root"]) / f"generation-{successor['ordinal']}"
    state = Path(cfg["state_root"]) / f"generation-{successor['ordinal']}"
    for directory in (root, state): directory.mkdir(parents=True, exist_ok=True, mode=0o700); directory.chmod(0o700)
    manifest = profiles.validate_manifest(_load(successor["manifest_path"]))
    if manifest["manifest_digest"] != successor["manifest_digest"] or manifest["base_sha"] != successor["base_sha"]:
        raise ValueError("successor_manifest_binding_mismatch")
    old_wake = wake.load_config(predecessor["wake_config_path"])
    old_health = health.load_config(old_wake["health_probe_configuration_path"])
    old_autonomy = autonomy.load_config(old_wake["autonomy_cycle_configuration_path"])
    old_collector = collector.load_config(old_autonomy["collector_configuration_path"])
    old_watchdog = watchdog.load_config(old_autonomy["watchdog_configuration_path"])
    paths = {name: root / f"{name}.json" for name in ("watchdog", "collector", "autonomy", "health", "wake")}
    checked_bundle = profiles.verify_profile_bundle(successor["manifest_path"], str(old_wake["evaluation_time"]))
    if checked_bundle["status"] != "profile_bundle_ready" or checked_bundle["bundle_digest"] != successor["profile_bundle_digest"]:
        raise ValueError("successor_profile_bundle_binding_mismatch")
    profile_dir = Path(manifest["output_directory"])
    watchdog_state = state / "watchdog"
    for p in (watchdog_state, state / "workspace", state / "scratch", state / "inbox"):
        p.mkdir(mode=0o700); p.chmod(0o700)
    wd = dict(old_watchdog); wd.update(base_sha=successor["base_sha"], state_root=str(watchdog_state),
        workspace_root=str(state / "workspace"), scratch_root=str(state / "scratch"),
        candidate_inbox_roots=[str(state / "inbox")])
    for field, filename in profiles.FILENAMES.items():
        if field in wd: wd[field] = str(profile_dir / filename)
    wd.pop("config_digest", None); wd = watchdog.validate_config(wd); _write_exact(paths["watchdog"], wd)
    cc = dict(old_collector); cc.update(base_sha=successor["base_sha"], activation_profile_bundle_manifest_path=str(Path(successor["manifest_path"]).resolve()), watchdog_configuration_path=str(paths["watchdog"].resolve()), collector_state_root=str(state / "collector"), receipt_journal_path=str(state / "collector" / "receipts.jsonl"), stop_marker=str(state / "collector" / "STOP")); cc.pop("config_digest", None)
    for p in (state / "collector",): p.mkdir(mode=0o700); p.chmod(0o700)
    cc = collector.validate_config(cc); _write_exact(paths["collector"], cc)
    ac = dict(old_autonomy); ac.update(base_sha=successor["base_sha"], activation_profile_bundle_manifest_path=str(Path(successor["manifest_path"]).resolve()), collector_configuration_path=str(paths["collector"].resolve()), watchdog_configuration_path=str(paths["watchdog"].resolve()), external_cycle_state_root=str(state / "autonomy"), cycle_receipt_journal_path=str(state / "autonomy" / "receipts.jsonl"), stop_marker=str(state / "autonomy" / "STOP")); ac.pop("config_digest", None)
    (state / "autonomy").mkdir(mode=0o700); (state / "autonomy").chmod(0o700); ac = autonomy.validate_config(ac); _write_exact(paths["autonomy"], ac)
    hc = dict(old_health); hc.update(base_sha=successor["base_sha"], probe_state_root=str(state / "health"), governed_signal_output_root=str(state / "signals"), receipt_journal_path=str(state / "health" / "receipts.jsonl")); hc.pop("config_digest", None)
    for p in (state / "health", state / "signals"): p.mkdir(mode=0o700); p.chmod(0o700)
    hc = health.validate_config(hc); _write_exact(paths["health"], hc)
    wc = dict(old_wake); wc.update(base_sha=successor["base_sha"], health_probe_configuration_path=str(paths["health"].resolve()), autonomy_cycle_configuration_path=str(paths["autonomy"].resolve()), external_wake_state_root=str(state / "wake"), wake_receipt_journal_path=str(state / "wake" / "receipts.jsonl"), stop_marker=str(state / "wake" / "STOP")); wc.pop("config_digest", None)
    (state / "wake").mkdir(mode=0o700); (state / "wake").chmod(0o700); wc = wake.validate_config(wc); _write_exact(paths["wake"], wc)
    # The new digest gets new cadence custody, but starts at N's exact next due instant.
    next_due = wake_daemon.inspect(predecessor)["next_due_utc"]
    cadence = state / "cadence"; cadence.mkdir(mode=0o700); cadence.chmod(0o700)
    output = root / "wake-adoption.json"
    activation.render_wake_daemon_adoption(output, wake_config_path=paths["wake"], cadence_state_root=cadence,
        enabled=True, cadence_interval_seconds=int(predecessor["cadence_interval_seconds"]), schedule_anchor_utc=next_due,
        initial_run_posture="immediate", maximum_cycles=int(predecessor["maximum_cycles"]),
        maximum_daemon_wall_clock_seconds=int(predecessor["maximum_daemon_wall_clock_seconds"]),
        shutdown_timeout_seconds=float(predecessor["shutdown_timeout_seconds"]))
    result = wake_daemon.load_adoption(output)
    if wake.doctor(wc, evaluation_time=str(wc["evaluation_time"]))["status"] != "maintenance_wake_ready":
        raise ValueError("successor_wake_closure_not_ready")
    return cast(dict[str, Any], result)


def _append(cfg: Mapping[str, Any], event_type: str, generation: Mapping[str, Any], successor: Mapping[str, Any], **detail: Any) -> dict[str, Any]:
    rows = _journal(cfg); row = {"schema_version": HANDOFF_SCHEMA, "config_digest": cfg["config_digest"],
        "event_type": event_type, "lineage_id": generation["lineage_id"],
        "predecessor_ordinal": generation["ordinal"], "predecessor_generation_digest": generation["generation_digest"],
        "successor_ordinal": successor["ordinal"], "successor_generation_digest": successor["generation_digest"],
        "prior_event_digest": rows[-1]["event_digest"] if rows else ZERO_DIGEST, **detail}
    row["event_digest"] = digest(row); path = Path(str(cfg["handoff_journal_path"])); path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "ab") as handle: handle.write(canonical_bytes(row) + b"\n"); handle.flush(); os.fsync(handle.fileno())
    return row


def reconstruct_current(config: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = validate_config(config); policy = continuity.validate_policy(_load(cfg["continuity_policy_path"]))
    generation = continuity.validate_generation(_load(cfg["initial_generation_path"]), policy)
    adoption = wake_daemon.load_adoption(cfg["initial_wake_adoption_path"])
    rows = _journal(cfg)
    complete_length = len(rows) - len(rows) % len(PHASES)
    for offset in range(0, complete_length, len(PHASES)):
        completed = rows[offset + len(PHASES) - 1]
        if completed["predecessor_generation_digest"] != generation["generation_digest"]: raise ValueError("successor_handoff_chain_branched")
        generation = continuity.validate_generation(_load(Path(policy["generation_root"]) / f"generation-{completed['successor_ordinal']}.json"), policy)
        if generation["generation_digest"] != completed["successor_generation_digest"]:
            raise ValueError("successor_handoff_chain_branched")
        adoption = wake_daemon.load_adoption(completed["successor_wake_adoption_path"])
        if adoption["adoption_config_digest"] != completed["successor_wake_adoption_digest"]: raise ValueError("successor_wake_adoption_binding_mismatch")
    return generation, adoption


def verified_successor(config: Mapping[str, Any], current: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    cfg = validate_config(config); policy = continuity.validate_policy(_load(cfg["continuity_policy_path"])); ordinal = int(current["ordinal"]) + 1
    generation_path = Path(policy["generation_root"]) / f"generation-{ordinal}.json"; receipt_path = Path(policy["receipt_root"]) / f"receipt-{ordinal}.json"
    if not generation_path.exists():
        if (Path(policy["generation_root"]) / f"generation-{ordinal + 1}.json").exists(): raise ValueError("successor_generation_skipped")
        return None
    successor = continuity.validate_generation(_load(generation_path), policy); receipt = _load(receipt_path)
    if set(receipt) != continuity.RECEIPT_KEYS or receipt.get("schema_version") != continuity.RECEIPT_SCHEMA or receipt.get("receipt_digest") != continuity.digest(receipt, "receipt_digest"):
        raise ValueError("successor_continuity_receipt_invalid")
    if successor["ordinal"] != ordinal or successor["predecessor_generation_digest"] != current["generation_digest"] or receipt["lineage_id"] != current["lineage_id"] or receipt["ordinal"] != ordinal or receipt["successor_generation_digest"] != successor["generation_digest"] or receipt["predecessor_generation_digest"] != current["generation_digest"] or receipt["successor_sha"] != successor["base_sha"] or receipt["successor_manifest_digest"] != successor["manifest_digest"] or receipt["successor_profile_bundle_digest"] != successor["profile_bundle_digest"] or successor["prior_receipt_digest"] != receipt["receipt_digest"] or receipt["same_or_narrower"] is not True:
        raise ValueError("successor_continuity_binding_mismatch")
    return successor, receipt


def _owner_lock_free(adoption: Mapping[str, Any]) -> bool:
    """Prove absence of an effectful owner and reject ambiguous wake intent."""
    wake_daemon.inspect(adoption)
    path = Path(str(adoption["cadence_state_root"])) / "wake-daemon-owner.lock"
    path.touch(exist_ok=True)
    with path.open("r+") as handle:
        try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return False
        finally:
            try: fcntl.flock(handle, fcntl.LOCK_UN)
            except OSError: pass
    return True


class MaintenanceSuccessorGenerationOwner:
    """Own exactly one wake owner and perform bounded, forward-only handoffs."""
    def __init__(self, config: Mapping[str, Any], *, wake_owner_factory: Callable[[Mapping[str, Any]], Any] = wake_daemon.MaintenanceWakeOwner,
                 successor_adoption_builder: Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]] | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc), waiter: Callable[[float], None] = time.sleep) -> None:
        self.config = validate_config(config); self._factory = wake_owner_factory
        self._builder = successor_adoption_builder or (lambda cur, old, nxt: build_successor_adoption(self.config, cur, old, nxt))
        self._clock = clock; self._waiter = waiter; self._owner: Any = None; self._thread: threading.Thread | None = None
        self._stop = threading.Event(); self._lock = threading.Lock(); self._health = {"status": "configured" if self.config["enabled"] else "disabled", "read_only": True}

    def health(self) -> dict[str, Any]:
        with self._lock: return dict(self._health)

    def _set(self, status: str, **fields: Any) -> None:
        with self._lock: self._health = {"status": status, "read_only": True, **fields}

    def start(self) -> bool:
        if not self.config["enabled"]: return False
        current, adoption = reconstruct_current(self.config)
        if len(_journal(self.config)) % len(PHASES) == 0:
            self._owner = self._factory(adoption)
            if not self._owner.start(): self._set("degraded", reason="current_wake_owner_start_failed"); return False
        self._set("running_generation", lineage_id=current["lineage_id"], current_ordinal=current["ordinal"], current_generation_digest=current["generation_digest"])
        self._thread = threading.Thread(target=self._run, name="sentientosd-maintenance-successor", daemon=True); self._thread.start(); return True

    def _run(self) -> None:
        began = time.monotonic(); count = 0
        while not self._stop.is_set() and count < self.config["maximum_handoffs"] and time.monotonic() - began < self.config["maximum_wall_clock_seconds"]:
            try:
                result = self.handoff_once(); count += int(result["status"] == "handoff_completed")
            except Exception as exc:
                self._set("degraded", reason=str(exc), terminal=True)
                return
            self._stop.wait(float(self.config["observation_delay_seconds"]))

    def handoff_once(self) -> dict[str, Any]:
        current, current_adoption = reconstruct_current(self.config)
        if Path(self.config["stop_marker"]).exists() or Path(current_adoption["stop_marker"]).exists(): self._set("paused"); return {"status": "paused", "effect_count": 0}
        rows = _journal(self.config); pending = rows[len(rows) - len(rows) % len(PHASES):] if len(rows) % len(PHASES) else []
        found = verified_successor(self.config, current)
        if found is None: self._set("waiting_for_successor", current_ordinal=current["ordinal"]); return {"status": "waiting_for_successor", "effect_count": 0}
        successor, receipt = found
        if pending and (pending[0]["successor_generation_digest"] != successor["generation_digest"] or
                        pending[0].get("continuity_receipt_digest") != receipt["receipt_digest"]):
            raise ValueError("successor_handoff_chain_branched")
        adoption = wake_daemon.validate_adoption(self._builder(current, current_adoption, successor))
        output = Path(self.config["successor_configuration_root"]) / f"generation-{successor['ordinal']}" / "wake-adoption.json"
        output.parent.mkdir(parents=True, exist_ok=True); data = canonical_bytes(adoption) + b"\n"
        if output.exists() and output.read_bytes() != data: raise ValueError("successor_configuration_output_conflict")
        if not output.exists(): output.write_bytes(data)
        phase = len(pending)
        if phase == 0: _append(self.config, PHASES[0], current, successor, continuity_receipt_digest=receipt["receipt_digest"]); phase = 1
        if phase == 1: _append(self.config, PHASES[1], current, successor); phase = 2
        if phase <= 2:
            self._set("quiescing_predecessor")
            if self._owner is not None:
                if not self._owner.stop(): self._set("bounded_shutdown_timeout"); return {"status": "bounded_shutdown_timeout", "effect_count": 1}
                self._owner = None
            elif not _owner_lock_free(current_adoption):
                raise ValueError("predecessor_owner_custody_ambiguous")
            _append(self.config, PHASES[2], current, successor); phase = 3
        if phase == 3: _append(self.config, PHASES[3], current, successor); phase = 4
        if phase == 4 and not _owner_lock_free(adoption): raise ValueError("successor_start_custody_ambiguous")
        candidate = self._factory(adoption)
        if phase <= 4:
            if not candidate.start(): self._set("degraded", reason="successor_start_failed"); return {"status": "successor_start_failed", "effect_count": 1}
            self._owner = candidate; _append(self.config, PHASES[4], current, successor); phase = 5
        elif self._owner is None:
            if not _owner_lock_free(adoption): raise ValueError("successor_start_custody_ambiguous")
            if not candidate.start(): raise ValueError("successor_reconstruction_failed")
            self._owner = candidate
        _append(self.config, PHASES[5], current, successor, successor_wake_adoption_path=str(output), successor_wake_adoption_digest=adoption["adoption_config_digest"])
        self._set("running_successor_generation", lineage_id=successor["lineage_id"], current_ordinal=successor["ordinal"], current_generation_digest=successor["generation_digest"])
        return {"status": "handoff_completed", "effect_count": 1, "successor_ordinal": successor["ordinal"]}

    def stop(self) -> bool:
        self._set("shutdown_requested"); self._stop.set(); thread = self._thread
        if thread: thread.join(float(self.config["shutdown_timeout_seconds"]))
        if thread and thread.is_alive(): self._set("bounded_shutdown_timeout"); return False
        return bool(self._owner is None or self._owner.stop())


def inspect(config: Mapping[str, Any]) -> dict[str, Any]:
    current, adoption = reconstruct_current(config); successor = verified_successor(config, current)
    return {"status": "successor_adoption_ready", "lineage_id": current["lineage_id"], "current_ordinal": current["ordinal"],
            "current_generation_digest": current["generation_digest"], "current_wake_adoption_digest": adoption["adoption_config_digest"],
            "successor_ordinal": successor[0]["ordinal"] if successor else None, "handoff_event_count": len(_journal(validate_config(config)))}


__all__ = ["CONFIG_SCHEMA", "HANDOFF_SCHEMA", "PHASES", "MaintenanceSuccessorGenerationOwner", "build_successor_adoption", "validate_config", "load_config", "reconstruct_current", "verified_successor", "inspect"]
