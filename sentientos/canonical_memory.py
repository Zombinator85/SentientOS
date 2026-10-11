"""Side-effect-free canonical live-memory storage and explicit retention authority."""
from __future__ import annotations
import hashlib, json, os, re, stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Mapping
from .windows_handle_custody import (
    WindowsHandleCustodyError, read_explicit_file, read_regular_files,
)
CANDIDATE_TYPE = "explicit_conversation_user_retention"
MAX_RETENTION_RECORD_BYTES = 256 * 1024
MAX_MEMORY_SCAN_ENTRIES = 4096
MAX_MEMORY_RECORDS = 1024
MAX_MEMORY_TOTAL_BYTES = 16 * 1024 * 1024
_PROCESS_MEMORY_ROOT_IDENTITIES: dict[str, tuple[int, int]] = {}
_PROCESS_MEMORY_ROOT_IDENTITIES_LOCK = RLock()
_PROCESS_MEMORY_ROOT_IDENTITY_LIMIT = 32
def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def retention_request_id(operation_id: str) -> str:
    """Return the retry-stable id for one already-authorized turn operation."""
    if not isinstance(operation_id, str) or not operation_id or len(operation_id) > 4096:
        raise ValueError("retention_operation_identity_invalid")
    return "retain-request-" + hashlib.sha256(
        operation_id.encode("utf-8")).hexdigest()[:24]
# Freeze shared root configuration at first import.  The legacy manager keeps
# module-level path constants, so re-reading environment variables for chat would
# otherwise let the two owners silently diverge after startup.
_PROCESS_DATA_ROOT = Path(os.getenv("SENTIENTOS_DATA_DIR") or os.getenv("SENTIENTOS_DATA_ROOT")
    or (Path.cwd() / "sentientos_data")).expanduser().resolve()
_PROCESS_MEMORY_DIR = os.getenv("MEMORY_DIR")
_PROCESS_MEMORY_ROOT = (
    Path(_PROCESS_MEMORY_DIR).expanduser().resolve() if _PROCESS_MEMORY_DIR else None
)
_PROCESS_DEFAULT_MEMORY_ROOT = (_PROCESS_DATA_ROOT / "memory").resolve()


def sentientos_data_dir() -> Path:
    """Return this process's immutable data-root configuration."""
    return _PROCESS_DATA_ROOT


def sentientos_memory_dir(data_root: Path | None = None) -> Path:
    """Return this process's fixed user-memory root configuration."""
    if _PROCESS_MEMORY_ROOT is not None:
        return _PROCESS_MEMORY_ROOT
    if data_root is None or data_root == _PROCESS_DATA_ROOT:
        return _PROCESS_DEFAULT_MEMORY_ROOT
    return (data_root / "memory").expanduser().resolve()
@dataclass(frozen=True)
class RetentionAdmission:
    decision: str; candidate_digest: str; request_id: str; receipt_digest: str; reason: str|None=None
class ExplicitRetentionAdmissionGate:
    """Independent, default-deny authority for an exact structured user request."""
    def decide(self, candidate: Mapping[str, Any]) -> RetentionAdmission:
        required=("session_id","source_turn_id","source_text_digest","request_id","operation_id")
        valid=(candidate.get("candidate_type")==CANDIDATE_TYPE and candidate.get("explicitly_requested") is True
               and candidate.get("source_role")=="user" and all(candidate.get(k) for k in required))
        cd=digest(candidate); decision="retention_admitted" if valid else "retention_denied"
        body={"decision":decision,"candidate_digest":cd,"request_id":str(candidate.get("request_id") or ""),"authority":"explicit_retention_admission_gate"}
        return RetentionAdmission(decision,cd,body["request_id"],digest(body),None if valid else "invalid_explicit_user_candidate")
