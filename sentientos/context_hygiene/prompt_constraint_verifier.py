from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_dry_run_envelope import (
    ContextPromptDryRunEnvelope,
    ContextPromptDryRunRefSummary,
    ContextPromptDryRunStatus,
)


class PromptAssemblyConstraintVerificationStatus:
    CONSTRAINT_VERIFIED = "constraint_verified"
    CONSTRAINT_VERIFIED_WITH_WARNINGS = "constraint_verified_with_warnings"
    CONSTRAINT_FAILED = "constraint_failed"
    CONSTRAINT_NOT_APPLICABLE = "constraint_not_applicable"
    CONSTRAINT_INVALID_ENVELOPE = "constraint_invalid_envelope"
    CONSTRAINT_INVALID_CANDIDATE_PLAN = "constraint_invalid_candidate_plan"


@dataclass(frozen=True)
class PromptAssemblyConstraintViolation:
    code: str
    detail: str
    ref_id: str = ""


@dataclass(frozen=True)
class PromptAssemblyConstraintWarning:
    code: str
    detail: str
    ref_id: str = ""


@dataclass(frozen=True)
class PromptAssemblyCandidateRef:
    ref_id: str
    ref_type: str
    lane: str
    content_summary: str
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)
    provenance_status: str = ""
    source_kind: str = ""
    privacy_posture: str = ""
    pollution_risk: str = ""
    freshness_status: str = ""
    contradiction_status: str = ""
    caveats: tuple[str, ...] = field(default_factory=tuple)
    safety_summary: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptAssemblyCandidatePlan:
    plan_id: str
    envelope_id: str
    envelope_digest: str
    packet_id: str
    packet_scope: str
    intended_ref_ids: tuple[str, ...]
    candidate_refs: tuple[PromptAssemblyCandidateRef, ...]
    preserved_caveats: tuple[str, ...] = field(default_factory=tuple)
    preserved_constraints: Mapping[str, Any] = field(default_factory=dict)
    provenance_notes: Mapping[str, Any] = field(default_factory=dict)
    safety_notes: Mapping[str, Any] = field(default_factory=dict)
    truth_notes: Mapping[str, Any] = field(default_factory=dict)
    privacy_notes: Mapping[str, Any] = field(default_factory=dict)
    non_authoritative: bool = True
    no_runtime_markers: Mapping[str, bool] = field(default_factory=dict)
    diagnostic_markers: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptAssemblyConstraintVerification:
    status: str
    envelope_id: str
    plan_id: str
    violations: tuple[PromptAssemblyConstraintViolation, ...] = field(default_factory=tuple)
    warnings: tuple[PromptAssemblyConstraintWarning, ...] = field(default_factory=tuple)
    checked_ref_ids: tuple[str, ...] = field(default_factory=tuple)
    rationale: str = ""


_READY_STATUSES = {
    ContextPromptDryRunStatus.DRY_RUN_READY,
    ContextPromptDryRunStatus.DRY_RUN_READY_WITH_CAVEATS,
}
_BLOCKED_STATUSES = {ContextPromptDryRunStatus.DRY_RUN_BLOCKED}
_NOT_APPLICABLE_STATUSES = {ContextPromptDryRunStatus.DRY_RUN_NOT_APPLICABLE}
_INVALID_STATUSES = {ContextPromptDryRunStatus.DRY_RUN_INVALID_MANIFEST}

