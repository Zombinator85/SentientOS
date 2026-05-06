from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_adapter_contract import (
    PromptAssemblyAdapterPayload,
    PromptAssemblyAdapterStatus,
    adapter_payload_contains_no_prompt_text,
    adapter_payload_contains_no_raw_payloads,
    adapter_payload_has_no_runtime_authority,
)


class PromptAssemblerComplianceStatus:
    COMPLIANCE_READY_FOR_FUTURE_INTEGRATION = "compliance_ready_for_future_integration"
    COMPLIANCE_READY_WITH_WARNINGS = "compliance_ready_with_warnings"
    COMPLIANCE_BLOCKED = "compliance_blocked"
    COMPLIANCE_NOT_APPLICABLE = "compliance_not_applicable"
    COMPLIANCE_INVALID_ADAPTER_PAYLOAD = "compliance_invalid_adapter_payload"
    COMPLIANCE_RUNTIME_WIRING_DETECTED = "compliance_runtime_wiring_detected"


@dataclass(frozen=True)
class PromptAssemblerComplianceRequirement:
    requirement_id: str
    summary: str
    severity: str = "must"


@dataclass(frozen=True)
class PromptAssemblerFutureIntegrationRule:
    rule_id: str
    must_clause: str


@dataclass(frozen=True)
class PromptAssemblerComplianceGap:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class PromptAssemblerComplianceReport:
    compliance_status: str
    adapter_payload_status: str
    may_future_assembler_consume: bool
    must_block_prompt_materialization: bool
    gaps: tuple[PromptAssemblerComplianceGap, ...] = field(default_factory=tuple)
    warnings: tuple[PromptAssemblerComplianceGap, ...] = field(default_factory=tuple)
    requirements: tuple[PromptAssemblerComplianceRequirement, ...] = field(default_factory=tuple)
    prompt_assembler_static_findings: Mapping[str, Any] = field(default_factory=dict)
    no_runtime_wiring_detected: bool = True
    no_forbidden_context_bypass_detected: bool = True
    rationale: str = ""
    compliance_harness_only: bool = True
    does_not_modify_prompt_assembler: bool = True
    does_not_assemble_prompt: bool = True
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True


_READY_STATUSES = {
    PromptAssemblyAdapterStatus.ADAPTER_READY,
    PromptAssemblyAdapterStatus.ADAPTER_READY_WITH_WARNINGS,
}
_BLOCKING_STATUSES = {
    PromptAssemblyAdapterStatus.ADAPTER_BLOCKED,
    PromptAssemblyAdapterStatus.ADAPTER_NOT_APPLICABLE,
    PromptAssemblyAdapterStatus.ADAPTER_INVALID_VERIFICATION,
    PromptAssemblyAdapterStatus.ADAPTER_INVALID_CANDIDATE_PLAN,
}
_INVALID_STATUSES = {
    PromptAssemblyAdapterStatus.ADAPTER_INVALID_VERIFICATION,
    PromptAssemblyAdapterStatus.ADAPTER_INVALID_CANDIDATE_PLAN,
}
_REQUIRED_IDENTIFIER_FIELDS = ("adapter_payload_id", "candidate_plan_id", "envelope_id", "envelope_digest", "packet_id")
_REQUIRED_NOTE_FIELDS = ("provenance_notes", "privacy_notes", "truth_notes", "safety_notes")
_REQUIRED_NO_RUNTIME_MARKERS = (
    "does_not_call_llm",
    "does_not_retrieve_memory",
    "does_not_write_memory",
    "does_not_trigger_feedback",
    "does_not_commit_retention",
    "does_not_execute_or_route_work",
    "does_not_admit_work",
)
_FORBIDDEN_BYPASS_IMPORTS = (
    "sentientos.context_hygiene.selector",
    "sentientos.context_hygiene.prompt_preflight",
    "sentientos.context_hygiene.prompt_handoff_manifest",
    "sentientos.context_hygiene.prompt_dry_run_envelope",
    "sentientos.context_hygiene.prompt_constraint_verifier",
    "sentientos.context_hygiene.prompt_adapter_contract",
    "sentientos.context_hygiene.context_packet",
)
_CONTEXT_HYGIENE_HELPER_NAMES = (
    "ContextPacket",
    "ContextCandidate",
    "PromptAssemblyAdapterPayload",
    "build_context_packet_from_candidates",
    "select_context_candidates",
    "evaluate_context_packet_prompt_eligibility",
    "build_context_prompt_handoff_manifest",
    "build_context_prompt_dry_run_envelope",
    "verify_prompt_assembly_constraints",
    "build_prompt_assembly_adapter_payload",
)


