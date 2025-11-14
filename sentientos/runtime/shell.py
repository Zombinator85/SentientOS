"""Windows-oriented runtime shell for SentientOS services."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Dict, Iterable, Mapping, MutableMapping, Optional, Tuple

from sentientos.persona import PersonaLoop, initial_state
from sentientos.persona_events import collect_recent_events

__all__ = [
    "DEFAULT_RUNTIME_CONFIG",
    "RuntimeShell",
    "ensure_runtime_dirs",
    "load_or_init_config",
]


DEFAULT_RUNTIME_CONFIG: Dict[str, object] = {
    "llama_server_path": "C:/SentientOS/bin/llama-server.exe",
    "model_path": "C:/SentientOS/sentientos_data/models/default.gguf",
    "relay_host": "127.0.0.1",
    "relay_port": 65432,
    "watchdog_interval": 5.0,
    "windows_mode": True,
}

DEFAULT_PERSONA_CONFIG: Dict[str, object] = {
    "enabled": True,
    "tick_interval_seconds": 60.0,
    "max_message_length": 200,
}


def ensure_runtime_dirs(base: str | Path = "C:/SentientOS") -> Dict[str, Path]:
    """Ensure the Windows runtime directory layout exists."""

    base_path = Path(base)
    logs_dir = base_path / "logs"
    data_dir = base_path / "sentientos_data"
    models_dir = data_dir / "models"
    config_dir = data_dir / "config"

    for directory in (base_path, logs_dir, data_dir, models_dir, config_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return {
        "root": base_path,
        "logs": logs_dir,
        "data": data_dir,
        "models": models_dir,
        "config": config_dir,
    }


class RuntimeShell:
    """Manage SentientOS runtime services on Windows."""

    def __init__(self, config: Mapping[str, object]) -> None:
        self._config = dict(config)
        runtime_section = _ensure_runtime_config(self._config)
        self._runtime_root = Path(runtime_section.get("root") or "C:/SentientOS")
        ensure_runtime_dirs(self._runtime_root)

        self._log_path = self._runtime_root / "logs" / "runtime.log"
        self._logger = logging.getLogger("sentientos.runtime.shell")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        if not any(_handler_targets(self._log_path, handler) for handler in self._logger.handlers):
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(self._log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self._logger.addHandler(handler)

        persona_section = _ensure_persona_config(self._config)

        self._process_commands: Dict[str, Tuple[Tuple[str, ...], Dict[str, Optional[object]]]] = {}
        self._processes: Dict[str, subprocess.Popen[bytes]] = {}
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._running = False
        self._watchdog_interval = float(runtime_section.get("watchdog_interval", 5.0))
        self._windows_mode = bool(runtime_section.get("windows_mode", True))
        self._persona_enabled = bool(persona_section.get("enabled", True))
        self._persona_tick_interval = float(
            persona_section.get("tick_interval_seconds", DEFAULT_PERSONA_CONFIG["tick_interval_seconds"])
        )
        self._persona_max_message_length = int(
            persona_section.get("max_message_length", DEFAULT_PERSONA_CONFIG["max_message_length"])
        )
        self._persona_loop: Optional[PersonaLoop] = None
        self._log("RuntimeShell initialised", extra=runtime_section)

    @property
    def log_path(self) -> Path:
        return self._log_path

    @property
    def runtime_root(self) -> Path:
        return self._runtime_root

    def start(self) -> None:
        """Start all managed services in deterministic order."""

        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._log("Starting runtime shell")
        self.start_llama_server()
        self.start_relay()
        self.start_core()
        self._start_persona_loop()
        self._monitor_thread = threading.Thread(target=self.monitor_processes, daemon=True)
        self._monitor_thread.start()

    def start_llama_server(self) -> None:
        runtime = _ensure_runtime_config(self._config)
        llama_path = str(runtime.get("llama_server_path"))
        model_path = str(runtime.get("model_path"))
        command = [llama_path, "--model", model_path]
        self._register_process("llama", command)
        self._log("llama.cpp server launched", extra={"command": command})

    def start_relay(self) -> None:
        runtime = _ensure_runtime_config(self._config)
        host = str(runtime.get("relay_host", "127.0.0.1"))
        port = str(runtime.get("relay_port", 65432))
        command = [
            "python",
            "-m",
            "sentientos.oracle_relay",
            "--host",
            host,
            "--port",
            str(port),
        ]
        self._register_process("relay", command)
        self._log("Relay server launched", extra={"command": command})

    def start_core(self) -> None:
        """Start core daemons required for SentientOS."""

        integrity_cmd = [
            "python",
            "-m",
            "sentientos.daemons.integrity_daemon",
        ]
        scheduler_cmd = [
            "python",
            str(Path("autonomous_ops.py").resolve()),
        ]
        self._register_process("integrity_daemon", integrity_cmd)
        self._register_process("autonomous_ops", scheduler_cmd)
        self._log("Core daemons launched", extra={"daemons": list(self._processes.keys())})

    def _start_persona_loop(self) -> None:
        if not self._persona_enabled:
            return
        if not self._persona_loop:
            self._persona_loop = PersonaLoop(
                initial_state(),
                tick_interval_seconds=self._persona_tick_interval,
                event_source=collect_recent_events,
                max_message_length=self._persona_max_message_length,
            )
        self._persona_loop.start()
        self._log(
            "Persona loop launched",
            extra={
                "tick_interval_seconds": self._persona_tick_interval,
                "max_message_length": self._persona_max_message_length,
            },
        )

    def monitor_processes(self, run_once: bool = False) -> None:
        """Watch managed processes and restart on unexpected exit."""

        while not self._stop_event.is_set():
            with self._lock:
                items = list(self._processes.items())
            for name, process in items:
                if process.poll() is None:
                    continue
                exit_code = process.returncode
                self._log(
                    "Process exited; restarting",
                    extra={"process": name, "exit_code": exit_code},
                )
                self._spawn_process(name)
            if run_once:
                break
            self._stop_event.wait(self._watchdog_interval)

    def shutdown(self) -> None:
        """Stop the monitor and gracefully terminate processes."""

        if not self._running:
            return
        self._log("Shutdown requested")
        self._running = False
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=self._watchdog_interval * 2)
            self._monitor_thread = None
        if self._persona_loop:
            self._persona_loop.stop()
            self._persona_loop = None
        with self._lock:
            items = list(self._processes.items())
        for name, process in items:
            if process.poll() is not None:
                continue
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        self._log("Runtime shell stopped")

    def _register_process(
        self,
        name: str,
        command: Iterable[str],
        *,
        cwd: Optional[str | os.PathLike[str]] = None,
        env: Optional[MutableMapping[str, str]] = None,
    ) -> None:
        self._process_commands[name] = (
            tuple(command),
            {"cwd": cwd, "env": dict(env) if env else None},
        )
        self._spawn_process(name)

    def _spawn_process(self, name: str) -> None:
        command, options = self._process_commands[name]
        kwargs: Dict[str, object] = {}
        if options["cwd"] is not None:
            kwargs["cwd"] = options["cwd"]
        if options["env"] is not None:
            kwargs["env"] = options["env"]
        if os.name == "nt" or self._windows_mode:
            creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            kwargs["creationflags"] = creation_flags
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(list(command), **kwargs)
        with self._lock:
            self._processes[name] = process

    def _log(self, message: str, *, extra: Optional[Mapping[str, object]] = None) -> None:
        payload = {"message": message}
        if extra:
            payload.update(extra)
        self._logger.info(json.dumps(payload, sort_keys=True))


def _ensure_runtime_config(config: MutableMapping[str, object]) -> MutableMapping[str, object]:
    runtime_section = config.get("runtime", {})
    if not isinstance(runtime_section, Mapping):
        runtime_section = {}
    runtime = dict(runtime_section)
    updated = False
    for key, default in DEFAULT_RUNTIME_CONFIG.items():
        if key not in runtime:
            runtime[key] = default
            updated = True
    if "runtime" not in config or updated:
        config["runtime"] = runtime
    return runtime


def _ensure_persona_config(config: MutableMapping[str, object]) -> MutableMapping[str, object]:
    persona_section = config.get("persona", {})
    if not isinstance(persona_section, Mapping):
        persona_section = {}
    persona = dict(persona_section)
    updated = False
    for key, default in DEFAULT_PERSONA_CONFIG.items():
        if key not in persona:
            persona[key] = default
            updated = True
    if "persona" not in config or updated:
        config["persona"] = persona
    return persona


def load_or_init_config(path: Path) -> Dict[str, object]:
    """Load runtime configuration, writing defaults on first run."""

    if len(path.parents) >= 3:
        ensure_runtime_dirs(path.parents[2])
    else:
        ensure_runtime_dirs()
    existing_text = None
    if path.exists():
        try:
            existing_text = path.read_text(encoding="utf-8")
            data = json.loads(existing_text)
            if not isinstance(data, dict):
                data = {}
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    runtime = _ensure_runtime_config(data)
    persona = _ensure_persona_config(data)
    data["runtime"] = runtime
    data["persona"] = persona
    serialized = json.dumps(data, indent=2)
    if existing_text != serialized:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized, encoding="utf-8")
    return data


def _handler_targets(path: Path, handler: logging.Handler) -> bool:
    if not isinstance(handler, logging.FileHandler):
        return False
    handler_path = Path(getattr(handler, "baseFilename", ""))
    return handler_path == path
