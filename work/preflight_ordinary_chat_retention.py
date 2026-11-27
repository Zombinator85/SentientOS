"""Replay a fresh ordinary-chat prompt against an archived resident and an empty store."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from scripts.preflight_resident_strategy_inclusion_pair import (
    _copy_without_symlinks, _LocalReceiptVerifier, _NoInferenceInvoker,
    _read_receipt, _source_kinds_from_history,
)
from sentientos.chat_service import (
    PersistentConversationService, _ordinary_epistemic_context_budget, _ordinary_epistemic_relevance_query,
)
from sentientos.canonical_memory import CanonicalMemoryStore
from sentientos.developmental_companion_bridge import ResidentDevelopmentalCompanionBridge
from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.conversation_session import (
    ConversationSessionStore, assemble_local_chat_context,
    ordinary_chat_developmental_history_prompt_block_digest,
    verify_ordinary_chat_history_projection_triplet,
)
from sentientos.governed_local_model_invocation import validate_receipt
from sentientos.local_model_authority import digest_payload
from sentientos.resident_developmental_cognition import (
    ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionOwner,
    _task_family_history_examples,
)
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.runtime_admission import (
    AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier,
)

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / ("artifacts/experiments/identity-neutral-journal-recovery-20261125-wide-power-v1/"
                "strategy_inclusion_cpu_preflight_v11.json")
PROBES = (367, 619, 883)
QUESTION = ("For the same number-prediction task we worked on before, what outputs would "
            "you predict for inputs " + ", ".join(map(str, PROBES)) +
            "? If you don't have enough information, say so.")
PARAPHRASE_PROBES = (101, 257, 811)
PARAPHRASE = ("We tried an arithmetic exercise earlier. Given inputs "
              + ", ".join(map(str, PARAPHRASE_PROBES)) +
              ", what outputs follow? Say when the evidence is insufficient.")
DISTRACTOR = "Can you predict the number of dropped frames in a game from its title alone?"
EMPTY_MEMORY = {"memories": [], "retrieval_posture": "complete",
                "selection_posture": "all_matching_records_selected", "omitted_memory_count": 0}


def _owner(root: Path, kinds: tuple[str, ...], cycle: Path,
           request: Mapping[str, Any]) -> ResidentDevelopmentalCognitionOwner:
    history, state = root / "history", root / "state"
    config = ResidentDevelopmentalCognitionConfig(history_root=history, state_root=state,
        allowed_source_kinds=kinds, max_selected_facts=32, max_retrieved_records=8)
    ledger = AdmissionLedger(state / "runtime_admissions.json")
    definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
    writeback = ResidentDevelopmentalWritebackController(history_root=history,
        admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger),
        current_sequence=ledger.current_sequence)
    return ResidentDevelopmentalCognitionOwner(config=config, writeback=writeback,
        admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
        current_sequence=ledger.current_sequence, invoker=_NoInferenceInvoker(request),
        invocation_receipt_verifier=_LocalReceiptVerifier(cycle))


def _render(owner: ResidentDevelopmentalCognitionOwner, sessions_dir: Path,
            identity: Mapping[str, Any]) -> dict[str, Any]:
    sessions = ConversationSessionStore(sessions_dir)
    session = sessions.create(model_identity=identity)
    history = sessions.reconstruct(session["session_id"], budget_chars=8000)
    args = dict(history=history, memory_snapshot=EMPTY_MEMORY, current_message=QUESTION)
    base = assemble_local_chat_context(**args)
    budget = _ordinary_epistemic_context_budget(base)
    if history.turns or budget is None:
        raise ValueError("fresh transcript or history budget unavailable")
    query = _ordinary_epistemic_relevance_query(QUESTION, history)
    before = owner.ordinary_chat_developmental_history_state_snapshot()
    context = owner.ordinary_chat_developmental_history_context_for_model(
        question=query, target_model_identity=identity, max_input_chars=budget)
    comparison = owner.compare_ordinary_chat_developmental_history_retrieval(
        question=query, target_model_identity=identity, max_input_chars=budget)
    owner.verify_ordinary_chat_developmental_history_retrieval_comparison(comparison)
    selection = next(arm for arm in comparison["conditions"] if arm["condition"] == "semantic")
    packets = context["developmental_history"] if context else []
    if (selection["selected_records"] != (context["selection"]["selected_records"] if context else [])
            or before != owner.ordinary_chat_developmental_history_state_snapshot()
            or comparison["history_state_digest"] != before["history_state_digest"]):
        raise ValueError("ordinary selection did not reproduce on the same resident inventory")
    try:
        prompt = assemble_local_chat_context(**args, developmental_history_context=context)
    except ValueError as error:
        raise ValueError("ordinary chat rejected the selected historical context") from error
    accepted = context is not None and len(prompt) <= 8000
    block = ordinary_chat_developmental_history_prompt_block_digest(prompt) if accepted else None
    delivered = prompt if accepted else base
    result = {
        "inventory_count": len(before["record_refs"]), "inventory_digest": before["history_state_digest"],
        "retrieval_policy_id": selection["retrieval_policy_id"],
        "retrieval_posture": selection["posture"], "history_budget_chars": budget,
        "ranked_record_ids": [r["record_id"] for r in selection["available_records"]],
        "binder_selected_record_ids": [p["record_id"] for p in packets],
        "prompt_record_ids": [p["record_id"] for p in packets] if accepted else [],
        "prompt_task_experience_count": sum(len(p.get("task_relevant_experience", []))
                                            for p in packets) if accepted else 0,
        "history_block_digest": block, "candidate_prompt_chars": len(prompt),
        "delivered_prompt_chars": len(delivered),
        "delivered_prompt_sha256": hashlib.sha256(delivered.encode()).hexdigest(),
    }
    if selection["available_records"] and not accepted:
        def get_context(limit: int) -> dict[str, Any] | None:
            return owner.ordinary_chat_developmental_history_context_for_model(
                question=query, target_model_identity=identity, max_input_chars=limit)

        # Measure the first ranked prefix that can leave the real binder. The
        # enlarged budget here is for diagnosis only and never feeds the trial.
        low, high = 128, 48000
        smallest = get_context(high)
        if smallest is None:
            result["budget_diagnostic"] = {"no_prefix_at_chars": high}
            return result
        while low < high:
            middle = (low + high) // 2
            context_at_limit = get_context(middle)
            if context_at_limit is None:
                low = middle + 1
            else:
                smallest = context_at_limit
                high = middle
        def chars(value: Any) -> int:
            return len(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")))

        try:
            diagnostic_prompt = assemble_local_chat_context(**args, developmental_history_context=smallest)
            assembly_error = None
        except ValueError as error:
            diagnostic_prompt = None
            assembly_error = str(error)
        result["budget_diagnostic"] = {
            "minimum_binder_budget_chars": high,
            "prefix_record_ids": [p["record_id"] for p in smallest["developmental_history"]],
            "instruction_chars": len(smallest["instruction"]),
            "selection_json_chars": chars(smallest["selection"]),
            "packet_array_json_chars": chars(smallest["developmental_history"]),
            "assembled_prompt_chars": len(diagnostic_prompt) if diagnostic_prompt is not None else None,
            "assembly_error": assembly_error,
        }
    return result


class _CapturedRequest(Exception):
    def __init__(self, prompt, linkage):
        super().__init__("stopped at chat inference boundary")
        self.prompt = prompt
        self.linkage = linkage


def _service_request(owner, root, identity, question=QUESTION, *, bind_invocation=False,
                     capture_adapter=None, capture_history_instruction=False):
    root.mkdir(parents=True, exist_ok=True)
    (root / "sessions").mkdir(exist_ok=True)
    (root / "memory").mkdir(exist_ok=True)
    if os.name == "posix":
        root.chmod(0o700)
        (root / "sessions").chmod(0o700)
        (root / "memory").chmod(0o700)

    class CaptureOnly:
        def current_conversation_model_identity(self):
            return identity

        def generate(self, *, prompt, caller_linkage, **kwargs):
            raise _CapturedRequest(prompt, caller_linkage)

    service = PersistentConversationService(inference=capture_adapter or CaptureOnly(),
        session_store=ConversationSessionStore(root / "sessions"),
        memory_store=CanonicalMemoryStore(root / "memory"),
        resident_cognition_bridge=ResidentDevelopmentalCompanionBridge(
            owner, cognition_available=lambda: False))
    try:
        service.chat(question, session_id=service.create_session(), request_id="fresh-retention-probe")
    except _CapturedRequest as captured:
        prompt, linkage = captured.prompt, captured.linkage
    else:
        raise ValueError("ordinary chat did not reach the capture boundary")
    start = prompt.find("[DEVELOPMENTAL_HISTORY_GUIDANCE]\n")
    matched_base, examples, example_renderings = prompt, [], []
    history_instruction = None
    candidate_hypotheses = []
    if start >= 0:
        end = prompt.index("\n[SESSION_HISTORY_DATA]", start)
        data = prompt.index("[DEVELOPMENTAL_HISTORY_DATA]\n", start) + len("[DEVELOPMENTAL_HISTORY_DATA]\n")
        context = json.loads(prompt[data:end])
        guidance_start = start + len("[DEVELOPMENTAL_HISTORY_GUIDANCE]\n")
        history_instruction = prompt[guidance_start:prompt.index(
            "\n[DEVELOPMENTAL_HISTORY_DATA]", guidance_start)]
        verify_ordinary_chat_history_projection_triplet(history_present=context, history_withheld=None,
            history_restored=context)
        if (ordinary_chat_developmental_history_prompt_block_digest(prompt)
                != linkage["ordinary_developmental_history_prompt_block_digest"]
                or context["selection_digest"] != linkage["ordinary_developmental_history_selection_digest"]
                or context["selection"]["history_state_digest"] != linkage["ordinary_developmental_history_state_digest"]):
            raise ValueError("service linkage does not match the rendered history")
        for packet in context["developmental_history"]:
            stored = owner.writeback.store.get(packet["record_id"])
            if stored.record_digest != packet["record_digest"]:
                raise ValueError("service history record differs from archive")
            for item in packet.get("task_relevant_experience", []):
                sources = _task_family_history_examples(stored.candidate, task_family_id=item["task_family_id"])
                if not any(item["source_score_digest"] == source["source_score_digest"]
                           and item["source_run_id"] == source["source_run_id"]
                           and item["source_fact_id"] == source["source_fact_id"]
                           and item["examples"] == source["examples"] for source in sources):
                    raise ValueError("service rows differ from the archived score")
                examples.append({"record_id": stored.record_id,
                    **{key: value for key, value in item.items()
                        if key not in {"human_readable_examples",
                            "derived_integer_affine_hypothesis"}}})
                hypothesis = item.get("derived_integer_affine_hypothesis")
                if isinstance(hypothesis, dict):
                    candidate_hypotheses.append({
                        "record_id": stored.record_id,
                        "task_family_id": item.get("task_family_id"),
                        "source_run_id": item.get("source_run_id"),
                        "source_score_digest": item.get("source_score_digest"),
                        "source_fact_id": item.get("source_fact_id"),
                        "hypothesis": hypothesis,
                    })
                rendering = item.get("human_readable_examples")
                if isinstance(rendering, str):
                    example_renderings.append({
                        "record_id": stored.record_id,
                        "task_family_id": item["task_family_id"],
                        "source_run_id": item["source_run_id"],
                        "source_score_digest": item["source_score_digest"],
                        "human_readable_examples": rendering,
                    })
        matched_base = prompt[:start] + prompt[end + 1:]
    return matched_base, {
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        **({"invocation_prompt_digest": digest_payload({"prompt": prompt})} if bind_invocation else {}),
        "prompt_chars": len(prompt),
        "history_block_digest": linkage.get("ordinary_developmental_history_prompt_block_digest"),
        "history_context_posture": linkage.get(
            "ordinary_developmental_history_context_posture"),
        "prompt_score_evidence": examples,
        "prompt_example_renderings": example_renderings,
        **({"derived_rule_hypotheses": candidate_hypotheses}
            if candidate_hypotheses else {}),
        **({"history_instruction": history_instruction} if capture_history_instruction else {}),
    }


def _matched_service_requests(owner, empty_owner, root, identity, question):
    present_base, present = _service_request(owner, root / "present", identity, question)
    empty_base, empty = _service_request(empty_owner, root / "empty", identity, question)
    if present_base != empty_base or empty["history_block_digest"] is not None:
        raise ValueError("service prompts differ outside the history exposure")
    return {"question": question, "archived": present, "empty": empty}


def build_report(cycle: Path) -> dict[str, Any]:
    pilot_bytes = PILOT.read_bytes()
    pilot = json.loads(pilot_bytes)
    arm = pilot["owner_arm_protocols"]["strategy_included"]
    descriptor = arm["objective_task_descriptor"]
    _, receipt = _read_receipt(cycle)
    valid, reasons = validate_receipt(receipt)
    identity = receipt["request"]["active_model_identity"]
    if not valid:
        raise ValueError(f"invalid archived receipt: {reasons}")
    if (receipt["receipt_digest"] != pilot["source_receipt_digest"]
            or cycle.name != pilot["cycle_root_id"] or identity != arm["active_model_identity"]):
        raise ValueError("archived receipt does not match the pilot")

    with tempfile.TemporaryDirectory(prefix="sentientos-chat-retention-") as tmp:
        root = Path(tmp)
        archived = root / "archived"
        _copy_without_symlinks(cycle / "resident-cognition", archived)
        kinds = _source_kinds_from_history(archived / "history")
        owner = _owner(archived, kinds, cycle, receipt["request"])
        historical_inputs = set()
        correct_inputs = set()
        source_records = {}
        adverse_control = None
        families = descriptor["history_task_family_ids"]
        for record, _ in owner.writeback.inspect_completed_records():
            for family in families:
                for experience in _task_family_history_examples(record.candidate, task_family_id=family):
                    if any(row.get("abstained") is True for row in experience["examples"]) and any(
                            row["evaluator_correct"] is False for row in experience["examples"]):
                        adverse_control = (record.record_id, record.record_digest, experience)
                    for example in experience["examples"]:
                        value = example["probe_input"]
                        if type(value) is not int:
                            raise ValueError("invalid historical probe input")
                        historical_inputs.add(value)
                        source_records[record.record_id] = record.record_digest
                        if example["evaluator_correct"] is True:
                            correct_inputs.add(value)
        required = pilot["strategy_pair_protocol"]
        for rid, digest in zip(required["history_record_ids"], required["history_record_digests"], strict=True):
            if source_records.get(rid) != digest:
                raise ValueError("pilot support record missing from reconciled task history")
        trial_inputs = set(PROBES) | set(PARAPHRASE_PROBES)
        overlap = sorted(trial_inputs & (historical_inputs | set(descriptor["probe_inputs"])))
        if overlap:
            raise ValueError(f"probe inputs already appear in historical rows or pilot: {overlap}")
        exposed = _render(owner, root / "archive-session", identity)
        empty_owner = _owner(root / "empty", kinds, cycle, receipt["request"])
        empty = _render(empty_owner, root / "empty-session", identity)
        if empty["inventory_count"] or empty["history_block_digest"] is not None:
            raise ValueError("empty control contains history")
        present_base, present_request = _service_request(owner, root / "present", identity)
        empty_base, empty_request = _service_request(empty_owner, root / "withheld", identity)
        reopened = _owner(archived, kinds, cycle, receipt["request"])
        restored_base, restored_request = _service_request(reopened, root / "restored", identity)
        if (present_base != empty_base or restored_base != empty_base or present_request != restored_request
                or empty_request["history_block_digest"] is not None):
            raise ValueError("independent service requests differ outside their history exposure")
        first_inputs = ", ".join(map(str, PROBES))
        second_inputs = ", ".join(map(str, PARAPHRASE_PROBES))
        crossed = {}
        for name, question in (
                ("reworded_new_inputs", PARAPHRASE),
                ("reworded_original_inputs", PARAPHRASE.replace(second_inputs, first_inputs)),
                ("original_wording_new_inputs", QUESTION.replace(first_inputs, second_inputs))):
            crossed[name] = _matched_service_requests(reopened, empty_owner, root / name, identity, question)
        _, distractor_request = _service_request(reopened, root / "distractor", identity, DISTRACTOR)
        if adverse_control is None:
            raise ValueError("archive has no run containing both errors and abstentions")
        adverse_id, adverse_digest, adverse_run = adverse_control
        diagnostic = reopened.ordinary_chat_developmental_history_context_for_model(
            question=QUESTION, target_model_identity=identity,
            record_allowlist=(adverse_id,), record_digest_allowlist={adverse_id: adverse_digest},
            max_input_chars=exposed["history_budget_chars"])
        if diagnostic is None:
            raise ValueError("pinned adverse control did not fit")
        adverse_packet, = diagnostic["developmental_history"]
        adverse = next(item for item in adverse_packet["task_relevant_experience"]
            if item["source_score_digest"] == adverse_run["source_score_digest"])
        if adverse["examples"] != adverse_run["examples"]:
            raise ValueError("adverse outcomes changed during projection")
    return {
        "schema_version": "sentientos.ordinary_chat_retention_preflight:v2",
        "chat_service_requests": {"archived": present_request, "empty": empty_request,
            "reopened": restored_request, "matched_non_history_prompt_sha256": hashlib.sha256(empty_base.encode()).hexdigest()},
        "second_probe_inputs": list(PARAPHRASE_PROBES), "crossed_queries": crossed,
        "numeric_distractor": {"question": DISTRACTOR, "archived": distractor_request},
        "exact_record_projection_control": {"record_id": adverse_id, "record_digest": adverse_digest,
            "source_score_digest": adverse["source_score_digest"], "examples": adverse["examples"]},
        "cycle_id": cycle.name, "source_receipt_digest": receipt["receipt_digest"],
        "pilot_file_sha256": hashlib.sha256(pilot_bytes).hexdigest(),
        "question": QUESTION, "probe_inputs": list(PROBES), "prior_pilot_inputs": descriptor["probe_inputs"],
        "audited_task_families": families, "archived_projected_inputs": sorted(historical_inputs),
        "archived_correct_inputs": sorted(correct_inputs), "source_records_with_projected_rows": source_records,
        "probe_input_overlap": overlap, "archived_store": exposed, "empty_store": empty,
        "identical_delivered_prompts": exposed["delivered_prompt_sha256"] == empty["delivered_prompt_sha256"],
        "model_invoked": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cycle_root", type=Path)
    options = parser.parse_args()
    print(json.dumps(build_report(options.cycle_root.resolve(strict=True)), indent=2, sort_keys=True))
