from __future__ import annotations

import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from sentientos.bounded_subprocess import _terminate_windows_process, run_supervised

pytestmark = pytest.mark.no_legacy_skip


def test_stage_output_streams_before_process_exit() -> None:
    lines: list[tuple[float, str]] = []
    result = run_supervised([sys.executable, "-c", "import time;print('now',flush=True);time.sleep(.3)"], stage_id="live", timeout_seconds=2, emit=lambda line: lines.append((time.monotonic(), line)))
    assert any("[live][stdout] now" in line for _, line in lines[:-1]) and result.status == "passed"


def test_quiet_stage_emits_heartbeat() -> None:
    lines: list[str] = []
    run_supervised([sys.executable, "-c", "import time;time.sleep(.15)"], stage_id="quiet", timeout_seconds=1, heartbeat_seconds=.05, emit=lines.append)
    assert any("[quiet][heartbeat]" in line for line in lines)


def _tree_script(tmp_path: Path) -> str:
    marker, pids = tmp_path / "marker", tmp_path / "pids"
    grandchild = f"import os,time;open({str(pids)!r},'a').write(str(os.getpid())+'\\n');time.sleep(.8);open({str(marker)!r},'w').write('survived')"
    return f"import os,subprocess,sys,time;open({str(pids)!r},'a').write(str(os.getpid())+'\\n');subprocess.Popen([sys.executable,'-c',{grandchild!r}]);time.sleep(5)"


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group timeout proof")
def test_stage_timeout_terminates_child_and_grandchild(tmp_path: Path) -> None:
    result = run_supervised([sys.executable, "-c", _tree_script(tmp_path)], stage_id="tree", timeout_seconds=.3, termination_grace_seconds=.2, emit=lambda _: None)
    time.sleep(.8)
    assert result.termination_reason == "timeout" and not (tmp_path / "marker").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX signal lifecycle proof")
def test_controller_termination_does_not_leave_grandchild_running(tmp_path: Path) -> None:
    controller = tmp_path / "controller.py"
    controller.write_text("from sentientos.bounded_subprocess import run_supervised\nimport sys\nrun_supervised([sys.executable,'-c',sys.argv[1]],stage_id='tree',timeout_seconds=10,emit=lambda x:None)\n")
    proc = subprocess.Popen([sys.executable, str(controller), _tree_script(tmp_path)])
    for _ in range(50):
        if (tmp_path / "pids").exists() and len((tmp_path / "pids").read_text().splitlines()) >= 2: break
        time.sleep(.02)
    proc.send_signal(signal.SIGTERM); proc.wait(timeout=3); time.sleep(.8)
    assert not (tmp_path / "marker").exists()


def test_output_tail_is_bounded() -> None:
    result = run_supervised([sys.executable, "-c", "print(*range(100),sep='\\n')"], stage_id="tail", timeout_seconds=2, tail_lines=5, emit=lambda _: None)
    assert len(result.stdout_tail.splitlines()) == 5


def test_budget_refusal_starts_no_child_process() -> None:
    with pytest.raises(ValueError):
        run_supervised([sys.executable, "-c", "raise SystemExit(99)"], stage_id="none", timeout_seconds=0)


def test_invalid_numeric_limits_start_no_child_process() -> None:
    invalid_limits = (
        (math.nan, 30, 2, 40),
        (math.inf, 30, 2, 40),
        (-math.inf, 30, 2, 40),
        (1, math.nan, 2, 40),
        (1, math.inf, 2, 40),
        (1, 30, -1, 40),
        (1, 30, math.nan, 40),
        (1, 30, math.inf, 40),
        (True, 30, 2, 40),
        (1, False, 2, 40),
        (1, 30, False, 40),
        (1, 30, 2, -1),
        (1, 30, 2, 0),
        (1, 30, 2, math.nan),
        (1, 30, 2, math.inf),
        (1, 30, 2, 1.5),
        (1, 30, 2, True),
    )
    for timeout, heartbeat, grace, tail in invalid_limits:
        with pytest.raises(ValueError, match="supervision_limits_must_be_finite_and_valid"):
            run_supervised(
                [sys.executable, "-c", "raise SystemExit(99)"],
                stage_id="invalid-limits",
                timeout_seconds=timeout,
                heartbeat_seconds=heartbeat,
                termination_grace_seconds=grace,
                tail_lines=tail,
                emit=lambda _: None,
            )

    zero_grace_result = run_supervised(
        [sys.executable, "-c", "import time;time.sleep(5)"],
        stage_id="zero-grace",
        timeout_seconds=0.05,
        termination_grace_seconds=0,
        emit=lambda _: None,
    )
    assert zero_grace_result.status == "timed_out"


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group timeout proof")
def test_stage_timeout_covers_descendant_held_output_pipes(tmp_path: Path) -> None:
    marker = tmp_path / "descendant-survived"
    child_script = f"import time;time.sleep(.8);open({str(marker)!r},'w').write('survived')"
    parent_script = (
        "import subprocess,sys; "
        "subprocess.Popen([sys.executable,'-c',sys.argv[1]]); "
        "print('parent exited',flush=True)"
    )

    started = time.monotonic()
    result = run_supervised(
        [sys.executable, "-c", parent_script, child_script],
        stage_id="inherited-pipe",
        timeout_seconds=.2,
        termination_grace_seconds=.1,
        emit=lambda _: None,
    )
    duration = time.monotonic() - started
    time.sleep(.9)

    assert result.status == "timed_out"
    assert duration < .75
    assert not marker.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX nonblocking pipe timeout proof")
