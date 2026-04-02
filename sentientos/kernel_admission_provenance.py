from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from sentientos.protected_mutation_corridor import non_bypass_model_definition
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
_EXECUTION_CONSISTENCY_STATUSES = (
    "consistent",
    "declared_domain_mismatch",
    "declared_authority_mismatch",
    "side_effect_domain_mismatch",
    "admitted_but_missing_expected_side_effect",
    "undeclared_side_effect",
    "not_applicable",
)
_EXECUTION_CONSISTENCY_OUTCOMES = (
    "not_applicable",
    "declared_and_consistent",
    "declared_but_mismatched",
    "undeclared_but_protected_action",
    "execution_drift_detected",
    "admitted_but_missing_expected_side_effect",
)
_NON_BYPASS_BLOCKING_STATUSES = frozenset(
    {
        "alternate_writer_detected",
        "unadmitted_operator_path_detected",
        "uncovered_mutation_entrypoint_detected",
        "canonical_boundary_missing",
    }
)
_DEFAULT_NON_BYPASS_STATUS = "no_obvious_bypass_detected"
_WRITE_MARKERS = ("write_text(", ".write(", "open(", "json.dump(", "json.dumps(", "append_jsonl(", "write_json(")
_COVERED_DOMAIN_ORDER = (
    "genesisforge_lineage_proposal_adoption",
    "immutable_manifest_identity_writes",
    "quarantine_clear_privileged_operator_action",
    "codexhealer_repair_regenesis_linkage",
)
_TRUST_POSTURE_STATUS_VOCABULARY = (
    "trusted",
    "legacy_only",
    "forward_risk_present",
    "strict_failure_present",
    "not_applicable",
    "evidence_incomplete",
)
_EVIDENCE_INCOMPLETE_CODES = frozenset(
    {
        "missing_allow_admission",
        "missing_lineage_admission_link",
        "missing_manifest_admission_link",
        "missing_quarantine_correlation",
        "missing_repair_admission_link",
        "missing_expected_lineage_side_effect",
        "missing_expected_manifest_side_effect",
        "missing_expected_quarantine_clear_side_effect",
        "missing_expected_proposal_adopt_side_effect",
        "execution_consistency_admitted_but_missing_expected_side_effect",
    }
)


def _consistency_outcome_for_status(*, declared: bool, status: str) -> str:
    if status == "not_applicable":
        return "not_applicable"
    if status == "consistent":
        return "declared_and_consistent" if declared else "undeclared_but_protected_action"
    if status == "admitted_but_missing_expected_side_effect":
        return "admitted_but_missing_expected_side_effect"
    if status in {"side_effect_domain_mismatch", "undeclared_side_effect"}:
        return "execution_drift_detected"
    return "declared_but_mismatched"


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


