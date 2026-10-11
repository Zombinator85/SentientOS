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
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from sentientos.platform_fcntl import fcntl, require_flock
from sentientos import maintenance_resident_runtime_adoption as resident
from sentientos import maintenance_successor_generation_adoption as successor
from sentientos.runtime.services import ChildProcessServiceAdapter, HealthResult, ServiceAdapter
from sentientos.windows_handle_custody import WindowsHandleCustodyError, read_explicit_file

STATE_SCHEMA = "sentientos.maintenance_resident_parent_supervision_state:v1"
RECEIPT_SCHEMA = "sentientos.maintenance_resident_parent_supervision_receipt:v1"
SERVICE_ID = "exact-maintenance-resident"
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



def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


class MaintenanceResidentParentSupervisor:
    """Own exactly one ``sentientosd`` child and no generation-selection policy."""

    def __init__(self, resident_config: Mapping[str, Any], *, state_root: Path,
                 resident_readiness_guard: Callable[[Mapping[str, Any]], bool] | None = None,
                 restart_budget: int = 3, rolling_restart_window: float = 300.0,
                 min_backoff: float = 0.1, max_backoff: float = 30.0,
                 clock: Callable[[], float] = time.time,
                 sleeper: Callable[[float], None] = time.sleep,
                 adapter_factory: Callable[..., ServiceAdapter] = ChildProcessServiceAdapter,
                 process_presence_observer: Callable[[int], bool | None] | None = None) -> None:
        if restart_budget < 0 or rolling_restart_window <= 0 or min_backoff < 0 or max_backoff < min_backoff:
            raise ValueError("invalid_parent_restart_policy")
        self.config = resident.validate_config(resident_config)
        if not self.config["enabled"]:
            raise ValueError("resident_parent_supervision_disabled")
        self.root = Path(state_root).resolve()
        repository = Path(self.config["repository_root"])
        if self.root == repository or repository in self.root.parents:
            raise ValueError("parent_supervision_custody_inside_repository")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            root_metadata = os.lstat(self.root)
            if (not stat.S_ISDIR(root_metadata.st_mode) or root_metadata.st_uid != os.geteuid()
                    or stat.S_IMODE(root_metadata.st_mode) & 0o077):
                raise ValueError("parent_supervision_state_root_not_private")
        self._owner_lock_fd: int | None = None
        self._acquire_owner_lock()
        self._state_path = self.root / "parent-state.json"
        self._receipt_path = self.root / "parent-receipts.jsonl"
        self._readiness_guard = (resident_readiness_guard if resident_readiness_guard is not None
            else self._verify_launch_readiness)
        self._readiness_basis = ("injected_readiness_guard" if resident_readiness_guard is not None
            else "child_owned_launch_provenance")
        self._verified_child_provenance: dict[str, Any] | None = None
        self._clock, self._sleep = clock, sleeper
        self._process_presence_observer = process_presence_observer or self._observe_pid_presence
        self._budget, self._window = restart_budget, rolling_restart_window
        self._min_backoff, self._max_backoff = min_backoff, max_backoff
        self._environment = self._exact_environment()
        self._argv = (self.config["python_executable"], "-m", "sentientosd")
        self._spec = {"service_id": SERVICE_ID, "executable": self._argv[0], "argv": list(self._argv),
            "cwd": self.config["working_directory"], "environment": self._environment,
            "resident_config_digest": self.config["config_digest"]}
        self._spec_digest = _digest(self._spec)
        self._adapter = adapter_factory(name=SERVICE_ID, argv=self._argv,
            cwd=Path(self.config["working_directory"]), environment=self._environment)
        self._sequence = 0; self._restart_history: list[float] = []
        self._receipt_count = 0; self._receipt_bytes = 0; self._receipt_head_digest: str | None = None
        self._panic = False; self._shutdown = False; self._exhausted = False
        self._status = "configured"; self._generation_digest: str | None = None
        self._launch: dict[str, Any] | None = None
        self._state_recovery_valid = True
        try:
            self._load()
            if self._state_recovery_valid:
                self._receipt("parent_startup", {"child_spec_digest": self._spec_digest})
        except Exception:
            self._release_owner_lock()
            raise

    def _acquire_owner_lock(self) -> None:
        require_flock()
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            raise OSError("parent_supervision_safe_lock_unavailable")
        descriptor = os.open(self.root / "parent-supervisor.lock",
            os.O_RDWR | os.O_CREAT | nofollow | getattr(os, "O_CLOEXEC", 0), 0o600)
        try:
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_uid != os.geteuid()):
                raise OSError("parent_supervision_lock_custody_invalid")
            os.fchmod(descriptor, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("parent_supervision_owner_already_held") from exc
            self._owner_lock_fd = descriptor
            descriptor = -1
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def _release_owner_lock(self) -> None:
        descriptor = self._owner_lock_fd
        self._owner_lock_fd = None
        if descriptor is not None:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _exact_environment(self) -> dict[str, str]:
        env = {key: os.environ[key] for key in self.config["inherited_environment_allowlist"] if key in os.environ}
        env.update(self.config["required_environment"])
        env.pop("PYTHONPATH", None); env.pop("PYTHONHOME", None); env.pop(resident.TRANSITION_ENV, None)
        return env

    def _atomic(self, value: Mapping[str, Any]) -> None:
        fd, temporary = tempfile.mkstemp(prefix=".parent-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(_canonical(value) + b"\n"); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self._state_path)
            if os.name == "posix":
                directory_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0))
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def _persist(self) -> None:
        state = {"schema_version": STATE_SCHEMA, "child_spec_digest": self._spec_digest,
            "sequence": self._sequence, "restart_history": self._restart_history,
            "panic_latched": self._panic, "shutdown_latched": self._shutdown,
            "restart_budget_exhausted": self._exhausted, "status": self._status,
            "generation_digest": self._generation_digest, "launch": self._launch,
            "receipt_head_digest": self._receipt_head_digest}
        state["state_digest"] = _digest(state)
        try:
            self._atomic(state)
        except Exception:
            self._state_recovery_valid = False
            self._panic = True; self._status = "parent_state_publication_failed"
            raise

    def _read_receipt_journal(self) -> list[dict[str, Any]]:
        try:
            raw = read_explicit_file(self._receipt_path, max_bytes=MAX_PARENT_RECEIPT_BYTES,
                require_private_acl=os.name == "nt")
        except WindowsHandleCustodyError as exc:
            if exc.args == ("explicit_file_missing",):
                return []
            raise ValueError("parent_receipt_journal_custody_invalid") from exc
        if raw and not raw.endswith(b"\n"):
            raise ValueError("parent_receipt_journal_truncated")
        lines = raw.split(b"\n")[:-1] if raw else []
        if len(lines) > MAX_PARENT_RECEIPT_ROWS:
            raise ValueError("parent_receipt_journal_retention_limit_exceeded")
        rows: list[dict[str, Any]] = []
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
                    or row["child_spec_digest"] != self._spec_digest
                    or not isinstance(row["event"], str) or not row["event"] or len(row["event"]) > 128
                    or not isinstance(row["timestamp"], str)
                    or not isinstance(row["detail"], dict)
                    or _digest(row) != claimed):
                raise ValueError("parent_receipt_journal_binding_invalid")
            row["receipt_digest"] = claimed
            if _canonical(row) != line:
                raise ValueError("parent_receipt_journal_noncanonical")
            rows.append(row)
        self._receipt_count = len(rows)
        self._receipt_bytes = len(raw)
        self._receipt_head_digest = rows[-1]["receipt_digest"] if rows else None
        return rows

    def _load(self) -> None:
        try:
            rows = self._read_receipt_journal()
            try:
                raw = read_explicit_file(self._state_path, max_bytes=MAX_PARENT_STATE_BYTES,
                    require_private_acl=True)
            except WindowsHandleCustodyError as exc:
                if exc.args == ("explicit_file_missing",):
                    if rows:
                        raise ValueError("parent_state_missing_with_receipts")
                    return
                raise ValueError("parent_state_custody_invalid") from exc
            if not raw.endswith(b"\n"):
                raise ValueError("parent_state_noncanonical")
            value = json.loads(raw[:-1].decode("utf-8"))
            legacy_fields = {"schema_version", "child_spec_digest", "sequence", "restart_history",
                "panic_latched", "shutdown_latched", "restart_budget_exhausted", "status",
                "generation_digest", "launch"}
            current_fields = legacy_fields | {"receipt_head_digest", "state_digest"}
            if (not isinstance(value, dict) or set(value) not in (legacy_fields, current_fields)
                    or _canonical(value) + b"\n" != raw
                    or value["schema_version"] != STATE_SCHEMA
                    or value["child_spec_digest"] != self._spec_digest):
                raise ValueError("parent_state_binding_mismatch")
            if set(value) == current_fields:
                body = {key: item for key, item in value.items() if key != "state_digest"}
                if (value["state_digest"] != _digest(body)
                        or value["receipt_head_digest"] != self._receipt_head_digest):
                    raise ValueError("parent_state_digest_or_receipt_head_mismatch")
            if type(value["sequence"]) is not int or value["sequence"] != len(rows):
                raise ValueError("parent_state_receipt_sequence_mismatch")
            sequence = value["sequence"]
            history = value["restart_history"]
            if (type(sequence) is not int or sequence < 0
                    or sequence > MAX_PARENT_SEQUENCE
                    or not isinstance(history, list)
                    or len(history) > MAX_PARENT_RESTART_HISTORY
                    or any(type(item) not in (int, float) or not math.isfinite(item) for item in history)
                    or any(type(value[key]) is not bool for key in
                        ("panic_latched", "shutdown_latched", "restart_budget_exhausted"))
                    or not isinstance(value["status"], str) or not value["status"]
                    or len(value["status"]) > 128):
                raise ValueError("parent_state_shape_invalid")
            launch = value["launch"]
            if launch is not None:
                launch_fields = {"child_spec_digest", "config_digest", "lineage_id",
                    "generation_digest", "pid", "launched_at", "launch_provenance_digest"}
                body = {key: item for key, item in launch.items()
                    if key != "launch_provenance_digest"} if isinstance(launch, dict) else {}
                if (not isinstance(launch, dict) or set(launch) != launch_fields
                        or launch["child_spec_digest"] != self._spec_digest
                        or launch["config_digest"] != self.config["config_digest"]
                        or not isinstance(launch["lineage_id"], str) or not launch["lineage_id"]
                        or not isinstance(launch["generation_digest"], str) or not launch["generation_digest"]
                        or type(launch["pid"]) is not int or launch["pid"] < 1
                        or type(launch["launched_at"]) not in (int, float)
                        or not math.isfinite(launch["launched_at"])
                        or launch["launch_provenance_digest"] != _digest(body)):
                    raise ValueError("parent_launch_provenance_invalid")
            generation_digest = value["generation_digest"]
            if generation_digest is not None and not isinstance(generation_digest, str):
                raise ValueError("parent_generation_identity_invalid")
            if launch is not None and launch["generation_digest"] != generation_digest:
                raise ValueError("parent_launch_generation_mismatch")
            self._sequence = sequence
            self._restart_history = [float(item) for item in history]
            self._panic = value["panic_latched"]; self._shutdown = value["shutdown_latched"]
            self._exhausted = value["restart_budget_exhausted"]
            self._status = value["status"]; self._generation_digest = generation_digest
            self._launch = dict(launch) if launch is not None else None
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError,
                RecursionError, OverflowError):
            self._state_recovery_valid = False
            self._panic = True; self._status = "fail_closed_state"; self._launch = None

    def _receipt(self, event: str, detail: Mapping[str, Any] | None = None) -> None:
        if not self._state_recovery_valid:
            raise RuntimeError("parent_state_recovery_not_trusted")
        if self._sequence >= MAX_PARENT_SEQUENCE or self._receipt_count >= MAX_PARENT_RECEIPT_ROWS:
            self._panic = True; self._status = "receipt_sequence_exhausted"
            raise RuntimeError("parent_receipt_sequence_limit_exceeded")
        row = {"schema_version": RECEIPT_SCHEMA, "sequence": self._sequence + 1,
            "timestamp": datetime.fromtimestamp(self._clock(), timezone.utc).isoformat(),
            "event": event, "child_spec_digest": self._spec_digest, "detail": dict(detail or {})}
        row["receipt_digest"] = _digest(row)
        encoded = _canonical(row) + b"\n"
        if (len(encoded) > MAX_PARENT_RECEIPT_LINE_BYTES
                or self._receipt_bytes + len(encoded) > MAX_PARENT_RECEIPT_BYTES):
            self._panic = True; self._status = "receipt_retention_limit_exceeded"
            raise RuntimeError("parent_receipt_journal_retention_limit_exceeded")
        try:
            if os.name == "posix":
                flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(self._receipt_path, flags, 0o600)
                try:
                    metadata = os.fstat(descriptor)
                    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                            or metadata.st_uid != os.geteuid()
                            or metadata.st_size != self._receipt_bytes):
                        raise ValueError("parent_receipt_journal_changed")
                    if stat.S_IMODE(metadata.st_mode) & 0o077:
                        os.fchmod(descriptor, 0o600)
                    remaining = memoryview(encoded)
                    while remaining:
                        written = os.write(descriptor, remaining)
                        if written <= 0:
                            raise OSError("parent_receipt_write_incomplete")
                        remaining = remaining[written:]
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            else:
                with self._receipt_path.open("ab") as stream:
                    stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
        except Exception:
            self._state_recovery_valid = False
            self._panic = True; self._status = "receipt_publication_failed"
            raise
        self._sequence += 1
        self._receipt_count += 1
        self._receipt_bytes += len(encoded)
        self._receipt_head_digest = row["receipt_digest"]
        self._persist()

    @staticmethod
    def _open_private_provenance_directory(path: Path) -> int:
        """Open one configured provenance directory without following path links."""
        if os.name != "posix":
            raise OSError("resident_provenance_directory_platform_unsupported")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        if not getattr(os, "O_NOFOLLOW", 0) or not getattr(os, "O_DIRECTORY", 0):
            raise OSError("resident_provenance_directory_custody_unsupported")
        absolute = Path(os.path.abspath(path))
        descriptor = os.open(os.sep, flags)
        try:
            for component in absolute.parts[1:]:
                if component in {"", ".", ".."}:
                    raise OSError("resident_provenance_path_invalid")
                child = os.open(component, flags, dir_fd=descriptor)
                metadata = os.fstat(child)
                if not stat.S_ISDIR(metadata.st_mode):
                    os.close(child)
                    raise OSError("resident_provenance_component_not_directory")
                os.close(descriptor)
                descriptor = child
            metadata = os.fstat(descriptor)
            if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid()
                    or stat.S_IMODE(metadata.st_mode) & 0o077):
                raise OSError("resident_provenance_directory_not_private")
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    def _read_generation_provenance(self, ordinal: int) -> list[dict[str, Any]]:
        """Read only bounded, owner-private records in the exact configured generation."""
        directory_path = Path(self.config["provenance_root"]) / f"generation-{ordinal}"
        directory_fd = self._open_private_provenance_directory(directory_path)
        records: list[dict[str, Any]] = []
        total_bytes = 0
        try:
            with os.scandir(directory_fd) as entries:
                names: list[str] = []
                for entry in entries:
                    if len(names) >= MAX_PARENT_PROVENANCE_FILES:
                        raise ValueError("resident_provenance_file_bound_exceeded")
                    names.append(entry.name)
            for name in sorted(names):
                if not _PARENT_PROVENANCE_NAME.fullmatch(name):
                    raise ValueError("resident_provenance_filename_invalid")
                observed = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if (not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1
                        or observed.st_uid != os.geteuid()
                        or stat.S_IMODE(observed.st_mode) & 0o077
                        or observed.st_size > MAX_PARENT_PROVENANCE_RECORD_BYTES):
                    raise ValueError("resident_provenance_file_custody_invalid")
                total_bytes += observed.st_size
                if total_bytes > MAX_PARENT_PROVENANCE_BYTES:
                    raise ValueError("resident_provenance_total_bound_exceeded")
                descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=directory_fd)
                try:
                    before = os.fstat(descriptor)
                    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                            or before.st_uid != os.geteuid()
                            or before.st_dev != observed.st_dev or before.st_ino != observed.st_ino
                            or before.st_size != observed.st_size
                            or stat.S_IMODE(before.st_mode) & 0o077):
                        raise ValueError("resident_provenance_file_changed")
                    chunks: list[bytes] = []
                    remaining = MAX_PARENT_PROVENANCE_RECORD_BYTES + 1
                    while remaining:
                        chunk = os.read(descriptor, min(65_536, remaining))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    raw = b"".join(chunks)
                    after = os.fstat(descriptor)
                    if (len(raw) > MAX_PARENT_PROVENANCE_RECORD_BYTES
                            or len(raw) != before.st_size or after.st_size != before.st_size
                            or after.st_dev != before.st_dev or after.st_ino != before.st_ino
                            or after.st_mtime_ns != before.st_mtime_ns
                            or after.st_ctime_ns != before.st_ctime_ns):
                        raise ValueError("resident_provenance_file_changed")
                finally:
                    os.close(descriptor)
                value = json.loads(raw.decode("utf-8"))
                process_instance_id = value.get("process_instance_id") if isinstance(value, dict) else None
                if (not isinstance(process_instance_id, str)
                        or not re.fullmatch(r"sha256:[0-9a-f]{64}", process_instance_id)
                        or name != process_instance_id.removeprefix("sha256:") + ".json"
                        or resident.canonical_bytes(value) + b"\n" != raw):
                    raise ValueError("resident_provenance_record_noncanonical")
                records.append(value)
            return records
        finally:
            os.close(directory_fd)

    def _verify_launch_readiness(self, launch: Mapping[str, Any]) -> bool:
        """Verify the child's own bounded, digest-bound startup provenance.

        The process adapter separately proves that its exact child PID is alive.
        This check proves that the configured resident owner captured that same
        child under the reconstructed generation and a clean repository state.
        It does not claim general system or cognitive readiness.
        """
        self._verified_child_provenance = None
        try:
            launch_fields = {"child_spec_digest", "config_digest", "lineage_id",
                "generation_digest", "pid", "launched_at", "launch_provenance_digest"}
            if not isinstance(launch, Mapping) or set(launch) != launch_fields:
                return False
            launch_body = {key: item for key, item in launch.items()
                if key != "launch_provenance_digest"}
            if (launch.get("child_spec_digest") != self._spec_digest
                    or launch.get("config_digest") != self.config["config_digest"]
                    or launch.get("launch_provenance_digest") != _digest(launch_body)
                    or type(launch.get("pid")) is not int or launch["pid"] < 1
                    or type(launch.get("launched_at")) not in (int, float)
                    or not math.isfinite(launch["launched_at"])):
                return False
            custody = resident.inspect_transition_custody(self.config)
            if custody.get("status") not in {
                    "no_resident_transactions", "complete_resident_transactions_only"}:
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
                "pid": identity["pid"], "launched_at": self._clock()}
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
            try:
                present = self._process_presence_observer(prior_pid)
            except Exception:
                present = None
            if present is not False:
                self._status = "prior_child_unreconciled"
                self._receipt("prior_child_reconciliation_blocked", {
                    "pid": prior_pid, "presence": "present" if present is True else "unknown",
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
            "readiness_basis": self._readiness_basis}


__all__ = ["MaintenanceResidentParentSupervisor", "STATE_SCHEMA", "RECEIPT_SCHEMA", "SERVICE_ID"]
