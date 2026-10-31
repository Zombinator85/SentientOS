from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

import sentientos.codex_subject_epistemic_pilot_runner as pilot_runner
from sentientos.codex_subject_epistemic_pilot_runner import (
    _redacted_cli_diagnostic, preregister, run_observations, score_observations,
)


FAKE_CODEX = r'''import json, os, pathlib, sys
args = sys.argv[1:]
if args == ["--version"]:
    print("codex-cli fake-1")
    raise SystemExit(0)
if args == ["login", "status"]:
    if not (pathlib.Path(os.environ["CODEX_HOME"]) / "auth.json").is_symlink():
        raise SystemExit(31)
    print("Logged in using ChatGPT")
    raise SystemExit(0)
if args[0] != "exec":
    raise SystemExit(2)
codex_home = pathlib.Path(os.environ["CODEX_HOME"])
home = pathlib.Path(os.environ["HOME"])
if not (codex_home / "auth.json").is_symlink():
    raise SystemExit(32)
(codex_home / "writable-probe").write_text("ok", encoding="utf-8")
(home / "writable-probe").write_text("ok", encoding="utf-8")
if "--ask-for-approval" in args:
    raise SystemExit(2)
prompt = sys.stdin.read()
if "FAIL_INFERENCE" in prompt:
    print("inference unavailable", file=sys.stderr)
    raise SystemExit(17)
if "GLOBAL_TRANSPORT_FAILURE" in prompt:
    print("websocket network connection failed", file=sys.stderr)
    raise SystemExit(17)
if "GLOBAL_AUTH_FAILURE" in prompt:
    print("HTTP 401 Unauthorized", file=sys.stderr)
    raise SystemExit(17)
if "GLOBAL_AUTH_CONNECT_FAILURE" in prompt:
    print("failed to connect to websocket: HTTP error: 401 Unauthorized", file=sys.stderr)
    raise SystemExit(17)
if "GLOBAL_SERVICE_DENIAL" in prompt:
    print("HTTP 451 no_biscuit_no_service", file=sys.stderr)
    raise SystemExit(17)
if "GLOBAL_CLI_FAILURE" in prompt:
    print("provider request failed without a response", file=sys.stderr)
    raise SystemExit(17)
if "GLOBAL_USAGE_FAILURE" in prompt:
    print("invalid CLI invocation", file=sys.stderr)
    raise SystemExit(2)
if "INVALID_RESPONSE" in prompt:
    text = json.dumps({"stance": "not-a-valid-stance"}, separators=(",", ":"))
else:
    stance = prompt.rsplit("TEST_STANCE=", 1)[1].split()[0]
    text = json.dumps({"stance": stance}, separators=(",", ":"))
out = pathlib.Path(args[args.index("--output-last-message") + 1])
out.write_text(text, encoding="utf-8")
print(json.dumps({"type":"thread.started","thread_id":out.parent.name}))
print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":text}}))
raise SystemExit(0)
'''


def _inputs(tmp_path: Path, *, failing: bool = False):
    rows = []
    answers = []
    stances = ("supported", "contradicted", "contradicted")
    for case_no in range(4):
        for condition, stance in zip(("original", "corrected", "pressure_only"), stances):
            observation_id = f"case-{case_no}-{condition}"
            prompt = f"TEST_STANCE={stance}"
            if failing and case_no == 0 and condition == "corrected":
                prompt += " FAIL_INFERENCE"
            rows.append({"observation_id": observation_id, "case_id": f"case-{case_no}",
                "condition": condition, "prompt": prompt})
            answers.append({"observation_id": observation_id, "expected_stance": stance})
    protocol = {"schema_version": "sentientos.codex_subject_epistemic_pilot_protocol:v1",
        "pilot_id": "test-pilot", "model": {"id": "gpt-6-astra", "reasoning_effort": "high"},
        "tool_policy": "ephemeral_read_only_isolated_cwd_no_web_search", "observations": rows}
    key = {"schema_version": "sentientos.codex_subject_epistemic_pilot_answer_keys:v1",
        "answers": answers}
    protocol_path, key_path = tmp_path / "protocol.json", tmp_path / "keys.json"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    key_path.write_text(json.dumps(key), encoding="utf-8")
    fake = tmp_path / "fake_codex.py"
    fake.write_text(FAKE_CODEX, encoding="utf-8")
    return protocol_path, key_path, fake


