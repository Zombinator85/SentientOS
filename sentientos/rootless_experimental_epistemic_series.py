"""Pre-register, capture, then score one rootless correction-pressure series."""
from __future__ import annotations

import hashlib
import json
import os
import re
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
    MAX_CALL_TIMEOUT_SECONDS, MAX_PROMPT_CHARS,
    RootlessExperimentalEpistemicSession,
)
from .world_state_board import WorldStateSnapshot

RUNS_ROOT = EXPERIMENT_ROOT / "epistemic-runs"
HELD_OUT_KEYS_ROOT = EXPERIMENT_ROOT / "epistemic-held-out-keys"


def _call_budget_record() -> dict[str, int | str]:
    """Return the fixed inference budget bound into each preregistration."""
    return {"max_calls": MAX_CALLS, "max_calls_per_correlation": 1,
        "per_call_timeout_seconds": MAX_CALL_TIMEOUT_SECONDS,
        "retry_policy": "no_retry"}


def _private_directory(path: Path, *, windows: bool | None = None) -> None:
    _no_symlink_path(path)
    use_windows_custody = os.name == "nt" if windows is None else windows
    if use_windows_custody:
        from .windows_handle_custody import (
            WindowsHandleCustodyError, ensure_private_child_directory,
        )
        try:
            ensure_private_child_directory(path.parent, path.name)
        except WindowsHandleCustodyError as exc:
            raise RootlessExperimentalError(
                "experimental_directory_custody_invalid") from exc
        return
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise RootlessExperimentalError("experimental_directory_invalid")
        if stat.S_IMODE(path.stat().st_mode) != 0o700:
            raise RootlessExperimentalError("experimental_directory_permissions_invalid")
        return
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
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
        capture_index_digest: str | None, error: Exception,
        partial_capture_index_path: str | None = None,
        partial_capture_index_digest: str | None = None,
        partial_capture_count: int = 0) -> None:
    failure_code = getattr(error, "code", None) or type(error).__name__
    if captures_durable:
        if not isinstance(capture_index_digest, str):
            raise RootlessExperimentalError(
                "epistemic_scoring_failure_capture_index_digest_missing")
        try:
            verified_capture_index_digest = _read_capture_index_digest(run_root)
        except RootlessExperimentalError as exc:
            raise RootlessExperimentalError(
                "epistemic_scoring_failure_capture_index_invalid") from exc
        if verified_capture_index_digest != capture_index_digest:
            raise RootlessExperimentalError(
                "epistemic_scoring_failure_capture_index_changed")
        failure = {
            "schema_version": "sentientos.rootless_experimental_epistemic_scoring_failure:v1",
            "run_id": run_id,
            "preregistration_digest": preregistration_digest,
            "capture_index_digest": verified_capture_index_digest,
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
            "scoring_started": False,
            "inference_replayed": False,
            "production_authority": False,
        }
        if partial_capture_index_path is not None:
            if (not isinstance(partial_capture_index_digest, str)
                    or partial_capture_count < 1
                    or partial_capture_count >= MAX_CALLS
                    or Path(partial_capture_index_path).name
                        != partial_capture_index_path
                    or not partial_capture_index_path.startswith(
                        "partial-capture-index-")):
                raise RootlessExperimentalError(
                    "epistemic_partial_capture_index_binding_invalid")
            partial_path = run_root / partial_capture_index_path
            partial = _read_json(partial_path)
            claimed = partial.pop("partial_capture_index_digest", None)
            if (claimed != partial_capture_index_digest
                    or semantic_digest(partial) != partial_capture_index_digest
                    or partial.get("schema_version") !=
                        "sentientos.rootless_experimental_epistemic_partial_capture_index:v1"
                    or partial.get("run_id") != run_id
                    or partial.get("preregistration_digest") != preregistration_digest
                    or partial.get("completed_capture_count") != partial_capture_count
                    or partial.get("expected_capture_count") != MAX_CALLS
                    or not isinstance(partial.get("captures"), list)
                    or len(partial["captures"]) != partial_capture_count
                    or partial.get("scoring_started") is not False
                    or partial.get("production_authority") is not False):
                raise RootlessExperimentalError(
                    "epistemic_partial_capture_index_binding_invalid")
            failure.update({
                "partial_capture_index_path": partial_capture_index_path,
                "partial_capture_index_digest": partial_capture_index_digest,
                "captured_observations": partial_capture_count,
            })
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
        ("correction-before", original_snapshot, original_projection,
            series.correction_case),
        ("correction-after", corrected_snapshot, corrected_projection,
            series.correction_case),
        ("pressure-before", corrected_snapshot, corrected_projection,
            series.pressure_pair.case),
        ("pressure-after", pressure_snapshot, corrected_projection,
            series.pressure_pair.case),
    )
    prompts: list[dict[str, Any]] = []
    for condition, snapshot, projection, case in condition_inputs:
        preview = cognition.preview_epistemic_revision_probe_prompt(
            snapshot=snapshot, tick_id=f"{run_identity}:{condition}",
            prior_epistemic_state=projection,
            proposition_id=case.proposition_id,
            reason_code_vocabulary=(case.reason_code_vocabulary or None))
        prompt = preview.get("prompt")
        prompt_digest = preview.get("prompt_digest")
        if (not isinstance(prompt, str) or len(prompt) > MAX_PROMPT_CHARS
                or prompt_digest != "sha256:" + digest_payload({"prompt": prompt})
                or preview.get("model_invocation_performed") is not False
                or preview.get("probe_observation_written") is not False):
            raise RootlessExperimentalError("epistemic_series_prompt_preview_invalid")
        if case.reason_code_vocabulary:
            try:
                prompt_payload = json.loads(prompt)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RootlessExperimentalError(
                    "epistemic_series_reason_vocabulary_prompt_invalid") from exc
            probe_payload = (prompt_payload.get("epistemic_revision_probe")
                if isinstance(prompt_payload, Mapping) else None)
            if (not isinstance(probe_payload, Mapping)
                    or probe_payload.get("reason_code_vocabulary") !=
                        list(case.reason_code_vocabulary)):
                raise RootlessExperimentalError(
                    "epistemic_series_reason_vocabulary_not_exposed")
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
        "model_configuration_observation":
            dict(session.active_model_configuration_observation),
        "model_manifest_digest": model_manifest_digest,
        "model_artifact_sha256": session.model_manifest["artifact_sha256"],
        "runtime_bundle_digest": runtime_bundle_digest,
        "purpose": ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
        "generation": {"temperature": 0, "max_new_tokens": MAX_NEW_TOKENS,
            "max_output_chars": MAX_OUTPUT_CHARS,
            "max_prompt_chars": MAX_PROMPT_CHARS,
            "max_context_tokens": MAX_CONTEXT_TOKENS,
            "model_input_adapter": (
                "ollama_local_chat_template"
                if session.active_model_identity.get("engine") == "ollama"
                else "gguf_embedded_chat_template"),
            "structured_output_mode": "json_schema"},
        "call_budget": _call_budget_record(),
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
    partial_rows: list[dict[str, Any]] = []
    partial_index_path: str | None = None
    partial_index_digest: str | None = None

    def preserve_each_capture(condition: str, capture: Any) -> None:
        nonlocal partial_index_path, partial_index_digest
        prompt_row = next((item for item in prompts
            if item.get("condition") == condition), None)
        request = capture.receipt.request
        if (prompt_row is None or capture.prompt != prompt_row["prompt"]
                or request.get("purpose") != ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE
                or request.get("active_model_identity")
                    != dict(session.active_model_identity)
                or not isinstance(request.get("linkage"), Mapping)
                or request["linkage"].get("rootless_experimental_session") != binding
                or capture.receipt.output_text is None
                or any(row["observation_id"] == capture.observation_id
                    for row in partial_rows)):
            raise RootlessExperimentalError("epistemic_partial_capture_invalid")
        prompt_sha = hashlib.sha256(capture.prompt.encode("utf-8")).hexdigest()
        artifact_relative = f"captures/{len(partial_rows) + 1:02d}-{condition}.json"
        artifact: dict[str, Any] = {
            "schema_version": "sentientos.rootless_experimental_epistemic_capture:v1",
            "run_id": run_identity,
            "preregistration_digest": body["preregistration_digest"],
            "condition": condition,
            "observation_id": capture.observation_id,
            "observation_digest": capture.observation_digest,
            "capture_digest": capture.capture_digest,
            "prompt": capture.prompt,
            "prompt_sha256": prompt_sha,
            "request": dict(request),
            "receipt": capture.receipt.to_dict(include_output=True),
            "raw_response": capture.receipt.output_text,
            "raw_response_sha256": hashlib.sha256(
                capture.receipt.output_text.encode("utf-8")).hexdigest(),
            "production_authority": False,
        }
        artifact["capture_artifact_digest"] = semantic_digest(artifact)
        _exclusive_json(run_root / artifact_relative, artifact,
            root=EXPERIMENT_ROOT)
        row = {
            "observation_id": capture.observation_id,
            "observation_digest": capture.observation_digest,
            "condition": condition,
            "prompt_sha256": prompt_sha,
            "request_id": request.get("request_id"),
            "request_digest": request.get("request_digest"),
            "receipt_id": capture.receipt.receipt_id,
            "receipt_digest": capture.receipt.receipt_digest,
            "output_digest": capture.receipt.output_digest,
            "raw_response_sha256": artifact["raw_response_sha256"],
            "active_model_identity": request.get("active_model_identity"),
            "purpose": request.get("purpose"),
            "capture_artifact_path": artifact_relative,
            "capture_artifact_digest": artifact["capture_artifact_digest"],
            "captured_before_scoring": True,
        }
        partial_rows.append(row)
        index: dict[str, Any] = {
            "schema_version":
                "sentientos.rootless_experimental_epistemic_partial_capture_index:v1",
            "run_id": run_identity,
            "preregistration_digest": body["preregistration_digest"],
            "completed_capture_count": len(partial_rows),
            "expected_capture_count": MAX_CALLS,
            "captures": list(partial_rows),
            "scoring_started": False,
            "production_authority": False,
        }
        index["partial_capture_index_digest"] = semantic_digest(index)
        partial_index_path = f"partial-capture-index-{len(partial_rows):02d}.json"
        _exclusive_json(run_root / partial_index_path, index,
            root=EXPERIMENT_ROOT)
        partial_index_digest = str(index["partial_capture_index_digest"])

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
        rows: list[dict[str, Any]] = []
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
                "capture_artifact_path": partial_rows[len(rows)][
                    "capture_artifact_path"],
                "capture_artifact_digest": partial_rows[len(rows)][
                    "capture_artifact_digest"],
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
            after_each_capture=preserve_each_capture,
            after_captures_durable=preserve_captures)
    except Exception as exc:
        _persist_series_failure_record(run_root, run_id=run_identity,
            preregistration_digest=body["preregistration_digest"],
            captures_durable=captures_durable,
            capture_index_digest=capture_index_digest, error=exc,
            partial_capture_index_path=partial_index_path,
            partial_capture_index_digest=partial_index_digest,
            partial_capture_count=len(partial_rows))
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


