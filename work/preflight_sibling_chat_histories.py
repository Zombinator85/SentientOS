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
from sentientos.resident_developmental_cognition import _ordinary_chat_integer_experiences
from work.preflight_ordinary_chat_retention import (
    PARAPHRASE, QUESTION, _copy_without_symlinks, _owner, _read_receipt,
    _service_request, _source_kinds_from_history,
)
from work.rootless_history_boundary_campaign import (
    _admission_boundary_preserves, _cognition_recovery_state_boundary,
    _cognition_recovery_state_preserves, _history_boundary, _runtime_admission_boundary,
)


CYCLES = {"parent": "20261124000000000054", "left": "1a8cb8d5e3b704c159ef",
          "right": "20261124000000000057"}
TARGET = "20261124000000000009"
TARGET_RECEIPT = "d14f3d9870e9dbc64f5812f5d7c525cd0ecda9d340d41b4ff1920f244403140b"
QUESTIONS = {
    "latest_wide": ("On our most recent scored wide-range arithmetic exercise, what inputs did we try, "
                    "what did we answer for each, and which predictions were incorrect or abstentions? "
                    "If the record is unclear, say so."),
    "latest_low": ("On our most recent scored low-range arithmetic exercise, what inputs did we try, "
                   "what did we answer for each, and which predictions were incorrect or abstentions? "
                   "If the record is unclear, say so."),
    "prediction": QUESTION, "paraphrase": PARAPHRASE,
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
    if arms["left"]["addition"]["record_id"] == arms["right"]["addition"]["record_id"]:
        raise ValueError("sibling experiences must be distinct")
    return {"schema_version": "sentientos.ordinary_chat_sibling_history_exposure:v1",
            "evaluation_receipt_digest": TARGET_RECEIPT, "generative_model_invoked": False,
            "arms": arms, "questions": {name: {"text": question,
                "matched_base_sha256": hashlib.sha256(controls[name].encode()).hexdigest(),
                "captures": captures[name]} for name, question in QUESTIONS.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cycles_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = build_report(args.cycles_root)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