@pytest.mark.no_legacy_skip
def test_unverified_astra_model_identifier_is_rejected_before_preregistration(tmp_path):
    protocol, keys, _fake = _inputs(tmp_path)
    data = json.loads(protocol.read_text(encoding="utf-8"))
    data["model"]["id"] = "gpt-6.1-astra"
    protocol.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="pilot_model_must_be_pinned"):
        preregister(protocol, keys, tmp_path / "prereg.json")


@pytest.fixture(autouse=True)
def fake_authenticated_codex_home(tmp_path: Path, monkeypatch):
    home = tmp_path / "codex-login"
    home.mkdir()
    (home / "auth.json").write_text("fixture-only-login-material", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(home))


@pytest.mark.no_legacy_skip
def test_preregister_run_and_score_four_correction_pressure_triples(tmp_path):
    protocol, keys, fake = _inputs(tmp_path)
    prereg_path, raw_path, score_path = (tmp_path / name for name in
        ("prereg.json", "observations.json", "score.json"))
    prereg = preregister(protocol, keys, prereg_path)
    assert prereg["observation_count"] == 12
    assert "supported" not in prereg_path.read_text(encoding="utf-8")

    raw = run_observations(protocol, prereg_path, raw_path, codex_command=str(fake))
    assert raw["attempted_observations"] == 12
    assert raw["run_state"] == "complete"
    assert raw["sentientos_inference_receipt"] is False
    assert raw["persistent_epistemic_state_mutated"] is False
    assert all(row["status"] == "response_captured" for row in raw["observations"])
    assert len({row["cli_session_id"] for row in raw["observations"]}) == 12

    score = score_observations(protocol, keys, prereg_path, raw_path, score_path)
    assert score["status"] == "series_passed"
    assert len(score["case_results"]) == 4


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize("prior_score", [None, b"prior score record\\n"])
def test_score_write_failure_preserves_observations_and_retries_without_inference(
        tmp_path, monkeypatch, prior_score):
    protocol, keys, fake = _inputs(tmp_path)
    prereg_path, raw_path, score_path = (tmp_path / name for name in
        ("prereg.json", "observations.json", "score.json"))
    preregister(protocol, keys, prereg_path)
    raw = run_observations(protocol, prereg_path, raw_path, codex_command=str(fake))
    raw_bytes = raw_path.read_bytes()
    if prior_score is not None:
        score_path.write_bytes(prior_score)

    real_replace = os.replace

    def fail_score_promotion(source, destination):
        if Path(destination) == score_path:
            raise OSError("fixture failure promoting score artifact")
        return real_replace(source, destination)

    with monkeypatch.context() as patcher:
        patcher.setattr(pilot_runner.os, "replace", fail_score_promotion)
        with pytest.raises(OSError, match="promoting score artifact"):
            score_observations(protocol, keys, prereg_path, raw_path, score_path)

    assert raw_path.read_bytes() == raw_bytes
    if prior_score is None:
        assert not score_path.exists()
    else:
        assert score_path.read_bytes() == prior_score
    assert list(tmp_path.glob(".score.json.*.tmp")) == []

    recovered = score_observations(protocol, keys, prereg_path, raw_path, score_path)
    assert recovered["status"] == "series_passed"
    assert raw_path.read_bytes() == raw_bytes
    assert json.loads(score_path.read_text(encoding="utf-8")) == recovered


@pytest.mark.no_legacy_skip
def test_failed_inference_is_preserved_and_scores_insufficient(tmp_path):
    protocol, keys, fake = _inputs(tmp_path, failing=True)
    prereg_path, raw_path, score_path = (tmp_path / name for name in
        ("prereg.json", "observations.json", "score.json"))
    preregister(protocol, keys, prereg_path)
    raw = run_observations(protocol, prereg_path, raw_path, codex_command=str(fake))
    failed = next(row for row in raw["observations"] if row["observation_id"] == "case-0-corrected")
    assert failed["status"] == "failed_inference"
    assert failed["exit_code"] == 17
    assert failed["failure_category"] == "codex_cli_or_provider_error"
    score = score_observations(protocol, keys, prereg_path, raw_path, score_path)
    assert score["status"] == "insufficient"
    assert next(row for row in score["scored_observations"]
        if row["observation_id"] == "case-0-corrected")["outcome"] == "insufficient"