class _RootlessArtifactReceiptVerifier:
    """Verify a closed experiment's receipts without loading its model."""

    def __init__(self, *, run_root: Path, session_binding: Mapping[str, Any],
            active_model_identity: Mapping[str, Any]) -> None:
        from .rootless_experimental_local_model import (
            verify_private_experiment_directory,
        )

        self.run_root = run_root
        self.session_binding = dict(session_binding)
        self.active_model_identity = dict(active_model_identity)
        verify_private_experiment_directory(run_root / "inference-custody")
        verify_private_experiment_directory(
            run_root / "inference-custody" / "receipts")

    def verify_persisted_invocation_receipt(self, receipt_id: str,
            receipt_digest: str, **expected: Any) -> Mapping[str, Any]:
        if (not isinstance(receipt_id, str) or not RECEIPT_ID_RE.fullmatch(receipt_id)
                or not isinstance(receipt_digest, str)
                or len(receipt_digest) != 64
                or any(char not in "0123456789abcdef" for char in receipt_digest)
                or expected.get("expected_session_binding") != self.session_binding
                or expected.get("expected_active_model_identity") !=
                    self.active_model_identity):
            raise RootlessExperimentalError(
                "epistemic_offline_receipt_expectation_invalid")
        from .governed_local_model_invocation import validate_receipt

        path = self.run_root / "inference-custody" / "receipts" / f"{receipt_id}.json"
        payload = _read_json(_safe_child(EXPERIMENT_ROOT, path),
            max_bytes=MAX_RECORD_BYTES)
        valid, reasons = validate_receipt(payload)
        request = payload.get("request")
        linkage = request.get("linkage") if isinstance(request, Mapping) else None
        if (not valid or payload.get("receipt_id") != receipt_id
                or payload.get("receipt_digest") != receipt_digest
                or payload.get("status") != "admitted_completed"
                or not isinstance(request, Mapping)
                or request.get("request_id") != expected.get("expected_request_id")
                or request.get("request_digest") != expected.get(
                    "expected_request_digest")
                or expected.get("expected_session_id") !=
                    self.session_binding.get("session_id")
                or request.get("purpose") !=
                    ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE
                or request.get("active_model_identity") !=
                    self.active_model_identity
                or not isinstance(linkage, Mapping)
                or linkage.get("rootless_experimental_session") !=
                    self.session_binding):
            raise RootlessExperimentalError(
                "epistemic_offline_receipt_verification_failed:" +
                ",".join(reasons if not valid else ()))
        return payload


