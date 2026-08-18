"""Verify Household Presence metadata reflects retired generic camera talkback."""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
from typing import NoReturn


ROOT = Path(__file__).resolve().parents[1]


def _fail(message: str) -> NoReturn:
    raise SystemExit(f"household talkback reconciliation verification failed: {message}")


def main() -> int:
    inventory_source = (ROOT / "sentientos/household_presence_sensor_inventory.py").read_text(encoding="utf-8")
    readiness_source = (ROOT / "sentientos/household_presence_camera_live_adapter_readiness.py").read_text(encoding="utf-8")
    inventory_tree = ast.parse(inventory_source)
    readiness_tree = ast.parse(readiness_source)
    literals = {
        node.value
        for tree in (inventory_tree, readiness_tree)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    if "existing_talkback_surface" in literals:
        _fail("readiness retains an active talkback surface class")
    if "talkback_boundary_risk" in literals:
        _fail("readiness retains the retired risk input")
    if "retired_compatibility_surface" not in literals:
        _fail("retired compatibility classification is absent")
    if "speaker_output_boundary_risk" not in literals:
        _fail("future speaker output boundary risk is absent")
    if not all(term in inventory_source for term in ("typed speaker renderer", "media-runtime", "output-transport")):
        _fail("future typed speaker/media-output boundary is incomplete")

    talkback_entries = [
        node for node in ast.walk(inventory_tree)
        if isinstance(node, ast.Call)
        and any(isinstance(arg, ast.Constant) and arg.value == "talkback_bridge.py" for arg in node.args)
    ]
    if len(talkback_entries) != 1:
        _fail("expected one explicit talkback compatibility inventory entry")
    entry_literals = {arg.value for arg in talkback_entries[0].args if isinstance(arg, ast.Constant)}
    if {"existing_live_surface", "live_runtime", "speaker_output"} & entry_literals:
        _fail("retired bridge retains live or speaker capability metadata")

    retired = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify_actuator_talkback_retirement.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if retired.returncode != 0:
        _fail(f"dedicated retirement verifier failed: {retired.stderr or retired.stdout}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
