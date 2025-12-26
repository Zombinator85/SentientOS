from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
from typing import Any, Mapping

from logging_config import get_log_path
from log_utils import append_json


IDENTITY_LOG_PATH = get_log_path("identity_drift.jsonl", "IDENTITY_DRIFT_LOG")


@dataclass(frozen=True)
class IdentityDriftReport:
    classification: str
    changes: tuple[dict[str, object], ...]
    pre_digest: str
    post_digest: str


class IdentityDriftError(RuntimeError):
    """Raised when critical identity drift is detected."""


_TASK_LIFECYCLE: Mapping[str, object] = {
    "task_statuses": ("completed", "failed"),
    "step_statuses": ("completed", "failed"),
    "epr_action_statuses": ("completed", "blocked", "failed"),
    "prerequisite_statuses": (
        "satisfied",
        "epr-fixable",
        "authority-required",
        "impossible",
        "unknown",
    ),
    "exhaustion_types": ("closure_exhausted", "epr_exhausted"),
    "task_terminal_outcomes": (
        "completed",
        "failed",
        "closure_exhausted",
        "epr_exhausted",
        "authority-required",
        "impossible",
        "unknown",
    ),
    "prerequisite_transitions": {
        "unknown": ("unknown", "epr-fixable", "authority-required", "impossible", "satisfied"),
        "epr-fixable": ("epr-fixable", "satisfied", "authority-required", "impossible"),
        "authority-required": ("authority-required", "satisfied"),
        "impossible": ("impossible",),
        "satisfied": ("satisfied",),
    },
}


_EPR_RULES: Mapping[str, object] = {
    "kind": "EPR",
    "allowed_authority_impact": ("none", "local", "global"),
    "allowed_reversibility": ("guaranteed", "bounded", "none"),
    "allowed_rollback_proof": ("snapshot", "diff", "commit", "none"),
    "allowed_external_effects": ("yes", "no"),
    "external_effects_forbidden": True,
    "prohibited_mutations": (
        "changes_governance",
        "changes_admission",
        "changes_authorization",
        "changes_policy",
        "changes_permissions",
        "privilege_escalation",
        "task_goal_reinterpretation",
        "background_execution",
    ),
    "approval_rules": (
        {
            "authority_impact": "none",
            "reversibility": "guaranteed",
            "requires_approval": False,
        },
        {
            "authority_impact": "none",
            "reversibility": "bounded",
            "rollback_proof_required": True,
        },
        {
            "otherwise": "approval_required",
        },
    ),
    "unknown_prerequisite_rules": {
        "requires_condition": True,
        "requires_reason": True,
        "disallowed_resolved_status": ("unknown",),
    },
    "identity_persistence": {
        "epr_persists_identity_changes": False,
    },
}


