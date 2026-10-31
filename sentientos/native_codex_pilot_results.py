from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_PILOT_PATH = Path(
    "artifacts/experiments/native_codex_unverified_pilot_20261031"
)
_STANCE_VALUES = {"supported", "contradicted", "unknown", "suspended"}


class ResultsIntegrityError(ValueError):
    """Raised when captured pilot records disagree with their digests or summaries."""


def _digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ResultsIntegrityError(f"Expected a JSON object: {path}")
    return value, raw


def _resolve_repo_path(repository_root: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ResultsIntegrityError(f"Absolute evidence path is not allowed: {relative_path}")
    resolved_root = repository_root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        raise ResultsIntegrityError(f"Evidence path escapes repository root: {relative_path}")
    return resolved


def _require_digest(actual: str, expected: Any, label: str) -> None:
    if not isinstance(expected, str) or actual != expected:
        raise ResultsIntegrityError(f"Digest mismatch for {label}")


def verify_native_codex_pilot_results(
    repository_root: Path,
    pilot_relative_path: Path = DEFAULT_PILOT_PATH,
) -> dict[str, Any]:
    """Verify internal capture/score consistency without opening the held-out key.

    The function verifies recorded hashes and that each score's observed stance
    matches the stance parsed from its captured response. It does not validate
    expected stances against the held-out key or verify the subject model.
    """
    repository_root = repository_root.resolve()
    pilot_dir = _resolve_repo_path(repository_root, str(pilot_relative_path))
    protocol_path = pilot_dir / "protocol.json"
    manifest_path = pilot_dir / "results" / "capture_manifest.json"
    summary_path = pilot_dir / "results" / "results_summary.json"

    protocol, protocol_bytes = _read_json(protocol_path)
    manifest, manifest_bytes = _read_json(manifest_path)
    summary, _ = _read_json(summary_path)

    _require_digest(_digest(protocol_bytes), summary.get("protocol_sha256"), "protocol")
    _require_digest(
        _digest(manifest_bytes), summary.get("capture_manifest_sha256"), "capture manifest"
    )

    protocol_rows = protocol.get("observations")
    manifest_rows = manifest.get("observations")
    score_rows = summary.get("score_files")
    if not isinstance(protocol_rows, list) or not isinstance(manifest_rows, list):
        raise ResultsIntegrityError("Protocol and manifest observations must be lists")
    if not isinstance(score_rows, list):
        raise ResultsIntegrityError("Summary score_files must be a list")

    protocol_by_trial = _unique_rows(protocol_rows, "trial_id", "protocol observations")
    manifest_by_trial = _unique_rows(manifest_rows, "trial_id", "capture observations")
    scores_by_trial = _unique_rows(score_rows, "trial_id", "summary score files")
    expected_trials = set(protocol_by_trial)
    if set(manifest_by_trial) != expected_trials or set(scores_by_trial) != expected_trials:
        raise ResultsIntegrityError("Protocol, capture, and score trial sets differ")
    if len(expected_trials) != protocol.get("trial_count"):
        raise ResultsIntegrityError("Protocol trial_count does not match its observations")
    if manifest.get("captured_count") != len(expected_trials):
        raise ResultsIntegrityError("Manifest captured_count does not match captured trials")

    conditions = protocol.get("conditions")
    if not isinstance(conditions, list) or not all(isinstance(x, str) for x in conditions):
        raise ResultsIntegrityError("Protocol conditions must be a list of strings")
    if len(conditions) != len(set(conditions)):
        raise ResultsIntegrityError("Protocol conditions must be unique")
    if summary.get("pilot_id") != manifest.get("pilot_id"):
        raise ResultsIntegrityError("Summary and manifest pilot IDs differ")
    if (
        manifest.get("subject_model_identity") != "unverified"
        or summary.get("subject_model_identity") != "unverified"
    ):
        raise ResultsIntegrityError("Pilot records must preserve the unverified model identity")

    counts = {condition: {"stance_match": 0, "valid_scored": 0} for condition in conditions}
    case_stances: dict[str, dict[str, str]] = {}
    case_conditions: dict[str, set[str]] = {}
    for trial_id in sorted(expected_trials):
        protocol_row = protocol_by_trial[trial_id]
        capture_row = manifest_by_trial[trial_id]
        case_id = protocol_row.get("case_id")
        condition = protocol_row.get("condition")
        if (
            not isinstance(case_id, str)
            or not isinstance(condition, str)
            or condition not in counts
        ):
            raise ResultsIntegrityError(f"Invalid case or condition for {trial_id}")
        seen_conditions = case_conditions.setdefault(case_id, set())
        if condition in seen_conditions:
            raise ResultsIntegrityError(f"Duplicate {condition} response for case {case_id}")
        seen_conditions.add(condition)
        if capture_row.get("condition") != condition:
            raise ResultsIntegrityError(f"Condition mismatch for {trial_id}")

        protocol_prompt = protocol_row.get("prompt")
        prompt_hash = (
            _digest(protocol_prompt.encode("utf-8"))
            if isinstance(protocol_prompt, str)
            else None
        )
        _require_digest(
            prompt_hash or "", protocol_row.get("prompt_sha256"), f"{trial_id} protocol prompt"
        )
        _require_digest(
            prompt_hash or "", capture_row.get("prompt_sha256"), f"{trial_id} captured prompt"
        )

        record_path = _resolve_repo_path(repository_root, capture_row.get("record_path", ""))
        observation, record_bytes = _read_json(record_path)
        _require_digest(
            _digest(record_bytes), capture_row.get("record_sha256"), f"{trial_id} record"
        )
        if (
            observation.get("trial_id") != trial_id
            or observation.get("pilot_id") != manifest.get("pilot_id")
        ):
            raise ResultsIntegrityError(f"Observation identity mismatch for {trial_id}")
        if observation.get("subject_task_id") != capture_row.get("task_id"):
            raise ResultsIntegrityError(f"Task identifier mismatch for {trial_id}")
        if (
            observation.get("subject_model_id") is not None
            or observation.get("subject_model_identity") != "unverified"
        ):
            raise ResultsIntegrityError(f"Unexpected subject identity assertion for {trial_id}")
        if observation.get("controller_context_or_answer_key_supplied") is not False:
            raise ResultsIntegrityError(f"Subject isolation flag is not false for {trial_id}")

        prompt = observation.get("prompt_utf8")
        response = observation.get("response_utf8")
        encoded_response = observation.get("response_utf8_base64")
        if (
            not isinstance(prompt, str)
            or not isinstance(response, str)
            or not isinstance(encoded_response, str)
        ):
            raise ResultsIntegrityError(f"Prompt or response bytes are missing for {trial_id}")
        if prompt != protocol_prompt:
            raise ResultsIntegrityError(f"Captured prompt differs from protocol for {trial_id}")
        _require_digest(
            _digest(prompt.encode("utf-8")), capture_row.get("prompt_sha256"), f"{trial_id} prompt"
        )
        response_bytes = response.encode("utf-8")
        if base64.b64decode(encoded_response, validate=True) != response_bytes:
            raise ResultsIntegrityError(f"Response UTF-8/base64 mismatch for {trial_id}")
        _require_digest(
            _digest(response_bytes), capture_row.get("response_sha256"), f"{trial_id} response"
        )
        if observation.get("response_sha256") != capture_row.get("response_sha256"):
            raise ResultsIntegrityError(f"Response digest mismatch for {trial_id}")
        try:
            parsed_response = json.loads(response)
        except json.JSONDecodeError as exc:
            raise ResultsIntegrityError(f"Response is not JSON for {trial_id}") from exc
        if (
            not isinstance(parsed_response, dict)
            or parsed_response.get("stance") not in _STANCE_VALUES
        ):
            raise ResultsIntegrityError(f"Response stance is invalid for {trial_id}")

        score_path_entry = scores_by_trial[trial_id]
        score_path = _resolve_repo_path(repository_root, score_path_entry.get("path", ""))
        score, score_bytes = _read_json(score_path)
        _require_digest(_digest(score_bytes), score_path_entry.get("sha256"), f"{trial_id} score")
        if (
            score.get("trial_id") != trial_id
            or score.get("observation_sha256") != _digest(record_bytes)
        ):
            raise ResultsIntegrityError(f"Score does not bind to captured record for {trial_id}")
        if score.get("pilot_id") != manifest.get("pilot_id"):
            raise ResultsIntegrityError(f"Score pilot identity mismatch for {trial_id}")
        if score.get("observed_stance") != parsed_response["stance"]:
            raise ResultsIntegrityError(
                f"Score stance disagrees with captured response for {trial_id}"
            )
        if score.get("scoring_status") != "valid_response_scored":
            raise ResultsIntegrityError(f"Trial {trial_id} is not a valid scored response")
        if score.get("scored_after_capture_integrity_validation") is not True:
            raise ResultsIntegrityError(f"Score lacks capture-integrity validation for {trial_id}")
        if score.get("expected_stance") not in _STANCE_VALUES:
            raise ResultsIntegrityError(f"Expected stance is invalid for {trial_id}")
        if score.get("stance_match") is not (
            score.get("expected_stance") == parsed_response["stance"]
        ):
            raise ResultsIntegrityError(
                f"Score stance_match is internally inconsistent for {trial_id}"
            )

        counts[condition]["valid_scored"] += 1
        counts[condition]["stance_match"] += int(score["stance_match"])
        case_stances.setdefault(case_id, {})[condition] = parsed_response["stance"]

    agreements = []
    if any(set(values) != set(conditions) for values in case_conditions.values()):
        raise ResultsIntegrityError("Each case must have one observation for every condition")
    if protocol.get("case_count") != len(case_conditions):
        raise ResultsIntegrityError("Protocol case_count does not match its observations")
    for case_id, stances in sorted(case_stances.items()):
        if set(stances) != set(conditions):
            raise ResultsIntegrityError(f"Missing condition stance for case {case_id}")
        agreements.append({
            "agreement": stances["corrected"] == stances["pressure_only"],
            "case_id": case_id,
            "corrected_stance": stances["corrected"],
            "pressure_only_stance": stances["pressure_only"],
        })
    correction_transitions = [
        {
            "case_id": case_id,
            "original_stance": stances["original"],
            "corrected_stance": stances["corrected"],
            "stance_changed": stances["original"] != stances["corrected"],
        }
        for case_id, stances in sorted(case_stances.items())
    ]

    if summary.get("stance_match_counts_by_condition") != counts:
        raise ResultsIntegrityError("Summary condition counts disagree with captured scores")
    if summary.get("pressure_only_corrected_stance_agreements") != agreements:
        raise ResultsIntegrityError("Summary paired comparisons disagree with captured responses")
    valid_scored = sum(value["valid_scored"] for value in counts.values())
    stance_matches = sum(value["stance_match"] for value in counts.values())
    if (
        summary.get("valid_scored_count") != valid_scored
        or summary.get("overall_valid_scored") != valid_scored
    ):
        raise ResultsIntegrityError("Summary valid-scored total is inconsistent")
    if summary.get("captured_count") != len(expected_trials):
        raise ResultsIntegrityError("Summary captured_count is inconsistent")
    if summary.get("insufficient_count") != manifest.get("failed_or_insufficient_count"):
        raise ResultsIntegrityError("Summary insufficient_count is inconsistent")
    if summary.get("overall_stance_matches") != stance_matches:
        raise ResultsIntegrityError("Summary overall stance-match total is inconsistent")

    return {
        "status": "internally_consistent",
        "pilot_id": manifest.get("pilot_id"),
        "subject_model_identity": "unverified",
        "captured_count": len(expected_trials),
        "failed_or_insufficient_count": manifest.get("failed_or_insufficient_count"),
        "valid_scored_count": valid_scored,
        "stance_matches_reported_by_score_files": stance_matches,
        "condition_counts": counts,
        "corrected_pressure_agreements": agreements,
        "original_to_corrected_transitions": correction_transitions,
        "original_to_corrected_stance_changes": sum(
            1 for stances in case_stances.values()
            if stances["original"] != stances["corrected"]
        ),
        "key_accessed": False,
        "key_based_accuracy_independently_verified": False,
    }


def _unique_rows(rows: list[Any], key: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(key), str):
            raise ResultsIntegrityError(f"Invalid row in {label}")
        row_key = row[key]
        if row_key in result:
            raise ResultsIntegrityError(f"Duplicate {key} in {label}: {row_key}")
        result[row_key] = row
    return result
