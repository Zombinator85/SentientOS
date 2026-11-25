#!/usr/bin/env python3
"""Build and verify a resident strategy-inclusion pair without model inference.

The owner runs against a private copy of one cycle's resident-cognition state.
An invocation adapter reconstructs request metadata from an existing local
receipt and fails closed if inference is attempted. The output contains only
protocol bindings and digests, never prompts or model outputs.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.developmental_model_replacement_experiment import (
    ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
    rootless_integer_affine_transfer_task_pair,
)
from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore,
)
from sentientos.governed_local_model_invocation import (
    GovernedLocalModelInvoker,
    LocalModelInvocationBudget,
    LocalModelInvocationRequest,
    validate_receipt,
)
from sentientos.local_model import ActiveModelIdentity
from sentientos.local_model import (
    GenerationConfig, ModelCandidate, ModelConfig,
    candidate_artifact_identity, candidate_configuration_digest,
)
from sentientos.local_model_authority import (
    build_rootless_experimental_developmental_authority_map,
    digest_payload,
)
from sentientos.resident_developmental_cognition import (
    ResidentDevelopmentalCognitionConfig,
    ResidentDevelopmentalCognitionOwner,
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
from work.strategy_inclusion_intervention import (
    _digest,
    prepare_strategy_inclusion_pair,
    validate_strategy_inclusion_protocol,
)
from work.historical_examples_intervention import HistoricalExamplesPairJournal


class _NoInferenceInvoker:
    """Build governed request values from a receipt; never execute a request."""

    def __init__(self, request: Mapping[str, Any], *,
            identity_override: Mapping[str, Any] | None = None,
            request_builder: Any | None = None,
            authority_policy_digest: str | None = None) -> None:
        identity = (identity_override if identity_override is not None
            else request.get("active_model_identity"))
        if not isinstance(identity, Mapping) or not identity:
            raise ValueError("source_receipt_model_identity_missing")
        self._identity = dict(identity)
        self.model = SimpleNamespace(active_identity=ActiveModelIdentity(**identity))
        self.authority_map = SimpleNamespace(
            map_digest=request.get("authority_map_digest"),
            policy_digest=(authority_policy_digest
                or request.get("authority_map_policy_digest")))
        self._model_id = request.get("model_id")
        self._model_artifact_digest = request.get("model_artifact_digest")
        self._request_builder = request_builder
        self.requests: list[LocalModelInvocationRequest] = []

    def observed_current_model_identity(self) -> Mapping[str, Any]:
        return dict(self._identity)

    def build_request(self, *, purpose: str, prompt: str, caller: str,
            correlation_id: str, lifecycle_phase: str = "runtime",
            expected_output_format: str = "text",
            budget: LocalModelInvocationBudget | None = None,
            upstream_evidence: Mapping[str, Any] | None = None,
            linkage: Mapping[str, Any] | None = None,
            structured_output_schema: Mapping[str, Any] | None = None
            ) -> LocalModelInvocationRequest:
        if self._request_builder is not None:
            request = self._request_builder.build_request(
                purpose=purpose, prompt=prompt, caller=caller,
                correlation_id=correlation_id, lifecycle_phase=lifecycle_phase,
                expected_output_format=expected_output_format, budget=budget,
                upstream_evidence=upstream_evidence, linkage=linkage,
                structured_output_schema=structured_output_schema)
            self.requests.append(request)
            return request
        if (not isinstance(self._model_id, str) or not self._model_id
                or not isinstance(self.authority_map.map_digest, str)
                or not self.authority_map.map_digest):
            raise ValueError("source_receipt_request_identity_invalid")
        request = LocalModelInvocationRequest(
            purpose=purpose, prompt=prompt, model_id=self._model_id,
            authority_map_digest=self.authority_map.map_digest,
            model_artifact_digest=self._model_artifact_digest,
            caller=caller, lifecycle_phase=lifecycle_phase,
            correlation_id=correlation_id,
            expected_output_format=expected_output_format,
            budget=budget or LocalModelInvocationBudget(),
            upstream_evidence=dict(upstream_evidence or {}),
            linkage=dict(linkage or {}),
            active_model_identity=dict(self._identity),
            authority_map_policy_digest=self.authority_map.policy_digest,
            structured_output_schema=(dict(structured_output_schema)
                if structured_output_schema is not None else None))
        self.requests.append(request)
        return request

    def invoke(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("cpu_strategy_preflight_forbids_model_inference")


class _LocalReceiptVerifier:
    """Read-only integrity verifier for receipts inside this rootless cycle."""

    def __init__(self, cycle_root: Path) -> None:
        self._root = cycle_root / "inference-custody" / "receipts"

    def verify_persisted_invocation_receipt(self, receipt_id: str,
            receipt_digest: str, *, expected_request_id: str,
            expected_request_digest: str,
            expected_active_model_identity: Mapping[str, Any]
            ) -> Mapping[str, Any]:
        if (not isinstance(receipt_id, str) or not receipt_id.startswith("lmrec-")
                or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-"
                    for ch in receipt_id)):
            raise ValueError("historical_receipt_identity_invalid")
        path = self._root / f"{receipt_id}.json"
        if path.is_symlink() or not path.is_file():
            raise ValueError("historical_receipt_missing")
        value = json.loads(path.read_text(encoding="utf-8"))
        request = value.get("request") if isinstance(value, Mapping) else None
        valid, reasons = validate_receipt(value)
        if (not valid or value.get("receipt_id") != receipt_id
                or value.get("receipt_digest") != receipt_digest
                or not isinstance(request, Mapping)
                or request.get("request_id") != expected_request_id
                or request.get("request_digest") != expected_request_digest
                or request.get("active_model_identity") !=
                    dict(expected_active_model_identity)):
            raise ValueError("historical_receipt_binding_invalid:" + ",".join(reasons))
        return dict(value)


def _read_receipt(cycle_root: Path) -> tuple[Path, dict[str, Any]]:
    receipt_root = cycle_root / "inference-custody" / "receipts"
    if receipt_root.is_symlink() or not receipt_root.is_dir():
        raise ValueError("cycle_receipt_root_unavailable")
    terminal_path = cycle_root / "cycle-result.json"
    if terminal_path.is_symlink() or not terminal_path.is_file():
        raise ValueError("cycle_terminal_model_identity_unavailable")
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    target_identity = (terminal.get("active_model_identity")
        if isinstance(terminal, Mapping) else None)
    cycle_id = terminal.get("run_id") if isinstance(terminal, Mapping) else None
    if (not isinstance(target_identity, Mapping) or not target_identity
            or not isinstance(cycle_id, str) or not cycle_id):
        raise ValueError("cycle_terminal_model_identity_invalid")
    target_identity_key = json.dumps(dict(target_identity), sort_keys=True,
        separators=(",", ":"))
    receipts: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(receipt_root.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            continue
        value = json.loads(path.read_text(encoding="utf-8"))
        request = value.get("request") if isinstance(value, Mapping) else None
        linkage = request.get("linkage") if isinstance(request, Mapping) else None
        session = (linkage.get("rootless_experimental_session")
            if isinstance(linkage, Mapping) else None)
        if (isinstance(request, Mapping)
                and isinstance(request.get("active_model_identity"), Mapping)
                and json.dumps(dict(request["active_model_identity"]),
                    sort_keys=True, separators=(",", ":")) == target_identity_key
                and request.get("purpose") ==
                    "resident_developmental_history_intervention_experiment"
                and isinstance(session, Mapping)
                and session.get("run_id") == cycle_id):
            receipts.append((path, dict(value)))
    if receipts:
        return receipts[-1]
    raise ValueError("matching_source_receipt_unavailable")


def _reconstruct_source_authority_policy_digest(cycle_root: Path,
        identity_payload: Mapping[str, Any]) -> str:
    """Rebuild the stable authority policy from the pinned source config."""
    terminal = json.loads((cycle_root / "cycle-result.json").read_text(
        encoding="utf-8"))
    observation = (terminal.get("model_configuration_observation")
        if isinstance(terminal, Mapping) else None)
    payload = observation.get("payload") if isinstance(observation, Mapping) else None
    if (not isinstance(payload, Mapping)
            or payload.get("engine") != "ollama"
            or not isinstance(payload.get("options"), Mapping)
            or not isinstance(payload.get("generation"), Mapping)
            or type(payload.get("max_context_tokens")) is not int):
        raise ValueError("source_model_configuration_observation_unavailable")
    artifact_path = Path(str(identity_payload.get("resolved_artifact_path", "")))
    options = dict(payload["options"])
    model_name = options.get("model")
    if not isinstance(model_name, str) or not model_name:
        raise ValueError("source_model_configuration_model_name_invalid")
    candidate = ModelCandidate(artifact_path, "ollama", model_name, options)
    config = ModelConfig([candidate], default_engine="ollama",
        max_context_tokens=payload["max_context_tokens"],
        generation=GenerationConfig(**dict(payload["generation"])))
    resolved, semantic, content_digest, artifact_size, sidecar_digest = (
        candidate_artifact_identity(candidate, {}))
    reconstructed_identity = ActiveModelIdentity(engine="ollama",
        resolved_artifact_path=resolved,
        semantic_artifact_identity=semantic,
        model_content_sha256=content_digest,
        artifact_size_bytes=artifact_size,
        sidecar_metadata_digest=sidecar_digest,
        configuration_digest=candidate_configuration_digest(
            candidate, config, "ollama"),
        candidate_index=0, posture="development_only", fallback=False)
    if reconstructed_identity.to_dict() != dict(identity_payload):
        raise ValueError("source_model_configuration_identity_mismatch")
    authority_map = build_rootless_experimental_developmental_authority_map(
        config, allowed_roots=(artifact_path.parent,),
        observed_at="2026-11-23T00:00:00+00:00")
    record = authority_map.record_for_active_identity(reconstructed_identity,
        "resident_developmental_history_intervention_experiment")
    if record is None:
        raise ValueError("source_model_authority_policy_unavailable")
    return authority_map.policy_digest


def _copy_without_symlinks(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("cycle_resident_cognition_root_invalid")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError("cycle_resident_cognition_contains_symlink")
    shutil.copytree(source, destination)


def _source_kinds_from_history(history_root: Path) -> tuple[str, ...]:
    kinds: set[str] = set()
    records = history_root / "records"
    if records.is_symlink() or not records.is_dir():
        raise ValueError("copied_history_records_unavailable")
    for path in records.glob("*.json"):
        if path.is_symlink() or not path.is_file():
            raise ValueError("copied_history_record_not_regular")
        value = json.loads(path.read_text(encoding="utf-8"))
        candidate = value.get("candidate") if isinstance(value, Mapping) else None
        facts = candidate.get("selected_facts") if isinstance(candidate, Mapping) else None
        for fact in facts if isinstance(facts, list) else ():
            source = fact.get("source") if isinstance(fact, Mapping) else None
            kind = source.get("kind") if isinstance(source, Mapping) else None
            if isinstance(kind, str) and kind:
                kinds.add(kind)
    if not kinds:
        raise ValueError("copied_history_source_kinds_unavailable")
    return tuple(sorted(kinds))


def _plan_bound_identity(plan_path: Path, cycle_index: int, *,
        backend_seed: int | None = None,
        allow_recomputed_campaign_source_pin_mismatch: bool = False,
        authority_map_observed_at: str | None = None
        ) -> tuple[dict[str, Any], GovernedLocalModelInvoker, dict[str, Any]]:
    from work.rootless_history_boundary_campaign import (
        _load_plan, verify_model_identity_recipe,
    )
    from sentientos.rootless_experimental_ollama_epistemic_session import (
        _rootless_ollama_model_options,
    )
    plan = _load_plan(plan_path)
    identity_recipe_evidence = verify_model_identity_recipe(plan,
        allow_recomputed_campaign_source_pin_mismatch=
            allow_recomputed_campaign_source_pin_mismatch)
    cycle_count = len(plan["ordered_cycle_ids"])
    if type(cycle_index) is not int or not 0 <= cycle_index < cycle_count:
        raise ValueError("plan_cycle_index_out_of_bounds")
    recipe = plan["model_identity_recipe"]
    manifest_path = Path(recipe["resolved_manifest_path"])
    options = _rootless_ollama_model_options(
        model_name=recipe["model_name"],
        manifest_digest=recipe["manifest_sha256"],
        gpu_layers=recipe["gpu_layers"])
    if (backend_seed is not None and (type(backend_seed) is not int
            or not 0 <= backend_seed <= 2**31 - 1)):
        raise ValueError("plan_identity_backend_seed_invalid")
    effective_backend_seed = (plan["ordered_backend_seeds"][cycle_index]
        if backend_seed is None else backend_seed)
    options["seed"] = effective_backend_seed
    candidate = ModelCandidate(manifest_path, "ollama",
        recipe["model_name"], options)
    model_config = ModelConfig([candidate], default_engine="ollama",
        max_context_tokens=recipe["max_context_tokens"],
        generation=GenerationConfig(**dict(recipe["generation_config"])))
    resolved, semantic, content_digest, size, sidecar_digest = (
        candidate_artifact_identity(candidate, {}))
    identity_object = ActiveModelIdentity(engine="ollama",
        resolved_artifact_path=resolved,
        semantic_artifact_identity=semantic,
        model_content_sha256=content_digest, artifact_size_bytes=size,
        sidecar_metadata_digest=sidecar_digest,
        configuration_digest=candidate_configuration_digest(
            candidate, model_config, "ollama"),
        candidate_index=0, posture="development_only", fallback=False)
    identity = identity_object.to_dict()
    target_digest = digest_payload({"identity": identity})
    if (backend_seed is None and target_digest !=
            plan["ordered_model_identity_digests"][cycle_index]):
        raise ValueError("plan_model_identity_reconstruction_mismatch")
    authority_map_observed_at = (authority_map_observed_at
        or "2026-11-23T00:00:00+00:00")
    try:
        observed_time = datetime.fromisoformat(
            authority_map_observed_at.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("plan_authority_map_observation_time_invalid") from exc
    if (observed_time.tzinfo is None or observed_time.utcoffset() is None
            or authority_map_observed_at.endswith("-00:00")):
        raise ValueError("plan_authority_map_observation_time_invalid")
    authority_map = build_rootless_experimental_developmental_authority_map(
        model_config, allowed_roots=(manifest_path.parent,),
        observed_at=authority_map_observed_at)
    purpose = "resident_developmental_history_intervention_experiment"
    record = authority_map.record_for_active_identity(identity_object, purpose)
    if record is None:
        raise ValueError("plan_model_identity_authority_record_unavailable")
    request_builder = GovernedLocalModelInvoker.__new__(
        GovernedLocalModelInvoker)
    request_builder.model = SimpleNamespace(active_identity=identity_object)
    request_builder.authority_map = authority_map
    return identity, request_builder, {
        "campaign_id": plan["campaign_id"],
        "plan_digest": plan["plan_digest"],
        "cycle_id": plan["ordered_cycle_ids"][cycle_index],
        "cycle_index": cycle_index,
        "authority_map_observed_at": authority_map_observed_at,
        "planned_model_identity_digest": target_digest,
        "authority_map_digest": authority_map.map_digest,
        "model_id": record.model_id,
        "model_artifact_digest": record.model_content_sha256,
        "identity_recipe_evidence": identity_recipe_evidence,
        **({"effective_backend_seed": effective_backend_seed,
            "backend_seed_overrode_campaign_cycle_seed": True}
            if backend_seed is not None else {}),
    }


def build_preflight(*, cycle_root: Path, seed: int,
        task_family_id: str, plan_path: Path | None = None,
        cycle_index: int = 0,
        journal_root: Path | None = None) -> dict[str, Any]:
    cycle_root = cycle_root.resolve(strict=True)
    receipt_path, receipt = _read_receipt(cycle_root)
    request = receipt["request"]
    plan_binding: dict[str, Any] | None = None
    request_builder = None
    identity_override = None
    if plan_path is not None:
        identity_override, request_builder, plan_binding = (
            _plan_bound_identity(plan_path, cycle_index))
    identity = (identity_override if identity_override is not None
        else request["active_model_identity"])
    generation_config = receipt.get("generation_config")
    if not isinstance(generation_config, Mapping):
        raise ValueError("source_receipt_generation_config_missing")
    max_input_chars = generation_config.get("max_input_chars")
    timeout_seconds = generation_config.get("timeout_seconds")
    if (type(max_input_chars) is not int or not 1024 <= max_input_chars <= 48_000
            or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300):
        raise ValueError("source_receipt_generation_bounds_invalid")
    resident_root = cycle_root / "resident-cognition"
    with tempfile.TemporaryDirectory(prefix="sentientos-strategy-preview-") as temp:
        copied_root = Path(temp) / "resident-cognition"
        _copy_without_symlinks(resident_root, copied_root)
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
        authority_policy_digest = (None if request_builder is not None else
            _reconstruct_source_authority_policy_digest(cycle_root, identity))
        invoker = _NoInferenceInvoker(request,
            identity_override=identity_override,
            request_builder=request_builder,
            authority_policy_digest=authority_policy_digest)
        owner = ResidentDevelopmentalCognitionOwner(config=config,
            writeback=writeback,
            admission_authority=RuntimeAdmissionAuthority(
                definitions=definitions, ledger=ledger),
            invoker=invoker, current_sequence=ledger.current_sequence,
            invocation_receipt_verifier=_LocalReceiptVerifier(cycle_root))
        task_pair = rootless_integer_affine_transfer_task_pair(seed,
            task_family_id=task_family_id)
        task = task_pair[1]
        snapshot = WorldStateBoardBuilder(clock=lambda: datetime(
            2026, 11, 23, tzinfo=timezone.utc)).build((),
                manifest_id="resident-strategy-cpu-preflight")
        if not validate_snapshot(snapshot).valid:
            raise ValueError("synthetic_snapshot_invalid")
        preview = owner.preview_objective_strategy_inclusion_pair(
            snapshot=snapshot,
            tick_id=f"strategy-cpu-preflight-{seed}",
            objective_task=task)
        identity_digest = "sha256:" + digest_payload(dict(identity))
        if request_builder is not None:
            arm_requests = [item for item in invoker.requests
                if "objective_task_plan_digest" in item.upstream_evidence]
            if len(arm_requests) != 2:
                raise ValueError("planned_arm_requests_missing")
            record = request_builder.authority_map.record_for_active_identity(
                request_builder.model.active_identity,
                "resident_developmental_history_intervention_experiment")
            if record is None:
                raise ValueError("planned_model_authority_record_unavailable")
            def _generation_config(arm_request: LocalModelInvocationRequest
                    ) -> dict[str, Any]:
                actual = {
                    "max_new_tokens": min(arm_request.budget.max_new_tokens,
                        int(record.generation_ceilings.get("max_new_tokens",
                            arm_request.budget.max_new_tokens))),
                    "temperature": 0,
                    "structured_output_schema": (
                        dict(arm_request.structured_output_schema)
                        if arm_request.structured_output_schema is not None else None),
                    "use_model_chat_template": False,
                }
                actual = {key: value for key, value in actual.items()
                    if value is not None}
                return {**arm_request.budget.to_dict(),
                    "actual_generation_parameters": actual}
            generation_config = _generation_config(arm_requests[0])
            omitted_generation_config = _generation_config(arm_requests[1])
            if generation_config != omitted_generation_config:
                differing_fields = sorted(key for key in set(generation_config)
                    | set(omitted_generation_config)
                    if generation_config.get(key) !=
                        omitted_generation_config.get(key))
                details: list[str] = []
                for key in differing_fields:
                    left, right = generation_config.get(key), \
                        omitted_generation_config.get(key)
                    if isinstance(left, Mapping) and isinstance(right, Mapping):
                        nested = sorted(field for field in set(left) | set(right)
                            if left.get(field) != right.get(field))
                        details.append(key + "=" + ",".join(nested))
                        if "structured_output_schema" in nested:
                            details.append("schemas=" + json.dumps({
                                "included": left.get("structured_output_schema"),
                                "omitted": right.get("structured_output_schema")},
                                sort_keys=True, separators=(",", ":")))
                    else:
                        details.append(key)
                raise ValueError("planned_arm_generation_configs_differ:" +
                    ";".join(details) + ";requests=" + json.dumps([{
                        "purpose": item.purpose,
                        "output_format": item.expected_output_format,
                        "condition_id": item.linkage.get("condition_id"),
                        "objective_plan_bound": "objective_task_plan_digest"
                            in item.upstream_evidence,
                        "task_shape": item.upstream_evidence.get(
                            "objective_task_response_shape"),
                        "probe_count": item.upstream_evidence.get(
                            "objective_task_probe_count"),
                        "allow_abstention": item.upstream_evidence.get(
                            "objective_task_allow_abstention"),
                        "include_confidence": item.upstream_evidence.get(
                            "objective_task_include_confidence"),
                    } for item in arm_requests], sort_keys=True,
                        separators=(",", ":")))
            generation_config_source = (
                "governed_invoker_request_projection_without_resource_context")
        else:
            generation_config_source = "historical_receipt_generation_config"
        generation_config_digest = "sha256:" + digest_payload(
            dict(generation_config))
        prepared = prepare_strategy_inclusion_pair(
            target_model_identity_digest=identity_digest,
            task_digest=task.public_descriptor()["task_digest"],
            generation_config_digest=generation_config_digest,
            owner_prompt_pair_preview=preview)
        protocol = prepared["protocol"]
        private_task_plan_digest = None
        answer_key_digest = None
        if journal_root is not None:
            task_specification = task.specification()
            descriptor = task.public_descriptor()
            probes = descriptor.get("probe_inputs")
            multiplier = task_specification.get("multiplier")
            offset = task_specification.get("offset")
            if (not isinstance(probes, (list, tuple)) or not probes
                    or type(multiplier) is not int or type(offset) is not int):
                raise ValueError("strategy_inclusion_answer_key_invalid")
            answer_key = {_digest({
                "schema_version": "sentientos.objective_probe_binding:v1",
                "task_digest": descriptor["task_digest"],
                "probe_index": index, "probe_input": probe,
            }): multiplier * probe + offset
                for index, probe in enumerate(probes)}
            if set(answer_key) != set(protocol.get(
                    "probe_binding_digests", ())):
                raise ValueError("strategy_inclusion_answer_key_binding_mismatch")
            journal_store = DevelopmentalExperimentStore(journal_root)
            journal = HistoricalExamplesPairJournal(store=journal_store)
            private_task_plan_digest = journal.persist_private_task_plan(
                objective_task=task)
            answer_key_digest = _digest(answer_key)
            prepared = prepare_strategy_inclusion_pair(
                target_model_identity_digest=identity_digest,
                task_digest=descriptor["task_digest"],
                generation_config_digest=generation_config_digest,
                owner_prompt_pair_preview=preview,
                private_task_plan_digest=private_task_plan_digest,
                answer_key_digest=answer_key_digest)
            protocol = prepared["protocol"]
            persisted_protocol = journal_store.persist_strategy_inclusion_protocol(
                protocol)
            if persisted_protocol != protocol:
                raise ValueError("strategy_inclusion_protocol_persist_mismatch")
        validate_strategy_inclusion_protocol(protocol=protocol,
            target_model_identity_digest=identity_digest,
            task_digest=task.public_descriptor()["task_digest"])
        if any(value is True for value in (
                preview.get("inference_performed"),
                protocol.get("inference_performed"),
                preview.get("learning_established"),
                protocol.get("learning_established"),
                preview.get("authority"), protocol.get("authority"))):
            raise ValueError("cpu_preflight_claim_boundary_invalid")
        return {
            "schema_version": ("sentientos.resident_strategy_inclusion_cpu_preflight:v3"
                if journal_root is not None else
                "sentientos.resident_strategy_inclusion_cpu_preflight:v2"),
            "cycle_root_id": cycle_root.name,
            "source_receipt_id": receipt.get("receipt_id"),
            "source_receipt_digest": receipt.get("receipt_digest"),
            "source_model_identity_digest": identity_digest,
            "source_identity_posture": "reconstructed_from_verified_historical_receipt",
            "plan_binding": plan_binding,
            "task_family_id": task_family_id,
            "task_digest": task.public_descriptor()["task_digest"],
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_digest": snapshot.digest,
            "pair_preview_digest": preview["pair_preview_digest"],
            "strategy_evidence_summary": dict(
                preview["strategy_evidence_summary"]),
            "private_task_plan_digest": private_task_plan_digest,
            "answer_key_digest": answer_key_digest,
            "private_task_plan_persisted": journal_root is not None,
            "strategy_protocol_persisted": journal_root is not None,
            "protocol_digest": protocol.get("protocol_digest"),
            "generation_config_digest": generation_config_digest,
            "generation_config_source": generation_config_source,
            "arm_request_digests": dict(protocol["preview_request_digests"]),
            "arm_execution_tick_ids": dict(protocol["owner_execution_tick_ids"]),
            "owner_protocol_digests": {
                arm: preview["owner_protocols"][arm]["protocol_digest"]
                for arm in ("strategy_included", "strategy_omitted")},
            "strategy_pair_protocol": dict(protocol),
            "owner_arm_protocols": {
                arm: dict(preview["owner_protocols"][arm]["protocol"])
                for arm in ("strategy_included", "strategy_omitted")},
            "protocol_validation": "verified",
            "source_history_mutated": False,
            "model_loaded": False,
            "model_invoked": False,
            "learning_established": False,
            "authority": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-root", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=2026112709)
    parser.add_argument("--task-family-id", default=(
        ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY))
    parser.add_argument("--plan", type=Path,
        help="verified campaign plan; reconstruct this cycle's model identity without loading it")
    parser.add_argument("--cycle-index", type=int, default=0)
    parser.add_argument("--journal-root", type=Path,
        help="private experiment journal for the salted task plan and frozen protocol")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_preflight(cycle_root=args.cycle_root, seed=args.seed,
        task_family_id=args.task_family_id, plan_path=args.plan,
        cycle_index=args.cycle_index, journal_root=args.journal_root)
    if args.output.exists():
        raise ValueError("preflight_output_already_exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        print(f"preflight failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
