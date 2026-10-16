"""Durable, non-effectful lifecycle custody for bounded admission evidence."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from sentientos.codex_task_authority_admission import TaskAuthorityDefinition, authority_definition_digest
from sentientos.windows_handle_custody import WindowsHandleCustodyError, read_explicit_file
from sentientos.private_file_custody import (
    PrivateFileCustodyError, open_private_directory, read_private_file_at, replace_private_bytes,
)
from sentientos.platform_fcntl import fcntl, require_flock

SCHEMA = "sentientos.runtime_admission_ledger:v1"
ISSUER_ID = "sentientos.control_plane.runtime_admission_authority:v1"
MAX_LEDGER_BYTES = 4_194_304
MAX_ADMISSIONS = 8_192
MAX_REVOCATIONS = 8_192


class AdmissionError(ValueError): pass


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class AdmissionEvidence:
    admission_id: str; capability_id: str; authority_definition_digest: str
    authority_definition_version: int; subsystem_kind: str; principal_id: str
    principal_kind: str; effects: tuple[str, ...]; subject_id: str
    request_configuration_digest: str; issuer_id: str; provenance: str
    issued_sequence: int; valid_through_sequence: int; status: str = "active"
    predecessor_admission_id: str | None = None; originating_grant_id: str | None = None
    originating_grant_digest: str | None = None; binding_digest: str = ""


@dataclass(frozen=True)
class RevocationEvidence:
    revocation_id: str; admission_id: str; capability_id: str; principal_id: str
    subject_id: str; issuer_id: str; sequence: int; reason_category: str
    provenance: str; binding_digest: str = ""


def _seal(record: AdmissionEvidence | RevocationEvidence) -> str:
    payload = asdict(record); payload.pop("binding_digest")
    return _digest(payload)


class AdmissionLedger:
    """Atomic hash-sealed snapshot; loading always revalidates every record."""
    def __init__(self, path: Path) -> None: self.path = path

    @contextmanager
    def _exclusive_update_lock(self) -> Iterator[None]:
        """Serialize admission read/check/write updates across local processes."""
        if os.name != "posix":
            raise AdmissionError("admission_ledger_lock_unsupported_platform")
        directory_fd: int | None = None
        descriptor: int | None = None
        try:
            require_flock()
            if not hasattr(os, "O_NOFOLLOW"):
                raise AdmissionError("admission_ledger_nofollow_unsupported")
            directory_fd = open_private_directory(self.path.parent, create=True)
            descriptor = os.open(".runtime-admission.lock",
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                0o600, dir_fd=directory_fd)
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode)
                    or opened.st_uid != os.geteuid() or opened.st_nlink != 1
                    or opened.st_mode & 0o077):
                raise AdmissionError("admission_ledger_lock_invalid")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except AdmissionError:
            if descriptor is not None:
                os.close(descriptor)
            if directory_fd is not None:
                os.close(directory_fd)
            raise
        except (OSError, PrivateFileCustodyError) as exc:
            if descriptor is not None:
                os.close(descriptor)
            if directory_fd is not None:
                os.close(directory_fd)
            raise AdmissionError("admission_ledger_lock_unavailable") from exc
        assert directory_fd is not None and descriptor is not None
        try:
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
                os.close(directory_fd)

    def load(self) -> tuple[tuple[AdmissionEvidence, ...], tuple[RevocationEvidence, ...]]:
        if os.name == "nt":
            try:
                raw = read_explicit_file(self.path, max_bytes=MAX_LEDGER_BYTES)
            except WindowsHandleCustodyError as exc:
                if str(exc) == "explicit_file_missing":
                    return (), ()
                raise AdmissionError("corrupt_admission_ledger") from exc
        else:
            try:
                directory_fd = open_private_directory(self.path.parent, create=False)
            except PrivateFileCustodyError as exc:
                if exc.code == "directory_root_missing":
                    return (), ()
                raise AdmissionError("corrupt_admission_ledger") from exc
            try:
                try:
                    raw = read_private_file_at(directory_fd, self.path.name,
                        max_bytes=MAX_LEDGER_BYTES, require_private_mode=False)
                except PrivateFileCustodyError as exc:
                    if exc.code == "file_missing":
                        return (), ()
                    raise AdmissionError("corrupt_admission_ledger") from exc
            finally:
                os.close(directory_fd)
        try:
            payload = json.loads(raw.decode("utf-8"))
            if (not isinstance(payload, dict)
                    or json.dumps(payload, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False).encode("utf-8") != raw):
                raise ValueError
            claimed = payload.pop("ledger_digest")
            if set(payload) != {"schema", "admissions", "revocations"} or payload.get("schema") != SCHEMA or claimed != _digest(payload): raise ValueError
            if (not isinstance(payload["admissions"], list) or len(payload["admissions"]) > MAX_ADMISSIONS
                    or not isinstance(payload["revocations"], list) or len(payload["revocations"]) > MAX_REVOCATIONS):
                raise ValueError
            admissions = tuple(AdmissionEvidence(**{**row, "effects": tuple(row["effects"])}) for row in payload["admissions"])
            revocations = tuple(RevocationEvidence(**row) for row in payload["revocations"])
            if any(item.binding_digest != _seal(item) for item in admissions): raise ValueError
            if any(item.binding_digest != _seal(item) for item in revocations): raise ValueError
            if (len({item.admission_id for item in admissions}) != len(admissions)
                    or len({item.revocation_id for item in revocations}) != len(revocations)
                    or any(not item.effects or tuple(sorted(set(item.effects))) != item.effects for item in admissions)):
                raise ValueError
            orders = [x.issued_sequence for x in admissions] + [x.sequence for x in revocations]
            if len(orders) != len(set(orders)) or any(x < 1 for x in orders): raise ValueError
            by_id = {item.admission_id: item for item in admissions}
            if any((item.admission_id not in by_id
                    or item.capability_id != by_id[item.admission_id].capability_id
                    or item.principal_id != by_id[item.admission_id].principal_id
                    or item.subject_id != by_id[item.admission_id].subject_id
                    or item.sequence <= by_id[item.admission_id].issued_sequence)
                    for item in revocations):
                raise ValueError
            return admissions, revocations
        except (OSError, UnicodeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AdmissionError("corrupt_admission_ledger") from exc

    def current_sequence(self) -> int:
        """Return the latest durable issue or revocation sequence for this ledger."""
        admissions, revocations = self.load()
        return max([item.issued_sequence for item in admissions]
                   + [item.sequence for item in revocations], default=1)

    def next_sequence(self) -> int:
        """Return the next local ledger sequence; issuance still rechecks under lock."""
        admissions, revocations = self.load()
        return max([item.issued_sequence for item in admissions]
                   + [item.sequence for item in revocations], default=0) + 1

    def save(self, admissions: tuple[AdmissionEvidence, ...],
             revocations: tuple[RevocationEvidence, ...]) -> None:
        with self._exclusive_update_lock():
            self._save_unlocked(admissions, revocations)

    def _save_unlocked(self, admissions: tuple[AdmissionEvidence, ...],
                       revocations: tuple[RevocationEvidence, ...]) -> None:
        if os.name != "posix":
            raise AdmissionError("admission_ledger_publication_unsupported_platform")
        if len(admissions) > MAX_ADMISSIONS or len(revocations) > MAX_REVOCATIONS:
            raise AdmissionError("admission_ledger_retention_limit_exceeded")
        payload: dict[str, Any] = {"schema": SCHEMA, "admissions": [asdict(x) for x in admissions],
            "revocations": [asdict(x) for x in revocations]}
        payload["ledger_digest"] = _digest(payload)
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        if len(raw) > MAX_LEDGER_BYTES:
            raise AdmissionError("admission_ledger_size_limit_exceeded")
        try:
            replace_private_bytes(self.path, raw, max_bytes=MAX_LEDGER_BYTES)
        except PrivateFileCustodyError as exc:
            raise AdmissionError("admission_ledger_publication_failed") from exc


class RuntimeAdmissionAuthority:
    """Independent control-plane evidence issuer; performs no admitted effect."""
    def __init__(self, *, definitions: Mapping[str, TaskAuthorityDefinition], ledger: AdmissionLedger, issuer_id: str = ISSUER_ID) -> None:
        self._definitions, self._ledger, self._issuer_id = definitions, ledger, issuer_id

    def issue(self, *, admission_id: str, capability_id: str, definition_version: int,
              subsystem_kind: str, principal_id: str, principal_kind: str, effects: tuple[str, ...],
              subject_id: str, request_configuration_digest: str, provenance: str,
              issued_sequence: int, valid_through_sequence: int,
              affirmative_preconditions: tuple[str, ...], predecessor_admission_id: str | None = None,
              originating_grant_id: str | None = None,
              originating_grant_digest: str | None = None) -> AdmissionEvidence:
        with self._ledger._exclusive_update_lock():
            return self._issue_locked(
                admission_id=admission_id, capability_id=capability_id,
                definition_version=definition_version, subsystem_kind=subsystem_kind,
                principal_id=principal_id, principal_kind=principal_kind, effects=effects,
                subject_id=subject_id, request_configuration_digest=request_configuration_digest,
                provenance=provenance, issued_sequence=issued_sequence,
                valid_through_sequence=valid_through_sequence,
                affirmative_preconditions=affirmative_preconditions,
                predecessor_admission_id=predecessor_admission_id,
                originating_grant_id=originating_grant_id,
                originating_grant_digest=originating_grant_digest)

    def issue_next(self, *, admission_id_for_sequence: Callable[[int], str],
                   capability_id: str, definition_version: int, subsystem_kind: str,
                   principal_id: str, principal_kind: str, effects: tuple[str, ...],
                   subject_id: str, request_configuration_digest: str, provenance: str,
                   affirmative_preconditions: tuple[str, ...],
                   predecessor_admission_id: str | None = None,
                   originating_grant_id: str | None = None,
                   originating_grant_digest: str | None = None) -> AdmissionEvidence:
        """Allocate a one-sequence admission inside the same locked ledger transaction."""
        with self._ledger._exclusive_update_lock():
            sequence = self._ledger.next_sequence()
            admission_id = admission_id_for_sequence(sequence)
            if not isinstance(admission_id, str):
                raise AdmissionError("malformed_admission_request")
            return self._issue_locked(
                admission_id=admission_id, capability_id=capability_id,
                definition_version=definition_version, subsystem_kind=subsystem_kind,
                principal_id=principal_id, principal_kind=principal_kind, effects=effects,
                subject_id=subject_id, request_configuration_digest=request_configuration_digest,
                provenance=provenance, issued_sequence=sequence,
                valid_through_sequence=sequence,
                affirmative_preconditions=affirmative_preconditions,
                predecessor_admission_id=predecessor_admission_id,
                originating_grant_id=originating_grant_id,
                originating_grant_digest=originating_grant_digest)

    def _issue_locked(self, *, admission_id: str, capability_id: str,
                      definition_version: int, subsystem_kind: str, principal_id: str,
                      principal_kind: str, effects: tuple[str, ...], subject_id: str,
                      request_configuration_digest: str, provenance: str,
                      issued_sequence: int, valid_through_sequence: int,
                      affirmative_preconditions: tuple[str, ...],
                      predecessor_admission_id: str | None,
                      originating_grant_id: str | None,
                      originating_grant_digest: str | None) -> AdmissionEvidence:
        definition = self._definitions.get(capability_id)
        if definition is None:
            raise AdmissionError("unregistered_capability")
        if subsystem_kind not in definition.subsystem_kinds:
            raise AdmissionError("subsystem_not_admitted")
        if principal_kind not in definition.principal_kinds or not principal_id:
            raise AdmissionError("principal_not_admitted")
        if not effects or not frozenset(effects).issubset(definition.required_effects) or len(effects) != len(set(effects)):
            raise AdmissionError("effect_scope_mismatch")
        if affirmative_preconditions != definition.approval_requirements:
            raise AdmissionError("affirmative_preconditions_mismatch")
        if (any(not isinstance(value, str) or not value or "*" in value for value in
                (admission_id, subject_id, request_configuration_digest, provenance))
                or definition_version < 1 or issued_sequence < 1
                or valid_through_sequence < issued_sequence):
            raise AdmissionError("malformed_admission_request")
        scoped_text = f"{subject_id} {provenance}".casefold()
        if any(phrase.casefold() in scoped_text for phrase in definition.forbidden_goal_phrases):
            raise AdmissionError("forbidden_scope")
        admissions, revocations = self._ledger.load()
        if any(item.admission_id == admission_id for item in admissions):
            raise AdmissionError("duplicate_admission_id")
        used_sequences = {item.issued_sequence for item in admissions}
        used_sequences.update(item.sequence for item in revocations)
        if issued_sequence in used_sequences:
            raise AdmissionError("duplicate_evidence_sequence")
        if predecessor_admission_id and not any(
                item.admission_id == predecessor_admission_id for item in admissions):
            raise AdmissionError("unknown_predecessor")
        item = AdmissionEvidence(
            admission_id, capability_id, authority_definition_digest(definition), definition_version,
            subsystem_kind, principal_id, principal_kind, tuple(sorted(effects)), subject_id,
            request_configuration_digest, self._issuer_id, provenance, issued_sequence,
            valid_through_sequence, predecessor_admission_id=predecessor_admission_id,
            originating_grant_id=originating_grant_id,
            originating_grant_digest=originating_grant_digest)
        item = replace(item, binding_digest=_seal(item))
        self._ledger._save_unlocked((*admissions, item), revocations)
        return item

    def revoke(self, admission_id: str, *, sequence: int, reason_category: str,
               provenance: str) -> RevocationEvidence:
        with self._ledger._exclusive_update_lock():
            admissions, revocations = self._ledger.load()
            admission = next((x for x in admissions if x.admission_id == admission_id), None)
            used_sequences = {x.issued_sequence for x in admissions} | {x.sequence for x in revocations}
            if (admission is None or sequence <= admission.issued_sequence or not reason_category
                    or not provenance or sequence in used_sequences):
                raise AdmissionError("invalid_revocation")
            item = RevocationEvidence(
                f"revocation-{admission_id}-{sequence}", admission_id, admission.capability_id,
                admission.principal_id, admission.subject_id, self._issuer_id, sequence,
                reason_category, provenance)
            item = replace(item, binding_digest=_seal(item))
            self._ledger._save_unlocked(admissions, (*revocations, item))
            return item



class RuntimeAdmissionVerifier:
    def __init__(self, *, definitions: Mapping[str, TaskAuthorityDefinition], ledger: AdmissionLedger, issuer_id: str = ISSUER_ID) -> None:
        self._definitions, self._ledger, self._issuer_id = definitions, ledger, issuer_id

    def recorded_admission(self, admission_id: str) -> AdmissionEvidence:
        """Resolve one exact, ledger-verified admission for historical custody recovery."""
        admissions, _ = self._ledger.load()
        matches = tuple(item for item in admissions if item.admission_id == admission_id)
        if len(matches) != 1:
            raise AdmissionError("recorded_admission_missing_or_ambiguous")
        return matches[0]

    @contextmanager
    def authorized_local_commit(self) -> Iterator[None]:
        """Order an admitted local mutation atomically against issue/revocation."""
        with self._ledger._exclusive_update_lock():
            yield

    def verify(self, admission: AdmissionEvidence, *, current_sequence: int, capability_id: str, principal_id: str, effect: str, subject_id: str, request_configuration_digest: str) -> None:
        admissions, revocations = self._ledger.load(); definition = self._definitions.get(capability_id)
        stored = next((x for x in admissions if x.admission_id == admission.admission_id), None)
        if definition is None: raise AdmissionError("unregistered_capability")
        if stored != admission or admission.binding_digest != _seal(admission) or admission.status != "active": raise AdmissionError("malformed_or_unknown_admission")
        if admission.issuer_id != self._issuer_id or not admission.provenance: raise AdmissionError("invalid_issuer_or_provenance")
        if admission.capability_id != capability_id or admission.authority_definition_digest != authority_definition_digest(definition): raise AdmissionError("authority_definition_mismatch")
        if (admission.principal_id, effect in admission.effects, admission.subject_id, admission.request_configuration_digest) != (principal_id, True, subject_id, request_configuration_digest): raise AdmissionError("admission_binding_mismatch")
        if not admission.issued_sequence <= current_sequence <= admission.valid_through_sequence: raise AdmissionError("admission_expired")
        if any(x.admission_id == admission.admission_id and x.sequence <= current_sequence for x in revocations): raise AdmissionError("admission_revoked")
        if any(x.predecessor_admission_id == admission.admission_id and x.issued_sequence <= current_sequence for x in admissions): raise AdmissionError("admission_superseded")
