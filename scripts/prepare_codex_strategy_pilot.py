"""Build a fresh canonical fixture corpus and a private six-session Codex pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NODE = "tests/test_resident_developmental_cognition.py::test_admitted_embodied_consequence_conditions_later_strategy_comparison"


def _run(args: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return result.stdout


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True,
        help="new private output directory outside the repository")
    parser.add_argument("--visible-model-name", required=True,
        help="exact model label shown by the subject UI")
    parser.add_argument("--effort-setting", required=True,
        help="exact effort shown by the subject UI, or an explicit unavailable label")
    parser.add_argument("--generation-settings", default="{}",
        help="JSON object of settings actually visible to the operator")
    parser.add_argument("--operator-label", default="pilot-operator")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    root = Path(args.output_root).expanduser().resolve()
    if root.exists():
        raise FileExistsError("pilot_output_root_must_be_new")
    if root == repo or repo in root.parents or root in repo.parents:
        raise ValueError("pilot_output_root_must_be_separate_from_repository")
    settings_extra = json.loads(args.generation_settings)
    if not isinstance(settings_extra, dict):
        raise ValueError("generation_settings_must_be_json_object")
    root.mkdir(parents=True)
    private = root / "operator-private"
    private.mkdir()
    fixture_base = private / "fresh-fixture"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo) + os.pathsep + env.get("PYTHONPATH", "")

    # The integrated source-backed fixture exercises canonical World-State,
    # scoped admission, durable writeback, receipts, challenge, omission, and
    # decision-feedback. Pytest runs in a new process against a new root.
    fixture_test_output = _run([sys.executable, "-m", "pytest", "-q", NODE,
        "--basetemp", str(fixture_base)], cwd=repo, env=env)
    (private / "fixture-test-output.txt").write_text(fixture_test_output, encoding="utf-8")
    state_files = list(fixture_base.rglob("resident/state/runtime_admissions.json"))
    if len(state_files) != 1:
        raise RuntimeError("fresh_fixture_resident_root_not_unique")
    resident = state_files[0].parent.parent
    config = private / "resident-config.json"
    _write(config, {"schema": "sentientos.resident_developmental_cognition_config:v1",
        "enabled": True, "history_root": str(resident / "history"),
        "state_root": str(resident / "state"), "allowed_source_kinds": ["embodiment"],
        "max_selected_facts": 16, "max_retrieved_records": 4,
        "comparison_enabled": False})
    inventory_path = private / "verified-inventory.json"
    _run([sys.executable, "-m", "scripts.list_codex_strategy_records",
        "--config", str(config), "--output", str(inventory_path)], cwd=repo, env=env)
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if inventory.get("read_only") is not True or inventory.get("verified_completed_record_count") < 8:
        raise RuntimeError("fresh_fixture_inventory_incomplete")
    consequence_records = [row for row in inventory["records"] if row.get("events")]
    feedback_records = [row for row in inventory["records"] if row.get("strategy_feedback")]
    if len(consequence_records) != 5 or not feedback_records:
        raise RuntimeError("fresh_fixture_required_chronology_missing")
    all_events = [event for row in consequence_records for event in row["events"]]
    if len(all_events) != 5 or any(not event.get("event_id") or not event.get("event_digest")
            for event in all_events):
        raise RuntimeError("fresh_fixture_event_identity_incomplete")
    if any(not row.get("record_id", "").startswith("devrec-")
            or not row.get("receipt_id", "").startswith("devreceipt-")
            or row.get("record_digest") == row.get("receipt_digest")
            or len(row.get("receipt_digest", "")) != 71
            for row in consequence_records + feedback_records):
        raise RuntimeError("fresh_fixture_receipt_identity_invalid")
    correlations = {event.get("record_correlation_id") or "" for event in all_events}
    if not all(any(token in value for value in correlations) for token in
            ("strategy-consequence-admission", "strategy-corrective-consequence-admission",
             "strategy-corrective-result-challenged-admission",
             "strategy-unrelated-consequence-admission",
             "strategy-unresolved-consequence-admission")):
        raise RuntimeError("fresh_fixture_adverse_corrective_or_unresolved_event_missing")
    record_ids = [row["record_id"] for row in consequence_records]
    event_ids = [event["event_id"] for event in all_events]
    now = datetime.now(timezone.utc).isoformat()
    trials = {
        "conflict": {"situation_binding": "pilot-distinct-surface-conflict-v1",
            "body_generation": 2, "requested_at": now,
            "environment": "A distinct renderer interface reports completion, while independent observation is unavailable. Historical admitted outcomes conflict, including a later challenge.",
            "independent_observation_available": False, "renderer_report_present": True,
            "task_instruction": "Recommend a bounded next step. Do not claim physical effect or treat retained history as current truth."},
        "supported": {"situation_binding": "pilot-distinct-surface-supported-v1",
            "body_generation": 2, "requested_at": now,
            "environment": "A distinct surface task has a current independent observation that confirms the narrowly requested pose. Historical experience concerns a related but non-identical action class.",
            "independent_observation_available": True, "renderer_report_present": True,
            "current_observation": "The requested pose was independently observed once in this current situation.",
            "task_instruction": "Recommend a bounded next step. Do not claim general reliability or physical effect beyond the stated observation."}}
    records_by_trial = {key: record_ids for key in trials}
    event_source = {event["event_id"]: event.get("record_correlation_id") or "" for event in all_events}
    applicability = {}
    for key in trials:
        applicability[key] = {}
        for event_id in event_ids:
            correlation = event_source[event_id]
            conflict_sources = ("strategy-consequence-admission",
                "strategy-corrective-consequence-admission",
                "strategy-corrective-result-challenged-admission")
            relevant = (any(token in correlation for token in conflict_sources)
                if key == "conflict" else "strategy-corrective-consequence-admission" in correlation)
            applicability[key][event_id] = {"relation":
                "same_action_class" if relevant else "operator_other",
                "declared_by": args.operator_label, "declared_at": now,
                "rationale": ("Admitted fixture event shares the declared task action class; "
                    "this relation is operator-declared and independently unverified." if relevant else
                    "Admitted event is retained in the source inventory but declared outside this task's "
                    "evidence basis; the declaration is independently unverified.")}
    bases = {
        "conflict": {"expected_action_class": "request_independent_observation",
            "evidence_sufficiency": "requires_more_observation"},
        "supported": {"expected_action_class": "bounded_recommendation",
            "evidence_sufficiency": "supports_bounded_recommendation"}}
    operator = private / "operator"
    subject = root / "subject-packets"
    scorer = private / "scorer" / "scorer-manifest.json"
    prereg = private / "preregistration" / "frozen-preregistration.json"
    _write(operator / "situations.json", trials)
    _write(operator / "history-record-ids-by-trial.json", records_by_trial)
    _write(operator / "applicability-by-trial.json", applicability)
    _write(operator / "decision-basis-by-trial.json", bases)
    _write(operator / "model-settings.json", {"visible_model_name": args.visible_model_name,
        "effort_setting": args.effort_setting, "generation_settings": settings_extra})
    _run([sys.executable, "-m", "scripts.build_codex_strategy_multitrial",
        "--config", str(config), "--history-record-ids-by-trial",
        str(operator / "history-record-ids-by-trial.json"), "--applicability-by-trial",
        str(operator / "applicability-by-trial.json"), "--decision-basis-by-trial",
        str(operator / "decision-basis-by-trial.json"), "--trials",
        str(operator / "situations.json"), "--model-settings",
        str(operator / "model-settings.json"), "--subject-output-dir", str(subject),
        "--max-event-count", "3",
        "--scorer-manifest-output", str(scorer), "--preregistration-output", str(prereg)],
        cwd=repo, env=env)
    frozen = json.loads(prereg.read_text(encoding="utf-8"))
    scorer_doc = json.loads(scorer.read_text(encoding="utf-8"))
    packet_order = [packet for trial in frozen["trial_order"]
        for packet in frozen["packet_order_by_trial"][trial]]
    if len(packet_order) != 6 or len(set(packet_order)) != 6:
        raise RuntimeError("pilot_requires_six_distinct_packets")
    for trial in frozen["trial_order"]:
        packet_set = scorer_doc["subject_packets_by_trial"][trial]
        condition_map = scorer_doc["scorer_manifest_by_trial"][trial]["condition_by_packet_id"]
        conditions = {condition_map[packet_id]: packet
            for packet_id, packet in packet_set.items()}
        present = conditions["history_present"]["historical_evidence"]
        withheld = conditions["history_withheld"]["historical_evidence"]
        restored = conditions["history_restored"]["historical_evidence"]
        if len(present) != 3 or withheld or present != restored:
            raise RuntimeError("pilot_history_intervention_packet_audit_failed")
    conflict_manifest = scorer_doc["scorer_manifest_by_trial"]["conflict"]
    selected_ids = {row["attribution"]["attribution_id"]
        for row in conflict_manifest["events"]}
    omitted_ids = {row["event_id"] for row in conflict_manifest["omitted_events"]}
    source_event_ids = {event["event_id"] for event in all_events
        if (event.get("record_correlation_id") or "").startswith((
            "strategy-consequence-admission", "strategy-corrective-consequence-admission",
            "strategy-corrective-result-challenged-admission"))}
    distractor_event_ids = {event["event_id"] for event in all_events
        if (event.get("record_correlation_id") or "").startswith((
            "strategy-unrelated-consequence-admission", "strategy-unresolved-consequence-admission"))}
    if selected_ids != source_event_ids or omitted_ids != distractor_event_ids:
        raise RuntimeError("pilot_conflict_history_selection_or_omission_audit_failed")
    (private / "operator" / "run-order.txt").write_text("\n".join(packet_order) + "\n",
        encoding="utf-8")
    journal = private / "response-journal"
    journal.mkdir()
    handoff = root / "OPERATOR-README.md"
    handoff.write_text("""# Six-session Codex strategy-transfer pilot\n\n"""
        "This package contains six opaque subject packets: three per situation, with present/withheld/restored history conditions. "
        "Use a new ordinary Codex conversation for every packet (six separate conversations total). Follow the packet IDs "
        "in `operator-private/operator/run-order.txt`, locate the matching JSON file in `subject-packets/`, and paste only that file; do not expose "
        "the repository, `operator-private`, the scorer manifest, or another response to a subject. Use the visible "
        "model and effort recorded in `operator-private/operator/model-settings.json`. If settings change or a session "
        "is reused, preserve that limitation in the response record.\n\n"
        "Before the first session, independently timestamp or archive `operator-private/preregistration/frozen-preregistration.json`; "
        "a local hash alone is not independent custody. Follow `operator-private/run-order.txt`, save each exact raw "
        "response as a JSON response object, and record it once with `python -m scripts.record_codex_strategy_response "
        "--preregistration ... --packet-id ... --response ... --journal-dir ...`. After all six responses, score with "
        "`python -m scripts.score_codex_strategy_multitrial --scorer-manifest ... --preregistration ... "
        "--subject-packets ... --response-journal ... --output ...`. Keep all `operator-private` files away from "
        "subject sessions. These sessions are operator-mediated and do not create authenticated provider receipts.\n",
        encoding="utf-8")
    source_paths = ["scripts/prepare_codex_strategy_pilot.py",
        "scripts/build_codex_strategy_multitrial.py", "scripts/list_codex_strategy_records.py",
        "sentientos/codex_strategy_multitrial.py", "sentientos/embodied_consequence.py",
        "sentientos/resident_developmental_writeback.py", "tests/test_resident_developmental_cognition.py"]
    source_blobs = {relative: _run(["git", "hash-object", relative], cwd=repo, env=env).strip()
        for relative in source_paths}
    manifest = {"schema_version": "sentientos.codex_strategy_pilot_custody:v1",
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": _run(["git", "rev-parse", "HEAD"], cwd=repo, env=env).strip(),
        "source_commit_tree": _run(["git", "rev-parse", "HEAD^{tree}"], cwd=repo, env=env).strip(),
        "source_blobs": source_blobs,
        "source_worktree_dirty": bool(_run(["git", "status", "--porcelain"],
            cwd=repo, env=env).strip()),
        "fixture_test_node": NODE,
        "fixture_test_output_sha256": _sha256(private / "fixture-test-output.txt"),
        "verified_inventory_sha256": _sha256(inventory_path),
        "verified_completed_record_count": inventory["verified_completed_record_count"],
        "record_receipt_identities": [{key: row.get(key) for key in
            ("record_id", "record_digest", "receipt_id", "receipt_digest",
             "admission_id", "admission_binding_digest")}
            for row in consequence_records + feedback_records],
        "event_identities": [{key: event.get(key) for key in
            ("event_id", "event_digest", "record_correlation_id", "classification", "evaluated_at")}
            for event in all_events],
        "decision_feedback_record_count": len(feedback_records),
        "preregistration_sha256": _sha256(prereg),
        "scorer_manifest_sha256": _sha256(scorer),
        "subject_packet_sha256_by_filename": {path.name: _sha256(path)
            for path in sorted(subject.glob("*.json"))},
        "subject_session_count_completed": 0,
        "independent_preregistration_archive": {
            "status": "pending_operator_action_before_subject_sessions",
            "requirement": "Archive or timestamp the exact preregistration file outside this workspace before any subject session."}}
    manifest_path = private / "pilot-custody-manifest.json"
    _write(manifest_path, manifest)
    print(json.dumps({"output_root": str(root), "packet_count": 6,
        "subject_packet_dir": str(subject), "operator_handoff": str(handoff),
        "private_scorer_manifest": str(scorer), "private_preregistration": str(prereg),
        "private_inventory": str(inventory_path), "private_custody_manifest": str(manifest_path),
        "source_chronology": {
            "verified_completed_record_count": inventory["verified_completed_record_count"],
            "consequence_record_count": len(consequence_records),
            "consequence_event_count": len(all_events),
            "decision_feedback_record_count": len(feedback_records)},
        "real_subject_sessions_run": 0}, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
