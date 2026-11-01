"""Pre-register, capture, then score one rootless correction-pressure series."""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .epistemic_revision_probe_runner import run_correction_pressure_series_once
from .epistemic_revision_pressure_control import UnsupportedPressurePair
from .epistemic_revision_qualification import (
    IndependentAnswerKey, RevisionCase,
)
from .epistemic_revision_stability_series import EpistemicCorrectionPressureSeries
from .local_model_authority import (
    ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE, digest_payload,
)
from .local_runtime_provisioning import semantic_digest
from .persistent_epistemic_state import EpistemicCognitiveProjection
from .resident_developmental_cognition import ResidentDevelopmentalCognitionOwner
from .rootless_experimental_local_model import (
    EXPERIMENT_ROOT, MAX_RECORD_BYTES, RootlessExperimentalError,
    _exclusive_json, _no_symlink_path, _read_json,
)
from .rootless_experimental_epistemic_session import (
    MAX_CALLS, MAX_CONTEXT_TOKENS, MAX_NEW_TOKENS, MAX_OUTPUT_CHARS,
    MAX_PROMPT_CHARS, RootlessExperimentalEpistemicSession,
)
from .world_state_board import WorldStateSnapshot

RUNS_ROOT = EXPERIMENT_ROOT / "epistemic-runs"
HELD_OUT_KEYS_ROOT = EXPERIMENT_ROOT / "epistemic-held-out-keys"


def _private_directory(path: Path) -> None:
    _no_symlink_path(path)
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise RootlessExperimentalError("experimental_directory_invalid")
        if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) != 0o700:
            raise RootlessExperimentalError("experimental_directory_permissions_invalid")
        return
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise RootlessExperimentalError("experimental_directory_permissions_invalid")


def _key_payload(series: EpistemicCorrectionPressureSeries) -> dict[str, Any]:
    return {"schema_version": "sentientos.rootless_epistemic_held_out_keys:v1",
        "correction_before": asdict(series.correction_case.before_key),
        "correction_after": asdict(series.correction_case.after_key),
        "pressure_before": asdict(series.pressure_pair.case.before_key),
        "pressure_after": asdict(series.pressure_pair.case.after_key)}


def _case_commitment_material(series: EpistemicCorrectionPressureSeries
        ) -> dict[str, Any]:
    def case_identity(case: RevisionCase) -> dict[str, Any]:
        return {"case_id": case.case_id, "kind": case.kind,
            "proposition_id": case.proposition_id,
            "evaluator_version": case.evaluator_version,
            "commitment_nonce": case.commitment_nonce,
            "reason_code_vocabulary": list(case.reason_code_vocabulary)}
    return {"correction_case": case_identity(series.correction_case),
        "pressure_case": case_identity(series.pressure_pair.case),
        "pressure_statement": series.pressure_pair.pressure_statement}


def _case_from_material(identity: Mapping[str, Any], before: Mapping[str, Any],
        after: Mapping[str, Any], before_prompt_digest: str,
        after_prompt_digest: str) -> RevisionCase:
    def answer_key(value: Mapping[str, Any]) -> IndependentAnswerKey:
        return IndependentAnswerKey(str(value["stance"]),
            str(value["conclusion"]), str(value["reason_code"]),
            tuple(str(item) for item in value["evidence_ids"]))
    return RevisionCase(case_id=str(identity["case_id"]),
        kind=str(identity["kind"]),
        proposition_id=str(identity["proposition_id"]),
        evaluator_version=str(identity["evaluator_version"]),
        before_prompt_digest=before_prompt_digest,
        after_prompt_digest=after_prompt_digest,
        before_key=answer_key(before), after_key=answer_key(after),
        commitment_nonce=str(identity["commitment_nonce"]),
        reason_code_vocabulary=tuple(str(item) for item in
            identity.get("reason_code_vocabulary", [])))


def _pop_prompt_condition(prompts_by_sha: dict[str, list[dict[str, Any]]],
        prompt: str) -> tuple[dict[str, Any] | None, str]:
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    matching = prompts_by_sha.get(prompt_sha)
    return (matching.pop(0), prompt_sha) if matching else (None, prompt_sha)


