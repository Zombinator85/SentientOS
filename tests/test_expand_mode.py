from __future__ import annotations

import json
from pathlib import Path
from queue import Queue

import pytest

from daemon import codex_daemon
from sentientos.daemons import pulse_bus


class _DummyProcess:
    def __init__(self, stdout: str = "") -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def _configure_expand_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    request_dir = tmp_path / "requests"
    archive_dir = request_dir / "archive"
    suggestion_dir = tmp_path / "suggestions"
    reasoning_dir = tmp_path / "reasoning"
    project_root = tmp_path / "repo"
    log_path = tmp_path / "codex.jsonl"

    monkeypatch.setattr(codex_daemon, "EXPAND_REQUEST_DIR", request_dir)
    monkeypatch.setattr(codex_daemon, "EXPAND_ARCHIVE_DIR", archive_dir)
    monkeypatch.setattr(codex_daemon, "CODEX_SUGGEST_DIR", suggestion_dir)
    monkeypatch.setattr(codex_daemon, "CODEX_PATCH_DIR", suggestion_dir)
    monkeypatch.setattr(codex_daemon, "CODEX_REASONING_DIR", reasoning_dir)
    monkeypatch.setattr(codex_daemon, "CODEX_LOG", log_path)
    monkeypatch.setattr(codex_daemon, "PROJECT_ROOT", project_root)

    request_dir.mkdir(parents=True, exist_ok=True)
    project_root.mkdir(parents=True, exist_ok=True)
    suggestion_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(codex_daemon, "CODEX_MODE", "expand")
    monkeypatch.setattr(codex_daemon, "CODEX_CONFIRM_PATTERNS", [])
    monkeypatch.setattr(codex_daemon, "load_ethics", lambda: "Sanctuary Ethics")

    return request_dir, archive_dir, project_root


def _drain(queue: Queue) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    while not queue.empty():
        entries.append(queue.get())
    return entries


@pytest.fixture(autouse=True)
def reset_pulse_bus() -> None:
    pulse_bus.reset()
    yield
    pulse_bus.reset()


def test_expand_diff_request_applies_patch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request_dir, archive_dir, _ = _configure_expand_environment(tmp_path, monkeypatch)

    request_path = request_dir / "feature.txt"
    request_path.write_text("Expand SentientOS with a helper.", encoding="utf-8")

    sample_diff = """--- a/module.py\n+++ b/module.py\n@@\n-print('old')\n+print('new')\n"""

    captured_prompts: list[str] = []
    git_calls: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, **_: object):
        if cmd[:2] == ["codex", "exec"]:
            captured_prompts.append(cmd[2])
            return _DummyProcess(sample_diff)
        git_calls.append(cmd)
        return _DummyProcess("")

    apply_calls: list[str] = []
    run_ci_calls: list[Queue] = []

    def fake_apply(diff: str) -> bool:
        apply_calls.append(diff)
        return True

    def fake_run_ci(queue: Queue) -> bool:
        run_ci_calls.append(queue)
        return True

    published: list[dict[str, object]] = []

    def fake_publish(event: dict[str, object]) -> dict[str, object]:
        published.append(event)
        return event

    monkeypatch.setattr(codex_daemon.subprocess, "run", fake_run)
    monkeypatch.setattr(codex_daemon, "apply_patch", fake_apply)
    monkeypatch.setattr(codex_daemon, "run_ci", fake_run_ci)
    monkeypatch.setattr(codex_daemon.pulse_bus, "publish", fake_publish)

    ledger_queue: Queue = Queue()
    result = codex_daemon.run_once(ledger_queue)

    assert result is not None
    assert result["event"] == "self_expand"
    assert captured_prompts, "Codex prompt was not issued"
    assert apply_calls and apply_calls[0] == sample_diff
    assert run_ci_calls, "run_ci was not invoked"

    assert any(cmd[:2] == ["git", "add"] for cmd in git_calls)
    assert any(cmd[:2] == ["git", "commit"] for cmd in git_calls)

    archive_files = list(archive_dir.glob("*"))
    assert archive_files, "request archive missing"
    assert any(path.suffix == ".diff" or path.suffix == ".json" for path in archive_files)

    suggestions = list((tmp_path / "suggestions").glob("expand_*.diff"))
    assert suggestions, "suggested diff not written"
    reasoning = list((tmp_path / "reasoning").glob("expand_*.json"))
    assert reasoning, "reasoning trace missing"

    entries = _drain(ledger_queue)
    assert any(entry["event"] == "self_expand_suggested" for entry in entries)
    assert any(entry["event"] == "self_expand" for entry in entries)

    event_types = [event["event_type"] for event in published]
    assert "expand_request" in event_types
    assert "expand_result" in event_types


