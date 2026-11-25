#!/usr/bin/env python3
"""Freeze a resident historical-examples pair without loading or invoking a model."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import sys
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.preflight_resident_strategy_inclusion_pair import (
    _LocalReceiptVerifier,
    _NoInferenceInvoker,
    _copy_without_symlinks,
    _plan_bound_identity,
    _read_receipt,
    _source_kinds_from_history,
)
from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore,
)
from sentientos.developmental_model_replacement_experiment import (
    ROOTLESS_INTEGER_AFFINE_TRANSFER_TASK_FAMILY,
    ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
    derive_rootless_task_commitment_nonces,
    rootless_integer_affine_transfer_task_pair,
)
from sentientos.local_model_authority import digest_payload
from sentientos.resident_developmental_cognition import (
    ResidentDevelopmentalCognitionConfig,
    ResidentDevelopmentalCognitionOwner,
    validate_historical_examples_execution_protocol,
)
from sentientos.resident_developmental_writeback import (
    ResidentDevelopmentalWritebackController,
)
from sentientos.runtime_admission import (
    AdmissionLedger,
    RuntimeAdmissionAuthority,
    RuntimeAdmissionVerifier,
)
from sentientos.world_state_board import WorldStateBoardBuilder, validate_snapshot
from work.historical_examples_intervention import (
    HistoricalExamplesPairJournal,
    _digest,
    derive_historical_examples_objective_request_bindings,
    prepare_historical_examples_pair,
    validate_historical_examples_protocol,
)
from work.negative_guidance_intervention import (
    ARMS as NEGATIVE_GUIDANCE_ARMS,
    prepare_negative_guidance_pair,
    validate_negative_guidance_execution_protocol,
    validate_negative_guidance_protocol,
)


def _generation_binding(*, invoker: Any, receipt: Mapping[str, Any],
        request_builder: Any | None) -> dict[str, Any]:
    requests = [item for item in invoker.requests
        if isinstance(getattr(item, "upstream_evidence", None), Mapping)
        and "objective_task_plan_digest" in item.upstream_evidence]
    if len(requests) != 2:
        raise ValueError("historical_examples_preview_requests_missing")
    if request_builder is None:
        generation = receipt.get("generation_config")
        if not isinstance(generation, Mapping):
            raise ValueError("historical_examples_generation_config_missing")
        source_actual = generation.get("actual_generation_parameters")
        if not isinstance(source_actual, Mapping):
            raise ValueError("historical_examples_actual_generation_parameters_missing")
        arm_configs = []
        for request in requests:
            actual = dict(source_actual)
            actual["max_new_tokens"] = min(request.budget.max_new_tokens,
                int(source_actual.get("max_new_tokens",
                    request.budget.max_new_tokens)))
            actual["temperature"] = 0
            actual["structured_output_schema"] = (
                dict(request.structured_output_schema)
                if request.structured_output_schema is not None else None)
            actual["use_model_chat_template"] = False
            arm_configs.append({**request.budget.to_dict(),
                "actual_generation_parameters": {
                    key: value for key, value in actual.items()
                    if value is not None}})
        if arm_configs[0] != arm_configs[1]:
            raise ValueError("historical_examples_generation_configs_differ")
        return arm_configs[0]
    record = request_builder.authority_map.record_for_active_identity(
        request_builder.model.active_identity,
        "resident_developmental_history_intervention_experiment")
    if record is None:
        raise ValueError("historical_examples_model_authority_record_missing")

    def arm_config(request: Any) -> dict[str, Any]:
        actual = {
            "max_new_tokens": min(request.budget.max_new_tokens,
                int(record.generation_ceilings.get("max_new_tokens",
                    request.budget.max_new_tokens))),
            "temperature": 0,
            "structured_output_schema": (dict(request.structured_output_schema)
                if request.structured_output_schema is not None else None),
            "use_model_chat_template": False,
        }
        actual = {key: value for key, value in actual.items() if value is not None}
        return {**request.budget.to_dict(),
            "actual_generation_parameters": actual}

    included, omitted = (arm_config(request) for request in requests)
    if included != omitted:
        raise ValueError("historical_examples_generation_configs_differ")
    return included


def _randomized_arm_order(assignment_seed: str) -> tuple[str, str]:
    """Assign order from a separate OS-random seed, not the task seed."""
    if (not isinstance(assignment_seed, str) or len(assignment_seed) != 64
            or any(character not in "0123456789abcdef"
                for character in assignment_seed)):
        raise ValueError("historical_examples_arm_order_seed_invalid")
    return (("examples_included", "examples_omitted")
        if int(assignment_seed[-1], 16) & 1 == 0 else
        ("examples_omitted", "examples_included"))


def _negative_guidance_arm_order(assignment_seed: str) -> tuple[str, str]:
    if (not isinstance(assignment_seed, str) or len(assignment_seed) != 64
            or any(character not in "0123456789abcdef"
                for character in assignment_seed)):
        raise ValueError("negative_guidance_arm_order_seed_invalid")
    return (NEGATIVE_GUIDANCE_ARMS if int(assignment_seed[-1], 16) & 1 == 0
        else tuple(reversed(NEGATIVE_GUIDANCE_ARMS)))


def _read_private_task_commitment_key(path: Path) -> tuple[str, str]:
    """Read a 256-bit matched-task key without following links or exposing it."""
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ValueError("historical_examples_task_commitment_key_unreadable") from exc
    try:
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_size != 64
                or metadata.st_nlink != 1
                or (os.name != "nt" and metadata.st_mode & 0o077)):
            raise ValueError("historical_examples_task_commitment_key_not_private")
        raw = os.read(descriptor, 65)
        after = os.fstat(descriptor)
        if (len(raw) != 64 or after.st_size != 64
                or after.st_ino != metadata.st_ino
                or after.st_dev != metadata.st_dev
                or after.st_mtime_ns != metadata.st_mtime_ns):
            raise ValueError("historical_examples_task_commitment_key_changed")
    finally:
        os.close(descriptor)
    try:
        key = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("historical_examples_task_commitment_key_invalid") from exc
    if len(key) != 64 or any(character not in "0123456789abcdef" for character in key):
        raise ValueError("historical_examples_task_commitment_key_invalid")
    return key, "sha256:" + hashlib.sha256(raw).hexdigest()


def _read_history_record_allowlist(path: Path
        ) -> tuple[dict[str, Any], str]:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ValueError("historical_examples_record_allowlist_unreadable") from exc
    try:
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or metadata.st_size > 256 * 1024):
            raise ValueError("historical_examples_record_allowlist_invalid")
        raw = os.read(descriptor, metadata.st_size + 1)
        after = os.fstat(descriptor)
        if (len(raw) != metadata.st_size or after.st_size != metadata.st_size
                or after.st_ino != metadata.st_ino or after.st_dev != metadata.st_dev
                or after.st_mtime_ns != metadata.st_mtime_ns):
            raise ValueError("historical_examples_record_allowlist_changed")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_object,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("historical_examples_record_allowlist_nonstandard_json")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("historical_examples_record_allowlist_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("historical_examples_record_allowlist_invalid")
    semantic = {key: item for key, item in value.items()
        if key != "allowlist_digest"}
    ids = value.get("record_ids")
    digests = value.get("record_digests")
    if (value.get("schema_version") !=
            "sentientos.historical_examples_record_allowlist:v1"
            or value.get("basis") !=
                "intersection_of_verified_matched_preflight_history_sets"
            or not isinstance(ids, list) or not ids
            or any(not isinstance(item, str) or not item.startswith("devrec-")
                for item in ids)
            or len(ids) != len(set(ids))
            or not isinstance(digests, dict) or set(digests) != set(ids)
            or any(not isinstance(item, str) or len(item) != 71
                or not item.startswith("sha256:")
                or any(char not in "0123456789abcdef" for char in item[7:])
                for item in digests.values())
            or value.get("allowlist_digest") != _digest(semantic)
            or value.get("inference_performed") is not False
            or value.get("learning_established") is not False
            or value.get("authority") is not False):
        raise ValueError("historical_examples_record_allowlist_binding_invalid")
    return value, "sha256:" + hashlib.sha256(raw).hexdigest()


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("historical_examples_record_allowlist_duplicate_key")
        value[key] = item
    return value


def _source_file_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("historical_examples_source_file_invalid")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _history_probe_overlap_audit(*, history_root: Path,
        task_probe_inputs: Any) -> dict[str, Any]:
    """Measure exact probe reuse across all recursively stored history inputs."""
    if (not isinstance(task_probe_inputs, (list, tuple))
            or not task_probe_inputs
            or any(type(value) is not int for value in task_probe_inputs)
            or len(set(task_probe_inputs)) != len(task_probe_inputs)):
        raise ValueError("historical_examples_task_probe_inputs_invalid")
    records_root = history_root / "records"
    if records_root.is_symlink() or not records_root.is_dir():
        raise ValueError("historical_examples_history_records_unavailable")
    paths = sorted(records_root.glob("*.json"))
    if not paths or any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError("historical_examples_history_records_invalid")
    historical_inputs: list[int] = []

    def collect(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in {"probe_input", "input"}:
                    if type(item) is not int:
                        raise ValueError(
                            "historical_examples_history_probe_input_incomplete")
                    historical_inputs.append(item)
                elif key == "probe_inputs":
                    if (not isinstance(item, (list, tuple))
                            or any(type(probe) is not int for probe in item)):
                        raise ValueError(
                            "historical_examples_history_probe_input_incomplete")
                    historical_inputs.extend(item)
                collect(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)

    for path in paths:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "historical_examples_history_record_unreadable") from exc
        if not isinstance(record, Mapping):
            raise ValueError("historical_examples_history_record_invalid")
        collect(record)

    task_set = set(task_probe_inputs)
    history_set = set(historical_inputs)
    overlap = sorted(task_set & history_set)
    audit = {
        "schema_version":
            "sentientos.historical_examples_probe_history_overlap_audit:v1",
        "scope": "all_recursive_input_and_probe_fields_in_all_history_records",
        "history_record_count": len(paths),
        "history_probe_input_occurrence_count": len(historical_inputs),
        "history_probe_input_set_digest": _digest(sorted(history_set)),
        "task_probe_count": len(task_probe_inputs),
        "task_probe_input_digest": _digest(list(task_probe_inputs)),
        "overlapping_probe_input_count": len(overlap),
        "overlapping_probe_input_digest": _digest(overlap),
        "measurement_complete": True,
        "no_exact_overlap_detected": not overlap,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    if overlap:
        raise ValueError("historical_examples_held_out_probe_overlap_detected")
    return audit


def build_preflight(*, cycle_root: Path, seed: int, journal_root: Path,
        plan_path: Path | None = None, cycle_index: int = 0,
        task_family_id: str = ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
        transfer_probe_count: int = 3,
        model_identity_backend_seed: int | None = None,
        history_record_allowlist_file: Path | None = None,
        objective_task: Any | None = None,
        task_commitment_nonces: tuple[str, str] | None = None,
        task_commitment_key_file_sha256: str | None = None,
        allow_recomputed_campaign_source_pin_mismatch: bool = False,
        arm_order_seed: str | None = None,
        ablation_target: str = "raw_examples",
        prompt_preview_only: bool = False,
        history_prompt_identity_policy: str | None = None,
        authority_map_observed_at: str | None = None) -> dict[str, Any]:
    if (type(transfer_probe_count) is not int
            or not 1 <= transfer_probe_count <= 16
            or task_family_id not in {ROOTLESS_INTEGER_AFFINE_TRANSFER_TASK_FAMILY,
            ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY}
            or (task_commitment_nonces is None) !=
            (task_commitment_key_file_sha256 is None)
            or task_commitment_key_file_sha256 is not None
                and (not isinstance(task_commitment_key_file_sha256, str)
                    or len(task_commitment_key_file_sha256) != 71
                    or not task_commitment_key_file_sha256.startswith("sha256:")
                    or any(character not in "0123456789abcdef"
                        for character in task_commitment_key_file_sha256[7:]))):
        raise ValueError("historical_examples_task_commitment_key_binding_invalid")
    if (ablation_target not in {"raw_examples", "negative_guidance"}
            or (ablation_target == "negative_guidance"
                and not prompt_preview_only)
            or (prompt_preview_only and ablation_target != "negative_guidance")):
        raise ValueError("historical_examples_preflight_ablation_mode_invalid")
    if arm_order_seed is None:
        arm_order_seed = secrets.token_hex(32)
    arm_order = _randomized_arm_order(arm_order_seed)
    cycle_root = cycle_root.resolve(strict=True)
    receipt_path, receipt = _read_receipt(cycle_root)
    history_allowlist: dict[str, Any] | None = None
    history_allowlist_file_sha256: str | None = None
    if history_record_allowlist_file is not None:
        history_allowlist, history_allowlist_file_sha256 = (
            _read_history_record_allowlist(history_record_allowlist_file))
        if (history_allowlist.get("cycle_root_id") != cycle_root.name
                or history_allowlist.get("source_receipt_digest") !=
                    receipt.get("receipt_digest")):
            raise ValueError("historical_examples_record_allowlist_source_mismatch")
    request = receipt.get("request")
    if not isinstance(request, Mapping):
        raise ValueError("historical_examples_source_receipt_request_missing")
    identity_override = None
    request_builder = None
    plan_binding = None
    if plan_path is not None:
        identity_override, request_builder, plan_binding = _plan_bound_identity(
            plan_path, cycle_index,
            backend_seed=model_identity_backend_seed,
            allow_recomputed_campaign_source_pin_mismatch=
                allow_recomputed_campaign_source_pin_mismatch,
            authority_map_observed_at=authority_map_observed_at)
    elif authority_map_observed_at is not None:
        raise ValueError("authority_map_observation_time_requires_plan")
    elif model_identity_backend_seed is not None:
        raise ValueError("model_identity_backend_seed_requires_campaign_plan")
    identity = (identity_override if identity_override is not None
        else request.get("active_model_identity"))
    if not isinstance(identity, Mapping) or not identity:
        raise ValueError("historical_examples_model_identity_missing")
    generation = receipt.get("generation_config")
    if not isinstance(generation, Mapping):
        raise ValueError("historical_examples_generation_config_missing")
    max_input_chars = generation.get("max_input_chars")
    timeout_seconds = generation.get("timeout_seconds")
    if (type(max_input_chars) is not int or not 1024 <= max_input_chars <= 48_000
            or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300):
        raise ValueError("historical_examples_generation_bounds_invalid")

    source_root = cycle_root / "resident-cognition"
    with tempfile.TemporaryDirectory(prefix="sentientos-historical-examples-") as temp:
        copied_root = Path(temp) / "resident-cognition"
        _copy_without_symlinks(source_root, copied_root)
        history_root = copied_root / "history"
        state_root = copied_root / "state"
        config = ResidentDevelopmentalCognitionConfig(
            history_root=history_root, state_root=state_root,
            allowed_source_kinds=_source_kinds_from_history(history_root),
            max_selected_facts=32, max_retrieved_records=8,
            comparison_enabled=True, enabled=True,
            max_inference_timeout_seconds=timeout_seconds,
            max_inference_input_chars=max_input_chars)
        ledger = AdmissionLedger(state_root / "runtime_admissions.json")
        definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK:
            RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
        writeback = ResidentDevelopmentalWritebackController(
            history_root=history_root,
            admission_verifier=RuntimeAdmissionVerifier(
                definitions=definitions, ledger=ledger),
            current_sequence=ledger.current_sequence)
        if history_allowlist is not None:
            for record_id in history_allowlist["record_ids"]:
                source_record = writeback.store.get(record_id)
                if source_record.record_digest != history_allowlist[
                        "record_digests"][record_id]:
                    raise ValueError(
                        "historical_examples_record_allowlist_record_digest_mismatch")
        invoker = _NoInferenceInvoker(request,
            identity_override=identity_override, request_builder=request_builder)
        owner = ResidentDevelopmentalCognitionOwner(config=config,
            writeback=writeback,
            admission_authority=RuntimeAdmissionAuthority(
                definitions=definitions, ledger=ledger),
            invoker=invoker, current_sequence=ledger.current_sequence,
            invocation_receipt_verifier=_LocalReceiptVerifier(cycle_root))
        generated_task = rootless_integer_affine_transfer_task_pair(seed,
            task_family_id=task_family_id,
            transfer_probe_count=transfer_probe_count,
            commitment_nonces=task_commitment_nonces)[1]
        if history_prompt_identity_policy is not None:
            if history_prompt_identity_policy != (
                    "matched_cross_model_identity_omitted:v1"):
                raise ValueError(
                    "historical_examples_prompt_identity_policy_invalid")
            if objective_task is None:
                generated_task = replace(generated_task,
                    history_prompt_identity_policy=history_prompt_identity_policy)
            elif objective_task.public_descriptor().get(
                    "history_prompt_identity_policy") != history_prompt_identity_policy:
                raise ValueError(
                    "historical_examples_prompt_identity_policy_task_mismatch")
        if (objective_task is not None
                and (not callable(getattr(objective_task, "specification", None))
                    or objective_task.specification()
                        != generated_task.specification()
                    or task_commitment_nonces is not None
                        and getattr(objective_task, "commitment_nonce", None)
                            != task_commitment_nonces[1])):
            raise ValueError("historical_examples_task_seed_binding_mismatch")
        task = objective_task if objective_task is not None else generated_task
        commitment_evidence = ({} if task_commitment_nonces is None else {
            "task_commitment_key_file_sha256": task_commitment_key_file_sha256,
            "task_factory_source_sha256": _source_file_sha256(
                Path(__file__).resolve().parents[1]
                / "sentientos/developmental_model_replacement_experiment.py"),
            "preflight_source_sha256": _source_file_sha256(Path(__file__)),
            "resident_cognition_source_sha256": _source_file_sha256(
                Path(__file__).resolve().parents[1]
                / "sentientos/resident_developmental_cognition.py"),
            "task_commitment_nonce_pair_digest": _digest({
                "schema_version": "sentientos.matched_task_commitment_pair:v1",
                "task_generation_seed": seed,
                "task_family_id": task_family_id,
                "acquisition_nonce": task_commitment_nonces[0],
                "transfer_nonce": task_commitment_nonces[1],
            }),
        })
        task_descriptor = task.public_descriptor()
        if not isinstance(task_descriptor, Mapping):
            raise ValueError("historical_examples_task_description_invalid")
        if (history_allowlist is not None
                and history_allowlist.get("task_digest") !=
                    task_descriptor.get("task_digest")):
            raise ValueError("historical_examples_record_allowlist_task_mismatch")
        probe_overlap_audit = _history_probe_overlap_audit(
            history_root=history_root,
            task_probe_inputs=task_descriptor.get("probe_inputs"))
        snapshot = WorldStateBoardBuilder(clock=lambda: datetime(
            2026, 11, 23, tzinfo=timezone.utc)).build((),
                manifest_id="resident-historical-examples-cpu-preflight")
        if not validate_snapshot(snapshot).valid:
            raise ValueError("historical_examples_synthetic_snapshot_invalid")
        preview = owner.preview_objective_historical_examples_pair(
            snapshot=snapshot,
            tick_id=f"historical-examples-cpu-preflight-{seed}",
            objective_task=task, ablation_target=ablation_target,
            history_record_allowlist=(tuple(history_allowlist["record_ids"])
                if history_allowlist is not None else None))
        if history_allowlist is not None:
            ablation = preview.get("historical_examples_prompt_ablation")
            selected_ids = (ablation.get("selected_record_ids")
                if isinstance(ablation, Mapping) else None)
            selected_digests = (ablation.get("selected_record_digests")
                if isinstance(ablation, Mapping) else None)
            if (not isinstance(selected_ids, list)
                    or set(selected_ids) != set(history_allowlist["record_ids"])
                    or len(selected_ids) != len(history_allowlist["record_ids"])
                    or not isinstance(selected_digests, list)
                    or dict(zip(selected_ids, selected_digests, strict=True))
                        != history_allowlist["record_digests"]):
                raise ValueError(
                    "historical_examples_record_allowlist_selection_mismatch")
        generation_config = _generation_binding(invoker=invoker,
            receipt=receipt, request_builder=request_builder)
        generation_config_digest = "sha256:" + digest_payload(generation_config)

    descriptor = task.public_descriptor()
    specification = task.specification()
    if not isinstance(descriptor, Mapping) or not isinstance(specification, Mapping):
        raise ValueError("historical_examples_task_description_invalid")
    if prompt_preview_only:
        ablation = preview.get("historical_negative_guidance_ablation")
        if not isinstance(ablation, Mapping):
            raise ValueError("negative_guidance_preflight_ablation_missing")
        journal = HistoricalExamplesPairJournal(
            store=DevelopmentalExperimentStore(journal_root))
        private_task_plan_digest = journal.persist_private_task_plan(
            objective_task=task)
        probes = descriptor.get("probe_inputs")
        multiplier = specification.get("multiplier")
        offset = specification.get("offset")
        if (not isinstance(probes, (list, tuple))
                or type(multiplier) is not int or type(offset) is not int):
            raise ValueError("negative_guidance_answer_key_invalid")
        answer_key = {_digest({
            "schema_version": "sentientos.objective_probe_binding:v1",
            "task_digest": descriptor["task_digest"],
            "probe_index": index, "probe_input": probe,
        }): multiplier * probe + offset for index, probe in enumerate(probes)}
        if set(answer_key) != set(preview.get("probe_binding_digests", ())):
            raise ValueError("negative_guidance_answer_key_binding_mismatch")
        identity_digest = "sha256:" + digest_payload(dict(identity))
        protocol = prepare_negative_guidance_pair(preview=preview,
            target_model_identity_digest=identity_digest,
            task_digest=descriptor["task_digest"],
            private_task_plan_digest=private_task_plan_digest,
            generation_config_digest=generation_config_digest,
            answer_key_digest=_digest(answer_key),
            held_out_probe_overlap_audit=probe_overlap_audit,
            held_out_probe_overlap_audit_digest=_digest(probe_overlap_audit),
            arm_order=_negative_guidance_arm_order(arm_order_seed))
        return {
            "schema_version":
                ("sentientos.resident_negative_guidance_prompt_preview:v2"
                    if task_commitment_nonces is not None else
                    "sentientos.resident_negative_guidance_prompt_preview:v1"),
            "cycle_root_id": cycle_root.name,
            "source_receipt_id": receipt.get("receipt_id"),
            "source_receipt_digest": receipt.get("receipt_digest"),
            "source_model_identity_digest": identity_digest,
            "task_generation_seed": seed,
            "arm_order_seed": arm_order_seed,
            "arm_order_policy": "independent_os_random_seed_v1",
            **commitment_evidence,
            "task_family_id": descriptor.get("task_family_id"),
            "task_digest": descriptor.get("task_digest"),
            "private_task_plan_digest": private_task_plan_digest,
            "answer_key_digest": _digest(answer_key),
            "history_record_ids": list(ablation["selected_record_ids"]),
            "history_record_digests": list(ablation["selected_record_digests"]),
            "pair_preview_digest": preview.get("pair_preview_digest"),
            "owner_pair_preview": json.loads(json.dumps(preview,
                sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                allow_nan=False)),
            "historical_negative_guidance_ablation": dict(ablation),
            "negative_guidance_execution_protocol": protocol,
            "generation_config_digest": generation_config_digest,
            "held_out_probe_overlap_audit": probe_overlap_audit,
            "runtime_condition_created": False,
            "model_loaded": False,
            "model_invoked": False,
            "inference_performed": False,
            "learning_established": False,
            "authority": False,
        }

    probes = descriptor.get("probe_inputs")
    multiplier = specification.get("multiplier")
    offset = specification.get("offset")
    if (not isinstance(probes, (list, tuple)) or not probes
            or any(type(value) is not int for value in probes)
            or type(multiplier) is not int or type(offset) is not int):
        raise ValueError("historical_examples_task_answer_key_invalid")
    answer_key = {_digest({
        "schema_version": "sentientos.objective_probe_binding:v1",
        "task_digest": descriptor["task_digest"],
        "probe_index": index, "probe_input": probe,
    }): multiplier * probe + offset for index, probe in enumerate(probes)}
    if set(answer_key) != set(preview.get("probe_binding_digests", ())):
        raise ValueError("historical_examples_probe_answer_binding_mismatch")

    identity_digest = "sha256:" + digest_payload(dict(identity))
    journal = HistoricalExamplesPairJournal(
        store=DevelopmentalExperimentStore(journal_root))
    private_task_plan_digest = journal.persist_private_task_plan(
        objective_task=task)
    prepared = prepare_historical_examples_pair(
        target_model_identity_digest=identity_digest,
        task_digest=descriptor["task_digest"],
        generation_config_digest=generation_config_digest,
        owner_prompt_pair_preview=preview,
        answer_key=answer_key,
        private_task_plan_digest=private_task_plan_digest,
        held_out_probe_overlap_audit_digest=_digest(probe_overlap_audit),
        arm_order=arm_order)
    protocol = prepared["protocol"]
    validate_historical_examples_protocol(protocol=protocol,
        target_model_identity_digest=identity_digest,
        task_digest=descriptor["task_digest"])
    journal.persist_preflight_audit(protocol=protocol,
        audit=probe_overlap_audit)
    journal.persist_protocol(protocol=protocol)
    objective_request_bindings = (
        derive_historical_examples_objective_request_bindings(
            protocol=protocol, objective_task=task))
    return {
        "schema_version": ("sentientos.resident_historical_examples_cpu_preflight:v10"
            if authority_map_observed_at is not None else
            "sentientos.resident_historical_examples_cpu_preflight:v9"
            if model_identity_backend_seed is not None else
            "sentientos.resident_historical_examples_cpu_preflight:v8"
            if descriptor.get("history_prompt_identity_policy") is not None else
            "sentientos.resident_historical_examples_cpu_preflight:v7"
            if task_commitment_nonces is not None else
            "sentientos.resident_historical_examples_cpu_preflight:v6"),
        "arm_order_policy": "independent_os_random_seed_v1",
        "arm_order_seed": arm_order_seed,
        "cycle_root_id": cycle_root.name,
        "source_receipt_id": receipt.get("receipt_id"),
        "source_receipt_digest": receipt.get("receipt_digest"),
        "source_model_identity_digest": identity_digest,
        **({"model_identity_backend_seed": model_identity_backend_seed}
            if model_identity_backend_seed is not None else {}),
        "source_identity_posture": (
            "reconstructed_from_verified_historical_receipt" if plan_path is None
            else "reconstructed_from_verified_campaign_plan"),
        "plan_binding": plan_binding,
        **({"authority_map_observed_at": plan_binding[
                "authority_map_observed_at"]}
            if isinstance(plan_binding, Mapping) else {}),
        "task_generation_seed": seed,
        **({"history_record_allowlist_digest":
                history_allowlist["allowlist_digest"],
            "history_record_allowlist_file_sha256":
                history_allowlist_file_sha256}
            if history_allowlist is not None else {}),
        **commitment_evidence,
        "task_family_id": descriptor.get("task_family_id"),
        "transfer_probe_count": transfer_probe_count,
        "task_digest": descriptor["task_digest"],
        **({"history_prompt_identity_policy": descriptor[
            "history_prompt_identity_policy"]}
            if descriptor.get("history_prompt_identity_policy") is not None else {}),
        "held_out_probe_overlap_audit": probe_overlap_audit,
        "snapshot_id": preview.get("snapshot_id"),
        "snapshot_digest": preview.get("snapshot_digest"),
        "owner_prompt_pair_preview_digest": preview.get("pair_preview_digest"),
        **({"history_prompt_identity_bindings_by_arm": preview[
            "history_prompt_identity_bindings_by_arm"]}
            if isinstance(preview.get(
                "history_prompt_identity_bindings_by_arm"), Mapping) else {}),
        "generation_config_digest": generation_config_digest,
        "answer_key_digest": protocol["answer_key_digest"],
        "private_task_plan_digest": private_task_plan_digest,
        "protocol_digest": protocol["protocol_digest"],
        "historical_examples_protocol": protocol,
        "objective_request_bindings_by_arm": objective_request_bindings,
        "objective_request_bindings_digest": _digest(
            objective_request_bindings),
        "protocol_persisted": True,
        "source_history_mutated": False,
        "model_loaded": False,
        "model_invoked": False,
        "inference_performed": False,
        "runtime_condition_created": False,
        "learning_established": False,
        "authority": False,
    }


def verify_preflight_report(*, cycle_root: Path, journal_root: Path,
        report_path: Path, seed: int,
        plan_path: Path | None = None, cycle_index: int = 0,
        task_family_id: str = ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
        transfer_probe_count: int | None = None,
        model_identity_backend_seed: int | None = None,
        history_record_allowlist_file: Path | None = None,
        task_commitment_nonces: tuple[str, str] | None = None,
        task_commitment_key_file_sha256: str | None = None,
        history_prompt_identity_policy: str | None = None,
        allow_recomputed_campaign_source_pin_mismatch: bool = False
        ) -> dict[str, Any]:
    """Rebuild and compare the saved preflight from its exact private task."""
    try:
        saved = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("historical_examples_preflight_report_unreadable") from exc
    saved_transfer_probe_count = (saved.get("transfer_probe_count", 3)
        if isinstance(saved, Mapping) else 3)
    if (type(saved_transfer_probe_count) is not int
            or not 1 <= saved_transfer_probe_count <= 16
            or transfer_probe_count is not None
                and transfer_probe_count != saved_transfer_probe_count):
        raise ValueError("historical_examples_preflight_probe_count_mismatch")
    transfer_probe_count = saved_transfer_probe_count
    if (isinstance(saved, Mapping) and saved.get("schema_version") in {
            "sentientos.resident_negative_guidance_prompt_preview:v1",
            "sentientos.resident_negative_guidance_prompt_preview:v2"}):
        if saved.get("task_generation_seed") != seed:
            raise ValueError("negative_guidance_prompt_preview_seed_mismatch")
        journal = HistoricalExamplesPairJournal(
            store=DevelopmentalExperimentStore(journal_root))
        task_digest = saved.get("task_digest")
        task_plan_digest = saved.get("private_task_plan_digest")
        if (not isinstance(task_digest, str)
                or not isinstance(task_plan_digest, str)):
            raise ValueError("negative_guidance_prompt_preview_task_binding_missing")
        task = journal.load_private_task_plan(task_digest=task_digest,
            task_plan_digest=task_plan_digest)
        protocol = saved.get("negative_guidance_execution_protocol")
        if not isinstance(protocol, Mapping):
            raise ValueError("negative_guidance_execution_protocol_missing")
        validate_negative_guidance_protocol(protocol,
            target_model_identity_digest=saved.get(
                "source_model_identity_digest"), task_digest=task_digest)
        for arm in NEGATIVE_GUIDANCE_ARMS:
            validate_negative_guidance_execution_protocol(
                protocol=protocol, objective_task=task, arm=arm,
                tick_id=protocol["owner_execution_tick_ids"][arm],
                accumulated_strategy_inclusion="included")
        saved_arm_order_seed = saved.get("arm_order_seed")
        legacy_frozen_order = saved_arm_order_seed is None
        if legacy_frozen_order:
            conditions = protocol.get("conditions")
            if conditions == list(NEGATIVE_GUIDANCE_ARMS):
                saved_arm_order_seed = "0" * 64
            elif conditions == list(reversed(NEGATIVE_GUIDANCE_ARMS)):
                saved_arm_order_seed = "0" * 63 + "1"
            else:
                raise ValueError(
                    "negative_guidance_legacy_arm_order_unreconstructable")
        rebuilt_preview = build_preflight(cycle_root=cycle_root, seed=seed,
            journal_root=journal_root, plan_path=plan_path,
            cycle_index=cycle_index, task_family_id=task_family_id,
            transfer_probe_count=transfer_probe_count,
            history_record_allowlist_file=history_record_allowlist_file,
            task_commitment_nonces=task_commitment_nonces,
            task_commitment_key_file_sha256=task_commitment_key_file_sha256,
            allow_recomputed_campaign_source_pin_mismatch=
                allow_recomputed_campaign_source_pin_mismatch,
            arm_order_seed=saved_arm_order_seed,
            ablation_target="negative_guidance",
            prompt_preview_only=True, objective_task=task)
        if legacy_frozen_order:
            rebuilt_preview.pop("arm_order_seed", None)
            rebuilt_preview.pop("arm_order_policy", None)
        if rebuilt_preview != dict(saved):
            raise ValueError("negative_guidance_prompt_preview_reconstruction_mismatch")
        return {"schema_version":
                "sentientos.negative_guidance_prompt_preview_verification:v1",
            "preflight_report_digest": _digest(dict(saved)),
            "pair_preview_digest": saved.get("pair_preview_digest"),
            "source_history_reconstructed": True,
            "owner_prompt_pair_reconstructed": True,
            "execution_protocol_verified": True,
            "resident_arm_bindings_verified": True,
            "held_out_probe_overlap_verified": True,
            "model_loaded": False, "model_invoked": False,
            "inference_performed": False, "learning_established": False,
            "authority": False}
    if (not isinstance(saved, Mapping)
            or saved.get("schema_version") not in {
                "sentientos.resident_historical_examples_cpu_preflight:v6",
                "sentientos.resident_historical_examples_cpu_preflight:v7",
                "sentientos.resident_historical_examples_cpu_preflight:v8",
                "sentientos.resident_historical_examples_cpu_preflight:v9",
                "sentientos.resident_historical_examples_cpu_preflight:v10"}
            or saved.get("task_generation_seed") != seed
            or not isinstance(saved.get("historical_examples_protocol"), Mapping)):
        raise ValueError("historical_examples_preflight_report_invalid")
    saved_identity_backend_seed = saved.get("model_identity_backend_seed")
    if (saved_identity_backend_seed is not None
            and (type(saved_identity_backend_seed) is not int
                or not 0 <= saved_identity_backend_seed <= 2**31 - 1)):
        raise ValueError("historical_examples_preflight_identity_backend_seed_invalid")
    if (model_identity_backend_seed is not None
            and model_identity_backend_seed != saved_identity_backend_seed):
        raise ValueError("historical_examples_preflight_identity_backend_seed_mismatch")
    model_identity_backend_seed = saved_identity_backend_seed
    request_bindings = saved.get("objective_request_bindings_by_arm")
    if (not isinstance(request_bindings, Mapping)
            or set(request_bindings) != {"examples_included", "examples_omitted"}
            or saved.get("objective_request_bindings_digest") !=
                _digest(request_bindings)):
        raise ValueError(
            "historical_examples_preflight_objective_request_bindings_invalid")
    protocol = saved["historical_examples_protocol"]
    validate_historical_examples_protocol(protocol=protocol)
    arm_order_seed = saved.get("arm_order_seed")
    if protocol.get("conditions") != list(
            _randomized_arm_order(arm_order_seed)):
        raise ValueError("historical_examples_preflight_arm_order_mismatch")
    journal = HistoricalExamplesPairJournal(
        store=DevelopmentalExperimentStore(journal_root))
    stored_protocol = journal.load_protocol(
        protocol_digest=protocol["protocol_digest"])
    if stored_protocol != dict(protocol):
        raise ValueError("historical_examples_preflight_journal_mismatch")
    task = journal.load_task_for_protocol(
        protocol_digest=protocol["protocol_digest"])
    for arm in protocol["conditions"]:
        validate_historical_examples_execution_protocol(
            protocol=protocol, objective_task=task, arm=arm,
            tick_id=protocol["owner_execution_tick_ids"][arm])
    rebuilt = build_preflight(cycle_root=cycle_root, seed=seed,
        journal_root=journal_root, plan_path=plan_path,
        cycle_index=cycle_index, task_family_id=task_family_id,
        transfer_probe_count=transfer_probe_count,
        model_identity_backend_seed=model_identity_backend_seed,
        history_record_allowlist_file=history_record_allowlist_file,
        objective_task=task,
        task_commitment_nonces=task_commitment_nonces,
        task_commitment_key_file_sha256=task_commitment_key_file_sha256,
        history_prompt_identity_policy=history_prompt_identity_policy,
        authority_map_observed_at=saved.get("authority_map_observed_at"),
        allow_recomputed_campaign_source_pin_mismatch=
            allow_recomputed_campaign_source_pin_mismatch,
        arm_order_seed=arm_order_seed)
    if rebuilt != dict(saved):
        raise ValueError("historical_examples_preflight_reconstruction_mismatch")
    return {"schema_version":
            "sentientos.resident_historical_examples_preflight_verification:v7",
        "preflight_report_digest": _digest(dict(saved)),
        "protocol_digest": protocol["protocol_digest"],
        "private_task_plan_digest": protocol["private_task_plan_digest"],
        "objective_request_bindings_digest": _digest(request_bindings),
        "source_history_reconstructed": True,
        "owner_prompt_pair_reconstructed": True,
        "journal_protocol_verified": True,
        "resident_owner_protocol_gate_verified": True,
        "model_loaded": False, "model_invoked": False,
        "learning_established": False, "authority": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-root", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--journal-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--cycle-index", type=int, default=0)
    parser.add_argument("--task-family", choices=(
        ROOTLESS_INTEGER_AFFINE_TRANSFER_TASK_FAMILY,
        ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY),
        default=ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
        help="task family used for matched history and held-out probes")
    parser.add_argument("--transfer-probe-count", type=int,
        help="number of held-out probes per task (1 to 16; defaults to 3)")
    parser.add_argument("--model-identity-backend-seed", type=int,
        help="bind target identity to the fixed runner backend seed")
    parser.add_argument("--authority-map-observed-at",
        help="fixed aware timestamp for CPU-only authority-map parity audits")
    parser.add_argument("--history-record-allowlist-file", type=Path,
        help="digest-bound common history set from a matched parity audit")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    parser.add_argument("--verification-output", type=Path)
    parser.add_argument("--ablation-target",
        choices=("raw_examples", "negative_guidance"),
        default="raw_examples")
    parser.add_argument("--prompt-preview-only", action="store_true")
    parser.add_argument("--shared-task-commitment-key-file", type=Path,
        help="private 64-hex key reused by matched target preflights")
    parser.add_argument("--arm-order-seed",
        help="optional frozen 64-hex assignment seed for exact CPU preflight reconstruction")
    parser.add_argument("--history-prompt-identity-policy",
        choices=("matched_cross_model_identity_omitted:v1",),
        help="opt in to target-digest omission with controller identity evidence")
    parser.add_argument("--allow-recomputed-identity-recipe", action="store_true",
        help="allow the campaign planner source pin to differ only when the "+
            "current identity replay exactly matches the plan")
    args = parser.parse_args()
    task_commitment_nonces = None
    task_commitment_key_file_sha256 = None
    if args.shared_task_commitment_key_file is not None:
        master_key, task_commitment_key_file_sha256 = (
            _read_private_task_commitment_key(
                args.shared_task_commitment_key_file))
        task_commitment_nonces = derive_rootless_task_commitment_nonces(
            master_key, seed=args.seed,
            task_family_id=args.task_family)
    if args.verify_report is not None:
        result = verify_preflight_report(cycle_root=args.cycle_root,
            journal_root=args.journal_root, report_path=args.verify_report,
            seed=args.seed, plan_path=args.plan, cycle_index=args.cycle_index,
            task_family_id=args.task_family,
            transfer_probe_count=args.transfer_probe_count,
            model_identity_backend_seed=args.model_identity_backend_seed,
            history_record_allowlist_file=args.history_record_allowlist_file,
            task_commitment_nonces=task_commitment_nonces,
            task_commitment_key_file_sha256=task_commitment_key_file_sha256,
            history_prompt_identity_policy=args.history_prompt_identity_policy,
            allow_recomputed_campaign_source_pin_mismatch=
                args.allow_recomputed_identity_recipe)
        encoded = json.dumps(result, sort_keys=True, indent=2) + "\n"
        if args.verification_output is not None:
            args.verification_output.parent.mkdir(parents=True, exist_ok=True)
            with args.verification_output.open("x", encoding="utf-8",
                    newline="\n") as stream:
                stream.write(encoded)
        print(encoded, end="")
        return 0
    if args.output is None:
        raise ValueError("historical_examples_preflight_output_required")
    report = build_preflight(cycle_root=args.cycle_root, seed=args.seed,
        journal_root=args.journal_root, plan_path=args.plan,
        cycle_index=args.cycle_index, task_family_id=args.task_family,
        transfer_probe_count=(args.transfer_probe_count
            if args.transfer_probe_count is not None else 3),
        model_identity_backend_seed=args.model_identity_backend_seed,
        ablation_target=args.ablation_target,
        history_record_allowlist_file=args.history_record_allowlist_file,
        prompt_preview_only=args.prompt_preview_only,
        history_prompt_identity_policy=args.history_prompt_identity_policy,
        authority_map_observed_at=args.authority_map_observed_at,
        arm_order_seed=args.arm_order_seed,
        task_commitment_nonces=task_commitment_nonces,
        task_commitment_key_file_sha256=task_commitment_key_file_sha256,
        allow_recomputed_campaign_source_pin_mismatch=
            args.allow_recomputed_identity_recipe)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, sort_keys=True, indent=2) + "\n")
    summary_fields = (("cycle_root_id", "task_generation_seed", "task_family_id",
        "task_digest", "task_commitment_key_file_sha256",
        "task_commitment_nonce_pair_digest", "task_factory_source_sha256",
        "preflight_source_sha256", "pair_preview_digest",
        "model_loaded", "model_invoked",
        "inference_performed", "runtime_condition_created",
        "learning_established", "authority") if args.prompt_preview_only else (
        "cycle_root_id", "task_generation_seed", "task_family_id",
        "task_digest", "task_commitment_key_file_sha256",
        "task_commitment_nonce_pair_digest", "task_factory_source_sha256",
        "preflight_source_sha256", "protocol_digest", "answer_key_digest",
        "objective_request_bindings_digest", "model_loaded", "model_invoked",
        "inference_performed", "runtime_condition_created",
        "learning_established", "authority"))
    print(json.dumps({key: report[key] for key in summary_fields
        if key in report},
        sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        print(f"preflight failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
