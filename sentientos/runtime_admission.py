"""Durable, non-effectful lifecycle custody for bounded admission evidence."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from sentientos.codex_task_authority_admission import TaskAuthorityDefinition, authority_definition_digest

SCHEMA = "sentientos.runtime_admission_ledger:v1"
ISSUER_ID = "sentientos.control_plane.runtime_admission_authority:v1"


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

    def load(self) -> tuple[tuple[AdmissionEvidence, ...], tuple[RevocationEvidence, ...]]:
        if not self.path.exists(): return (), ()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8")); claimed = payload.pop("ledger_digest")
            if payload.get("schema") != SCHEMA or claimed != _digest(payload): raise ValueError
            admissions = tuple(AdmissionEvidence(**{**row, "effects": tuple(row["effects"])}) for row in payload["admissions"])
            revocations = tuple(RevocationEvidence(**row) for row in payload["revocations"])
            if any(item.binding_digest != _seal(item) for item in admissions): raise ValueError
            if any(item.binding_digest != _seal(item) for item in revocations): raise ValueError
            orders = [x.issued_sequence for x in admissions] + [x.sequence for x in revocations]
            if len(orders) != len(set(orders)) or any(x < 1 for x in orders): raise ValueError
            return admissions, revocations
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AdmissionError("corrupt_admission_ledger") from exc

    def save(self, admissions: tuple[AdmissionEvidence, ...], revocations: tuple[RevocationEvidence, ...]) -> None:
        payload: dict[str, Any] = {"schema": SCHEMA, "admissions": [asdict(x) for x in admissions], "revocations": [asdict(x) for x in revocations]}
        payload["ledger_digest"] = _digest(payload)
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        self.path.parent.mkdir(parents=True, exist_ok=True); temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("xb") as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            if temporary.exists(): temporary.unlink()


class RuntimeAdmissionAuthority:
    """Independent control-plane evidence issuer; performs no admitted effect."""
    def __init__(self, *, definitions: Mapping[str, TaskAuthorityDefinition], ledger: AdmissionLedger, issuer_id: str = ISSUER_ID) -> None:
        self._definitions, self._ledger, self._issuer_id = definitions, ledger, issuer_id

    def issue(self, *, admission_id: str, capability_id: str, definition_version: int, subsystem_kind: str, principal_id: str, principal_kind: str, effects: tuple[str, ...], subject_id: str, request_configuration_digest: str, provenance: str, issued_sequence: int, valid_through_sequence: int, affirmative_preconditions: tuple[str, ...], predecessor_admission_id: str | None = None, originating_grant_id: str | None = None, originating_grant_digest: str | None = None) -> AdmissionEvidence:
        definition = self._definitions.get(capability_id)
        if definition is None: raise AdmissionError("unregistered_capability")
        if subsystem_kind not in definition.subsystem_kinds: raise AdmissionError("subsystem_not_admitted")
        if principal_kind not in definition.principal_kinds or not principal_id: raise AdmissionError("principal_not_admitted")
        if not effects or not frozenset(effects).issubset(definition.required_effects) or len(effects) != len(set(effects)): raise AdmissionError("effect_scope_mismatch")
        if affirmative_preconditions != definition.approval_requirements: raise AdmissionError("affirmative_preconditions_mismatch")
        if any(not x or "*" in x for x in (admission_id, subject_id, request_configuration_digest, provenance)) or definition_version < 1 or issued_sequence < 1 or valid_through_sequence < issued_sequence: raise AdmissionError("malformed_admission_request")
        scoped_text = f"{subject_id} {provenance}".casefold()
        if any(phrase.casefold() in scoped_text for phrase in definition.forbidden_goal_phrases): raise AdmissionError("forbidden_scope")
        admissions, revocations = self._ledger.load()
        if any(x.admission_id == admission_id for x in admissions): raise AdmissionError("duplicate_admission_id")
        if issued_sequence in {x.issued_sequence for x in admissions} | {x.sequence for x in revocations}: raise AdmissionError("duplicate_evidence_sequence")
        if predecessor_admission_id and not any(x.admission_id == predecessor_admission_id for x in admissions): raise AdmissionError("unknown_predecessor")
        item = AdmissionEvidence(admission_id, capability_id, authority_definition_digest(definition), definition_version, subsystem_kind, principal_id, principal_kind, tuple(sorted(effects)), subject_id, request_configuration_digest, self._issuer_id, provenance, issued_sequence, valid_through_sequence, predecessor_admission_id=predecessor_admission_id, originating_grant_id=originating_grant_id, originating_grant_digest=originating_grant_digest)
        item = replace(item, binding_digest=_seal(item)); self._ledger.save((*admissions, item), revocations); return item

    def revoke(self, admission_id: str, *, sequence: int, reason_category: str, provenance: str) -> RevocationEvidence:
        admissions, revocations = self._ledger.load(); admission = next((x for x in admissions if x.admission_id == admission_id), None)
        if admission is None or sequence <= admission.issued_sequence or not reason_category or not provenance or sequence in {x.issued_sequence for x in admissions} | {x.sequence for x in revocations}: raise AdmissionError("invalid_revocation")
        item = RevocationEvidence(f"revocation-{admission_id}-{sequence}", admission_id, admission.capability_id, admission.principal_id, admission.subject_id, self._issuer_id, sequence, reason_category, provenance)
        item = replace(item, binding_digest=_seal(item)); self._ledger.save(admissions, (*revocations, item)); return item


class RuntimeAdmissionVerifier:
    def __init__(self, *, definitions: Mapping[str, TaskAuthorityDefinition], ledger: AdmissionLedger, issuer_id: str = ISSUER_ID) -> None:
        self._definitions, self._ledger, self._issuer_id = definitions, ledger, issuer_id

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