def _candidate_source_files(repo_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for prefix in ("scripts", "sentientos"):
        root = repo_root / prefix
        if root.exists():
            candidates.extend(path for path in root.rglob("*.py") if path.is_file())
    candidates.extend(path for path in repo_root.glob("*.py") if path.is_file())
    candidates.extend(path for path in repo_root.glob("*.bat") if path.is_file())
    return sorted(set(candidates))


def _first_match_line(content: str, token: str) -> int:
    for idx, line in enumerate(content.splitlines(), start=1):
        if token in line:
            return idx
    return 1


def _verify_non_bypass(repo_root: Path, model: Mapping[str, Any], *, relevant_domains: set[str]) -> list[dict[str, Any]]:
    domains = model.get("domains")
    if not isinstance(domains, list):
        return []
    files = _candidate_source_files(repo_root)
    checks: list[dict[str, Any]] = []
    for item in domains:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "")
        canonical_boundary = str(item.get("canonical_boundary") or "")
        protected_artifacts = [str(value) for value in item.get("protected_artifact_domains", []) if isinstance(value, str)]
        allowed_writers = {str(value) for value in item.get("allowed_writer_surfaces", []) if isinstance(value, str)}
        status = _DEFAULT_NON_BYPASS_STATUS
        findings: list[dict[str, Any]] = []
        if name not in relevant_domains:
            checks.append(
                {
                    "domain": name,
                    "status": _DEFAULT_NON_BYPASS_STATUS,
                    "canonical_boundary": canonical_boundary,
                    "expected_kernel_action_kinds": list(item.get("expected_kernel_action_kinds", [])),
                    "expected_authority_classes": list(item.get("expected_authority_classes", [])),
                    "protected_artifact_domains": protected_artifacts,
                    "allowed_writer_surfaces": sorted(allowed_writers),
                    "findings": [{"kind": "out_of_scope_for_current_evidence"}],
                }
            )
            continue
        if not canonical_boundary:
            status = "canonical_boundary_missing"
            findings.append({"kind": "missing_mapping", "detail": "canonical_boundary is empty"})
        elif not (repo_root / canonical_boundary).exists():
            status = "canonical_boundary_missing"
            findings.append({"kind": "missing_file", "path": canonical_boundary})
        elif canonical_boundary not in allowed_writers:
            status = "canonical_boundary_missing"
            findings.append({"kind": "mapping_invalid", "detail": "canonical boundary not listed as allowed writer"})

        token_candidates = [token for token in protected_artifacts if token and "*" not in token]
        bypass_hits: list[dict[str, Any]] = []
        operator_hits: list[dict[str, Any]] = []
        for source in files:
            rel = source.relative_to(repo_root).as_posix()
            if rel in allowed_writers:
                continue
            content = source.read_text(encoding="utf-8", errors="ignore")
            if not any(token in content for token in token_candidates):
                continue
            if not any(marker in content for marker in _WRITE_MARKERS):
                continue
            matched_token = next((token for token in token_candidates if token in content), "")
            hit = {
                "path": rel,
                "line": _first_match_line(content, matched_token or token_candidates[0]),
                "artifact_token": matched_token,
            }
            bypass_hits.append(hit)
            if rel.startswith("scripts/"):
                has_admission = "admit_action(" in content or "admission_decision_ref" in content or "protected_mutation_intent" in content
                if not has_admission:
                    operator_hits.append(hit)

        if status != "canonical_boundary_missing":
            if operator_hits:
                status = "unadmitted_operator_path_detected"
                findings.extend({"kind": "operator_path", **hit} for hit in operator_hits)
            elif bypass_hits:
                status = "alternate_writer_detected"
                findings.extend({"kind": "alternate_writer", **hit} for hit in bypass_hits)

        checks.append(
            {
                "domain": name,
                "status": status,
                "canonical_boundary": canonical_boundary,
                "expected_kernel_action_kinds": list(item.get("expected_kernel_action_kinds", [])),
                "expected_authority_classes": list(item.get("expected_authority_classes", [])),
                "protected_artifact_domains": protected_artifacts,
                "allowed_writer_surfaces": sorted(allowed_writers),
                "findings": findings,
            }
        )
    return checks


def _domain_for_issue(issue: VerificationIssue) -> str | None:
    code = issue.code
    detail = issue.detail
    if "lineage" in code or "proposal_adopt" in code or "lineage_integrate" in detail:
        return "genesisforge_lineage_proposal_adoption"
    if "manifest" in code:
        return "immutable_manifest_identity_writes"
    if "quarantine" in code:
        return "quarantine_clear_privileged_operator_action"
    if "repair" in code:
        return "codexhealer_repair_regenesis_linkage"
    if code.startswith("protected_intent_") or code.startswith("execution_consistency_"):
        if "proposal_adopt" in detail or "lineage_integrate" in detail:
            return "genesisforge_lineage_proposal_adoption"
        if "generate_immutable_manifest" in detail:
            return "immutable_manifest_identity_writes"
        if "quarantine_clear" in detail:
            return "quarantine_clear_privileged_operator_action"
    return None


