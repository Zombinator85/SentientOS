"""Offline operator-scoped policy for bounded runtime admission issuance.

Definitions describe possible authority; grants record authenticated operator intent;
this policy may narrow both into admission evidence.  None of these operations execute
an effect.  Grant revocation prevents new issuance but, deliberately, does not revoke
admissions already issued: those remain governed by their own bounded lifecycle.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from sentientos.codex_task_authority_admission import TaskAuthorityDefinition, authority_definition_digest
from sentientos.runtime_admission import AdmissionEvidence, RuntimeAdmissionAuthority

SCHEMA = "sentientos.runtime_operator_grant_ledger:v1"
APPROVAL_SCHEMA = "sentientos.runtime_operator_grant_approval:v1"


class RuntimeGrantError(ValueError):
    pass


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class OperatorGrantApproval:
    evidence_id: str
    operator_identity_label: str
    approval_status: str
    grant_id: str
    grant_payload_digest: str
    provenance: str
    evidence_digest: str = ""


@dataclass(frozen=True)
class RuntimeOperatorGrant:
    grant_id: str
    operator_identity_label: str
    capability_id: str
    authority_definition_digest: str
    authority_definition_version: int
    subsystem_kind: str
    principal_id: str
    principal_kind: str
    effects: tuple[str, ...]
    subject_ids: tuple[str, ...]
    request_configuration_digests: tuple[str, ...]
    valid_from_sequence: int
    valid_through_sequence: int
    policy_epoch: int
    provenance: str
    issued_sequence: int
    status: str = "active"
    binding_digest: str = ""


@dataclass(frozen=True)
class GrantRevocation:
    revocation_id: str
    grant_id: str
    sequence: int
    operator_identity_label: str
    reason_category: str
    provenance: str
    binding_digest: str = ""


@dataclass(frozen=True)
class RuntimeGrantRequest:
    admission_id: str
    capability_id: str
    definition_version: int
    subsystem_kind: str
    principal_id: str
    principal_kind: str
    effects: tuple[str, ...]
    subject_id: str
    request_configuration_digest: str
    issued_sequence: int
    valid_through_sequence: int
    policy_epoch: int
    provenance: str
    affirmative_preconditions: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeGrantDecision:
    status: str
    reason: str
    grant_id: str | None = None


def _seal(value: RuntimeOperatorGrant | GrantRevocation) -> str:
    payload = asdict(value); payload.pop("binding_digest")
    return digest(payload)


def grant_payload_digest(grant: RuntimeOperatorGrant) -> str:
    payload = asdict(grant); payload.pop("binding_digest")
    return digest(payload)


def approval_digest(approval: OperatorGrantApproval) -> str:
    payload = {"schema": APPROVAL_SCHEMA, **asdict(approval)}; payload.pop("evidence_digest")
    return digest(payload)


class RuntimeGrantLedger:
    """Atomic digest-sealed grant and revocation custody; corruption fails closed."""
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> tuple[tuple[RuntimeOperatorGrant, ...], tuple[GrantRevocation, ...]]:
        if not self.path.exists():
            return (), ()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8")); claimed = payload.pop("ledger_digest")
            if payload.get("schema") != SCHEMA or claimed != digest(payload): raise ValueError
            grants = tuple(RuntimeOperatorGrant(**{**row, "effects": tuple(row["effects"]), "subject_ids": tuple(row["subject_ids"]), "request_configuration_digests": tuple(row["request_configuration_digests"])}) for row in payload["grants"])
            revocations = tuple(GrantRevocation(**row) for row in payload["revocations"])
            if any(x.binding_digest != _seal(x) for x in grants): raise ValueError
            if any(x.binding_digest != _seal(x) for x in revocations): raise ValueError
            ids = [x.grant_id for x in grants]; orders = [x.issued_sequence for x in grants] + [x.sequence for x in revocations]
            if len(ids) != len(set(ids)) or len(orders) != len(set(orders)) or any(x < 1 for x in orders): raise ValueError
            return grants, revocations
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeGrantError("corrupt_grant_ledger") from exc

    def save(self, grants: tuple[RuntimeOperatorGrant, ...], revocations: tuple[GrantRevocation, ...]) -> None:
        payload: dict[str, Any] = {"schema": SCHEMA, "grants": [asdict(x) for x in grants], "revocations": [asdict(x) for x in revocations]}
        payload["ledger_digest"] = digest(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        try:
            with temp.open("xb") as stream: stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()); stream.flush(); os.fsync(stream.fileno())
            temp.replace(self.path)
        finally:
            if temp.exists(): temp.unlink()


class RuntimeGrantAuthority:
    """Operator-side custody boundary. Consumers are never given this object."""
    def __init__(self, *, definitions: Mapping[str, TaskAuthorityDefinition], ledger: RuntimeGrantLedger) -> None:
        self._definitions, self._ledger = definitions, ledger

    def record(self, grant: RuntimeOperatorGrant, approval: OperatorGrantApproval) -> RuntimeOperatorGrant:
        definition = self._definitions.get(grant.capability_id)
        if definition is None: raise RuntimeGrantError("unregistered_capability")
        if grant.binding_digest: raise RuntimeGrantError("malformed_grant")
        if (approval.approval_status != "approved" or approval.grant_id != grant.grant_id or approval.operator_identity_label != grant.operator_identity_label or approval.grant_payload_digest != grant_payload_digest(grant) or approval.evidence_digest != approval_digest(approval) or not approval.evidence_id or not approval.provenance): raise RuntimeGrantError("invalid_operator_provenance")
        if grant.authority_definition_digest != authority_definition_digest(definition): raise RuntimeGrantError("authority_definition_mismatch")
        if grant.subsystem_kind not in definition.subsystem_kinds or grant.principal_kind not in definition.principal_kinds or not set(grant.effects).issubset(definition.required_effects): raise RuntimeGrantError("grant_broadens_definition")
        values = (grant.grant_id, grant.operator_identity_label, grant.principal_id, grant.provenance, *grant.effects, *grant.subject_ids)
        if grant.status != "active" or not grant.effects or not grant.subject_ids or len(grant.effects) != len(set(grant.effects)) or len(grant.subject_ids) != len(set(grant.subject_ids)) or any(not x or "*" in x for x in values) or grant.authority_definition_version < 1 or grant.policy_epoch < 1 or grant.issued_sequence < 1 or not grant.valid_from_sequence <= grant.valid_through_sequence: raise RuntimeGrantError("malformed_grant")
        grants, revocations = self._ledger.load()
        if any(x.grant_id == grant.grant_id for x in grants): raise RuntimeGrantError("duplicate_grant_id")
        if grant.issued_sequence in {x.issued_sequence for x in grants} | {x.sequence for x in revocations}: raise RuntimeGrantError("duplicate_grant_order")
        sealed = replace(grant, effects=tuple(sorted(grant.effects)), subject_ids=tuple(sorted(grant.subject_ids)), request_configuration_digests=tuple(sorted(grant.request_configuration_digests)))
        sealed = replace(sealed, binding_digest=_seal(sealed)); self._ledger.save((*grants, sealed), revocations); return sealed

    def revoke(self, grant_id: str, *, sequence: int, operator_identity_label: str, reason_category: str, provenance: str) -> GrantRevocation:
        grants, revocations = self._ledger.load(); grant = next((x for x in grants if x.grant_id == grant_id), None)
        orders = {x.issued_sequence for x in grants} | {x.sequence for x in revocations}
        if grant is None or operator_identity_label != grant.operator_identity_label or sequence <= grant.issued_sequence or sequence in orders or not reason_category or not provenance: raise RuntimeGrantError("invalid_grant_revocation")
        item = GrantRevocation(f"revocation-{grant_id}-{sequence}", grant_id, sequence, operator_identity_label, reason_category, provenance)
        item = replace(item, binding_digest=_seal(item)); self._ledger.save(grants, (*revocations, item)); return item


class RuntimeGrantPolicy:
    """Deterministic policy and the sole grant-aware admission orchestration path."""
    def __init__(self, *, definitions: Mapping[str, TaskAuthorityDefinition], ledger: RuntimeGrantLedger, admission_authority: RuntimeAdmissionAuthority) -> None:
        self._definitions, self._ledger, self.__admission_authority = definitions, ledger, admission_authority

    def evaluate(self, grant_id: str, request: RuntimeGrantRequest, *, current_sequence: int, current_policy_epoch: int, policy_available: bool = True, operational_feasibility: object | None = None) -> RuntimeGrantDecision:
        try: grants, revocations = self._ledger.load()
        except RuntimeGrantError: return RuntimeGrantDecision("invalid", "corrupt_grant_state", grant_id)
        grant = next((x for x in grants if x.grant_id == grant_id), None); definition = self._definitions.get(request.capability_id)
        if not request.admission_id or current_sequence < 1 or request.issued_sequence < current_sequence or request.valid_through_sequence < request.issued_sequence: return RuntimeGrantDecision("invalid", "malformed_request", grant_id)
        if grant is None: return RuntimeGrantDecision("denied", "missing_grant", grant_id)
        if definition is None: return RuntimeGrantDecision("denied", "unknown_capability", grant_id)
        if not policy_available: return RuntimeGrantDecision("denied", "policy_unavailable", grant_id)
        if grant.binding_digest != _seal(grant): return RuntimeGrantDecision("invalid", "malformed_grant", grant_id)
        if grant.capability_id != request.capability_id or grant.authority_definition_digest != authority_definition_digest(definition) or grant.authority_definition_version != request.definition_version: return RuntimeGrantDecision("denied", "definition_binding_mismatch", grant_id)
        if grant.policy_epoch != current_policy_epoch or request.policy_epoch != current_policy_epoch: return RuntimeGrantDecision("denied", "stale_grant", grant_id)
        if not grant.valid_from_sequence <= current_sequence <= grant.valid_through_sequence: return RuntimeGrantDecision("denied", "expired_grant", grant_id)
        if any(x.grant_id == grant_id and x.sequence <= current_sequence for x in revocations): return RuntimeGrantDecision("denied", "revoked_grant", grant_id)
        if request.subsystem_kind != grant.subsystem_kind: return RuntimeGrantDecision("denied", "wrong_subsystem", grant_id)
        if (request.principal_id, request.principal_kind) != (grant.principal_id, grant.principal_kind): return RuntimeGrantDecision("denied", "wrong_principal", grant_id)
        if not set(request.effects).issubset(grant.effects) or not request.effects: return RuntimeGrantDecision("denied", "effect_scope_broadened", grant_id)
        if request.subject_id not in grant.subject_ids: return RuntimeGrantDecision("denied", "wrong_subject", grant_id)
        if grant.request_configuration_digests and request.request_configuration_digest not in grant.request_configuration_digests: return RuntimeGrantDecision("denied", "request_configuration_mismatch", grant_id)
        if request.valid_through_sequence > grant.valid_through_sequence: return RuntimeGrantDecision("denied", "admission_outlives_grant", grant_id)
        if request.capability_id == "external_model_inference":
            from sentientos.external_model_operational_feasibility import verify_operational_feasibility
            if not verify_operational_feasibility(
                operational_feasibility, capability_id=request.capability_id,
                principal_id=request.principal_id, principal_kind=request.principal_kind,
                effects=request.effects, subject_id=request.subject_id,
                request_configuration_digest=request.request_configuration_digest,
                current_sequence=current_sequence, current_policy_epoch=current_policy_epoch,
                definition_version=request.definition_version,
            ): return RuntimeGrantDecision("denied", "operational_feasibility_required", grant_id)
        return RuntimeGrantDecision("allowed", "policy_satisfied", grant_id)

    def issue(self, grant_id: str, request: RuntimeGrantRequest, *, current_sequence: int, current_policy_epoch: int, policy_available: bool = True, operational_feasibility: object | None = None) -> AdmissionEvidence:
        decision = self.evaluate(grant_id, request, current_sequence=current_sequence, current_policy_epoch=current_policy_epoch, policy_available=policy_available, operational_feasibility=operational_feasibility)
        if decision.status != "allowed": raise RuntimeGrantError(decision.reason)
        grant = next(x for x in self._ledger.load()[0] if x.grant_id == grant_id)
        return self.__admission_authority.issue(admission_id=request.admission_id, capability_id=request.capability_id, definition_version=request.definition_version, subsystem_kind=request.subsystem_kind, principal_id=request.principal_id, principal_kind=request.principal_kind, effects=request.effects, subject_id=request.subject_id, request_configuration_digest=request.request_configuration_digest, provenance=request.provenance, issued_sequence=request.issued_sequence, valid_through_sequence=request.valid_through_sequence, affirmative_preconditions=request.affirmative_preconditions, originating_grant_id=grant.grant_id, originating_grant_digest=grant.binding_digest)