_FORBIDDEN_RAW_KEYS = frozenset(
    {
        "raw_payload",
        "raw_memory_payload",
        "raw_screen_payload",
        "raw_audio_payload",
        "raw_vision_payload",
        "raw_multimodal_payload",
        "screen_frame",
        "mic_audio",
        "audio_payload",
        "vision_frame",
        "multimodal_raw_data",
        "browser_control_data",
        "mouse_control_data",
        "keyboard_control_data",
        "hidden_chain_of_thought",
        "chain_of_thought",
    }
)
_FORBIDDEN_PROMPT_TEXT_KEYS = frozenset({"prompt_text", "final_prompt_text", "assembled_prompt", "rendered_prompt", "system_prompt", "developer_prompt"})
_FORBIDDEN_LLM_KEYS = frozenset({"llm_params", "llm_parameters", "model_params", "provider_params", "model", "temperature", "max_tokens", "tool_choice"})
_RUNTIME_HANDLE_KEYS = frozenset({"execution_handle", "action_handle", "retention_handle", "retrieval_handle", "browser_handle", "mouse_handle", "keyboard_handle"})
_MEMORY_WRITE_KEYS = frozenset({"memory_write", "can_write_memory", "write_memory", "memory_write_capability"})
_RETENTION_KEYS = frozenset({"retention_commit", "can_commit_retention", "commit_retention", "retention_commit_capability"})
_FEEDBACK_KEYS = frozenset({"feedback_trigger", "can_trigger_feedback", "trigger_feedback", "feedback_trigger_capability"})
_ACTION_KEYS = frozenset({"execute_action", "action_execution", "can_execute_action", "action_execution_capability"})
_ROUTE_ADMIT_KEYS = frozenset({"route_work", "admit_work", "execute_work", "can_route_work", "can_admit_work", "can_execute_work", "can_fulfill_work", "can_route", "can_admit", "can_execute"})
_RUNTIME_AUTHORITY_KEYS = _RUNTIME_HANDLE_KEYS | _MEMORY_WRITE_KEYS | _RETENTION_KEYS | _FEEDBACK_KEYS | _ACTION_KEYS | _ROUTE_ADMIT_KEYS
_REQUIRED_NO_RUNTIME_MARKERS = (
    "does_not_assemble_prompt",
    "does_not_contain_final_prompt_text",
    "does_not_call_llm",
    "does_not_retrieve_memory",
    "does_not_write_memory",
    "does_not_trigger_feedback",
    "does_not_commit_retention",
    "does_not_execute_or_route_work",
    "does_not_admit_work",
)