def _derive_domain_posture(*, evidence: Mapping[str, Any], mode: str, applicable: bool) -> str:
    if not applicable:
        return "not_applicable"
    forward_risk = bool(evidence.get("forward_risk_present", False))
    evidence_incomplete = bool(evidence.get("evidence_incomplete", False))
    legacy_only = bool(evidence.get("legacy_only", False))
    strict_blocking = bool(evidence.get("strict_blocking_present", False))
    if forward_risk:
        return "forward_risk_present"
    if mode == "strict" and strict_blocking:
        return "strict_failure_present"
    if evidence_incomplete:
        return "evidence_incomplete"
    if legacy_only:
        return "legacy_only"
    return "trusted"


def _compose_trust_posture(
    *,
    mode: str,
    issues: list[VerificationIssue],
    intent_checks: list[dict[str, object]],
    execution_consistency_checks: list[dict[str, object]],
    non_bypass_checks: list[dict[str, Any]],
    covered_relevance_domains: set[str],
    change_relevant_domains: set[str] | None = None,
) -> dict[str, object]:
    domain_evidence: dict[str, dict[str, Any]] = {
        domain: {
            "issue_count": 0,
            "issue_codes": {},
            "issue_categories": {},
            "enforcement_classes": {},
            "intent_status_counts": {},
            "execution_consistency_status_counts": {},
            "execution_consistency_outcome_counts": {},
            "non_bypass_status_counts": {},
            "non_bypass_blocking_count": 0,
            "evidence_incomplete_signals": 0,
            "fresh_forward_signals": 0,
            "legacy_signals": 0,
            "strict_blocking_signals": 0,
        }
        for domain in _COVERED_DOMAIN_ORDER
    }
    action_to_domain = {
        "lineage_integrate": "genesisforge_lineage_proposal_adoption",
        "proposal_adopt": "genesisforge_lineage_proposal_adoption",
        "generate_immutable_manifest": "immutable_manifest_identity_writes",
        "quarantine_clear": "quarantine_clear_privileged_operator_action",
    }
    for issue in issues:
        domain = _domain_for_issue(issue)
        if domain is None:
            continue
        bucket = domain_evidence[domain]
        bucket["issue_count"] = int(bucket["issue_count"]) + 1
        codes = bucket["issue_codes"]
        if isinstance(codes, dict):
            codes[issue.code] = int(codes.get(issue.code, 0)) + 1
        categories = bucket["issue_categories"]
        if isinstance(categories, dict):
            categories[issue.category] = int(categories.get(issue.category, 0)) + 1
        enforcement = bucket["enforcement_classes"]
        if isinstance(enforcement, dict):
            enforcement[issue.enforcement_class] = int(enforcement.get(issue.enforcement_class, 0)) + 1
        if issue.code in _EVIDENCE_INCOMPLETE_CODES:
            bucket["evidence_incomplete_signals"] = int(bucket["evidence_incomplete_signals"]) + 1
        if issue.enforcement_class in _FORWARD_BLOCKING_CLASSES:
            bucket["fresh_forward_signals"] = int(bucket["fresh_forward_signals"]) + 1
        if issue.enforcement_class == "legacy_debt":
            bucket["legacy_signals"] = int(bucket["legacy_signals"]) + 1
            bucket["strict_blocking_signals"] = int(bucket["strict_blocking_signals"]) + 1

    for check in intent_checks:
        domain_candidates = [str(item) for item in check.get("expected_domains", []) if isinstance(item, str)]
        if not domain_candidates:
            mapped = action_to_domain.get(str(check.get("action_kind") or ""))
            if mapped:
                domain_candidates = [mapped]
        status = str(check.get("status") or "not_applicable")
        for domain in domain_candidates:
            if domain not in domain_evidence:
                continue
            counts = domain_evidence[domain]["intent_status_counts"]
            if isinstance(counts, dict):
                counts[status] = int(counts.get(status, 0)) + 1

    for check in execution_consistency_checks:
        status = str(check.get("status") or "not_applicable")
        outcome = str(check.get("consistency_outcome") or "not_applicable")
        domains = [str(item) for item in check.get("expected_domains", []) if isinstance(item, str)]
        observed = [str(item) for item in check.get("observed_side_effect_domains", []) if isinstance(item, str)]
        domains = sorted(set(domains + observed))
        if not domains:
            mapped = action_to_domain.get(str(check.get("action_kind") or ""))
            if mapped:
                domains = [mapped]
        for domain in domains:
            if domain not in domain_evidence:
                continue
            status_counts = domain_evidence[domain]["execution_consistency_status_counts"]
            if isinstance(status_counts, dict):
                status_counts[status] = int(status_counts.get(status, 0)) + 1
            outcome_counts = domain_evidence[domain]["execution_consistency_outcome_counts"]
            if isinstance(outcome_counts, dict):
                outcome_counts[outcome] = int(outcome_counts.get(outcome, 0)) + 1
            if status in {
                "declared_domain_mismatch",
                "declared_authority_mismatch",
                "side_effect_domain_mismatch",
                "admitted_but_missing_expected_side_effect",
                "undeclared_side_effect",
            }:
                domain_evidence[domain]["fresh_forward_signals"] = int(domain_evidence[domain]["fresh_forward_signals"]) + 1
            if status == "admitted_but_missing_expected_side_effect":
                domain_evidence[domain]["evidence_incomplete_signals"] = int(domain_evidence[domain]["evidence_incomplete_signals"]) + 1

    for check in non_bypass_checks:
        domain = str(check.get("domain") or "")
        if domain not in domain_evidence:
            continue
        status = str(check.get("status") or _DEFAULT_NON_BYPASS_STATUS)
        status_counts = domain_evidence[domain]["non_bypass_status_counts"]
        if isinstance(status_counts, dict):
            status_counts[status] = int(status_counts.get(status, 0)) + 1
        if status in _NON_BYPASS_BLOCKING_STATUSES:
            domain_evidence[domain]["non_bypass_blocking_count"] = int(domain_evidence[domain]["non_bypass_blocking_count"]) + 1
            domain_evidence[domain]["fresh_forward_signals"] = int(domain_evidence[domain]["fresh_forward_signals"]) + 1

    def _view(change_set: set[str] | None) -> dict[str, object]:
        posture_counts: dict[str, int] = {status: 0 for status in _TRUST_POSTURE_STATUS_VOCABULARY}
        domain_posture: dict[str, Any] = {}
        for domain in _COVERED_DOMAIN_ORDER:
            evidence = domain_evidence[domain]
            applicable = domain in covered_relevance_domains
            if change_set is not None:
                applicable = applicable and domain in change_set
            derived = {
                **evidence,
                "forward_risk_present": int(evidence["fresh_forward_signals"]) > 0,
                "evidence_incomplete": int(evidence["evidence_incomplete_signals"]) > 0,
                "legacy_only": int(evidence["legacy_signals"]) > 0 and int(evidence["fresh_forward_signals"]) == 0,
                "strict_blocking_present": int(evidence["strict_blocking_signals"]) > 0,
                "applicable": applicable,
            }
            posture = _derive_domain_posture(evidence=derived, mode=mode, applicable=applicable)
            posture_counts[posture] = posture_counts.get(posture, 0) + 1
            domain_posture[domain] = {
                "posture": posture,
                "applicable": applicable,
                "evidence": derived,
                "evidence_classes": [
                    "kernel_admission_issues",
                    "protected_intent_checks",
                    "execution_consistency_checks",
                    "non_bypass_checks",
                ],
            }
        if posture_counts.get("forward_risk_present", 0):
            overall = "forward_risk_present"
        elif posture_counts.get("strict_failure_present", 0):
            overall = "strict_failure_present"
        elif posture_counts.get("evidence_incomplete", 0):
            overall = "evidence_incomplete"
        elif posture_counts.get("legacy_only", 0):
            overall = "legacy_only"
        elif posture_counts.get("trusted", 0):
            overall = "trusted"
        else:
            overall = "not_applicable"
        return {"overall_posture": overall, "posture_counts": posture_counts, "domains": domain_posture}

    return {
        "scope": "covered_protected_mutation_corridor",
        "status_vocabulary": list(_TRUST_POSTURE_STATUS_VOCABULARY),
        "global_covered_scope": _view(None),
        "current_change_surface": _view(change_relevant_domains),
    }


