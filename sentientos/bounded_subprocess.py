from __future__ import annotations

import os
import selectors
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping, Sequence, TextIO, cast


DEFAULT_HEARTBEAT_SECONDS = 30.0
DEFAULT_TAIL_LINES = 40
DEFAULT_TERMINATION_GRACE_SECONDS = 2.0


@dataclass(frozen=True)
class SupervisedProcessResult:
    argv: tuple[str, ...]
    child_pid: int
    process_group_id: int | None
    return_code: int
    status: str
    duration_seconds: float
    stdout_tail: str
    stderr_tail: str
    termination_reason: str | None
    graceful_termination_attempted: bool
    forced_termination_attempted: bool
    descendants_confirmed_terminated: bool
    supervision_status: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _terminate_tree(process: subprocess.Popen[str], grace: float) -> tuple[bool, bool]:
    graceful = True
    forced = False
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=grace)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        forced = True
        if os.name == "posix":
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait(timeout=max(1.0, grace))
    return graceful, forced


def run_supervised(
    argv: Sequence[str] | str,
    *,
    stage_id: str,
    timeout_seconds: float,
    env: Mapping[str, str] | None = None,
    shell: bool = False,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    tail_lines: int = DEFAULT_TAIL_LINES,
    termination_grace_seconds: float = DEFAULT_TERMINATION_GRACE_SECONDS,
    emit: Callable[[str], None] | None = None,
) -> SupervisedProcessResult:
    if timeout_seconds <= 0 or heartbeat_seconds <= 0 or tail_lines <= 0:
        raise ValueError("supervision_limits_must_be_positive")
    writer = emit or (lambda line: print(line, flush=True))
    command = argv if isinstance(argv, str) else list(argv)
    started = time.monotonic()
    writer(f"[finalizer] stage start: {stage_id}")
    creationflags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if os.name == "nt" else 0
    process = subprocess.Popen(
        command, shell=shell, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        bufsize=1, env=dict(env) if env else None, start_new_session=os.name == "posix",
        creationflags=creationflags,
    )
    pgid = os.getpgid(process.pid) if os.name == "posix" else process.pid
    tails: dict[str, deque[str]] = {"stdout": deque(maxlen=tail_lines), "stderr": deque(maxlen=tail_lines)}
    selector = selectors.DefaultSelector()
    assert process.stdout is not None and process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    last_output = started
    termination_reason: str | None = None
    graceful = forced = False
    previous_handlers: dict[int, Any] = {}

    def cancel(signum: int, _frame: object) -> None:
        nonlocal termination_reason, graceful, forced
        termination_reason = f"signal:{signum}"
        graceful, forced = _terminate_tree(process, termination_grace_seconds)

    if os.name == "posix" and sys.platform != "win32":
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, cancel)
    try:
        while process.poll() is None:
            now = time.monotonic()
            if now - started >= timeout_seconds:
                termination_reason = "timeout"
                graceful, forced = _terminate_tree(process, termination_grace_seconds)
                break
            events = selector.select(timeout=min(0.2, heartbeat_seconds))
            for key, _ in events:
                line = cast(TextIO, key.fileobj).readline()
                if line:
                    clean = line.rstrip("\r\n")
                    tails[key.data].append(clean)
                    writer(f"[{stage_id}][{key.data}] {clean}")
                    last_output = time.monotonic()
            if time.monotonic() - last_output >= heartbeat_seconds:
                writer(f"[{stage_id}][heartbeat] quiet stage still running")
                last_output = time.monotonic()
        for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
            for line in stream:
                clean = line.rstrip("\r\n")
                tails[name].append(clean)
                writer(f"[{stage_id}][{name}] {clean}")
        return_code = process.wait()
    except BaseException:
        if process.poll() is None:
            termination_reason = termination_reason or "controller_exception"
            graceful, forced = _terminate_tree(process, termination_grace_seconds)
        raise
    finally:
        for saved_signum, handler in previous_handlers.items():
            signal.signal(saved_signum, handler)
        selector.close()
    duration = time.monotonic() - started
    status = "timed_out" if termination_reason == "timeout" else "cancelled" if termination_reason else "passed" if return_code == 0 else "failed"
    # On POSIX wait() plus process-group signalling is the strongest portable
    # repository-level confirmation. Windows cannot independently enumerate descendants.
    confirmed = os.name == "posix" and process.poll() is not None
    writer(f"[finalizer] stage end: {stage_id} status={status} exit_code={return_code} duration={duration:.3f}s")
    return SupervisedProcessResult(
        tuple(argv) if not isinstance(argv, str) else (argv,), process.pid, pgid, return_code,
        status, duration, "\n".join(tails["stdout"]), "\n".join(tails["stderr"]),
        termination_reason, graceful, forced, confirmed,
        "descendants_confirmed_terminated" if confirmed else "platform_limited_termination_evidence",
    )