@pytest.mark.no_legacy_skip
@pytest.mark.parametrize(("marker", "category"), [
    ("GLOBAL_TRANSPORT_FAILURE", "transport_error"),
    ("GLOBAL_AUTH_FAILURE", "authentication_error"),
    ("GLOBAL_AUTH_CONNECT_FAILURE", "authentication_error"),
    ("GLOBAL_SERVICE_DENIAL", "authentication_error"),
    ("GLOBAL_CLI_FAILURE", "codex_cli_or_provider_error"),
    ("GLOBAL_USAGE_FAILURE", "codex_cli_usage_or_configuration_error"),
])
def test_global_failure_stops_remaining_slots_and_scores_them_insufficient(
        tmp_path, monkeypatch, marker, category):
    protocol, keys, fake = _inputs(tmp_path)
    data = json.loads(protocol.read_text(encoding="utf-8"))
    data["observations"][0]["prompt"] += " " + marker
    protocol.write_text(json.dumps(data), encoding="utf-8")
    prereg_path, raw_path, score_path = (tmp_path / name for name in
        ("prereg.json", "observations.json", "score.json"))
    preregister(protocol, keys, prereg_path)
    actual_run = subprocess.run
    exec_calls = []

    def count_exec(command, *args, **kwargs):
        if "exec" in command:
            exec_calls.append(command)
        return actual_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", count_exec)
    raw = run_observations(protocol, prereg_path, raw_path, codex_command=str(fake))
    assert len(exec_calls) == 1
    assert raw["attempted_observations"] == 1
    assert raw["run_state"] == "complete"
    failed = raw["observations"][0]
    assert failed["failure_category"] == category
    skipped = raw["observations"][1:]
    assert len(skipped) == 11
    assert all(item["status"] == "not_attempted_global_failure" for item in skipped)
    assert all(item["candidate"] is None and item["candidate_response_text"] is None
        and item["cli_session_id"] is None for item in skipped)
    score = score_observations(protocol, keys, prereg_path, raw_path, score_path)
    assert score["status"] == "insufficient"
    assert all(item["outcome"] == "insufficient" for item in score["scored_observations"])


