"""Verify a saved rootless run projects into bounded, usable task-family history.

This audit validates persisted invocation receipts without constructing or
loading a model. It checks the World-State projection budget and confirms that
the cognition reader reconstructs every score-bound acquisition example from
the retained history-present score rows. It performs no inference.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
import sys
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.developmental_history_intervention_experiment import (  # noqa: E402
    DevelopmentalExperimentStore,
)
from sentientos.local_model_authority import digest_payload  # noqa: E402
from sentientos.resident_developmental_cognition import (  # noqa: E402
    _task_family_history_examples,
)
from sentientos.resident_developmental_writeback import (  # noqa: E402
    MAX_OBJECTIVE_TASK_FAMILY_SELECTED_EVIDENCE_BYTES,
    _is_bounded_objective_task_family_trial,
    _resource_interpretation_projection,
)
from sentientos.rootless_experimental_local_model import (  # noqa: E402
    validate_experiment_root,
)
from sentientos.rootless_experimental_ollama_epistemic_session import (  # noqa: E402
    verify_rootless_historical_invocation_receipt,
)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True,
        allow_nan=False) + "\n").encode("utf-8")


def _invocation_verifier(cycle_root: Path):
    """Bind the dedicated receipt verifier without constructing a model session."""
    def verify(observation: Mapping[str, Any]) -> Mapping[str, Any]:
        identity = observation.get("active_model_identity")
        if not isinstance(identity, Mapping):
            raise ValueError("historical_observation_model_identity_missing")
        return verify_rootless_historical_invocation_receipt(
            cycle_root=cycle_root,
            receipt_id=str(observation.get("inference_receipt_id", "")),
            receipt_digest=str(observation.get("inference_receipt_digest", "")),
            expected_request_id=str(observation.get("request_id", "")),
            expected_request_digest=str(observation.get("request_digest", "")),
            expected_active_model_identity=dict(identity))

    return verify


def create_audit(*, cycle_root: Path, run_id: str) -> dict[str, Any]:
    root = validate_experiment_root(cycle_root)
    if not re.fullmatch(r"rootless-cognition-cycle-[0-9a-f]{20}", root.name):
        raise ValueError("projection_audit_cycle_identity_invalid")
    if not re.fullmatch(r"devexp-run-[0-9a-f]{24}", run_id):
        raise ValueError("projection_audit_run_identity_invalid")
    state_root = root / "resident-cognition" / "state"
    store = DevelopmentalExperimentStore(state_root,
        invocation_verifier=_invocation_verifier(root))
    run = store.load_run(run_id)
    records = store.world_state_records(run_refs=[(run_id, run["run_digest"])])
    if len(records) != 1:
        raise ValueError("projection_audit_source_record_count_invalid")
    record = records[0]
    fact = {
        "fact_id": record["source_id"],
        "source": {"kind": record["source_kind"],
            "source_id": record["source_id"], "digest": record["digest"]},
        "subject": {"subject_kind": record["subject_kind"],
            "subject_id": record["subject_id"]},
        "payload": record["payload"],
    }
    projected = _resource_interpretation_projection(fact)
    payload = projected.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("projection_audit_projected_payload_invalid")
    projected_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")
    projection = payload.get("interpretation_projection")
    evaluation = payload.get("objective_evaluation")
    outcomes = evaluation.get("probe_level_outcomes") \
        if isinstance(evaluation, Mapping) else None
    descriptor = payload.get("objective_task_descriptor")
    probe_inputs = descriptor.get("probe_inputs") \
        if isinstance(descriptor, Mapping) else None
    family_id = payload.get("objective_task_family")
    if (not _is_bounded_objective_task_family_trial(projected)
            or len(projected_bytes) >
                MAX_OBJECTIVE_TASK_FAMILY_SELECTED_EVIDENCE_BYTES
            or not isinstance(projection, Mapping)
            or projection.get("schema_version")
                != "sentientos.developmental_history_interpretation_projection:v4"
            or not isinstance(outcomes, Mapping)
            or outcomes.get("schema_version")
                != "sentientos.objective_probe_level_outcomes_projection:v2"
            or not isinstance(probe_inputs, list)
            or outcomes.get("probe_count") != len(probe_inputs)):
        raise ValueError("projection_audit_bounded_projection_invalid")
    candidate = {"selected_facts": [projected],
        "selected_sources": [projected["source"]]}
    examples = _task_family_history_examples(candidate,
        task_family_id=str(family_id))
    score_examples = examples[0].get("examples") if len(examples) == 1 else None
    score_probe_inputs = ([item.get("probe_input") for item in score_examples]
        if isinstance(score_examples, list)
        and all(isinstance(item, Mapping) for item in score_examples) else None)
    if (not isinstance(score_examples, list)
            or len(score_examples) != len(probe_inputs)
            or score_probe_inputs != probe_inputs
            or "acquisition_examples" in payload):
        raise ValueError("projection_audit_score_bound_examples_invalid")
    full_source_payload = record["payload"]
    semantic = {
        "schema_version": "sentientos.rootless_history_projection_compaction_audit:v2",
        "cycle_id": root.name,
        "run_id": run_id,
        "run_digest": run["run_digest"],
        "source_record_id": record["source_id"],
        "source_record_digest": record["digest"],
        "verified_condition_receipt_count": len(run["conditions"]),
        "task_family_id": family_id,
        "task_digest": descriptor.get("task_digest"),
        "history_present_score_digest": next(item.get("score_digest")
            for item in payload["objective_scores"]
            if item.get("condition_id") == "history_present"),
        "source_payload_bytes": len(json.dumps(full_source_payload,
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False).encode("utf-8")),
        "projected_payload_bytes": len(projected_bytes),
        "projection_byte_limit": MAX_OBJECTIVE_TASK_FAMILY_SELECTED_EVIDENCE_BYTES,
        "projection_schema_version": projection["schema_version"],
        "objective_outcome_projection_schema_version": outcomes["schema_version"],
        "compact_outcome_vectors_validated": True,
        "probe_count": len(probe_inputs),
        "reconstructed_score_bound_example_count": len(score_examples),
        "example_probe_input_digest": digest_payload(probe_inputs),
        "separate_acquisition_examples_omitted": True,
        "source_projection_digest": projection.get("projection_digest"),
        "inference_performed": False,
        "model_loaded": False,
        "learning_established": False,
        "authority": False,
    }
    return {**semantic, "audit_digest": digest_payload(semantic)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    report = create_audit(cycle_root=args.cycle_root, run_id=args.run_id)
    encoded = _canonical_bytes(report)
    if args.verify_existing:
        if args.output.is_symlink() or not args.output.is_file() \
                or args.output.read_bytes() != encoded:
            raise SystemExit("projection_audit_existing_artifact_mismatch")
        operation = "verified_existing"
    else:
        if args.output.is_symlink() or args.output.exists():
            raise SystemExit("projection_audit_output_already_exists")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
        operation = "created"
    print(json.dumps({"operation": operation, "audit_digest": report["audit_digest"],
        "projected_payload_bytes": report["projected_payload_bytes"],
        "probe_count": report["probe_count"], "inference_performed": False},
        sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
