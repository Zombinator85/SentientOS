from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCOPED_ACTION_IDS: tuple[str, ...] = (
    "sentientos.manifest.generate",
    "sentientos.quarantine.clear",
    "sentientos.genesis.lineage_integrate",
    "sentientos.genesis.proposal_adopt",
    "sentientos.codexhealer.repair",
    "sentientos.merge_train.hold",
    "sentientos.merge_train.release",
)

_EXPECTED_HANDLERS: dict[str, str] = {
    "sentientos.manifest.generate": "scripts.generate_immutable_manifest.generate_manifest",
    "sentientos.quarantine.clear": "sentientos.integrity_quarantine.clear",
    "sentientos.genesis.lineage_integrate": "sentientos.genesis_forge.SpecBinder.integrate",
    "sentientos.genesis.proposal_adopt": "sentientos.genesis_forge.AdoptionRite.promote",
    "sentientos.codexhealer.repair": "sentientos.codex_healer.RepairSynthesizer.apply",
    "sentientos.merge_train.hold": "sentientos.forge_merge_train.ForgeMergeTrain._apply_hold_transition",
    "sentientos.merge_train.release": "sentientos.forge_merge_train.ForgeMergeTrain._apply_release_transition",
}


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if isinstance(payload, (dict, list)):
        return payload
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _find_router_event(rows: list[dict[str, Any]], action_id: str, correlation_id: str) -> dict[str, Any] | None:
    for row in reversed(rows):
        if row.get("event") != "constitutional_mutation_router_execution":
            continue
        if str(row.get("typed_action_id") or "") != action_id:
            continue
        if str(row.get("correlation_id") or "") != correlation_id:
            continue
        return row
    return None


def _find_kernel_row(rows: list[dict[str, Any]], correlation_id: str) -> dict[str, Any] | None:
    for row in reversed(rows):
        if str(row.get("correlation_id") or "") == correlation_id:
            return row
    return None


