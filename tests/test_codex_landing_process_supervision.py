from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from sentientos.bounded_subprocess import run_supervised

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
