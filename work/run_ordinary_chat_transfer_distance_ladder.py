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
from sentientos.conversation_session import ConversationSessionStore
from sentientos.developmental_companion_bridge import ResidentDevelopmentalCompanionBridge
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker, validate_receipt
from sentientos.local_model import LocalModel
from sentientos.local_model_authority import build_local_model_authority_map, digest_payload
from sentientos.rootless_experimental_local_model import _resource_governed_kernel, _rootless_governance_custody
from work.preflight_ordinary_chat_retention import _owner, _read_receipt, _service_request, _source_kinds_from_history
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
STRICT_JSON_OUTPUT = (
    "[RESPONSE_FORMAT_CONSTRAINT]\n"
    "Output one JSON object with only an answers array of three integer-or-null values, in order. "
    "No other text.")
HISTORY_RULE_DERIVATION = (
    "[HISTORY_RULE_DERIVATION_PROCEDURE]\n"
    "Infer the simplest plausible input-output rule that fits the available developmental-history examples, "
    "then apply it to each probe. Check the rule against every available example before answering. "
    "If there are no usable examples or no simple rule fits them, use null.")


class DistanceLadderChat(VerifiedChat):
    """Optionally append a strict output instruction after retrieval is complete."""

    strict_json_output = False
    derive_rule_from_history = False

    def generate(self, **kwargs):
        if self.strict_json_output or self.derive_rule_from_history:
            kwargs = dict(kwargs)
            prompt = kwargs["prompt"]
            if self.strict_json_output and prompt.count("[RESPONSE_FORMAT_CONSTRAINT]") != 0:
                raise ValueError("strict output constraint was already present")
            if self.derive_rule_from_history and prompt.count("[HISTORY_RULE_DERIVATION_PROCEDURE]") != 0:
                raise ValueError("history rule derivation procedure was already present")
            suffix = []
            if self.derive_rule_from_history:
                suffix.append(HISTORY_RULE_DERIVATION)
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
        derive_rule_from_history: bool = False) -> None:
    if type(gpu_layers) is not int or not 1 <= gpu_layers <= 128:
        raise ValueError("transfer-ladder inference requires 1 through 128 GPU layers")
    if not preflight_only and expected_plan_sha256 is None:
        raise ValueError("inference requires the reviewed model-bound plan hash")
    if expected_plan_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_plan_sha256):
        raise ValueError("expected plan hash must be 64 lowercase hexadecimal characters")
    if derive_rule_from_history and not strict_json_output:
        raise ValueError("history rule derivation treatment requires the matched strict JSON constraint")
    if not (os.environ.get("SENTIENTOS_OLLAMA_MODELS") or os.environ.get("SENTIENTOS_OLLAMA_CPU_MODELS")):
        raise ValueError("GPU inference requires an explicitly isolated external Ollama server")
    manifest_digest = MODEL_MANIFESTS[MODEL]
    root.mkdir(parents=True, exist_ok=False)
    protocol = read(REPORT)
    if (protocol.get("schema") != "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v1"
            or protocol.get("inference_performed") is not False
            or protocol.get("model_bound_execution_plan_created") is not False
            or protocol.get("probe_inputs_disjoint_from_history_and_prior_probes") is not True
            or protocol.get("all_tier_prompts_match_outside_probe_values") is not True):
        raise ValueError("distance-ladder model-free preflight is not qualified")
    target_cycle = cycles / ("rootless-cognition-cycle-" + TARGET)
    historical_request = _read_receipt(target_cycle)[1]["request"]

    with model_server(install, models, root, MODEL, manifest_digest) as (manifest, version), \
            _rootless_governance_custody(root):
        options = {"api_base": BASE, "model": MODEL, "manifest_sha256": manifest_digest,
                   "num_gpu": gpu_layers, "num_thread": 2, "timeout_seconds": 120,
                   "seed": 42, "think": False, "keep_alive": "5m"}
        config = ModelConfig([ModelCandidate(manifest, "ollama", MODEL, options)],
            max_context_tokens=4096,
            generation=GenerationConfig(max_new_tokens=160, temperature=0.0, top_p=1.0))
        authority = build_local_model_authority_map(config, allowed_roots=[manifest.parent])
        model = LocalModel.load_candidate(0, config=config)
        identity = model.active_identity.to_dict()
        if not authority.record_for_active_identity(model.active_identity, "local_user_chat"):
            raise ValueError("ordinary-chat model identity is ineligible")
        inference = DistanceLadderChat(GovernedLocalModelInvoker(model=model, authority_map=authority,
            kernel=_resource_governed_kernel(root), runtime_root=root / "inference-custody"))
        inference.strict_json_output = strict_json_output
        inference.derive_rule_from_history = derive_rule_from_history

        parent_cycle = cycles / ("rootless-cognition-cycle-" + CYCLES["parent"])
        history_root = root / "history" / "resident-cognition"
        archive(parent_cycle, history_root)
        kinds = _source_kinds_from_history(history_root / "history")
        history_owner = _owner(history_root, kinds, history_root.parent, historical_request)
        exposure_report = read(ROOT / "artifacts/experiments/ordinary-chat-retention-20261125/later-session-novel-transfer-preflight-v3.json")
        if admitted_boundary(history_owner.writeback.inspect_completed_records()) != exposure_report[
                "arms"]["parent"]["admitted_boundary_digest"]:
            raise ValueError("parent history differs from the archived transfer source")
        empty_root = root / "empty" / "resident-cognition"
        empty_root.mkdir(parents=True)
        empty_owner = _owner(empty_root, kinds, target_cycle, historical_request)
        owners = {"history": history_owner, "empty": empty_owner}
        snapshots = {arm: owner.ordinary_chat_developmental_history_state_snapshot()
                     for arm, owner in owners.items()}

        questions, captures, base_by_condition, normalized_bases = {}, {}, {}, []
        for tier, tier_protocol in protocol["tiers"].items():
            questions[tier] = tier_protocol["question"]
            expected_evidence = tier_protocol["captures"]["history"]["prompt_score_evidence"]
            for arm in ("history", "empty"):
                key = tier + "_" + arm
                current_owner = owners[arm]
                base, captured = _service_request(current_owner, root / "preflight" / tier / arm,
                    identity, questions[tier], bind_invocation=True, capture_adapter=inference)
                base_by_condition[key] = base
                captures[key] = captured
                normalized_bases.append(base.replace(", ".join(map(str, tier_protocol["probe_inputs"])), "[PROBES]"))
                if arm == "history":
                    actual = captured["prompt_score_evidence"]
                    if _evidence_signature(actual) != _evidence_signature(expected_evidence):
                        raise ValueError(f"{tier} history prompt selected different scored evidence")
                elif captured["prompt_score_evidence"] or captured["history_block_digest"] is not None:
                    raise ValueError(f"{tier} empty control exposed developmental history")
            if base_by_condition[tier + "_history"] != base_by_condition[tier + "_empty"]:
                raise ValueError(f"{tier} prompts differ outside the history block")
        if len(set(normalized_bases)) != 1:
            raise ValueError("distance-tier prompt templates differ beyond probe values")

        plan = {
            "schema": "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v3"
                if derive_rule_from_history else (
                    "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v2"
                    if strict_json_output else "sentientos.ordinary_chat_transfer_distance_ladder_execution_plan:v1"),
            "source_report_sha256": sha(REPORT.read_bytes()),
            "model": MODEL, "model_manifest_sha256": manifest_digest,
            "model_identity": identity, "ollama_version": version,
            "options": options, "context_tokens": config.max_context_tokens,
            "generation": config.generation.as_kwargs(), "gpu_layers": gpu_layers,
            "format_treatment": "strict_json_post_retrieval:v1" if strict_json_output
                else "user_message_only:v1",
            "output_constraint": STRICT_JSON_OUTPUT if strict_json_output else None,
            "output_constraint_sha256": sha(STRICT_JSON_OUTPUT.encode()) if strict_json_output else None,
            "semantic_treatment": "derive_rule_from_available_history:v1" if derive_rule_from_history else None,
            "semantic_procedure": HISTORY_RULE_DERIVATION if derive_rule_from_history else None,
            "semantic_procedure_sha256": sha(HISTORY_RULE_DERIVATION.encode()) if derive_rule_from_history else None,
            "trial_order": [{"tier": tier, "arm": arm} for tier, arm in TRIAL_ORDER],
            "tiers": {tier: {"probe_inputs": entry["probe_inputs"],
                "answer_key_commitment": entry["answer_key_commitment"],
                "question": entry["question"]} for tier, entry in protocol["tiers"].items()},
            "prompt_bindings": captures,
            "matched_base_sha256": sha(normalized_bases[0].encode()),
            "source_code_sha256": {path: sha((ROOT / path).read_bytes()) for path in (
                "work/run_ordinary_chat_transfer_distance_ladder.py",
                "work/preflight_ordinary_chat_transfer_distance_ladder.py",
                "work/preflight_ordinary_chat_retention.py",
                "work/preflight_sibling_chat_histories.py",
                "work/run_sibling_chat_recall.py", "sentientos/chat_service.py",
                "sentientos/conversation_session.py", "sentientos/resident_developmental_cognition.py")},
            "primary_outcome": "Exact-answer count per tier and history condition; report history-minus-empty differences.",
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
        for index, (tier, arm) in enumerate(TRIAL_ORDER):
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
            try:
                delivered = service.chat(questions[tier], session_id=service.create_session(),
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
            trial = {"trial": index, "tier": tier, "arm": arm, "plan_sha256": plan_hash,
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
    args = parser.parse_args()
    run(args.cycles, args.ollama_install, args.models, args.new_run_directory,
        expected_plan_sha256=args.expected_plan_sha256,
        preflight_only=args.preflight_only, gpu_layers=args.gpu_layers,
        strict_json_output=args.strict_json_output,
        derive_rule_from_history=args.derive_rule_from_history)
