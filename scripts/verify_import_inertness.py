#!/usr/bin/env python3
"""Verify selected imports are inert in isolated Python interpreters."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

SCHEMA_VERSION = "sentientos.import_inertness:v1"
MODULES = (
    "sentientos", "scripts.lock", "api", "api.actuator",
    "integration_memory", "codex", "codex.integrity_daemon", "codex.strategy",
    "memory_manager", "curiosity_goal_helper", "curiosity_executor",
    "emotion_memory", "emotion_utils", "semantic_embeddings", "memory_governor", "node_registry",
    "capability_ledger", "cathedral_const", "sentient_autonomy",
    "sentientos.autonomy.curiosity_loop", "sentientos.autonomy.runtime",
    "sentientos.hosted_validation_evidence",
)
CAPTURE_LIMIT = 4096

_CHILD = r'''
import builtins, importlib, importlib.abc, io, json, logging, logging.config, os, pathlib, socket, subprocess, sys, threading, traceback
module, module_root, state_root = sys.argv[1:]
sys.path.insert(0, module_root)
root = pathlib.Path(state_root)
log_dir = root / "logs"
sandbox = root / "sandbox"
plugins = root / "plugins"
marker = root / "plugin-executed.marker"
autonomous = root / "autonomous.jsonl"
os.environ.update({
    "SENTIENTOS_LOG_DIR": str(log_dir),
    "ACT_SANDBOX": str(sandbox),
    "ACT_PLUGINS_DIR": str(plugins),
    "AUTONOMOUS_CALLS_LOG": str(autonomous),
    "EXPERIMENTS_FILE": str(root / "experiments.json"),
    "EXPERIMENT_AUDIT_FILE": str(root / "experiment_audit.jsonl"),
    "INTEGRATION_ROOT": str(root / "integration"),
    "MEMORY_DIR": str(root / "memory"),
    "SENTIENTOS_DATA_DIR": str(root / "data"),
    "IMPORT_INERTNESS_PLUGIN_MARKER": str(marker),
})
# Startup markers are deliberately absent in every import probe. Inherit neither
# an earlier bootstrap's state nor ambient Cloud state as evidence of inertness.
os.environ.pop("CODEX_STARTUP_ROOT_PID", None)
os.environ.pop("CODEX_STARTUP_FINALIZED", None)
invoked = []
effects = []
environment_before = dict(os.environ)
error = None
try:
    privilege = importlib.import_module("sentientos.privilege")
    admin_utils = importlib.import_module("sentientos.admin_utils")
    def guard(name):
        def fail(*args, **kwargs):
            invoked.append(name)
            raise RuntimeError("import privilege sentinel invoked: " + name)
        return fail
    for target in (privilege, admin_utils):
        for name in ("require_admin_banner", "require_lumos_approval", "require_covenant_alignment", "require_admin"):
            if hasattr(target, name):
                setattr(target, name, guard(name))
except BaseException:
    error = traceback.format_exc(limit=8)

def effect(name):
    def fail(*args, **kwargs):
        effects.append(name)
        raise RuntimeError("import effect sentinel invoked: " + name)
    return fail

if error is None:
    try:
        class GuardModelAndProviderImports(importlib.abc.MetaPathFinder):
            blocked = ("sentence_transformers", "transformers", "torch", "openai", "anthropic", "boto3")
            def find_spec(self, fullname, path=None, target=None):
                if any(fullname == name or fullname.startswith(name + ".") for name in self.blocked):
                    effects.append("model_or_provider_import:" + fullname)
                    raise RuntimeError("model/provider import sentinel invoked: " + fullname)
                return None
        sys.meta_path.insert(0, GuardModelAndProviderImports())
        pathlib.Path.mkdir = effect("filesystem.mkdir")
        original_path_write_text = pathlib.Path.write_text
        def guarded_path_write_text(path, data, *args, **kwargs):
            if path == marker:
                return original_path_write_text(path, data, *args, **kwargs)
            return effect("filesystem.path_write")(path, data, *args, **kwargs)
        pathlib.Path.write_text = guarded_path_write_text
        pathlib.Path.write_bytes = effect("filesystem.path_write")
        pathlib.Path.unlink = effect("filesystem.unlink")
        os.mkdir = effect("filesystem.mkdir")
        os.makedirs = effect("filesystem.makedirs")
        os.remove = effect("filesystem.remove")
        original_io_open = io.open
        def guarded_io_open(file, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+") and pathlib.Path(file) != marker:
                return effect("filesystem.io_open")(file, mode, *args, **kwargs)
            return original_io_open(file, mode, *args, **kwargs)
        io.open = guarded_io_open
        original_open = builtins.open
        def guarded_open(file, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+"):
                return effect("filesystem.open_write")(file, mode, *args, **kwargs)
            return original_open(file, mode, *args, **kwargs)
        builtins.open = guarded_open
        threading.Thread.start = effect("thread.start")
        subprocess.Popen.__init__ = effect("process.start")
        socket.socket.connect = effect("network.connect")
        socket.socket.send = effect("network.send")
        socket.socket.sendto = effect("network.send")
        logging.basicConfig = effect("logging.configure")
        logging.config.dictConfig = effect("logging.configure")
    except BaseException:
        error = traceback.format_exc(limit=8)
try:
    if error is None:
        importlib.import_module(module)
except BaseException:
    error = traceback.format_exc(limit=8)
created = [str(p.relative_to(root)) for p in (log_dir, sandbox, autonomous) if p.exists()]
print(json.dumps({
    "module": module,
    "imported": error is None,
    "error": error,
    "privilege_invoked": invoked,
    "effects_invoked": effects,
    "environment_changes": {
        name: {"before_present": name in environment_before, "after_present": name in os.environ}
        for name in sorted(set(environment_before) | set(os.environ))
        if environment_before.get(name) != os.environ.get(name)
    },
    "created_paths": created,
    "plugin_marker_exists": marker.exists(),
}, sort_keys=True))
sys.exit(0 if error is None else 1)
'''


def _sha(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def _bounded(value: str) -> str:
    return value[:CAPTURE_LIMIT]


def verify(module_root: Path, modules: tuple[str, ...] = MODULES) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="sentientos-import-inertness-") as temp:
            base = Path(temp)
            for index, module in enumerate(modules):
                state = base / str(index)
                plugins = state / "plugins"
                plugins.mkdir(parents=True)
                marker = state / "plugin-executed.marker"
                (plugins / "sentinel.py").write_text(
                    "import os\nfrom pathlib import Path\n"
                    "Path(os.environ['IMPORT_INERTNESS_PLUGIN_MARKER']).write_text('executed')\n",
                    encoding="utf-8",
                )
                completed = subprocess.run(
                    [sys.executable, "-c", _CHILD, module, str(module_root), str(state)],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                parsed: dict[str, Any]
                try:
                    line = completed.stdout.strip().splitlines()[-1]
                    parsed = json.loads(line)
                except (IndexError, json.JSONDecodeError):
                    parsed = {
                        "module": module,
                        "imported": False,
                        "error": "child emitted no canonical result",
                        "privilege_invoked": [],
                        "effects_invoked": [],
                        "environment_changes": {},
                        "created_paths": [],
                        "plugin_marker_exists": marker.exists(),
                    }
                parsed.update(
                    return_code=completed.returncode,
                    stdout=_bounded(completed.stdout),
                    stderr=_bounded(completed.stderr),
                )
                results.append(parsed)
    except BaseException as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "repository_sha": _sha(module_root),
            "python_version": sys.version,
            "status": "verifier_error",
            "error": f"{type(exc).__name__}: {exc}",
            "module_results": results,
        }

    status = "import_inertness_ready"
    if any(result["plugin_marker_exists"] for result in results):
        status = "plugin_executed"
    elif any(result["privilege_invoked"] for result in results):
        status = "privilege_invoked"
    elif any(result["effects_invoked"] for result in results):
        status = "runtime_effect_invoked"
    elif any(result["environment_changes"] for result in results):
        status = "runtime_effect_invoked"
    elif any(result["created_paths"] for result in results):
        status = "filesystem_mutated"
    elif any(not result["imported"] or result["return_code"] != 0 for result in results):
        status = "import_failed"
    return {
        "schema_version": SCHEMA_VERSION,
        "repository_sha": _sha(module_root),
        "python_version": sys.version,
        "status": status,
        "module_results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("glow/test_runs/import_inertness.json"))
    parser.add_argument("--module-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--module", action="append", dest="modules", help="Module to import; may be repeated")
    args = parser.parse_args()
    result = verify(args.module_root.resolve(), tuple(args.modules) if args.modules else MODULES)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["status"] == "import_inertness_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