def _is_dataclass_instance(value: Any) -> bool:
    return is_dataclass(value) and not isinstance(value, type)


def _mapping(value: Any) -> Mapping[str, Any]:
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


def build_prompt_assembler_compliance_requirements() -> tuple[PromptAssemblerComplianceRequirement, ...]:
    return (
        PromptAssemblerComplianceRequirement("adapter_status_ready", "future assembler may consume only adapter_ready or adapter_ready_with_warnings payloads"),
        PromptAssemblerComplianceRequirement("blocked_statuses_withhold_material", "blocked, not-applicable, and invalid adapter payloads must not materialize prompt content"),
        PromptAssemblerComplianceRequirement("adapter_refs_only", "future assembler may consume adapter_refs only and must never consume raw payloads"),
        PromptAssemblerComplianceRequirement("no_prompt_text", "adapter payload must not contain final prompt text or prompt fragments"),
        PromptAssemblerComplianceRequirement("no_runtime_authority", "adapter payload must carry no LLM, memory, routing, admission, execution, feedback, or retention authority"),
        PromptAssemblerComplianceRequirement("non_authoritative", "adapter payload posture must remain non-authoritative"),
        PromptAssemblerComplianceRequirement("boundaries_preserved", "caveats, provenance, privacy, truth, and safety boundaries must be preserved"),
        PromptAssemblerComplianceRequirement("digest_and_ids_present", "adapter digest and packet, envelope, and candidate identifiers must be present"),
        PromptAssemblerComplianceRequirement("static_no_runtime_wiring", "pre-integration prompt_assembler.py must not contain context hygiene runtime wiring or bypasses"),
    )


def _gap(code: str, detail: str, severity: str = "blocker") -> PromptAssemblerComplianceGap:
    return PromptAssemblerComplianceGap(code=code, detail=detail, severity=severity)


def _constraints_include_no_runtime_guards(data: Mapping[str, Any]) -> bool:
    constraints = data.get("assembly_constraints", {})
    constraint_map = dict(constraints) if isinstance(constraints, Mapping) else {}
    return all(data.get(name) is True or constraint_map.get(name) is True for name in _REQUIRED_NO_RUNTIME_MARKERS)


def _adapter_payload_status(data: Mapping[str, Any]) -> str:
    return str(data.get("adapter_status", ""))


def adapter_payload_may_be_consumed_by_future_assembler(payload: PromptAssemblyAdapterPayload | Mapping[str, Any]) -> bool:
    data = _mapping(payload)
    return _adapter_payload_status(data) in _READY_STATUSES and adapter_payload_satisfies_compliance_prerequisites(payload)


def adapter_payload_blocks_prompt_materialization(payload: PromptAssemblyAdapterPayload | Mapping[str, Any]) -> bool:
    data = _mapping(payload)
    status = _adapter_payload_status(data)
    if status in _BLOCKING_STATUSES:
        return True
    return not adapter_payload_satisfies_compliance_prerequisites(payload)


def adapter_payload_satisfies_compliance_prerequisites(payload: PromptAssemblyAdapterPayload | Mapping[str, Any]) -> bool:
    report = evaluate_prompt_assembler_adapter_compliance(payload, prompt_assembler_source="")
    return not report.gaps and report.compliance_status in {
        PromptAssemblerComplianceStatus.COMPLIANCE_READY_FOR_FUTURE_INTEGRATION,
        PromptAssemblerComplianceStatus.COMPLIANCE_READY_WITH_WARNINGS,
    }


