"""Verify the narrow structural retirement of legacy actuator talkback."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import NoReturn


ROOT = Path(__file__).resolve().parents[1]


def _fail(message: str) -> NoReturn:
    raise SystemExit(f"actuator talkback retirement verification failed: {message}")


def main() -> int:
    actuator_path = ROOT / "api" / "actuator.py"
    bridge_path = ROOT / "talkback_bridge.py"
    actuator_source = actuator_path.read_text(encoding="utf-8")
    actuator_tree = ast.parse(actuator_source, filename=str(actuator_path))

    if any(isinstance(node, ast.ClassDef) and node.name == "TalkbackActuator" for node in ast.walk(actuator_tree)):
        _fail("active TalkbackActuator remains")
    assignments = [
        node for node in ast.walk(actuator_tree)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "BUILTIN_ACTUATOR_TYPES"
    ]
    if len(assignments) != 1:
        _fail("could not identify the built-in actuator registry")
    registry = assignments[0].value
    if not isinstance(registry, ast.Dict):
        _fail("could not identify the built-in actuator registry")
    keys = [key.value for key in registry.keys if isinstance(key, ast.Constant)]
    if "talkback" in keys:
        _fail("talkback remains in the built-in actuator registry")
    if any(isinstance(node, (ast.Import, ast.ImportFrom)) and any(alias.name == "talkback_bridge" for alias in node.names) for node in ast.walk(actuator_tree)):
        _fail("actuator imports the retired bridge")

    if not bridge_path.is_file():
        return 0
    bridge_source = bridge_path.read_text(encoding="utf-8")
    bridge_tree = ast.parse(bridge_source, filename=str(bridge_path))
    forbidden_names = {"subprocess", "Popen", "run", "shutil", "which", "getenv", "environ", "speak", "TemporaryDirectory"}
    used_names = {node.id for node in ast.walk(bridge_tree) if isinstance(node, ast.Name)}
    used_attributes = {node.attr for node in ast.walk(bridge_tree) if isinstance(node, ast.Attribute)}
    if forbidden_names & (used_names | used_attributes):
        _fail("compatibility bridge retains an effect or discovery API")
    forbidden_literals = ("CAMERA_TALKBACK_URL", "FFMPEG_BINARY", "rtsp://", "ffmpeg")
    if any(token in bridge_source for token in forbidden_literals):
        _fail("compatibility bridge retains endpoint or executable selection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