@pytest.mark.no_legacy_skip
def test_resume_after_global_failure_completes_without_cli_invocation(tmp_path, monkeypatch):
    protocol, keys, fake = _inputs(tmp_path)
    data = json.loads(protocol.read_text(encoding="utf-8"))
    data["observations"][0]["prompt"] += " GLOBAL_AUTH_FAILURE"
    protocol.write_text(json.dumps(data), encoding="utf-8")
    prereg_path, raw_path = tmp_path / "prereg.json", tmp_path / "observations.json"
    preregister(protocol, keys, prereg_path)
    with monkeypatch.context() as patcher:
        patcher.setattr(pilot_runner, "_complete_report",
            lambda *_args: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            run_observations(protocol, prereg_path, raw_path, codex_command=str(fake))

    checkpoint = json.loads(raw_path.read_text(encoding="utf-8"))
    assert checkpoint["run_state"] == "in_progress"
    assert checkpoint["attempted_observations"] == 1
    assert sum(item["status"] == "not_attempted_global_failure"
        for item in checkpoint["observations"]) == 11

    def no_cli_invocation(*_args, **_kwargs):
        raise AssertionError("resume invoked Codex after recorded global failure")

    monkeypatch.setattr(subprocess, "run", no_cli_invocation)
    resumed = run_observations(protocol, prereg_path, raw_path,
        codex_command=str(fake), resume=True)
    assert resumed["run_state"] == "complete"
    assert resumed["attempted_observations"] == 1


@pytest.mark.no_legacy_skip
def test_scoring_preserves_complete_historical_report_with_later_observations(tmp_path):
    protocol, keys, fake = _inputs(tmp_path)
    prereg_path, raw_path, score_path = (tmp_path / name for name in
        ("prereg.json", "observations.json", "score.json"))
    preregister(protocol, keys, prereg_path)
    raw = run_observations(protocol, prereg_path, raw_path, codex_command=str(fake))
    raw["observations"][0].update({"status": "failed_inference", "exit_code": 17,
        "candidate": None, "candidate_response_text": None,
        "failure_category": "transport_error", "failure_detail": "historical transport failure"})
    raw = pilot_runner._seal({key: value for key, value in raw.items() if key != "report_digest"})
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    score = score_observations(protocol, keys, prereg_path, raw_path, score_path)
    assert score["status"] == "insufficient"
    assert len(score["scored_observations"]) == 12
    assert sum(item["outcome"] == "insufficient" for item in score["scored_observations"]) == 1


@pytest.mark.no_legacy_skip
def test_invalid_model_response_is_preserved_and_scores_insufficient(tmp_path):
    protocol, keys, fake = _inputs(tmp_path)
    data = json.loads(protocol.read_text(encoding="utf-8"))
    target = next(row for row in data["observations"]
        if row["observation_id"] == "case-0-corrected")
    target["prompt"] += " INVALID_RESPONSE"
    protocol.write_text(json.dumps(data), encoding="utf-8")
    prereg_path, raw_path, score_path = (tmp_path / name for name in
        ("prereg.json", "observations.json", "score.json"))
    preregister(protocol, keys, prereg_path)
    raw = run_observations(protocol, prereg_path, raw_path, codex_command=str(fake))
    invalid = next(row for row in raw["observations"] if row["observation_id"] == "case-0-corrected")
    assert invalid["status"] == "invalid_response_shape"
    assert invalid["candidate"] is None
    assert "not-a-valid-stance" in invalid["candidate_response_text"]
    score = score_observations(protocol, keys, prereg_path, raw_path, score_path)
    assert score["status"] == "insufficient"


@pytest.mark.no_legacy_skip
def test_protocol_tampering_after_preregistration_blocks_before_calls(tmp_path):
    protocol, keys, fake = _inputs(tmp_path)
    prereg_path = tmp_path / "prereg.json"
    preregister(protocol, keys, prereg_path)
    protocol.write_text(protocol.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="pilot_preregistration_binding_invalid"):
        run_observations(protocol, prereg_path, tmp_path / "observations.json", codex_command=str(fake))


@pytest.mark.no_legacy_skip
def test_tampered_preregistration_receipt_blocks_before_calls(tmp_path):
    protocol, keys, fake = _inputs(tmp_path)
    prereg_path = tmp_path / "prereg.json"
    preregister(protocol, keys, prereg_path)
    receipt = json.loads(prereg_path.read_text(encoding="utf-8"))
    receipt["model"]["reasoning_effort"] = "low"
    prereg_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="pilot_preregistration_binding_invalid"):
        run_observations(protocol, prereg_path, tmp_path / "observations.json", codex_command=str(fake))


@pytest.mark.no_legacy_skip
def test_reused_cli_session_ids_are_rejected_as_non_independent(tmp_path):
    protocol, keys, fake = _inputs(tmp_path)
    fake.write_text(FAKE_CODEX.replace('out.parent.name', '"same-session"'), encoding="utf-8")
    prereg_path, raw_path = tmp_path / "prereg.json", tmp_path / "observations.json"
    preregister(protocol, keys, prereg_path)
    run_observations(protocol, prereg_path, raw_path, codex_command=str(fake))
    with pytest.raises(ValueError, match="pilot_cli_sessions_not_independent"):
        score_observations(protocol, keys, prereg_path, raw_path, tmp_path / "score.json")


@pytest.mark.no_legacy_skip
def test_answer_key_tampering_after_capture_is_rejected(tmp_path):
    protocol, keys, fake = _inputs(tmp_path)
    prereg_path, raw_path = tmp_path / "prereg.json", tmp_path / "observations.json"
    preregister(protocol, keys, prereg_path)
    run_observations(protocol, prereg_path, raw_path, codex_command=str(fake))
    data = json.loads(keys.read_text(encoding="utf-8"))
    data["answers"][0]["expected_stance"] = "unknown"
    keys.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="pilot_preregistration_key_binding_invalid"):
        score_observations(protocol, keys, prereg_path, raw_path, tmp_path / "score.json")