def _evaluate_payload(payload: PromptAssemblyAdapterPayload | Mapping[str, Any]) -> tuple[list[PromptAssemblerComplianceGap], list[PromptAssemblerComplianceGap]]:
    data = _mapping(payload)
    gaps: list[PromptAssemblerComplianceGap] = []
    warnings: list[PromptAssemblerComplianceGap] = []
    status = _adapter_payload_status(data)

    if not data:
        return [_gap("invalid_payload_shape", "adapter payload must be a PromptAssemblyAdapterPayload or mapping")], warnings
    if status not in _READY_STATUSES | _BLOCKING_STATUSES:
        gaps.append(_gap("unknown_adapter_status", "adapter payload status is not recognized"))

    if not adapter_payload_contains_no_prompt_text(payload):
        gaps.append(_gap("prompt_text_present", "adapter payload contains prompt_text or final prompt text"))
    if not adapter_payload_contains_no_raw_payloads(payload):
        gaps.append(_gap("raw_payload_present", "adapter payload contains raw payload material"))
    if not adapter_payload_has_no_runtime_authority(payload):
        gaps.append(_gap("runtime_authority_present", "adapter payload contains runtime authority or missing non-effect markers"))

    if data.get("non_authoritative") is not True:
        gaps.append(_gap("non_authoritative_missing", "adapter payload must preserve non_authoritative posture"))
    if data.get("adapter_contract_only") is not True:
        gaps.append(_gap("adapter_contract_only_missing", "adapter payload must remain adapter-contract-only"))
    if not data.get("digest"):
        gaps.append(_gap("digest_missing", "adapter payload digest is required"))
    for field_name in _REQUIRED_IDENTIFIER_FIELDS:
        if not data.get(field_name):
            gaps.append(_gap(f"{field_name}_missing", f"adapter payload requires {field_name}"))

    refs = tuple(data.get("adapter_refs", ()) or ())
    if status in _READY_STATUSES and not refs:
        gaps.append(_gap("adapter_refs_missing_for_ready_status", "ready adapter payloads must expose adapter refs for future assembler consumption"))
    if status in _BLOCKING_STATUSES and refs:
        gaps.append(_gap("adapter_refs_present_for_blocked_status", "blocking adapter statuses must withhold adapter refs"))

    if not _constraints_include_no_runtime_guards(data):
        gaps.append(_gap("no_runtime_constraints_missing", "adapter constraints must include no LLM, memory, feedback, retention, execution, routing, and admission guards"))

    if status in _READY_STATUSES and "preserved_caveats" not in data:
        warnings.append(_gap("caveats_missing", "preserved_caveats should be present even when upstream had none", "warning"))
    for field_name in _REQUIRED_NOTE_FIELDS:
        if field_name not in data or data.get(field_name) in (None, ""):
            warnings.append(_gap(f"{field_name}_missing", f"{field_name} should be preserved when upstream supplied it", "warning"))

    return gaps, warnings


def _imports_from_tree(tree: ast.AST) -> tuple[str, ...]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    return tuple(imports)


def _names_from_tree(tree: ast.AST) -> tuple[str, ...]:
    return tuple(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))