def verify_kernel_admission_provenance(
    *,
    repo_root: Path,
    decisions_path: Path | None = None,
    lineage_path: Path | None = None,
    manifest_path: Path | None = None,
    forge_events_path: Path | None = None,
    repair_ledger_path: Path | None = None,
    adoption_live_mount_path: Path | None = None,
    adoption_codex_index_path: Path | None = None,
    strict: bool = False,
    mode: str | None = None,
    non_bypass_model: Mapping[str, Any] | None = None,
    change_relevant_domains: set[str] | None = None,
) -> dict[str, object]:
    resolved_mode = "strict" if strict else (mode or "baseline-aware")
    if resolved_mode not in {"baseline-aware", "forward-enforcement", "strict"}:
        raise ValueError(f"unsupported mode: {resolved_mode}")
    strict_mode = resolved_mode == "strict"
    resolved_non_bypass_model = non_bypass_model or non_bypass_model_definition()

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
    adoption_live_mount = adoption_live_mount_path or (root / "live")
    adoption_codex_index = adoption_codex_index_path or (root / "codex_index.json")
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
    adoption_live_rows: list[dict[str, Any]] = []
    if adoption_live_mount.exists() and adoption_live_mount.is_dir():
        for candidate in sorted(adoption_live_mount.glob("*.json")):
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                admission = payload.get("admission")
                if isinstance(admission, Mapping):
                    adoption_live_rows.append({"path": str(candidate), "admission": dict(admission)})
    adoption_codex_rows: list[dict[str, Any]] = []
    if adoption_codex_index.exists():
        try:
            index_payload = json.loads(adoption_codex_index.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            index_payload = []
        if isinstance(index_payload, list):
            for item in index_payload:
                if isinstance(item, dict):
                    admission = item.get("admission")
                    if isinstance(admission, Mapping):
                        adoption_codex_rows.append({"admission": dict(admission)})
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

    repair_rows = _read_jsonl(repair_ledger_path or (root / "glow/forge/recovery_ledger.jsonl"))
    for row in repair_rows:
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

    side_effect_domains_by_correlation: dict[str, set[str]] = {}

    def _record_side_effect(correlation_id: str, domain: str) -> None:
        if not correlation_id or not domain:
            return
        side_effect_domains_by_correlation.setdefault(correlation_id, set()).add(domain)

    for item in lineage_rows:
        _record_side_effect(str(item.get("correlation_id") or ""), "genesisforge_lineage_proposal_adoption")
    if resolved_manifest.exists():
        manifest_payload = json.loads(resolved_manifest.read_text(encoding="utf-8"))
        if isinstance(manifest_payload, Mapping):
            admission = manifest_payload.get("admission")
            if isinstance(admission, Mapping):
                _record_side_effect(str(admission.get("correlation_id") or ""), "immutable_manifest_identity_writes")
    for item in forge_rows:
        if str(item.get("event") or "") == "integrity_recovered":
            _record_side_effect(str(item.get("correlation_id") or ""), "quarantine_clear_privileged_operator_action")
    for item in adoption_live_rows:
        admission = item.get("admission")
        if isinstance(admission, Mapping):
            _record_side_effect(str(admission.get("correlation_id") or ""), "genesisforge_lineage_proposal_adoption")
    for item in adoption_codex_rows:
        admission = item.get("admission")
        if isinstance(admission, Mapping):
            _record_side_effect(str(admission.get("correlation_id") or ""), "genesisforge_lineage_proposal_adoption")
    for item in repair_rows:
        details = item.get("details")
        if not isinstance(details, Mapping):
            continue
        kernel_admission = details.get("kernel_admission")
        if not isinstance(kernel_admission, Mapping):
            continue
        if str(item.get("status") or "") != "auto-repair verified":
            continue
        correlation_id = str(kernel_admission.get("correlation_id") or "")
        _record_side_effect(correlation_id, "codexhealer_repair_regenesis_linkage")

    execution_consistency_checks: list[dict[str, object]] = []
    for correlation_id, rows in decisions_by_correlation.items():
        for row in rows:
            action_kind = str(row.get("action_kind") or "")
            if action_kind not in _COVERED_ALLOW_ACTIONS:
                continue
            if str(row.get("final_disposition") or "") != "allow":
                continue
            eval_result = evaluate_declared_intent_for_decision(row)
            expected_domains = set(eval_result.expected_domains)
            observed_domains = set(side_effect_domains_by_correlation.get(correlation_id, set()))
            status = "consistent"
            if not eval_result.declared and observed_domains:
                status = "undeclared_side_effect"
            elif eval_result.declared and not expected_domains.intersection(set(eval_result.declared_domains)):
                status = "declared_domain_mismatch"
            elif eval_result.declared and not eval_result.authority_match:
                status = "declared_authority_mismatch"
            elif expected_domains and not observed_domains:
                status = "admitted_but_missing_expected_side_effect"
            elif observed_domains and not observed_domains.issubset(expected_domains):
                status = "side_effect_domain_mismatch"
            execution_consistency_checks.append(
                {
                    "correlation_id": correlation_id,
                    "action_kind": action_kind,
                    "authority_class": str(row.get("authority_class") or ""),
                    "status": status,
                    "declared": eval_result.declared,
                    "declared_domains": list(eval_result.declared_domains),
                    "expected_domains": list(expected_domains),
                    "observed_side_effect_domains": sorted(observed_domains),
                    "consistency_outcome": _consistency_outcome_for_status(declared=eval_result.declared, status=status),
                }
            )
            if status in {"declared_domain_mismatch", "declared_authority_mismatch"}:
                issues.append(
                    VerificationIssue(
                        code=f"execution_consistency_{status}",
                        detail=correlation_id,
                        category="malformed_current_contract",
                        enforcement_class=_enforcement_class_for_category("malformed_current_contract"),
                    )
                )
            if status in {"side_effect_domain_mismatch", "undeclared_side_effect"}:
                issues.append(
                    VerificationIssue(
                        code=f"execution_consistency_{status}",
                        detail=correlation_id,
                        category="unexpected_collision",
                        enforcement_class=_enforcement_class_for_category("unexpected_collision"),
                    )
                )
            if status == "admitted_but_missing_expected_side_effect":
                issues.append(
                    VerificationIssue(
                        code="execution_consistency_admitted_but_missing_expected_side_effect",
                        detail=correlation_id,
                        category="missing_expected_side_effect",
                        enforcement_class=_enforcement_class_for_category("missing_expected_side_effect"),
                    )
                )
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
            if action_kind == "proposal_adopt":
                has_live = any(
                    isinstance(item.get("admission"), Mapping)
                    and str((item.get("admission") or {}).get("correlation_id") or "") == correlation_id
                    for item in adoption_live_rows
                )
                has_index = any(
                    isinstance(item.get("admission"), Mapping)
                    and str((item.get("admission") or {}).get("correlation_id") or "") == correlation_id
                    for item in adoption_codex_rows
                )
                if not (has_live and has_index):
                    issues.append(
                        VerificationIssue(
                            code="missing_expected_proposal_adopt_side_effect",
                            detail=correlation_id,
                            category="missing_expected_side_effect",
                            enforcement_class=_enforcement_class_for_category("missing_expected_side_effect"),
                        )
                        )

    relevant_domains: set[str] = set()
    for domains in side_effect_domains_by_correlation.values():
        relevant_domains.update(domains)
    action_to_domain = {
        "lineage_integrate": "genesisforge_lineage_proposal_adoption",
        "proposal_adopt": "genesisforge_lineage_proposal_adoption",
        "generate_immutable_manifest": "immutable_manifest_identity_writes",
        "quarantine_clear": "quarantine_clear_privileged_operator_action",
    }
    for row in decision_rows:
        action_kind = str(row.get("action_kind") or "")
        mapped = action_to_domain.get(action_kind)
        if mapped:
            relevant_domains.add(mapped)
    if repair_rows:
        relevant_domains.add("codexhealer_repair_regenesis_linkage")

    non_bypass_checks = _verify_non_bypass(root, resolved_non_bypass_model, relevant_domains=relevant_domains)
    non_bypass_status_counts: dict[str, int] = {}
    fresh_non_bypass_violation_count = 0
    for check in non_bypass_checks:
        status = str(check.get("status") or _DEFAULT_NON_BYPASS_STATUS)
        non_bypass_status_counts[status] = non_bypass_status_counts.get(status, 0) + 1
        if status in _NON_BYPASS_BLOCKING_STATUSES:
            fresh_non_bypass_violation_count += 1
            issues.append(
                VerificationIssue(
                    code=f"non_bypass_{status}",
                    detail=json.dumps(
                        {
                            "domain": check.get("domain"),
                            "canonical_boundary": check.get("canonical_boundary"),
                            "findings": check.get("findings", []),
                        },
                        sort_keys=True,
                    ),
                    category="fresh_regression",
                    enforcement_class=_enforcement_class_for_category("fresh_regression"),
                )
            )

    trust_posture = _compose_trust_posture(
        mode=resolved_mode,
        issues=issues,
        intent_checks=intent_checks,
        execution_consistency_checks=execution_consistency_checks,
        non_bypass_checks=non_bypass_checks,
        covered_relevance_domains=relevant_domains,
        change_relevant_domains=change_relevant_domains,
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
    consistency_status_counts: dict[str, int] = {}
    consistency_outcome_counts: dict[str, int] = {}
    for check in execution_consistency_checks:
        status = str(check.get("status") or "not_applicable")
        outcome = str(check.get("consistency_outcome") or "not_applicable")
        consistency_status_counts[status] = consistency_status_counts.get(status, 0) + 1
        consistency_outcome_counts[outcome] = consistency_outcome_counts.get(outcome, 0) + 1
    fresh_consistency_violation_count = sum(
        1
        for check in execution_consistency_checks
        if str(check.get("status") or "")
        in {
            "declared_domain_mismatch",
            "declared_authority_mismatch",
            "side_effect_domain_mismatch",
            "admitted_but_missing_expected_side_effect",
            "undeclared_side_effect",
        }
    )
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
        "execution_consistency": {
            "status_vocabulary": list(_EXECUTION_CONSISTENCY_STATUSES),
            "outcome_vocabulary": list(_EXECUTION_CONSISTENCY_OUTCOMES),
            "status_counts": consistency_status_counts,
            "outcome_counts": consistency_outcome_counts,
            "fresh_violation_count": fresh_consistency_violation_count,
            "fresh_violation_blocking_in_mode": bool(
                fresh_consistency_violation_count and resolved_mode in {"forward-enforcement", "strict"}
            ),
        },
        "non_bypass": {
            "status_vocabulary": list(resolved_non_bypass_model.get("status_vocabulary", [])),
            "status_counts": non_bypass_status_counts,
            "fresh_violation_count": fresh_non_bypass_violation_count,
            "fresh_violation_blocking_in_mode": bool(
                fresh_non_bypass_violation_count and resolved_mode in {"forward-enforcement", "strict"}
            ),
            "model_scope_id": str(resolved_non_bypass_model.get("scope_id") or ""),
            "model_version": str(resolved_non_bypass_model.get("model_version") or ""),
        },
        "trust_posture": trust_posture,
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
        "execution_consistency_checks": execution_consistency_checks,
        "execution_consistency_status_counts": consistency_status_counts,
        "execution_consistency_outcome_counts": consistency_outcome_counts,
        "non_bypass_checks": non_bypass_checks,
        "non_bypass_status_counts": non_bypass_status_counts,
        "trust_posture": trust_posture,
        "checked": {
            "kernel_decisions": len(decision_rows),
            "lineage_entries": len(lineage_rows),
            "forge_events": len(forge_rows),
            "repair_rows": len(repair_rows),
            "adoption_live_rows": len(adoption_live_rows),
            "adoption_codex_rows": len(adoption_codex_rows),
        },
        "summary": summary,
    }
