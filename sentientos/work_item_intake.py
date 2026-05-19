"""Metadata-only task/work-item intake adapter for SentientOS.

This module normalizes external task metadata into a deterministic local packet.
It does not call network services, providers, shell/subprocess surfaces, workspace
lifecycle helpers, or execution helpers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Mapping, Sequence

WORK_ITEM_SOURCE_KINDS = frozenset({
    "generic_issue",
    "github_issue_metadata",
    "github_pr_metadata",
    "linear_issue_metadata",
    "codex_task_metadata",
    "manual_operator_task",
})

INTAKE_STATUSES = frozenset({
    "intake_accepted",
    "intake_accepted_with_warnings",
    "intake_blocked",
    "intake_contradicted",
    "intake_insufficient_metadata",
})

RISK_CLASSES = frozenset({
    "informational",
    "documentation_only",
    "bounded_workspace_change",
    "code_change_requires_review",
    "authority_expansion_requested",
    "external_integration_requested",
    "unsafe_or_unbounded_request",
    "insufficient_metadata",
})

BLOCKING_AUTHORITIES = frozenset({
    "network",
    "provider",
    "prompt_export",
    "subprocess",
    "shell",
    "service_control",
    "package_install",
    "hardware_control",
    "issue_mutation",
    "pr_creation",
    "branch_creation",
    "scheduling",
    "workspace_execution",
})

REVIEW_GATED_AUTHORITIES = frozenset({"filesystem_write", "agent_execution"})

EXPLICIT_NON_AUTHORITY_BOUNDARIES: tuple[str, ...] = (
    "metadata_only_intake",
    "no_live_issue_tracker_integration",
    "no_scheduler",
    "no_agent_execution",
    "no_workspace_creation",
    "no_branch_creation",
    "no_pr_creation",
    "no_network_access",
    "no_provider_invocation",
    "no_workspace_file_execution",
    "no_prompt_assembly_or_export",
)


@dataclass(frozen=True)
class WorkItemIntakePolicy:
    metadata_only: bool = True
    allow_workspace_proposal_derivation: bool = True
    require_title_description_outcome: bool = True


@dataclass(frozen=True)
class WorkItemSourceMetadata:
    source_kind: str
    source_ref: str = ""
    tracker_project: str = ""


@dataclass(frozen=True)
class WorkItemIntakeRequest:
    source: WorkItemSourceMetadata
    title: str = ""
    description: str = ""
    requested_outcome: str = ""
    acceptance_criteria: tuple[str, ...] = ()
    declared_constraints: tuple[str, ...] = ()
    declared_authority_requests: tuple[str, ...] = ()
    declared_targets: tuple[str, ...] = ()
    declared_tests: tuple[str, ...] = ()
    agent_execution_requested: bool = False
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkItemIntakeDecision:
    intake_status: str
    risk_class: str
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]


@dataclass(frozen=True)
class NormalizedWorkItemPacket:
    work_item_id: str
    source_kind: str
    source_ref: str
    title: str
    description_summary: str
    requested_outcome: str
    acceptance_criteria: tuple[str, ...]
    declared_constraints: tuple[str, ...]
    declared_authority_requests: tuple[str, ...]
    declared_targets: tuple[str, ...]
    declared_tests: tuple[str, ...]
    risk_class: str
    intake_status: str
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    workspace_change_set_admission_may_be_attempted: bool
    agent_execution_is_requested: bool
    agent_execution_is_permitted_by_this_packet: bool
    explicit_non_authority_boundaries: tuple[str, ...] = EXPLICIT_NON_AUTHORITY_BOUNDARIES
    workspace_change_set_proposal_metadata: Mapping[str, Any] | None = None


def _compact(text: str, *, max_len: int = 220) -> str:
    compact = " ".join(text.strip().split())
    return compact[:max_len]


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({v.strip() for v in values if v.strip()}))


def _extract_tuple(payload: Mapping[str, Any], keys: Sequence[str]) -> tuple[str, ...]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return _unique([str(v) for v in value])
    return ()


def _extract_text(payload: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _derive_workspace_proposal(targets: tuple[str, ...], payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if not targets:
        return None
    return {
        "proposal_kind": "workspace_change_set_proposal_metadata_only",
        "declared_targets": list(targets),
        "change_intent": _compact(_extract_text(payload, ("change_intent", "patch_intent", "workspace_change_intent"))),
        "proposal_requires_admission": True,
        "admission_not_invoked": True,
    }


def normalize_work_item_intake(
    payload: Mapping[str, Any],
    *,
    policy: WorkItemIntakePolicy | None = None,
    derive_workspace_proposal: bool = False,
) -> tuple[NormalizedWorkItemPacket, WorkItemIntakeDecision]:
    chosen_policy = policy or WorkItemIntakePolicy()
    source_kind = str(payload.get("source_kind", "")).strip()
    blockers: list[str] = []
    warnings: list[str] = []

    if source_kind not in WORK_ITEM_SOURCE_KINDS:
        blockers.append("unknown_source_kind")

    title = _extract_text(payload, ("title", "issue_title", "task_title"))
    description = _extract_text(payload, ("description", "body", "summary", "task_description"))
    outcome = _extract_text(payload, ("requested_outcome", "outcome", "goal"))
    source_ref = _extract_text(payload, ("source_ref", "external_ref", "issue_ref", "id"))

    acceptance = _extract_tuple(payload, ("acceptance_criteria", "acceptance", "criteria"))
    constraints = _extract_tuple(payload, ("declared_constraints", "constraints"))
    authorities = _extract_tuple(payload, ("declared_authority_requests", "authority_requests", "requested_authorities"))
    targets = _extract_tuple(payload, ("declared_targets", "files", "target_files", "workspace_targets"))
    tests = _extract_tuple(payload, ("declared_tests", "validation_expectations", "tests"))

    if chosen_policy.require_title_description_outcome:
        if not title:
            blockers.append("missing_title")
        if not description:
            blockers.append("missing_description")
        if not outcome:
            blockers.append("missing_requested_outcome")

    if not acceptance:
        warnings.append("acceptance_criteria_missing")

    blocking_requested = sorted(a for a in authorities if a in BLOCKING_AUTHORITIES)
    if blocking_requested:
        blockers.extend(f"authority_blocked_{a}" for a in blocking_requested)
    gated_requested = sorted(a for a in authorities if a in REVIEW_GATED_AUTHORITIES)
    if gated_requested:
        warnings.extend(f"authority_review_required_{a}" for a in gated_requested)

    agent_execution_requested = bool(payload.get("agent_execution_requested", False) or "agent_execution" in authorities)

    if blockers and any(x in blockers for x in ("missing_title", "missing_description", "missing_requested_outcome")):
        intake_status = "intake_insufficient_metadata"
        risk_class = "insufficient_metadata"
    elif blockers and "unknown_source_kind" in blockers:
        intake_status = "intake_contradicted"
        risk_class = "unsafe_or_unbounded_request"
    elif blockers:
        intake_status = "intake_blocked"
        risk_class = "authority_expansion_requested"
    elif warnings:
        intake_status = "intake_accepted_with_warnings"
        risk_class = "code_change_requires_review" if targets else "informational"
    else:
        intake_status = "intake_accepted"
        risk_class = "bounded_workspace_change" if targets else "documentation_only"

    if any(a in authorities for a in ("network", "provider", "prompt_export")):
        risk_class = "external_integration_requested"

    can_attempt_admission = bool(targets) and intake_status in {"intake_accepted", "intake_accepted_with_warnings"}
    proposal = _derive_workspace_proposal(targets, payload) if derive_workspace_proposal else None

    packet_seed = json.dumps(
        {
            "source_kind": source_kind,
            "source_ref": source_ref,
            "title": title,
            "requested_outcome": outcome,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    work_item_id = "wi_" + hashlib.sha256(packet_seed.encode("utf-8")).hexdigest()[:16]

    packet = NormalizedWorkItemPacket(
        work_item_id=work_item_id,
        source_kind=source_kind,
        source_ref=source_ref,
        title=title,
        description_summary=_compact(description),
        requested_outcome=outcome,
        acceptance_criteria=acceptance,
        declared_constraints=constraints,
        declared_authority_requests=authorities,
        declared_targets=targets,
        declared_tests=tests,
        risk_class=risk_class,
        intake_status=intake_status,
        blocker_codes=tuple(sorted(set(blockers))),
        warning_codes=tuple(sorted(set(warnings))),
        workspace_change_set_admission_may_be_attempted=can_attempt_admission,
        agent_execution_is_requested=agent_execution_requested,
        agent_execution_is_permitted_by_this_packet=False,
        workspace_change_set_proposal_metadata=proposal,
    )
    decision = WorkItemIntakeDecision(
        intake_status=packet.intake_status,
        risk_class=packet.risk_class,
        blocker_codes=packet.blocker_codes,
        warning_codes=packet.warning_codes,
    )
    return packet, decision


def summarize_work_item_packet(packet: NormalizedWorkItemPacket) -> dict[str, Any]:
    summary = asdict(packet)
    summary["workspace_change_set_proposal_metadata"] = packet.workspace_change_set_proposal_metadata
    return summary


__all__ = [
    "INTAKE_STATUSES",
    "RISK_CLASSES",
    "WORK_ITEM_SOURCE_KINDS",
    "NormalizedWorkItemPacket",
    "WorkItemIntakeDecision",
    "WorkItemIntakePolicy",
    "WorkItemIntakeRequest",
    "WorkItemSourceMetadata",
    "normalize_work_item_intake",
    "summarize_work_item_packet",
]
