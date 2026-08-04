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
MODULES = ("sentientos", "scripts.lock", "api", "api.actuator")
CAPTURE_LIMIT = 4096

_CHILD = r'''
import importlib, json, os, pathlib, sys, traceback
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
    "IMPORT_INERTNESS_PLUGIN_MARKER": str(marker),
})
invoked = []
error = None
if module in {"api", "api.actuator"}:
    try:
        privilege = importlib.import_module("sentientos.privilege")
        def sentinel(name):
            def fail(*args, **kwargs):
                invoked.append(name)
                raise RuntimeError("import privilege sentinel invoked: " + name)
            return fail
        privilege.require_admin_banner = sentinel("require_admin_banner")
        privilege.require_lumos_approval = sentinel("require_lumos_approval")
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


def verify(module_root: Path) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="sentientos-import-inertness-") as temp:
            base = Path(temp)
            for index, module in enumerate(MODULES):
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
    args = parser.parse_args()
    result = verify(args.module_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["status"] == "import_inertness_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