def test_expand_json_mapping_creates_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request_dir, archive_dir, project_root = _configure_expand_environment(tmp_path, monkeypatch)

    request_path = request_dir / "create.json"
    request_path.write_text(json.dumps({"task": "Add a manifest."}), encoding="utf-8")

    mapping = {"services/manifest.txt": "ready"}

    git_calls: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, **_: object):
        if cmd[:2] == ["codex", "exec"]:
            return _DummyProcess(json.dumps(mapping))
        git_calls.append(cmd)
        return _DummyProcess("")

    def fail_apply(_: str) -> bool:
        pytest.fail("apply_patch should not be called for JSON mapping")

    ci_calls: list[Queue] = []

    def fake_run_ci(queue: Queue) -> bool:
        ci_calls.append(queue)
        return True

    published: list[dict[str, object]] = []
    monkeypatch.setattr(codex_daemon.subprocess, "run", fake_run)
    monkeypatch.setattr(codex_daemon, "apply_patch", fail_apply)
    monkeypatch.setattr(codex_daemon, "run_ci", fake_run_ci)
    monkeypatch.setattr(codex_daemon.pulse_bus, "publish", lambda event: published.append(event) or event)

    ledger_queue: Queue = Queue()
    result = codex_daemon.run_once(ledger_queue)

    assert result is not None
    assert result["event"] == "self_expand"
    created_file = project_root / "services" / "manifest.txt"
    assert created_file.exists()
    assert created_file.read_text(encoding="utf-8") == "ready"

    entries = _drain(ledger_queue)
    assert any(entry["event"] == "self_expand" for entry in entries)
    assert ci_calls, "run_ci not invoked"

    assert any(cmd[:2] == ["git", "commit"] for cmd in git_calls)
    event_types = [event["event_type"] for event in published]
    assert "expand_request" in event_types
    assert any(evt.get("payload", {}).get("status") == "applied" for evt in published if evt["event_type"] == "expand_result")
    assert any(path.name.endswith("_response.json") for path in archive_dir.glob("*.json"))


def test_expand_off_limits_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request_dir, _, _ = _configure_expand_environment(tmp_path, monkeypatch)

    (request_dir / "limit.txt").write_text("Touch NEWLEGACY.", encoding="utf-8")
    forbidden_diff = """--- a/NEWLEGACY.txt\n+++ b/NEWLEGACY.txt\n@@\n-old\n+new\n"""

    monkeypatch.setattr(codex_daemon.subprocess, "run", lambda *a, **k: _DummyProcess(forbidden_diff))
    monkeypatch.setattr(codex_daemon, "apply_patch", lambda _: pytest.fail("should not apply off-limits patch"))
    monkeypatch.setattr(codex_daemon, "run_ci", lambda queue: pytest.fail("CI should not run for off-limits"))

    published: list[dict[str, object]] = []
    monkeypatch.setattr(codex_daemon.pulse_bus, "publish", lambda event: published.append(event) or event)

    ledger_queue: Queue = Queue()
    result = codex_daemon.run_once(ledger_queue)

    assert result is not None
    assert result["event"] == "self_expand_rejected"
    assert result["reason"] == "off_limits"

    entries = _drain(ledger_queue)
    assert any(entry["event"] == "self_expand_suggested" for entry in entries)
    assert any(entry["event"] == "self_expand_rejected" and entry["reason"] == "off_limits" for entry in entries)

    results = [event for event in published if event["event_type"] == "expand_result"]
    assert results and results[0]["payload"]["status"] == "rejected"


def test_expand_request_triggers_veil(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request_dir, archive_dir, _ = _configure_expand_environment(tmp_path, monkeypatch)

    monkeypatch.setattr(codex_daemon, "CODEX_CONFIRM_PATTERNS", ["sensitive/"])

    (request_dir / "veil.txt").write_text("Modify sensitive region.", encoding="utf-8")
    guarded_diff = """--- a/sensitive/data.txt\n+++ b/sensitive/data.txt\n@@\n-old\n+new\n"""

    monkeypatch.setattr(codex_daemon.subprocess, "run", lambda *a, **k: _DummyProcess(guarded_diff))
    monkeypatch.setattr(codex_daemon, "apply_patch", lambda _: pytest.fail("veil changes must not auto-apply"))
    monkeypatch.setattr(codex_daemon, "run_ci", lambda queue: pytest.fail("CI should not run for veil pending"))

    published: list[dict[str, object]] = []

    def fake_publish(event: dict[str, object]) -> dict[str, object]:
        published.append(event)
        return event

    monkeypatch.setattr(codex_daemon.pulse_bus, "publish", fake_publish)

    ledger_queue: Queue = Queue()
    result = codex_daemon.run_once(ledger_queue)

    assert result is not None
    assert result["event"] == "self_expand_rejected"
    assert result["reason"] == "veil"

    entries = _drain(ledger_queue)
    assert any(entry["event"] == "veil_pending" for entry in entries)

    metadata_files = list((tmp_path / "suggestions").glob("*.veil.json"))
    assert metadata_files, "veil metadata missing"
    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    assert metadata["requires_confirmation"] is True
    assert metadata["response_format"] == "diff"

    assert any(event["event_type"] == "veil_request" for event in published)
    results = [event for event in published if event["event_type"] == "expand_result"]
    assert results and results[0]["payload"]["status"] == "veil_pending"
    assert archive_dir.exists()