def scan_prompt_assembler_static_findings(
    prompt_assembler_path: str | Path = "prompt_assembler.py", *, source_text: str | None = None
) -> dict[str, Any]:
    if source_text is None:
        path = Path(prompt_assembler_path)
        source_text = path.read_text(encoding="utf-8") if path.exists() else ""
    tree = ast.parse(source_text or "", filename=str(prompt_assembler_path))
    imports = _imports_from_tree(tree)
    names = _names_from_tree(tree)
    imports_context_hygiene_adapter_modules = any("sentientos.context_hygiene" in imp for imp in imports)
    imports_prompt_adapter_contract = any("prompt_adapter_contract" in imp for imp in imports)
    uses_context_packet_directly = "ContextPacket" in names or "ContextPacket" in (source_text or "")
    calls_context_hygiene_helpers = any(name in names for name in _CONTEXT_HYGIENE_HELPER_NAMES)
    bypasses_adapter_contract = any(imp in _FORBIDDEN_BYPASS_IMPORTS for imp in imports) and not imports_prompt_adapter_contract
    retrieves_memory_for_context_hygiene = "context_hygiene" in (source_text or "") and any("memory" in imp for imp in imports)
    calls_llm_for_context_hygiene = "context_hygiene" in (source_text or "") and any(token in (source_text or "") for token in ("openai", "anthropic", "ChatCompletion", "llm"))
    contains_phase70_adapter_payload_usage = "PromptAssemblyAdapterPayload" in names or "build_prompt_assembly_adapter_payload" in names
    active_context_hygiene_runtime_wiring = any(
        (
            imports_context_hygiene_adapter_modules,
            imports_prompt_adapter_contract,
            uses_context_packet_directly,
            calls_context_hygiene_helpers,
            contains_phase70_adapter_payload_usage,
        )
    )
    forbidden_context_bypass_detected = any((bypasses_adapter_contract, retrieves_memory_for_context_hygiene, calls_llm_for_context_hygiene))
    return {
        "imports_context_hygiene_adapter_modules": imports_context_hygiene_adapter_modules,
        "imports_prompt_adapter_contract": imports_prompt_adapter_contract,
        "uses_context_packet_directly": uses_context_packet_directly,
        "calls_selector_preflight_manifest_envelope_verifier_or_adapter_helpers": calls_context_hygiene_helpers,
        "bypasses_adapter_contract_by_reading_context_hygiene_internals": bypasses_adapter_contract,
        "retrieves_memory_directly_for_context_hygiene_purposes": retrieves_memory_for_context_hygiene,
        "calls_llm_provider_apis_for_context_hygiene_purposes": calls_llm_for_context_hygiene,
        "contains_phase70_adapter_payload_usage": contains_phase70_adapter_payload_usage,
        "active_context_hygiene_runtime_wiring": active_context_hygiene_runtime_wiring,
        "forbidden_context_bypass_detected": forbidden_context_bypass_detected,
        "inspection_mode": "source_text_ast_only_no_import",
    }


def prompt_assembler_module_has_no_context_hygiene_runtime_wiring(prompt_assembler_path: str | Path = "prompt_assembler.py") -> bool:
    return not scan_prompt_assembler_static_findings(prompt_assembler_path)["active_context_hygiene_runtime_wiring"]


def prompt_assembler_module_has_no_forbidden_context_bypass(prompt_assembler_path: str | Path = "prompt_assembler.py") -> bool:
    return not scan_prompt_assembler_static_findings(prompt_assembler_path)["forbidden_context_bypass_detected"]


def evaluate_prompt_assembler_adapter_compliance(
    payload: PromptAssemblyAdapterPayload | Mapping[str, Any],
    *,
    prompt_assembler_path: str | Path = "prompt_assembler.py",
    prompt_assembler_source: str | None = None,
) -> PromptAssemblerComplianceReport:
    data = _mapping(payload)
    payload_status = _adapter_payload_status(data)
    gaps, warnings = _evaluate_payload(payload)
    findings = scan_prompt_assembler_static_findings(prompt_assembler_path, source_text=prompt_assembler_source)
    no_runtime_wiring = not findings["active_context_hygiene_runtime_wiring"]
    no_bypass = not findings["forbidden_context_bypass_detected"]
    if not no_bypass:
        gaps.append(_gap("forbidden_context_bypass_detected", "prompt_assembler.py appears to bypass context hygiene adapter contract"))
    if findings["active_context_hygiene_runtime_wiring"]:
        gaps.append(_gap("context_hygiene_runtime_wiring_detected", "prompt_assembler.py contains active context hygiene wiring"))

    if not no_bypass or findings["active_context_hygiene_runtime_wiring"]:
        status = PromptAssemblerComplianceStatus.COMPLIANCE_RUNTIME_WIRING_DETECTED
    elif payload_status in _INVALID_STATUSES or any(g.code.startswith("invalid") for g in gaps):
        status = PromptAssemblerComplianceStatus.COMPLIANCE_INVALID_ADAPTER_PAYLOAD
    elif payload_status == PromptAssemblyAdapterStatus.ADAPTER_NOT_APPLICABLE and not gaps:
        status = PromptAssemblerComplianceStatus.COMPLIANCE_NOT_APPLICABLE
    elif payload_status in _BLOCKING_STATUSES or gaps:
        status = PromptAssemblerComplianceStatus.COMPLIANCE_BLOCKED
    elif payload_status == PromptAssemblyAdapterStatus.ADAPTER_READY_WITH_WARNINGS or warnings or data.get("warnings"):
        status = PromptAssemblerComplianceStatus.COMPLIANCE_READY_WITH_WARNINGS
    else:
        status = PromptAssemblerComplianceStatus.COMPLIANCE_READY_FOR_FUTURE_INTEGRATION

    may_consume = status in {
        PromptAssemblerComplianceStatus.COMPLIANCE_READY_FOR_FUTURE_INTEGRATION,
        PromptAssemblerComplianceStatus.COMPLIANCE_READY_WITH_WARNINGS,
    }
    must_block = not may_consume
    rationale = "future assembler may consume adapter_refs only" if may_consume else "prompt materialization must be blocked before future assembler consumption"
    return PromptAssemblerComplianceReport(
        compliance_status=status,
        adapter_payload_status=payload_status,
        may_future_assembler_consume=may_consume,
        must_block_prompt_materialization=must_block,
        gaps=tuple(gaps),
        warnings=tuple(warnings),
        requirements=build_prompt_assembler_compliance_requirements(),
        prompt_assembler_static_findings=findings,
        no_runtime_wiring_detected=no_runtime_wiring,
        no_forbidden_context_bypass_detected=no_bypass,
        rationale=rationale,
    )


