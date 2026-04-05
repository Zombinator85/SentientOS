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

_TRACE_CATALOG: dict[str, dict[str, str]] = {
    "sentientos.manifest.generate": {
        "typed_action_identity": "sentientos.manifest.generate",
        "router_execution_surface": "pulse/forge_events.jsonl:event=constitutional_mutation_router_execution",
        "kernel_admission_surface": "glow/control_plane/kernel_decisions.jsonl:event_type=control_plane_decision",
        "canonical_handler": "scripts.generate_immutable_manifest.generate_manifest",
        "side_effect_surface": "vow/immutable_manifest.json:admission",
        "proof_surface": "vow/immutable_manifest.json:admission",
        "corridor_surface": "sentientos/protected_mutation_corridor.py:immutable_manifest_identity_writes",
        "trust_surfaces": "runtime_governor/proof_budget(authority_of_judgment when present)",
    },
    "sentientos.quarantine.clear": {
        "typed_action_identity": "sentientos.quarantine.clear",
        "router_execution_surface": "pulse/forge_events.jsonl:event=constitutional_mutation_router_execution",
        "kernel_admission_surface": "glow/control_plane/kernel_decisions.jsonl:event_type=control_plane_decision",
        "canonical_handler": "sentientos.integrity_quarantine.clear",
        "side_effect_surface": "pulse/forge_events.jsonl:event=integrity_recovered",
        "proof_surface": "pulse/forge_events.jsonl:event=integrity_recovered",
        "corridor_surface": "sentientos/protected_mutation_corridor.py:quarantine_clear_privileged_operator_action",
        "trust_surfaces": "receipt_chain/receipt_anchor/audit_chain/federation_integrity",
    },
    "sentientos.genesis.lineage_integrate": {
        "typed_action_identity": "sentientos.genesis.lineage_integrate",
        "router_execution_surface": "pulse/forge_events.jsonl:event=constitutional_mutation_router_execution",
        "kernel_admission_surface": "glow/control_plane/kernel_decisions.jsonl:event_type=control_plane_decision",
        "canonical_handler": "sentientos.genesis_forge.SpecBinder.integrate",
        "side_effect_surface": "lineage/lineage.jsonl entry + daemon spec write",
        "proof_surface": "lineage/lineage.jsonl (canonical tuple + daemon_spec_path)",
        "corridor_surface": "sentientos/protected_mutation_corridor.py:genesisforge_lineage_proposal_adoption",
        "trust_surfaces": "runtime_governor/proof_budget(authority_of_judgment when present)",
    },
    "sentientos.genesis.proposal_adopt": {
        "typed_action_identity": "sentientos.genesis.proposal_adopt",
        "router_execution_surface": "pulse/forge_events.jsonl:event=constitutional_mutation_router_execution",
        "kernel_admission_surface": "glow/control_plane/kernel_decisions.jsonl:event_type=control_plane_decision",
        "canonical_handler": "sentientos.genesis_forge.AdoptionRite.promote",
        "side_effect_surface": "live mount json + codex index entry (with lineage linkage fields)",
        "proof_surface": "live mount json admission + codex index admission + codex lineage_* linkage",
        "corridor_surface": "sentientos/protected_mutation_corridor.py:genesisforge_lineage_proposal_adoption",
        "trust_surfaces": "runtime_governor/proof_budget(authority_of_judgment when present)",
    },
    "sentientos.codexhealer.repair": {
        "typed_action_identity": "sentientos.codexhealer.repair",
        "router_execution_surface": "pulse/forge_events.jsonl:event=constitutional_mutation_router_execution",
        "kernel_admission_surface": "glow/control_plane/kernel_decisions.jsonl:event_type=control_plane_decision",
        "canonical_handler": "sentientos.codex_healer.RepairSynthesizer.apply",
        "side_effect_surface": "healer_runtime.log.jsonl entries",
        "proof_surface": "healer_runtime.log.jsonl details.kernel_admission",
        "corridor_surface": "sentientos/protected_mutation_corridor.py:codexhealer_repair_regenesis_linkage",
        "trust_surfaces": "review_board + runtime_governor + regenesis threshold",
    },
    "sentientos.merge_train.hold": {
        "typed_action_identity": "sentientos.merge_train.hold",
        "router_execution_surface": "pulse/forge_events.jsonl:event=constitutional_mutation_router_execution",
        "kernel_admission_surface": "glow/control_plane/kernel_decisions.jsonl:event_type=control_plane_decision",
        "canonical_handler": "sentientos.forge_merge_train.ForgeMergeTrain._apply_hold_transition",
        "side_effect_surface": "glow/forge/merge_train.json + pulse/forge_train_events.jsonl",
        "proof_surface": "pulse/forge_train_events.jsonl:event=train_held",
        "corridor_surface": "sentientos/protected_mutation_corridor.py:merge_train_protected_mutation_hold_release",
        "trust_surfaces": "runtime_governor/proof_budget(authority_of_judgment when present)",
    },
    "sentientos.merge_train.release": {
        "typed_action_identity": "sentientos.merge_train.release",
        "router_execution_surface": "pulse/forge_events.jsonl:event=constitutional_mutation_router_execution",
        "kernel_admission_surface": "glow/control_plane/kernel_decisions.jsonl:event_type=control_plane_decision",
        "canonical_handler": "sentientos.forge_merge_train.ForgeMergeTrain._apply_release_transition",
        "side_effect_surface": "glow/forge/merge_train.json + pulse/forge_train_events.jsonl",
        "proof_surface": "pulse/forge_train_events.jsonl:event=train_released",
        "corridor_surface": "sentientos/protected_mutation_corridor.py:merge_train_protected_mutation_hold_release",
        "trust_surfaces": "runtime_governor/proof_budget(authority_of_judgment when present)",
    },
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


def _latest_router_event(rows: list[dict[str, Any]], action_id: str) -> dict[str, Any] | None:
    for row in reversed(rows):
        if row.get("event") == "constitutional_mutation_router_execution" and row.get("typed_action_id") == action_id:
            return row
    return None


def _find_kernel_row(kernel_rows: list[dict[str, Any]], correlation_id: str) -> dict[str, Any] | None:
    for row in reversed(kernel_rows):
        if str(row.get("correlation_id") or "") == correlation_id:
            return row
    return None


def _manifest_side_effect_status(repo_root: Path, correlation_id: str) -> tuple[str, list[dict[str, str]]]:
    payload = _read_json(repo_root / "vow/immutable_manifest.json")
    if not isinstance(payload, dict):
        return "unresolved_side_effect_link", [{"kind": "missing_manifest_artifact", "path": "vow/immutable_manifest.json"}]
    admission = payload.get("admission")
    if not isinstance(admission, dict):
        return "unresolved_side_effect_link", [{"kind": "missing_manifest_admission"}]
    if str(admission.get("correlation_id") or "") != correlation_id:
        return "unresolved_side_effect_link", [{"kind": "correlation_mismatch", "surface": "vow/immutable_manifest.json:admission"}]
    if str(admission.get("typed_action_id") or "") != "sentientos.manifest.generate":
        return "missing_canonical_linkage", [{"kind": "typed_action_missing", "surface": "vow/immutable_manifest.json:admission"}]
    return "trace_complete", []


def _merge_train_side_effect_status(
    *,
    action_id: str,
    correlation_id: str,
    train_event_rows: list[dict[str, Any]],
) -> tuple[str, list[dict[str, str]]]:
    expected_event = "train_held" if action_id.endswith(".hold") else "train_released"
    for row in reversed(train_event_rows):
        if row.get("event") != expected_event:
            continue
        if str(row.get("correlation_id") or "") != correlation_id:
            continue
        if str(row.get("admission_decision_ref") or "") != f"kernel_decision:{correlation_id}":
            return "missing_canonical_linkage", [{"kind": "missing_admission_ref", "surface": f"pulse/forge_train_events.jsonl:{expected_event}"}]
        if str(row.get("typed_action_id") or "") != action_id:
            return "missing_canonical_linkage", [{"kind": "missing_typed_action", "surface": f"pulse/forge_train_events.jsonl:{expected_event}"}]
        return "trace_complete", []
    return "unresolved_side_effect_link", [{"kind": "missing_merge_train_event", "surface": f"pulse/forge_train_events.jsonl:{expected_event}"}]


def _genesis_proposal_adopt_side_effect_status(repo_root: Path, correlation_id: str) -> tuple[str, list[dict[str, str]]]:
    live_mount = repo_root / "live"
    live_candidates = sorted(live_mount.glob("*.json")) if live_mount.exists() else []
    for path in live_candidates:
        payload = _read_json(path)
        if not isinstance(payload, dict):
            continue
        admission = payload.get("admission")
        if not isinstance(admission, dict):
            continue
        if str(admission.get("correlation_id") or "") != correlation_id:
            continue
        if str(admission.get("admission_decision_ref") or "") != f"kernel_decision:{correlation_id}":
            return "missing_canonical_linkage", [{"kind": "missing_admission_ref", "surface": f"{path.as_posix()}:admission"}]
        if str(admission.get("typed_action_id") or "") != "sentientos.genesis.proposal_adopt":
            return "missing_canonical_linkage", [{"kind": "missing_typed_action", "surface": f"{path.as_posix()}:admission"}]
        codex_payload = _read_json(repo_root / "codex.json")
        if not isinstance(codex_payload, list):
            return "unresolved_side_effect_link", [{"kind": "missing_codex_index", "surface": "codex.json"}]
        for row in codex_payload:
            if not isinstance(row, dict):
                continue
            row_admission = row.get("admission")
            if not isinstance(row_admission, dict):
                continue
            if str(row_admission.get("correlation_id") or "") != correlation_id:
                continue
            if str(row_admission.get("admission_decision_ref") or "") != f"kernel_decision:{correlation_id}":
                return "missing_canonical_linkage", [{"kind": "codex_missing_admission_ref", "surface": "codex.json:admission"}]
            if str(row_admission.get("typed_action_id") or "") != "sentientos.genesis.proposal_adopt":
                return "missing_canonical_linkage", [{"kind": "codex_missing_typed_action", "surface": "codex.json:admission"}]
            if str(row.get("lineage_typed_action_id") or "") != "sentientos.genesis.lineage_integrate":
                return "missing_canonical_linkage", [{"kind": "codex_missing_lineage_typed_action", "surface": "codex.json:lineage_typed_action_id"}]
            if str(row.get("lineage_correlation_id") or "") == "":
                return "missing_canonical_linkage", [{"kind": "codex_missing_lineage_correlation_id", "surface": "codex.json:lineage_correlation_id"}]
            if str(row.get("lineage_admission_decision_ref") or "") == "":
                return "missing_canonical_linkage", [
                    {"kind": "codex_missing_lineage_admission_decision_ref", "surface": "codex.json:lineage_admission_decision_ref"}
                ]
            return "trace_complete", []
        return "unresolved_side_effect_link", [{"kind": "missing_codex_adoption_entry", "surface": "codex.json"}]
    return "unresolved_side_effect_link", [{"kind": "missing_live_adoption_artifact", "surface": "live/*.json"}]


def _genesis_lineage_integrate_side_effect_status(repo_root: Path, correlation_id: str) -> tuple[str, list[dict[str, str]]]:
    lineage_rows = _read_jsonl(repo_root / "lineage/lineage.jsonl")
    for row in reversed(lineage_rows):
        if str(row.get("correlation_id") or "") != correlation_id:
            continue
        if str(row.get("admission_decision_ref") or "") != f"kernel_decision:{correlation_id}":
            return "missing_canonical_linkage", [{"kind": "lineage_missing_admission_ref", "surface": "lineage/lineage.jsonl"}]
        if str(row.get("typed_action_id") or "") != "sentientos.genesis.lineage_integrate":
            return "missing_canonical_linkage", [{"kind": "lineage_missing_typed_action", "surface": "lineage/lineage.jsonl"}]
        daemon_spec_path = str(row.get("daemon_spec_path") or "").strip()
        if not daemon_spec_path:
            return "missing_canonical_linkage", [{"kind": "lineage_missing_daemon_spec_path", "surface": "lineage/lineage.jsonl"}]
        if not (repo_root / daemon_spec_path).exists():
            return "unresolved_side_effect_link", [{"kind": "lineage_daemon_spec_missing", "surface": daemon_spec_path}]
        return "trace_complete", []
    return "unresolved_side_effect_link", [{"kind": "missing_lineage_artifact", "surface": "lineage/lineage.jsonl"}]


def evaluate_scoped_trace_completeness(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    router_rows = _read_jsonl(root / "pulse/forge_events.jsonl")
    kernel_rows = _read_jsonl(root / "glow/control_plane/kernel_decisions.jsonl")
    merge_train_rows = _read_jsonl(root / "pulse/forge_train_events.jsonl")

    action_rows: list[dict[str, Any]] = []
    for action_id in SCOPED_ACTION_IDS:
        map_row = _TRACE_CATALOG[action_id]
        router_event = _latest_router_event(router_rows, action_id)
        if router_event is None:
            action_rows.append(
                {
                    **map_row,
                    "status": "trace_partially_fragmented",
                    "linkage_findings": [{"kind": "router_event_not_observed"}],
                }
            )
            continue
        correlation_id = str(router_event.get("correlation_id") or "")
        if not correlation_id:
            action_rows.append(
                {
                    **map_row,
                    "status": "missing_canonical_linkage",
                    "linkage_findings": [{"kind": "router_correlation_missing"}],
                }
            )
            continue
        kernel_row = _find_kernel_row(kernel_rows, correlation_id)
        if kernel_row is None:
            action_rows.append(
                {
                    **map_row,
                    "status": "missing_canonical_linkage",
                    "correlation_id": correlation_id,
                    "linkage_findings": [{"kind": "kernel_decision_missing"}],
                }
            )
            continue
        if str(kernel_row.get("admission_decision_ref") or "") != f"kernel_decision:{correlation_id}":
            action_rows.append(
                {
                    **map_row,
                    "status": "missing_canonical_linkage",
                    "correlation_id": correlation_id,
                    "linkage_findings": [{"kind": "kernel_admission_ref_mismatch"}],
                }
            )
            continue

        status = "trace_partially_fragmented"
        findings: list[dict[str, str]] = []
        if action_id == "sentientos.manifest.generate":
            status, findings = _manifest_side_effect_status(root, correlation_id)
        elif action_id in {"sentientos.merge_train.hold", "sentientos.merge_train.release"}:
            status, findings = _merge_train_side_effect_status(
                action_id=action_id,
                correlation_id=correlation_id,
                train_event_rows=merge_train_rows,
            )
        elif action_id == "sentientos.quarantine.clear":
            matched = any(
                str(row.get("correlation_id") or "") == correlation_id and row.get("event") == "integrity_recovered"
                for row in router_rows
            )
            if matched:
                status = "trace_complete"
            else:
                status = "unresolved_side_effect_link"
                findings = [{"kind": "missing_integrity_recovered_event"}]
        elif action_id == "sentientos.genesis.proposal_adopt":
            status, findings = _genesis_proposal_adopt_side_effect_status(root, correlation_id)
        elif action_id == "sentientos.genesis.lineage_integrate":
            status, findings = _genesis_lineage_integrate_side_effect_status(root, correlation_id)
        else:
            status = "trace_partially_fragmented"
            findings = [{"kind": "side_effect_resolution_not_yet_scoped"}]

        action_rows.append(
            {
                **map_row,
                "status": status,
                "correlation_id": correlation_id,
                "admission_decision_ref": f"kernel_decision:{correlation_id}",
                "router_event": {
                    "canonical_router": router_event.get("canonical_router"),
                    "canonical_handler": router_event.get("canonical_handler"),
                    "path_status": router_event.get("path_status"),
                    "final_disposition": router_event.get("final_disposition"),
                },
                "kernel_decision": {
                    "final_disposition": kernel_row.get("final_disposition"),
                    "reason_codes": kernel_row.get("reason_codes", []),
                    "delegate_checks_consulted": kernel_row.get("delegate_checks_consulted", []),
                },
                "linkage_findings": findings,
            }
        )

    status_order = {
        "trace_complete": 0,
        "trace_partially_fragmented": 1,
        "unresolved_side_effect_link": 2,
        "missing_canonical_linkage": 3,
    }
    overall = max((row.get("status", "trace_partially_fragmented") for row in action_rows), key=lambda item: status_order.get(str(item), 99))
    return {
        "scope": "constitutional_execution_fabric_scoped_slice",
        "status": overall,
        "actions": action_rows,
    }


def build_scoped_trace_coherence_map(repo_root: Path) -> dict[str, Any]:
    return evaluate_scoped_trace_completeness(repo_root)