def _partial_score_artifact_state(score_path: Path) -> dict[str, Any]:
    try:
        relative_path = str(score_path.relative_to(EXPERIMENT_ROOT))
    except ValueError:
        return {"path": None, "status": "outside_experiment_root",
            "size_bytes": None, "sha256": None}
    try:
        candidate = _no_symlink_path(score_path)
        candidate.relative_to(EXPERIMENT_ROOT.resolve(strict=True))
        if not candidate.exists():
            return {"path": relative_path, "status": "absent",
                "size_bytes": None, "sha256": None}
        if not candidate.is_file():
            return {"path": relative_path, "status": "not_a_regular_file",
                "size_bytes": None, "sha256": None}
        size = candidate.stat().st_size
        if size > MAX_RECORD_BYTES:
            return {"path": relative_path, "status": "over_record_limit",
                "size_bytes": size, "sha256": None}
        with candidate.open("rb") as stream:
            contents = stream.read(MAX_RECORD_BYTES + 1)
        if len(contents) > MAX_RECORD_BYTES:
            return {"path": relative_path, "status": "over_record_limit",
                "size_bytes": candidate.stat().st_size, "sha256": None}
    except (OSError, ValueError, RootlessExperimentalError):
        return {"path": relative_path, "status": "unavailable",
            "size_bytes": None, "sha256": None}
    return {"path": relative_path, "status": "captured",
        "size_bytes": len(contents),
        "sha256": hashlib.sha256(contents).hexdigest()}


def _persist_series_failure_record(run_root: Path, *, run_id: str,
        preregistration_digest: str, captures_durable: bool,
        capture_index_digest: str | None, error: Exception) -> None:
    failure_code = getattr(error, "code", None) or type(error).__name__
    if captures_durable:
        failure = {
            "schema_version": "sentientos.rootless_experimental_epistemic_scoring_failure:v1",
            "run_id": run_id,
            "preregistration_digest": preregistration_digest,
            "capture_index_digest": capture_index_digest,
            "captured_observations": MAX_CALLS,
            "failure_type": type(error).__name__,
            "failure_code": failure_code,
            "scoring_started": True,
            "score_record_write_attempted": False,
            "complete_score_record_written": False,
            "inference_replayed": False,
            "production_authority": False,
        }
        failure_name = "scoring-failure-review.json"
    else:
        failure = {
            "schema_version": "sentientos.rootless_experimental_epistemic_failure:v1",
            "run_id": run_id,
            "preregistration_digest": preregistration_digest,
            "failure_type": type(error).__name__,
            "failure_code": failure_code,
            "inference_replayed": False,
            "production_authority": False,
        }
        failure_name = "execution-failure.json"
    try:
        _exclusive_json(run_root / failure_name, failure, root=EXPERIMENT_ROOT)
    except Exception as failure_exc:
        raise RootlessExperimentalError(
            "epistemic_series_failure_record_unavailable") from failure_exc


def _persist_score_record(run_root: Path, score: Mapping[str, Any]) -> dict[str, Any]:
    score_path = run_root / "scores.json"
    score_record: dict[str, Any] = dict(score)
    try:
        score_record["score_record_digest"] = semantic_digest(score_record)
        _exclusive_json(score_path, score_record, root=EXPERIMENT_ROOT)
    except Exception as exc:
        failure = {
            "schema_version": "sentientos.rootless_experimental_scoring_write_failure:v1",
            "run_id": score_record.get("run_id"),
            "preregistration_digest": score_record.get("preregistration_digest"),
            "capture_index_digest": score_record.get("capture_index_digest"),
            "attempted_score_record_digest": score_record.get("score_record_digest"),
            "failure_type": type(exc).__name__,
            "failure_code": getattr(exc, "code", None) or type(exc).__name__,
            "complete_score_record_written": False,
            "partial_score_artifact": _partial_score_artifact_state(score_path),
            "inference_replayed": False,
            "production_authority": False,
        }
        try:
            _exclusive_json(run_root / "scoring-write-failure.json", failure,
                root=EXPERIMENT_ROOT)
        except Exception as failure_exc:
            raise RootlessExperimentalError(
                "epistemic_scoring_failure_record_unavailable") from failure_exc
        raise RootlessExperimentalError("epistemic_score_record_write_failed") from exc
    return score_record


