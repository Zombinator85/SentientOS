from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import pytest

from tests.privilege_surface import (
    PRIVILEGED_IMPORT_ALLOWLIST,
    PRIVILEGED_MODULE_PREFIXES,
)

pytestmark = pytest.mark.no_legacy_skip

REPO_ROOT = Path(__file__).resolve().parents[1]
PULSE_FORBIDDEN_IMPORT_PREFIXES = (
    "sentientos.admission",
    "sentientos.authorization",
    "sentientos.executor",
    "sentientos.control",
    "sentientos.daemon",
    "sentientos.daemons",
    "task_admission",
    "task_executor",
    "control_plane",
    "daemon",
)

SAFE_CLI_FORBIDDEN_PREFIXES = (
    "sentientos.privilege",
    "privilege_lint",
    "task_executor",
    "task_admission",
    "control_plane",
    "sentientos.local_model",
    "model_bridge",
)


def _matches_prefix(name: str, prefixes: Iterable[str]) -> bool:
    return any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes)


def _iter_python_files(root: Path, *, exclude_parts: Iterable[str] = ()) -> Iterable[Path]:
    exclude = set(exclude_parts)
    for path in root.rglob("*.py"):
        if any(part in exclude for part in path.parts):
            continue
        yield path


def _parse_imports(path: Path) -> set[str]:
    imports: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _find_privileged_import_offenders(
    paths: Iterable[Path],
    *,
    root: Path = REPO_ROOT,
) -> dict[str, set[str]]:
    offenders: dict[str, set[str]] = {}
    for path in paths:
        imports = _parse_imports(path)
        privileged = {name for name in imports if _matches_prefix(name, PRIVILEGED_MODULE_PREFIXES)}
        if privileged:
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                relative = path.as_posix()
            if relative not in PRIVILEGED_IMPORT_ALLOWLIST:
                offenders[relative] = privileged
    return offenders


def test_pulse_imports_never_touch_control_plane() -> None:
    pulse_dir = REPO_ROOT / "sentientos" / "pulse"
    assert pulse_dir.is_dir(), "pulse package missing"
    offenders: dict[str, set[str]] = {}

    for path in pulse_dir.glob("*.py"):
        imports = _parse_imports(path)
        forbidden = {name for name in imports if _matches_prefix(name, PULSE_FORBIDDEN_IMPORT_PREFIXES)}
        if forbidden:
            offenders[path.name] = forbidden

    assert not offenders, f"pulse imports forbidden control-plane modules: {offenders}"


def _run_cli_and_capture_forbidden(argv: list[str]) -> list[str]:
    payload = json.dumps(
        {"argv": argv, "forbidden": SAFE_CLI_FORBIDDEN_PREFIXES},
    )
    script = """
import json
import os
import sys

payload = json.loads(os.environ["SENTIENTOS_CLI_IMPORT_PAYLOAD"])
argv = payload["argv"]
forbidden = payload["forbidden"]

from sentientos import __main__ as sentientos_main

try:
    sentientos_main.main(argv)
except SystemExit:
    pass

loaded = [
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(f"{prefix}.") for prefix in forbidden)
]
print(json.dumps(sorted(loaded)))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["SENTIENTOS_CLI_IMPORT_PAYLOAD"] = payload
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    stdout = result.stdout.strip().splitlines()
    if not stdout:
        return []
    return json.loads(stdout[-1])


@pytest.mark.parametrize("argv", [["--help"], ["status"], ["doctor"], ["--version"]])
def test_safe_cli_commands_never_import_privileged_modules(argv: list[str]) -> None:
    loaded = _run_cli_and_capture_forbidden(argv)
    assert not loaded, f"safe CLI command imported privileged modules: {loaded}"


def test_privileged_surface_allowlist_is_enforced() -> None:
    paths = _iter_python_files(REPO_ROOT, exclude_parts=("tests", "__pycache__"))
    offenders = _find_privileged_import_offenders(paths, root=REPO_ROOT)
    assert not offenders, f"unexpected privileged imports: {offenders}"


def test_privileged_surface_rejects_accidental_import(tmp_path: Path) -> None:
    rogue = tmp_path / "helper.py"
    rogue.write_text("import task_executor\n", encoding="utf-8")
    offenders = _find_privileged_import_offenders([rogue], root=tmp_path)
    assert offenders, "expected privileged import to be rejected"
