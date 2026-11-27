"""Bind and optionally execute the balanced ordinary-chat transfer ladder."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from sentientos.canonical_memory import CanonicalMemoryStore
from sentientos.chat_service import PersistentConversationService
from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.conversation_session import (
    ConversationSessionStore,
    ordinary_chat_developmental_history_prompt_block_digest,
)
from sentientos.developmental_companion_bridge import ResidentDevelopmentalCompanionBridge
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker, validate_receipt
from sentientos.local_model import LocalModel
from sentientos.local_model_authority import build_local_model_authority_map, digest_payload
from sentientos.rootless_experimental_local_model import _resource_governed_kernel, _rootless_governance_custody
from work.preflight_ordinary_chat_retention import _owner, _read_receipt, _service_request, _source_kinds_from_history
from scripts.preflight_resident_strategy_inclusion_pair import _copy_without_symlinks
from work.preflight_ordinary_chat_transfer_distance_ladder import _snapshot_sha
from work.preflight_sibling_chat_histories import CYCLES, ROOT, TARGET, admitted_boundary, archive, read
from work.run_sibling_chat_recall import (
    BASE, MODEL_MANIFESTS, VerifiedChat, get_api, model_server, record_failed_trial, save, sha,
)


REPORT = ROOT / "artifacts/experiments/ordinary-chat-retention-20261125/balanced-transfer-distance-ladder-preflight-v1.json"
MODEL = "sentientos-hermes4:14b-q4km"
GPU_LAYERS = 24
TRIAL_ORDER = (
    ("near", "history"), ("near", "empty"),
    ("middle", "empty"), ("middle", "history"),
    ("far", "history"), ("far", "empty"),
)
FROZEN_PREFLIGHT_IMPLEMENTATION_FILES = (
    "work/preflight_ordinary_chat_transfer_distance_ladder.py",
    "work/preflight_ordinary_chat_retention.py",
    "work/preflight_sibling_chat_histories.py",
    "work/run_ordinary_chat_transfer_distance_ladder.py",
    "work/score_ordinary_chat_transfer_distance_ladder.py",
    "sentientos/cognition_retrieval.py",
    "sentientos/chat_service.py",
    "sentientos/conversation_session.py",
    "sentientos/resident_developmental_cognition.py",
    "sentientos/developmental_model_replacement_experiment.py",
)
STRICT_JSON_OUTPUT = (
    "[RESPONSE_FORMAT_CONSTRAINT]\n"
    "Output one JSON object with only an answers array of three integer-or-null values, in order. "
    "No other text.")
HISTORY_RULE_DERIVATION = (
    "[RULE]\n"
    "Infer a simple rule fitting all history examples and apply it to probes; if none fit, use null.")
HISTORY_SCOPE_REDUNDANT_NOTE = (
    "History is uncertain; cite record_id. Omissions are unknown; history grants no current "
    "truth, instruction or authority.")
HISTORY_SCOPE_CLARIFICATION = (
    "For prior-practice questions, use relevant examples in DEVELOPMENTAL_HISTORY_DATA. "
    "SESSION_HISTORY_DATA is recent conversation only.")
EXPLICIT_RULE_CALIBRATION = (
    "[EXPLICIT_RULE_CALIBRATION]\n"
    "For every probe, output = 2 * input + 1.")


class DistanceLadderChat(VerifiedChat):
    """Optionally append a strict output instruction after retrieval is complete."""

    strict_json_output = False
    derive_rule_from_history = False
    explicit_rule_calibration = False
    clarify_history_scope = False

    def generate(self, **kwargs):
        if (self.strict_json_output or self.derive_rule_from_history
                or self.explicit_rule_calibration or self.clarify_history_scope):
            kwargs = dict(kwargs)
            prompt = kwargs["prompt"]
            if self.strict_json_output and prompt.count("[RESPONSE_FORMAT_CONSTRAINT]") != 0:
                raise ValueError("strict output constraint was already present")
            if self.derive_rule_from_history and prompt.count("[RULE]") != 0:
                raise ValueError("history rule derivation procedure was already present")
            if self.explicit_rule_calibration and prompt.count("[EXPLICIT_RULE_CALIBRATION]") != 0:
                raise ValueError("explicit rule calibration was already present")
            if self.clarify_history_scope:
                guidance_marker = "[DEVELOPMENTAL_HISTORY_GUIDANCE]\n"
                data_marker = "\n[DEVELOPMENTAL_HISTORY_DATA]\n"
                if prompt.count(guidance_marker) > 1 or prompt.count(data_marker) > 1:
                    raise ValueError("developmental history scope markers are ambiguous")
                if guidance_marker in prompt and data_marker in prompt:
                    guidance_start = prompt.index(guidance_marker) + len(guidance_marker)
                    data_start = prompt.index(data_marker, guidance_start)
                    guidance = prompt[guidance_start:data_start]
                    if HISTORY_SCOPE_CLARIFICATION in guidance:
                        raise ValueError("history scope clarification was already present")
                    if guidance.count(HISTORY_SCOPE_REDUNDANT_NOTE) != 1:
                        raise ValueError("history scope treatment could not find its replaceable note")
                    guidance = guidance.replace(
                        HISTORY_SCOPE_REDUNDANT_NOTE, HISTORY_SCOPE_CLARIFICATION, 1)
                    prompt = prompt[:guidance_start] + guidance + prompt[data_start:]
                    linkage = kwargs.get("caller_linkage")
                    if not isinstance(linkage, dict):
                        raise ValueError("history scope clarification requires caller linkage")
                    linkage = dict(linkage)
                    linkage["ordinary_developmental_history_prompt_block_digest"] = (
                        ordinary_chat_developmental_history_prompt_block_digest(prompt))
                    kwargs["caller_linkage"] = linkage
            suffix = []
            if self.derive_rule_from_history:
                suffix.append(HISTORY_RULE_DERIVATION)
            if self.explicit_rule_calibration:
                suffix.append(EXPLICIT_RULE_CALIBRATION)
            if self.strict_json_output:
                suffix.append(STRICT_JSON_OUTPUT)
            kwargs["prompt"] = prompt.rstrip() + "\n\n" + "\n\n".join(suffix)
        return super().generate(**kwargs)


def _evidence_signature(items):
    return [{key: item.get(key) for key in (
        "record_id", "source_run_id", "source_score_digest", "task_family_id", "examples")}
        for item in items]


def run(cycles: Path, install: Path, models: Path, root: Path, *,
        expected_plan_sha256: str | None = None, preflight_only: bool = False,
        gpu_layers: int = GPU_LAYERS, strict_json_output: bool = False,
        derive_rule_from_history: bool = False,
        explicit_rule_calibration: bool = False,
        clarify_history_scope: bool = False,
        derive_affine_hypothesis: bool = False,
        include_affine_negative_control: bool = False,
        seed: int = 42,
        report_path: Path | None = None,
        parent_snapshot: Path | None = None) -> None:
    if type(gpu_layers) is not int or not 1 <= gpu_layers <= 128:
        raise ValueError("transfer-ladder inference requires 1 through 128 GPU layers")
    if not preflight_only and expected_plan_sha256 is None:
        raise ValueError("inference requires the reviewed model-bound plan hash")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("seed must be an integer from 0 through 2**32 - 1")
    if expected_plan_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_plan_sha256):
        raise ValueError("expected plan hash must be 64 lowercase hexadecimal characters")
    if sum((derive_rule_from_history, explicit_rule_calibration, clarify_history_scope,
            derive_affine_hypothesis)) > 1:
        raise ValueError("history derivation and explicit rule calibration are separate treatments")
    if include_affine_negative_control and not derive_affine_hypothesis:
        raise ValueError("affine negative control requires the derived-candidate treatment")
    if (derive_rule_from_history or explicit_rule_calibration or clarify_history_scope
            or derive_affine_hypothesis) and not strict_json_output:
        raise ValueError("cognition treatments require the matched strict JSON constraint")
    if not (os.environ.get("SENTIENTOS_OLLAMA_MODELS") or os.environ.get("SENTIENTOS_OLLAMA_CPU_MODELS")):
        raise ValueError("GPU inference requires an explicitly isolated external Ollama server")
    manifest_digest = MODEL_MANIFESTS[MODEL]
    root.mkdir(parents=True, exist_ok=False)
    selected_report = report_path or REPORT
    protocol = read(selected_report)
    if (protocol.get("schema") not in {
                "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v1",
                "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v2",
                "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v3",
                "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v8",
                "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v9"}
            or protocol.get("inference_performed") is not False
            or protocol.get("model_bound_execution_plan_created") is not False
            or protocol.get("probe_inputs_disjoint_from_history_and_prior_probes") is not True
            or protocol.get("all_tier_prompts_match_outside_probe_values") is not True):
        raise ValueError("distance-ladder model-free preflight is not qualified")
    protocol_has_affine_negative_control = protocol.get("schema", "").endswith(":v9")
    if include_affine_negative_control != protocol_has_affine_negative_control:
        raise ValueError("negative-control option does not match the frozen protocol")
    expected_arms = (["history", "derived_history", "sham_history", "empty"]
        if protocol_has_affine_negative_control else
        ["history", "derived_history", "empty"]
        if protocol.get("schema", "").endswith(":v8") else ["history", "empty"])
    if (protocol.get("arms") != expected_arms
            or (protocol.get("derived_rule_hypothesis_treatment") is not None
                and not protocol.get("schema", "").endswith((":v8", ":v9")))
            or (protocol.get("schema", "").endswith((":v8", ":v9"))
                and protocol.get("derived_rule_hypothesis_treatment")
                    != "exact_integer_affine_fit_from_scored_rows:v1")
            or (protocol_has_affine_negative_control
                and protocol.get("affine_negative_control_treatment")
                    != "same_width_offset_step_protocol_sham:v1")
            or derive_affine_hypothesis != (expected_arms[0] == "history"
                and len(expected_arms) in {3, 4})
            or protocol_has_affine_negative_control != (len(expected_arms) == 4)):
        raise ValueError("run treatment does not match the frozen preflight arms")
    if protocol.get("schema", "").endswith((":v8", ":v9")):
        implementation_hashes = protocol.get("implementation_sha256")
        if (not isinstance(implementation_hashes, dict)
                or set(implementation_hashes) != set(FROZEN_PREFLIGHT_IMPLEMENTATION_FILES)
                or any(not isinstance(implementation_hashes.get(name), str)
                    or sha((ROOT / name).read_bytes()) != implementation_hashes[name]
                    for name in FROZEN_PREFLIGHT_IMPLEMENTATION_FILES)):
            raise ValueError("frozen preflight implementation differs from current source")
    trial_order = tuple(tuple(item) for item in protocol.get("trial_order", TRIAL_ORDER))
    if (len(trial_order) != len(expected_arms) * len(protocol.get("tiers", {}))
            or any(len(item) != 2 or item[1] not in expected_arms
                or item[0] not in protocol.get("tiers", {}) for item in trial_order)
            or len(set(trial_order)) != len(trial_order)):
        raise ValueError("frozen trial order does not match the preflight arms")
    target_cycle = (cycles / ("rootless-cognition-cycle-" + TARGET)
                    if cycles is not None and parent_snapshot is None else None)

    with model_server(install, models, root, MODEL, manifest_digest) as (manifest, version), \
            _rootless_governance_custody(root):
        options = {"api_base": BASE, "model": MODEL, "manifest_sha256": manifest_digest,
                   "num_gpu": gpu_layers, "num_thread": 2, "timeout_seconds": 120,
                   "seed": seed, "think": False, "keep_alive": "5m"}
        config = ModelConfig([ModelCandidate(manifest, "ollama", MODEL, options)],
            max_context_tokens=4096,
            generation=GenerationConfig(max_new_tokens=160, temperature=0.0, top_p=1.0))
        authority = build_local_model_authority_map(config, allowed_roots=[manifest.parent])
        model = LocalModel.load_candidate(0, config=config)
        identity = model.active_identity.to_dict()
        identity_binding = protocol.get("identity_binding")
        if parent_snapshot is not None:
            if (not isinstance(identity_binding, dict)
                    or identity_binding.get("model") != MODEL
                    or identity_binding.get("model_manifest_sha256") != manifest_digest
                    or identity_binding.get("model_identity") != identity
                    or _snapshot_sha(parent_snapshot) != protocol.get("parent_snapshot_tree_sha256")):
                raise ValueError("parent snapshot or model identity differs from the frozen source-near report")
        if target_cycle is not None:
            historical_request = _read_receipt(target_cycle)[1]["request"]
        else:
            if parent_snapshot is None:
                raise ValueError("cycles root or a bound parent snapshot is required")
            historical_request = {
                "active_model_identity": identity,
                "model_id": MODEL,
                "model_artifact_digest": manifest_digest,
                "authority_map_digest": authority.map_digest,
                "authority_map_policy_digest": authority.policy_digest,
            }
        if not authority.record_for_active_identity(model.active_identity, "local_user_chat"):
            raise ValueError("ordinary-chat model identity is ineligible")
        inference = DistanceLadderChat(GovernedLocalModelInvoker(model=model, authority_map=authority,
            kernel=_resource_governed_kernel(root), runtime_root=root / "inference-custody"))
        inference.strict_json_output = strict_json_output
        inference.derive_rule_from_history = derive_rule_from_history
        inference.explicit_rule_calibration = explicit_rule_calibration
        inference.clarify_history_scope = clarify_history_scope

        history_root = root / "history" / "resident-cognition"
        if parent_snapshot is None:
            parent_cycle = cycles / ("rootless-cognition-cycle-" + CYCLES["parent"])
            archive(parent_cycle, history_root)
        else:
            _copy_without_symlinks(parent_snapshot / "resident-cognition", history_root)
            _copy_without_symlinks(parent_snapshot / "inference-custody" / "receipts",
                                   history_root.parent / "inference-custody" / "receipts")
            if os.name == "posix":
                for path in sorted(history_root.parent.rglob("*"), reverse=True):
                    if path.is_dir():
                        path.chmod(0o700)
                    elif path.is_file():
                        path.chmod(0o600)
                history_root.parent.chmod(0o700)
            parent_cycle = history_root.parent
        kinds = _source_kinds_from_history(history_root / "history")
        history_owner = _owner(history_root, kinds, history_root.parent, historical_request)
        example_presentation = protocol.get("example_presentation", "record_linked")
        if example_presentation not in {"structured_only", "record_linked"}:
            raise ValueError("model-free protocol has an unknown example presentation")
        history_owner.include_human_readable_integer_examples = (
            example_presentation == "record_linked")
        if protocol.get("schema", "").endswith((":v8", ":v9")):
            if (protocol.get("derived_rule_hypothesis_treatment")
                    != "exact_integer_affine_fit_from_scored_rows:v1"
                    or protocol.get("derived_rule_hypothesis_projection_verified") is not True
                    or not derive_affine_hypothesis):
                raise ValueError("derived affine hypothesis preflight is not qualified")
            history_owner.include_affine_rule_guidance = True
            derived_root = root / "derived-history" / "resident-cognition"
            derived_root.parent.mkdir(parents=True, exist_ok=True)
            _copy_without_symlinks(history_root, derived_root)
            derived_owner = _owner(derived_root, kinds, history_root.parent,
                historical_request)
            derived_owner.include_human_readable_integer_examples = (
                example_presentation == "record_linked")
            derived_owner.include_affine_rule_hypothesis = True
            derived_owner.include_affine_rule_guidance = True
            owners_extra = {"derived_history": derived_owner}
            if protocol_has_affine_negative_control:
                sham_root = root / "sham-history" / "resident-cognition"
                sham_root.parent.mkdir(parents=True, exist_ok=True)
                _copy_without_symlinks(history_root, sham_root)
                sham_owner = _owner(sham_root, kinds, history_root.parent,
                    historical_request)
                sham_owner.include_human_readable_integer_examples = (
                    example_presentation == "record_linked")
                sham_owner.include_affine_rule_negative_control = True
                sham_owner.include_affine_rule_guidance = True
                owners_extra["sham_history"] = sham_owner
        elif derive_affine_hypothesis:
            raise ValueError("derived affine hypothesis requires its frozen candidate preflight")
        expected_boundary = (protocol.get("parent_history_boundary_digest") if parent_snapshot is not None
            else read(ROOT / "artifacts/experiments/ordinary-chat-retention-20261125/later-session-novel-transfer-preflight-v3.json")[
                "arms"]["parent"]["admitted_boundary_digest"])
        if admitted_boundary(history_owner.writeback.inspect_completed_records()) != expected_boundary:
            raise ValueError("parent history differs from the archived transfer source")
        empty_root = root / "empty" / "resident-cognition"
        empty_root.mkdir(parents=True)
        empty_owner = _owner(empty_root, kinds, target_cycle or parent_cycle, historical_request)
        owners = {"history": history_owner, "empty": empty_owner}
        if derive_affine_hypothesis:
            owners.update(owners_extra)
        snapshots = {arm: owner.ordinary_chat_developmental_history_state_snapshot()
                     for arm, owner in owners.items()}

        questions, captures, base_by_condition, normalized_bases = {}, {}, {}, []
        for tier, tier_protocol in protocol["tiers"].items():
            questions[tier] = tier_protocol["question"]
            expected_evidence = tier_protocol["captures"]["history"]["prompt_score_evidence"]
            for arm in protocol["arms"]:
                key = tier + "_" + arm
                current_owner = owners[arm]
                base, captured = _service_request(current_owner, root / "preflight" / tier / arm,
                    identity, questions[tier], bind_invocation=True,
                    capture_adapter=inference,
                    capture_history_instruction=derive_affine_hypothesis)
                base_by_condition[key] = base
                captures[key] = captured
                normalized_bases.append(base.replace(", ".join(map(str, tier_protocol["probe_inputs"])), "[PROBES]"))
                if arm in {"history", "derived_history", "sham_history"}:
                    actual = captured["prompt_score_evidence"]
                    if _evidence_signature(actual) != _evidence_signature(expected_evidence):
                        raise ValueError(f"{tier} history prompt selected different scored evidence")
                    if captured.get("prompt_example_renderings") != tier_protocol[
                            "captures"][arm].get("prompt_example_renderings"):
                        raise ValueError(f"{tier} history prompt changed the bound rendering")
                    if captured.get("derived_rule_hypotheses", []) != tier_protocol[
                            "captures"][arm].get("derived_rule_hypotheses", []):
                        raise ValueError(
                            f"{tier} history prompt changed the bound derived candidate")
                    if captured.get("history_instruction") != tier_protocol[
                            "captures"][arm].get("history_instruction"):
                        raise ValueError(
                            f"{tier} {arm} prompt changed its frozen history guidance")
                    if captured.get("ordinary_history_selection") != tier_protocol[
                            "captures"][arm].get("ordinary_history_selection"):
                        raise ValueError(
                            f"{tier} {arm} prompt changed its frozen history selection")
                elif (captured["prompt_score_evidence"]
                        or captured.get("prompt_example_renderings")
                        or captured.get("derived_rule_hypotheses")
                        or captured.get("ordinary_history_selection") is not None
                        or captured["history_block_digest"] is not None):
                    raise ValueError(f"{tier} empty control exposed developmental history")
            if len({base_by_condition[tier + "_" + arm] for arm in protocol["arms"]}) != 1:
                raise ValueError(f"{tier} prompts differ outside the history block")
        if len(set(normalized_bases)) != 1:
            raise ValueError("distance-tier prompt templates differ beyond probe values")

        plan = {
            "schema": "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v12"
                if protocol_has_affine_negative_control else
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v11"
                if derive_affine_hypothesis else
                "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v5"
                if clarify_history_scope else "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v4"
                if explicit_rule_calibration else (
                    "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v3"
                    if derive_rule_from_history else (
                    "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v2"
                    if strict_json_output else "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v1")),
            "source_report_sha256": sha(selected_report.read_bytes()),
            "ladder_design": protocol.get("ladder_design", "balanced_magnitude_v1"),
            "example_presentation": example_presentation,
            "task_family_id": protocol.get("task_family_id"),
            "parent_snapshot_tree_sha256": protocol.get("parent_snapshot_tree_sha256"),
            "model": MODEL, "model_manifest_sha256": manifest_digest,
            "model_identity": identity, "ollama_version": version,
            "options": options, "context_tokens": config.max_context_tokens,
            "generation": config.generation.as_kwargs(), "gpu_layers": gpu_layers,
            "format_treatment": "strict_json_post_retrieval:v1" if strict_json_output
                else "user_message_only:v1",
            "output_constraint": STRICT_JSON_OUTPUT if strict_json_output else None,
            "output_constraint_sha256": sha(STRICT_JSON_OUTPUT.encode()) if strict_json_output else None,
            "semantic_treatment": ("clarify_developmental_history_scope:v1" if clarify_history_scope else
                "explicit_mapping_calibration:v1" if explicit_rule_calibration else
                "derive_rule_from_available_history:v3" if derive_rule_from_history else None),
            "semantic_procedure": (HISTORY_SCOPE_CLARIFICATION if clarify_history_scope else
                EXPLICIT_RULE_CALIBRATION if explicit_rule_calibration else
                HISTORY_RULE_DERIVATION if derive_rule_from_history else None),
            "semantic_procedure_sha256": (sha(HISTORY_SCOPE_CLARIFICATION.encode()) if clarify_history_scope else
                sha(EXPLICIT_RULE_CALIBRATION.encode()) if explicit_rule_calibration else
                sha(HISTORY_RULE_DERIVATION.encode()) if derive_rule_from_history else None),
            "derived_rule_hypothesis_treatment": (
                "exact_integer_affine_fit_from_scored_rows:v1"
                if derive_affine_hypothesis else None),
            "affine_negative_control_treatment": (
                protocol.get("affine_negative_control_treatment")
                if protocol_has_affine_negative_control else None),
            "arms": protocol["arms"],
            "trial_order": [{"tier": tier, "arm": arm} for tier, arm in trial_order],
            "tiers": {tier: {"probe_inputs": entry["probe_inputs"],
                "answer_key_commitment": entry["answer_key_commitment"],
                "question": entry["question"]} for tier, entry in protocol["tiers"].items()},
            "prompt_bindings": captures,
            "matched_base_sha256": sha(normalized_bases[0].encode()),
            "source_code_sha256": {path: sha((ROOT / path).read_bytes()) for path in (
                "work/run_ordinary_chat_transfer_distance_ladder.py",
                "work/preflight_ordinary_chat_transfer_distance_ladder.py",
                "work/preflight_ordinary_chat_retention.py",
                "sentientos/cognition_retrieval.py",
                "work/preflight_sibling_chat_histories.py",
                "work/run_sibling_chat_recall.py", "sentientos/chat_service.py",
                "sentientos/conversation_session.py", "sentientos/resident_developmental_cognition.py",
                "work/score_ordinary_chat_transfer_distance_ladder.py")},
            "primary_outcome": ("Derived-history minus sham-history exact-answer count per tier; report derived and sham against raw and empty history."
                if protocol_has_affine_negative_control else
                "Derived-history minus raw-history exact-answer count per tier; also report each against empty history."
                if derive_affine_hypothesis else
                "Exact-answer count per tier and history condition; report history-minus-empty differences."),
            "secondary_outcome": "Strict JSON-only format validity, independent of exact-answer correctness.",
            "inference_performed": False, "learning_established": False,
        }
        save(root / "plan.json", plan)
        plan_hash = sha((root / "plan.json").read_bytes())
        if expected_plan_sha256 is not None and plan_hash != expected_plan_sha256:
            save(root / "preflight_rejection.json", {"expected_plan_sha256": expected_plan_sha256,
                "observed_plan_sha256": plan_hash, "model_invoked": False, "inference_performed": False})
            raise ValueError("fresh execution plan differs from the reviewed plan; inference was not started")
        if expected_plan_sha256 is not None and not preflight_only:
            save(root / "preflight_binding.json", {
                "schema": "sentientos.ordinary_chat_transfer_distance_ladder_preflight_binding:v1",
                "preflight_plan_sha256": expected_plan_sha256,
                "full_run_plan_sha256": plan_hash, "matched": True,
            })
        if preflight_only:
            if get_api("ps")["models"]:
                raise ValueError("preflight-only mode found a resident server model")
            save(root / "preflight.json", {"schema": "sentientos.ordinary_chat_transfer_distance_ladder_execution_preflight:v1",
                "plan_sha256": plan_hash, "model_invoked": False, "inference_performed": False,
                "learning_established": False, "resident_vram_bytes": 0})
            print("preflight_saved", plan_hash, flush=True)
            return

        trials = []
        inference.capture_only = False
        for index, (tier, arm) in enumerate(trial_order):
            key = tier + "_" + arm
            inference.frozen_hash = captures[key]["prompt_sha256"]
            inference.receipt = None
            trial_root = root / "trials" / str(index)
            service = PersistentConversationService(inference=inference,
                inference_timeout_seconds=options["timeout_seconds"],
                session_store=ConversationSessionStore(trial_root / "sessions"),
                memory_store=CanonicalMemoryStore(trial_root / "memory"),
                resident_cognition_bridge=ResidentDevelopmentalCompanionBridge(
                    owners[arm], cognition_available=lambda: False))
            session_id = service.create_session()
            try:
                delivered = service.chat(questions[tier], session_id=session_id,
                    request_id=f"transfer-ladder-{tier}-{arm}").response
            except Exception as error:
                record_failed_trial(root, trial_root, index=index, condition=key,
                    plan_hash=plan_hash, prompt_hash=captures[key]["invocation_prompt_digest"], error=error)
                raise
            receipt = inference.receipt
            disk = read(root / "inference-custody" / "receipts" / (receipt.receipt_id + ".json"))
            if (not validate_receipt(disk)[0] or disk["receipt_digest"] != receipt.receipt_digest
                    or disk["request"]["active_model_identity"] != identity
                    or disk["request"]["prompt_digest"] != captures[key]["invocation_prompt_digest"]
                    or disk["output_digest"] != digest_payload({"output": receipt.output_text})
                    or disk["status"] != "admitted_completed" or receipt.fallback_occurred
                    or receipt.output_text is None):
                raise ValueError("governed inference failed its prompt or receipt binding")
            placement, = get_api("ps")["models"]
            if placement["digest"] != manifest_digest or placement["size_vram"] <= 0:
                raise ValueError("pinned model was not resident on the requested GPU")
            trial = {"trial": index, "tier": tier, "arm": arm, "session_id": session_id,
                "plan_sha256": plan_hash,
                "prompt_sha256": captures[key]["prompt_sha256"], "receipt": disk,
                "model_output": receipt.output_text, "delivered": delivered,
                "resident_vram_bytes": placement["size_vram"], "independent_scoring": "pending"}
            save(trial_root / "result.json", trial)
            trials.append(trial)
            print(index, tier, arm, "inference_complete", flush=True)
        if any(owner.ordinary_chat_developmental_history_state_snapshot() != snapshots[arm]
                for arm, owner in owners.items()):
            raise ValueError("read-only transfer ladder changed developmental history")
        save(root / "result.json", {"plan_sha256": plan_hash, "trials": trials,
            "learning_established": False, "independent_scoring": "pending"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cycles", "ollama_install", "models", "new_run_directory"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--gpu-layers", type=int, default=GPU_LAYERS)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--strict-json-output", action="store_true",
        help="Append the frozen JSON-only constraint after history retrieval")
    parser.add_argument("--derive-rule-from-history", action="store_true",
        help="Add a rule-derivation procedure equally to history and empty arms; requires strict JSON")
    parser.add_argument("--explicit-rule-calibration", action="store_true",
        help="Supply the mapping equally to both arms as an arithmetic/format calibration")
    parser.add_argument("--clarify-history-scope", action="store_true",
        help="Clarify that selected DEVELOPMENTAL_HISTORY_DATA is historical evidence, not recent-turn transcript")
    parser.add_argument("--derive-affine-hypothesis", action="store_true",
        help="Expose a non-authoritative affine candidate fitted from all correct scored history rows")
    parser.add_argument("--include-affine-negative-control", action="store_true",
        help="Add a provenance-labeled same-width sham candidate arm; requires --derive-affine-hypothesis")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--report", type=Path,
        help="Use a separately frozen model-free protocol report")
    parser.add_argument("--parent-snapshot", type=Path,
        help="Use the parent snapshot whose history boundary is bound by the report")
    args = parser.parse_args()
    run(args.cycles, args.ollama_install, args.models, args.new_run_directory,
        expected_plan_sha256=args.expected_plan_sha256,
        preflight_only=args.preflight_only, gpu_layers=args.gpu_layers,
        strict_json_output=args.strict_json_output,
        derive_rule_from_history=args.derive_rule_from_history,
        explicit_rule_calibration=args.explicit_rule_calibration,
        clarify_history_scope=args.clarify_history_scope,
        derive_affine_hypothesis=args.derive_affine_hypothesis,
        include_affine_negative_control=args.include_affine_negative_control,
        seed=args.seed,
        report_path=args.report, parent_snapshot=args.parent_snapshot)