def _side_effect_and_proof_state(
    *,
    repo_root: Path,
    action_id: str,
    correlation_id: str,
    router_rows: list[dict[str, Any]],
    train_rows: list[dict[str, Any]],
) -> tuple[str, str, list[dict[str, str]]]:
    findings: list[dict[str, str]] = []

    if action_id == "sentientos.manifest.generate":
        payload = _read_json(repo_root / "vow/immutable_manifest.json")
        if not isinstance(payload, dict):
            return "absent", "absent", [{"kind": "manifest_missing", "surface": "vow/immutable_manifest.json"}]
        admission = payload.get("admission")
        if not isinstance(admission, dict):
            return "absent", "absent", [{"kind": "manifest_admission_missing", "surface": "vow/immutable_manifest.json:admission"}]
        if str(admission.get("correlation_id") or "") != correlation_id:
            return "absent", "fragmented", [{"kind": "manifest_correlation_mismatch", "surface": "vow/immutable_manifest.json:admission"}]
        if str(admission.get("typed_action_id") or "") != action_id:
            return "present", "fragmented", [{"kind": "manifest_typed_action_mismatch", "surface": "vow/immutable_manifest.json:admission"}]
        return "present", "present", findings

    if action_id in {"sentientos.merge_train.hold", "sentientos.merge_train.release"}:
        expected_event = "train_held" if action_id.endswith(".hold") else "train_released"
        for row in reversed(train_rows):
            if row.get("event") != expected_event:
                continue
            if str(row.get("correlation_id") or "") != correlation_id:
                continue
            proof_state = "present"
            if str(row.get("typed_action_id") or "") != action_id:
                proof_state = "fragmented"
                findings.append({"kind": "merge_train_typed_action_mismatch", "surface": f"pulse/forge_train_events.jsonl:{expected_event}"})
            if str(row.get("admission_decision_ref") or "") != f"kernel_decision:{correlation_id}":
                proof_state = "fragmented"
                findings.append({"kind": "merge_train_admission_ref_missing", "surface": f"pulse/forge_train_events.jsonl:{expected_event}"})
            return "present", proof_state, findings
        return "absent", "absent", [{"kind": "merge_train_side_effect_missing", "surface": f"pulse/forge_train_events.jsonl:{expected_event}"}]

    if action_id == "sentientos.quarantine.clear":
        for row in reversed(router_rows):
            if row.get("event") != "integrity_recovered":
                continue
            if str(row.get("correlation_id") or "") != correlation_id:
                continue
            return "present", "present", findings
        return "absent", "absent", [{"kind": "quarantine_side_effect_missing", "surface": "pulse/forge_events.jsonl:integrity_recovered"}]

    if action_id == "sentientos.genesis.lineage_integrate":
        lineage_rows = _read_jsonl(repo_root / "lineage/lineage.jsonl")
        for row in reversed(lineage_rows):
            if str(row.get("correlation_id") or "") != correlation_id:
                continue
            proof_state = "present"
            if str(row.get("typed_action_id") or "") != action_id:
                proof_state = "fragmented"
                findings.append({"kind": "lineage_typed_action_mismatch", "surface": "lineage/lineage.jsonl"})
            if str(row.get("admission_decision_ref") or "") != f"kernel_decision:{correlation_id}":
                proof_state = "fragmented"
                findings.append({"kind": "lineage_admission_ref_missing", "surface": "lineage/lineage.jsonl"})
            daemon_spec_path = str(row.get("daemon_spec_path") or "").strip()
            if not daemon_spec_path:
                proof_state = "fragmented"
                findings.append({"kind": "lineage_daemon_spec_path_missing", "surface": "lineage/lineage.jsonl:daemon_spec_path"})
            elif not (repo_root / daemon_spec_path).exists():
                return "fragmented", "fragmented", [{"kind": "lineage_daemon_spec_missing", "surface": daemon_spec_path}]
            return "present", proof_state, findings
        return "absent", "absent", [{"kind": "lineage_side_effect_missing", "surface": "lineage/lineage.jsonl"}]

    if action_id == "sentientos.genesis.proposal_adopt":
        live_mount = repo_root / "live"
        candidates = sorted(live_mount.glob("*.json")) if live_mount.exists() else []
        for path in candidates:
            payload = _read_json(path)
            if not isinstance(payload, dict):
                continue
            admission = payload.get("admission")
            if not isinstance(admission, dict):
                continue
            if str(admission.get("correlation_id") or "") != correlation_id:
                continue
            proof_state = "present"
            if str(admission.get("typed_action_id") or "") != action_id:
                proof_state = "fragmented"
                findings.append({"kind": "adopt_live_typed_action_mismatch", "surface": f"{path.as_posix()}:admission"})
            if str(admission.get("admission_decision_ref") or "") != f"kernel_decision:{correlation_id}":
                proof_state = "fragmented"
                findings.append({"kind": "adopt_live_admission_ref_missing", "surface": f"{path.as_posix()}:admission"})
            codex_payload = _read_json(repo_root / "codex.json")
            if not isinstance(codex_payload, list):
                return "fragmented", "fragmented", [{"kind": "codex_missing", "surface": "codex.json"}]
            codex_row = None
            for row in codex_payload:
                if isinstance(row, dict) and isinstance(row.get("admission"), dict):
                    if str(row["admission"].get("correlation_id") or "") == correlation_id:
                        codex_row = row
                        break
            if codex_row is None:
                return "fragmented", "fragmented", [{"kind": "codex_adoption_entry_missing", "surface": "codex.json"}]
            codex_admission = codex_row.get("admission") if isinstance(codex_row, dict) else None
            if not isinstance(codex_admission, dict):
                return "fragmented", "fragmented", [{"kind": "codex_admission_missing", "surface": "codex.json:admission"}]
            if str(codex_admission.get("typed_action_id") or "") != action_id:
                proof_state = "fragmented"
                findings.append({"kind": "codex_adopt_typed_action_mismatch", "surface": "codex.json:admission"})
            if str(codex_admission.get("admission_decision_ref") or "") != f"kernel_decision:{correlation_id}":
                proof_state = "fragmented"
                findings.append({"kind": "codex_adopt_admission_ref_missing", "surface": "codex.json:admission"})
            if str(codex_row.get("lineage_typed_action_id") or "") != "sentientos.genesis.lineage_integrate":
                proof_state = "fragmented"
                findings.append({"kind": "codex_lineage_link_missing", "surface": "codex.json:lineage_typed_action_id"})
            return "present", proof_state, findings
        return "absent", "absent", [{"kind": "adopt_live_artifact_missing", "surface": "live/*.json"}]

    if action_id == "sentientos.codexhealer.repair":
        rows = _read_jsonl(repo_root / "integration/healer_runtime.log.jsonl")
        for row in reversed(rows):
            if str(row.get("correlation_id") or "") != correlation_id:
                continue
            canonical_admission = row.get("canonical_admission")
            details = row.get("details")
            kernel_admission = details.get("kernel_admission") if isinstance(details, dict) else None
            proof_state = "present"
            if not isinstance(canonical_admission, dict):
                return "fragmented", "fragmented", [{"kind": "healer_canonical_admission_missing", "surface": "integration/healer_runtime.log.jsonl:canonical_admission"}]
            if str(canonical_admission.get("typed_action_id") or "") != action_id:
                proof_state = "fragmented"
                findings.append({"kind": "healer_typed_action_mismatch", "surface": "integration/healer_runtime.log.jsonl:canonical_admission"})
            if str(canonical_admission.get("admission_decision_ref") or "") != f"kernel_decision:{correlation_id}":
                proof_state = "fragmented"
                findings.append({"kind": "healer_admission_ref_missing", "surface": "integration/healer_runtime.log.jsonl:canonical_admission"})
            if not isinstance(kernel_admission, dict):
                proof_state = "fragmented"
                findings.append({"kind": "healer_kernel_admission_missing", "surface": "integration/healer_runtime.log.jsonl:details.kernel_admission"})
            return "present", proof_state, findings
        return "absent", "absent", [{"kind": "healer_row_missing", "surface": "integration/healer_runtime.log.jsonl"}]

    return "unknown", "unknown", [{"kind": "unsupported_action"}]


