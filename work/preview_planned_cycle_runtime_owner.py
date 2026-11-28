"""Preview a planned transfer prompt through the resident owner without inference.

The adapter fails closed if the owner attempts to invoke a model. The report
contains protocol bindings and digests only; prompt text and model outputs are
never written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_rootless_ollama_embodied_cognition_cycle import (  # noqa: E402
    ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT,
)

PREVIEW_MAX_INFERENCE_INPUT_CHARS = (
    ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT)

from sentientos.codex_task_authority_admission import (  # noqa: E402
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.developmental_model_replacement_experiment import (  # noqa: E402
    rootless_integer_affine_transfer_task_pair,
)
from sentientos.embodiment_self_observation import (  # noqa: E402
    EmbodimentEvidenceOwner,
    make_synthetic_pre_action_proprioception_observation,
)
from sentientos.local_model_authority import digest_payload  # noqa: E402
from sentientos.resident_developmental_cognition import (  # noqa: E402
    ResidentDevelopmentalCognitionConfig,
    ResidentDevelopmentalCognitionOwner,
)
from sentientos.resident_developmental_writeback import (  # noqa: E402
    ResidentDevelopmentalWritebackController,
)
from sentientos.runtime_admission import (  # noqa: E402
    AdmissionLedger,
    RuntimeAdmissionAuthority,
    RuntimeAdmissionVerifier,
)
from sentientos.world_state_board import (  # noqa: E402
    WorldStateBoardBuilder,
    validate_snapshot,
)
from scripts.preflight_resident_strategy_inclusion_pair import (  # noqa: E402
    _LocalReceiptVerifier,
    _NoInferenceInvoker,
    _copy_without_symlinks,
    _plan_bound_identity,
    _source_kinds_from_history,
)
from work.rootless_history_boundary_campaign import (  # noqa: E402
    _cognition_recovery_state_boundary,
    _history_boundary,
    _load_plan,
    _runtime_admission_boundary,
    verify_experiment_implementation,
    verify_model_identity_recipe,
)


def _read_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("runtime_owner_preview_input_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("runtime_owner_preview_input_invalid")
    return value


def _prompt_size_binding_payload(*, condition_id: str,
        prompt_digest: str, request_digest: str, prompt_chars: int,
        prompt_utf8_bytes: int, history_treatment: str,
        selected_record_ids: list[str],
        selected_record_digests: list[str]) -> dict[str, Any]:
    return {
        "condition_id": condition_id,
        "prompt_digest": prompt_digest,
        "request_digest": request_digest,
        "prompt_chars": prompt_chars,
        "prompt_utf8_bytes": prompt_utf8_bytes,
        "history_treatment": history_treatment,
        "selected_record_ids": selected_record_ids,
        "selected_record_digests": selected_record_digests,
    }


def build_report(*, plan_path: Path, preflight_path: Path,
        prior_history_root: Path, cycle_index: int) -> dict[str, Any]:
    plan = _load_plan(plan_path)
    verify_model_identity_recipe(plan)
    implementation = verify_experiment_implementation(plan)
    preflight = _read_object(preflight_path)
    cycle_ids = plan.get("ordered_cycle_ids")
    seeds = plan.get("ordered_task_generation_seeds")
    if (not isinstance(cycle_ids, list) or not isinstance(seeds, list)
            or type(cycle_index) is not int
            or not 0 <= cycle_index < len(cycle_ids)
            or len(seeds) != len(cycle_ids)):
        raise ValueError("runtime_owner_preview_plan_invalid")
    cycle_id = cycle_ids[cycle_index]
    if (preflight.get("plan_digest") != plan.get("plan_digest")
            or preflight.get("cycle_id") != cycle_id
            or preflight.get("inference_performed") is not False
            or not isinstance(preflight.get("binder_selected_record_ids"), list)
            or not isinstance(preflight.get("binder_selected_record_digests"), list)):
        raise ValueError("runtime_owner_preview_preflight_binding_mismatch")

    source_history = prior_history_root.resolve(strict=True)
    source_resident_root = source_history.parent
    source_state = source_resident_root / "state"
    source_boundary = _history_boundary(source_history)
    if cycle_index == 0:
        if (source_boundary != plan.get("initial_history_boundary")
                or _cognition_recovery_state_boundary(source_state)
                    != plan.get("initial_cognition_recovery_state")
                or _runtime_admission_boundary(source_history)
                    != plan.get("initial_runtime_admission_ledger")):
            raise ValueError("runtime_owner_preview_source_boundary_mismatch")

    identity, request_builder, model_binding = _plan_bound_identity(
        plan_path, cycle_index)
    request_template = {
        "active_model_identity": identity,
        "model_id": model_binding["model_id"],
        "model_artifact_digest": model_binding["model_artifact_digest"],
        "authority_map_digest": model_binding["authority_map_digest"],
    }

    with tempfile.TemporaryDirectory(prefix="sentientos-cross-range-owner-preview-") as temporary:
        temporary_root = Path(temporary)
        resident_root = temporary_root / "resident-cognition"
        _copy_without_symlinks(source_resident_root, resident_root)
        # Recovery-state boundary validation follows observation receipt IDs
        # into the cycle-level inference-custody tree. Copy that immutable
        # receipt scope beside the resident state so the check remains valid
        # inside the isolated preview workspace.
        source_cycle_root = source_resident_root.parent
        source_custody = source_cycle_root / "inference-custody"
        if source_custody.exists():
            _copy_without_symlinks(source_custody,
                temporary_root / "inference-custody")
        history_root = resident_root / "history"
        state_root = resident_root / "state"
        copied_boundary = _history_boundary(history_root)
        if copied_boundary != source_boundary:
            raise ValueError("runtime_owner_preview_history_copy_mismatch")
        before_recovery = _cognition_recovery_state_boundary(state_root)
        before_admission = _runtime_admission_boundary(history_root)

        ledger = AdmissionLedger(state_root / "runtime_admissions.json")
        definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK:
            RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
        writeback = ResidentDevelopmentalWritebackController(
            history_root=history_root,
            admission_verifier=RuntimeAdmissionVerifier(
                definitions=definitions, ledger=ledger),
            current_sequence=ledger.current_sequence)
        invoker = _NoInferenceInvoker(request_template,
            identity_override=identity, request_builder=request_builder)
        owner = ResidentDevelopmentalCognitionOwner(
            config=ResidentDevelopmentalCognitionConfig(
                history_root=history_root, state_root=state_root,
                allowed_source_kinds=_source_kinds_from_history(history_root),
                max_selected_facts=16, max_retrieved_records=4,
                comparison_enabled=True, enabled=True,
                max_inference_timeout_seconds=30,
                max_inference_input_chars=PREVIEW_MAX_INFERENCE_INPUT_CHARS),
            writeback=writeback,
            admission_authority=RuntimeAdmissionAuthority(
                definitions=definitions, ledger=ledger),
            invoker=invoker, current_sequence=ledger.current_sequence,
            invocation_receipt_verifier=_LocalReceiptVerifier(temporary_root))

        task_family = plan["task_family_id"]
        _, transfer_task = rootless_integer_affine_transfer_task_pair(
            seeds[cycle_index], task_family_id=task_family,
            transfer_probe_count=plan.get("transfer_probe_count", 3))
        task_descriptor = transfer_task.public_descriptor()
        if task_descriptor.get("probe_inputs") != preflight.get(
                "transfer_probe_inputs"):
            raise ValueError("runtime_owner_preview_task_probe_binding_mismatch")
        raw_history_allowlist = preflight.get(
            "objective_history_record_allowlist")
        if raw_history_allowlist is None:
            history_record_allowlist = None
        elif (not isinstance(raw_history_allowlist, list)
                or not raw_history_allowlist
                or len(raw_history_allowlist) > 4
                or any(not isinstance(record_id, str) or not record_id
                    for record_id in raw_history_allowlist)
                or len(set(raw_history_allowlist)) != len(raw_history_allowlist)
                or raw_history_allowlist != preflight.get(
                    "binder_selected_record_ids")):
            raise ValueError("runtime_owner_preview_history_allowlist_invalid")
        else:
            history_record_allowlist = tuple(raw_history_allowlist)
        observed_at = datetime.now(timezone.utc).isoformat()
        body = make_synthetic_pre_action_proprioception_observation(
            run_id=cycle_id, pose="idle", observed_at=observed_at)
        snapshot = WorldStateBoardBuilder().build(
            EmbodimentEvidenceOwner([body]).world_state_records())
        if not validate_snapshot(snapshot).valid:
            raise ValueError("runtime_owner_preview_snapshot_invalid")
        preview = owner.preview_objective_history_conditions(
            snapshot=snapshot,
            tick_id=f"cross-range-owner-preview-{cycle_index}",
            objective_task=transfer_task,
            history_record_allowlist=history_record_allowlist)

        expected_ids = preflight["binder_selected_record_ids"]
        expected_digests = preflight["binder_selected_record_digests"]
        arm_requests = [request for request in invoker.requests
            if "objective_task_plan_digest" in request.upstream_evidence]
        if (preview.get("protocol_record_ids") != expected_ids
                or preview.get("protocol_record_digests")
                    != expected_digests
                or preview.get("inference_performed") is not False
                or len(arm_requests) != 3):
            raise ValueError(
                "runtime_owner_preview_history_binding_mismatch:" + json.dumps({
                    "expected_ids": expected_ids,
                    "actual_ids": preview.get("protocol_record_ids"),
                    "expected_digests": expected_digests,
                    "actual_digests": preview.get("protocol_record_digests"),
                    "inference_performed": preview.get("inference_performed"),
                    "request_count": len(invoker.requests),
                    "objective_condition_request_count": len(arm_requests),
                }, sort_keys=True))
        condition_rows = preview.get("conditions")
        if (not isinstance(condition_rows, Mapping)
                or set(condition_rows) != {
                    "history_present", "history_withheld", "history_restored"}):
            raise ValueError("runtime_owner_preview_conditions_missing")
        for condition in ("history_present", "history_withheld",
                "history_restored"):
            row = condition_rows[condition]
            if not isinstance(row, Mapping):
                raise ValueError("runtime_owner_preview_condition_invalid")
            if condition == "history_withheld":
                expected_condition_ids: list[str] = []
                expected_condition_digests: list[str] = []
            else:
                expected_condition_ids = expected_ids
                expected_condition_digests = expected_digests
            if (row.get("selected_record_ids") != expected_condition_ids
                    or row.get("selected_record_digests")
                        != expected_condition_digests
                    or row.get("history_treatment") != (
                        "withheld" if condition == "history_withheld"
                        else "present")):
                raise ValueError(
                    "runtime_owner_preview_condition_history_mismatch:" + json.dumps({
                        "condition": condition,
                        "expected_ids": expected_condition_ids,
                        "actual_ids": row.get("selected_record_ids"),
                        "expected_digests": expected_condition_digests,
                        "actual_digests": row.get("selected_record_digests"),
                    }, sort_keys=True))
        if (any(request.upstream_evidence.get("objective_task_plan_digest") is None
                for request in arm_requests)
                or {"sha256:" + request.request_digest
                    for request in arm_requests}
                    != {"sha256:" + row["request_digest"]
                        for row in condition_rows.values()}):
            raise ValueError(
                "runtime_owner_preview_request_binding_mismatch:" + json.dumps({
                    "all_arm_request_objective_plan_bound": all(
                        request.upstream_evidence.get(
                            "objective_task_plan_digest") is not None
                        for request in arm_requests),
                    "arm_request_digests": [request.request_digest
                        for request in arm_requests],
                    "preview_request_digests": {
                        key: value.get("request_digest")
                        for key, value in condition_rows.items()},
                }, sort_keys=True))

        requests_by_digest = {request.request_digest: request
            for request in arm_requests}
        condition_prompt_sizes: dict[str, dict[str, int]] = {}
        for condition, row in condition_rows.items():
            request = requests_by_digest.get(row.get("request_digest"))
            if request is None:
                raise ValueError(
                    "runtime_owner_preview_prompt_size_request_missing")
            prompt_chars = len(request.prompt)
            prompt_utf8_bytes = len(request.prompt.encode("utf-8"))
            if (request.semantic_payload().get("prompt_size")
                    != prompt_utf8_bytes
                    or prompt_chars > PREVIEW_MAX_INFERENCE_INPUT_CHARS):
                raise ValueError(
                    "runtime_owner_preview_prompt_size_binding_invalid")
            condition_prompt_sizes[condition] = {
                "prompt_chars": prompt_chars,
                "prompt_utf8_bytes": prompt_utf8_bytes,
            }
        condition_prompt_size_binding_digests = {
            condition: "sha256:" + digest_payload(
                _prompt_size_binding_payload(
                    condition_id=condition,
                    prompt_digest=condition_rows[condition]["prompt_digest"],
                    request_digest="sha256:" + condition_rows[condition][
                        "request_digest"],
                    prompt_chars=condition_prompt_sizes[condition][
                        "prompt_chars"],
                    prompt_utf8_bytes=condition_prompt_sizes[condition][
                        "prompt_utf8_bytes"],
                    history_treatment=condition_rows[condition][
                        "history_treatment"],
                    selected_record_ids=list(condition_rows[condition][
                        "selected_record_ids"]),
                    selected_record_digests=list(condition_rows[condition][
                        "selected_record_digests"])))
            for condition in condition_rows}

        after_history = _history_boundary(history_root)
        after_recovery = _cognition_recovery_state_boundary(state_root)
        after_admission = _runtime_admission_boundary(history_root)
        if (after_history != copied_boundary
                or after_recovery != before_recovery
                or after_admission != before_admission):
            raise ValueError("runtime_owner_preview_mutated_copied_state")

        semantic = {
            "schema_version": (
                "sentientos.rootless_planned_cycle_runtime_owner_preview:v5"),
            "campaign_id": plan["campaign_id"],
            "plan_digest": plan["plan_digest"],
            "cycle_id": cycle_id,
            "cycle_index": cycle_index,
            "implementation_digest": implementation[
                "experiment_implementation_digest"],
            "source_history_boundary_digest": source_boundary[
                "boundary_digest"],
            "target_model_identity_digest": "sha256:" + digest_payload({
                "identity": identity}),
            "target_task_family_id": task_family,
            "target_task_digest": task_descriptor["task_digest"],
            "target_task_probe_inputs": list(task_descriptor["probe_inputs"]),
            "snapshot_digest": snapshot.digest,
            "history_record_ids": list(expected_ids),
            "history_record_digests": list(expected_digests),
            "runtime_owner_preview_digest": preview["preview_digest"],
            # Preserve the digest-bound owner payload so an offline reader can
            # recompute the owner's digest and cross-check the flattened report.
            "owner_preview_evidence": {
                key: value for key, value in preview.items()
                if key != "preview_digest"},
            "condition_protocol_digest": preview["protocol_digest"],
            "condition_order": list(preview["condition_order"]),
            "condition_prompt_digests": {
                key: value["prompt_digest"]
                for key, value in condition_rows.items()},
            "condition_prompt_sizes": condition_prompt_sizes,
            "condition_prompt_size_binding_digests": (
                condition_prompt_size_binding_digests),
            "condition_request_digests": {
                key: "sha256:" + value["request_digest"]
                for key, value in condition_rows.items()},
            "condition_task_digests": {
                key: value["objective_task_digest"]
                for key, value in condition_rows.items()},
            "condition_history_treatments": {
                key: value["history_treatment"]
                for key, value in condition_rows.items()},
            "condition_selected_record_ids": {
                key: list(value["selected_record_ids"])
                for key, value in condition_rows.items()},
            "condition_selected_record_digests": {
                key: list(value["selected_record_digests"])
                for key, value in condition_rows.items()},
            "request_count": len(invoker.requests),
            "objective_condition_request_count": len(arm_requests),
            "prompt_limit_chars": PREVIEW_MAX_INFERENCE_INPUT_CHARS,
            "full_prompt_text_included": False,
            "model_outputs_included": False,
            "owner_state_mutated": False,
            "owner_to_binder_path_exercised": True,
            "cross_range_three_condition_prompt_protocol_exercised": True,
            "cross_range_three_condition_runtime_experiment_exercised": False,
            "inference_performed": False,
            "model_attention_established": False,
            "learning_established": False,
            "verification_scope": (
                "owner_payload_digest_and_flattened_report_consistency"),
            "report_origin_attested": False,
            "authority": False,
        }
    report = {**semantic, "audit_digest": digest_payload(semantic)}
    return report


def verify_report(*, report_path: Path, plan_path: Path,
        preflight_path: Path) -> dict[str, Any]:
    """Independently verify a persisted three-condition owner preview."""
    report = _read_object(report_path)
    plan = _load_plan(plan_path)
    verify_model_identity_recipe(plan)
    pinned_implementation = plan.get("experiment_implementation_sha256")
    if not isinstance(pinned_implementation, Mapping):
        raise ValueError("runtime_owner_preview_implementation_unbound")
    pinned_implementation_digest = digest_payload(dict(pinned_implementation))
    try:
        current_implementation = verify_experiment_implementation(plan)
        implementation_matches_current = True
    except ValueError:
        # A historical report remains checkable against its immutable plan
        # after later source revisions. This does not claim current-source
        # reproduction; the result reports that distinction explicitly.
        current_implementation = None
        implementation_matches_current = False
    implementation = {
        "experiment_implementation_digest": pinned_implementation_digest,
        "experiment_implementation_matches_current":
            implementation_matches_current,
        "experiment_implementation_source_count": len(pinned_implementation),
    }
    preflight = _read_object(preflight_path)
    base_keys = {
        "audit_digest", "authority", "campaign_id",
        "condition_history_treatments", "condition_order",
        "condition_prompt_digests", "condition_protocol_digest",
        "condition_request_digests", "condition_selected_record_digests",
        "condition_selected_record_ids",
        "cross_range_three_condition_prompt_protocol_exercised",
        "cross_range_three_condition_runtime_experiment_exercised",
        "cycle_id", "cycle_index", "full_prompt_text_included",
        "history_record_digests", "history_record_ids",
        "implementation_digest", "inference_performed", "learning_established",
        "model_attention_established", "model_outputs_included",
        "objective_condition_request_count", "owner_state_mutated",
        "owner_to_binder_path_exercised", "plan_digest", "request_count",
        "runtime_owner_preview_digest", "schema_version", "snapshot_digest",
        "source_history_boundary_digest", "target_model_identity_digest",
        "target_task_digest", "target_task_family_id",
        "target_task_probe_inputs", "condition_task_digests",
    }
    optional_groups = (
        {"owner_preview_evidence"},
        {"verification_scope", "report_origin_attested"},
    )
    prompt_size_keys = {
        "condition_prompt_sizes", "condition_prompt_size_binding_digests",
        "prompt_limit_chars"}
    allowed_key_sets = {frozenset(base_keys)}
    allowed_key_sets.add(frozenset(base_keys | optional_groups[0]))
    allowed_key_sets.add(frozenset(base_keys | optional_groups[0] | optional_groups[1]))
    allowed_key_sets.add(frozenset(base_keys | prompt_size_keys))
    allowed_key_sets.add(frozenset(base_keys | prompt_size_keys
        | optional_groups[0]))
    allowed_key_sets.add(frozenset(base_keys | prompt_size_keys
        | optional_groups[0] | optional_groups[1]))
    if frozenset(report) not in allowed_key_sets:
        raise ValueError("runtime_owner_preview_report_shape_invalid")
    schema_version = report.get("schema_version")
    has_owner_evidence = "owner_preview_evidence" in report
    has_scope_fields = "verification_scope" in report
    if ((schema_version in {
            "sentientos.rootless_planned_cycle_runtime_owner_preview:v2",
            "sentientos.rootless_planned_cycle_runtime_owner_preview:v3",
            "sentientos.rootless_planned_cycle_runtime_owner_preview:v4",
            "sentientos.rootless_planned_cycle_runtime_owner_preview:v5"}
            and (not has_owner_evidence or not has_scope_fields
                or report.get("verification_scope") !=
                    "owner_payload_digest_and_flattened_report_consistency"
                or report.get("report_origin_attested") is not False))
            or (schema_version ==
                "sentientos.rootless_planned_cycle_runtime_owner_preview:v1"
                and has_scope_fields)
            or schema_version not in {
                "sentientos.rootless_planned_cycle_runtime_owner_preview:v1",
                "sentientos.rootless_planned_cycle_runtime_owner_preview:v2",
                "sentientos.rootless_planned_cycle_runtime_owner_preview:v3",
                "sentientos.rootless_planned_cycle_runtime_owner_preview:v4",
                "sentientos.rootless_planned_cycle_runtime_owner_preview:v5"}):
        raise ValueError("runtime_owner_preview_report_schema_version_invalid")
    has_prompt_sizes = "condition_prompt_sizes" in report
    if ((schema_version in {
            "sentientos.rootless_planned_cycle_runtime_owner_preview:v3",
            "sentientos.rootless_planned_cycle_runtime_owner_preview:v4",
            "sentientos.rootless_planned_cycle_runtime_owner_preview:v5"}
            and (not has_prompt_sizes
                or report.get("prompt_limit_chars")
                    != PREVIEW_MAX_INFERENCE_INPUT_CHARS))
            or (schema_version in {
                "sentientos.rootless_planned_cycle_runtime_owner_preview:v1",
                "sentientos.rootless_planned_cycle_runtime_owner_preview:v2"}
                and has_prompt_sizes)):
        raise ValueError("runtime_owner_preview_prompt_size_schema_invalid")
    semantic = {key: value for key, value in report.items()
        if key != "audit_digest"}
    cycle_ids = plan.get("ordered_cycle_ids")
    identity_digests = plan.get("ordered_model_identity_digests")
    if (not isinstance(cycle_ids, list)
            or not isinstance(identity_digests, list)
            or type(report.get("cycle_index")) is not int
            or not 0 <= report["cycle_index"] < len(cycle_ids)
            or len(identity_digests) != len(cycle_ids)):
        raise ValueError("runtime_owner_preview_plan_index_invalid")
    cycle_index = report["cycle_index"]
    cycle_id = cycle_ids[cycle_index]
    if (report.get("campaign_id") != plan.get("campaign_id")
            or report.get("plan_digest") != plan.get("plan_digest")
            or report.get("cycle_id") != cycle_id
            or report.get("implementation_digest") != implementation.get(
                "experiment_implementation_digest")
            or report.get("target_model_identity_digest")
                != "sha256:" + identity_digests[cycle_index]
            or report.get("target_task_family_id") != plan.get("task_family_id")
            or report.get("audit_digest") != digest_payload(semantic)):
        raise ValueError("runtime_owner_preview_report_plan_binding_invalid")
    if (preflight.get("plan_digest") != plan.get("plan_digest")
            or preflight.get("cycle_id") != cycle_id
            or preflight.get("inference_performed") is not False
            or report.get("history_record_ids")
                != preflight.get("binder_selected_record_ids")
            or report.get("history_record_digests")
                != preflight.get("binder_selected_record_digests")):
        raise ValueError("runtime_owner_preview_preflight_binding_invalid")
    if cycle_index == 0:
        initial_boundary = plan.get("initial_history_boundary")
        if (not isinstance(initial_boundary, Mapping)
                or report.get("source_history_boundary_digest")
                    != initial_boundary.get("boundary_digest")):
            raise ValueError("runtime_owner_preview_initial_boundary_invalid")
    if (not isinstance(report.get("target_task_digest"), str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}",
                report["target_task_digest"]) is None
            or report.get("target_task_probe_inputs")
                != preflight.get("transfer_probe_inputs")):
        raise ValueError("runtime_owner_preview_task_binding_invalid")

    owner_evidence = report.get("owner_preview_evidence")
    owner_evidence_schema = (owner_evidence.get("schema_version")
        if isinstance(owner_evidence, Mapping) else None)
    expected_owner_keys = {
        "schema_version", "tick_id", "snapshot_id", "snapshot_digest",
        "objective_task_digest", "task_family_id", "condition_order",
        "protocol_digest", "protocol_record_ids", "protocol_record_digests",
        "conditions", "history_restoration_exact", "history_withheld_empty",
        "inference_performed", "learning_established", "authority",
    }
    if (owner_evidence is not None and (not isinstance(owner_evidence, Mapping)
            or set(owner_evidence) != expected_owner_keys
            or owner_evidence_schema not in {
                "sentientos.objective_history_conditions_owner_preview:v2",
                "sentientos.objective_history_conditions_owner_preview:v3"}
            or "sha256:" + digest_payload(dict(owner_evidence))
                != report.get("runtime_owner_preview_digest")
            or owner_evidence.get("snapshot_digest")
                != report.get("snapshot_digest")
            or owner_evidence.get("objective_task_digest")
                != report.get("target_task_digest")
            or owner_evidence.get("task_family_id")
                != report.get("target_task_family_id")
            or owner_evidence.get("condition_order")
                != report.get("condition_order")
            or owner_evidence.get("protocol_digest")
                != report.get("condition_protocol_digest")
            or owner_evidence.get("protocol_record_ids")
                != report.get("history_record_ids")
            or owner_evidence.get("protocol_record_digests")
                != report.get("history_record_digests")
            or owner_evidence.get("history_restoration_exact") is not True
            or owner_evidence.get("history_withheld_empty") is not True
            or owner_evidence.get("inference_performed") is not False
            or owner_evidence.get("learning_established") is not False
            or owner_evidence.get("authority") is not False)):
        raise ValueError("runtime_owner_preview_owner_evidence_invalid")

    condition_ids = ("history_present", "history_withheld", "history_restored")
    observed_order = report.get("condition_order")
    if (not isinstance(observed_order, list)
            or len(observed_order) != len(condition_ids)
            or set(observed_order) != set(condition_ids)
            or report.get("condition_history_treatments") != {
                "history_present": "present", "history_withheld": "withheld",
                "history_restored": "present"}
            or report.get("condition_selected_record_ids") != {
                "history_present": report["history_record_ids"],
                "history_withheld": [],
                "history_restored": report["history_record_ids"]}
            or report.get("condition_selected_record_digests") != {
                "history_present": report["history_record_digests"],
                "history_withheld": [],
                "history_restored": report["history_record_digests"]}):
        raise ValueError("runtime_owner_preview_condition_selection_invalid")
    for field in ("condition_prompt_digests", "condition_request_digests",
            "condition_task_digests"):
        values = report.get(field)
        if (not isinstance(values, Mapping) or set(values) != set(condition_ids)
                or any(not isinstance(value, str)
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
                    for value in values.values())):
            raise ValueError("runtime_owner_preview_condition_digest_invalid")
    if has_prompt_sizes:
        prompt_sizes = report.get("condition_prompt_sizes")
        size_binding_digests = report.get(
            "condition_prompt_size_binding_digests")
        if (not isinstance(prompt_sizes, Mapping)
                or set(prompt_sizes) != set(condition_ids)
                or not isinstance(size_binding_digests, Mapping)
                or set(size_binding_digests) != set(condition_ids)
                or any(not isinstance(value, str)
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
                    for value in size_binding_digests.values())
                or any(not isinstance(size, Mapping)
                    or set(size) != {"prompt_chars", "prompt_utf8_bytes"}
                    or type(size.get("prompt_chars")) is not int
                    or type(size.get("prompt_utf8_bytes")) is not int
                    or size["prompt_chars"] <= 0
                    or size["prompt_utf8_bytes"] < size["prompt_chars"]
                    or size["prompt_chars"] > report["prompt_limit_chars"]
                    for size in prompt_sizes.values())):
            raise ValueError("runtime_owner_preview_prompt_sizes_invalid")
        for condition in condition_ids:
            size = prompt_sizes[condition]
            binding_digest = "sha256:" + digest_payload(
                _prompt_size_binding_payload(
                    condition_id=condition,
                    prompt_digest=report["condition_prompt_digests"][condition],
                    request_digest=report["condition_request_digests"][condition],
                    prompt_chars=size["prompt_chars"],
                    prompt_utf8_bytes=size["prompt_utf8_bytes"],
                    history_treatment=report[
                        "condition_history_treatments"][condition],
                    selected_record_ids=report[
                        "condition_selected_record_ids"][condition],
                    selected_record_digests=report[
                        "condition_selected_record_digests"][condition]))
            if binding_digest != size_binding_digests[condition]:
                raise ValueError(
                    "runtime_owner_preview_prompt_size_binding_invalid")
    if any(value != report["target_task_digest"] for value in
            report["condition_task_digests"].values()):
        raise ValueError("runtime_owner_preview_condition_task_binding_invalid")
    owner_conditions = (owner_evidence.get("conditions")
        if isinstance(owner_evidence, Mapping) else None)
    expected_owner_condition_keys = {
        "prompt_digest", "request_digest", "objective_task_digest",
        "history_projection_digest", "history_treatment",
        "selected_record_ids", "selected_record_digests",
        "selected_record_count",
    }
    if owner_evidence_schema in {
            "sentientos.objective_history_conditions_owner_preview:v2",
            "sentientos.objective_history_conditions_owner_preview:v3"}:
        expected_owner_condition_keys.update({
            "projected_example_count", "projected_records"})
    if owner_evidence_schema == (
            "sentientos.objective_history_conditions_owner_preview:v3"):
        expected_owner_condition_keys.update({
            "prompt_chars", "prompt_utf8_bytes"})
    if (owner_evidence is not None and (not isinstance(owner_conditions, Mapping)
            or set(owner_conditions) != set(condition_ids))):
        raise ValueError("runtime_owner_preview_owner_conditions_invalid")
    for condition in condition_ids if owner_evidence is not None else ():
        row = owner_conditions[condition]
        if (not isinstance(row, Mapping)
                or set(row) != expected_owner_condition_keys
                or row.get("prompt_digest")
                    != report["condition_prompt_digests"][condition]
                or not isinstance(row.get("request_digest"), str)
                or "sha256:" + row["request_digest"]
                    != report["condition_request_digests"][condition]
                or row.get("objective_task_digest")
                    != report["condition_task_digests"][condition]
                or row.get("history_treatment")
                    != report["condition_history_treatments"][condition]
                or row.get("selected_record_ids")
                    != report["condition_selected_record_ids"][condition]
                or row.get("selected_record_digests")
                    != report["condition_selected_record_digests"][condition]
                or row.get("selected_record_count") != len(
                    report["condition_selected_record_ids"][condition])
                or (owner_evidence_schema ==
                    "sentientos.objective_history_conditions_owner_preview:v3"
                    and (not isinstance(row.get("prompt_chars"), int)
                        or type(row.get("prompt_chars")) is not int
                        or row["prompt_chars"] <= 0
                        or not isinstance(row.get("prompt_utf8_bytes"), int)
                        or type(row.get("prompt_utf8_bytes")) is not int
                        or row["prompt_utf8_bytes"] < row["prompt_chars"]
                        or not has_prompt_sizes
                        or row["prompt_chars"] != report[
                            "condition_prompt_sizes"][condition]["prompt_chars"]
                        or row["prompt_utf8_bytes"] != report[
                            "condition_prompt_sizes"][condition]["prompt_utf8_bytes"]))
                or not isinstance(row.get("history_projection_digest"), str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}",
                    row["history_projection_digest"]) is None
                or (owner_evidence_schema in {
                    "sentientos.objective_history_conditions_owner_preview:v2",
                    "sentientos.objective_history_conditions_owner_preview:v3"}
                    and (not isinstance(row.get("projected_example_count"), int)
                        or type(row.get("projected_example_count")) is not int
                        or row["projected_example_count"] < 0
                        or not isinstance(row.get("projected_records"), list)))):
            raise ValueError("runtime_owner_preview_owner_condition_binding_invalid")
        if owner_evidence_schema not in {
                "sentientos.objective_history_conditions_owner_preview:v2",
                "sentientos.objective_history_conditions_owner_preview:v3"}:
            continue
        projected_records = row["projected_records"]
        expected_projection_ids = report["condition_selected_record_ids"][condition]
        expected_projection_digests = report["condition_selected_record_digests"][condition]
        if (len(projected_records) != len(expected_projection_ids)
                or [item.get("record_id") for item in projected_records
                    if isinstance(item, Mapping)] != expected_projection_ids
                or [item.get("record_digest") for item in projected_records
                    if isinstance(item, Mapping)] != expected_projection_digests):
            raise ValueError("runtime_owner_preview_projected_record_binding_invalid")
        for item in projected_records:
            if (not isinstance(item, Mapping)
                    or set(item) != {"record_id", "record_digest",
                        "prompt_packet_digest", "prompt_packet_serialization_present",
                        "experience_count", "example_count", "examples_digest",
                        "score_bound_source_run_digests",
                        "score_bound_source_score_digests"}
                    or not isinstance(item.get("prompt_packet_digest"), str)
                    or re.fullmatch(r"sha256:[0-9a-f]{64}",
                        item["prompt_packet_digest"]) is None
                    or item.get("prompt_packet_serialization_present") is not True
                    or any(type(item.get(key)) is not int or item[key] < 0
                        for key in ("experience_count", "example_count"))
                    or not isinstance(item.get("examples_digest"), str)
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", item["examples_digest"]) is None
                    or any(not isinstance(item.get(key), list)
                        or item[key] != sorted(set(item[key]))
                        or any(not isinstance(value, str)
                            or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
                            for value in item[key])
                        for key in ("score_bound_source_run_digests",
                            "score_bound_source_score_digests"))):
                raise ValueError("runtime_owner_preview_projected_record_evidence_invalid")
        if (sum(item["example_count"] for item in projected_records)
                != row["projected_example_count"]
                or (condition == "history_withheld"
                    and (row["projected_example_count"] != 0
                        or projected_records))):
            raise ValueError("runtime_owner_preview_projected_example_count_invalid")
    for field in ("condition_protocol_digest", "runtime_owner_preview_digest"):
        if (not isinstance(report.get(field), str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", report[field]) is None):
            raise ValueError("runtime_owner_preview_digest_invalid")
    if (not isinstance(report.get("snapshot_digest"), str)
            or re.fullmatch(r"[0-9a-f]{64}", report["snapshot_digest"]) is None
            or report.get("request_count") != 4
            or report.get("objective_condition_request_count") != 3
            or report.get("owner_state_mutated") is not False
            or report.get("owner_to_binder_path_exercised") is not True
            or report.get("cross_range_three_condition_prompt_protocol_exercised")
                is not True
            or report.get("cross_range_three_condition_runtime_experiment_exercised")
                is not False
            or report.get("full_prompt_text_included") is not False
            or report.get("model_outputs_included") is not False
            or report.get("inference_performed") is not False
            or report.get("model_attention_established") is not False
            or report.get("learning_established") is not False
            or report.get("authority") is not False):
        raise ValueError("runtime_owner_preview_claim_scope_invalid")
    return {
        "status": "verified",
        "campaign_id": plan["campaign_id"],
        "plan_digest": plan["plan_digest"],
        "cycle_id": cycle_id,
        "implementation_digest": implementation[
            "experiment_implementation_digest"],
        "implementation_matches_current": implementation_matches_current,
        "report_digest": report["audit_digest"],
        "verification_scope": (
            "owner_payload_digest_and_flattened_report_consistency"
            if owner_evidence is not None else
            "legacy_report_digest_and_plan_preflight_bindings_only"),
        "owner_payload_digest_verified": owner_evidence is not None,
        "report_origin_attested": False,
        "history_record_ids": report["history_record_ids"],
        "condition_order": observed_order,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }


def _write_exclusive(path: Path, report: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("runtime_owner_preview_output_exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(report), sort_keys=True, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--prior-history-root", type=Path)
    parser.add_argument("--cycle-index", type=int, default=0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report is not None:
        if args.prior_history_root is not None or args.output is not None:
            parser.error("--verify-report cannot be combined with preview output options")
        result = verify_report(report_path=args.verify_report,
            plan_path=args.plan, preflight_path=args.preflight)
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.prior_history_root is None or args.output is None:
        parser.error("preview mode requires --prior-history-root and --output")
    report = build_report(plan_path=args.plan,
        preflight_path=args.preflight,
        prior_history_root=args.prior_history_root,
        cycle_index=args.cycle_index)
    _write_exclusive(args.output, report)
    print(json.dumps({key: report[key] for key in (
        "campaign_id", "plan_digest", "cycle_id", "audit_digest",
        "history_record_ids", "history_record_digests", "request_count",
        "owner_to_binder_path_exercised",
        "cross_range_three_condition_prompt_protocol_exercised",
        "cross_range_three_condition_runtime_experiment_exercised",
        "inference_performed", "learning_established", "authority")},
        sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
