"""Exact, fail-closed process-image adoption for the maintenance resident.

The controller is intentionally not a service manager.  It can only prove the
canonical successor handoff and replace itself with the interpreter/module
contract sealed in its persistent configuration.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from sentientos import maintenance_authority_continuity as continuity
from sentientos import maintenance_authority_continuity_auto_derivation as auto_continuity
from sentientos import maintenance_commit_publication as publication
from sentientos import maintenance_successor_generation_adoption as successor

CONFIG_SCHEMA = "sentientos.maintenance_resident_runtime_adoption_config:v1"
PROVENANCE_SCHEMA = "sentientos.maintenance_resident_runtime_launch_provenance:v2"
EVENT_SCHEMA = "sentientos.maintenance_resident_runtime_transition_event:v3"
RECEIPT_SCHEMA = "sentientos.maintenance_resident_runtime_adoption_receipt:v2"
TRANSITION_ENV = "SENTIENTOS_MAINTENANCE_RESIDENT_RUNTIME_TRANSITION_ID"
CONFIG_ENV = "SENTIENTOS_MAINTENANCE_RESIDENT_RUNTIME_ADOPTION_CONFIG"
SUCCESSOR_CONFIG_ENV = "SENTIENTOS_MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION_CONFIG"
AUTO_CONFIG_ENV = "SENTIENTOS_MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION_CONFIG"
ZERO_DIGEST = "sha256:" + "0" * 64
PHASES = ("resident_adoption_intent_recorded", "predecessor_resident_provenance_verified",
          "maintenance_runtime_quiescence_confirmed", "self_exec_requested",
          "successor_launch_provenance_verified", "successor_resident_readiness_recorded",
          "resident_adoption_completed")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any, omitted: str | None = None) -> str:
    body = {k: v for k, v in value.items() if k != omitted} if omitted else value
    return "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: str | Path, reason: str) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError(reason)
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(reason)
    return value


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
        if not Path(str(cfg[key])).is_absolute(): raise ValueError(key + "_must_be_absolute")
    if os.path.realpath(str(cfg["python_executable"])) != str(cfg["python_executable"]):
        raise ValueError("python_executable_not_realpath")
    if cfg["daemon_module"] != "sentientosd" or not isinstance(cfg["inherited_environment_allowlist"], list):
        raise ValueError("resident_launch_contract_invalid")
    if any(not isinstance(k, str) or k in {"PYTHONPATH", "PYTHONHOME", TRANSITION_ENV} for k in cfg["inherited_environment_allowlist"]):
        raise ValueError("unbound_interpreter_environment")
    if (not isinstance(cfg["required_environment"], dict) or
            any(not isinstance(k, str) or not isinstance(v, str) or k in {"PYTHONPATH", "PYTHONHOME", TRANSITION_ENV}
                for k, v in cfg["required_environment"].items())):
        raise ValueError("invalid_required_environment")
    for key in ("quiescence_timeout_seconds", "readiness_timeout_seconds", "maximum_wall_clock_seconds"):
        if type(cfg[key]) not in (int, float) or cfg[key] <= 0: raise ValueError("invalid_resident_bound")
    if type(cfg["maximum_successful_transitions"]) is not int or cfg["maximum_successful_transitions"] < 1:
        raise ValueError("invalid_resident_bound")
    if not cfg["enabled"]:
        return cfg

    repo = Path(str(cfg["repository_root"])).resolve(strict=True)
    if str(repo) != cfg["repository_root"] or Path(cfg["working_directory"]).resolve(strict=True) != repo:
        raise ValueError("resident_repository_root_mismatch")
    entrypoint = (repo / "sentientosd.py").resolve(strict=True)
    if entrypoint != Path(cfg["daemon_entrypoint"]).resolve(strict=True):
        raise ValueError("resident_daemon_entrypoint_not_canonical")
    python = Path(cfg["python_executable"])
    if not python.is_file(): raise ValueError("resident_python_executable_invalid")
    policy = continuity.validate_policy(_load_object(cfg["continuity_policy_path"], "continuity_policy_invalid"))
    if policy["policy_digest"] != cfg["continuity_policy_digest"]:
        raise ValueError("continuity_policy_digest_mismatch")
    successor_cfg = successor.load_config(cfg["successor_adoption_config_path"])
    if successor_cfg["config_digest"] != cfg["successor_adoption_config_digest"]:
        raise ValueError("successor_adoption_config_digest_mismatch")
    if (successor_cfg["continuity_policy_digest"] != policy["policy_digest"] or
            Path(successor_cfg["continuity_policy_path"]).resolve() != Path(cfg["continuity_policy_path"]).resolve() or
            successor_cfg["repository_identity"] != cfg["repository_identity"] or
            Path(successor_cfg["repository_root"]).resolve() != repo):
        raise ValueError("resident_successor_lineage_binding_mismatch")
    auto_path = str(cfg["automatic_continuity_config_path"])
    if bool(auto_path) != bool(cfg["automatic_continuity_config_digest"]):
        raise ValueError("automatic_continuity_binding_incomplete")
    if auto_path:
        if not Path(auto_path).is_absolute(): raise ValueError("automatic_continuity_config_path_must_be_absolute")
        automatic = auto_continuity.load_config(auto_path)
        if (automatic["config_digest"] != cfg["automatic_continuity_config_digest"] or
                automatic["continuity_policy_digest"] != policy["policy_digest"] or
                automatic["successor_adoption_config_digest"] != successor_cfg["config_digest"] or
                automatic["repository_identity"] != cfg["repository_identity"] or
                Path(automatic["repository_root"]).resolve() != repo):
            raise ValueError("automatic_continuity_config_digest_mismatch")
    required = cfg["required_environment"]
    topology = {
        CONFIG_ENV: required.get(CONFIG_ENV),
        SUCCESSOR_CONFIG_ENV: required.get(SUCCESSOR_CONFIG_ENV),
    }
    expected = {
        CONFIG_ENV: required.get(CONFIG_ENV),  # load_config binds this to its source path
        SUCCESSOR_CONFIG_ENV: str(Path(cfg["successor_adoption_config_path"]).resolve()),
    }
    if not topology[CONFIG_ENV] or topology[SUCCESSOR_CONFIG_ENV] != expected[SUCCESSOR_CONFIG_ENV]:
        raise ValueError("resident_topology_environment_binding_mismatch")
    for env_name, binding in topology.items():
        if not binding or not Path(str(binding)).is_absolute() or str(Path(str(binding)).resolve()) != binding:
            raise ValueError("resident_topology_environment_binding_mismatch")
    if auto_path:
        if required.get(AUTO_CONFIG_ENV) != str(Path(auto_path).resolve()):
            raise ValueError("resident_topology_environment_binding_mismatch")
    elif AUTO_CONFIG_ENV in required:
        raise ValueError("contradictory_automatic_continuity_environment_binding")
    state = Path(cfg["state_root"]).resolve()
    for key in ("transition_journal_path", "provenance_root", "receipt_root", "stop_marker"):
        bound = Path(cfg[key]).resolve()
        if bound != state and state not in bound.parents: raise ValueError("resident_custody_outside_state_root")
        if bound == repo or repo in bound.parents: raise ValueError("resident_custody_inside_repository")
    configured_path = cfg["required_environment"].get(CONFIG_ENV)
    if configured_path and (not Path(configured_path).is_absolute() or str(Path(configured_path).resolve()) != configured_path):
        raise ValueError("resident_config_environment_binding_mismatch")
    cfg.update(repository_root=str(repo), working_directory=str(repo), daemon_entrypoint=str(entrypoint))
    return cfg


def load_config(path: str | Path) -> dict[str, Any]:
    cfg = validate_config(_load_object(path, "resident_config_not_regular"))
    configured = cfg["required_environment"].get(CONFIG_ENV)
    if cfg["enabled"] and (not configured or Path(configured).resolve() != Path(path).resolve()):
        raise ValueError("resident_config_environment_binding_mismatch")
    return cfg


def _write_exact(path: Path, value: Mapping[str, Any]) -> None:
    data = canonical_bytes(value) + b"\n"; path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data: raise ValueError("resident_custody_conflict")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())


def _rows(cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = Path(str(cfg["transition_journal_path"])); rows: list[dict[str, Any]] = []; prior = ZERO_DIGEST
    if not path.exists(): return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if (row.get("schema_version") != EVENT_SCHEMA or row.get("config_digest") != cfg["config_digest"] or
                row.get("prior_event_digest") != prior or row.get("event_digest") != digest(row, "event_digest")):
            raise ValueError("resident_transition_journal_corrupt")
        index = len(rows); expected = PHASES[index % len(PHASES)]
        if row.get("phase") != expected: raise ValueError("resident_transition_phase_invalid")
        start = index - index % len(PHASES)
        if index > start:
            first = rows[start]
            for key in ("transition_id", "lineage_id", "predecessor_generation_digest", "successor_generation_digest",
                        "continuity_receipt_digest", "pending_handoff_event_digest"):
                if row.get(key) != first.get(key): raise ValueError("resident_transition_chain_branched")
        prior = row["event_digest"]; rows.append(row)
    return rows


def _append(cfg: Mapping[str, Any], phase: str, tid: str, evidence: Mapping[str, Any], **detail: Any) -> dict[str, Any]:
    rows = _rows(cfg); expected = PHASES[len(rows) % len(PHASES)]
    if phase != expected: raise ValueError("resident_transition_phase_invalid")
    if rows and len(rows) % len(PHASES) and rows[-1]["transition_id"] != tid:
        raise ValueError("resident_transition_already_in_flight")
    row = {"schema_version": EVENT_SCHEMA, "config_digest": cfg["config_digest"], "transition_id": tid,
        "phase": phase, "lineage_id": evidence["lineage_id"],
        "predecessor_generation_digest": evidence["predecessor_generation_digest"],
        "successor_generation_digest": evidence["successor_generation_digest"],
        "continuity_receipt_digest": evidence["continuity_receipt_digest"],
        "pending_handoff_event_digest": evidence["pending_handoff_event_digest"],
        "prior_event_digest": rows[-1]["event_digest"] if rows else ZERO_DIGEST, **detail}
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
    def __init__(self, config: Mapping[str, Any], *, execve: Callable[[str, list[str], Mapping[str, str]], Any] = os.execve,
                 clock: Callable[[], float] = time.time, process_observer: Callable[[], Mapping[str, Any]] | None = None) -> None:
        self.config = validate_config(config); self._execve = execve; self._clock = clock
        self._process_observer = process_observer or self._observe_process
        self._started = clock(); self._startup_timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._baseline: dict[str, Any] | None = None
        self._health: dict[str, Any] = {"status": "configured" if self.config["enabled"] else "disabled", "read_only": True}

    def health(self) -> dict[str, Any]: return dict(self._health)

    def _within_lifecycle(self) -> None:
        if self._clock() - self._started > float(self.config["maximum_wall_clock_seconds"]):
            raise ValueError("resident_lifecycle_bound_exhausted")

    def _transition_lock(self) -> Any:
        path = Path(self.config["state_root"]) / "resident-transition.lock"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        handle = path.open("a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            self._health = {"status": "blocked", "reason": "resident_transition_lock_busy", "read_only": True}
            raise ValueError("resident_transition_lock_busy")
        return handle

    def _environment(self, tid: str | None = None) -> dict[str, str]:
        env = {key: os.environ[key] for key in self.config["inherited_environment_allowlist"] if key in os.environ}
        env.update(self.config["required_environment"])
        if tid is not None: env[TRANSITION_ENV] = tid
        return env

    def _observe_process(self) -> Mapping[str, Any]:
        original = list(getattr(sys, "orig_argv", []))
        module = sys.modules.get("sentientosd")
        main_module = sys.modules.get("__main__")
        if module is None and getattr(getattr(main_module, "__spec__", None), "name", None) == "sentientosd":
            module = main_module
        module_file = getattr(module, "__file__", None)
        spec = getattr(module, "__spec__", None)
        return {"python_executable": os.path.realpath(sys.executable), "cwd": str(Path.cwd().resolve()),
                "argv": original, "pid": os.getpid(), "startup_timestamp": self._startup_timestamp,
                "daemon_entrypoint": str(Path(str(module_file)).resolve()) if module_file else None,
                "module_spec_origin": str(Path(str(spec.origin)).resolve()) if spec and spec.origin else None,
                "environment": {key: os.environ.get(key) for key in
                    ("PYTHONPATH", "PYTHONHOME", TRANSITION_ENV, CONFIG_ENV, SUCCESSOR_CONFIG_ENV, AUTO_CONFIG_ENV)}}

    def _repository(self, generation: Mapping[str, Any]) -> dict[str, Any]:
        repo = Path(self.config["repository_root"]); manifest = _load_object(generation["manifest_path"], "generation_manifest_invalid")
        ref = str(manifest["tracked_base_ref"]); git = str(manifest.get("git_executable", ""))
        if not Path(git).is_absolute() or os.path.realpath(git) != git or not Path(git).is_file() or not os.access(git, os.X_OK):
            raise ValueError("generation_manifest_git_executable_invalid")
        head = publication._git_text(git, repo, ["rev-parse", "HEAD"])
        symbolic = publication._git_text(git, repo, ["symbolic-ref", "-q", "HEAD"])
        ref_sha = publication._git_text(git, repo, ["rev-parse", ref])
        tree = publication._git_text(git, repo, ["show", "-s", "--format=%T", head])
        if (head != generation["base_sha"] or ref_sha != head or symbolic != ref or
                not publication._git_clean(git, repo) or publication._operation_in_progress(git, repo)):
            raise ValueError("exact_resident_repository_state_not_proven")
        return {"canonical_base_ref": ref, "observed_head_sha": head, "observed_commit_sha": head,
                "observed_tree_sha": tree, "observed_symbolic_ref": symbolic,
                "clean_working_tree": True, "ambiguous_git_operation_in_progress": False,
                "git_executable": git}

    def _canonical_current(self) -> dict[str, Any]:
        cfg = successor.load_config(self.config["successor_adoption_config_path"])
        return successor.reconstruct_current(cfg)[0]

    def capture_baseline(self, generation: Mapping[str, Any] | None = None, *, argv: list[str] | None = None,
                         expected_transition_marker: str | None = None) -> dict[str, Any]:
        if not self.config["enabled"]: raise ValueError("resident_adoption_disabled")
        self._within_lifecycle(); canonical = self._canonical_current()
        if generation is not None and generation.get("generation_digest") != canonical["generation_digest"]:
            successor_cfg = successor.load_config(self.config["successor_adoption_config_path"])
            verified = successor.verified_successor(successor_cfg, canonical)
            if verified is None or generation.get("generation_digest") != verified[0]["generation_digest"]:
                raise ValueError("caller_generation_not_canonical")
            canonical = verified[0]
        observation = dict(self._process_observer())
        if argv is not None: observation["argv"] = argv
        expected_argv = [self.config["python_executable"], "-m", self.config["daemon_module"]]
        if (observation.get("python_executable") != self.config["python_executable"] or
                observation.get("daemon_entrypoint") != self.config["daemon_entrypoint"] or
                observation.get("cwd") != self.config["working_directory"] or observation.get("argv") != expected_argv):
            raise ValueError("resident_launch_provenance_mismatch")
        spec_origin = observation.get("module_spec_origin")
        if spec_origin is not None and spec_origin != self.config["daemon_entrypoint"]:
            raise ValueError("resident_launch_module_spec_mismatch")
        observed_env = observation.get("environment")
        if observed_env is not None:
            if not isinstance(observed_env, Mapping) or observed_env.get("PYTHONPATH") is not None or observed_env.get("PYTHONHOME") is not None:
                raise ValueError("resident_launch_environment_mismatch")
            if (observed_env.get(CONFIG_ENV) != self.config["required_environment"][CONFIG_ENV] or
                    observed_env.get(SUCCESSOR_CONFIG_ENV) != self.config["successor_adoption_config_path"] or
                    observed_env.get(AUTO_CONFIG_ENV) != (self.config["automatic_continuity_config_path"] or None) or
                    observed_env.get(TRANSITION_ENV) != expected_transition_marker):
                raise ValueError("resident_launch_environment_mismatch")
        manifest = _load_object(canonical["manifest_path"], "generation_manifest_invalid")
        projection = (dict(observed_env) if observed_env is not None else self._environment())
        env_digest = digest(projection)
        instance = digest({"pid": observation["pid"], "startup_timestamp": observation["startup_timestamp"],
                           "generation_digest": canonical["generation_digest"], "argv": expected_argv,
                           "python_executable": observation["python_executable"],
                           "daemon_entrypoint": observation["daemon_entrypoint"], "module_spec_origin": spec_origin})
        if expected_transition_marker is None:
            journal = _rows(self.config)
            prefix = journal[len(journal) - len(journal) % len(PHASES):] if len(journal) % len(PHASES) else []
            if prefix:
                intent = prefix[0]
                bound = _load_object(intent.get("predecessor_launch_provenance_path", ""),
                                     "predecessor_launch_provenance_missing")
                if (bound.get("provenance_digest") != digest(bound, "provenance_digest") or
                        intent.get("predecessor_launch_provenance_digest") != bound.get("provenance_digest") or
                        instance != bound.get("process_instance_id") or
                        canonical.get("generation_digest") != bound.get("represented_generation_digest") or
                        self.config.get("config_digest") != bound.get("config_digest")):
                    self._health = {"status": "blocked", "reason": "foreign_predecessor_process_provenance",
                                    "terminal": True, "read_only": True}
                    raise ValueError("foreign_predecessor_process_provenance")
        repository = self._repository(canonical)
        record = {"schema_version": PROVENANCE_SCHEMA, "config_digest": self.config["config_digest"],
            "repository_identity": self.config["repository_identity"], "repository_root": self.config["repository_root"],
            "lineage_id": canonical["lineage_id"], "represented_generation_ordinal": canonical["ordinal"],
            "represented_generation_digest": canonical["generation_digest"], "represented_generation_base_sha": canonical["base_sha"],
            "manifest_digest": canonical["manifest_digest"], **repository, "python_executable": self.config["python_executable"],
            "daemon_module": self.config["daemon_module"], "daemon_entrypoint": self.config["daemon_entrypoint"],
            "module_spec_origin": spec_origin,
            "cwd": self.config["working_directory"], "argv": expected_argv, "environment_identity_digest": env_digest,
            "pid": observation["pid"], "process_instance_id": instance, "startup_timestamp": observation["startup_timestamp"]}
        if manifest.get("manifest_digest") != canonical["manifest_digest"]: raise ValueError("generation_manifest_digest_mismatch")
        record["provenance_digest"] = digest(record, "provenance_digest")
        name = instance.removeprefix("sha256:") + ".json"
        path = Path(self.config["provenance_root"]) / f"generation-{canonical['ordinal']}" / name
        _write_exact(path, record); record["provenance_path"] = str(path)
        self._baseline = record
        if expected_transition_marker is None:
            self._verify_pre_exec_prefix_predecessor()
        self._health = {"status": "baseline_provenance_ready", "read_only": True,
                        "resident_ordinal": canonical["ordinal"], "resident_generation_digest": canonical["generation_digest"]}
        return record

    def _verify_pre_exec_prefix_predecessor(self, rows: list[dict[str, Any]] | None = None) -> None:
        """Bind every resumable pre-exec prefix to its creating process instance."""
        journal = _rows(self.config) if rows is None else rows
        prefix = journal[len(journal) - len(journal) % len(PHASES):] if len(journal) % len(PHASES) else []
        if not prefix:
            return
        if len(prefix) > 4:
            raise ValueError("resident_transition_marker_missing")
        if self._baseline is None:
            raise ValueError("predecessor_launch_provenance_missing")
        intent = prefix[0]
        bound = _load_object(intent.get("predecessor_launch_provenance_path", ""),
                             "predecessor_launch_provenance_missing")
        baseline = self._baseline
        if (bound.get("provenance_digest") != digest(bound, "provenance_digest") or
                intent.get("predecessor_launch_provenance_digest") != bound.get("provenance_digest") or
                baseline.get("provenance_digest") != bound.get("provenance_digest") or
                baseline.get("process_instance_id") != bound.get("process_instance_id") or
                baseline.get("represented_generation_digest") != bound.get("represented_generation_digest") or
                baseline.get("config_digest") != bound.get("config_digest")):
            self._health = {"status": "blocked", "reason": "foreign_predecessor_process_provenance",
                            "terminal": True, "read_only": True}
            raise ValueError("foreign_predecessor_process_provenance")

    def _pending(self, asserted: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        cfg = successor.load_config(self.config["successor_adoption_config_path"]); handoff = successor.pending_handoff(cfg)
        if handoff is None or handoff.get("current_phase") != successor.PHASES[2] or not handoff["predecessor_quiescence_confirmed"] or handoff["successor_start_attempted"]:
            raise ValueError("resident_handoff_not_eligible")
        if asserted is not None and dict(asserted) != handoff: raise ValueError("caller_handoff_not_canonical")
        current, _ = successor.reconstruct_current(cfg); verified = successor.verified_successor(cfg, current)
        if verified is None: raise ValueError("successor_generation_not_verified")
        generation, receipt = verified
        if (generation["ordinal"] != current["ordinal"] + 1 or handoff["predecessor_generation_digest"] != current["generation_digest"] or
                handoff["successor_generation_digest"] != generation["generation_digest"] or handoff["continuity_receipt_digest"] != receipt["receipt_digest"]):
            raise ValueError("resident_handoff_continuity_mismatch")
        return handoff, generation, receipt

    def readiness_guard(self, asserted: Mapping[str, Any]) -> bool:
        try:
            handoff, generation, receipt = self._pending(asserted); tid = transition_id(self.config, handoff)
            path = Path(self.config["receipt_root"]) / (tid.removeprefix("sha256:") + ".json")
            value = _load_object(path, "resident_readiness_missing")
            provenance = _load_object(value["successor_launch_provenance_path"], "successor_launch_provenance_missing")
            return (value.get("schema_version") == RECEIPT_SCHEMA and value.get("receipt_digest") == digest(value, "receipt_digest") and
                value.get("config_digest") == self.config["config_digest"] and value.get("transition_id") == tid and
                value.get("lineage_id") == handoff["lineage_id"] and value.get("predecessor_generation_digest") == handoff["predecessor_generation_digest"] and
                value.get("successor_generation_digest") == generation["generation_digest"] and value.get("continuity_receipt_digest") == receipt["receipt_digest"] and
                value.get("pending_handoff_event_digest") == handoff["pending_handoff_event_digest"] and value.get("status") == "resident_ready" and
                self._baseline is not None and provenance.get("process_instance_id") == self._baseline.get("process_instance_id") and
                provenance.get("provenance_digest") == value.get("successor_launch_provenance_digest") == digest(provenance, "provenance_digest"))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError): return False

    def request_replacement(self, asserted_handoff: Mapping[str, Any] | None = None,
                            *, quiesce: Callable[[float], bool] | None = None) -> dict[str, Any]:
        if not self.config["enabled"] or os.name != "posix": raise ValueError("resident_adoption_unsupported_or_disabled")
        self._within_lifecycle()
        if Path(self.config["stop_marker"]).exists(): raise ValueError("resident_adoption_paused")
        lock = self._transition_lock()
        try:
            complete = len(_rows(self.config)) // len(PHASES)
            if complete >= self.config["maximum_successful_transitions"]: raise ValueError("resident_transition_bound_exhausted")
            handoff, generation, _ = self._pending(asserted_handoff)
            if self._baseline is None: raise ValueError("predecessor_launch_provenance_missing")
            provenance = _load_object(self._baseline["provenance_path"], "predecessor_launch_provenance_missing")
            if (provenance.get("provenance_digest") != digest(provenance, "provenance_digest") or
                    provenance.get("represented_generation_digest") != handoff["predecessor_generation_digest"] or
                    provenance.get("process_instance_id") != self._baseline["process_instance_id"]):
                raise ValueError("predecessor_launch_provenance_invalid")
            repository = self._repository(generation); tid = transition_id(self.config, handoff)
            rows = _rows(self.config); prefix = rows[len(rows) - len(rows) % len(PHASES):] if len(rows) % len(PHASES) else []
            if prefix and any(row["transition_id"] != tid for row in prefix): raise ValueError("resident_transition_already_in_flight")
            self._verify_pre_exec_prefix_predecessor(rows)
            if len(prefix) < 1:
                intent = _append(self.config, PHASES[0], tid, handoff, predecessor_ordinal=handoff["predecessor_ordinal"],
                    successor_ordinal=handoff["successor_ordinal"], predecessor_launch_provenance_path=self._baseline["provenance_path"],
                    predecessor_launch_provenance_digest=provenance["provenance_digest"], successor_repository_commit=repository["observed_commit_sha"],
                    successor_repository_tree=repository["observed_tree_sha"], git_executable=repository["git_executable"],
                    exec_argv=[self.config["python_executable"], "-m", "sentientosd"])
                prefix.append(intent)
            if len(prefix) < 2:
                prefix.append(_append(self.config, PHASES[1], tid, handoff, predecessor_launch_provenance_digest=provenance["provenance_digest"]))
            if len(prefix) < 3:
                started = self._clock()
                if quiesce is not None and (not quiesce(float(self.config["quiescence_timeout_seconds"])) or
                                            self._clock() - started > float(self.config["quiescence_timeout_seconds"])):
                    self._health = {"status": "blocked", "reason": "maintenance_runtime_quiescence_timeout", "terminal": True, "read_only": True}
                    raise ValueError("maintenance_runtime_quiescence_timeout")
                prefix.append(_append(self.config, PHASES[2], tid, handoff))
            if len(prefix) < 4:
                prefix.append(_append(self.config, PHASES[3], tid, handoff,
                    intent_event_digest=prefix[0]["event_digest"], request_timestamp=self._clock()))
            argv = [self.config["python_executable"], "-m", self.config["daemon_module"]]; env = self._environment(tid)
            self._health = {"status": "self_exec_requested", "read_only": True, "transition_id": tid}
            try: self._execve(self.config["python_executable"], argv, env)
            except Exception as exc:
                self._health = {"status": "blocked", "reason": "self_exec_failed", "detail": str(exc), "terminal": True, "read_only": True}; raise
            return {"status": "self_exec_requested", "transition_id": tid, "executable": argv[0], "argv": argv,
                    "environment_identity_digest": digest(env)}
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN); lock.close()

    def complete_post_exec(self, asserted_handoff: Mapping[str, Any] | None = None, marker: str | None = None) -> dict[str, Any]:
        lock = self._transition_lock()
        try:
            handoff, generation, receipt = self._pending(asserted_handoff); tid = transition_id(self.config, handoff)
            actual_marker = os.environ.get(TRANSITION_ENV) if marker is None else marker
            if actual_marker != tid: raise ValueError("resident_transition_marker_mismatch")
            rows = _rows(self.config); prefix = rows[len(rows) - len(rows) % len(PHASES):] if len(rows) % len(PHASES) else rows[-len(PHASES):]
            if len(prefix) < 4 or any(r["transition_id"] != tid for r in prefix):
                raise ValueError("resident_transition_intent_mismatch")
            request = prefix[3]
            requested_at = request.get("request_timestamp")
            if type(requested_at) not in (int, float): raise ValueError("resident_self_exec_timestamp_missing")
            assert isinstance(requested_at, (int, float))
            if self._clock() - float(requested_at) > float(self.config["readiness_timeout_seconds"]):
                raise ValueError("resident_readiness_timeout")
            launch = self.capture_baseline(generation, expected_transition_marker=tid)
            if len(prefix) >= 5:
                phase_launch = prefix[4]
                existing = _load_object(phase_launch["successor_launch_provenance_path"], "successor_launch_provenance_missing")
                if (existing.get("provenance_digest") != phase_launch.get("successor_launch_provenance_digest") or
                        existing.get("provenance_digest") != digest(existing, "provenance_digest")):
                    raise ValueError("successor_launch_provenance_conflict")
                if existing.get("process_instance_id") != launch.get("process_instance_id"):
                    raise ValueError("foreign_successor_process_provenance")
                launch = {**existing, "provenance_path": phase_launch["successor_launch_provenance_path"]}
            else:
                prefix.append(_append(self.config, PHASES[4], tid, handoff, successor_launch_provenance_path=launch["provenance_path"],
                    successor_launch_provenance_digest=launch["provenance_digest"]))
            readiness = {"schema_version": RECEIPT_SCHEMA, "config_digest": self.config["config_digest"], "transition_id": tid,
            "lineage_id": handoff["lineage_id"], "predecessor_ordinal": handoff["predecessor_ordinal"],
            "predecessor_generation_digest": handoff["predecessor_generation_digest"], "successor_ordinal": handoff["successor_ordinal"],
            "successor_generation_digest": generation["generation_digest"], "continuity_receipt_digest": receipt["receipt_digest"],
            "pending_handoff_event_digest": handoff["pending_handoff_event_digest"],
            "successor_launch_provenance_path": launch["provenance_path"], "successor_launch_provenance_digest": launch["provenance_digest"],
                "status": "resident_ready"}
            readiness["receipt_digest"] = digest(readiness, "receipt_digest")
            readiness_path = Path(self.config["receipt_root"]) / (tid.removeprefix("sha256:") + ".json")
            _write_exact(readiness_path, readiness)
            stored = _load_object(readiness_path, "resident_readiness_missing")
            if stored != readiness: raise ValueError("resident_readiness_conflict")
            if len(prefix) < 6:
                prefix.append(_append(self.config, PHASES[5], tid, handoff, readiness_receipt_digest=readiness["receipt_digest"]))
            elif prefix[5].get("readiness_receipt_digest") != readiness["receipt_digest"]:
                raise ValueError("resident_readiness_conflict")
            if len(prefix) < 7:
                _append(self.config, PHASES[6], tid, handoff, readiness_receipt_digest=readiness["receipt_digest"])
            elif prefix[6].get("readiness_receipt_digest") != readiness["receipt_digest"]:
                raise ValueError("resident_readiness_conflict")
            self._health = {"status": "resident_ready", "read_only": True, "transition_id": tid, "resident_ordinal": generation["ordinal"]}
            return readiness
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN); lock.close()


def inspect(config: Mapping[str, Any]) -> dict[str, Any]:
    cfg = validate_config(config); rows = _rows(cfg)
    return {"status": "disabled" if not cfg["enabled"] else (rows[-1]["phase"] if rows else "configured"),
            "read_only": True, "transition_event_count": len(rows), "config_digest": cfg["config_digest"]}


__all__ = ["CONFIG_SCHEMA", "PROVENANCE_SCHEMA", "EVENT_SCHEMA", "RECEIPT_SCHEMA", "TRANSITION_ENV", "CONFIG_ENV",
           "SUCCESSOR_CONFIG_ENV", "AUTO_CONFIG_ENV",
           "PHASES", "MaintenanceResidentRuntimeAdoptionController", "validate_config", "load_config", "transition_id", "inspect", "digest"]