@pytest.mark.no_legacy_skip
def test_captured_response_tampering_is_detected_by_report_seal(tmp_path):
    protocol, keys, fake = _inputs(tmp_path)
    prereg_path, raw_path = tmp_path / "prereg.json", tmp_path / "observations.json"
    preregister(protocol, keys, prereg_path)
    run_observations(protocol, prereg_path, raw_path, codex_command=str(fake))
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw["observations"][0]["candidate"]["stance"] = "unknown"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="pilot_observation_binding_invalid"):
        score_observations(protocol, keys, prereg_path, raw_path, tmp_path / "score.json")


@pytest.mark.no_legacy_skip
def test_missing_chatgpt_login_is_rejected_before_any_observation(tmp_path):
    protocol, keys, fake = _inputs(tmp_path)
    fake.write_text(FAKE_CODEX.replace("Logged in using ChatGPT", "Not logged in"), encoding="utf-8")
    prereg_path = tmp_path / "prereg.json"
    preregister(protocol, keys, prereg_path)
    with pytest.raises(ValueError, match="codex_chatgpt_login_required"):
        run_observations(protocol, prereg_path, tmp_path / "observations.json", codex_command=str(fake))


@pytest.mark.no_legacy_skip
def test_chatgpt_login_status_on_stderr_is_recognized(tmp_path):
    protocol, keys, fake = _inputs(tmp_path)
    fake.write_text(FAKE_CODEX.replace('print("Logged in using ChatGPT")',
        'print("Logged in using ChatGPT", file=sys.stderr)'), encoding="utf-8")
    prereg_path = tmp_path / "prereg.json"
    preregister(protocol, keys, prereg_path)
    report = run_observations(protocol, prereg_path, tmp_path / "observations.json",
        codex_command=str(fake))
    assert report["attempted_observations"] == 12


@pytest.mark.no_legacy_skip
def test_failure_diagnostic_masks_secrets_urls_and_paths():
    diagnostic = _redacted_cli_diagnostic(
        "WARNING: startup warning\nERROR: authorization=Bearer-secret "
        "https://internal.example/token /tmp/private/key.json")
    assert diagnostic is not None
    assert "ERROR:" in diagnostic
    assert "startup warning" in diagnostic
    assert "Bearer-secret" not in diagnostic
    assert "internal.example" not in diagnostic
    assert "/tmp/private" not in diagnostic


@pytest.mark.no_legacy_skip
def test_interrupted_run_checkpoints_and_resumes_without_repeating_slots(tmp_path, monkeypatch):
    protocol, keys, fake = _inputs(tmp_path)
    prereg_path, raw_path, score_path = (tmp_path / name for name in
        ("prereg.json", "observations.json", "score.json"))
    preregister(protocol, keys, prereg_path)
    real_run = subprocess.run
    exec_calls = 0

    def interrupt_second_exec(*args, **kwargs):
        nonlocal exec_calls
        command = args[0]
        if "exec" in command:
            exec_calls += 1
            if exec_calls == 2:
                raise KeyboardInterrupt
        return real_run(*args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(subprocess, "run", interrupt_second_exec)
        with pytest.raises(KeyboardInterrupt):
            run_observations(protocol, prereg_path, raw_path, codex_command=str(fake))

    checkpoint = json.loads(raw_path.read_text(encoding="utf-8"))
    assert checkpoint["run_state"] == "in_progress"
    assert len(checkpoint["observations"]) == 1
    first_id = checkpoint["observations"][0]["observation_id"]
    active_id = checkpoint["active_observation_id"]
    assert active_id != first_id

    with pytest.raises(ValueError, match="pilot_observation_output_exists_use_resume"):
        run_observations(protocol, prereg_path, raw_path, codex_command=str(fake))

    exec_calls = []
    actual_run = subprocess.run

    def count_exec(command, *args, **kwargs):
        if "exec" in command:
            exec_calls.append(command)
        return actual_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", count_exec)
    resumed = run_observations(protocol, prereg_path, raw_path,
        codex_command=str(fake), resume=True)
    by_id = {item["observation_id"]: item for item in resumed["observations"]}
    assert resumed["run_state"] == "complete"
    assert resumed["attempted_observations"] == 2
    assert exec_calls == []
    assert by_id[first_id]["status"] == "response_captured"
    assert by_id[active_id]["status"] == "interrupted_unknown"
    assert sum(item["status"] == "not_attempted_global_failure"
        for item in resumed["observations"]) == 10
    score = score_observations(protocol, keys, prereg_path, raw_path, score_path)
    assert score["status"] == "insufficient"
    assert next(item for item in score["scored_observations"]
        if item["observation_id"] == active_id)["outcome"] == "insufficient"


@pytest.mark.no_legacy_skip
def test_resume_rejects_tampered_in_progress_checkpoint(tmp_path):
    protocol, keys, fake = _inputs(tmp_path)
    prereg_path, raw_path = tmp_path / "prereg.json", tmp_path / "observations.json"
    preregister(protocol, keys, prereg_path)
    raw_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="pilot_resume_checkpoint_binding_invalid"):
        run_observations(protocol, prereg_path, raw_path, codex_command=str(fake), resume=True)


