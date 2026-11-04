from __future__ import annotations

import io
import queue

from scripts.run_local_companion_dev import (
    _LatestScreenObservation,
    _TemporaryCompanionEdge,
    _kill_windows_process_tree,
    _parse_edge_ready,
    _stage_windows_edge_source,
    _wait_for_edge_ready,
    main,
)
from scripts.terminate_owned_process_tree import (
    terminate_owned_process_tree,
)


def test_forward_lines_surfaces_worker_output_after_ready(tmp_path, capsys) -> None:
    lines: queue.Queue[str] = queue.Queue()
    report_file = tmp_path / "renderer-reports.jsonl"

    _TemporaryCompanionEdge._forward_lines(
        io.StringIO("READY 12345\nRuntimeError: worker stopped\n"),
        lines,
        report_file,
    )

    assert lines.get_nowait() == "READY 12345"
    assert lines.get_nowait() == "RuntimeError: worker stopped"
    assert capsys.readouterr().out == (
        "WINDOWS_EDGE RuntimeError: worker stopped\n"
    )


def test_terminate_owned_process_tree_stops_windows_descendants(
    tmp_path, monkeypatch
) -> None:
    class Process:
        pid = 1234
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            self.returncode = 0
            return self.returncode

        def kill(self):
            self.returncode = -9

    process = Process()
    taskkill = tmp_path / "taskkill.exe"
    taskkill.touch()
    calls = []

    def stop_tree(args, **kwargs):
        calls.append((args, kwargs))
        process.returncode = 0

    monkeypatch.setattr(
        "scripts.terminate_owned_process_tree.subprocess.run", stop_tree
    )

    terminate_owned_process_tree(process, taskkill_executable=taskkill)

    assert process.returncode == 0
    assert calls[0][0] == [str(taskkill), "/T", "/F", "/PID", "1234"]
    assert calls[0][1]["timeout"] == 8


def test_parse_edge_ready_includes_exact_godot_pid() -> None:
    assert _parse_edge_ready("READY 12345 67890") == (12345, 67890)




def test_wait_for_edge_ready_skips_screen_startup_diagnostics() -> None:
    class Process:
        def poll(self):
            return None

    lines: queue.Queue[str] = queue.Queue()
    lines.put("SCREEN_PUMP_STARTED interval_seconds=2.5 raw_frame_retained=false")
    lines.put("READY 12345 67890")

    assert _wait_for_edge_ready(lines, Process()) == "READY 12345 67890"


def test_forward_lines_surfaces_edge_startup_progress_before_ready(tmp_path, capsys) -> None:
    lines: queue.Queue[str] = queue.Queue()

    _TemporaryCompanionEdge._forward_lines(
        io.StringIO("EDGE_STARTUP phase=worker_started\nREADY 12345 67890\n"),
        lines,
        tmp_path / "renderer-reports.jsonl",
    )

    assert lines.get_nowait() == "EDGE_STARTUP phase=worker_started"
    assert lines.get_nowait() == "READY 12345 67890"
    assert capsys.readouterr().out == (
        "WINDOWS_EDGE EDGE_STARTUP phase=worker_started\n"
    )


def test_wait_for_edge_ready_timeout_reports_live_worker() -> None:
    import pytest

    class Process:
        def poll(self):
            return None

    with pytest.raises(RuntimeError, match="ready_timeout.*edge_process_still_running"):
        _wait_for_edge_ready(queue.Queue(), Process(), timeout_seconds=0.01)


def test_wait_for_edge_ready_reports_worker_exit_before_ready() -> None:
    import pytest

    class Process:
        def poll(self):
            return 1

    lines: queue.Queue[str] = queue.Queue()
    lines.put("SCREEN_PUMP_FAILURE game_screen_capture_backend_unavailable")

    with pytest.raises(RuntimeError, match="exited_before_ready.*SCREEN_PUMP_FAILURE"):
        _wait_for_edge_ready(lines, Process(), timeout_seconds=0.2)

def test_parse_edge_ready_rejects_missing_or_invalid_godot_pid() -> None:
    import pytest

    with pytest.raises(RuntimeError, match="ready_missing_godot_pid"):
        _parse_edge_ready("READY 12345")
    with pytest.raises(RuntimeError, match="invalid_ready_values"):
        _parse_edge_ready("READY 12345 0")


def test_kill_windows_process_tree_targets_only_reported_godot_pid(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "scripts.run_local_companion_dev.shutil.which",
        lambda name: "/mnt/c/Windows/System32/taskkill.exe",
    )
    monkeypatch.setattr(
        "scripts.run_local_companion_dev.subprocess.run",
        lambda args, **kwargs: calls.append((args, kwargs)),
    )

    _kill_windows_process_tree(67890)

    assert calls[0][0] == [
        "/mnt/c/Windows/System32/taskkill.exe", "/T", "/F", "/PID", "67890"
    ]
    assert calls[0][1]["timeout"] == 8