def _is_dataclass_instance(value: Any) -> bool:
    return is_dataclass(value) and not isinstance(value, type)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if _is_dataclass_instance(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return value
    return {}


def _walk(value: Any) -> Sequence[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []

    def rec(child: Any) -> None:
        if _is_dataclass_instance(child):
            rec(asdict(child))
        elif isinstance(child, Mapping):
            for key, nested in child.items():
                found.append((str(key), nested))
                rec(nested)
        elif isinstance(child, (tuple, list, set, frozenset)):
            for nested in child:
                rec(nested)

    rec(value)
    return tuple(found)


def _truthy_forbidden(value: Any) -> bool:
    return bool(value)


def _violation(code: str, detail: str, ref_id: str = "") -> PromptAssemblyConstraintViolation:
    return PromptAssemblyConstraintViolation(code=code, detail=detail, ref_id=ref_id)


def _warning(code: str, detail: str, ref_id: str = "") -> PromptAssemblyConstraintWarning:
    return PromptAssemblyConstraintWarning(code=code, detail=detail, ref_id=ref_id)


def _ref_from_dry_run_summary(ref: ContextPromptDryRunRefSummary) -> PromptAssemblyCandidateRef:
    return PromptAssemblyCandidateRef(
        ref_id=ref.ref_id,
        ref_type=ref.ref_type,
        lane=ref.lane,
        content_summary=ref.content_summary,
        provenance_refs=tuple(ref.provenance_refs),
        provenance_status=ref.provenance_status,
        source_kind=ref.source_kind,
        privacy_posture=ref.privacy_posture,
        pollution_risk=ref.pollution_risk,
        freshness_status=ref.freshness_status,
        contradiction_status=ref.contradiction_status,
        caveats=tuple(ref.caveats),
        safety_summary=dict(ref.safety_metadata_summary),
    )


def _default_no_runtime_markers() -> dict[str, bool]:
    return {name: True for name in _REQUIRED_NO_RUNTIME_MARKERS}


def build_candidate_plan_from_dry_run_envelope(envelope: ContextPromptDryRunEnvelope) -> PromptAssemblyCandidatePlan:
    candidate_refs: tuple[PromptAssemblyCandidateRef, ...] = ()
    if envelope.dry_run_status in _READY_STATUSES:
        candidate_refs = tuple(_ref_from_dry_run_summary(ref) for ref in envelope.admissible_ref_summaries)
    return PromptAssemblyCandidatePlan(
        plan_id=f"candidate-plan:{envelope.envelope_id}",
        envelope_id=envelope.envelope_id,
        envelope_digest=envelope.digest,
        packet_id=envelope.packet_id,
        packet_scope=envelope.packet_scope,
        intended_ref_ids=tuple(ref.ref_id for ref in candidate_refs),
        candidate_refs=candidate_refs,
        preserved_caveats=tuple(envelope.caveats),
        preserved_constraints=dict(envelope.assembly_constraints),
        provenance_notes={"summary": envelope.provenance_summary},
        safety_notes={"safety_contract_gap_summary": tuple(envelope.safety_contract_gap_summary)},
        truth_notes={"block_reasons": tuple(envelope.block_reasons), "caveats": tuple(envelope.caveats)},
        privacy_notes={"packet_scope": envelope.packet_scope},
        non_authoritative=True,
        no_runtime_markers=_default_no_runtime_markers(),
        diagnostic_markers={
            "dry_run_status": envelope.dry_run_status,
            "block_reasons": tuple(envelope.block_reasons),
            "source_kind_summary": dict(envelope.source_kind_summary),
        },
    )


def _candidate_ref_mapping(ref: PromptAssemblyCandidateRef | Mapping[str, Any]) -> Mapping[str, Any]:
    return _as_mapping(ref)


def _candidate_ref_id(ref: PromptAssemblyCandidateRef | Mapping[str, Any]) -> str:
    return str(_candidate_ref_mapping(ref).get("ref_id", ""))


def candidate_plan_contains_no_raw_payloads(candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> bool:
    return not any(key in _FORBIDDEN_RAW_KEYS for key, _ in _walk(candidate_plan))


def candidate_plan_contains_no_prompt_text(candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> bool:
    return not any(key in _FORBIDDEN_PROMPT_TEXT_KEYS for key, _ in _walk(candidate_plan))


def _contains_truthy_key(candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any], keys: frozenset[str]) -> bool:
    return any(key in keys and _truthy_forbidden(value) for key, value in _walk(candidate_plan))


def candidate_plan_has_no_runtime_authority(candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> bool:
    return not _contains_truthy_key(candidate_plan, _RUNTIME_AUTHORITY_KEYS)


def _candidate_refs(candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> tuple[PromptAssemblyCandidateRef | Mapping[str, Any], ...]:
    mapping = _as_mapping(candidate_plan)
    refs = mapping.get("candidate_refs", ())
    if isinstance(refs, tuple):
        return refs
    if isinstance(refs, list):
        return tuple(refs)
    return ()


def _candidate_ids(candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(_candidate_ref_id(ref) for ref in _candidate_refs(candidate_plan))


def _admissible_by_id(envelope: ContextPromptDryRunEnvelope) -> dict[str, ContextPromptDryRunRefSummary]:
    return {ref.ref_id: ref for ref in envelope.admissible_ref_summaries}


def _constraint_items(envelope: ContextPromptDryRunEnvelope) -> tuple[tuple[str, Any], ...]:
    return tuple((str(k), v) for k, v in envelope.assembly_constraints.items())


def candidate_plan_uses_only_admissible_refs(envelope: ContextPromptDryRunEnvelope, candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> bool:
    admissible = set(_admissible_by_id(envelope))
    return all(ref_id in admissible for ref_id in _candidate_ids(candidate_plan))


def candidate_plan_preserves_required_caveats(envelope: ContextPromptDryRunEnvelope, candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> bool:
    plan = _as_mapping(candidate_plan)
    preserved = set(plan.get("preserved_caveats", ()))
    required = set(envelope.caveats)
    for ref in envelope.admissible_ref_summaries:
        required.update(ref.caveats)
    return required.issubset(preserved)


def candidate_plan_preserves_provenance_boundaries(envelope: ContextPromptDryRunEnvelope, candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> bool:
    admissible = _admissible_by_id(envelope)
    for ref in _candidate_refs(candidate_plan):
        mapping = _candidate_ref_mapping(ref)
        expected = admissible.get(str(mapping.get("ref_id", "")))
        if expected is None:
            continue
        if tuple(mapping.get("provenance_refs", ())) != tuple(expected.provenance_refs):
            return False
        if str(mapping.get("provenance_status", "")) != expected.provenance_status:
            return False
    return True


def candidate_plan_preserves_safety_constraints(envelope: ContextPromptDryRunEnvelope, candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> bool:
    admissible = _admissible_by_id(envelope)
    for ref in _candidate_refs(candidate_plan):
        mapping = _candidate_ref_mapping(ref)
        expected = admissible.get(str(mapping.get("ref_id", "")))
        if expected is None:
            continue
        if str(mapping.get("source_kind", "")) != expected.source_kind:
            return False
        if dict(mapping.get("safety_summary", {})) != dict(expected.safety_metadata_summary):
            return False
    return True


def _plan_shape_is_valid(candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> bool:
    mapping = _as_mapping(candidate_plan)
    required = {"plan_id", "envelope_id", "envelope_digest", "packet_id", "packet_scope", "candidate_refs", "intended_ref_ids"}
    if not required.issubset(mapping):
        return False
    refs = mapping.get("candidate_refs")
    if not isinstance(refs, (tuple, list)):
        return False
    return all("ref_id" in _candidate_ref_mapping(ref) for ref in refs)


def _specific_capability_violations(candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> tuple[PromptAssemblyConstraintViolation, ...]:
    checks = (
        (_FORBIDDEN_RAW_KEYS, "raw_payload_present", False),
        (_FORBIDDEN_PROMPT_TEXT_KEYS, "final_prompt_text_present", False),
        (_FORBIDDEN_LLM_KEYS, "llm_call_parameters_present", True),
        (_RUNTIME_HANDLE_KEYS, "runtime_authority_present", True),
        (_MEMORY_WRITE_KEYS, "memory_write_capability_present", True),
        (_RETENTION_KEYS, "retention_commit_capability_present", True),
        (_FEEDBACK_KEYS, "feedback_trigger_capability_present", True),
        (_ACTION_KEYS, "action_execution_capability_present", True),
        (_ROUTE_ADMIT_KEYS, "route_or_admit_capability_present", True),
    )
    out: list[PromptAssemblyConstraintViolation] = []
    walked = _walk(candidate_plan)
    for keys, code, require_truthy in checks:
        for key, value in walked:
            if key in keys and ((not require_truthy) or _truthy_forbidden(value)):
                out.append(_violation(code, f"candidate plan includes forbidden key {key}"))
                break
    return tuple(out)


def _id_set_from_constraints(envelope: ContextPromptDryRunEnvelope, name: str) -> set[str]:
    value = envelope.assembly_constraints.get(name, ())
    if isinstance(value, str):
        return {value}
    if isinstance(value, (tuple, list, set, frozenset)):
        return {str(v) for v in value}
    return set()


def _missing_boundaries(envelope: ContextPromptDryRunEnvelope, candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> tuple[PromptAssemblyConstraintViolation, ...]:
    out: list[PromptAssemblyConstraintViolation] = []
    plan = _as_mapping(candidate_plan)
    preserved_constraints = dict(plan.get("preserved_constraints", {}))
    for key, value in _constraint_items(envelope):
        if key not in preserved_constraints or preserved_constraints[key] != value:
            out.append(_violation("assembly_constraint_missing", f"assembly constraint {key} was not preserved"))
            break
    if not candidate_plan_preserves_required_caveats(envelope, candidate_plan):
        out.append(_violation("required_caveat_missing", "candidate plan does not preserve every envelope/ref caveat"))
    if not candidate_plan_preserves_provenance_boundaries(envelope, candidate_plan):
        out.append(_violation("provenance_boundary_missing", "candidate ref provenance refs/status changed or missing"))

    admissible = _admissible_by_id(envelope)
    preserved_caveats = set(plan.get("preserved_caveats", ()))
    for ref in _candidate_refs(candidate_plan):
        mapping = _candidate_ref_mapping(ref)
        ref_id = str(mapping.get("ref_id", ""))
        expected = admissible.get(ref_id)
        if expected is None:
            continue
        if str(mapping.get("privacy_posture", "")) != expected.privacy_posture:
            out.append(_violation("privacy_boundary_missing", "candidate ref privacy posture changed or missing", ref_id))
        expected_truth = {c for c in tuple(expected.caveats) + tuple(envelope.caveats) if "truth" in c.lower() or "contradict" in c.lower()}
        if expected.contradiction_status and expected.contradiction_status.lower() not in {"", "unknown", "clear", "none"}:
            if str(mapping.get("contradiction_status", "")) != expected.contradiction_status:
                out.append(_violation("truth_boundary_missing", "candidate ref contradiction status changed or missing", ref_id))
        if expected_truth and not expected_truth.issubset(preserved_caveats):
            out.append(_violation("truth_boundary_missing", "truth/contradiction caveat not preserved", ref_id))
        if str(mapping.get("source_kind", "")) != expected.source_kind or dict(mapping.get("safety_summary", {})) != dict(expected.safety_metadata_summary):
            out.append(_violation("safety_boundary_missing", "candidate ref source kind or safety summary changed or missing", ref_id))
    return tuple(out)


def verify_prompt_assembly_candidate_plan(envelope: ContextPromptDryRunEnvelope, candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> PromptAssemblyConstraintVerification:
    return verify_prompt_assembly_constraints(envelope, candidate_plan)


def verify_prompt_assembly_constraints(envelope: ContextPromptDryRunEnvelope, candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> PromptAssemblyConstraintVerification:
    plan = _as_mapping(candidate_plan)
    plan_id = str(plan.get("plan_id", ""))
    if envelope.dry_run_status in _INVALID_STATUSES:
        base_invalid = True
    else:
        base_invalid = False
    if not _plan_shape_is_valid(candidate_plan):
        return PromptAssemblyConstraintVerification(
            status=PromptAssemblyConstraintVerificationStatus.CONSTRAINT_INVALID_CANDIDATE_PLAN,
            envelope_id=envelope.envelope_id,
            plan_id=plan_id,
            violations=(_violation("invalid_candidate_plan", "candidate plan is missing required non-runtime fields"),),
            rationale="candidate plan shape is invalid",
        )

    violations: list[PromptAssemblyConstraintViolation] = []
    warnings: list[PromptAssemblyConstraintWarning] = []
    candidate_ids = _candidate_ids(candidate_plan)
    admissible = set(_admissible_by_id(envelope))
    excluded = _id_set_from_constraints(envelope, "excluded_ref_ids")
    blocked = _id_set_from_constraints(envelope, "blocked_ref_ids")

    if plan.get("envelope_id") != envelope.envelope_id:
        violations.append(_violation("envelope_identity_mismatch", "candidate plan envelope_id does not match envelope"))
    if plan.get("envelope_digest") != envelope.digest:
        violations.append(_violation("envelope_digest_mismatch", "candidate plan envelope_digest does not match envelope digest"))
    if plan.get("packet_id") != envelope.packet_id:
        violations.append(_violation("packet_identity_mismatch", "candidate plan packet_id does not match envelope packet_id"))

    if envelope.dry_run_status in _BLOCKED_STATUSES and candidate_ids:
        violations.append(_violation("blocked_envelope_has_candidate_refs", "blocked dry-run envelope cannot admit candidate refs"))
    if envelope.dry_run_status in _NOT_APPLICABLE_STATUSES and candidate_ids:
        violations.append(_violation("non_applicable_envelope_has_candidate_refs", "not-applicable dry-run envelope cannot admit candidate refs"))
    if envelope.dry_run_status in _INVALID_STATUSES and candidate_ids:
        violations.append(_violation("invalid_envelope_has_candidate_refs", "invalid dry-run envelope cannot admit candidate refs"))

    for ref in _candidate_refs(candidate_plan):
        mapping = _candidate_ref_mapping(ref)
        ref_id = str(mapping.get("ref_id", ""))
        if ref_id in excluded or mapping.get("excluded") is True or "excluded" in tuple(mapping.get("caveats", ())):
            violations.append(_violation("excluded_ref_used", "candidate plan uses an excluded ref", ref_id))
        if ref_id in blocked or str(mapping.get("pollution_risk", "")).lower() == "blocked" or mapping.get("blocked") is True:
            violations.append(_violation("blocked_ref_used", "candidate plan uses a blocked ref", ref_id))
        if ref_id not in admissible:
            violations.append(_violation("non_admissible_ref_used", "candidate ref is not in envelope admissible refs", ref_id))
            if ref_id not in excluded and ref_id not in blocked:
                violations.append(_violation("unknown_ref_used", "candidate ref is unknown to the dry-run envelope", ref_id))

    violations.extend(_missing_boundaries(envelope, candidate_plan))
    violations.extend(_specific_capability_violations(candidate_plan))

    if plan.get("non_authoritative") is not True:
        violations.append(_violation("non_authoritative_marker_missing", "candidate plan must be explicitly non-authoritative"))
    markers = plan.get("no_runtime_markers", {})
    if not isinstance(markers, Mapping) or any(markers.get(name) is not True for name in _REQUIRED_NO_RUNTIME_MARKERS):
        violations.append(_violation("runtime_authority_present", "candidate plan is missing no-runtime markers"))

    if envelope.dry_run_status == ContextPromptDryRunStatus.DRY_RUN_READY_WITH_CAVEATS and not violations:
        warnings.append(_warning("caveated_dry_run_envelope", "dry-run envelope is caveated; preserved caveats remain required"))
    if envelope.block_reasons and envelope.dry_run_status in _BLOCKED_STATUSES and not candidate_ids and not violations:
        warnings.append(_warning("blocked_envelope_no_candidate_refs", "blocked dry-run envelope withheld candidate refs"))

    if base_invalid:
        status = PromptAssemblyConstraintVerificationStatus.CONSTRAINT_INVALID_ENVELOPE
    elif violations:
        status = PromptAssemblyConstraintVerificationStatus.CONSTRAINT_FAILED
    elif envelope.dry_run_status in _NOT_APPLICABLE_STATUSES or envelope.dry_run_status in _BLOCKED_STATUSES:
        status = PromptAssemblyConstraintVerificationStatus.CONSTRAINT_NOT_APPLICABLE
    elif warnings or envelope.dry_run_status == ContextPromptDryRunStatus.DRY_RUN_READY_WITH_CAVEATS:
        status = PromptAssemblyConstraintVerificationStatus.CONSTRAINT_VERIFIED_WITH_WARNINGS
    else:
        status = PromptAssemblyConstraintVerificationStatus.CONSTRAINT_VERIFIED

    return PromptAssemblyConstraintVerification(
        status=status,
        envelope_id=envelope.envelope_id,
        plan_id=plan_id,
        violations=tuple(violations),
        warnings=tuple(warnings),
        checked_ref_ids=tuple(candidate_ids),
        rationale=summarize_prompt_assembly_constraint_verification_status(status, tuple(violations), tuple(warnings)),
    )


def summarize_prompt_assembly_constraint_verification_status(
    status: str,
    violations: tuple[PromptAssemblyConstraintViolation, ...],
    warnings: tuple[PromptAssemblyConstraintWarning, ...],
) -> str:
    if violations:
        return f"{status}: {len(violations)} violation(s)"
    if warnings:
        return f"{status}: {len(warnings)} warning(s)"
    return status


def explain_prompt_assembly_constraint_violations(verification: PromptAssemblyConstraintVerification) -> tuple[str, ...]:
    return tuple(f"{v.code}:{v.ref_id}:{v.detail}" if v.ref_id else f"{v.code}:{v.detail}" for v in verification.violations)


def summarize_prompt_assembly_constraint_verification(verification: PromptAssemblyConstraintVerification) -> dict[str, Any]:
    return {
        "status": verification.status,
        "envelope_id": verification.envelope_id,
        "plan_id": verification.plan_id,
        "violation_codes": tuple(v.code for v in verification.violations),
        "warning_codes": tuple(w.code for w in verification.warnings),
        "checked_ref_ids": verification.checked_ref_ids,
        "rationale": verification.rationale,
    }