class CanonicalMemoryStore:
    """Canonical raw-fragment domain compatible with memory_manager.RAW_PATH."""
    def __init__(self,memory_root:Path)->None:
        # Preserve the already-fixed path spelling. Resolution here could follow a
        # substituted symlink after process-start configuration was frozen; the
        # descriptor-relative root opener rejects such components instead.
        self.root = Path(os.path.abspath(Path(memory_root).expanduser()))
        self.raw = self.root / "raw"

    def _legacy_sidecar_posture(self) -> str:
        """Report bounded path metadata only; the legacy sidecar is never ingested here."""
        path = self.root / "conversation_memories.json"
        try:
            metadata = os.lstat(path)
        except FileNotFoundError:
            return "missing"
        except OSError:
            return "custody_unavailable"
        if not stat.S_ISREG(metadata.st_mode):
            return "not_regular_file"
        if metadata.st_nlink != 1:
            return "link_count_invalid"
        if os.name == "posix" and metadata.st_uid != os.geteuid():
            return "owner_mismatch"
        if metadata.st_size > MAX_RETENTION_RECORD_BYTES:
            return "size_exceeded"
        return "present_unverified"
    @staticmethod
    def _read_at(directory_fd: int, name: str, *, max_bytes: int) -> bytes:
        descriptor: int | None = None
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW
                | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
            before = os.fstat(descriptor)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.geteuid()
                    or stat.S_IMODE(before.st_mode) & 0o022
                    or before.st_size > max_bytes):
                raise WindowsHandleCustodyError("memory_record_custody_invalid")
            chunks: list[bytes] = []
            remaining = max_bytes + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(descriptor)
            if (len(raw) > max_bytes or len(raw) != before.st_size
                    or after.st_size != before.st_size
                    or after.st_mtime_ns != before.st_mtime_ns
                    or after.st_ctime_ns != before.st_ctime_ns
                    or after.st_dev != before.st_dev or after.st_ino != before.st_ino):
                raise WindowsHandleCustodyError("memory_record_changed_during_read")
            return raw
        except WindowsHandleCustodyError:
            raise
        except OSError as exc:
            raise WindowsHandleCustodyError("memory_record_custody_unavailable") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _records(self) -> tuple[list[dict[str, Any]], str]:
        if os.name == "nt":
            try:
                from .windows_handle_custody import verify_explicit_directory
                verify_explicit_directory(self.root, require_private_acl=True)
                entries = read_regular_files(self.raw, max_entries=MAX_MEMORY_RECORDS,
                    max_file_bytes=MAX_RETENTION_RECORD_BYTES,
                    max_total_bytes=MAX_MEMORY_TOTAL_BYTES, suffix=".json",
                    require_private_acl=True)
            except WindowsHandleCustodyError as exc:
                posture = ("directory_missing" if "missing" in str(exc)
                    else "custody_or_bound_unavailable")
                return [], posture
            raw_entries = entries
        else:
            directory_fd: int | None = None
            try:
                if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")
                        or os.open not in os.supports_dir_fd
                        or os.scandir not in os.supports_fd):
                    return [], "safe_directory_read_unsupported"
                directory_fd = self.open_raw_directory()
                metadata = os.fstat(directory_fd)
                if (not stat.S_ISDIR(metadata.st_mode)
                        or metadata.st_uid != os.geteuid()
                        or stat.S_IMODE(metadata.st_mode) & 0o077):
                    return [], "directory_custody_invalid"
                names: list[str] = []
                with os.scandir(directory_fd) as entries:
                    for index, entry in enumerate(entries):
                        if index >= MAX_MEMORY_SCAN_ENTRIES:
                            return [], "directory_entry_bound_exceeded"
                        if entry.name.endswith(".json"):
                            names.append(entry.name)
                            if len(names) > MAX_MEMORY_RECORDS:
                                return [], "memory_record_bound_exceeded"
                raw_entries = []
                total = 0
                for name in sorted(names):
                    raw = self._read_at(directory_fd, name,
                        max_bytes=MAX_RETENTION_RECORD_BYTES)
                    total += len(raw)
                    if total > MAX_MEMORY_TOTAL_BYTES:
                        return [], "memory_total_byte_bound_exceeded"
                    raw_entries.append((name, raw))
            except FileNotFoundError:
                return [], "directory_missing"
            except (OSError, WindowsHandleCustodyError):
                return [], "custody_unavailable"
            finally:
                if directory_fd is not None:
                    os.close(directory_fd)
        out: list[dict[str, Any]] = []
        posture = "complete"
        total = 0
        for name, raw in raw_entries:
            total += len(raw)
            if total > MAX_MEMORY_TOTAL_BYTES:
                return [], "memory_total_byte_bound_exceeded"
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                posture = "partial_malformed_records"
                continue
            if isinstance(value, dict) and isinstance(value.get("text"), str):
                record_id = value.get("id")
                if (not isinstance(record_id, str) or not record_id
                        or name != record_id + ".json"):
                    posture = "partial_record_filename_identity_mismatch"
                    continue
                stored_text_digest = value.get("text_digest")
                if (stored_text_digest is not None
                        and (not isinstance(stored_text_digest, str)
                            or stored_text_digest != digest({"text": value["text"]}))):
                    posture = "partial_text_digest_mismatch"
                    continue
                out.append(value)
            else:
                posture = "partial_invalid_records"
        unique: list[dict[str, Any]] = []
        first_identity: dict[str, str] = {}
        conflicting_ids: set[str] = set()
        duplicate_seen = False
        for record in out:
            record_id = record.get("id")
            if not isinstance(record_id, str) or not record_id:
                unique.append(record)
                continue
            record_identity = digest(record)
            previous = first_identity.get(record_id)
            if previous is None:
                first_identity[record_id] = record_identity
                unique.append(record)
            else:
                duplicate_seen = True
                if previous != record_identity:
                    conflicting_ids.add(record_id)
        if conflicting_ids:
            unique = [record for record in unique
                if record.get("id") not in conflicting_ids]
            posture = "partial_duplicate_identity_conflict"
        elif duplicate_seen and posture == "complete":
            posture = "partial_duplicate_records"
        return unique, posture

    def retrieve(self,query:str,*,limit:int=4,budget_chars:int=2000)->dict[str,Any]:
        records, retrieval_posture = self._records()
        legacy_sidecar_posture = self._legacy_sidecar_posture()
        legacy_sidecar_present = legacy_sidecar_posture == "present_unverified"
        terms=set(re.findall(r"[a-z0-9]+",query.lower())); ranked=[]
        for record in records:
            score=len(terms & set(re.findall(r"[a-z0-9]+",record["text"].lower())))
            if score: ranked.append((score,str(record.get("id","")),record))
        selected: list[dict[str, Any]]=[]; used=0; omitted=[]
        for _,_,record in sorted(ranked,key=lambda x:(-x[0],x[1])):
            identity=(record.get("id"),record.get("text_digest") or digest({"text":record["text"]}))
            if len(selected)>=max(0,limit):
                omitted.append((identity,"selection_limit"))
                continue
            if used+len(record["text"])<=budget_chars:
                selected.append(record); used+=len(record["text"])
            else:
                omitted.append((identity,"character_budget"))
        identities=[(r.get("id"),r.get("text_digest") or digest({"text":r["text"]})) for r in selected]
        selection_posture = "matching_records_omitted" if omitted else "all_matching_records_selected"
        return {"memories":selected,"selected_memory_ids":[x[0] for x in identities],"read_only":True,
                "legacy_sidecar_present":legacy_sidecar_present,
                "legacy_sidecar_posture":legacy_sidecar_posture,
                "retrieval_posture":retrieval_posture,
                "selection_posture":selection_posture,
                "omitted_memory_count":len(omitted),
                "snapshot_digest":digest({"query_digest":digest({"query":query}),"selected":identities,
                    "omitted":omitted,"selection_posture":selection_posture,
                    "limit":limit,"budget_chars":budget_chars,"retrieval_posture":retrieval_posture,
                    "legacy_sidecar_posture":legacy_sidecar_posture})}
    def open_memory_root(self, *, prepare_for_write: bool = False) -> int:
        """Open and verify the shared user-memory root without following links."""
        if os.name != "posix":
            raise PermissionError("canonical_memory_atomic_publication_unsupported_platform")
        nofollow = getattr(os, "O_NOFOLLOW", None)
        directory = getattr(os, "O_DIRECTORY", None)
        if (nofollow is None or directory is None or os.open not in os.supports_dir_fd
                or (prepare_for_write and os.mkdir not in os.supports_dir_fd)):
            raise PermissionError("canonical_memory_safe_publication_unavailable")
        absolute = Path(os.path.abspath(self.root))
        descriptor = os.open(os.sep, os.O_RDONLY | directory)
        try:
            for component in absolute.parts[1:]:
                if component in {"", ".", ".."}:
                    raise PermissionError("canonical_memory_path_component_invalid")
                try:
                    child = os.open(component, os.O_RDONLY | directory | nofollow,
                        dir_fd=descriptor)
                except FileNotFoundError:
                    if not prepare_for_write:
                        raise
                    try:
                        os.mkdir(component, mode=0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                    else:
                        os.fsync(descriptor)
                    child = os.open(component, os.O_RDONLY | directory | nofollow,
                        dir_fd=descriptor)
                metadata = os.fstat(child)
                if not stat.S_ISDIR(metadata.st_mode):
                    os.close(child)
                    raise PermissionError("canonical_memory_root_not_directory")
                os.close(descriptor)
                descriptor = child
            metadata = os.fstat(descriptor)
            if (not stat.S_ISDIR(metadata.st_mode)
                    or metadata.st_uid != os.geteuid()):
                raise PermissionError("canonical_memory_root_owner_invalid")
            if stat.S_IMODE(metadata.st_mode) & 0o077:
                if not prepare_for_write:
                    raise PermissionError("canonical_memory_root_permissions_invalid")
                os.fchmod(descriptor, 0o700)
                metadata = os.fstat(descriptor)
                if stat.S_IMODE(metadata.st_mode) & 0o077:
                    raise PermissionError("canonical_memory_root_permissions_invalid")
            identity = (metadata.st_dev, metadata.st_ino)
            root_key = str(absolute)
            with _PROCESS_MEMORY_ROOT_IDENTITIES_LOCK:
                expected_identity = _PROCESS_MEMORY_ROOT_IDENTITIES.get(root_key)
                if expected_identity is None:
                    if len(_PROCESS_MEMORY_ROOT_IDENTITIES) >= _PROCESS_MEMORY_ROOT_IDENTITY_LIMIT:
                        raise PermissionError("canonical_memory_root_identity_bound_exceeded")
                    _PROCESS_MEMORY_ROOT_IDENTITIES[root_key] = identity
                elif expected_identity != identity:
                    raise PermissionError("canonical_memory_root_identity_changed")
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    def open_raw_directory(self, *, prepare_for_write: bool = False) -> int:
        """Open the raw subtree relative to a verified private memory root."""
        if os.name != "posix":
            raise PermissionError("canonical_memory_atomic_publication_unsupported_platform")
        nofollow = getattr(os, "O_NOFOLLOW", None)
        directory = getattr(os, "O_DIRECTORY", None)
        if (nofollow is None or directory is None
                or os.open not in os.supports_dir_fd
                or os.link not in os.supports_dir_fd
                or os.unlink not in os.supports_dir_fd):
            raise PermissionError("canonical_memory_safe_publication_unavailable")
        root_fd = self.open_memory_root(prepare_for_write=prepare_for_write)
        try:
            if prepare_for_write:
                try:
                    os.mkdir("raw", mode=0o700, dir_fd=root_fd)
                except FileExistsError:
                    pass
                else:
                    os.fsync(root_fd)
            descriptor = os.open("raw", os.O_RDONLY | directory | nofollow,
                dir_fd=root_fd)
            try:
                metadata = os.fstat(descriptor)
                if (not stat.S_ISDIR(metadata.st_mode)
                        or metadata.st_uid != os.geteuid()):
                    raise PermissionError("canonical_memory_raw_root_owner_invalid")
                if stat.S_IMODE(metadata.st_mode) & 0o077:
                    if not prepare_for_write:
                        raise PermissionError("canonical_memory_raw_root_permissions_invalid")
                    os.fchmod(descriptor, 0o700)
                    metadata = os.fstat(descriptor)
                    if stat.S_IMODE(metadata.st_mode) & 0o077:
                        raise PermissionError("canonical_memory_raw_root_permissions_invalid")
                return descriptor
            except Exception:
                os.close(descriptor)
                raise
        finally:
            os.close(root_fd)
class AdmittedRetentionWriter:
    """Terminal executor validates admission evidence but never decides admission."""
    def __init__(self, store: CanonicalMemoryStore,
                 admission_gate: ExplicitRetentionAdmissionGate | None = None) -> None:
        self.store = store
        self.admission_gate = admission_gate or ExplicitRetentionAdmissionGate()
    def verify_committed_artifact(self, receipt: Mapping[str, Any],
                                  source_turn: Mapping[str, Any],
                                  session_id: str) -> dict[str, Any]:
        """Verify the exact stored fragment without replaying admission or writes.

        The deterministic gate decision is recomputed from the artifact-bound
        candidate. This does not attest that the original gate invocation ran.
        """
        if (not isinstance(session_id, str) or not session_id
                or source_turn.get("role") != "user"
                or not isinstance(source_turn.get("turn_id"), str)
                or not isinstance(source_turn.get("text"), str)
                or not isinstance(source_turn.get("text_digest"), str)
                or digest({"text": source_turn.get("text")}) != source_turn.get("text_digest")):
            return {"artifact_status": "unverified", "reason_code": "source_turn_invalid",
                    "admission_status": "not_independently_recoverable", "write_replayed": False}
        operation = "retain:" + session_id + ":" + source_turn["turn_id"]
        expected_id = "memory-" + hashlib.sha256(operation.encode()).hexdigest()[:24]
        expected_fields = {"status", "memory_id", "source_session_id", "source_turn_id",
            "source_text_digest", "admission_receipt_digest", "execution_operation_id",
            "canonical_stored_record_digest", "target_root_identity", "index_update_result"}
        receipt_digest = receipt.get("admission_receipt_digest")
        if (not isinstance(receipt, Mapping) or set(receipt) != expected_fields
                or receipt.get("status") != "memory_retention_committed"
                or receipt.get("memory_id") != expected_id
                or receipt.get("source_session_id") != session_id
                or receipt.get("source_turn_id") != source_turn["turn_id"]
                or receipt.get("source_text_digest") != source_turn["text_digest"]
                or receipt.get("execution_operation_id") != operation
                or receipt.get("target_root_identity") != digest({"root": str(self.store.root)})
                or receipt.get("index_update_result") != "raw_fragment_available"
                or not isinstance(receipt_digest, str)
                or len(receipt_digest) != 64
                or any(char not in "0123456789abcdef" for char in receipt_digest)):
            return {"artifact_status": "conflict", "reason_code": "stored_receipt_binding_invalid",
                    "admission_status": "not_independently_recoverable", "write_replayed": False}
        stored_digest = receipt.get("canonical_stored_record_digest")
        if (not isinstance(stored_digest, str) or len(stored_digest) != 64
                or any(char not in "0123456789abcdef" for char in stored_digest)):
            return {"artifact_status": "conflict", "reason_code": "stored_record_digest_invalid",
                    "admission_status": "not_independently_recoverable", "write_replayed": False}
        path = self.store.raw / (expected_id + ".json")
        try:
            from .windows_handle_custody import verify_explicit_directory
            verify_explicit_directory(self.store.root, require_private_acl=True)
            verify_explicit_directory(self.store.raw, require_private_acl=True)
            raw = read_explicit_file(path, max_bytes=MAX_RETENTION_RECORD_BYTES,
                require_private_acl=True)
        except WindowsHandleCustodyError as exc:
            reason = ("artifact_missing" if exc.args == ("explicit_file_missing",)
                      else "artifact_custody_unavailable")
            return {"artifact_status": "unavailable", "reason_code": reason,
                    "admission_status": "not_independently_recoverable", "write_replayed": False}
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            return {"artifact_status": "conflict", "reason_code": "artifact_malformed",
                    "admission_status": "not_independently_recoverable", "write_replayed": False}
        fields = {"id", "text", "text_digest", "timestamp", "source", "category",
                  "tags", "importance", "meta"}
        meta = record.get("meta") if isinstance(record, dict) else None
        expected_meta_fields = {"session_id", "turn_id", "request_id", "operation_id",
                                "admission_receipt_digest"}
        timestamp = record.get("timestamp") if isinstance(record, dict) else None
        try:
            instant = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            timestamp_valid = instant.tzinfo is not None and instant.utcoffset() is not None
        except (OverflowError, OSError, TypeError, ValueError):
            timestamp_valid = False
        if (not isinstance(record, dict) or set(record) != fields
                or record.get("id") != expected_id
                or record.get("text") != source_turn["text"]
                or record.get("text_digest") != source_turn["text_digest"]
                or record.get("source") != "conversation_user_turn"
                or record.get("category") != "event"
                or record.get("tags") != ["explicit-retention"]
                or type(record.get("importance")) is not float
                or record.get("importance") != 1.0
                or not isinstance(meta, dict) or set(meta) != expected_meta_fields
                or meta.get("session_id") != session_id
                or meta.get("turn_id") != source_turn["turn_id"]
                or not isinstance(meta.get("request_id"), str)
                or not re.fullmatch(r"retain-request-[0-9a-f]{24}", meta.get("request_id", ""))
                or meta.get("operation_id") != operation
                or meta.get("admission_receipt_digest") != receipt_digest
                or not timestamp_valid or digest(record) != stored_digest):
            return {"artifact_status": "conflict", "reason_code": "stored_artifact_binding_invalid",
                    "admission_status": "not_independently_recoverable", "write_replayed": False}
        if source_turn.get("retention_state") not in {"requested", "retained"}:
            return {"artifact_status": "verified", "memory_id": expected_id,
                    "record_digest": stored_digest,
                    "admission_status": "not_independently_recoverable",
                    "reason_code": "explicit_request_state_not_recoverable",
                    "write_replayed": False}
        candidate = {"candidate_type": CANDIDATE_TYPE, "session_id": session_id,
            "source_turn_id": source_turn["turn_id"], "source_role": "user",
            "source_text_digest": source_turn["text_digest"], "explicitly_requested": True,
            "request_id": meta["request_id"], "operation_id": operation}
        admission = self.admission_gate.decide(candidate)
        if (admission.decision != "retention_admitted"
                or admission.candidate_digest != digest(candidate)
                or admission.receipt_digest != receipt_digest):
            return {"artifact_status": "verified", "memory_id": expected_id,
                    "record_digest": stored_digest, "admission_status": "conflict",
                    "reason_code": "admission_digest_policy_mismatch",
                    "write_replayed": False}
        return {"artifact_status": "verified", "memory_id": expected_id,
                "record_digest": stored_digest,
                "admission_status": "policy_recomputed_not_execution_attested",
                "admission_receipt_digest": receipt_digest,
                "write_replayed": False}

    def recover_existing_artifact(self, source_turn: Mapping[str, Any],
                                  session_id: str) -> dict[str, Any]:
        """Verify a commit or finish linking its exact prior stage.

        Recovery never reconstructs the record payload or replays inference. It
        recomputes the deterministic admission policy only as a binding check.
        """
        if (not isinstance(session_id, str) or not session_id
                or source_turn.get("retention_state") != "requested"
                or source_turn.get("role") != "user"
                or not isinstance(source_turn.get("turn_id"), str)
                or not isinstance(source_turn.get("text"), str)
                or not isinstance(source_turn.get("text_digest"), str)
                or digest({"text": source_turn.get("text")}) != source_turn.get("text_digest")):
            return {"artifact_status": "unverified", "reason_code": "source_turn_invalid",
                    "admission_status": "not_independently_recoverable",
                    "write_replayed": False}
        operation = "retain:" + session_id + ":" + source_turn["turn_id"]
        memory_id = "memory-" + hashlib.sha256(operation.encode()).hexdigest()[:24]
        if os.name == "nt":
            try:
                raw = read_explicit_file(self.store.raw / (memory_id + ".json"),
                    max_bytes=MAX_RETENTION_RECORD_BYTES)
                record = json.loads(raw.decode("utf-8"))
            except WindowsHandleCustodyError as exc:
                reason = ("artifact_missing" if exc.args == ("explicit_file_missing",)
                          else "artifact_custody_unavailable")
                return {"artifact_status": "unavailable", "reason_code": reason,
                        "admission_status": "not_independently_recoverable",
                        "write_replayed": False}
            except (UnicodeError, json.JSONDecodeError):
                return {"artifact_status": "conflict", "reason_code": "artifact_malformed",
                        "admission_status": "not_independently_recoverable",
                        "write_replayed": False}
        else:
            directory_fd: int | None = None
            try:
                directory_fd = self._open_raw_directory()
                record = self._read_raw_record(directory_fd, memory_id + ".json",
                    max_links=2)
                staged_artifact_published = False
                if record is None:
                    temporary_name = ".memory-" + memory_id + ".tmp"
                    staged = self._read_raw_record(directory_fd, temporary_name)
                    if staged is None:
                        return {"artifact_status": "unavailable",
                                "reason_code": "artifact_missing",
                                "admission_status": "not_independently_recoverable",
                                "write_replayed": False}
                    staged_meta = staged.get("meta")
                    staged_request_id = (
                        staged_meta.get("request_id")
                        if isinstance(staged_meta, Mapping) else None
                    )
                    if (not isinstance(staged_request_id, str)
                            or not re.fullmatch(
                                r"retain-request-[0-9a-f]{24}", staged_request_id)):
                        return {"artifact_status": "conflict",
                                "reason_code": "staged_request_identity_invalid",
                                "admission_status": "not_independently_recoverable",
                                "write_replayed": False}
                    candidate = {
                        "candidate_type": CANDIDATE_TYPE,
                        "session_id": session_id,
                        "source_turn_id": source_turn["turn_id"],
                        "source_role": "user",
                        "source_text_digest": source_turn["text_digest"],
                        "explicitly_requested": True,
                        "request_id": staged_request_id,
                        "operation_id": operation,
                    }
                    admission = self.admission_gate.decide(candidate)
                    expected_record = {
                        "id": memory_id, "text": source_turn["text"],
                        "text_digest": source_turn["text_digest"],
                        "timestamp": staged.get("timestamp"),
                        "source": "conversation_user_turn", "category": "event",
                        "tags": ["explicit-retention"], "importance": 1.0,
                        "meta": {"session_id": session_id,
                            "turn_id": source_turn["turn_id"],
                            "request_id": candidate["request_id"],
                            "operation_id": operation,
                            "admission_receipt_digest": admission.receipt_digest},
                    }
                    if (admission.decision != "retention_admitted"
                            or not self._same_operation_record(staged, expected_record)):
                        return {"artifact_status": "conflict",
                                "reason_code": "staged_artifact_binding_invalid",
                                "admission_status": "not_independently_recoverable",
                                "write_replayed": False}
                    try:
                        os.link(temporary_name, memory_id + ".json",
                            src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                            follow_symlinks=False)
                    except FileExistsError:
                        return {"artifact_status": "conflict",
                                "reason_code": "artifact_appeared_during_recovery",
                                "admission_status": "not_independently_recoverable",
                                "write_replayed": False}
                    os.fsync(directory_fd)
                    record = self._read_raw_record(directory_fd,
                        memory_id + ".json", max_links=2)
                    if (record is None
                            or not self._same_operation_record(record, expected_record)):
                        return {"artifact_status": "conflict",
                                "reason_code": "staged_artifact_publication_mismatch",
                                "admission_status": "not_independently_recoverable",
                                "write_replayed": False}
                    staged_artifact_published = True
                metadata = os.stat(memory_id + ".json", dir_fd=directory_fd,
                    follow_symlinks=False)
                if metadata.st_nlink == 2:
                    matching_temporaries: list[str] = []
                    with os.scandir(directory_fd) as entries:
                        for index, entry in enumerate(entries):
                            if index >= MAX_MEMORY_SCAN_ENTRIES:
                                return {"artifact_status": "conflict",
                                    "reason_code": "artifact_recovery_scan_bound_exceeded",
                                    "admission_status": "not_independently_recoverable",
                                    "write_replayed": False}
                            if (entry.name.startswith(".memory-")
                                    and entry.name.endswith(".tmp")):
                                item = entry.stat(follow_symlinks=False)
                                if (item.st_dev == metadata.st_dev
                                        and item.st_ino == metadata.st_ino):
                                    matching_temporaries.append(entry.name)
                    if len(matching_temporaries) != 1:
                        return {"artifact_status": "conflict",
                            "reason_code": "artifact_linked_temporary_unresolved",
                            "admission_status": "not_independently_recoverable",
                            "write_replayed": False}
                    temporary = self._read_raw_record(directory_fd,
                        matching_temporaries[0], max_links=2)
                    if temporary != record:
                        return {"artifact_status": "conflict",
                            "reason_code": "artifact_temporary_content_mismatch",
                            "admission_status": "not_independently_recoverable",
                            "write_replayed": False}
                    os.unlink(matching_temporaries[0], dir_fd=directory_fd)
                    os.fsync(directory_fd)
                    record = self._read_raw_record(directory_fd, memory_id + ".json")
                    if record is None:
                        return {"artifact_status": "unavailable",
                            "reason_code": "artifact_missing_after_reconciliation",
                            "admission_status": "not_independently_recoverable",
                            "write_replayed": False}
                elif metadata.st_nlink != 1:
                    return {"artifact_status": "conflict",
                        "reason_code": "artifact_link_count_invalid",
                        "admission_status": "not_independently_recoverable",
                        "write_replayed": False}
                raw = (json.dumps(record, sort_keys=True, ensure_ascii=False)
                    + "\n").encode("utf-8")
            except FileNotFoundError:
                return {"artifact_status": "unavailable", "reason_code": "artifact_missing",
                        "admission_status": "not_independently_recoverable",
                        "write_replayed": False}
            except (OSError, PermissionError, WindowsHandleCustodyError):
                return {"artifact_status": "unavailable",
                    "reason_code": "artifact_custody_unavailable",
                    "admission_status": "not_independently_recoverable",
                    "write_replayed": False}
            finally:
                if directory_fd is not None:
                    os.close(directory_fd)
        if (not isinstance(record, dict)
                or raw != (json.dumps(record, sort_keys=True, ensure_ascii=False)
                    + "\n").encode("utf-8")
                or not isinstance(record.get("meta"), Mapping)):
            return {"artifact_status": "conflict", "reason_code": "artifact_noncanonical",
                    "admission_status": "not_independently_recoverable",
                    "write_replayed": False}
        receipt = {
            "status": "memory_retention_committed", "memory_id": memory_id,
            "source_session_id": session_id, "source_turn_id": source_turn["turn_id"],
            "source_text_digest": source_turn["text_digest"],
            "admission_receipt_digest": record["meta"].get("admission_receipt_digest"),
            "execution_operation_id": operation,
            "canonical_stored_record_digest": digest(record),
            "target_root_identity": digest({"root": str(self.store.root)}),
            "index_update_result": "raw_fragment_available",
        }
        verification = self.verify_committed_artifact(receipt, source_turn, session_id)
        if (verification.get("artifact_status") == "verified"
                and verification.get("admission_status")
                    == "policy_recomputed_not_execution_attested"):
            return {**verification, "receipt": receipt,
                    "staged_artifact_published": locals().get(
                        "staged_artifact_published", False)}
        return verification

    def _open_raw_directory(self, *, prepare_for_write: bool = False) -> int:
        return self.store.open_raw_directory(prepare_for_write=prepare_for_write)

    def _read_raw_record(self, directory_fd: int, name: str, *,
                         max_links: int = 1) -> dict[str, Any] | None:
        descriptor: int | None = None
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW
                | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise PermissionError("canonical_memory_existing_artifact_unavailable") from exc
        try:
            before = os.fstat(descriptor)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink < 1
                    or before.st_nlink > max_links
                    or before.st_uid != os.geteuid()
                    or stat.S_IMODE(before.st_mode) & 0o077
                    or before.st_size > MAX_RETENTION_RECORD_BYTES):
                raise PermissionError("canonical_memory_existing_artifact_custody_invalid")
            chunks: list[bytes] = []
            remaining = MAX_RETENTION_RECORD_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(descriptor)
            if (len(raw) > MAX_RETENTION_RECORD_BYTES or len(raw) != before.st_size
                    or after.st_size != before.st_size
                    or after.st_nlink != before.st_nlink
                    or after.st_mtime_ns != before.st_mtime_ns
                    or after.st_ctime_ns != before.st_ctime_ns
                    or after.st_dev != before.st_dev or after.st_ino != before.st_ino):
                raise PermissionError("canonical_memory_existing_artifact_changed")
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise PermissionError("canonical_memory_existing_artifact_malformed") from exc
            if (not isinstance(value, dict)
                    or raw != (json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")):
                raise PermissionError("canonical_memory_existing_artifact_noncanonical")
            return value
        finally:
            os.close(descriptor)

    @staticmethod
    def _same_operation_record(existing: Mapping[str, Any],
                               proposed: Mapping[str, Any]) -> bool:
        fields = {"id", "text", "text_digest", "timestamp", "source", "category",
                  "tags", "importance", "meta"}
        if set(existing) != fields or any(existing.get(key) != proposed.get(key)
                for key in fields - {"timestamp"}):
            return False
        try:
            timestamp = datetime.fromisoformat(
                str(existing.get("timestamp", "")).replace("Z", "+00:00"))
        except (OSError, OverflowError, TypeError, ValueError):
            return False
        return timestamp.tzinfo is not None and timestamp.utcoffset() is not None

    def execute(self, candidate: Mapping[str, Any], admission: RetentionAdmission,
                source_turn: Mapping[str, Any]) -> dict[str, Any]:
        expected_candidate_fields = {"candidate_type", "session_id", "source_turn_id",
            "source_role", "source_text_digest", "explicitly_requested", "request_id",
            "operation_id"}
        if (not isinstance(candidate, Mapping) or set(candidate) != expected_candidate_fields
                or candidate.get("candidate_type") != CANDIDATE_TYPE
                or candidate.get("source_role") != "user"
                or candidate.get("explicitly_requested") is not True
                or not isinstance(candidate.get("session_id"), str)
                or not candidate.get("session_id")
                or candidate.get("source_turn_id") != source_turn.get("turn_id")
                or candidate.get("source_text_digest") != source_turn.get("text_digest")
                or not isinstance(candidate.get("request_id"), str)
                or not re.fullmatch(r"retain-request-[0-9a-f]{24}",
                    candidate.get("request_id", ""))):
            raise PermissionError("invalid_retention_candidate")
        operation = "retain:" + candidate["session_id"] + ":" + candidate["source_turn_id"]
        if candidate.get("operation_id") != operation:
            raise PermissionError("retention_operation_binding_invalid")
        if (source_turn.get("role") != "user"
                or not isinstance(source_turn.get("text"), str)
                or not isinstance(source_turn.get("text_digest"), str)
                or digest({"text": source_turn.get("text")})
                    != source_turn.get("text_digest")):
            raise PermissionError("source_text_mismatch")
        expected_admission = self.admission_gate.decide(candidate)
        if admission != expected_admission or admission.decision != "retention_admitted":
            raise PermissionError("valid_admission_evidence_required")
        memory_id = "memory-" + hashlib.sha256(operation.encode()).hexdigest()[:24]
        record = {
            "id": memory_id, "text": source_turn["text"],
            "text_digest": source_turn["text_digest"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "conversation_user_turn", "category": "event",
            "tags": ["explicit-retention"], "importance": 1.0,
            "meta": {"session_id": candidate["session_id"],
                "turn_id": candidate["source_turn_id"],
                "request_id": candidate["request_id"], "operation_id": operation,
                "admission_receipt_digest": admission.receipt_digest},
        }
        encoded = (json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        directory_fd = self._open_raw_directory(prepare_for_write=True)
        temporary_name = ".memory-" + memory_id + ".tmp"
        temporary_fd: int | None = None
        temporary_created = False
        try:
            existing = self._read_raw_record(directory_fd, memory_id + ".json")
            if existing is not None:
                if not self._same_operation_record(existing, record):
                    raise PermissionError("operation_replay_mismatch")
                record = existing
            else:
                flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                    | getattr(os, "O_CLOEXEC", 0))
                temporary_fd = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
                temporary_created = True
                view = memoryview(encoded)
                while view:
                    written = os.write(temporary_fd, view)
                    if written <= 0:
                        raise OSError("short_canonical_memory_artifact_write")
                    view = view[written:]
                os.fsync(temporary_fd)
                try:
                    os.link(temporary_name, memory_id + ".json",
                        src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                        follow_symlinks=False)
                except FileExistsError:
                    existing = self._read_raw_record(directory_fd, memory_id + ".json")
                    if (existing is None
                            or not self._same_operation_record(existing, record)):
                        raise PermissionError("operation_replay_mismatch")
                    record = existing
                else:
                    os.fsync(directory_fd)
        finally:
            if temporary_fd is not None:
                os.close(temporary_fd)
            try:
                if temporary_created:
                    os.unlink(temporary_name, dir_fd=directory_fd)
                    os.fsync(directory_fd)
            except FileNotFoundError:
                pass
            finally:
                os.close(directory_fd)
        receipt = {
            "status": "memory_retention_committed", "memory_id": memory_id,
            "source_session_id": candidate["session_id"],
            "source_turn_id": candidate["source_turn_id"],
            "source_text_digest": candidate["source_text_digest"],
            "admission_receipt_digest": admission.receipt_digest,
            "execution_operation_id": operation,
            "canonical_stored_record_digest": digest(record),
            "target_root_identity": digest({"root": str(self.store.root)}),
            "index_update_result": "raw_fragment_available",
        }
        verification = self.verify_committed_artifact(receipt, source_turn,
            candidate["session_id"])
        if verification.get("artifact_status") != "verified":
            raise PermissionError("canonical_memory_artifact_reconciliation_failed")
        return receipt