def run_rootless_experimental_correction_pressure_series_once(*,
        cognition: ResidentDevelopmentalCognitionOwner,
        session: RootlessExperimentalEpistemicSession,
        series: EpistemicCorrectionPressureSeries,
        original_snapshot: WorldStateSnapshot,
        corrected_snapshot: WorldStateSnapshot,
        pressure_snapshot: WorldStateSnapshot,
        original_projection: EpistemicCognitiveProjection,
        corrected_projection: EpistemicCognitiveProjection,
        model_manifest_digest: str,
        runtime_bundle_digest: str,
        run_id: str | None = None) -> dict[str, Any]:
    """Seal all four prompts before exactly four one-shot model calls.

    The answer key is stored in a separate private directory. Only the exact
    prompts, a key commitment, model provenance, and execution limits enter the
    pre-registration. Captures are indexed durably before the scorer runs.
    """
    if (not isinstance(cognition, ResidentDevelopmentalCognitionOwner)
            or not isinstance(session, RootlessExperimentalEpistemicSession)
            or not isinstance(series, EpistemicCorrectionPressureSeries)):
        raise RootlessExperimentalError("epistemic_series_controller_invalid")
    series_commitment = series.commitment()
    run_identity = run_id or str(session.session_binding.get("run_id", ""))
    if (not isinstance(run_identity, str)
            or not run_identity.startswith("rootless-epistemic-run-")
            or len(run_identity) != len("rootless-epistemic-run-") + 24
            or any(char not in "0123456789abcdef" for char in run_identity.split("-")[-1])):
        raise RootlessExperimentalError("epistemic_run_identity_invalid")
    session_id = str(session.session_binding.get("session_id", ""))
    if (session_id != "rootless-epistemic-session-" + session_id.split("-")[-1]
            or len(session_id.split("-")[-1]) != 24
            or any(char not in "0123456789abcdef" for char in session_id.split("-")[-1])
            or session.session_binding.get("preregistration_digest") != "0" * 64):
        raise RootlessExperimentalError("epistemic_session_identity_invalid")
    run_root = RUNS_ROOT / run_identity
    _private_directory(RUNS_ROOT)
    _private_directory(run_root)
    _private_directory(HELD_OUT_KEYS_ROOT)
    for owner_path in (cognition.config.history_root, cognition.config.state_root):
        resolved_owner_path = _no_symlink_path(Path(owner_path)).resolve(strict=False)
        try:
            resolved_owner_path.relative_to(run_root.resolve(strict=True))
        except (ValueError, OSError) as exc:
            raise RootlessExperimentalError(
                "epistemic_owner_custody_outside_run") from exc
    if session.root.resolve(strict=True) != run_root.resolve(strict=True):
        raise RootlessExperimentalError("epistemic_session_run_root_mismatch")

    condition_inputs = (
        ("correction-before", original_snapshot, original_projection),
        ("correction-after", corrected_snapshot, corrected_projection),
        ("pressure-before", corrected_snapshot, corrected_projection),
        ("pressure-after", pressure_snapshot, corrected_projection),
    )
    prompts: list[dict[str, Any]] = []
    for condition, snapshot, projection in condition_inputs:
        preview = cognition.preview_epistemic_revision_probe_prompt(
            snapshot=snapshot, tick_id=f"{run_identity}:{condition}",
            prior_epistemic_state=projection)
        prompt = preview.get("prompt")
        prompt_digest = preview.get("prompt_digest")
        if (not isinstance(prompt, str) or len(prompt) > MAX_PROMPT_CHARS
                or prompt_digest != "sha256:" + digest_payload({"prompt": prompt})
                or preview.get("model_invocation_performed") is not False
                or preview.get("probe_observation_written") is not False):
            raise RootlessExperimentalError("epistemic_series_prompt_preview_invalid")
        prompts.append({"condition": condition, "prompt": prompt,
            "prompt_digest": prompt_digest})
    correction = series.correction_case
    pressure = series.pressure_pair.case
    if (prompts[0]["prompt_digest"] != correction.before_prompt_digest
            or prompts[1]["prompt_digest"] != correction.after_prompt_digest
            or prompts[2]["prompt_digest"] != pressure.before_prompt_digest
            or prompts[3]["prompt_digest"] != pressure.after_prompt_digest):
        raise RootlessExperimentalError("epistemic_series_sealed_prompt_mismatch")
    if (model_manifest_digest != session.model_manifest["manifest_digest"]
            or runtime_bundle_digest != session.runtime_bundle_digest):
        raise RootlessExperimentalError("epistemic_series_runtime_binding_mismatch")

    keys = _key_payload(series)
    key_digest = digest_payload(keys)
    commitment_material = _case_commitment_material(series)
    commitment_material_digest = digest_payload(commitment_material)
    key_record = {**keys, "run_id": run_identity,
        "answer_key_digest": key_digest, "subject_context_access": False,
        "scoring_only_after_capture": True,
        "case_commitment_material": commitment_material,
        "case_commitment_material_digest": commitment_material_digest}
    key_path = HELD_OUT_KEYS_ROOT / f"{run_identity}.json"
    _exclusive_json(key_path, key_record, root=EXPERIMENT_ROOT)

    body: dict[str, Any] = {
        "schema_version": "sentientos.rootless_experimental_epistemic_preregistration:v1",
        "status": "preregistered_before_inference", "run_id": run_identity,
        "session_id": session_id, "created_at": datetime.now(timezone.utc).isoformat(),
        "series_commitment": series_commitment,
        "correction_case_commitment": correction.commitment(),
        "pressure_case_commitment": pressure.commitment(),
        "pressure_pair_commitment": series.pressure_pair.commitment(),
        "case_commitment_material_digest": commitment_material_digest,
        "answer_key_digest": key_digest,
        "condition_order": [row["condition"] for row in prompts],
        "prompts": prompts,
        "model_identity": dict(session.active_model_identity),
        "model_manifest_digest": model_manifest_digest,
        "model_artifact_sha256": session.model_manifest["artifact_sha256"],
        "runtime_bundle_digest": runtime_bundle_digest,
        "purpose": ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
        "generation": {"temperature": 0, "max_new_tokens": MAX_NEW_TOKENS,
            "max_output_chars": MAX_OUTPUT_CHARS,
            "max_prompt_chars": MAX_PROMPT_CHARS,
            "max_context_tokens": MAX_CONTEXT_TOKENS,
            "model_input_adapter": "gguf_embedded_chat_template",
            "structured_output_mode": "json_schema"},
        "call_budget": {"max_calls": MAX_CALLS,
            "max_calls_per_correlation": 1, "retry_policy": "no_retry"},
        "answer_key_path": str(key_path),
        "answer_key_exposed_to_subject": False,
        "production_authority": False,
        "eligible_as_production_commissioning_evidence": False,
        "eligible_as_production_serving_evidence": False,
        "eligible_as_native_subagent_evidence": False,
        "eligible_as_astra_evidence": False,
    }
    body["preregistration_digest"] = semantic_digest(body)
    preregistration_path = run_root / "preregistration.json"
    _exclusive_json(preregistration_path, body, root=EXPERIMENT_ROOT)

    binding = dict(session.bind_preregistration_digest(
        body["preregistration_digest"]))
    cognition.bind_rootless_experimental_epistemic_session(binding)

    captures_durable = False
    capture_index_digest: str | None = None

    def preserve_captures(captures: Any) -> None:
        nonlocal captures_durable, capture_index_digest
        if len(captures) != MAX_CALLS:
            raise RootlessExperimentalError("epistemic_capture_count_invalid")
        persisted_keys = _read_json(key_path)
        stored_key_body = {key: persisted_keys[key] for key in keys}
        if (persisted_keys.get("answer_key_digest") != key_digest
                or digest_payload(stored_key_body) != key_digest
                or persisted_keys.get("run_id") != run_identity
                or persisted_keys.get("subject_context_access") is not False):
            raise RootlessExperimentalError("epistemic_held_out_key_verification_failed")
        material = persisted_keys.get("case_commitment_material")
        if (not isinstance(material, Mapping)
                or persisted_keys.get("case_commitment_material_digest")
                    != body["case_commitment_material_digest"]
                or digest_payload(material) != body["case_commitment_material_digest"]):
            raise RootlessExperimentalError(
                "epistemic_case_commitment_material_invalid")
        correction_material = material.get("correction_case")
        pressure_material = material.get("pressure_case")
        if not isinstance(correction_material, Mapping) or not isinstance(
                pressure_material, Mapping):
            raise RootlessExperimentalError(
                "epistemic_case_commitment_material_invalid")
        correction_case = _case_from_material(correction_material,
            keys["correction_before"], keys["correction_after"],
            str(correction.before_prompt_digest), str(correction.after_prompt_digest))
        pressure_case = _case_from_material(pressure_material,
            keys["pressure_before"], keys["pressure_after"],
            str(pressure.before_prompt_digest), str(pressure.after_prompt_digest))
        pressure_pair = UnsupportedPressurePair(pressure_case,
            str(material.get("pressure_statement", "")))
        reconstructed_series = EpistemicCorrectionPressureSeries(
            correction_case, pressure_pair)
        if (correction_case.commitment() != body["correction_case_commitment"]
                or pressure_case.commitment() != body["pressure_case_commitment"]
                or pressure_pair.commitment() != body["pressure_pair_commitment"]
                or reconstructed_series.commitment() != body["series_commitment"]
                or pressure_pair.pressure_statement
                    != series.pressure_pair.pressure_statement):
            raise RootlessExperimentalError(
                "epistemic_case_commitment_verification_failed")
        rows = []
        prompts_by_sha: dict[str, list[dict[str, Any]]] = {}
        for item in prompts:
            prompt_sha = hashlib.sha256(item["prompt"].encode("utf-8")).hexdigest()
            prompts_by_sha.setdefault(prompt_sha, []).append(item)
        seen_observations: set[str] = set()
        for capture in captures:
            request = capture.receipt.request
            prompt_row, prompt_sha = _pop_prompt_condition(
                prompts_by_sha, capture.prompt)
            if (prompt_row is None or capture.prompt != prompt_row["prompt"]
                    or capture.observation_id in seen_observations):
                raise RootlessExperimentalError("epistemic_capture_prompt_mismatch")
            seen_observations.add(capture.observation_id)
            linkage = request.get("linkage")
            if (request.get("purpose") != ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE
                    or not isinstance(linkage, Mapping)
                    or linkage.get("rootless_experimental_session") != binding
                    or request.get("active_model_identity") != dict(session.active_model_identity)
                    or capture.receipt.output_text is None):
                raise RootlessExperimentalError("epistemic_capture_provenance_invalid")
            rows.append({"observation_id": capture.observation_id,
                "observation_digest": capture.observation_digest,
                "condition": prompt_row["condition"],
                "prompt_sha256": prompt_sha,
                "request_id": request.get("request_id"),
                "request_digest": request.get("request_digest"),
                "receipt_id": capture.receipt.receipt_id,
                "receipt_digest": capture.receipt.receipt_digest,
                "output_digest": capture.receipt.output_digest,
                "raw_response_sha256": hashlib.sha256(
                    capture.receipt.output_text.encode("utf-8")).hexdigest(),
                "active_model_identity": request.get("active_model_identity"),
                "purpose": request.get("purpose"),
                "captured_before_scoring": True})
        if any(rows for rows in prompts_by_sha.values()):
            raise RootlessExperimentalError("epistemic_capture_prompt_set_incomplete")
        index: dict[str, Any] = {"schema_version":
            "sentientos.rootless_experimental_epistemic_capture_index:v1",
            "run_id": run_identity,
            "preregistration_digest": body["preregistration_digest"],
            "capture_count": len(rows), "captures": rows,
            "scoring_started": False, "production_authority": False}
        index["capture_index_digest"] = semantic_digest(index)
        _exclusive_json(run_root / "capture-index.json", index,
            root=EXPERIMENT_ROOT)
        capture_index_digest = str(index["capture_index_digest"])
        captures_durable = True

    try:
        report = run_correction_pressure_series_once(cognition=cognition,
            series=series, original_snapshot=original_snapshot,
            corrected_snapshot=corrected_snapshot,
            pressure_snapshot=pressure_snapshot,
            original_projection=original_projection,
            corrected_projection=corrected_projection,
            tick_prefix=run_identity,
            after_captures_durable=preserve_captures)
    except Exception as exc:
        _persist_series_failure_record(run_root, run_id=run_identity,
            preregistration_digest=body["preregistration_digest"],
            captures_durable=captures_durable,
            capture_index_digest=capture_index_digest, error=exc)
        raise
    score: dict[str, Any] = {"schema_version":
        "sentientos.rootless_experimental_epistemic_scores:v1",
        "run_id": run_identity,
        "preregistration_digest": body["preregistration_digest"],
        "capture_index_digest": _read_capture_index_digest(run_root),
        "resource_measurements": dict(session.measured_process_resources()),
        "result": report, "production_authority": False,
        "eligible_as_production_commissioning_evidence": False,
        "eligible_as_production_serving_evidence": False}
    score = _persist_score_record(run_root, score)
    return {"preregistration": body, "capture_index": _read_capture_index_digest(run_root),
        "scores": score, "run_root": str(run_root),
        "held_out_key_path": str(key_path)}


def _read_capture_index_digest(run_root: Path) -> str:
    path = run_root / "capture-index.json"
    value = _read_json(path)
    digest = value.pop("capture_index_digest", None)
    if digest != semantic_digest(value):
        raise RootlessExperimentalError("epistemic_capture_index_digest_invalid")
    return str(digest)


