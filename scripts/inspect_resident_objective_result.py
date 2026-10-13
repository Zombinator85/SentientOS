#!/usr/bin/env python3
"""Read one exact staged objective outcome without replay, admission, or writeback."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.developmental_history_intervention_experiment import DevelopmentalExperimentStore
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.resident_cognitive_model_serving import (
    CONFIG_ENV as SERVING_CONFIG_ENV, ResidentCognitiveInvocationReceiptReader,
    load_config as load_serving_config,
)
from sentientos.resident_developmental_cognition import (
    CONFIG_ENV as COGNITION_CONFIG_ENV, ResidentDevelopmentalCognitionError,
    ResidentDevelopmentalCognitionOwner,
    load_config as load_cognition_config, load_objective_request_by_identity,
    stored_objective_request_record, verified_objective_measurement_summary,
)
from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier


def _verify_observation(reader: ResidentCognitiveInvocationReceiptReader,
                        observation: Mapping[str, Any]) -> Mapping[str, Any] | None:
    session_id = observation.get("serving_session_id")
    binding = observation.get("serving_session_binding")
    if session_id is None and binding is None:
        return None
    if not isinstance(session_id, str) or not isinstance(binding, Mapping):
        raise ValueError("historical_invocation_session_binding_incomplete")
    return reader.verify_persisted_invocation_receipt(
        str(observation.get("inference_receipt_id", "")),
        str(observation.get("inference_receipt_digest", "")),
        expected_request_id=str(observation.get("request_id", "")),
        expected_request_digest=str(observation.get("request_digest", "")),
        expected_session_id=session_id,
        expected_session_binding=dict(binding),
        expected_active_model_identity=dict(observation.get("active_model_identity", {})),
        **({"expected_session_receipt_id": observation["serving_session_receipt_id"],
            "expected_session_receipt_digest": observation["serving_session_receipt_digest"]}
            if observation.get("serving_session_receipt_id") is not None else {}))


def inspect_result(*, cognition_config_path: Path, serving_config_path: Path,
                   request_id: str, request_digest: str,
                   installation_registry: InstallationStateRegistry | None = None) -> dict[str, Any]:
    """Reconcile one exact request from sealed state and installation custody."""
    config = load_cognition_config(cognition_config_path)
    if not config.enabled or not config.comparison_enabled:
        raise ResidentDevelopmentalCognitionError("history_comparison_not_enabled")
    serving_config = load_serving_config(str(serving_config_path))
    if not serving_config.enabled or not serving_config.installation_identity:
        raise ValueError("resident_serving_configuration_disabled")
    identity = InstallationIdentity.parse(serving_config.installation_identity)
    registry = installation_registry or InstallationStateRegistry.system()
    installation = registry.open_read_only(identity)
    reader = ResidentCognitiveInvocationReceiptReader(installation)
    custody = stored_objective_request_record(config.state_root,
        request_id=request_id, request_digest=request_digest)
    if custody.get("disposition") == "new":
        return {"status": "objective_request_not_recorded", "request_id": request_id,
            "request_digest": request_digest, "authority": False,
            "model_invoked": False, "write_performed": False}
    run_id = (custody.get("measurement_id") if custody.get("disposition") == "completed"
        else custody.get("recovered_experiment_run_id"))
    if not isinstance(run_id, str) or not run_id:
        return {"status": custody.get("objective_request_status") or "incomplete_without_scored_run",
            "request_id": request_id, "request_digest": request_digest,
            "tick_id": custody.get("tick_id"),
            "recovery_posture": "no_complete_score_custody; inference_replay_forbidden",
            "authority": False, "model_invoked": False, "write_performed": False}
    request = load_objective_request_by_identity(config.state_root,
        request_id=request_id, request_digest=request_digest)
    store = DevelopmentalExperimentStore(config.state_root,
        invocation_verifier=lambda row: _verify_observation(reader, row))
    result = dict(verified_objective_measurement_summary(experiments=store,
        measurement_id=run_id, request=request,
        verify_observation=lambda row: _verify_observation(reader, row)))
    expected_run_digest = custody.get("recovered_experiment_run_digest")
    if (isinstance(expected_run_digest, str)
            and result.get("measurement_digest") != expected_run_digest):
        raise ResidentDevelopmentalCognitionError("objective_outcome_recovered_run_digest_mismatch")
    result.update({"tick_id": custody.get("tick_id"),
        "recovery_posture": ("completed_run_loaded_without_inference_replay"
            if custody.get("disposition") == "interrupted" else "completed_run_loaded"),
        "model_invoked": False, "write_performed": False})
    return result


def inspect_progression(*, cognition_config_path: Path, serving_config_path: Path,
        request_refs: tuple[tuple[str, str], ...],
        installation_registry: InstallationStateRegistry | None = None) -> dict[str, Any]:
    """Read a bounded episode sequence through the configured receipt owner."""
    config = load_cognition_config(cognition_config_path)
    if not config.enabled or not config.comparison_enabled:
        raise ResidentDevelopmentalCognitionError("history_comparison_not_enabled")
    serving_config = load_serving_config(str(serving_config_path))
    if not serving_config.enabled or not serving_config.installation_identity:
        raise ValueError("resident_serving_configuration_disabled")
    identity = InstallationIdentity.parse(serving_config.installation_identity)
    registry = installation_registry or InstallationStateRegistry.system()
    installation = registry.open_read_only(identity)
    reader = ResidentCognitiveInvocationReceiptReader(installation)
    ledger = AdmissionLedger(config.state_root / "runtime_admissions.json")
    definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK:
        RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
    writeback = ResidentDevelopmentalWritebackController(
        history_root=config.history_root,
        admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger),
        current_sequence=ledger.current_sequence)
    owner = ResidentDevelopmentalCognitionOwner(config=config, writeback=writeback,
        admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
        invoker=reader, current_sequence=ledger.current_sequence)
    result = dict(owner.verified_objective_task_family_progression(
        request_refs=request_refs))
    result.update({"model_invoked": False, "write_performed": False})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get(COGNITION_CONFIG_ENV),
        help="exact resident developmental-cognition config")
    parser.add_argument("--serving-config", default=os.environ.get(SERVING_CONFIG_ENV),
        help="exact resident model-serving config for historical receipt verification")
    parser.add_argument("--request-id")
    parser.add_argument("--request-digest")
    parser.add_argument("--request", action="append", nargs=2, metavar=("ID", "DIGEST"),
        help="inspect a bounded task-family progression; repeat with exact request identities")
    args = parser.parse_args()
    if not args.config or not args.serving_config:
        parser.error(f"--config or {COGNITION_CONFIG_ENV}, and --serving-config or {SERVING_CONFIG_ENV} are required")
    try:
        if args.request:
            if args.request_id is not None or args.request_digest is not None:
                parser.error("use either repeated --request ID DIGEST or the single-request options")
            refs = tuple((str(request_id), str(request_digest))
                for request_id, request_digest in args.request)
            result = inspect_progression(cognition_config_path=Path(args.config),
                serving_config_path=Path(args.serving_config), request_refs=refs)
        else:
            if not args.request_id or not args.request_digest:
                parser.error("--request-id and --request-digest are required unless --request is used")
            result = inspect_result(cognition_config_path=Path(args.config),
                serving_config_path=Path(args.serving_config), request_id=args.request_id,
                request_digest=args.request_digest)
    except Exception as exc:
        result = {"status": "outcome_verification_unavailable",
            "reason_code": f"{type(exc).__name__}:{exc}"[:192],
            "request_id": args.request_id, "request_digest": args.request_digest,
            "model_invoked": False, "write_performed": False, "authority": False}
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result.get("status") in {
        "verified_objective_measurement", "objective_request_not_recorded",
        "comparable_scored_episodes", "descriptive_episodes_not_comparable",
        "insufficient_episode_count"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