def test_stage_windows_edge_source_uses_only_reviewed_python_source(tmp_path) -> None:
    import zipfile

    repo = tmp_path / "repo"
    (repo / "sentientos").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "sentientos" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "sentientos" / "chat.py").write_text("reviewed module", encoding="utf-8")
    (repo / "avatar_state.py").write_text("reviewed root module", encoding="utf-8")
    (repo / "scripts" / "local_companion_edge_dev_worker.py").write_text(
        "worker source", encoding="utf-8")
    (repo / "scripts" / "terminate_owned_process_tree.py").write_text(
        "cleanup source", encoding="utf-8")
    (repo / "unreviewed.env").write_text("must not be staged", encoding="utf-8")
    (repo / "sentientos" / "private.json").write_text(
        "non-source data must not be staged", encoding="utf-8")

    archive = _stage_windows_edge_source(repo, tmp_path / "temporary-edge")

    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert "sentientos/__init__.py" in names
        assert bundle.read("sentientos/chat.py").decode() == "reviewed module"
        assert bundle.read("avatar_state.py").decode() == "reviewed root module"
        assert bundle.read("terminate_owned_process_tree.py").decode() == "cleanup source"
        assert "unreviewed.env" not in names
        assert "sentientos/private.json" not in names

def test_explicit_tesseract_executable_requires_screen_observation_opt_in(monkeypatch, tmp_path):
    import sys
    import pytest

    monkeypatch.setattr(sys, "argv", [
        "run_local_companion_dev", "--state-dir", str(tmp_path),
        "--screen-observation-tesseract-executable",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    ])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_screen_observation_opt_in_requires_supervised_windows_edge(monkeypatch):
    import sys
    import pytest

    monkeypatch.setattr(sys, "argv", [
        "run_local_companion_dev", "--state-dir", "/tmp/sentientos-screen-test",
        "--screen-observation-process", "Cronos.exe",
    ])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2

def test_latest_screen_observation_drains_and_expires_cached_sample(monkeypatch):
    import threading
    import time

    now = [10.0]
    monkeypatch.setattr("scripts.run_local_companion_dev.time.monotonic",
                        lambda: now[0])
    sampled = threading.Event()

    def provider():
        if not sampled.is_set():
            sampled.set()
            return {"text": "objective changed"}
        raise RuntimeError("bridge_receive_timeout")

    observer = _LatestScreenObservation(provider=provider, max_age_seconds=5.0)
    try:
        assert sampled.wait(timeout=1.0)
        deadline = time.perf_counter() + 1.0
        while observer() is None and time.perf_counter() < deadline:
            time.sleep(0.01)
        assert observer() == {"text": "objective changed"}
        now[0] += 6.0
        assert observer() is None
    finally:
        observer.close()



def test_latest_screen_observation_adds_bounded_delta_and_drops_expired_baseline(monkeypatch):
    import threading
    import time

    now = [10.0]
    monkeypatch.setattr("scripts.run_local_companion_dev.time.monotonic",
                        lambda: now[0])
    samples = [
        {"text": "Quest\nFind the key"},
        {"text": "Quest\nOpen the gate"},
        {"text": "Quest\nEnter the hall"},
    ]
    changed = threading.Event()

    def provider():
        if samples:
            sample = samples.pop(0)
            if not samples:
                changed.set()
            return sample
        raise RuntimeError("bridge_receive_timeout")

    observer = _LatestScreenObservation(provider=provider, max_age_seconds=5.0)
    try:
        deadline = time.perf_counter() + 1.0
        first = None
        while first is None and time.perf_counter() < deadline:
            first = observer()
            time.sleep(0.01)
        assert first == {"text": "Quest\nFind the key"}

        deadline = time.perf_counter() + 1.0
        second = None
        while (second is None or "text_delta" not in second) and time.perf_counter() < deadline:
            second = observer()
            time.sleep(0.01)
        assert second["text_delta"]["added_lines"] == ["Open the gate"]
        assert second["text_delta"]["removed_lines"] == ["Find the key"]

        now[0] += 6.0
        samples.append({"text": "Quest\nBoss room"})
        deadline = time.perf_counter() + 1.0
        third = None
        while third is None or third.get("text") != "Quest\nBoss room":
            if time.perf_counter() >= deadline:
                raise AssertionError("new OCR sample was not observed")
            third = observer()
            time.sleep(0.01)
        assert "text_delta" not in third
    finally:
        observer.close()