def explain_prompt_assembler_compliance_gaps(report: PromptAssemblerComplianceReport) -> tuple[str, ...]:
    return tuple(f"{gap.severity}:{gap.code}:{gap.detail}" for gap in report.gaps)


def summarize_prompt_assembler_compliance_report(report: PromptAssemblerComplianceReport) -> dict[str, Any]:
    return {
        "compliance_status": report.compliance_status,
        "adapter_payload_status": report.adapter_payload_status,
        "may_future_assembler_consume": report.may_future_assembler_consume,
        "must_block_prompt_materialization": report.must_block_prompt_materialization,
        "gap_count": len(report.gaps),
        "warning_count": len(report.warnings),
        "no_runtime_wiring_detected": report.no_runtime_wiring_detected,
        "no_forbidden_context_bypass_detected": report.no_forbidden_context_bypass_detected,
        "rationale": report.rationale,
        "compliance_harness_only": report.compliance_harness_only,
    }


def summarize_future_prompt_assembler_integration_contract() -> tuple[PromptAssemblerFutureIntegrationRule, ...]:
    return (
        PromptAssemblerFutureIntegrationRule("accept_only_adapter_payload", "MUST accept only PromptAssemblyAdapterPayload"),
        PromptAssemblerFutureIntegrationRule("reject_non_ready_statuses", "MUST reject adapter statuses other than adapter_ready / adapter_ready_with_warnings"),
        PromptAssemblerFutureIntegrationRule("consume_only_adapter_refs", "MUST consume only adapter_refs"),
        PromptAssemblerFutureIntegrationRule("preserve_boundary_notes", "MUST preserve caveats/provenance/privacy/truth/safety notes"),
        PromptAssemblerFutureIntegrationRule("no_raw_payloads", "MUST never include raw payloads"),
        PromptAssemblerFutureIntegrationRule("non_authoritative", "MUST never treat adapter payload as authoritative"),
        PromptAssemblerFutureIntegrationRule("no_bypass_context", "MUST not retrieve bypass context"),
        PromptAssemblerFutureIntegrationRule("no_bypass_phase69", "MUST not bypass Phase 69 verifier"),
        PromptAssemblerFutureIntegrationRule("no_bypass_phase68", "MUST not bypass Phase 68 envelope"),
        PromptAssemblerFutureIntegrationRule("no_bypass_phase64", "MUST not bypass Phase 64 preflight"),
        PromptAssemblerFutureIntegrationRule("no_bypass_phase62", "MUST not bypass Phase 62 selector"),
        PromptAssemblerFutureIntegrationRule("blocked_refs_not_visible", "MUST not make blocked refs prompt-visible"),
        PromptAssemblerFutureIntegrationRule("record_compliance_before_materialization", "MUST emit/record compliance outcome before materialization in a future phase"),
    )
