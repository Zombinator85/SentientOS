Warning: truncated output (original token count: 17680)
Total output lines: 1268

"""Bounded parent custody for one configured maintenance resident.

This controller is deliberately narrower than a service manager.  Its child contract
is derived from the already validated resident-adoption configuration, and recovery
can only replay that contract for the canonically reconstructed generation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from sentientos.platform_fcntl import fcntl, require_flock
from sentientos.private_file_custody import (
    PrivateFileCustodyError, open_private_directory, read_private_file_at,
)
from sentientos import maintenance_resident_runtime_adoption as resident
from sentientos import maintenance_successor_generation_adoption as successor
from sentientos.runtime.services import ChildProcessServiceAdapter, HealthResult, ServiceAdapter

STATE_SCHEMA = "sentientos.maintenance_resident_parent_supervision_state:v1"
RECEIPT_SCHEMA = "sentientos.maintenance_resident_parent_supervision_receipt:v1"
PARENT_PROCESS_ATTRIBUTION_V1 = "sentientos.parent_process_attribution:v1"
PARENT_PROCESS_ATTRIBUTION_V2 = "sentientos.parent_process_attribution:v2"
SERVICE_ID = "exact-maintenance-resident"
PARENT_CONFIG_PATH_ENV = "SENTIENTOS_RESIDENT_PARENT_CONFIG_PATH"
MAX_PARENT_STATE_BYTES = 1_048_576
MAX_PARENT_RESTART_HISTORY = 65_536
MAX_PARENT_RECEIPT_BYTES = 16_777_216
MAX_PARENT_RECEIPT_ROWS = 65_536
MAX_PARENT_RECEIPT_LINE_BYTES = 65_536
MAX_PARENT_SEQUENCE = MAX_PARENT_RECEIPT_ROWS
MAX_PARENT_PROVENANCE_FILES = 4096
MAX_PARENT_PROVENANCE_BYTES = 16_777_216
MAX_PARENT_PROVENANCE_RECORD_BYTES = 262_144
_PARENT_PROVENANCE_NAME = re.compile(r"[0-9a-f]{64}\.json\Z")
_LEGACY_LAUNCH_FIELDS = frozenset({"child_spec_digest", "config_digest", "lineage_id",
    "generation_digest", "pid", "launched_at", "launch_provenance_digest"})
_PROCESS_GENERATION_LAUNCH_FIELDS = _LEGACY_LAUNCH_FIELDS | frozenset({
    "child_linux_proc_start_ticks", "child_linux_proc_start_ticks_posture"})



def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _valid_aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 128:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (OverflowError, OSError, TypeError, ValueError):
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _linux_process_start_ticks(process_id: int) -> int | None:
    """Read Linux procfs stat field 22 as a limited PID-reuse discriminator."""
    if sys.platform != "linux" or type(process_id) is not int or process_id < 1:
        return None
    descriptor: int | None = None
    try:
        descriptor = os.open(f"/proc/{process_id}/stat",
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0))
        chunks: list[bytes] = []
        remaining = 4097
        while remaining:
            chunk = os.read(descriptor, min(4096, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    except OSError:
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(raw) > 4096 or not raw.endswith(b"\\n"):
        return None
    separator = raw.rfind(b")")
    if separator < 0:
        return None
    try:
        observed_pid = int(raw[:raw.find(b" ")])
        fields_from_state = raw[separator + 1:].split()
        # Field 3 (state) is index 0; Linux starttime field 22 is index 19.
        start_ticks = int(fields_from_state[19])
    except (ValueError, IndexError):
        return None
    if observed_pid != process_id or start_ticks < 0:
        return None
    return start_ticks


def _valid_launch_process_generation(value: Mapping[str, Any]) -> bool:
    """Accept legacy PID-only provenance while validating new generation-bound launches."""
    fields = frozenset(value)
    if fields == _LEGACY_LAUNCH_FIELDS:
        return True
    if fields != _PROCESS_GENERATION_LAUNCH_FIELDS:
        return False
    ticks = value.get("child_linux_proc_start_ticks")
    posture = value.get("child_linux_proc_start_ticks_posture")
    return ((posture == "linux_procfs_starttime_field_22"
             and type(ticks) is int and ticks >= 0)
            or (posture == "unavailable" and ticks is None))


def _valid_parent_process_observation(value: object, schema: str) -> bool:
    legacy_fields = {
        "process_id", "parent_process_id", "observed_at",
        "monotonic_observed_ns", "instance_nonce",
    }
    procfs_fields = legacy_fields | {
        "linux_proc_start_ticks", "linux_proc_start_ticks_posture",
    }
    expected_fields = (legacy_fields if schema == PARENT_PROCESS_ATTRIBUTION_V1
        else procfs_fields if schema == PARENT_PROCESS_ATTRIBUTION_V2 else set())
    if not isinstance(value, dict) or set(value) != expected_fields:
        return False
    if (type(value.get("process_id")) is not int or value["process_id"] < 1
            or type(value.get("parent_process_id")) is not int or value["parent_process_id"] < 0
            or type(value.get("monotonic_observed_ns")) is not int
            or value["monotonic_observed_ns"] < 0
            or not isinstance(value.get("instance_nonce"), str)
            or re.fullmatch(r"[0-9a-f]{32}", value["instance_nonce"]) is None):
        return False
    if schema == PARENT_PROCESS_ATTRIBUTION_V2:
        ticks = value.get("linux_proc_start_ticks")
        posture = value.get("linux_proc_start_ticks_posture")
        if ((posture == "linux_procfs_starttime_field_22" and
                (type(ticks) is not int or ticks < 0))
                or (posture == "unavailable" and ticks is not None)
                or posture not in {"linux_procfs_starttime_field_22", "unavailable"}):
            return False
    try:
        started = datetime.fromisoformat(str(value["observed_at"]).replace("Z", "+00:00"))
    except (OverflowError, OSError, TypeError, ValueError):
        return False
    return started.tzinfo is not None and started.utcoffset() is not None


def _build_exact_child_environment(
    config: Mapping[str, Any], source_environment: Mapping[str, str],
    commissioned_config_path: Path | None,
) -> dict[str, str]:
    env = {key: source_environment[key] for key in config["inherited_environment_allowlist"]
        if key in source_environment}
    env.update(config["required_environment"])
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop(resident.TRANSITION_ENV, None)
    env.pop(PARENT_CONFIG_PATH_ENV, None)
    if commissioned_config_path is not None:
        env[PARENT_CONFIG_PATH_ENV] = str(commissioned_config_path)
    return env


def _resident_child_spec(config: Mapping[str, Any], environment: Mapping[str, str]) -> dict[str, Any]:
    argv = [str(config["python_executable"]), "-m", "sentientosd"]
    return {"service_id": SERVICE_ID, "executable": argv[0], "argv": argv,
        "cwd": str(config["working_directory"]), "environment": dict(environment),
        "resident_config_digest": config["config_digest"]}


def _parse_parent_receipt_journal(raw: bytes, expected_spec_digest: str) -> list[dict[str, Any]]:
    if raw and not raw.endswith(b"\\n"):
        raise ValueError("parent_receipt_journal_truncated")
    lines = raw.split(b"\\n")[:-1] if raw else []
    if len(lines) > MAX_PARENT_RECEIPT_ROWS:
        raise ValueError("parent_receipt_journal_retention_limit_exceeded")
    rows: list[dict[str, Any]] = []
    known_process_instances: set[str] = set()
    for index, line in enumerate(lines, start=1):
        if not line or len(line) > MAX_PARENT_RECEIPT_LINE_BYTES:
            raise ValueError("parent_receipt_journal_record_invalid")
        row = json.loads(line.decode("utf-8"))
        if not isinstance(row, dict):
            raise ValueError("parent_receipt_journal_record_invalid")
        claimed = row.pop("receipt_digest", None)
        if (set(row) != {"schema_version", "sequence", "timestamp", "event",
                "child_spec_digest", "detail"}
                or row["schema_version"] != RECEIPT_SCHEMA
                or type(row["sequence"]) is not int or row["sequence"] != index
                or row["child_spec_digest"] != expected_spec_digest
                or not isinstance(row["event"], str) or not row["event"] or len(row["event"]) > 128
                or not _valid_aware_timestamp(row["timestamp"])
                or not isinstance(row["detail"], dict)
                or _digest(row) != claimed):
            raise ValueError("parent_receipt_journal_binding_invalid")
        detail = row["detail"]
        attribution_schema = detail.get("parent_process_identity_schema")
        if ("parent_process_identity_schema" in detail
                and (attribution_schema not in {
                        PARENT_PROCESS_ATTRIBUTION_V1, PARENT_PROCESS_ATTRIBUTION_V2}
                    or "parent_process_instance_id" not in detail)):
            raise ValueError("parent_process_attribution_schema_invalid")
        if "parent_process_instance_id" in detail:
            process_instance_id = detail["parent_process_instance_id"]
            if (not isinstance(process_instance_id, str)
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", process_instance_id) is None):
                raise ValueError("parent_process_instance_identity_invalid")
            observation = detail.get("parent_process_observation")
            observation_schema = (attribution_schema if isinstance(attribution_schema, str)
                else PARENT_PROCESS_ATTRIBUTION_V1)
            if row["event"] == "parent_startup":
                if (not _valid_parent_process_observation(
                        observation, observation_schema)
                        or _digest(observation) != process_instance_id
                        or process_instance_id in known_process_instances):
                    raise ValueError("parent_process_startup_observation_invalid")
                known_process_instances.add(process_instance_id)
            elif (process_instance_id not in known_process_instances or observation is not None):
                raise ValueError("parent_process_event_lineage_invalid")
        row["receipt_digest"] = claimed
        if _canonical(row) != line:
            raise ValueError("parent_receipt_journal_noncanonical")
        rows.append(row)
    return rows


def _validate_parent_state_snapshot(raw: bytes, *, expected_spec_digest: str,
                                    expected_config_digest: str,
                                    rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not raw.endswith(b"\\n"):
        raise ValueError("parent_state_noncanonical")
    value = json.loads(raw[:-1].decode("utf-8"))
    legacy_fields = {"schema_version", "child_spec_digest", "sequence", "restart_history",
        "panic_latched", "shutdown_latched", "restart_budget_exhausted", "status",
        "generation_digest", "launch"}
    current_fields = legacy_fields | {"receipt_head_digest", "state_digest"}
    if (not isinstance(value, dict) or set(value) not in (legacy_fields, current_fields)
            or _canonical(value) + b"\\n" != raw
            or value["schema_version"] != STATE_SCHEMA
            or value["child_spec_digest"] != expected_spec_digest):
        raise ValueError("parent_state_binding_mismatch")
    if set(value) == current_fields:
        body = {key: item for key, item in value.items() if key != "state_digest"}
        expected_head = rows[-1]["receipt_digest"] if rows else None
        if value["state_digest"] != _digest(body) or value["receipt_head_digest"] != expected_head:
            raise ValueError("parent_state_digest_or_receipt_head_mismatch")
    if (type(value["sequence"]) is not int or value["sequence"] != len(rows)
            or not isinstance(value["restart_history"], list)
            or len(value["restart_history"]) > MAX_PARENT_RESTART_HISTORY
            or any(type(item) not in (int, float) or not math.isfinite(item)
                   for item in value["restart_history"])
            or any(type(value[key]) is not bool for key in
                ("panic_latched", "shutdown_latched", "restart_budget_exhausted"))
            or not isinstance(value["status"], str) or not value["status"]
            or len(value["status"]) > 128):
        raise ValueError("parent_state_shape_invalid")
    generation_digest = value["generation_digest"]
    launch = value["launch"]
    if generation_digest is not None and not isinstance(generation_digest, str):
        raise ValueError("parent_generation_identity_invalid")
    if launch is not None:
        body = {key: item for key, item in launch.items()
            if key != "launch_provenance_digest"} if isinstance(launch, dict) else {}
        if (not isinstance(launch, dict) or not _valid_launch_process_generation(launch)
                or launch["child_spec_digest"] != expected_spec_digest
                or launch["config_digest"] != expected_config_digest
                or not isinstance(launch["lineage_id"], str) or not launch["lineage_id"]
                or not isinstance(launch["generation_digest"], str) or not launch["generation_digest"]
                or type(launch["pid"]) is not int or launch["pid"] < 1
                or type(launch["launched_at"]) not in (int, float)
                or not math.isfinite(launch["launched_at"])
                or launch["launch_provenance_digest"] != _digest(body)
                or launch["generation_digest"] != generation_digest):
            raise ValueError("parent_launch_provenance_invalid")
    return value


class ResidentParentLifecycleEvidenceReader:
    """Read commissioned parent lifecycle history without owning or controlling it."""

    def __init__(self, commissioned_config_path: Path, *,
                 parent_pid: Callable[[], int] = os.getppid,
                 child_pid: Callable[[], int] = os.getpid) -> None:
        path = Path(commissioned_config_path)
        if not path.is_absolute():
            raise ValueError("parent_observation_config_path_must_be_absolute")
        self.config_path = path
        self._parent_pid = parent_pid
        self._child_pid = child_pid

    def world_state_records(self, *, observed_at: str) -> list[dict[str, Any]]:
        if not _valid_aware_timestamp(observed_at):
            raise ValueError("parent_observation_time_invalid")
        from sentientos import maintenance_initial_posix_resident_commissioning as commissioning

        verified = commissioning.verify_commissioned_resident_config(self.config_path)
        config = resident.validate_config(verified["resident_config"])
        if not config["enabled"]:
            raise ValueError("parent_observation_supervision_disabled")
        config_path = self.config_path.resolve(strict=True)
        environment = _build_exact_child_environment(config, os.environ, config_path)
        child_spec_digest = _digest(_resident_child_spec(config, environment))
        expected_parent_pid = self._parent_pid()
        expected_child_pid = self._child_pid()
        if (type(expected_parent_pid) is not int or expected_parent_pid < 1
                or type(expected_child_pid) is not int or expected_child_pid < 1):
            raise ValueError("parent_observation_pid_invalid")
        root = Path(config["state_root"]) / "parent-supervision"
        directory_fd = open_private_directory(root, create=False)
        try:
            journal_bytes = read_private_file_at(directory_fd, "parent-receipts.jsonl",
                max_bytes=MAX_PARENT_RECEIPT_BYTES, require_private_mode=True)
            state_bytes = read_private_file_at(directory_fd, "parent-state.json",
                max_bytes=MAX_PARENT_STATE_BYTES, require_private_mode=True)
        finally:
            os.close(directory_fd)
        rows = _parse_parent_receipt_journal(journal_bytes, child_spec_digest)
        state = _validate_parent_state_snapshot(
            state_bytes, expected_spec_digest=child_spec_digest,
            expected_config_digest=config["config_digest"], rows=rows)
        startup_rows = [row for row in rows if row["event"] == "parent_startup"]
        if not startup_rows:
            raise ValueError("parent_observation_startup_receipt_missing")
        startup = startup_rows[-1]
        parent_observation = startup["detail"]["parent_process_observation"]
        parent_instance_id = startup["detail"]["parent_process_instance_id"]
        if parent_observation["process_id"] != expected_parent_pid:
            raise ValueError("parent_observation_process_relation_unverified")
        claimed_start_ticks = parent_observation.get("linux_proc_start_ticks")
        if claimed_start_ticks is not None:
            current_start_ticks = _linux_process_start_ticks(expected_parent_pid)
            if current_start_ticks is None or current_start_ticks != claimed_start_ticks:
                raise ValueError("parent_observation_kernel_process_start_mismatch")
            process_relation_posture = (
                "commissioned_parent_and_child_pid_match_linux_procfs_start_ticks;"
                "pid_reuse_within_one_kernel_tick_not_excluded")
        else:
            process_relation_posture = (
                "commissioned_parent_pid_and_child_launch_pid_match_pid_reuse_not_excluded")
        selected = [row for row in rows
            if row["detail"].get("parent_process_instance_id") == parent_instance_id]
        active_launch = state.get("launch")
        if (not isinstance(active_launch, Mapping)
                or not _valid_launch_process_generation(active_launch)
                or active_launch.get("pid") != expected_child_pid):
            raise ValueError("parent_observation_child_launch_unverified")
        launch_receipts = [row for row in selected
            if row["event"] == "launch_provenance_verified"
            and {key: row["detail"].get(key) for key in active_launch} == dict(active_launch)]
        if len(launch_receipts) != 1:
            raise ValueError("parent_observation_launch_receipt_unverified")
        launch_receipt = launch_receipts[0]
        child_ticks = active_launch.get("child_linux_proc_start_ticks")
        if type(child_ticks) is int:
            observed_child_ticks = _linux_process_start_ticks(expected_child_pid)
            if observed_child_ticks != child_ticks:
                raise ValueError("parent_observation_child_process_generation_mismatch")
        compact_receipts = []
        for row in selected[-8:]:
            detail = row["detail"]
            launch_detail = detail.get("launch")
            launch_detail = launch_detail if isinstance(launch_detail, Mapping) else {}
            compact_receipts.append({
                "sequence": row["sequence"], "timestamp": row["timestamp"],
                "event": row["event"], "receipt_digest": row["receipt_digest"],
                "child_pid": detail.get("pid", launch_detail.get("pid")),
                "generation_digest": detail.get("generation_digest", launch_detail.get("generation_digest")),
                "launch_provenance_digest": detail.get(
                    "launch_provenance_digest", launch_detail.get("launch_provenance_digest")),
                "readiness_basis": detail.get("readiness_basis"),
                "reason": detail.get("reason"), "presence": detail.get("presence"),
            })
        latest = selected[-1] if selected else startup
        launch = dict(active_launch)
        payload = {
            "schem…7680 tokens truncated…             "no_resident_transactions", "complete_resident_transactions_only"}:
                return False
            successor_config = successor.load_config(
                self.config["successor_adoption_config_path"])
            generation, _adoption = successor.reconstruct_current(successor_config)
            if (generation.get("generation_digest") != launch["generation_digest"]
                    or generation.get("generation_digest") != self._generation_digest
                    or generation.get("lineage_id") != launch["lineage_id"]):
                return False
            verifier = resident.MaintenanceResidentRuntimeAdoptionController(self.config)
            repository = verifier._repository(generation)
            environment_keys = ( "PYTHONPATH", "PYTHONHOME", resident.TRANSITION_ENV,
                resident.CONFIG_ENV, resident.SUCCESSOR_CONFIG_ENV, resident.AUTO_CONFIG_ENV )
            environment = {key: self._environment.get(key) for key in environment_keys}
            expected_argv = [self.config["python_executable"], "-m",
                self.config["daemon_module"]]
            expected_fields = {
                "schema_version", "config_digest", "repository_identity", "repository_root",
                "lineage_id", "represented_generation_ordinal", "represented_generation_digest",
                "represented_generation_base_sha", "manifest_digest", "canonical_base_ref",
                "observed_head_sha", "observed_commit_sha", "observed_tree_sha",
                "observed_symbolic_ref", "clean_working_tree",
                "ambiguous_git_operation_in_progress", "git_executable", "python_executable",
                "daemon_module", "daemon_entrypoint", "module_spec_origin", "cwd", "argv",
                "environment_identity_digest", "pid", "process_instance_id", "startup_timestamp",
                "provenance_digest"}
            matches: list[dict[str, Any]] = []
            for value in self._read_generation_provenance(int(generation["ordinal"])):
                if (set(value) != expected_fields
                        or value.get("schema_version") != resident.PROVENANCE_SCHEMA
                        or value.get("provenance_digest") != resident.digest(value, "provenance_digest")
                        or value.get("config_digest") != self.config["config_digest"]
                        or value.get("repository_identity") != self.config["repository_identity"]
                        or value.get("repository_root") != self.config["repository_root"]
                        or value.get("lineage_id") != generation["lineage_id"]
                        or type(value.get("represented_generation_ordinal")) is not int
                        or value.get("represented_generation_ordinal") != generation["ordinal"]
                        or not isinstance(value.get("represented_generation_digest"), str)
                        or not isinstance(value.get("represented_generation_base_sha"), str)
                        or not isinstance(value.get("manifest_digest"), str)
                        or type(value.get("pid")) is not int or value["pid"] < 1
                        or not isinstance(value.get("startup_timestamp"), str)):
                    return False
                instance = resident.digest({
                    "pid": value["pid"], "startup_timestamp": value["startup_timestamp"],
                    "generation_digest": value["represented_generation_digest"],
                    "argv": expected_argv,
                    "python_executable": self.config["python_executable"],
                    "daemon_entrypoint": self.config["daemon_entrypoint"],
                    "module_spec_origin": value.get("module_spec_origin")})
                if value.get("process_instance_id") != instance:
                    return False
                if (value.get("python_executable") != self.config["python_executable"]
                        or value.get("daemon_module") != self.config["daemon_module"]
                        or value.get("daemon_entrypoint") != self.config["daemon_entrypoint"]
                        or value.get("module_spec_origin") not in
                            (None, self.config["daemon_entrypoint"])
                        or value.get("cwd") != self.config["working_directory"]
                        or value.get("argv") != expected_argv
                        or value.get("environment_identity_digest")
                            != resident.digest(environment)
                        or type(value.get("clean_working_tree")) is not bool
                        or value.get("clean_working_tree") is not True
                        or value.get("ambiguous_git_operation_in_progress") is not False):
                    return False
                if value.get("pid") != launch["pid"]:
                    continue
                timestamp = datetime.fromisoformat(
                    value["startup_timestamp"].replace("Z", "+00:00"))
                if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                    return False
                if timestamp.timestamp() + 1 < float(launch["launched_at"]):
                    continue
                if (value.get("represented_generation_digest") != generation["generation_digest"]
                        or value.get("represented_generation_base_sha") != generation["base_sha"]
                        or value.get("manifest_digest") != generation["manifest_digest"]
                        or value.get("canonical_base_ref") != repository["canonical_base_ref"]
                        or value.get("observed_head_sha") != repository["observed_head_sha"]
                        or value.get("observed_commit_sha") != repository["observed_commit_sha"]
                        or value.get("observed_tree_sha") != repository["observed_tree_sha"]
                        or value.get("observed_symbolic_ref") != repository["observed_symbolic_ref"]
                        or value.get("git_executable") != repository["git_executable"]):
                    return False
                matches.append(value)
            if len(matches) != 1:
                return False
            selected = matches[0]
            self._verified_child_provenance = {
                "process_instance_id": selected["process_instance_id"],
                "provenance_digest": selected["provenance_digest"],
                "generation_digest": selected["represented_generation_digest"],
            }
            return True
        except Exception:
            self._verified_child_provenance = None
            return False

    def _current_generation(self) -> dict[str, Any]:
        posture = resident.inspect_transition_custody(self.config)
        status = posture["status"]
        if status not in {"no_resident_transactions", "complete_resident_transactions_only"}:
            self._receipt("fail_closed_custody", {"custody": posture})
            raise ValueError("resident_transition_custody_not_recoverable")
        generation, _ = successor.reconstruct_current(
            successor.load_config(self.config["successor_adoption_config_path"]))
        if self._generation_digest is not None and generation["generation_digest"] != self._generation_digest:
            self._receipt("fail_closed_custody", {"reason": "maintenance_lineage_changed"})
            raise ValueError("maintenance_lineage_changed")
        return cast(dict[str, Any], generation)

    def _launch_exact(self, generation: Mapping[str, Any], *, recovery: bool) -> None:
        self._status = "launching"; self._launch = None
        self._receipt("recovery_attempt" if recovery else "child_launch_attempt",
                      {"generation_digest": generation["generation_digest"]})
        try:
            self._adapter.start()
            identity = dict(self._adapter.identity)
            observed_argv = identity.get("argv")
            if (not isinstance(observed_argv, (list, tuple)) or tuple(observed_argv) != self._argv or identity.get("cwd") != self._spec["cwd"] or
                    identity.get("adapter") != "child_process" or identity.get("name") != SERVICE_ID or
                    not isinstance(identity.get("pid"), int)):
                raise ValueError("exact_child_identity_mismatch")
            launch = {"child_spec_digest": self._spec_digest, "config_digest": self.config["config_digest"],
                "lineage_id": generation["lineage_id"], "generation_digest": generation["generation_digest"],
                "pid": identity["pid"], "launched_at": self._clock(),
                "child_linux_proc_start_ticks": self._observe_process_start_ticks(cast(int, identity["pid"])),
                "child_linux_proc_start_ticks_posture": "linux_procfs_starttime_field_22"}
            if launch["child_linux_proc_start_ticks"] is None:
                launch["child_linux_proc_start_ticks_posture"] = "unavailable"
            launch["launch_provenance_digest"] = _digest(launch)
            self._launch = launch; self._generation_digest = str(generation["generation_digest"])
            self._status = "awaiting_resident_readiness"
            self._receipt("launch_provenance_verified", launch)
        except Exception as exc:
            self._status = "recovery_failed" if recovery else "launch_failed"
            self._receipt("recovery_failure" if recovery else "fail_closed_provenance",
                          {"reason": type(exc).__name__})
            raise

    @staticmethod
    def _observe_pid_presence(pid: int) -> bool | None:
        """Use OS PID presence only to deny duplicate launch, never to adopt or signal."""
        if os.name != "posix":
            return None
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return None

    def _observe_process_start_ticks(self, pid: int) -> int | None:
        try:
            value = self._process_start_ticks_observer(pid)
        except Exception:
            return None
        return value if type(value) is int and value >= 0 else None

    def start(self) -> None:
        if self._panic: raise RuntimeError("panic_latched")
        if self._shutdown: raise RuntimeError("shutdown_latched")
        generation = self._current_generation()
        if self._launch is not None:
            prior_pid = self._launch.get("pid")
            if type(prior_pid) is not int or prior_pid < 1:
                self._status = "prior_child_unreconciled"
                self._receipt("prior_child_reconciliation_blocked",
                    {"reason": "prior_launch_pid_invalid"})
                raise RuntimeError("prior_child_process_unreconciled")
            prior_ticks = self._launch.get("child_linux_proc_start_ticks")
            current_ticks = self._observe_process_start_ticks(prior_pid)
            termination_evidence: dict[str, Any] | None = None
            if current_ticks is not None:
                if type(prior_ticks) is int and current_ticks != prior_ticks:
                    termination_evidence = {
                        "posture": "prior_process_generation_terminated_pid_reused",
                        "prior_start_ticks": prior_ticks,
                        "observed_start_ticks": current_ticks,
                    }
            else:
                try:
                    present = self._process_presence_observer(prior_pid)
                except Exception:
                    present = None
                if present is False:
                    termination_evidence = {"posture": "prior_pid_absent",
                        "prior_start_ticks": prior_ticks, "observed_start_ticks": None}
            if termination_evidence is None:
                self._status = "prior_child_unreconciled"
                self._receipt("prior_child_reconciliation_blocked", {
                    "pid": prior_pid, "prior_start_ticks": prior_ticks,
                    "observed_start_ticks": current_ticks,
                    "launch_provenance_digest": self._launch["launch_provenance_digest"]})
                raise RuntimeError("prior_child_process_unreconciled")
            now = self._clock()
            self._restart_history = [stamp for stamp in self._restart_history
                if now - stamp <= self._window]
            if len(self._restart_history) >= self._budget:
                self._exhausted = True; self._status = "restart_budget_exhausted"
                self._receipt("restart_budget_exhaustion",
                    {"used": len(self._restart_history), "budget": self._budget})
                raise RuntimeError("restart_budget_exhausted")
            self._restart_history.append(now)
            self._receipt("orphan_child_absence_reconciled", {
                "pid": prior_pid,
                "process_termination_evidence": termination_evidence,
                "prior_launch_provenance_digest": self._launch["launch_provenance_digest"],
                "generation_digest": generation["generation_digest"]})
            self._launch_exact(generation, recovery=True)
            return
        self._launch_exact(generation, recovery=False)

    def observe(self) -> None:
        if self._panic or self._shutdown or self._exhausted: return
        health = self._adapter.health()
        if not isinstance(health, HealthResult):
            self._fail("invalid_child_health")
            return
        if not health.ready:
            self._unexpected_death(health.reason)
            return
        if self._launch is None:
            self._fail("missing_launch_provenance")
            return
        if self._status == "awaiting_resident_readiness":
            if self._readiness_guard(dict(self._launch)):
                self._status = "maintenance_eligible"
                self._receipt("child_resident_readiness", {
                    "launch_provenance_digest": self._launch["launch_provenance_digest"],
                    "readiness_basis": self._readiness_basis,
                    "child_provenance": self._verified_child_provenance})
                if len(self._restart_history) > 0:
                    self._receipt("recovery_success", {"launch_provenance_digest": self._launch["launch_provenance_digest"]})
            else:
                self._receipt("fail_closed_readiness", {"reason": "resident_readiness_not_proven"})

    def _fail(self, reason: str) -> None:
        self._status = "fail_closed"; self._receipt("fail_closed_provenance", {"reason": reason})

    def _unexpected_death(self, reason: str) -> None:
        prior = self._launch["launch_provenance_digest"] if self._launch else None
        self._status = "child_dead"; self._receipt("unexpected_child_death", {"reason": reason, "launch_provenance_digest": prior})
        try: generation = self._current_generation()
        except ValueError:
            self._receipt("recovery_eligibility", {"eligible": False, "reason": "custody_not_proven"}); return
        now = self._clock(); self._restart_history = [stamp for stamp in self._restart_history if now - stamp <= self._window]
        if len(self._restart_history) >= self._budget:
            self._exhausted = True; self._status = "restart_budget_exhausted"
            self._receipt("restart_budget_exhaustion", {"used": len(self._restart_history), "budget": self._budget}); return
        self._receipt("recovery_eligibility", {"eligible": True, "generation_digest": generation["generation_digest"]})
        delay = min(self._max_backoff, self._min_backoff * (2 ** len(self._restart_history)))
        self._sleep(delay); self._restart_history.append(self._clock()); self._persist()
        try: self._launch_exact(generation, recovery=True)
        except Exception: return

    def shutdown(self, *, panic: bool = False) -> None:
        self._shutdown = True; self._panic = self._panic or panic
        self._adapter.stop(); self._status = "panic_stopped" if panic else "stopped"
        if self._state_recovery_valid:
            self._receipt("panic_stop" if panic else "explicit_shutdown")

    def status(self) -> dict[str, Any]:
        return {"schema_version": STATE_SCHEMA, "status": self._status,
            "maintenance_eligible": self._status == "maintenance_eligible",
            "panic_latched": self._panic, "shutdown_latched": self._shutdown,
            "restart_budget_exhausted": self._exhausted, "restart_count": len(self._restart_history),
            "child_spec_digest": self._spec_digest, "generation_digest": self._generation_digest,
            "launch_provenance_digest": self._launch.get("launch_provenance_digest") if self._launch else None,
            "parent_process_instance_id": self._parent_process_instance_id,
            "readiness_basis": self._readiness_basis}


__all__ = ["MaintenanceResidentParentSupervisor", "ResidentParentLifecycleEvidenceReader",
    "STATE_SCHEMA", "RECEIPT_SCHEMA", "SERVICE_ID", "PARENT_CONFIG_PATH_ENV", "main"]


def main(argv: list[str] | None = None) -> int:
    """Run the parent only when an operator names an exact resident config.

    This is a separate process entrypoint; it is never composed into sentientosd
    or the resident runtime, which prevents recursive parent launch.
    """
    import argparse
    import signal
    import sys
    from threading import Event
    from sentientos import maintenance_initial_posix_resident_commissioning as commissioning

    parser = argparse.ArgumentParser(
        description="Supervise one explicitly configured SentientOS maintenance resident.")
    parser.add_argument("--config", required=True,
        help="absolute path to the commissioned resident-adoption configuration")
    args = parser.parse_args(argv)
    try:
        config_path = Path(args.config)
        if not config_path.is_absolute():
            raise ValueError("resident_config_path_must_be_absolute")
        commissioning_result = commissioning.verify_commissioned_resident_config(config_path)
        config = commissioning_result["resident_config"]
        if config.get("enabled") is not True:
            raise ValueError("resident_parent_supervision_disabled")
        _verify_parent_invocation_origin(config, executable=Path(sys.executable),
            working_directory=Path.cwd(), module_path=Path(__file__))
        require_flock()
        parent_root = Path(config["state_root"]) / "parent-supervision"
        supervisor = MaintenanceResidentParentSupervisor(
            config, state_root=parent_root, commissioned_config_path=config_path)
    except Exception as exc:
        print(f"resident parent configuration rejected: {type(exc).__name__}", file=sys.stderr)
        return 2

    stopping = Event()
    previous_handlers: dict[signal.Signals, Any] = {}

    def request_stop(_signum: int, _frame: Any) -> None:
        stopping.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.signal(signum, request_stop)
    result = 0
    try:
        supervisor.start()
        while not stopping.wait(0.5):
            supervisor.observe()
            posture = supervisor.status()
            if (posture["panic_latched"] or posture["restart_budget_exhausted"]
                    or posture["status"] in {"fail_closed", "fail_closed_state",
                        "parent_state_publication_failed", "panic_stopped"}):
                result = 2
                break
    except Exception as exc:
        print(f"resident parent supervision stopped: {type(exc).__name__}", file=sys.stderr)
        result = 2
    finally:
        try:
            supervisor.shutdown(panic=result != 0)
        except Exception:
            result = 2
        for signal_number, handler in previous_handlers.items():
            signal.signal(signal_number, handler)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
