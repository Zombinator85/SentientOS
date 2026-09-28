"""Separately admitted deterministic mutation of persistent epistemic custody."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar

from .codex_task_authority_admission import RESIDENT_EPISTEMIC_STATE_MUTATION
from .persistent_epistemic_state import (
    DEPENDENCIES, EVIDENCE_RELATIONS, FALSE_AUTHORITY, STANCES, UPDATE_REASONS,
    EpistemicStateError, EpistemicUpdateCandidate, EvidenceBinding,
    PersistentEpistemicStateOwner, canonical_bytes, digest,
    make_epistemic_update_candidate, make_evidence_binding,
)
from .runtime_admission import AdmissionError, AdmissionEvidence, RuntimeAdmissionVerifier

PRINCIPAL = "deterministic_resident_epistemic_state_controller"
EVIDENCE_BINDING_EFFECTS = tuple(sorted({
    "exact_epistemic_proposition_read", "exact_epistemic_evidence_source_artifact_read",
    "exact_epistemic_evidence_binding_validation", "bounded_epistemic_evidence_binding_append",
    "epistemic_mutation_receipt_write", "read_only_epistemic_post_mutation_verification",
}))
STATE_UPDATE_EFFECTS = tuple(sorted({
    "exact_epistemic_proposition_read", "exact_epistemic_current_state_read",
    "exact_epistemic_update_candidate_read", "deterministic_epistemic_update_candidate_validation",
    "exact_epistemic_predecessor_state_compare_and_swap", "bounded_epistemic_state_generation_append",
    "bounded_epistemic_update_event_append", "epistemic_mutation_receipt_write",
    "read_only_epistemic_post_mutation_verification",
}))
SOURCE_PROOF_SCHEMA = "sentientos.epistemic_evidence_source_proof:v1"
RECEIPT_SCHEMA = "sentientos.resident_epistemic_mutation_receipt:v1"
ReceiptT = TypeVar("ReceiptT", bound="EvidenceBindingMutationReceipt | EpistemicStateMutationReceipt")


class EpistemicMutationError(ValueError):
    """A fail-closed admission, identity, or custody failure."""


def _identity(prefix: str, payload: Mapping[str, Any]) -> tuple[str, str]:
    value = digest(payload)
    return f"{prefix}:{value[7:31]}", value


@dataclass(frozen=True)
class EpistemicEvidenceSourceProof:
    proof_id: str; proof_digest: str; source_artifact_id: str; source_digest: str
    source_schema: str; source_class: str; recorded_at: str; adapter_id: str
    provenance_id: str; authority: Mapping[str, bool]; schema_version: str = SOURCE_PROOF_SCHEMA

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("proof_id"); value.pop("proof_digest"); return value


def make_epistemic_evidence_source_proof(**kwargs: Any) -> EpistemicEvidenceSourceProof:
    kwargs.setdefault("authority", dict(FALSE_AUTHORITY))
    raw = EpistemicEvidenceSourceProof("", "", **kwargs)
    if (dict(raw.authority) != FALSE_AUTHORITY or not all((raw.source_artifact_id,
            raw.source_digest, raw.source_schema, raw.source_class, raw.recorded_at,
            raw.adapter_id, raw.provenance_id))):
        raise EpistemicMutationError("source_proof_shape_invalid")
    proof_id, proof_digest = _identity("epistemic-source", raw.payload())
    return replace(raw, proof_id=proof_id, proof_digest=proof_digest)


@dataclass(frozen=True)
class EvidenceBindingMutationReceipt:
    receipt_id: str; receipt_digest: str; stage: str; binding_id: str; binding_digest: str
    proposition_id: str; source_artifact_id: str; source_digest: str; admission_id: str
    admission_binding_digest: str; principal: str; operation_id: str; correlation_id: str
    storage_verified: bool = True; authority: bool = False; schema_version: str = RECEIPT_SCHEMA

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("receipt_id"); value.pop("receipt_digest"); return value


@dataclass(frozen=True)
class EpistemicStateMutationReceipt:
    receipt_id: str; receipt_digest: str; stage: str; candidate_id: str; proposition_id: str
    predecessor_state_digest: str | None; successor_state_id: str; successor_state_digest: str
    update_event_id: str; update_event_digest: str; evidence_set_digest: str; generation: int
    admission_id: str; admission_binding_digest: str; principal: str; operation_id: str
    correlation_id: str; storage_verified: bool = True; authority: bool = False
    schema_version: str = RECEIPT_SCHEMA

    def payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("receipt_id"); value.pop("receipt_digest"); return value


class ResidentEpistemicStateMutationController:
    def __init__(self, *, owner: PersistentEpistemicStateOwner,
                 admission_verifier: RuntimeAdmissionVerifier,
                 current_sequence: Callable[[], int], receipt_root: str | Path) -> None:
        self.owner, self.admission_verifier = owner, admission_verifier
        self.current_sequence = current_sequence
        self.receipt_root = Path(receipt_root)
        if self.receipt_root.exists() and self.receipt_root.is_symlink():
            raise EpistemicMutationError("receipt_root_symlink_forbidden")
        for stage in ("evidence", "state"):
            path = self.receipt_root / "receipts" / stage
            path.mkdir(parents=True, exist_ok=True)
            if path.is_symlink(): raise EpistemicMutationError("receipt_path_symlink_forbidden")
        self.verify_receipts()

    @staticmethod
    def evidence_configuration_digest(*, binding: EvidenceBinding, proposition_digest: str,
                                      operation_id: str) -> str:
        return digest({"stage":"evidence_binding_append", "principal":PRINCIPAL,
            "proposition_id":binding.proposition_id, "proposition_digest":proposition_digest,
            "binding_id":binding.binding_id, "binding_digest":binding.binding_digest,
            "source_artifact_id":binding.source_artifact_id, "source_digest":binding.source_digest,
            "operation_id":operation_id, "effects":EVIDENCE_BINDING_EFFECTS})

    @staticmethod
    def state_configuration_digest(*, candidate: EpistemicUpdateCandidate, operation_id: str) -> str:
        return digest({"stage":"epistemic_state_update", "principal":PRINCIPAL,
            "candidate_id":candidate.candidate_id, "proposition_id":candidate.proposition_id,
            "predecessor_state_digest":candidate.predecessor_state_digest,
            "proposed_stance":candidate.proposed_stance,
            "evidence_binding_ids":candidate.evidence_binding_ids, "reason":candidate.reason,
            "operation_id":operation_id, "effects":STATE_UPDATE_EFFECTS})

    def _admit(self, admission: AdmissionEvidence, *, effects: tuple[str, ...],
               subject_id: str, configuration_digest: str) -> None:
        if tuple(admission.effects) != effects:
            raise EpistemicMutationError("admission_effect_surface_not_exact")
        try:
            for effect in effects:
                self.admission_verifier.verify(admission, current_sequence=self.current_sequence(),
                    capability_id=RESIDENT_EPISTEMIC_STATE_MUTATION, principal_id=PRINCIPAL,
                    effect=effect, subject_id=subject_id,
                    request_configuration_digest=configuration_digest)
        except AdmissionError as exc:
            raise EpistemicMutationError(f"runtime_admission_rejected:{exc}") from exc

    def _write_receipt(self, stage: str, receipt: ReceiptT) -> ReceiptT:
        path = self.receipt_root / "receipts" / stage / f"{receipt.receipt_id}.json"
        if path.is_symlink(): raise EpistemicMutationError("receipt_symlink_forbidden")
        raw = canonical_bytes(asdict(receipt)) + b"\n"
        try: fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if path.read_bytes() != raw: raise EpistemicMutationError("immutable_receipt_collision")
            return receipt
        with os.fdopen(fd, "wb") as stream: stream.write(raw)
        return receipt

    def verify_receipts(self) -> None:
        for stage, cls in (("evidence", EvidenceBindingMutationReceipt), ("state", EpistemicStateMutationReceipt)):
            for path in sorted((self.receipt_root / "receipts" / stage).glob("*.json")):
                if path.is_symlink(): raise EpistemicMutationError("receipt_symlink_forbidden")
                try: receipt = cls(**json.loads(path.read_text()))
                except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise EpistemicMutationError("mutation_receipt_corrupt") from exc
                rid, rdigest = _identity("epistemic-mutation-receipt", receipt.payload())
                if (receipt.receipt_id, receipt.receipt_digest) != (rid, rdigest) or path.stem != rid:
                    raise EpistemicMutationError("mutation_receipt_identity_mismatch")

    def append_evidence_binding(self, *, binding: EvidenceBinding,
                                source_proof: EpistemicEvidenceSourceProof,
                                admission: AdmissionEvidence, operation_id: str,
                                correlation_id: str) -> EvidenceBindingMutationReceipt:
        self.owner.verify(); proposition = self.owner.proposition(binding.proposition_id)
        expected = make_evidence_binding(**{k:v for k,v in asdict(binding).items()
                                            if k not in {"binding_id","binding_digest","schema_version"}})
        expected_proof = make_epistemic_evidence_source_proof(**{k:v for k,v in asdict(source_proof).items()
                                            if k not in {"proof_id","proof_digest","schema_version"}})
        if expected != binding: raise EpistemicMutationError("evidence_binding_identity_mismatch")
        if expected_proof != source_proof: raise EpistemicMutationError("source_proof_identity_mismatch")
        if dict(binding.authority) != FALSE_AUTHORITY: raise EpistemicMutationError("evidence_authority_widened")
        source_fields = (binding.source_artifact_id, binding.source_digest, binding.source_schema,
                         binding.source_class, binding.observation_time)
        proof_fields = (source_proof.source_artifact_id, source_proof.source_digest,
                        source_proof.source_schema, source_proof.source_class, source_proof.recorded_at)
        if source_fields != proof_fields: raise EpistemicMutationError("source_proof_binding_mismatch")
        if binding.evidence_relation not in EVIDENCE_RELATIONS or binding.dependency_kind not in DEPENDENCIES:
            raise EpistemicMutationError("evidence_binding_vocabulary_invalid")
        configuration = self.evidence_configuration_digest(binding=binding,
            proposition_digest=proposition.proposition_digest, operation_id=operation_id)
        self._admit(admission, effects=EVIDENCE_BINDING_EFFECTS,
                    subject_id=binding.binding_id, configuration_digest=configuration)
        self.owner.bind_evidence(binding); self.owner.verify()
        matches = [item for item in self.owner.bindings(binding.proposition_id) if item.binding_id == binding.binding_id]
        if matches != [binding] or dict(matches[0].authority) != FALSE_AUTHORITY:
            raise EpistemicMutationError("evidence_post_write_verification_failed")
        raw = EvidenceBindingMutationReceipt("", "", "evidence_binding_append", binding.binding_id,
            binding.binding_digest, binding.proposition_id, binding.source_artifact_id, binding.source_digest,
            admission.admission_id, admission.binding_digest, PRINCIPAL, operation_id, correlation_id)
        rid, rdigest = _identity("epistemic-mutation-receipt", raw.payload())
        return self._write_receipt("evidence", replace(raw, receipt_id=rid, receipt_digest=rdigest))

    def commit_update_candidate(self, *, candidate: EpistemicUpdateCandidate,
                                admission: AdmissionEvidence, operation_id: str,
                                correlation_id: str, tick: int,
                                recorded_at: str) -> EpistemicStateMutationReceipt:
        self.owner.verify(); self.owner.proposition(candidate.proposition_id)
        try:
            expected = make_epistemic_update_candidate(**{k:v for k,v in asdict(candidate).items()
                                                           if k not in {"candidate_id","schema_version"}})
        except EpistemicStateError as exc:
            raise EpistemicMutationError(f"candidate_invalid:{exc}") from exc
        if expected != candidate: raise EpistemicMutationError("candidate_identity_mismatch")
        if candidate.proposed_stance not in STANCES or candidate.reason not in UPDATE_REASONS:
            raise EpistemicMutationError("candidate_vocabulary_invalid")
        prior = self.owner.current_state(candidate.proposition_id)
        if candidate.predecessor_state_digest != (prior.state_digest if prior else None):
            raise EpistemicMutationError("epistemic_state_compare_and_swap_failed")
        known = {item.binding_id:item for item in self.owner.bindings(candidate.proposition_id)}
        if any(item not in known or known[item].withdrawn for item in candidate.evidence_binding_ids):
            raise EpistemicMutationError("candidate_evidence_missing_foreign_or_withdrawn")
        # A binding receipt is evidence of append only; its admission may never authorize this stage.
        used_evidence_admissions = {json.loads(path.read_text())["admission_id"] for path in
            (self.receipt_root / "receipts" / "evidence").glob("*.json")}
        if admission.admission_id in used_evidence_admissions:
            raise EpistemicMutationError("separate_stage_admission_required")
        configuration = self.state_configuration_digest(candidate=candidate, operation_id=operation_id)
        self._admit(admission, effects=STATE_UPDATE_EFFECTS, subject_id=candidate.candidate_id,
                    configuration_digest=configuration)
        previous_ids = set(self.owner.active_binding_ids(candidate.proposition_id))
        active_ids = set(candidate.evidence_binding_ids)
        state, event = self.owner.commit_update(proposition_id=candidate.proposition_id,
            expected_predecessor_digest=candidate.predecessor_state_digest,
            stance=candidate.proposed_stance, reason=candidate.reason,
            active_binding_ids=tuple(sorted(active_ids)),
            added_binding_ids=tuple(sorted(active_ids - previous_ids)),
            removed_binding_ids=tuple(sorted(previous_ids - active_ids)), candidate=candidate,
            correlation_id=correlation_id, tick=tick, recorded_at=recorded_at)
        self.owner.verify(); current = self.owner.current_state(candidate.proposition_id)
        events = self.owner.update_events(candidate.proposition_id)
        paired = [item for item in events if item.event_id == event.event_id]
        if (current != state or paired != [event] or event.candidate_id != candidate.candidate_id
                or event.prior_state_digest != candidate.predecessor_state_digest
                or event.successor_state_digest != state.state_digest
                or state.evidence_set_digest != digest(sorted(active_ids))
                or state.generation != (prior.generation + 1 if prior else 0)
                or dict(state.authority) != FALSE_AUTHORITY or dict(event.authority) != FALSE_AUTHORITY):
            raise EpistemicMutationError("state_post_write_verification_failed")
        raw = EpistemicStateMutationReceipt("", "", "epistemic_state_update", candidate.candidate_id,
            candidate.proposition_id, candidate.predecessor_state_digest, state.state_id, state.state_digest,
            event.event_id, event.event_digest, state.evidence_set_digest, state.generation,
            admission.admission_id, admission.binding_digest, PRINCIPAL, operation_id, correlation_id)
        rid, rdigest = _identity("epistemic-mutation-receipt", raw.payload())
        return self._write_receipt("state", replace(raw, receipt_id=rid, receipt_digest=rdigest))