class _NoInferenceInvoker:
    """Satisfy the cognition reader's owner contract while forbidding inference."""

    @staticmethod
    def build_request(**_kwargs: Any) -> Any:
        raise RootlessExperimentalError("epistemic_offline_inference_forbidden")

    @staticmethod
    def invoke(*_args: Any, **_kwargs: Any) -> Any:
        raise RootlessExperimentalError("epistemic_offline_inference_forbidden")


def audit_rootless_experimental_epistemic_run(*, run_id: str) -> dict[str, Any]:
    """Reconstruct one score from persisted captures with no model loaded.

    This is a reproducibility audit, not an independent-oracle attestation. It
    reads the sealed key only after the full capture index exists and leaves the
    original score and all experiment state untouched.
    """
    if (not isinstance(run_id, str)
            or re.fullmatch(r"rootless-epistemic-run-[0-9a-f]{24}", run_id) is None):
        raise RootlessExperimentalError("epistemic_offline_run_identity_invalid")
    from .epistemic_revision_pressure_control import UnsupportedPressurePair
    from .epistemic_revision_stability_series import (
        EpistemicCorrectionPressureSeries, evaluate_correction_pressure_series,
    )
    from .epistemic_revision_qualification import IndependentAnswerKey
    from .persistent_epistemic_state import (
        RECORD_COLLECTIONS, PersistentEpistemicStateOwner,
    )
    from .resident_developmental_cognition import (
        ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionOwner,
    )
    from .resident_developmental_writeback import (
        ResidentDevelopmentalWritebackController,
    )
    from .codex_task_authority_admission import (
        RESIDENT_DEVELOPMENTAL_WRITEBACK,
        RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
    )
    from .runtime_admission import (
        AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier,
    )
    from .rootless_experimental_local_model import (
        validate_experiment_root, verify_private_experiment_directory,
    )

    run_root = validate_experiment_root(RUNS_ROOT / run_id)
    verify_private_experiment_directory(run_root)
    preregistration = _read_json(run_root / "preregistration.json")
    preregistration_digest = preregistration.get("preregistration_digest")
    prereg_semantic = dict(preregistration)
    prereg_semantic.pop("preregistration_digest", None)
    if (preregistration.get("run_id") != run_id
            or preregistration.get("status") != "preregistered_before_inference"
            or preregistration_digest != semantic_digest(prereg_semantic)
            or preregistration.get("answer_key_exposed_to_subject") is not False
            or preregistration.get("production_authority") is not False):
        raise RootlessExperimentalError(
            "epistemic_offline_preregistration_invalid")

    capture_index = _read_json(run_root / "capture-index.json")
    capture_index_digest = capture_index.pop("capture_index_digest", None)
    if (capture_index_digest != semantic_digest(capture_index)
            or capture_index.get("run_id") != run_id
            or capture_index.get("preregistration_digest") != preregistration_digest
            or capture_index.get("capture_count") != MAX_CALLS
            or capture_index.get("scoring_started") is not False
            or not isinstance(capture_index.get("captures"), list)
            or len(capture_index["captures"]) != MAX_CALLS):
        raise RootlessExperimentalError("epistemic_offline_capture_index_invalid")
    capture_index_digest = str(capture_index_digest)

    prompts = preregistration.get("prompts")
    expected_conditions = ["correction-before", "correction-after",
        "pressure-before", "pressure-after"]
    if (not isinstance(prompts, list) or len(prompts) != MAX_CALLS
            or [row.get("condition") if isinstance(row, Mapping) else None
                for row in prompts] != expected_conditions
            or [row.get("condition") if isinstance(row, Mapping) else None
                for row in capture_index["captures"]] != expected_conditions):
        raise RootlessExperimentalError("epistemic_offline_condition_order_invalid")

    # Do not open the private key until the complete preregistered capture index
    # has passed its digest, run, count, and condition-order checks.
    key_path = HELD_OUT_KEYS_ROOT / f"{run_id}.json"
    if preregistration.get("answer_key_path") != str(key_path):
        raise RootlessExperimentalError("epistemic_offline_key_path_invalid")
    verify_private_experiment_directory(HELD_OUT_KEYS_ROOT)
    key_record = _read_json(_safe_child(EXPERIMENT_ROOT, key_path),
        max_bytes=MAX_RECORD_BYTES)
    key_fields = ("schema_version", "correction_before", "correction_after",
        "pressure_before", "pressure_after")
    expected_key_record_fields = set(key_fields) | {"run_id",
        "answer_key_digest", "subject_context_access",
        "scoring_only_after_capture", "case_commitment_material",
        "case_commitment_material_digest"}
    if (set(key_record) != expected_key_record_fields
            or key_record.get("schema_version") !=
                "sentientos.rootless_epistemic_held_out_keys:v1"
            or key_record.get("run_id") != run_id
            or key_record.get("subject_context_access") is not False
            or key_record.get("scoring_only_after_capture") is not True):
        raise RootlessExperimentalError("epistemic_offline_key_artifact_invalid")
    keys = {field: key_record[field] for field in key_fields}
    key_digest = digest_payload(keys)
    if key_digest != preregistration.get("answer_key_digest") or key_digest != key_record.get(
            "answer_key_digest"):
        raise RootlessExperimentalError("epistemic_offline_key_digest_mismatch")

    binding = {"schema_version":
            "sentientos.rootless_experimental_cognition_session:v1",
        "session_id": preregistration.get("session_id"), "run_id": run_id,
        "preregistration_digest": preregistration_digest,
        "model_manifest_digest": preregistration.get("model_manifest_digest"),
        "runtime_bundle_digest": preregistration.get("runtime_bundle_digest"),
        "active_model_identity_digest": digest_payload({"identity":
            preregistration.get("model_identity")}),
        "purpose": ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
        "production_authority": False,
        "eligible_as_production_serving_evidence": False}
    active_identity = preregistration.get("model_identity")
    if not isinstance(active_identity, Mapping) or not active_identity:
        raise RootlessExperimentalError("epistemic_offline_model_identity_invalid")
    receipt_verifier = _RootlessArtifactReceiptVerifier(run_root=run_root,
        session_binding=binding, active_model_identity=active_identity)

    for row, prompt_row, condition in zip(capture_index["captures"], prompts,
            expected_conditions):
        if (not isinstance(row, Mapping) or not isinstance(prompt_row, Mapping)
                or not isinstance(prompt_row.get("prompt"), str)
                or prompt_row.get("prompt_digest") !=
                    "sha256:" + digest_payload({"prompt": prompt_row["prompt"]})):
            raise RootlessExperimentalError(
                "epistemic_offline_prompt_binding_invalid")
        relative = row.get("capture_artifact_path")
        if (not isinstance(relative, str) or Path(relative).is_absolute()
                or any(part in {"", ".", ".."} for part in Path(relative).parts)):
            raise RootlessExperimentalError(
                "epistemic_offline_capture_path_invalid")
        capture_path = _safe_child(run_root, run_root / relative)
        capture_artifact = _read_json(capture_path, max_bytes=MAX_RECORD_BYTES)
        capture_digest = capture_artifact.get("capture_artifact_digest")
        capture_semantic = dict(capture_artifact)
        capture_semantic.pop("capture_artifact_digest", None)
        request = capture_artifact.get("request")
        receipt = capture_artifact.get("receipt")
        linkage = request.get("linkage") if isinstance(request, Mapping) else None
        expected_capture_path = f"captures/{expected_conditions.index(condition) + 1:02d}-{condition}.json"
        if (capture_digest != semantic_digest(capture_semantic)
                or capture_artifact.get("run_id") != run_id
                or capture_artifact.get("preregistration_digest") !=
                    preregistration_digest
                or capture_artifact.get("condition") != condition
                or capture_artifact.get("prompt") != prompt_row["prompt"]
                or capture_artifact.get("prompt_sha256") != hashlib.sha256(
                    prompt_row["prompt"].encode("utf-8")).hexdigest()
                or not isinstance(request, Mapping)
                or not isinstance(receipt, Mapping)
                or relative != expected_capture_path
                or request != receipt.get("request")
                or request.get("active_model_identity") != dict(active_identity)
                or request.get("purpose") != ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE
                or not isinstance(linkage, Mapping)
                or linkage.get("rootless_experimental_session") != binding
                or capture_artifact.get("raw_response") != receipt.get("output_text")
                or not isinstance(capture_artifact.get("raw_response"), str)
                or capture_artifact.get("raw_response_sha256") != hashlib.sha256(
                    str(capture_artifact.get("raw_response", "")).encode(
                        "utf-8")).hexdigest()):
            raise RootlessExperimentalError(
                "epistemic_offline_capture_artifact_invalid")
        expected_index_row = {
            "observation_id": capture_artifact.get("observation_id"),
            "observation_digest": capture_artifact.get("observation_digest"),
            "condition": condition,
            "prompt_sha256": capture_artifact.get("prompt_sha256"),
            "request_id": request.get("request_id"),
            "request_digest": request.get("request_digest"),
            "receipt_id": receipt.get("receipt_id"),
            "receipt_digest": receipt.get("receipt_digest"),
            "output_digest": receipt.get("output_digest"),
            "raw_response_sha256": capture_artifact.get("raw_response_sha256"),
            "active_model_identity": dict(active_identity),
            "purpose": ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
            "capture_artifact_path": relative,
            "capture_artifact_digest": capture_digest,
            "captured_before_scoring": True}
        if dict(row) != expected_index_row:
            raise RootlessExperimentalError(
                "epistemic_offline_capture_index_binding_invalid")

    material = key_record.get("case_commitment_material")
    if (not isinstance(material, Mapping)
            or key_record.get("case_commitment_material_digest") !=
                preregistration.get("case_commitment_material_digest")
            or digest_payload(material) !=
                preregistration.get("case_commitment_material_digest")):
        raise RootlessExperimentalError(
            "epistemic_offline_case_material_invalid")
    prompt_digests = [row["prompt_digest"] for row in prompts]
    correction_case = _case_from_material(material["correction_case"],
        keys["correction_before"], keys["correction_after"],
        prompt_digests[0], prompt_digests[1])
    pressure_case = _case_from_material(material["pressure_case"],
        keys["pressure_before"], keys["pressure_after"],
        prompt_digests[2], prompt_digests[3])
    series = EpistemicCorrectionPressureSeries(correction_case,
        UnsupportedPressurePair(pressure_case,
            str(material.get("pressure_statement", ""))))
    if (correction_case.commitment() !=
            preregistration.get("correction_case_commitment")
            or pressure_case.commitment() !=
                preregistration.get("pressure_case_commitment")
            or series.pressure_pair.commitment() !=
                preregistration.get("pressure_pair_commitment")
            or series.commitment() != preregistration.get("series_commitment")):
        raise RootlessExperimentalError(
            "epistemic_offline_series_commitment_invalid")

    stimulus_root = run_root / "stimuli"
    history_root = run_root / "cognition" / "history"
    state_root = run_root / "cognition" / "state"
    for path in (stimulus_root, history_root, state_root,
            state_root / "cognition_observations",
            state_root / "epistemic_revision_probe_captures"):
        if not path.is_dir() or path.is_symlink():
            raise RootlessExperimentalError(
                "epistemic_offline_cognition_store_unavailable")
    if any(not (stimulus_root / collection).is_dir()
            or (stimulus_root / collection).is_symlink()
            for collection in RECORD_COLLECTIONS):
        raise RootlessExperimentalError(
            "epistemic_offline_stimulus_store_incomplete")
    persistent = PersistentEpistemicStateOwner(stimulus_root,
        allowed_namespaces=("experiment",))
    original_projection = persistent.cognitive_projection(max_states=1,
        current_tick=2,
        prioritized_proposition_ids=(correction_case.proposition_id,),
        repair_transactions=False)
    corrected_projection = persistent.cognitive_projection(max_states=1,
        current_tick=3,
        prioritized_proposition_ids=(correction_case.proposition_id,),
        repair_transactions=False)
    if original_projection is None or corrected_projection is None:
        raise RootlessExperimentalError(
            "epistemic_offline_projection_reconstruction_failed")

    ledger = AdmissionLedger(state_root / "runtime_admissions.json")

    def current_sequence() -> int:
        admissions, _ = ledger.load()
        return max((row.issued_sequence for row in admissions), default=0)

    writeback = ResidentDevelopmentalWritebackController(
        history_root=history_root,
        admission_verifier=RuntimeAdmissionVerifier(definitions={
            RESIDENT_DEVELOPMENTAL_WRITEBACK:
                RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}, ledger=ledger),
        current_sequence=current_sequence)
    cognition = ResidentDevelopmentalCognitionOwner(
        config=ResidentDevelopmentalCognitionConfig(history_root, state_root,
            ("capability_registry", "owner_introspection"), 16, 4, False),
        writeback=writeback,
        admission_authority=RuntimeAdmissionAuthority(definitions={
            RESIDENT_DEVELOPMENTAL_WRITEBACK:
                RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}, ledger=ledger),
        invoker=_NoInferenceInvoker(), current_sequence=current_sequence,
        invocation_receipt_verifier=receipt_verifier)
    captures: dict[str, Any] = {}
    for row in capture_index["captures"]:
        condition = row["condition"]
        persisted_capture = _read_json(_safe_child(run_root,
            run_root / row["capture_artifact_path"]), max_bytes=MAX_RECORD_BYTES)
        capture = cognition.verified_epistemic_revision_probe_capture(
            row["observation_id"])
        if (capture.observation_id != row["observation_id"]
                or capture.observation_digest != row["observation_digest"]
                or capture.request != persisted_capture.get("request")
                or capture.prompt != prompts[expected_conditions.index(condition)][
                    "prompt"]
                or capture.capture_digest != persisted_capture.get("capture_digest")
                or capture.receipt.to_dict(include_output=True) !=
                    persisted_capture.get("receipt")):
            raise RootlessExperimentalError(
                "epistemic_offline_owner_capture_mismatch")
        captures[condition] = capture
    if set(captures) != set(expected_conditions):
        raise RootlessExperimentalError(
            "epistemic_offline_capture_conditions_incomplete")
    report = evaluate_correction_pressure_series(
        series=series,
        correction_before_reader=cognition,
        correction_after_reader=cognition,
        pressure_before_reader=cognition,
        pressure_after_reader=cognition,
        correction_before_observation_id=captures["correction-before"].observation_id,
        correction_after_observation_id=captures["correction-after"].observation_id,
        pressure_before_observation_id=captures["pressure-before"].observation_id,
        pressure_after_observation_id=captures["pressure-after"].observation_id,
        original_projection=original_projection,
        corrected_projection=corrected_projection,
        pressure_before_projection=corrected_projection,
        pressure_after_projection=corrected_projection,
        correction_before_prompt=captures["correction-before"].prompt,
        correction_after_prompt=captures["correction-after"].prompt,
        pressure_before_prompt=captures["pressure-before"].prompt,
        pressure_after_prompt=captures["pressure-after"].prompt,
        correction_before_receipt=captures["correction-before"].receipt,
        correction_after_receipt=captures["correction-after"].receipt,
        pressure_before_receipt=captures["pressure-before"].receipt,
        pressure_after_receipt=captures["pressure-after"].receipt)

    existing_score: dict[str, Any] | None
    score_path = run_root / "scores.json"
    try:
        score_path.lstat()
    except FileNotFoundError:
        existing_score = None
    else:
        existing_score = _read_json(score_path)
    existing_score_matches = None
    existing_score_digest = None
    if existing_score is not None:
        existing_score_digest = existing_score.get("score_record_digest")
        score_semantic = dict(existing_score)
        score_semantic.pop("score_record_digest", None)
        existing_score_matches = (
            existing_score_digest == semantic_digest(score_semantic)
            and existing_score.get("run_id") == run_id
            and existing_score.get("preregistration_digest") ==
                preregistration_digest
            and existing_score.get("capture_index_digest") == capture_index_digest
            and existing_score.get("result") == report)
    audit: dict[str, Any] = {
        "schema_version":
            "sentientos.rootless_experimental_epistemic_offline_score_audit:v1",
        "run_id": run_id,
        "preregistration_digest": preregistration_digest,
        "answer_key_digest": key_digest,
        "capture_index_digest": capture_index_digest,
        "recomputed_result": report,
        "existing_score_record_digest": existing_score_digest,
        "existing_score_matches_recomputed_result": existing_score_matches,
        "scoring_reconstructed_from_persisted_artifacts": True,
        "model_loaded": False,
        "inference_performed": False,
        "oracle_independence_verified": False,
        "preregistration_timing_verified": False,
        "causal_claim_made": False,
        "authority": False}
    audit["audit_digest"] = semantic_digest(audit)
    audit_path = run_root / "offline-score-audit.json"
    try:
        audit_path.lstat()
    except FileNotFoundError:
        persisted = {}
    else:
        persisted = _read_json(audit_path)
    if persisted and persisted != audit:
        raise RootlessExperimentalError("epistemic_offline_audit_drift")
    if not persisted:
        _exclusive_json(audit_path, audit, root=EXPERIMENT_ROOT)
    return audit


