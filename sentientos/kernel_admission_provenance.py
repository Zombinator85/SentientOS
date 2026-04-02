from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from sentientos.protected_mutation_provenance import (
    NON_EXECUTION_DISPOSITIONS,
    REQUIRED_ALLOW_FIELDS,
    REQUIRED_NON_EXECUTION_FIELDS,
)
from sentientos.protected_mutation_intent import evaluate_declared_intent_for_decision


@dataclass(frozen=True)
class VerificationIssue:
    code: str
    detail: str
    category: str
    enforcement_class: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "detail": self.detail,
            "category": self.category,
            "enforcement_class": self.enforcement_class,
        }


_COVERED_ALLOW_ACTIONS = {
    "lineage_integrate",
    "proposal_adopt",
    "generate_immutable_manifest",
    "quarantine_clear",
}
_LEGACY_ISSUE_CATEGORIES = frozenset({"legacy_missing_admission_link"})
_COVERED_SCOPE = "protected_mutation_proof:v1:kernel_admission"
_FORWARD_BLOCKING_CLASSES = frozenset({"fresh_regression", "malformed_current_contract", "active_contradiction"})
_INTENT_MISMATCH_STATUSES = frozenset({"declared_but_mismatched", "undeclared_but_protected_action"})


def _enforcement_class_for_category(category: str) -> str:
    if category == "legacy_missing_admission_link":
        return "legacy_debt"
    if category == "malformed_current_contract":
        return "malformed_current_contract"
    if category == "unexpected_collision":
        return "active_contradiction"
    return "fresh_regression"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _decision_index(decisions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_correlation: dict[str, list[dict[str, Any]]] = {}
    for row in decisions:
        correlation_id = str(row.get("correlation_id") or "")
        if not correlation_id:
            continue
        by_correlation.setdefault(correlation_id, []).append(row)
    return by_correlation


def _missing_fields(row: Mapping[str, Any], required: tuple[str, ...]) -> list[str]:
    return [field for field in required if not str(row.get(field) or "").strip()]


def _validate_ref(correlation_id: str, admission_ref: str) -> bool:
    return bool(correlation_id) and admission_ref == f"kernel_decision:{correlation_id}"


def _classify_missing_allow_link(*, decisions_by_correlation: Mapping[str, list[dict[str, Any]]], action_kind: str) -> str:
    has_current_contract_decision = any(
        action_kind == str(row.get("action_kind") or "") for rows in decisions_by_correlation.values() for row in rows
    )
    return "malformed_current_contract" if has_current_contract_decision else "legacy_missing_admission_link"


def verify_kernel_admission_provenance(
    *,
    repo_root: Path,
    decisions_path: Path | None = None,
    lineage_path: Path | None = None,
    manifest_path: Path | None = None,
    forge_events_path: Path | None = None,
    repair_ledger_path: Path | None = None,
    strict: bool = False,
    mode: str | None = None,
) -> dict[str, object]:
    resolved_mode = "strict" if strict else (mode or "baseline-aware")
    if resolved_mode not in {"baseline-aware", "forward-enforcement", "strict"}:
        raise ValueError(f"unsupported mode: {resolved_mode}")
    strict_mode = resolved_mode == "strict"

    root = repo_root.resolve()
    decision_rows = _read_jsonl(decisions_path or (root / "glow/control_plane/kernel_decisions.jsonl"))
    decisions_by_correlation = _decision_index(decision_rows)
    issues: list[VerificationIssue] = []

    for correlation_id, rows in decisions_by_correlation.items():
        action_kinds = {str(row.get("action_kind") or "") for row in rows if str(row.get("action_kind") or "")}
        if len(action_kinds) > 1:
            issues.append(
                VerificationIssue(
                    code="correlation_action_kind_collision",
                    detail=f"{correlation_id}: {sorted(action_kinds)}",
                    category="unexpected_collision",
                    enforcement_class=_enforcement_class_for_category("unexpected_collision"),
                )
            )
        for row in rows:
            action_kind = str(row.get("action_kind") or "")
            disposition = str(row.get("final_disposition") or "")
            if action_kind in _COVERED_ALLOW_ACTIONS and disposition == "allow":
                missing = _missing_fields(row, REQUIRED_ALLOW_FIELDS)
                if missing:
                    issues.append(
                        VerificationIssue(
                            code="decision_missing_required_allow_fields",
                            detail=f"{correlation_id}: action_kind={action_kind} missing={','.join(sorted(missing))}",
                            category="malformed_current_contract",
                            enforcement_class=_enforcement_class_for_category("malformed_current_contract"),
                        )
                    )
            elif action_kind in _COVERED_ALLOW_ACTIONS and disposition in NON_EXECUTION_DISPOSITIONS:
                missing = _missing_fields(row, REQUIRED_NON_EXECUTION_FIELDS)
                if missing:
                    issues.append(
                        VerificationIssue(
                            code="decision_missing_required_non_execution_fields",
                            detail=f"{correlation_id}: action_kind={action_kind} missing={','.join(sorted(missing))}",
                            category="malformed_current_contract",
                            enforcement_class=_enforcement_class_for_category("malformed_current_contract"),
                        )
                    )

    intent_checks: list[dict[str, object]] = []
    for row in decision_rows:
        if not isinstance(row, Mapping):
            continue
        eval_result = evaluate_declared_intent_for_decision(row)
        item = {
            "correlation_id": str(row.get("correlation_id") or ""),
            "action_kind": str(row.get("action_kind") or ""),
            "authority_class": str(row.get("authority_class") or ""),
            "actor": str(row.get("actor") or row.get("execution_owner") or ""),
            **eval_result.to_dict(),
        }
        intent_checks.append(item)
        if eval_result.status in _INTENT_MISMATCH_STATUSES:
            issues.append(
                VerificationIssue(
                    code=f"protected_intent_{eval_result.status}",
                    detail=json.dumps(
                        {
                            "correlation_id": item["correlation_id"],
                            "action_kind": item["action_kind"],
                            "declared_domains": item["declared_domains"],
                            "expected_domains": item["expected_domains"],
                        },
                        sort_keys=True,
                    ),
                    category="malformed_current_contract",
                    enforcement_class=_enforcement_class_for_category("malformed_current_contract"),
                )
            )

    def _require_allow_link(*, correlation_id: str, action_kind: str, source: str) -> None:
        candidates = decisions_by_correlation.get(correlation_id, [])
        allow_matches = [
            row for row in candidates if str(row.get("final_disposition") or "") == "allow" and str(row.get("action_kind") or "") == action_kind
        ]
        if not allow_matches:
            issues.append(
                VerificationIssue(
                    code="missing_allow_admission",
                    detail=f"{source}: correlation_id={correlation_id} action_kind={action_kind}",
                    category="malformed_current_contract",
                    enforcement_class=_enforcement_class_for_category("malformed_current_contract"),
                )
            )

    lineage_rows = _read_jsonl(lineage_path or (root / "lineage/lineage.jsonl"))
    for row in lineage_rows:
        correlation_id = str(row.get("correlation_id") or "")
        admission_ref = str(row.get("admission_decision_ref") or "")
        missing = _missing_fields(row, REQUIRED_ALLOW_FIELDS)
        if missing:
            issues.append(
                VerificationIssue(
                    code="missing_lineage_admission_link",
                    detail=json.dumps(row, sort_keys=True),
                    category=_classify_missing_allow_link(decisions_by_correlation=decisions_by_correlation, action_kind="lineage_integrate"),
                    enforcement_class=_enforcement_class_for_category(
                        _classify_missing_allow_link(decisions_by_correlation=decisions_by_correlation, action_kind="lineage_integrate")
                    ),
                )
            )
            continue
        if not _validate_ref(correlation_id, admission_ref):
            issues.append(
                VerificationIssue(
                    code="invalid_lineage_admission_ref",
                    detail=json.dumps(row, sort_keys=True),
                    category="malformed_current_contract",
                    enforcement_class=_enforcement_class_for_category("malformed_current_contract"),
                )
            )
        _require_allow_link(correlation_id=correlation_id, action_kind="lineage_integrate", source="lineage")

    resolved_manifest = manifest_path or (root / "vow/immutable_manifest.json")
    if resolved_manifest.exists():
        manifest_payload = json.loads(resolved_manifest.read_text(encoding="utf-8"))
        if isinstance(manifest_payload, dict):
            admission = manifest_payload.get("admission")
            if not isinstance(admission, Mapping):
                issues.append(
                    VerificationIssue(
                        code="missing_manifest_admission_link",
                        detail=str(resolved_manifest),
                        category=_classify_missing_allow_link(
                            decisions_by_correlation=decisions_by_correlation,
                            action_kind="generate_immutable_manifest",
                        ),
                        enforcement_class=_enforcement_class_for_category(
                            _classify_missing_allow_link(
                                decisions_by_correlation=decisions_by_correlation,
                                action_kind="generate_immutable_manifest",
                            )
                        ),
                    )
                )
            else:
                correlation_id = str(admission.get("correlation_id") or "")
                admission_ref = str(admission.get("admission_decision_ref") or "")
                missing = _missing_fields(admission, REQUIRED_ALLOW_FIELDS)
                if missing:
                    issues.append(
                        VerificationIssue(
                            code="invalid_manifest_admission_link",
                            detail=str(resolved_manifest),
                            category="malformed_current_contract",
                            enforcement_class=_enforcement_class_for_category("malformed_current_contract"),
                        )
                    )
                else:
                    if not _validate_ref(correlation_id, admission_ref):
                        issues.append(
                            VerificationIssue(
                                code="invalid_manifest_admission_ref",
                                detail=str(resolved_manifest),
                                category="malformed_current_contract",
                                enforcement_class=_enforcement_class_for_category("malformed_current_contract"),
                            )
                        )
                    _require_allow_link(
                        correlation_id=correlation_id,
                        action_kind="generate_immutable_manifest",
                        source="immutable_manifest",
                    )

    forge_rows = _read_jsonl(forge_events_path or (root / "pulse/forge_events.jsonl"))
    for row in forge_rows:
        event = str(row.get("event") or "")
        if event not in {"integrity_recovered", "kernel_admission_denied"}:
            continue
        correlation_id = str(row.get("correlation_id") or "")
        if event == "integrity_recovered":
            missing = _missing_fields(row, REQUIRED_ALLOW_FIELDS)
        else:
            missing = _missing_fields(row, REQUIRED_NON_EXECUTION_FIELDS)
        if missing:
            issues.append(
                VerificationIssue(
                    code="missing_quarantine_correlation",
                    detail=json.dumps(row, sort_keys=True),
                    category=_classify_missing_allow_link(decisions_by_correlation=decisions_by_correlation, action_kind="quarantine_clear"),
                    enforcement_class=_enforcement_class_for_category(
                        _classify_missing_allow_link(decisions_by_correlation=decisions_by_correlation, action_kind="quarantine_clear")
                    ),
                )
            )
            continue
        admission_ref = str(row.get("admission_decision_ref") or "")
        if not _validate_ref(correlation_id, admission_ref):
            issues.append(
                VerificationIssue(
                    code="invalid_quarantine_admission_ref",
                    detail=json.dumps(row, sort_keys=True),
                    category="malformed_current_contract",
                    enforcement_class=_enforcement_class_for_category("malformed_current_contract"),
                )
            )
        if event == "integrity_recovered":
            _require_allow_link(correlation_id=correlation_id, action_kind="quarantine_clear", source="quarantine_clear")
        else:
            denied_rows = decisions_by_correlation.get(correlation_id, [])
            if any(str(item.get("final_disposition") or "") == "allow" for item in denied_rows):
                issues.append(
                    VerificationIssue(
                        code="denied_event_has_allow_decision",
                        detail=f"kernel_admission_denied with allow decision: {correlation_id}",
                        category="unexpected_collision",
                        enforcement_class=_enforcement_class_for_category("unexpected_collision"),
                    )
                )

    for row in _read_jsonl(repair_ledger_path or (root / "glow/forge/recovery_ledger.jsonl")):
        details = row.get("details")
        if not isinstance(details, Mapping):
            continue
        kernel_admission = details.get("kernel_admission")
        if not isinstance(kernel_admission, Mapping):
            continue
        correlation_id = str(kernel_admission.get("correlation_id") or "")
        status = str(row.get("status") or "")
        expect_execution = status == "auto-repair verified"
        required = REQUIRED_ALLOW_FIELDS if expect_execution else REQUIRED_NON_EXECUTION_FIELDS
        missing = _missing_fields(kernel_admission, required)
        if missing:
            issues.append(
                VerificationIssue(
                    code="missing_repair_admission_link",
                    detail=json.dumps(row, sort_keys=True),
                    category=_classify_missing_allow_link(
                        decisions_by_correlation=decisions_by_correlation,
                        action_kind=str(kernel_admission.get("action_kind") or ""),
                    ),
                    enforcement_class=_enforcement_class_for_category(
                        _classify_missing_allow_link(
                            decisions_by_correlation=decisions_by_correlation,
                            action_kind=str(kernel_admission.get("action_kind") or ""),
                        )
                    ),
                )
            )
            continue
        admission_ref = str(kernel_admission.get("admission_decision_ref") or "")
        if not _validate_ref(correlation_id, admission_ref):
            issues.append(
                VerificationIssue(
                    code="invalid_repair_admission_ref",
                    detail=json.dumps(row, sort_keys=True),
                    category="malformed_current_contract",
                    enforcement_class=_enforcement_class_for_category("malformed_current_contract"),
                )
            )
        disposition = str(kernel_admission.get("final_disposition") or "")
        if status == "auto-repair verified":
            _require_allow_link(correlation_id=correlation_id, action_kind=str(kernel_admission.get("action_kind") or ""), source="repair")
        if status == "auto-repair verified" and disposition != "allow":
            issues.append(
                VerificationIssue(
                    code="repair_verified_without_allow",
                    detail=f"status=auto-repair verified correlation={correlation_id} disposition={disposition}",
                    category="malformed_current_contract",
                    enforcement_class=_enforcement_class_for_category("malformed_current_contract"),
                )
            )
        if status in {"auto-repair denied_by_governor", "auto-repair quarantined"} and disposition == "allow":
            issues.append(
                VerificationIssue(
                    code="repair_denied_with_allow",
                    detail=f"status=auto-repair denied_by_governor correlation={correlation_id}",
                    category="unexpected_collision",
                    enforcement_class=_enforcement_class_for_category("unexpected_collision"),
                )
            )

    for correlation_id, rows in decisions_by_correlation.items():
        for row in rows:
            action_kind = str(row.get("action_kind") or "")
            if action_kind not in _COVERED_ALLOW_ACTIONS:
                continue
            if str(row.get("final_disposition") or "") != "allow":
                continue
            if action_kind == "lineage_integrate" and not any(
                str(item.get("correlation_id") or "") == correlation_id for item in lineage_rows
            ):
                issues.append(
                    VerificationIssue(
                        code="missing_expected_lineage_side_effect",
                        detail=correlation_id,
                        category="missing_expected_side_effect",
                        enforcement_class=_enforcement_class_for_category("missing_expected_side_effect"),
                    )
                )
            if action_kind == "generate_immutable_manifest":
                if not resolved_manifest.exists():
                    issues.append(
                        VerificationIssue(
                            code="missing_expected_manifest_side_effect",
                            detail=correlation_id,
                            category="missing_expected_side_effect",
                            enforcement_class=_enforcement_class_for_category("missing_expected_side_effect"),
                        )
                    )
                else:
                    manifest_payload = json.loads(resolved_manifest.read_text(encoding="utf-8"))
                    admission = manifest_payload.get("admission") if isinstance(manifest_payload, Mapping) else None
                    if not isinstance(admission, Mapping) or str(admission.get("correlation_id") or "") != correlation_id:
                        issues.append(
                            VerificationIssue(
                                code="missing_expected_manifest_side_effect",
                                detail=correlation_id,
                                category="missing_expected_side_effect",
                                enforcement_class=_enforcement_class_for_category("missing_expected_side_effect"),
                            )
                        )
            if action_kind == "quarantine_clear" and not any(
                str(item.get("event") or "") == "integrity_recovered" and str(item.get("correlation_id") or "") == correlation_id
                for item in forge_rows
            ):
                issues.append(
                    VerificationIssue(
                        code="missing_expected_quarantine_clear_side_effect",
                        detail=correlation_id,
                        category="missing_expected_side_effect",
                        enforcement_class=_enforcement_class_for_category("missing_expected_side_effect"),
                    )
                )

    if strict_mode:
        blocking_issues = list(issues)
    else:
        blocking_issues = [issue for issue in issues if issue.enforcement_class in _FORWARD_BLOCKING_CLASSES]
    category_counts: dict[str, int] = {}
    enforcement_counts: dict[str, int] = {}
    intent_status_counts: dict[str, int] = {}
    for issue in issues:
        category_counts[issue.category] = category_counts.get(issue.category, 0) + 1
        enforcement_counts[issue.enforcement_class] = enforcement_counts.get(issue.enforcement_class, 0) + 1
    for check in intent_checks:
        status = str(check.get("status") or "unknown")
        intent_status_counts[status] = intent_status_counts.get(status, 0) + 1
    requires_forward = any(bool(item.get("expect_forward_enforcement")) for item in intent_checks if bool(item.get("declared")))
    forward_expectation_met = (resolved_mode in {"forward-enforcement", "strict"}) if requires_forward else True
    has_current_contract_violations = any(issue.category not in _LEGACY_ISSUE_CATEGORIES for issue in issues)
    has_only_legacy_issues = bool(issues) and not has_current_contract_violations
    if not issues:
        overall_status = "healthy"
    elif has_only_legacy_issues:
        overall_status = "legacy_only"
    else:
        overall_status = "current_violation_present"
    summary = {
        "covered_scope": _COVERED_SCOPE,
        "mode": resolved_mode,
        "counts": {
            "issue_count": len(issues),
            "blocking_issue_count": len(blocking_issues),
            "legacy_issue_count": len([issue for issue in issues if issue.category in _LEGACY_ISSUE_CATEGORIES]),
            "classification": category_counts,
            "enforcement_classification": enforcement_counts,
            "intent_status_classification": intent_status_counts,
        },
        "overall_status": overall_status,
        "has_current_contract_violations": has_current_contract_violations,
        "has_only_legacy_issues": has_only_legacy_issues,
        "fresh_regression_count": enforcement_counts.get("fresh_regression", 0),
        "legacy_debt_count": enforcement_counts.get("legacy_debt", 0),
        "malformed_current_contract_count": enforcement_counts.get("malformed_current_contract", 0),
        "active_contradiction_count": enforcement_counts.get("active_contradiction", 0),
        "ok": not blocking_issues,
        "protected_intent": {
            "declared_count": len([item for item in intent_checks if bool(item.get("declared"))]),
            "requires_forward_enforcement": requires_forward,
            "forward_enforcement_expectation_met": forward_expectation_met,
            "status_vocabulary": [
                "declared_and_consistent",
                "declared_but_mismatched",
                "undeclared_but_protected_action",
                "declared_but_not_applicable",
                "not_applicable",
            ],
        },
    }

    return {
        "ok": not blocking_issues,
        "mode": resolved_mode,
        "issue_count": len(issues),
        "blocking_issue_count": len(blocking_issues),
        "legacy_issue_count": len([issue for issue in issues if issue.category in _LEGACY_ISSUE_CATEGORIES]),
        "issues": [issue.to_dict() for issue in issues],
        "blocking_issues": [issue.to_dict() for issue in blocking_issues],
        "category_counts": category_counts,
        "enforcement_class_counts": enforcement_counts,
        "protected_intent_checks": intent_checks,
        "protected_intent_status_counts": intent_status_counts,
        "checked": {
            "kernel_decisions": len(decision_rows),
            "lineage_entries": len(lineage_rows),
            "forge_events": len(forge_rows),
        },
        "summary": summary,
    }
