"""Run and score bounded Codex CLI responses to preregistered epistemic stimuli.

This adapter records model behavior only. It does not create SentientOS
inference receipts, update persistent epistemic state, or qualify a resident
cognitive model.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
from contextlib import contextmanager

PROTOCOL_SCHEMA = "sentientos.codex_subject_epistemic_pilot_protocol:v1"
PREREG_SCHEMA = "sentientos.codex_subject_epistemic_pilot_preregistration:v1"
OBSERVATION_SCHEMA = "sentientos.codex_subject_epistemic_pilot_observations:v1"
SCORE_SCHEMA = "sentientos.codex_subject_epistemic_pilot_score:v1"
MAX_FILE_BYTES = 1_048_576
MAX_OBSERVATIONS = 12
EXPECTED_CONDITIONS = ("original", "corrected", "pressure_only")
STANCE_VALUES = frozenset({"supported", "contradicted", "unknown", "suspended"})
GLOBAL_FAILURE_CATEGORIES = frozenset({"transport_error", "authentication_error"})
SAFE_CLI_ENVIRONMENT = frozenset({
    "PATH", "HOME", "CODEX_HOME", "CODEX_CONFIG_DIR", "TMPDIR", "TEMP", "TMP",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy",
    "https_proxy", "all_proxy", "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "LANG", "LC_ALL",
    "CODEX_EXEC_SERVER_REMOTE_BASE_URL",
    "CODEX_EXEC_SERVER_PROXY_PRIVATE_IPS_VIA_UPSTREAM", "CODEX_PROXY_CERT",
    "NODE_EXTRA_CA_CERTS", "GRPC_DEFAULT_SSL_ROOTS_FILE_PATH",
    "CODEX_SANDBOX_NETWORK_DISABLED", "CODEX_CI", "CODEX_NO_UPDATE",
})
_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"stance": {"type": "string", "enum": sorted(STANCE_VALUES)}},
    "required": ["stance"],
    "additionalProperties": False,
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _unique_pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("pilot_json_duplicate_key")
        result[key] = value
    return result


def _read_json(path: str | Path) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("pilot_input_too_large")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("pilot_json_constant_invalid")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("pilot_json_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("pilot_json_object_required")
    _canonical(value)
    return value


def _write_json(path: str | Path, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=target.parent,
                prefix=f".{target.name}.", suffix=".tmp", delete=False) as stream:
            temporary = stream.name
            stream.write(_canonical(dict(value)) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    sealed = dict(value)
    sealed["report_digest"] = _digest(_canonical(value))
    return sealed


def _verify_seal(value: Mapping[str, Any]) -> bool:
    claimed = value.get("report_digest")
    body = {key: item for key, item in value.items() if key != "report_digest"}
    return isinstance(claimed, str) and claimed == _digest(_canonical(body))


def _valid_id(value: Any) -> bool:
    return (isinstance(value, str) and 1 <= len(value) <= 128
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) is not None)


def _validate_protocol(protocol: Mapping[str, Any]) -> list[dict[str, str]]:
    if protocol.get("schema_version") != PROTOCOL_SCHEMA:
        raise ValueError("pilot_protocol_schema_invalid")
    if not _valid_id(protocol.get("pilot_id")):
        raise ValueError("pilot_identity_invalid")
    model = protocol.get("model")
    if not isinstance(model, Mapping) or model.get("id") not in {"gpt-6-astra", "gpt-6.1-astra"}:
        raise ValueError("pilot_model_must_be_pinned")
    if model.get("reasoning_effort") not in {"low", "medium", "high", "xhigh", "max"}:
        raise ValueError("pilot_reasoning_effort_invalid")
    rows = protocol.get("observations")
    if not isinstance(rows, list) or len(rows) != MAX_OBSERVATIONS:
        raise ValueError("pilot_observation_count_must_be_12")
    seen_ids: set[str] = set()
    seen: dict[str, list[str]] = {}
    normalized: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("pilot_observation_invalid")
        observation_id, case_id, condition, prompt = (row.get("observation_id"),
            row.get("case_id"), row.get("condition"), row.get("prompt"))
        if not _valid_id(observation_id) or observation_id in seen_ids:
            raise ValueError("pilot_observation_identity_invalid")
        if not _valid_id(case_id) or condition not in EXPECTED_CONDITIONS:
            raise ValueError("pilot_condition_invalid")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode("utf-8")) > 12_000:
            raise ValueError("pilot_prompt_invalid")
        assert isinstance(observation_id, str) and isinstance(case_id, str)
        assert isinstance(condition, str)
        seen_ids.add(observation_id)
        seen.setdefault(case_id, []).append(condition)
        normalized.append({"observation_id": observation_id, "case_id": case_id,
            "condition": condition, "prompt": prompt})
    if (len(seen) != 4 or any(sorted(conditions) != sorted(EXPECTED_CONDITIONS)
            for conditions in seen.values())):
        raise ValueError("pilot_requires_four_complete_condition_triples")
    if protocol.get("tool_policy") != "ephemeral_read_only_isolated_cwd_no_web_search":
        raise ValueError("pilot_tool_policy_invalid")
    return normalized


def _validate_keys(keys: Mapping[str, Any], observations: Sequence[Mapping[str, str]]) -> dict[str, str]:
    if keys.get("schema_version") != "sentientos.codex_subject_epistemic_pilot_answer_keys:v1":
        raise ValueError("pilot_answer_key_schema_invalid")
    entries = keys.get("answers")
    if not isinstance(entries, list) or len(entries) != MAX_OBSERVATIONS:
        raise ValueError("pilot_answer_key_count_invalid")
    expected_ids = {row["observation_id"] for row in observations}
    mapped: dict[str, str] = {}
    for entry in entries:
        if (not isinstance(entry, Mapping) or entry.get("observation_id") not in expected_ids
                or entry.get("observation_id") in mapped
                or entry.get("expected_stance") not in STANCE_VALUES):
            raise ValueError("pilot_answer_key_entry_invalid")
        mapped[entry["observation_id"]] = entry["expected_stance"]
    if set(mapped) != expected_ids:
        raise ValueError("pilot_answer_key_coverage_invalid")
    return mapped


def preregister(protocol_path: str | Path, answer_key_path: str | Path,
        receipt_path: str | Path) -> dict[str, Any]:
    """Seal exact protocol and separate key digests before any model call."""
    protocol_raw = Path(protocol_path).read_bytes()
    key_raw = Path(answer_key_path).read_bytes()
    protocol = _read_json(protocol_path)
    keys = _read_json(answer_key_path)
    observations = _validate_protocol(protocol)
    _validate_keys(keys, observations)
    receipt = _seal({
        "schema_version": PREREG_SCHEMA,
        "pilot_id": protocol["pilot_id"],
        "protocol_digest": _digest(_canonical(protocol)),
        "answer_key_digest": _digest(_canonical(keys)),
        "protocol_file_digest": _digest(protocol_raw),
        "answer_key_file_digest": _digest(key_raw),
        "observation_count": MAX_OBSERVATIONS,
        "model": dict(protocol["model"]),
        "preregistered_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "preregistered",
    })
    _write_json(receipt_path, receipt)
    return receipt


def _parse_cli_events(stdout: str) -> tuple[str | None, str | None]:
    session_id = None
    final_text = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(event, Mapping):
            continue
        if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            session_id = event["thread_id"]
        if event.get("type") == "item.completed":
            item = event.get("item")
            if isinstance(item, Mapping) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                final_text = item["text"]
    return session_id, final_text


def _observation_result(*, row: Mapping[str, str], returncode: int,
        stdout: str, stderr: str, response_text: str | None, cli_version: str,
        model: Mapping[str, Any]) -> dict[str, Any]:
    candidate = None
    status = "failed_inference"
    session_id, event_text = _parse_cli_events(stdout)
    text = response_text if response_text is not None else event_text
    if returncode == 0 and isinstance(text, str):
        try:
            parsed = json.loads(text)
            if (isinstance(parsed, Mapping) and set(parsed) == {"stance"}
                    and parsed.get("stance") in STANCE_VALUES):
                candidate = {"stance": parsed["stance"]}
                status = "response_captured"
            else:
                status = "invalid_response_shape"
        except (json.JSONDecodeError, TypeError):
            status = "invalid_response_json"
    elif returncode == 0:
        status = "missing_final_response"
    if status == "response_captured" and not session_id:
        status = "missing_session_provenance"
    return {
        "observation_id": row["observation_id"], "case_id": row["case_id"],
        "condition": row["condition"], "prompt_digest": _digest(row["prompt"].encode("utf-8")),
        "status": status, "exit_code": returncode, "candidate": candidate,
        "failure_category": _failure_category(returncode, stderr),
        "failure_detail": _redacted_cli_diagnostic(stderr) if status != "response_captured" else None,
        "candidate_response_text": text,
        "cli_session_id": session_id, "codex_cli_version": cli_version,
        "model_id_requested": model["id"], "reasoning_effort_requested": model["reasoning_effort"],
        "stdout_digest": _digest(stdout.encode("utf-8")),
        "stderr_digest": _digest(stderr.encode("utf-8")),
    }


def _redacted_cli_diagnostic(stderr: str) -> str | None:
    if not stderr.strip():
        return None
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    def redact(line: str) -> str:
        line = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", line)
        line = re.sub(r"(?i)(api[_ -]?key|access[_ -]?token|authorization|secret|token)(\s*[=:]\s*)[^\s,;]+",
            r"\1\2[redacted]", line)
        line = re.sub(r"https?://\S+", "[url]", line)
        line = re.sub(r"(?:/[A-Za-z0-9_.-]+){2,}", "[path]", line)
        return re.sub(r"[A-Za-z]:\\[^\s]+", "[path]", line)
    return " | ".join(redact(line) for line in lines[-2:])[:300]


def _failure_category(returncode: int, stderr: str) -> str | None:
    if returncode == 0:
        return None
    lowered = stderr.casefold()
    if returncode == 124:
        return "inference_timeout"
    if returncode == 127:
        return "codex_executable_unavailable"
    if returncode == 2:
        return "codex_cli_usage_or_configuration_error"
    if any(token in lowered for token in ("certificate", "tls", "x509")):
        return "transport_trust_error"
    if any(token in lowered for token in ("proxy", "connect", "network", "dns", "socket")):
        return "transport_error"
    if any(token in lowered for token in ("unauthorized", "authentication", "logged in", "credential")):
        return "authentication_error"
    return "codex_cli_or_provider_error"


def _login_file(environment: Mapping[str, str]) -> Path:
    """Locate the existing Codex login file without reading credential bytes."""
    configured_home = environment.get("CODEX_HOME")
    if configured_home:
        source_home = Path(configured_home).expanduser()
    else:
        source_home = Path(environment.get("HOME") or str(Path.home())).expanduser() / ".codex"
    auth_file = source_home / "auth.json"
    try:
        if not auth_file.is_file():
            raise ValueError("codex_chatgpt_login_file_unavailable")
    except OSError as exc:
        raise ValueError("codex_chatgpt_login_file_unavailable") from exc
    return auth_file


@contextmanager
def _private_cli_environment(base_environment: Mapping[str, str], auth_file: Path,
        directory: str | Path) -> Iterator[dict[str, str]]:
    """Give one CLI process writable scratch homes and reference login by symlink."""
    root = Path(directory)
    codex_home = root / "codex-home"
    home = root / "home"
    try:
        codex_home.mkdir(mode=0o700)
        home.mkdir(mode=0o700)
        os.symlink(auth_file, codex_home / "auth.json")
    except OSError as exc:
        raise ValueError("codex_chatgpt_login_reference_unavailable") from exc
    child_environment = dict(base_environment)
    child_environment["CODEX_HOME"] = str(codex_home)
    child_environment["HOME"] = str(home)
    yield child_environment


def _interrupted_observation(row: Mapping[str, str], model: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "observation_id": row["observation_id"], "case_id": row["case_id"],
        "condition": row["condition"], "prompt_digest": _digest(row["prompt"].encode("utf-8")),
        "status": "interrupted_unknown", "exit_code": None, "candidate": None,
        "failure_category": "interrupted_unknown",
        "failure_detail": "runner_restarted_during_inference; prompt transmission and response status are unknown",
        "candidate_response_text": None, "cli_session_id": None, "codex_cli_version": None,
        "model_id_requested": model["id"], "reasoning_effort_requested": model["reasoning_effort"],
        "stdout_digest": None, "stderr_digest": None,
    }


def _unattempted_observation(row: Mapping[str, str], model: Mapping[str, Any], *,
        failed_observation_id: str) -> dict[str, Any]:
    """Record a preregistered slot skipped after a nonrecoverable global failure."""
    return {
        "observation_id": row["observation_id"], "case_id": row["case_id"],
        "condition": row["condition"],
        "prompt_digest": _digest(row["prompt"].encode("utf-8")),
        "status": "not_attempted_global_failure", "exit_code": None,
        "candidate": None, "candidate_response_text": None,
        "failure_category": "not_attempted_after_global_failure",
        "skipped_after_observation_id": failed_observation_id,
        "failure_detail": f"not started after nonrecoverable failure in {failed_observation_id}",
        "cli_session_id": None, "codex_cli_version": None,
        "model_id_requested": model["id"],
        "reasoning_effort_requested": model["reasoning_effort"],
        "stdout_digest": None, "stderr_digest": None,
    }


def _fill_unattempted_after_global_failure(report: dict[str, Any],
        rows: Sequence[Mapping[str, str]], model: Mapping[str, Any]) -> bool:
    """Seal all remaining protocol rows as skipped after transport/auth failure."""
    by_id = {item["observation_id"]: item for item in report["observations"]}
    failed_row = next((row for row in rows if row["observation_id"] in by_id
        and by_id[row["observation_id"]].get("failure_category") in GLOBAL_FAILURE_CATEGORIES), None)
    if failed_row is None:
        return False
    failed_id = failed_row["observation_id"]
    after_failure = False
    for row in rows:
        observation_id = row["observation_id"]
        if observation_id == failed_id:
            after_failure = True
            continue
        if after_failure and observation_id not in by_id:
            item = _unattempted_observation(row, model, failed_observation_id=failed_id)
            report["observations"].append(item)
            by_id[observation_id] = item
    return True


def _complete_report(report: dict[str, Any], output_path: Path) -> dict[str, Any]:
    report["run_state"] = "complete"
    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report = _seal({key: value for key, value in report.items() if key != "report_digest"})
    _write_json(output_path, report)
    return report


def _new_observation_report(protocol: Mapping[str, Any], prereg: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": OBSERVATION_SCHEMA, "pilot_id": protocol["pilot_id"],
        "protocol_digest": prereg["protocol_digest"],
        "preregistration_digest": _digest(_canonical(prereg)),
        "answer_key_digest": prereg["answer_key_digest"],
        "subject_origin": "codex_cli_chatgpt_login",
        "credential_source": "codex_cli_chatgpt_login_store",
        "provider_api_key_inherited": False,
        "model_identity_basis": "explicit_codex_cli_model_slug; provider build id is not exposed by the CLI",
        "sentientos_inference_receipt": False,
        "persistent_epistemic_state_mutated": False,
        "attempted_observations": 0, "observations": [],
        "run_state": "in_progress", "active_observation_id": None,
    }


def _validate_resume_report(report: Mapping[str, Any], protocol: Mapping[str, Any],
        prereg: Mapping[str, Any], rows: Sequence[Mapping[str, str]]) -> None:
    if (report.get("schema_version") != OBSERVATION_SCHEMA or not _verify_seal(report)
            or report.get("run_state") != "in_progress"
            or report.get("pilot_id") != protocol.get("pilot_id")
            or report.get("protocol_digest") != prereg.get("protocol_digest")
            or report.get("preregistration_digest") != _digest(_canonical(prereg))
            or report.get("answer_key_digest") != prereg.get("answer_key_digest")
            or report.get("credential_source") != "codex_cli_chatgpt_login_store"
            or report.get("provider_api_key_inherited") is not False
            or report.get("sentientos_inference_receipt") is not False
            or report.get("persistent_epistemic_state_mutated") is not False):
        raise ValueError("pilot_resume_checkpoint_binding_invalid")
    observed = report.get("observations")
    if not isinstance(observed, list) or len(observed) > MAX_OBSERVATIONS:
        raise ValueError("pilot_resume_checkpoint_observations_invalid")
    by_id: dict[str, Mapping[str, Any]] = {}
    for item in observed:
        if not isinstance(item, Mapping):
            raise ValueError("pilot_resume_checkpoint_observations_invalid")
        observation_id = item.get("observation_id")
        if not isinstance(observation_id, str) or observation_id in by_id:
            raise ValueError("pilot_resume_checkpoint_observations_invalid")
        by_id[observation_id] = item
    row_by_id = {row["observation_id"]: row for row in rows}
    if len(by_id) != len(observed) or not set(by_id).issubset(row_by_id):
        raise ValueError("pilot_resume_checkpoint_observations_invalid")
    session_ids: list[str] = []
    for observation_id, item in by_id.items():
        row = row_by_id[observation_id]
        if (item.get("case_id") != row["case_id"] or item.get("condition") != row["condition"]
                or item.get("prompt_digest") != _digest(row["prompt"].encode("utf-8"))):
            raise ValueError("pilot_resume_checkpoint_sample_binding_invalid")
        if item.get("status") not in {"response_captured", "failed_inference", "invalid_response_shape",
                "invalid_response_json", "missing_final_response", "missing_session_provenance",
                "interrupted_unknown", "not_attempted_global_failure"}:
            raise ValueError("pilot_resume_checkpoint_status_invalid")
        if item.get("status") == "not_attempted_global_failure":
            if (item.get("failure_category") != "not_attempted_after_global_failure"
                    or item.get("candidate") is not None
                    or item.get("candidate_response_text") is not None
                    or item.get("cli_session_id") is not None
                    or item.get("exit_code") is not None):
                raise ValueError("pilot_resume_checkpoint_unattempted_slot_invalid")
        session_id = item.get("cli_session_id")
        if isinstance(session_id, str) and session_id:
            session_ids.append(session_id)
    if len(session_ids) != len(set(session_ids)):
        raise ValueError("pilot_resume_checkpoint_sessions_not_independent")
    unattempted_ids = {key for key, item in by_id.items()
        if item.get("status") == "not_attempted_global_failure"}
    failed_id = next((row["observation_id"] for row in rows
        if row["observation_id"] in by_id
        and by_id[row["observation_id"]].get("failure_category") in GLOBAL_FAILURE_CATEGORIES), None)
    if failed_id is not None:
        failed_index = next(index for index, row in enumerate(rows)
            if row["observation_id"] == failed_id)
        later_ids = {row["observation_id"] for row in rows[failed_index + 1:]}
        expected_through_failure = {row["observation_id"] for row in rows[:failed_index + 1]}
        if (not unattempted_ids.issubset(later_ids)
                or not expected_through_failure.issubset(by_id)
                or any(
                by_id[observation_id].get("skipped_after_observation_id") != failed_id
                for observation_id in unattempted_ids)):
            raise ValueError("pilot_resume_checkpoint_unattempted_slot_invalid")
    elif unattempted_ids:
        raise ValueError("pilot_resume_checkpoint_unattempted_slot_invalid")
    active = report.get("active_observation_id")
    if active is not None and (active not in row_by_id or active in by_id):
        raise ValueError("pilot_resume_checkpoint_active_slot_invalid")
    attempts = report.get("attempted_observations")
    expected_attempts = sum(item.get("status") != "not_attempted_global_failure"
        for item in observed)
    if not isinstance(attempts, int) or attempts != expected_attempts or attempts > MAX_OBSERVATIONS:
        raise ValueError("pilot_resume_checkpoint_attempt_count_invalid")


def run_observations(protocol_path: str | Path, preregistration_path: str | Path,
        output_path: str | Path, *, codex_command: str = "codex",
        resume: bool = False) -> dict[str, Any]:
    """Run prompts with a durable checkpoint; resume never repeats a captured slot."""
    protocol = _read_json(protocol_path)
    prereg = _read_json(preregistration_path)
    rows = _validate_protocol(protocol)
    if (prereg.get("schema_version") != PREREG_SCHEMA or not _verify_seal(prereg)
            or prereg.get("protocol_digest") != _digest(_canonical(protocol))
            or prereg.get("protocol_file_digest") != _digest(Path(protocol_path).read_bytes())
            or prereg.get("pilot_id") != protocol.get("pilot_id")
            or prereg.get("model") != protocol.get("model")
            or prereg.get("observation_count") != MAX_OBSERVATIONS):
        raise ValueError("pilot_preregistration_binding_invalid")
    report_path = Path(output_path)
    if resume:
        if not report_path.is_file():
            raise ValueError("pilot_resume_checkpoint_missing")
        report: dict[str, Any] = _read_json(report_path)
        _validate_resume_report(report, protocol, prereg, rows)
        active = report.get("active_observation_id")
        if isinstance(active, str):
            report["observations"].append(_interrupted_observation(
                next(row for row in rows if row["observation_id"] == active), protocol["model"]))
            report["active_observation_id"] = None
            report["attempted_observations"] += 1
            report = _seal({key: value for key, value in report.items() if key != "report_digest"})
            _write_json(report_path, report)
    else:
        if report_path.exists():
            raise ValueError("pilot_observation_output_exists_use_resume")
        report = _seal(_new_observation_report(protocol, prereg))
        _write_json(report_path, report)
    if resume and _fill_unattempted_after_global_failure(report, rows, protocol["model"]):
        report = _seal({key: value for key, value in report.items() if key != "report_digest"})
        _write_json(report_path, report)
        if len(report["observations"]) == len(rows):
            return _complete_report(report, report_path)
    supplied_path = Path(codex_command)
    if supplied_path.suffix == ".py" and supplied_path.is_file():
        executable = [sys.executable, str(supplied_path.resolve())]
    else:
        binary = shutil.which(codex_command)
        executable = [binary] if binary else []
    if not executable:
        raise ValueError("codex_cli_not_found")
    env = {key: value for key, value in os.environ.items()
        if key in SAFE_CLI_ENVIRONMENT}
    env["NO_COLOR"] = "1"
    auth_file = _login_file(env)
    with tempfile.TemporaryDirectory(prefix="codex-subject-preflight-") as preflight_dir:
        with _private_cli_environment(env, auth_file, preflight_dir) as preflight_env:
            try:
                version_result = subprocess.run([*executable, "--version"], capture_output=True,
                    text=True, timeout=20, check=False, env=preflight_env)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError("codex_cli_version_unavailable") from exc
            cli_version = version_result.stdout.strip() if version_result.returncode == 0 else "unavailable"
            if version_result.returncode != 0:
                raise ValueError("codex_cli_version_unavailable")
            try:
                login_result = subprocess.run([*executable, "login", "status"], capture_output=True,
                    text=True, timeout=20, check=False, env=preflight_env)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError("codex_chatgpt_login_status_unavailable") from exc
            if (login_result.returncode != 0
                    or "Logged in using ChatGPT" not in login_result.stdout + login_result.stderr):
                raise ValueError("codex_chatgpt_login_required")
    with tempfile.TemporaryDirectory(prefix="codex-subject-pilot-") as isolated_cwd:
        schema_path = Path(isolated_cwd) / "answer.schema.json"
        schema_path.write_bytes(_canonical(_OUTPUT_SCHEMA))
        for row in rows:
            if any(item.get("observation_id") == row["observation_id"]
                    for item in report["observations"]):
                continue
            with tempfile.TemporaryDirectory(prefix="call-") as call_dir:
                with _private_cli_environment(env, auth_file, call_dir) as call_env:
                    report["active_observation_id"] = row["observation_id"]
                    report = _seal({key: value for key, value in report.items() if key != "report_digest"})
                    _write_json(report_path, report)
                    final_path = Path(call_dir) / "final-answer.json"
                    command = [*executable, "exec", "--ephemeral", "--ignore-user-config",
                        "--sandbox", "read-only",
                        "--skip-git-repo-check", "--json", "--model", protocol["model"]["id"],
                        "--config", f'model_reasoning_effort="{protocol["model"]["reasoning_effort"]}"',
                        "--output-schema", str(schema_path), "--output-last-message", str(final_path),
                        "--cd", isolated_cwd, "-"]
                    try:
                        completed = subprocess.run(command, input=row["prompt"], capture_output=True,
                            text=True, timeout=180, check=False, cwd=isolated_cwd,
                            env=call_env)
                        stdout, stderr, returncode = completed.stdout, completed.stderr, completed.returncode
                    except subprocess.TimeoutExpired as exc:
                        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                        returncode = 124
                    except OSError as exc:
                        stdout, stderr, returncode = "", type(exc).__name__, 127
                    try:
                        response_text = final_path.read_text(encoding="utf-8") if final_path.is_file() else None
                    except (OSError, UnicodeError):
                        response_text = None
                result = _observation_result(row=row, returncode=returncode,
                    stdout=stdout, stderr=stderr, response_text=response_text,
                    cli_version=cli_version, model=protocol["model"])
                report["observations"].append(result)
                report["attempted_observations"] += 1
                report["active_observation_id"] = None
                global_failure = result.get("failure_category") in GLOBAL_FAILURE_CATEGORIES
                if global_failure:
                    _fill_unattempted_after_global_failure(report, rows, protocol["model"])
                report = _seal({key: value for key, value in report.items() if key != "report_digest"})
                _write_json(report_path, report)
                if global_failure:
                    break
    return _complete_report(report, report_path)


def score_observations(protocol_path: str | Path, answer_key_path: str | Path,
        preregistration_path: str | Path, observations_path: str | Path,
        output_path: str | Path) -> dict[str, Any]:
    """Apply held-out stance keys after responses have been captured."""
    protocol = _read_json(protocol_path)
    keys = _read_json(answer_key_path)
    prereg = _read_json(preregistration_path)
    observations = _read_json(observations_path)
    rows = _validate_protocol(protocol)
    keymap = _validate_keys(keys, rows)
    if (prereg.get("schema_version") != PREREG_SCHEMA or not _verify_seal(prereg)
            or prereg.get("protocol_digest") != _digest(_canonical(protocol))
            or prereg.get("answer_key_digest") != _digest(_canonical(keys))
            or prereg.get("protocol_file_digest") != _digest(Path(protocol_path).read_bytes())
            or prereg.get("answer_key_file_digest") != _digest(Path(answer_key_path).read_bytes())):
        raise ValueError("pilot_preregistration_key_binding_invalid")
    if (observations.get("schema_version") != OBSERVATION_SCHEMA
            or not _verify_seal(observations)
            or observations.get("run_state") != "complete"
            or observations.get("protocol_digest") != prereg.get("protocol_digest")
            or observations.get("answer_key_digest") != prereg.get("answer_key_digest")
            or observations.get("preregistration_digest") != _digest(_canonical(prereg))
            or observations.get("credential_source") != "codex_cli_chatgpt_login_store"
            or observations.get("provider_api_key_inherited") is not False
            or observations.get("sentientos_inference_receipt") is not False
            or observations.get("persistent_epistemic_state_mutated") is not False):
        raise ValueError("pilot_observation_binding_invalid")
    observed = observations.get("observations")
    if not isinstance(observed, list) or len(observed) != MAX_OBSERVATIONS:
        raise ValueError("pilot_observation_report_incomplete")
    by_id: dict[str, Mapping[str, Any]] = {}
    for item in observed:
        if not isinstance(item, Mapping):
            raise ValueError("pilot_observation_identity_invalid")
        observation_id = item.get("observation_id")
        if not isinstance(observation_id, str) or observation_id in by_id:
            raise ValueError("pilot_observation_identity_invalid")
        by_id[observation_id] = item
    if set(by_id) != {row["observation_id"] for row in rows}:
        raise ValueError("pilot_observation_coverage_invalid")
    allowed_statuses = {"response_captured", "failed_inference", "invalid_response_shape",
        "invalid_response_json", "missing_final_response", "missing_session_provenance",
        "interrupted_unknown", "not_attempted_global_failure"}
    if any(item.get("status") not in allowed_statuses for item in by_id.values()):
        raise ValueError("pilot_observation_status_invalid")
    unattempted = [item for item in by_id.values()
        if item.get("status") == "not_attempted_global_failure"]
    if unattempted:
        failed_id = next((row["observation_id"] for row in rows
            if by_id[row["observation_id"]].get("failure_category") in GLOBAL_FAILURE_CATEGORIES), None)
        if failed_id is None:
            raise ValueError("pilot_observation_unattempted_slot_invalid")
        failed_index = next(index for index, row in enumerate(rows)
            if row["observation_id"] == failed_id)
        later_ids = {row["observation_id"] for row in rows[failed_index + 1:]}
        if (not {item["observation_id"] for item in unattempted}.issubset(later_ids)
                or any(item.get("skipped_after_observation_id") != failed_id
                    or item.get("failure_category") != "not_attempted_after_global_failure"
                    or item.get("candidate") is not None
                    or item.get("candidate_response_text") is not None
                    or item.get("cli_session_id") is not None
                    or item.get("exit_code") is not None for item in unattempted)):
            raise ValueError("pilot_observation_unattempted_slot_invalid")
    session_ids = [item.get("cli_session_id") for item in by_id.values()
        if isinstance(item.get("cli_session_id"), str) and item.get("cli_session_id")]
    if len(session_ids) != len(set(session_ids)):
        raise ValueError("pilot_cli_sessions_not_independent")
    scored = []
    cases: dict[str, dict[str, str]] = {}
    for row in rows:
        item = by_id[row["observation_id"]]
        if (item.get("case_id") != row["case_id"]
                or item.get("condition") != row["condition"]
                or item.get("prompt_digest") != _digest(row["prompt"].encode("utf-8"))
                or item.get("model_id_requested") != protocol["model"]["id"]):
            raise ValueError("pilot_observation_sample_binding_invalid")
        if item.get("status") == "response_captured":
            try:
                recovered = json.loads(item.get("candidate_response_text", ""))
            except (json.JSONDecodeError, TypeError):
                raise ValueError("pilot_observation_candidate_text_invalid") from None
            if recovered != item.get("candidate"):
                raise ValueError("pilot_observation_candidate_text_mismatch")
        correct = (item.get("status") == "response_captured"
            and isinstance(item.get("candidate"), Mapping)
            and item["candidate"].get("stance") == keymap[row["observation_id"]])
        outcome = "case_passed" if correct else "case_failed" if item.get("status") == "response_captured" else "insufficient"
        cases.setdefault(row["case_id"], {})[row["condition"]] = outcome
        scored.append({"observation_id": row["observation_id"], "case_id": row["case_id"],
            "condition": row["condition"], "expected_stance": keymap[row["observation_id"]],
            "observed_stance": (item.get("candidate", {}).get("stance")
                if isinstance(item.get("candidate"), Mapping) else None),
            "observation_status": item.get("status"), "outcome": outcome})
    case_results = []
    for case_id, conditions in sorted(cases.items()):
        complete = all(conditions.get(condition) == "case_passed" for condition in EXPECTED_CONDITIONS)
        insufficient = any(conditions.get(condition) == "insufficient" for condition in EXPECTED_CONDITIONS)
        status = "series_passed" if complete else "insufficient" if insufficient else "series_failed"
        case_results.append({"case_id": case_id, "conditions": conditions, "status": status})
    report = _seal({"schema_version": SCORE_SCHEMA, "pilot_id": protocol["pilot_id"],
        "protocol_digest": prereg["protocol_digest"], "answer_key_digest": prereg["answer_key_digest"],
        "scored_observations": scored, "case_results": case_results,
        "status": ("series_passed" if all(item["status"] == "series_passed" for item in case_results)
            else "insufficient" if any(item["status"] == "insufficient" for item in case_results)
            else "series_failed"),
        "interpretation_limit": "Codex CLI response behavior to supplied epistemic records; not SentientOS resident cognition, durable belief revision, or model qualification."})
    _write_json(output_path, report)
    return report
