from __future__ import annotations

import os
import selectors
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Callable, IO, Mapping, Sequence


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


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_tree(
    process: subprocess.Popen[Any], grace: float, process_group_id: int | None = None
) -> tuple[bool, bool]:
    graceful = True
    forced = False
    if os.name == "posix":
        group_id = process_group_id
        if group_id is None:
            try:
                group_id = os.getpgid(process.pid)
            except ProcessLookupError:
                return graceful, forced
        try:
            os.killpg(group_id, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline and _process_group_exists(group_id):
            time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))
        if _process_group_exists(group_id):
            forced = True
            try:
                os.killpg(group_id, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.poll() is None:
            process.wait(timeout=max(1.0, grace))
        return graceful, forced

    try:
        process.terminate()
        process.wait(timeout=grace)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        forced = True
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
    process: subprocess.Popen[bytes] = subprocess.Popen(
        command, shell=shell, text=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        bufsize=0, env=dict(env) if env else None, start_new_session=os.name == "posix",
        creationflags=creationflags,
    )
    pgid = process.pid
    tails: dict[str, deque[str]] = {"stdout": deque(maxlen=tail_lines), "stderr": deque(maxlen=tail_lines)}
    selector = selectors.DefaultSelector()
    stdout, stderr = process.stdout, process.stderr
    assert stdout is not None and stderr is not None
    output_streams: dict[int, IO[bytes]] = {}
    for output_stream, stream_name in ((stdout, "stdout"), (stderr, "stderr")):
        file_descriptor = output_stream.fileno()
        os.set_blocking(file_descriptor, False)
        output_streams[file_descriptor] = output_stream
        selector.register(file_descriptor, selectors.EVENT_READ, stream_name)
    pending_lines: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    skip_lf_after_cr = {"stdout": False, "stderr": False}
    max_line_bytes = 65536
    last_output = started
    termination_reason: str | None = None
    graceful = forced = False
    previous_handlers: dict[int, Any] = {}
    drain_deadline: float | None = None

    def cancel(signum: int, _frame: object) -> None:
        nonlocal termination_reason, graceful, forced, drain_deadline
        termination_reason = f"signal:{signum}"
        graceful, forced = _terminate_tree(process, termination_grace_seconds, pgid)
        drain_deadline = time.monotonic() + max(0.1, termination_grace_seconds)

    if os.name == "posix" and sys.platform != "win32":
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, cancel)
    try:
        def record_line(name: str, raw_line: bytes) -> None:
            nonlocal last_output
            clean = raw_line.decode("utf-8", errors="replace").rstrip("\r")
            tails[name].append(clean)
            writer(f"[{stage_id}][{name}] {clean}")
            last_output = time.monotonic()

        while process.poll() is None or selector.get_map():
            now = time.monotonic()
            if termination_reason is None and now - started >= timeout_seconds:
                termination_reason = "timeout"
                graceful, forced = _terminate_tree(process, termination_grace_seconds, pgid)
                drain_deadline = time.monotonic() + max(0.1, termination_grace_seconds)
            if drain_deadline is not None and now >= drain_deadline:
                for key in list(selector.get_map().values()):
                    stream_name = str(key.data)
                    buffered = pending_lines[stream_name]
                    if buffered:
                        record_line(stream_name, bytes(buffered))
                        buffered.clear()
                    file_descriptor = key.fd
                    selector.unregister(file_descriptor)
                    output_streams[file_descriptor].close()
                break
            if selector.get_map():
                wait_seconds = min(0.2, heartbeat_seconds)
                if drain_deadline is not None:
                    wait_seconds = min(wait_seconds, max(0.0, drain_deadline - now))
                events = selector.select(timeout=wait_seconds)
            else:
                time.sleep(min(0.2, heartbeat_seconds))
                events = []
            for key, _ in events:
                file_descriptor = key.fd
                stream_name = str(key.data)
                try:
                    chunk = os.read(file_descriptor, 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    buffered = pending_lines[stream_name]
                    if buffered:
                        record_line(stream_name, bytes(buffered))
                        buffered.clear()
                    selector.unregister(file_descriptor)
                    continue
                if skip_lf_after_cr[stream_name]:
                    if chunk.startswith(b"\n"):
                        chunk = chunk[1:]
                    skip_lf_after_cr[stream_name] = False
                if not chunk:
                    continue
                buffered = pending_lines[stream_name]
                buffered.extend(chunk)
                while True:
                    carriage_return = buffered.find(13)
                    newline = buffered.find(10)
                    delimiters = [position for position in (carriage_return, newline) if position >= 0]
                    if not delimiters:
                        break
                    delimiter = min(delimiters)
                    raw_line = bytes(buffered[:delimiter])
                    is_carriage_return = buffered[delimiter] == 13
                    del buffered[: delimiter + 1]
                    if is_carriage_return and buffered.startswith(b"\\n"):
                        del buffered[:1]
                    elif is_carriage_return and not buffered:
                        skip_lf_after_cr[stream_name] = True
                    if len(raw_line) > max_line_bytes:
                        raw_line = raw_line[:max_line_bytes] + b" [line truncated]"
                    record_line(stream_name, raw_line)
                while len(buffered) > max_line_bytes:
                    record_line(stream_name, bytes(buffered[:max_line_bytes]) + b" [line continues]")
                    del buffered[:max_line_bytes]
            if termination_reason is None and time.monotonic() - last_output >= heartbeat_seconds:
                writer(f"[{stage_id}][heartbeat] quiet stage still running")
                last_output = time.monotonic()
        return_code = process.wait()

    except BaseException:
        if process.poll() is None:
            termination_reason = termination_reason or "controller_exception"
            graceful, forced = _terminate_tree(process, termination_grace_seconds, pgid)
        raise
    finally:
        for saved_signum, handler in previous_handlers.items():
            signal.signal(saved_signum, handler)
        selector.close()
    duration = time.monotonic() - started
    status = "timed_out" if termination_reason == "timeout" else "cancelled" if termination_reason else "passed" if return_code == 0 else "failed"
    # On POSIX wait() plus process-group signalling is the strongest portable
    # repository-level confirmation. Windows cannot independently enumerate descendants.
    confirmed = os.name == "posix" and not _process_group_exists(pgid)
    writer(f"[finalizer] stage end: {stage_id} status={status} exit_code={return_code} duration={duration:.3f}s")
    return SupervisedProcessResult(
        tuple(argv) if not isinstance(argv, str) else (argv,), process.pid, pgid, return_code,
        status, duration, "\n".join(tails["stdout"]), "\n".join(tails["stderr"]),
        termination_reason, graceful, forced, confirmed,
        "descendants_confirmed_terminated" if confirmed else "platform_limited_termination_evidence",
    )