def test_stage_timeout_covers_unterminated_partial_output() -> None:
    lines: list[str] = []
    started = time.monotonic()
    result = run_supervised(
        [
            sys.executable,
            "-c",
            "import os,time;os.write(1,b'progress\\r');time.sleep(0.05);os.write(1,b'\\npartial output');time.sleep(5)",
        ],
        stage_id="partial-line",
        timeout_seconds=0.2,
        termination_grace_seconds=0.1,
        emit=lines.append,
    )

    assert result.status == "timed_out"
    assert result.stdout_tail == "progress\npartial output"
    assert time.monotonic() - started < 0.75
    assert any("[partial-line][stdout] progress" in line for line in lines)
    assert any("[partial-line][stdout] partial output" in line for line in lines)


def test_explicit_empty_environment_does_not_inherit_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_PARENT_ONLY_SENTINEL", "must-not-leak")
    result = run_supervised(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('SENTIENTOS_PARENT_ONLY_SENTINEL', '<missing>'))",
        ],
        stage_id="empty-env",
        timeout_seconds=2,
        env={},
        emit=lambda _: None,
    )

    assert result.status == "passed"
    assert result.stdout_tail == "<missing>"


def test_supervisor_drains_stdout_and_stderr_without_deadlock() -> None:
    result = run_supervised(
        [
            sys.executable,
            "-c",
            "import os, threading\n"
            "def write_all(fd, byte):\n"
            "    data = byte * 262144\n"
            "    while data:\n"
            "        written = os.write(fd, data)\n"
            "        data = data[written:]\n"
            "threads = [threading.Thread(target=write_all, args=(fd, byte)) "
            "for fd, byte in ((1, b'o'), (2, b'e'))]\n"
            "for thread in threads: thread.start()\n"
            "for thread in threads: thread.join()",
        ],
        stage_id="both-streams",
        timeout_seconds=5,
        emit=lambda _: None,
    )

    assert result.status == "passed"
    assert "line continues" in result.stdout_tail
    assert "line continues" in result.stderr_tail


def test_windows_group_shutdown_is_reported_as_graceful(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(signal, "CTRL_BREAK_EVENT", 123, raising=False)
    process = Mock()
    process.poll.return_value = None
    process.wait.return_value = 0

    graceful, forced = _terminate_windows_process(process, 0.2)

    assert graceful is True
    assert forced is False
    process.send_signal.assert_called_once_with(123)
    process.kill.assert_not_called()


def test_windows_shutdown_falls_back_to_reported_forced_termination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(signal, "CTRL_BREAK_EVENT", 123, raising=False)
    process = Mock()
    process.poll.return_value = None
    process.send_signal.side_effect = OSError("console control event unavailable")
    process.wait.return_value = -1

    graceful, forced = _terminate_windows_process(process, 0.2)

    assert graceful is True
    assert forced is True
    process.send_signal.assert_called_once_with(123)
    process.kill.assert_called_once_with()


def test_windows_shutdown_forces_child_after_grace_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(signal, "CTRL_BREAK_EVENT", 123, raising=False)
    process = Mock()
    process.poll.return_value = None
    process.wait.side_effect = [
        subprocess.TimeoutExpired("child", 0.2),
        -1,
    ]

    graceful, forced = _terminate_windows_process(process, 0.2)

    assert graceful is True
    assert forced is True
    process.send_signal.assert_called_once_with(123)
    process.kill.assert_called_once_with()
    assert process.wait.call_count == 2
