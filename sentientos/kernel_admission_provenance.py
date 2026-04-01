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


@dataclass(frozen=True)
class VerificationIssue:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


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


def verify_kernel_admission_provenance(
    *,
    repo_root: Path,
    decisions_path: Path | None = None,
    lineage_path: Path | None = None,
    manifest_path: Path | None = None,
    forge_events_path: Path | None = None,
    repair_ledger_path: Path | None = None,
) -> dict[str, object]:
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
                )
            )
        covered_mutation_allow_actions = {
            "lineage_integrate",
            "proposal_adopt",
            "generate_immutable_manifest",
            "quarantine_clear",
        }
        for row in rows:
            action_kind = str(row.get("action_kind") or "")
            disposition = str(row.get("final_disposition") or "")
            if action_kind in covered_mutation_allow_actions and disposition == "allow":
                missing = _missing_fields(row, REQUIRED_ALLOW_FIELDS)
                if missing:
                    issues.append(
                        VerificationIssue(
                            code="decision_missing_required_allow_fields",
                            detail=f"{correlation_id}: action_kind={action_kind} missing={','.join(sorted(missing))}",
                        )
                    )
            elif action_kind in covered_mutation_allow_actions and disposition in NON_EXECUTION_DISPOSITIONS:
                missing = _missing_fields(row, REQUIRED_NON_EXECUTION_FIELDS)
                if missing:
                    issues.append(
                        VerificationIssue(
                            code="decision_missing_required_non_execution_fields",
                            detail=f"{correlation_id}: action_kind={action_kind} missing={','.join(sorted(missing))}",
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
                )
            )

    lineage_rows = _read_jsonl(lineage_path or (root / "lineage/lineage.jsonl"))
    for row in lineage_rows:
        correlation_id = str(row.get("correlation_id") or "")
        admission_ref = str(row.get("admission_decision_ref") or "")
        missing = _missing_fields(row, REQUIRED_ALLOW_FIELDS)
        if missing:
            issues.append(VerificationIssue(code="missing_lineage_admission_link", detail=json.dumps(row, sort_keys=True)))
            continue
        if not _validate_ref(correlation_id, admission_ref):
            issues.append(VerificationIssue(code="invalid_lineage_admission_ref", detail=json.dumps(row, sort_keys=True)))
        _require_allow_link(correlation_id=correlation_id, action_kind="lineage_integrate", source="lineage")

    resolved_manifest = manifest_path or (root / "vow/immutable_manifest.json")
    if resolved_manifest.exists():
        manifest_payload = json.loads(resolved_manifest.read_text(encoding="utf-8"))
        if isinstance(manifest_payload, dict):
            admission = manifest_payload.get("admission")
            if not isinstance(admission, Mapping):
                issues.append(VerificationIssue(code="missing_manifest_admission_link", detail=str(resolved_manifest)))
            else:
                correlation_id = str(admission.get("correlation_id") or "")
                admission_ref = str(admission.get("admission_decision_ref") or "")
                missing = _missing_fields(admission, REQUIRED_ALLOW_FIELDS)
                if missing:
                    issues.append(VerificationIssue(code="invalid_manifest_admission_link", detail=str(resolved_manifest)))
                else:
                    if not _validate_ref(correlation_id, admission_ref):
                        issues.append(VerificationIssue(code="invalid_manifest_admission_ref", detail=str(resolved_manifest)))
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
            issues.append(VerificationIssue(code="missing_quarantine_correlation", detail=json.dumps(row, sort_keys=True)))
            continue
        admission_ref = str(row.get("admission_decision_ref") or "")
        if not _validate_ref(correlation_id, admission_ref):
            issues.append(VerificationIssue(code="invalid_quarantine_admission_ref", detail=json.dumps(row, sort_keys=True)))
        if event == "integrity_recovered":
            _require_allow_link(correlation_id=correlation_id, action_kind="quarantine_clear", source="quarantine_clear")
        else:
            denied_rows = decisions_by_correlation.get(correlation_id, [])
            if any(str(item.get("final_disposition") or "") == "allow" for item in denied_rows):
                issues.append(
                    VerificationIssue(
                        code="denied_event_has_allow_decision",
                        detail=f"kernel_admission_denied with allow decision: {correlation_id}",
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
            issues.append(VerificationIssue(code="missing_repair_admission_link", detail=json.dumps(row, sort_keys=True)))
            continue
        admission_ref = str(kernel_admission.get("admission_decision_ref") or "")
        if not _validate_ref(correlation_id, admission_ref):
            issues.append(VerificationIssue(code="invalid_repair_admission_ref", detail=json.dumps(row, sort_keys=True)))
        disposition = str(kernel_admission.get("final_disposition") or "")
        if status == "auto-repair verified":
            _require_allow_link(correlation_id=correlation_id, action_kind=str(kernel_admission.get("action_kind") or ""), source="repair")
        if status == "auto-repair verified" and disposition != "allow":
            issues.append(
                VerificationIssue(
                    code="repair_verified_without_allow",
                    detail=f"status=auto-repair verified correlation={correlation_id} disposition={disposition}",
                )
            )
        if status in {"auto-repair denied_by_governor", "auto-repair quarantined"} and disposition == "allow":
            issues.append(
                VerificationIssue(
                    code="repair_denied_with_allow",
                    detail=f"status=auto-repair denied_by_governor correlation={correlation_id}",
                )
            )

    for correlation_id, rows in decisions_by_correlation.items():
        for row in rows:
            action_kind = str(row.get("action_kind") or "")
            if action_kind not in {"lineage_integrate", "proposal_adopt", "generate_immutable_manifest", "quarantine_clear"}:
                continue
            if str(row.get("final_disposition") or "") != "allow":
                continue
            if action_kind == "lineage_integrate" and not any(
                str(item.get("correlation_id") or "") == correlation_id for item in lineage_rows
            ):
                issues.append(VerificationIssue(code="missing_expected_lineage_side_effect", detail=correlation_id))
            if action_kind == "generate_immutable_manifest":
                if not resolved_manifest.exists():
                    issues.append(VerificationIssue(code="missing_expected_manifest_side_effect", detail=correlation_id))
                else:
                    manifest_payload = json.loads(resolved_manifest.read_text(encoding="utf-8"))
                    admission = manifest_payload.get("admission") if isinstance(manifest_payload, Mapping) else None
                    if not isinstance(admission, Mapping) or str(admission.get("correlation_id") or "") != correlation_id:
                        issues.append(VerificationIssue(code="missing_expected_manifest_side_effect", detail=correlation_id))
            if action_kind == "quarantine_clear" and not any(
                str(item.get("event") or "") == "integrity_recovered" and str(item.get("correlation_id") or "") == correlation_id
                for item in forge_rows
            ):
                issues.append(VerificationIssue(code="missing_expected_quarantine_clear_side_effect", detail=correlation_id))

    return {
        "ok": not issues,
        "issue_count": len(issues),
        "issues": [issue.to_dict() for issue in issues],
        "checked": {
            "kernel_decisions": len(decision_rows),
            "lineage_entries": len(lineage_rows),
            "forge_events": len(forge_rows),
        },
    }
