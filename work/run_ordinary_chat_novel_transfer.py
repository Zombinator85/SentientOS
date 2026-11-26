"""Bind and run a held-out ordinary-chat transfer comparison on frozen histories."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

from sentientos.canonical_memory import CanonicalMemoryStore
from sentientos.chat_service import PersistentConversationService
from sentientos.conversation_session import ConversationSessionStore
from sentientos.developmental_companion_bridge import ResidentDevelopmentalCompanionBridge
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker, validate_receipt
from sentientos.local_model import LocalModel
from sentientos.local_model_authority import build_local_model_authority_map, digest_payload
from sentientos.rootless_experimental_local_model import _resource_governed_kernel, _rootless_governance_custody
from work.preflight_ordinary_chat_retention import _owner, _read_receipt, _service_request, _source_kinds_from_history
from work.preflight_sibling_chat_histories import (
    CYCLES, NOVEL_TRANSFER_PROBES, NOVEL_TRANSFER_QUESTION, ROOT, TARGET,
    admitted_boundary, archive, read,
)
from work.run_sibling_chat_recall import (
    BASE, MODEL_MANIFESTS, VerifiedChat, get_api, model_server, save, sha,
)

ARMS = ("parent", "left", "right", "empty")
MODEL = "sentientos-hermes4:14b-q4km"
ANSWER_KEY_COMMITMENT = "sha256:e606fd1931373bafc0fbe03282d7cec240bf4c90a23980963eca70f0db95d623"
NOVEL_REPORT = ROOT / "artifacts/experiments/ordinary-chat-retention-20261125/later-session-novel-transfer-preflight-v3.json"


def run(cycles: Path, install: Path, models: Path, root: Path, *,
        expected_plan_sha256: str | None = None, preflight_only: bool = False,
        model_name: str = MODEL, gpu_layers: int = 24) -> None:
    if model_name not in MODEL_MANIFESTS:
        raise ValueError("model is not in the pinned ordinary-chat recall registry")
    if type(gpu_layers) is not int or not 1 <= gpu_layers <= 128:
        raise ValueError("novel-transfer inference requires 1 through 128 GPU layers")
    if not preflight_only and expected_plan_sha256 is None:
        raise ValueError("inference requires the frozen model-bound plan hash")
    if expected_plan_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_plan_sha256):
        raise ValueError("expected plan hash must be 64 lowercase hexadecimal characters")
    if not (os.environ.get("SENTIENTOS_OLLAMA_MODELS") or os.environ.get("SENTIENTOS_OLLAMA_CPU_MODELS")):
        raise ValueError("GPU inference requires an explicitly isolated external Ollama server")
    manifest_digest = MODEL_MANIFESTS[model_name]
    root.mkdir(parents=True, exist_ok=False)
    baseline = read(NOVEL_REPORT)
    protocol = baseline["novel_transfer_protocol"]
    if (protocol.get("answer_key_commitment") != ANSWER_KEY_COMMITMENT
            or protocol.get("probe_inputs") != list(NOVEL_TRANSFER_PROBES)
            or protocol.get("inference_performed") is not False):
        raise ValueError("model-free novel-transfer protocol differs from the frozen protocol")
    target_cycle = cycles / ("rootless-cognition-cycle-" + TARGET)
    historical_request = _read_receipt(target_cycle)[1]["request"]

    with model_server(install, models, root, model_name, manifest_digest) as (manifest, version), \
            _rootless_governance_custody(root):
        options = {"api_base": BASE, "model": model_name, "manifest_sha256": manifest_digest,
                   "num_gpu": gpu_layers, "num_thread": 2, "timeout_seconds": 120, "seed": 42,
                   "think": False, "keep_alive": "5m"}
        from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
        config = ModelConfig([ModelCandidate(manifest, "ollama", model_name, options)], max_context_tokens=4096,
            generation=GenerationConfig(max_new_tokens=160, temperature=0.0, top_p=1.0))
        authority = build_local_model_authority_map(config, allowed_roots=[manifest.parent])
        model = LocalModel.load_candidate(0, config=config)
        identity = model.active_identity.to_dict()
        if not authority.record_for_active_identity(model.active_identity, "local_user_chat"):
            raise ValueError("ordinary-chat model identity is ineligible")
        inference = VerifiedChat(GovernedLocalModelInvoker(model=model, authority_map=authority,
            kernel=_resource_governed_kernel(root), runtime_root=root / "inference-custody"))
        owners, snapshots = {}, {}
        for arm in ("parent", "left", "right"):
            cycle = cycles / ("rootless-cognition-cycle-" + CYCLES[arm])
            resident = root / arm / "resident-cognition"
            archive(cycle, resident)
            kinds = _source_kinds_from_history(resident / "history")
            owner = _owner(resident, kinds, resident.parent, historical_request)
            if admitted_boundary(owner.writeback.inspect_completed_records()) != baseline["arms"][arm]["admitted_boundary_digest"]:
                raise ValueError("archived history differs from model-free exposure evidence")
            owners[arm] = owner
        empty_root = root / "empty" / "resident-cognition"
        empty_root.mkdir(parents=True)
        kinds = _source_kinds_from_history(root / "parent" / "resident-cognition" / "history")
        owners["empty"] = _owner(empty_root, kinds, target_cycle, historical_request)

        exposure, bases = {}, None
        for arm in ARMS:
            owner = owners[arm]
            snapshots[arm] = owner.ordinary_chat_developmental_history_state_snapshot()
            base, captured = _service_request(owner, root / "preflight" / arm, identity,
                NOVEL_TRANSFER_QUESTION, bind_invocation=True, capture_adapter=inference)
            if bases is None:
                bases = base
            elif bases != base:
                raise ValueError("novel-transfer prompts differ outside the developmental-history block")
            ref = protocol["prompt_bindings"][arm]
            if ([item["record_id"] for item in captured["prompt_score_evidence"]] != ref["history_record_ids"]
                    or sum(len(item.get("examples", ())) for item in captured["prompt_score_evidence"])
                    != ref["task_experience_count"]):
                raise ValueError("model-bound prompt selected different history evidence than the frozen protocol")
            exposure[arm] = captured

        plan = {
            "schema": "sentientos.ordinary_chat_novel_range_transfer_execution_plan:v1",
            "source_report_sha256": sha(NOVEL_REPORT.read_bytes()),
            "model": model_name, "model_manifest_sha256": manifest_digest,
            "model_identity": identity, "ollama_version": version,
            "options": options, "context_tokens": config.max_context_tokens,
            "generation": config.generation.as_kwargs(), "gpu_layers": gpu_layers,
            "arms": list(ARMS), "question": NOVEL_TRANSFER_QUESTION,
            "probe_inputs": list(NOVEL_TRANSFER_PROBES),
            "answer_key_commitment": ANSWER_KEY_COMMITMENT,
            "response_contract": protocol["response_contract"],
            "scoring": protocol["scoring"],
            "prompt_bindings": exposure,
            "matched_base_sha256": sha(bases.encode()),
            "source_code_sha256": {
                path: sha((ROOT / path).read_bytes()) for path in (
                    "work/run_ordinary_chat_novel_transfer.py",
                    "work/preflight_sibling_chat_histories.py",
                    "work/preflight_ordinary_chat_retention.py",
                    "work/run_sibling_chat_recall.py",
                    "sentientos/chat_service.py", "sentientos/conversation_session.py",
                    "sentientos/resident_developmental_cognition.py")},
            "criterion": "Score each delivered answer independently against the fixed held-out key; retain all four arm outputs.",
            "inference_performed": False, "learning_established": False,
        }
        save(root / "plan.json", plan)
        plan_hash = sha((root / "plan.json").read_bytes())
        if expected_plan_sha256 is not None and plan_hash != expected_plan_sha256:
            save(root / "preflight_rejection.json", {"expected_plan_sha256": expected_plan_sha256,
                "observed_plan_sha256": plan_hash, "model_invoked": False, "inference_performed": False})
            raise ValueError("fresh run differs from frozen model-bound plan; inference was not started")
        if expected_plan_sha256 is not None and not preflight_only:
            save(root / "preflight_binding.json", {
                "schema": "sentientos.ordinary_chat_novel_range_transfer_preflight_binding:v1",
                "preflight_plan_sha256": expected_plan_sha256,
                "full_run_plan_sha256": plan_hash,
                "matched": True,
            })
        if preflight_only:
            if get_api("ps")["models"]:
                raise ValueError("preflight-only mode found a resident server model")
            save(root / "preflight.json", {"schema": "sentientos.ordinary_chat_novel_range_transfer_preflight:v1",
                "plan_sha256": plan_hash, "model_invoked": False, "inference_performed": False,
                "learning_established": False, "resident_vram_bytes": 0})
            print("preflight_saved", plan_hash, flush=True)
            return

        trials = []
        inference.capture_only = False
        for index, arm in enumerate(ARMS):
            inference.frozen_hash = exposure[arm]["prompt_sha256"]
            inference.receipt = None
            trial_root = root / "trials" / str(index)
            service = PersistentConversationService(inference=inference,
                inference_timeout_seconds=options["timeout_seconds"],
                session_store=ConversationSessionStore(trial_root / "sessions"),
                memory_store=CanonicalMemoryStore(trial_root / "memory"),
                resident_cognition_bridge=ResidentDevelopmentalCompanionBridge(
                    owners[arm], cognition_available=lambda: False))
            delivered = service.chat(NOVEL_TRANSFER_QUESTION,
                session_id=service.create_session(), request_id="novel-range-transfer").response
            receipt = inference.receipt
            disk = read(root / "inference-custody" / "receipts" / (receipt.receipt_id + ".json"))
            if (not validate_receipt(disk)[0] or disk["receipt_digest"] != receipt.receipt_digest
                    or disk["request"]["active_model_identity"] != identity
                    or disk["request"]["prompt_digest"] != exposure[arm]["invocation_prompt_digest"]
                    or disk["output_digest"] != digest_payload({"output": receipt.output_text})
                    or disk["status"] != "admitted_completed" or receipt.fallback_occurred
                    or receipt.output_text is None):
                raise ValueError("governed inference did not yield the frozen model response")
            placement, = get_api("ps")["models"]
            if placement["digest"] != manifest_digest or placement["size_vram"] <= 0:
                raise ValueError("model was not resident on the requested GPU artifact")
            result = {"trial": index, "arm": arm, "plan_sha256": plan_hash,
                "prompt_sha256": exposure[arm]["prompt_sha256"], "receipt": disk,
                "model_output": receipt.output_text, "delivered": delivered,
                "resident_vram_bytes": placement["size_vram"], "independent_scoring": "pending"}
            save(trial_root / "result.json", result)
            trials.append(result)
            print(index, arm, "inference_complete", flush=True)
        if any(owner.ordinary_chat_developmental_history_state_snapshot() != snapshots[arm]
                for arm, owner in owners.items()):
            raise ValueError("read-only comparison changed resident developmental history")
        save(root / "result.json", {"plan_sha256": plan_hash, "trials": trials,
            "learning_established": False, "independent_scoring": "pending"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("cycles", "ollama_install", "models", "new_run_directory"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("--model", choices=tuple(MODEL_MANIFESTS), default=MODEL)
    parser.add_argument("--gpu-layers", type=int, default=24)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--expected-plan-sha256")
    args = parser.parse_args()
    run(args.cycles, args.ollama_install, args.models, args.new_run_directory,
        expected_plan_sha256=args.expected_plan_sha256, preflight_only=args.preflight_only,
        model_name=args.model, gpu_layers=args.gpu_layers)