def compute_system_identity_digest(
    *,
    admission_policy: Mapping[str, Any] | object,
    control_policy: Mapping[str, Any] | object,
    closure_limits: Mapping[str, Any] | object,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    components = _build_components(
        admission_policy=admission_policy,
        control_policy=control_policy,
        closure_limits=closure_limits,
        metadata=metadata,
    )
    serialized = json.dumps(components, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(serialized).hexdigest()
    return {"digest": digest, "components": components}


def classify_identity_drift(
    pre_identity: Mapping[str, Any],
    post_identity: Mapping[str, Any],
) -> IdentityDriftReport:
    pre_digest = str(pre_identity.get("digest", ""))
    post_digest = str(post_identity.get("digest", ""))
    pre_components = pre_identity.get("components", {})
    post_components = post_identity.get("components", {})

    if pre_digest and pre_digest == post_digest:
        return IdentityDriftReport(
            classification="none",
            changes=(),
            pre_digest=pre_digest,
            post_digest=post_digest,
        )

    stripped_pre = _strip_metadata(pre_components)
    stripped_post = _strip_metadata(post_components)

    if stripped_pre == stripped_post:
        changes = _diff_components(pre_components, post_components)
        return IdentityDriftReport(
            classification="benign",
            changes=changes,
            pre_digest=pre_digest,
            post_digest=post_digest,
        )

    changes = _diff_components(pre_components, post_components)
    return IdentityDriftReport(
        classification="critical",
        changes=changes,
        pre_digest=pre_digest,
        post_digest=post_digest,
    )


def enforce_identity_drift(
    pre_identity: Mapping[str, Any],
    post_identity: Mapping[str, Any],
) -> IdentityDriftReport:
    report = classify_identity_drift(pre_identity, post_identity)
    if report.classification == "none":
        return report

    severity = "critical" if report.classification == "critical" else "benign"
    _log_identity_drift(report, severity=severity)

    if report.classification == "critical":
        raise IdentityDriftError(
            "CRITICAL IDENTITY DRIFT DETECTED: governance or execution semantics changed"
        )
    return report


def _build_components(
    *,
    admission_policy: Mapping[str, Any] | object,
    control_policy: Mapping[str, Any] | object,
    closure_limits: Mapping[str, Any] | object,
    metadata: Mapping[str, Any] | None,
) -> dict[str, object]:
    admission_payload = _normalise_admission_policy(admission_policy)
    control_payload = _normalise_control_policy(control_policy)
    closure_payload = _normalise_closure_limits(closure_limits)

    governance = {
        "admission": admission_payload,
        "authorization": control_payload,
        "closure_rules": closure_payload,
    }

    execution = {
        "epr_rules": _EPR_RULES,
        "exhaustion_limits": closure_payload,
    }

    privilege_surface = {
        "allowed_step_kinds": tuple(admission_payload.get("allowed_step_kinds", ())),
        "control_plane_allowlist": _control_plane_allowlist(control_payload),
    }

    return {
        "governance": governance,
        "execution": execution,
        "privilege_surface": privilege_surface,
        "task_lifecycle": _TASK_LIFECYCLE,
        "metadata": _normalise_metadata(metadata or {}),
    }


def _normalise_admission_policy(policy: Mapping[str, Any] | object) -> dict[str, object]:
    payload = _to_dict(policy)
    allowed = payload.get("allowed_step_kinds") or payload.get("allowed_step_kinds", ())
    if isinstance(allowed, (set, frozenset, list, tuple)):
        allowed = tuple(sorted(str(value) for value in allowed))
    else:
        allowed = tuple()
    payload["allowed_step_kinds"] = allowed
    return {
        "policy_version": str(payload.get("policy_version", "")),
        "max_steps": int(payload.get("max_steps", 0) or 0),
        "max_shell_steps": int(payload.get("max_shell_steps", 0) or 0),
        "max_python_steps": int(payload.get("max_python_steps", 0) or 0),
        "allow_mesh": bool(payload.get("allow_mesh", False)),
        "allowed_step_kinds": allowed,
        "deny_shell_in_autonomous": bool(payload.get("deny_shell_in_autonomous", False)),
        "require_vow_digest_match": bool(payload.get("require_vow_digest_match", False)),
        "expected_vow_digest": str(payload.get("expected_vow_digest", ""))
        if payload.get("expected_vow_digest")
        else "",
        "require_doctrine_digest_match": bool(payload.get("require_doctrine_digest_match", False)),
        "expected_doctrine_digest": str(payload.get("expected_doctrine_digest", ""))
        if payload.get("expected_doctrine_digest")
        else "",
    }


def _normalise_control_policy(policy: Mapping[str, Any] | object) -> dict[str, object]:
    if hasattr(policy, "describe"):
        described = policy.describe()  # type: ignore[no-any-return]
        return _to_dict(described)
    return _to_dict(policy)


def _normalise_closure_limits(limits: Mapping[str, Any] | object) -> dict[str, object]:
    payload = _to_dict(limits)
    return {
        "max_closure_iterations": int(payload.get("max_closure_iterations", 0) or 0),
        "max_epr_actions_per_task": int(payload.get("max_epr_actions_per_task", 0) or 0),
        "max_nested_prerequisite_depth": int(payload.get("max_nested_prerequisite_depth", 0) or 0),
        "max_unknown_resolution_cycles": int(payload.get("max_unknown_resolution_cycles", 0) or 0),
    }


def _control_plane_allowlist(control_payload: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    rules = control_payload.get("request_rules", {})
    allowlist: dict[str, tuple[str, ...]] = {}
    if isinstance(rules, Mapping):
        for request_type, rule in rules.items():
            if not isinstance(rule, Mapping):
                continue
            allowed_requesters = list(rule.get("allowed_requesters", []) or [])
            allowed_contexts = list(rule.get("allowed_contexts", []) or [])
            allowlist[str(request_type)] = tuple(
                sorted({str(item) for item in allowed_requesters + allowed_contexts})
            )
    return allowlist


def _normalise_metadata(metadata: Mapping[str, Any]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key in sorted(metadata, key=str):
        value = metadata[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[str(key)] = value
        else:
            sanitized[str(key)] = repr(value)
    return sanitized


def _strip_metadata(components: Mapping[str, Any]) -> dict[str, object]:
    stripped = {key: value for key, value in components.items() if key != "metadata"}
    return _normalise_metadata_container(stripped)


def _normalise_metadata_container(payload: Mapping[str, Any]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key in sorted(payload, key=str):
        value = payload[key]
        if isinstance(value, Mapping):
            normalized[str(key)] = _normalise_metadata_container(value)
        elif isinstance(value, (list, tuple)):
            normalized[str(key)] = [
                _normalise_metadata_container(item) if isinstance(item, Mapping) else item
                for item in value
            ]
        else:
            normalized[str(key)] = value
    return normalized


def _diff_components(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> tuple[dict[str, object], ...]:
    changes: list[dict[str, object]] = []
    before_keys = set(before.keys())
    after_keys = set(after.keys())
    for key in sorted(before_keys | after_keys):
        before_value = before.get(key)
        after_value = after.get(key)
        if before_value == after_value:
            continue
        changes.append({"path": key, "before": before_value, "after": after_value})
    return tuple(changes)


def _log_identity_drift(report: IdentityDriftReport, *, severity: str) -> None:
    entry = {
        "event": "identity_drift",
        "classification": report.classification,
        "severity": severity,
        "pre_digest": report.pre_digest,
        "post_digest": report.post_digest,
        "changes": list(report.changes),
    }
    append_json(get_log_path("identity_drift.jsonl", "IDENTITY_DRIFT_LOG"), entry)


def _to_dict(value: Mapping[str, Any] | object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(k): value[k] for k in value}
    if is_dataclass(value):
        return asdict(value)
    payload: dict[str, object] = {}
    for key in dir(value):
        if key.startswith("_"):
            continue
        attr = getattr(value, key, None)
        if callable(attr):
            continue
        payload[str(key)] = attr
    return payload


__all__ = [
    "IdentityDriftError",
    "IdentityDriftReport",
    "compute_system_identity_digest",
    "classify_identity_drift",
    "enforce_identity_drift",
]
