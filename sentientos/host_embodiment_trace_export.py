"""Deterministic reviewer exports for host embodiment traces.

This module is metadata/export only. It does not collect live host data, mutate
host state, open network egress, invoke providers, assemble prompts, execute host
actions, or grant authorization.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping, cast

from sentientos.host_embodiment_trace import (
    HOST_EMBODIMENT_TRACE_STEP_KINDS,
    HostEmbodimentTrace,
    HostEmbodimentTraceValidationResult,
    summarize_host_embodiment_trace,
    validate_host_embodiment_trace,
)

FORBIDDEN_TRACE_EXPORT_FLAGS = (
    "live_authorization_granted",
    "effect_performed",
    "host_mutation_performed",
    "network_performed",
    "provider_invocation_performed",
    "prompt_assembly_performed",
)
REQUIRED_BLOCKED_ACTION_LABELS = frozenset(
    {
        "fan_pwm_write",
        "thermal_actuation",
        "power_profile_mutation",
        "service_restart",
        "process_kill",
        "file_cleanup",
        "file_delete",
        "provider_invocation",
        "network_egress",
        "prompt_assembly",
        "federation_transport",
        "remote_execution",
    }
)
REQUIRED_DEFERRED_CAPABILITY_LABELS = frozenset(
    {
        "live_authorization_grant",
        "real_effect_execution",
        "real_rollback_execution",
        "real_fan_pwm_control",
        "real_thermal_actuation",
        "real_power_profile_mutation",
        "real_service_restart",
        "real_process_kill",
        "real_file_cleanup",
        "real_file_delete",
        "network_egress",
        "provider_invocation",
        "prompt_assembly",
        "federation_transport",
        "remote_execution",
    }
)
LADDER_STAGE_LABELS = (
    "collector results",
    "inventory",
    "telemetry",
    "pressure",
    "policy",
    "proposal",
    "broker eligibility",
    "broker review",
    "fulfillment rehearsal",
    "execution proof",
    "authorization review",
    "future authorization schema",
    "controlled authorization contract",
    "schema-only grant record",
    "schema-only revocation record",
    "metadata-only ledger",
    "reviewer trace",
)


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(cast(Any, value))
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    return value


def _trace_payload(trace_or_payload: HostEmbodimentTrace | Mapping[str, Any]) -> dict[str, Any]:
    payload = _plain(trace_or_payload)
    if not isinstance(payload, dict):
        raise TypeError("trace export payload must be a HostEmbodimentTrace or mapping")
    return payload


def serialize_host_embodiment_trace_json(trace: HostEmbodimentTrace | Mapping[str, Any]) -> str:
    """Return deterministic sorted-key JSON for a trace payload."""

    payload = _trace_payload(trace)
    result = validate_trace_export_payload(payload)
    if not result.ok:
        raise ValueError("invalid trace export payload: " + ", ".join(result.findings))
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _list_items(items: tuple[str, ...] | list[str], *, limit: int | None = None) -> str:
    selected = list(items if limit is None else items[:limit])
    return ", ".join(str(item) for item in selected)


def serialize_host_embodiment_trace_markdown(trace: HostEmbodimentTrace | Mapping[str, Any]) -> str:
    """Return a concise reviewer-readable Markdown summary for a trace."""

    payload = _trace_payload(trace)
    result = validate_trace_export_payload(payload)
    if not result.ok:
        raise ValueError("invalid trace export payload: " + ", ".join(result.findings))

    steps = payload.get("steps", ())
    step_kinds = tuple(str(step.get("step_kind", "")) for step in steps if isinstance(step, Mapping))
    blocked = tuple(str(item) for item in payload.get("blocked_action_labels", ()))
    deferred = tuple(str(item) for item in payload.get("deferred_capability_labels", ()))
    flags = {flag: bool(payload.get(flag, False)) for flag in FORBIDDEN_TRACE_EXPORT_FLAGS}
    lines = [
        "# Host Embodiment Reviewer Demo Trace",
        "",
        f"- Scenario: {payload.get('scenario_label', '<missing>')}",
        f"- Scenario ID: `{payload.get('scenario_id', '<missing>')}`",
        f"- Trace status: `{payload.get('trace_status', '<missing>')}`",
        f"- Step count: {payload.get('step_count', len(steps))}",
        f"- Digest: `{payload.get('digest', '<missing>')}`",
        "",
        "## Key ladder stages",
        "",
    ]
    lines.extend(f"- {stage}" for stage in LADDER_STAGE_LABELS)
    lines.extend(
        [
            "",
            "## Trace step kinds",
            "",
            _list_items(step_kinds),
            "",
            "## Blocked/deferred capabilities",
            "",
            f"- Blocked actions: {_list_items(blocked)}",
            f"- Deferred capabilities: {_list_items(deferred)}",
            "",
            "## Reviewer proof statements",
            "",
            "- PWM presence is not control authority; the demo records PWM telemetry as a signal only.",
            "- The controlled authorization contract is not a live grant and cannot authorize fulfillment.",
            "- Grant/revocation records are schema-only/future-use-only and issue no runtime authority token.",
            "- Real actuation remains deferred; fulfillment is rehearsal/proof only.",
            "- The default reviewer demo uses fake/sample thermal+PWM telemetry, not live host collection.",
            "- The metadata-only ledger is an inspection artifact, not an authorization mechanism.",
            "",
            "## Proof flags",
            "",
        ]
    )
    flag_labels = {
        "live_authorization_granted": "no live authorization",
        "effect_performed": "no effect",
        "host_mutation_performed": "no host mutation",
        "network_performed": "no network",
        "provider_invocation_performed": "no provider",
        "prompt_assembly_performed": "no prompt assembly",
    }
    for flag, label in flag_labels.items():
        lines.append(f"- {label}: `{not flags[flag]}`")
    lines.extend(
        [
            "- no fan/PWM writes: `True`",
            "- no thermal writes: `True`",
            "- no power mutation: `True`",
            "- no service restart: `True`",
            "- no cleanup/delete: `True`",
            "",
        ]
    )
    return "\n".join(lines)


def validate_trace_export_payload(trace_or_payload: HostEmbodimentTrace | Mapping[str, Any]) -> HostEmbodimentTraceValidationResult:
    """Validate that an export payload remains demo/proof-only."""

    if isinstance(trace_or_payload, HostEmbodimentTrace):
        base = validate_host_embodiment_trace(trace_or_payload)
        payload = trace_or_payload.to_dict()
        findings = list(base.findings)
    else:
        payload = _trace_payload(trace_or_payload)
        findings = []

    if not payload.get("metadata_only", False):
        findings.append("export_payload_not_metadata_only")
    if not payload.get("demo_only", False):
        findings.append("export_payload_not_demo_only")
    for flag in FORBIDDEN_TRACE_EXPORT_FLAGS:
        if payload.get(flag, False):
            findings.append(f"export_forbidden_flag:{flag}")
    steps = payload.get("steps", ())
    if not isinstance(steps, (list, tuple)):
        findings.append("export_steps_not_sequence")
        steps = ()
    if payload.get("step_count") != len(steps):
        findings.append("export_step_count_mismatch")
    seen_kinds: set[str] = set()
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            findings.append(f"export_step_not_mapping:{index}")
            continue
        step_kind = str(step.get("step_kind", ""))
        seen_kinds.add(step_kind)
        if step_kind not in HOST_EMBODIMENT_TRACE_STEP_KINDS:
            findings.append(f"export_unknown_step_kind:{step_kind}")
        if not step.get("metadata_only", False):
            findings.append(f"export_step_not_metadata_only:{index}:{step_kind}")
        if step.get("effect_performed", False):
            findings.append(f"export_step_claims_effect:{index}:{step_kind}")
        if step.get("host_mutation_performed", False):
            findings.append(f"export_step_claims_host_mutation:{index}:{step_kind}")
    missing_blocks = REQUIRED_BLOCKED_ACTION_LABELS - set(payload.get("blocked_action_labels", ()))
    if missing_blocks:
        findings.append("export_missing_blocked_actions:" + ",".join(sorted(missing_blocks)))
    missing_deferred = REQUIRED_DEFERRED_CAPABILITY_LABELS - set(payload.get("deferred_capability_labels", ()))
    if missing_deferred:
        findings.append("export_missing_deferred_capabilities:" + ",".join(sorted(missing_deferred)))
    required_steps = {
        "collector_result",
        "host_inventory_manifest",
        "telemetry_snapshot",
        "pressure_report",
        "policy_decision",
        "proposal_receipt",
        "broker_decision",
        "broker_review_receipt",
        "fulfillment_rehearsal_receipt",
        "execution_readiness_manifest",
        "authorization_review_receipt",
        "future_authorization_schema",
        "controlled_authorization_contract",
        "controlled_authorization_grant_record",
        "controlled_authorization_revocation_record",
        "controlled_authorization_ledger",
    }
    missing_steps = required_steps - seen_kinds
    if missing_steps:
        findings.append("export_missing_ladder_steps:" + ",".join(sorted(missing_steps)))
    return HostEmbodimentTraceValidationResult(not findings, tuple(findings))


def write_trace_export_artifact(output_path: str | Path, content: str, *, create_parent: bool = False) -> Path:
    """Write export content to an explicit caller-supplied path.

    The target path is the only final artifact path. Parent directories are only
    created when the caller opts in with ``create_parent=True``.
    """

    path = Path(output_path)
    if not str(path):
        raise ValueError("output path is required")
    if path.exists() and path.is_dir():
        raise ValueError("output path must be a file path, not a directory")
    parent = path.parent if str(path.parent) else Path(".")
    if not parent.exists():
        if create_parent:
            parent.mkdir(parents=True, exist_ok=True)
        else:
            raise ValueError("output parent does not exist; pass create_parent=True to create it")
    temporary = parent / f".{path.name}.tmp"
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    return path
