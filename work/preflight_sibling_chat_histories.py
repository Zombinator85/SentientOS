"""Compare ordinary-chat evidence from two archived residents with a verified common parent."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from sentientos.governed_local_model_invocation import validate_receipt
from sentientos.local_model_authority import digest_payload
from sentientos.local_runtime_provisioning import semantic_digest
from sentientos.developmental_model_replacement_experiment import (
    FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS,
    FIXED_OBJECTIVE_TASK_FAMILY_PROBE_RANGES,
    ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
    ROOTLESS_INTEGER_AFFINE_TRANSFER_TASK_FAMILY,
    ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
)
from sentientos.resident_developmental_cognition import _ordinary_chat_integer_experiences
from work.preflight_ordinary_chat_retention import (
    PARAPHRASE, PARAPHRASE_PROBES, PILOT, PROBES, QUESTION,
    _copy_without_symlinks, _owner, _read_receipt, _service_request,
    _source_kinds_from_history,
)
from work.rootless_history_boundary_campaign import (
    _admission_boundary_preserves, _cognition_recovery_state_boundary,
    _cognition_recovery_state_preserves, _history_boundary, _runtime_admission_boundary,
)


CYCLES = {"parent": "20261124000000000054", "left": "1a8cb8d5e3b704c159ef",
          "right": "20261124000000000057"}
TARGET = "20261124000000000009"
TARGET_RECEIPT = "d14f3d9870e9dbc64f5812f5d7c525cd0ecda9d340d41b4ff1920f244403140b"
ROOT = Path(__file__).resolve().parents[1]
NOVEL_TRANSFER_PROBES = (1009, 8009, 50021)
NOVEL_TRANSFER_QUESTION = (
    "Earlier we practiced a number prediction exercise. What outputs should go "
    "with these inputs: " + ", ".join(map(str, NOVEL_TRANSFER_PROBES)) +
    "? If the history does not support a prediction, use null for that answer. "
    "Reply only as one JSON object with an answers array, one integer or null "
    "for each input in order.")
QUESTIONS = {
    "latest_wide": ("On our most recent scored wide-range arithmetic exercise, what inputs did we try, "
                    "what did we answer for each, and which predictions were incorrect or abstentions? "
                    "If the record is unclear, say so."),
    "latest_low": ("On our most recent scored low-range arithmetic exercise, what inputs did we try, "
                   "what did we answer for each, and which predictions were incorrect or abstentions? "
                   "If the record is unclear, say so."),
    "prediction": QUESTION, "paraphrase": PARAPHRASE,
    "novel_range_transfer": NOVEL_TRANSFER_QUESTION,
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def archive(cycle, root):
    _copy_without_symlinks(cycle / "resident-cognition", root)
    _copy_without_symlinks(cycle / "inference-custody" / "receipts",
                           root.parent / "inference-custody" / "receipts")
    history = _history_boundary(root / "history")
    ledger = _runtime_admission_boundary(root / "history", history)
    recovery = _cognition_recovery_state_boundary(root / "state")
    terminal_path, = [path for path in (cycle / "cycle-result.json", cycle / "cycle-failure.json")
                      if path.is_file()]
    terminal = read(terminal_path)
    reg = read(cycle / "preregistration.json")
    if (reg["run_id"] != cycle.name or terminal["run_id"] != cycle.name
            or semantic_digest({k: v for k, v in reg.items() if k != "preregistration_digest"})
                != reg["preregistration_digest"]
            or reg["preregistration_digest"] != terminal["run_preregistration_digest"]
            or reg["external_protocol_digest"] != terminal["external_preregistration_digest"]
            or reg["model_manifest_digest"] != terminal["model_manifest_digest"]
            or reg["prior_developmental_history_seed"] != terminal["prior_developmental_history_seed"]
            or ledger != terminal["runtime_admission_ledger"]
            or recovery != terminal["cognition_recovery_state_boundary"]):
        raise ValueError(f"archive does not match its recorded boundaries: {cycle.name}")
    files = {row["path"]: row for row in history["files"]}
    return reg, terminal, ledger, recovery, files


def admitted_boundary(pairs):
    records = [{"record_id": r.record_id, "record_digest": r.record_digest} for r, _ in pairs]
    receipts = [{"receipt_id": w.receipt_id, "receipt_digest": w.receipt_digest,
                 "record_id": w.record_id, "record_digest": w.record_digest} for _, w in pairs]
    return digest_payload({"records": sorted(records, key=lambda r: r["record_id"]),
                           "receipts": sorted(receipts, key=lambda r: r["receipt_id"])})


def added_experience(owner, record, receipt, reg):
    if record.correlation_id != reg["run_id"] + ":objective-family-acquisition-writeback:resident-developmental-writeback":
        raise ValueError("added record does not belong to the cycle's acquisition")
    experience, = _ordinary_chat_integer_experiences(record.candidate)
    run = owner.experiments.load_run(experience["source_run_id"])
    scored, = [s for s in run["objective_scores"] if s["condition_id"] == "history_present"]
    score = scored["score"]
    rows = [{"probe_input": e["probe_input"], "observed_answer": e["observed_answer"],
             "evaluator_correct": e["correct"], "abstained": e.get("abstained", False)}
            for e in score["probe_results"]]
    if (run["run_digest"] != experience["source_run_digest"]
            or score["score_digest"] != experience["source_score_digest"]
            or rows != experience["examples"]
            or experience["source_active_model_identity"] != reg["model_identity"]):
        raise ValueError("scored rows do not match the acquisition run")
    return {"record_id": record.record_id, "record_digest": record.record_digest,
            "receipt_digest": receipt.receipt_digest, "source_run_digest": run["run_digest"],
            **{k: experience[k] for k in ("source_run_id", "source_score_digest",
                                          "task_family_id", "examples")}}


def build_report(cycles_root):
    def cycle(suffix):
        return cycles_root / ("rootless-cognition-cycle-" + suffix)

    receipt = _read_receipt(cycle(TARGET))[1]
    if receipt["receipt_digest"] != TARGET_RECEIPT or not validate_receipt(receipt)[0]:
        raise ValueError("invalid evaluation identity receipt")
    request = receipt["request"]
    arms, controls, captures = {}, {}, {name: {} for name in QUESTIONS}
    historical_inputs_by_arm = {}
    with tempfile.TemporaryDirectory(prefix="sentientos-sibling-chat-") as tmp:
        for arm, suffix in CYCLES.items():
            source, root = cycle(suffix), Path(tmp) / arm / "resident-cognition"
            reg, terminal, ledger, recovery, files = archive(source, root)
            kinds = _source_kinds_from_history(root / "history")
            owner = _owner(root, kinds, root.parent, request)
            pairs = owner.writeback.inspect_completed_records()
            refs = owner._verified_history_record_refs(owner._state())
            if (len(pairs) != len(refs) or len(files) != 2 * len(pairs)
                    or {r.record_id: r.record_digest for r, _ in pairs}
                        != {r["record_id"]: r["record_digest"] for r in refs}):
                raise ValueError("checkpoint differs from admitted inventory")
            observed_inputs = set()
            for record, _ in pairs:
                for experience in _ordinary_chat_integer_experiences(record.candidate):
                    for example in experience["examples"]:
                        probe_input = example.get("probe_input")
                        if type(probe_input) is not int:
                            raise ValueError("historical integer prediction input is invalid")
                        observed_inputs.add(probe_input)
            historical_inputs_by_arm[arm] = observed_inputs
            arms[arm] = {"cycle": source.name, "terminal_status": terminal["status"],
                         "stopped_at": terminal.get("stage"), "failure_code": terminal.get("failure_code"),
                         "preregistration_digest": reg["preregistration_digest"],
                         "acquisition_seed": reg["experiment_seed"],
                         "source_configuration_digest": reg["model_identity"]["configuration_digest"],
                         "source_model_manifest_digest": reg["model_manifest_digest"],
                         "record_count": len(refs), "admitted_boundary_digest": admitted_boundary(pairs),
                         "admission_ledger_digest": ledger["sha256"],
                         "recovery_boundary_digest": recovery["boundary_digest"]}
            if arm == "parent":
                parent_files, parent_refs, parent_ledger, parent_recovery = files, refs, ledger, recovery
                parent_kinds = kinds
            else:
                seed = reg["prior_developmental_history_seed"]
                if (seed["source_boundary_digest"] != arms["parent"]["admitted_boundary_digest"]
                        or seed["source_runtime_admission_ledger"] != parent_ledger
                        or seed["source_cognition_recovery_state"] != parent_recovery
                        or seed["record_count"] != len(parent_refs) or seed["receipt_count"] != len(parent_refs)
                        or any(files.get(k) != v for k, v in parent_files.items())
                        or not _admission_boundary_preserves(parent_ledger, ledger)
                        or not _cognition_recovery_state_preserves(parent_recovery, recovery)
                        or parent_kinds != kinds or refs[:-1] != parent_refs):
                    raise ValueError("archives do not share the declared starting state")
                record, written = next((r, w) for r, w in pairs if r.record_id == refs[-1]["record_id"])
                if files.keys() - parent_files.keys() != {
                        f"records/{record.record_id}.json", f"receipts/{written.receipt_id}.json"}:
                    raise ValueError("unexpected changes to branch files")
                arms[arm]["addition"] = added_experience(owner, record, written, reg)
            for name, question in QUESTIONS.items():
                base, evidence = _service_request(owner, root / "chats" / name,
                                                  request["active_model_identity"], question)
                if controls.setdefault(name, base) != base:
                    raise ValueError("chat prompts differ outside the history block")
                captures[name][arm] = evidence
        empty_root = Path(tmp) / "empty" / "resident-cognition"
        empty_root.mkdir(parents=True)
        empty_owner = _owner(empty_root, (), cycle(TARGET), request)
        empty_base, empty_evidence = _service_request(empty_owner,
            Path(tmp) / "empty" / "chats" / "novel_range_transfer",
            request["active_model_identity"], NOVEL_TRANSFER_QUESTION)
        if controls.get("novel_range_transfer") != empty_base:
            raise ValueError("empty-history transfer prompt differs outside history")
        captures["novel_range_transfer"]["empty"] = empty_evidence
    if arms["left"]["addition"]["record_id"] == arms["right"]["addition"]["record_id"]:
        raise ValueError("sibling experiences must be distinct")
    mapping = FIXED_OBJECTIVE_TASK_FAMILY_MAPPINGS[
        ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY]
    ranges = FIXED_OBJECTIVE_TASK_FAMILY_PROBE_RANGES[
        ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY]
    if (len(mapping) != 2 or any(type(value) is not int for value in mapping)
            or any(not any(lower <= probe <= upper for lower, upper in ranges)
                for probe in NOVEL_TRANSFER_PROBES)):
        raise ValueError("novel transfer probes do not match the frozen task family")
    pilot = read(PILOT)
    pilot_inputs = set(pilot["owner_arm_protocols"]["strategy_included"]
        ["objective_task_descriptor"]["probe_inputs"])
    reference_inputs = pilot_inputs | set(PROBES) | set(PARAPHRASE_PROBES)
    prior_overlap = sorted(reference_inputs.intersection(NOVEL_TRANSFER_PROBES))
    historical_overlap_by_arm = {
        arm: sorted(values.intersection(NOVEL_TRANSFER_PROBES))
        for arm, values in historical_inputs_by_arm.items()}
    if prior_overlap or any(historical_overlap_by_arm.values()):
        raise ValueError("novel transfer probes overlap prior or historical inputs")
    expected_outputs = [mapping[0] * probe + mapping[1]
        for probe in NOVEL_TRANSFER_PROBES]
    answer_key_commitment = "sha256:" + digest_payload({
        "task_family_id": ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
        "probe_inputs": list(NOVEL_TRANSFER_PROBES),
        "expected_outputs": expected_outputs,
    })
    novel_transfer = {
        "schema_version": "sentientos.ordinary_chat_novel_range_transfer_preflight:v1",
        "task_family_id": ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
        "source_task_family_ids": [ROOTLESS_INTEGER_AFFINE_TRANSFER_TASK_FAMILY,
            ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY],
        "probe_ranges": [list(bounds) for bounds in ranges],
        "probe_inputs": list(NOVEL_TRANSFER_PROBES),
        "reference_test_inputs": {
            "strategy_inclusion_pilot": sorted(pilot_inputs),
            "ordinary_chat_retention_probes": sorted(
                set(PROBES) | set(PARAPHRASE_PROBES)),
        },
        "probe_input_overlap_with_reference_tests": prior_overlap,
        "historical_probe_overlap_by_arm": historical_overlap_by_arm,
        "probe_sets_disjoint_from_reference_tests_and_history": True,
        "answer_key_commitment": answer_key_commitment,
        "answer_values_withheld": True,
        "response_contract": (
            "one JSON object with an answers array containing one integer or null "
            "per probe in order; no prose"),
        "scoring": (
            "exact integer equality per probe; null, missing, malformed, or "
            "extra answers count as not correct in the fixed three-probe denominator"),
        "prompt_bindings": {
            arm: {
                "prompt_sha256": captures["novel_range_transfer"][arm].get(
                    "prompt_sha256"),
                "history_block_digest": captures[
                    "novel_range_transfer"][arm].get("history_block_digest"),
                "history_record_ids": [item["record_id"] for item in
                    captures["novel_range_transfer"][arm].get(
                        "prompt_score_evidence", ())],
                "task_experience_count": sum(len(item.get("examples", ()))
                    for item in captures["novel_range_transfer"][arm].get(
                        "prompt_score_evidence", ())),
            }
            for arm in ("parent", "left", "right", "empty")},
        "inference_performed": False,
        "model_bound_execution_plan_created": False,
        "learning_established": False,
        "authority": False,
    }
    implementation_paths = (
        "work/preflight_sibling_chat_histories.py",
        "work/preflight_ordinary_chat_retention.py",
        "sentientos/resident_developmental_cognition.py",
        "sentientos/developmental_model_replacement_experiment.py",
        "sentientos/chat_service.py",
        "sentientos/conversation_session.py",
    )
    return {"schema_version": "sentientos.ordinary_chat_sibling_history_exposure:v1",
            "evaluation_receipt_digest": TARGET_RECEIPT, "generative_model_invoked": False,
            "implementation_sha256": {name: hashlib.sha256(
                (ROOT / name).read_bytes()).hexdigest()
                for name in implementation_paths},
            "arms": arms, "novel_transfer_protocol": novel_transfer,
            "questions": {name: {"text": question,
                "matched_base_sha256": hashlib.sha256(controls[name].encode()).hexdigest(),
                "captures": captures[name]} for name, question in QUESTIONS.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cycles_root", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--verify-report", type=Path,
        help="reconstruct and compare a saved model-free exposure report")
    args = parser.parse_args()
    report = build_report(args.cycles_root)
    encoded = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.verify_report is not None:
        saved = read(args.verify_report)
        if saved != report:
            raise ValueError("saved sibling history exposure differs from reconstruction")
        print("sibling_history_exposure_reconstructed",
            hashlib.sha256(args.verify_report.read_bytes()).hexdigest())
    elif args.output is not None:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        parser.error("provide output or --verify-report")