def resolve_scoped_mutation_lifecycle(repo_root: Path, *, action_id: str, correlation_id: str) -> dict[str, Any]:
    if action_id not in SCOPED_ACTION_IDS:
        raise ValueError(f"action_out_of_scope:{action_id}")

    root = repo_root.resolve()
    router_rows = _read_jsonl(root / "pulse/forge_events.jsonl")
    kernel_rows = _read_jsonl(root / "glow/control_plane/kernel_decisions.jsonl")
    train_rows = _read_jsonl(root / "pulse/forge_train_events.jsonl")

    findings: list[dict[str, str]] = []
    router_event = _find_router_event(router_rows, action_id, correlation_id)
    kernel_row = _find_kernel_row(kernel_rows, correlation_id)

    if router_event is None:
        findings.append({"kind": "router_event_missing", "surface": "pulse/forge_events.jsonl"})
    if kernel_row is None:
        findings.append({"kind": "kernel_decision_missing", "surface": "glow/control_plane/kernel_decisions.jsonl"})

    final_disposition = "unknown"
    execution_status = "unknown"
    canonical_handler = _EXPECTED_HANDLERS[action_id]
    if isinstance(router_event, dict):
        execution_status = str(router_event.get("execution_status") or "unknown")
        canonical_handler = str(router_event.get("canonical_handler") or canonical_handler)
    if isinstance(kernel_row, dict):
        final_disposition = str(kernel_row.get("final_disposition") or "unknown")
    elif isinstance(router_event, dict):
        final_disposition = str(router_event.get("final_disposition") or "unknown")

    side_effect_state = "unknown"
    proof_linkage_state = "unknown"
    side_effect_findings: list[dict[str, str]] = []

    if final_disposition in {"allow", "deny", "defer", "quarantine"}:
        side_effect_state, proof_linkage_state, side_effect_findings = _side_effect_and_proof_state(
            repo_root=root,
            action_id=action_id,
            correlation_id=correlation_id,
            router_rows=router_rows,
            train_rows=train_rows,
        )
        findings.extend(side_effect_findings)

    outcome_class = "fragmented_unresolved"
    if final_disposition in {"deny", "defer", "quarantine"}:
        has_execution = bool((router_event or {}).get("executed"))
        if has_execution:
            findings.append({"kind": "denied_execution_flag_true", "surface": "pulse/forge_events.jsonl:constitutional_mutation_router_execution.executed"})
            outcome_class = "fragmented_unresolved"
        elif side_effect_state == "absent":
            outcome_class = "denied"
        else:
            findings.append({"kind": "denied_side_effect_leak", "surface": "scoped_side_effect_surfaces"})
            outcome_class = "fragmented_unresolved"
    elif final_disposition == "allow":
        if execution_status == "failed":
            failure = (router_event or {}).get("failure")
            partial = str((router_event or {}).get("partial_side_effect_state") or "")
            if isinstance(failure, dict) and str(failure.get("exception_type") or "") and partial == "unknown_partial_side_effects_possible":
                outcome_class = "failed_after_admission"
            else:
                findings.append({"kind": "failed_after_admission_payload_fragmented", "surface": "pulse/forge_events.jsonl:constitutional_mutation_router_execution"})
                outcome_class = "fragmented_unresolved"
        elif execution_status == "succeeded":
            if side_effect_state == "present" and proof_linkage_state == "present":
                outcome_class = "success"
            else:
                outcome_class = "fragmented_unresolved"
        else:
            findings.append({"kind": "allow_execution_status_unresolved", "surface": "pulse/forge_events.jsonl:constitutional_mutation_router_execution.execution_status"})
    else:
        findings.append({"kind": "final_disposition_unresolved", "surface": "router_or_kernel"})

    return {
        "typed_action_identity": action_id,
        "correlation_id": correlation_id,
        "canonical_router_execution_status": execution_status,
        "kernel_admission_disposition": final_disposition,
        "canonical_handler_identity": canonical_handler,
        "side_effect_state": side_effect_state,
        "proof_linkage_state": proof_linkage_state,
        "outcome_class": outcome_class,
        "admission_decision_ref": f"kernel_decision:{correlation_id}",
        "findings": findings,
    }
