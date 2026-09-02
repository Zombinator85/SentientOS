"""Bounded service adapters used by the canonical runtime supervisor."""
from __future__ import annotations

import os
import signal
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class HealthResult:
    ready: bool
    reason: str = "ready"
    metadata: Mapping[str, object] | None = None


class ServiceAdapter(Protocol):
    @property
    def identity(self) -> Mapping[str, object]: ...
    def start(self) -> None: ...
    def health(self) -> HealthResult: ...
    def stop(self) -> None: ...
    def force_stop(self) -> None: ...


class InProcessServiceAdapter:
    """Adapter for an existing owner; it does not confer business authority."""

    def __init__(self, *, name: str, start: Callable[[], None], health: Callable[[], HealthResult],
                 stop: Callable[[], None], force_stop: Callable[[], None] | None = None) -> None:
        self._name = name
        self._start = start
        self._health = health
        self._stop = stop
        self._force_stop = force_stop or stop

    @property
    def identity(self) -> Mapping[str, object]:
        return {"adapter": "in_process", "name": self._name}

    def start(self) -> None: self._start()
    def health(self) -> HealthResult: return self._health()
    def stop(self) -> None: self._stop()
    def force_stop(self) -> None: self._force_stop()


class ChildProcessServiceAdapter:
    """Strict argv-only child custody with bounded captured diagnostics."""

    def __init__(self, *, name: str, argv: Sequence[str], cwd: Path,
                 environment: Mapping[str, str], diagnostic_limit: int = 16_384) -> None:
        if not argv or isinstance(argv, (str, bytes)) or any(not isinstance(x, str) or not x for x in argv):
            raise ValueError("child_process_requires_nonempty_argv")
        self._name, self._argv, self._cwd = name, tuple(argv), Path(cwd).resolve()
        self._environment = dict(environment)
        self._diagnostic_limit = max(256, diagnostic_limit)
        self._process: subprocess.Popen[bytes] | None = None
        self._diagnostics = bytearray()
        self._reader: threading.Thread | None = None

    @property
    def identity(self) -> Mapping[str, object]:
        return {"adapter": "child_process", "name": self._name, "argv": self._argv,
                "cwd": str(self._cwd), "pid": self._process.pid if self._process else None}

    def start(self) -> None:
        if self._process is not None and self._process.poll() is None: return
        self._diagnostics.clear()
        self._process = subprocess.Popen(self._argv, cwd=self._cwd, env=self._environment,
            shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt")
        process = self._process
        stdout = process.stdout
        assert stdout is not None
        def read() -> None:
            for chunk in iter(lambda: stdout.read(4096), b""):
                self._diagnostics.extend(chunk)
                del self._diagnostics[:-self._diagnostic_limit]
        self._reader = threading.Thread(target=read, name=f"{self._name}-diagnostics", daemon=True)
        self._reader.start()

    def health(self) -> HealthResult:
        running = self._process is not None and self._process.poll() is None
        return HealthResult(running, "process_alive" if running else "process_exited",
                            {"diagnostics": bytes(self._diagnostics).decode("utf-8", "replace")})

    def stop(self) -> None:
        if self._process is not None and self._process.poll() is None: self._process.terminate()

    def force_stop(self) -> None:
        if self._process is None or self._process.poll() is not None: return
        if os.name != "nt": os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
        else: self._process.kill()