@pytest.mark.no_legacy_skip
def test_runner_uses_private_writable_home_and_references_login_without_copy(tmp_path, monkeypatch):
    protocol, keys, fake = _inputs(tmp_path)
    prereg_path, raw_path = tmp_path / "prereg.json", tmp_path / "observations.json"
    preregister(protocol, keys, prereg_path)
    source_home = Path(os.environ["CODEX_HOME"])
    source_auth = source_home / "auth.json"
    inherited_home = Path(os.environ.get("HOME", ""))
    original_run = subprocess.run
    homes: list[tuple[str, str, str]] = []
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-inherit")
    monkeypatch.setenv("CODEX_SESSION_ID", "must-not-inherit")
    monkeypatch.setenv("UNRELATED_PRIVATE_VALUE", "must-not-inherit")

    def inspect_child(command, *args, **kwargs):
        env = kwargs.get("env", {})
        if "exec" in command:
            codex_home = Path(env["CODEX_HOME"])
            home = Path(env["HOME"])
            auth = codex_home / "auth.json"
            assert codex_home != source_home and home != inherited_home
            assert auth.is_symlink() and os.path.samefile(auth, source_auth)
            assert "OPENAI_API_KEY" not in env
            assert "CODEX_SESSION_ID" not in env
            assert "UNRELATED_PRIVATE_VALUE" not in env
            homes.append((str(codex_home), str(home), str(auth.resolve())))
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", inspect_child)
    run_observations(protocol, prereg_path, raw_path, codex_command=str(fake))
    assert len(homes) == 12
    assert len({row[0] for row in homes}) == 12
    assert len({row[1] for row in homes}) == 12
    assert all(not Path(row[0]).exists() and not Path(row[1]).exists() for row in homes)
    assert source_auth.read_text(encoding="utf-8") == "fixture-only-login-material"


@pytest.mark.no_legacy_skip
def test_missing_login_file_blocks_before_cli_execution(tmp_path, monkeypatch):
    protocol, keys, fake = _inputs(tmp_path)
    prereg_path = tmp_path / "prereg.json"
    preregister(protocol, keys, prereg_path)
    absent = tmp_path / "empty-codex-home"
    absent.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(absent))
    called = []
    original_run = subprocess.run

    def track(command, *args, **kwargs):
        called.append(command)
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", track)
    with pytest.raises(ValueError, match="login_file_unavailable"):
        run_observations(protocol, prereg_path, tmp_path / "observations.json", codex_command=str(fake))
    assert called == []


@pytest.mark.no_legacy_skip
def test_login_symlink_failure_preserves_empty_checkpoint_without_starting_slot(tmp_path, monkeypatch):
    protocol, keys, fake = _inputs(tmp_path)
    prereg_path, raw_path = tmp_path / "prereg.json", tmp_path / "observations.json"
    preregister(protocol, keys, prereg_path)
    original_run = subprocess.run
    invoked = []

    def track(command, *args, **kwargs):
        if "exec" in command:
            invoked.append(command)
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", track)
    monkeypatch.setattr("sentientos.codex_subject_epistemic_pilot_runner.os.symlink",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("read only")))
    with pytest.raises(ValueError, match="login_reference_unavailable"):
        run_observations(protocol, prereg_path, raw_path, codex_command=str(fake))
    report = json.loads(raw_path.read_text(encoding="utf-8"))
    assert report["observations"] == []
    assert report["attempted_observations"] == 0
    assert report["active_observation_id"] is None
    assert invoked == []
