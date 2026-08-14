"""Mechanically verify plugin-framework external source activation is absent."""

from __future__ import annotations

import ast
import json
from pathlib import Path


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def verify(root: Path = Path(".")) -> dict[str, object]:
    framework_path = root / "plugin_framework.py"
    registry_path = root / "sentientos/plugin_builtin_registry.py"
    cli_path = root / "plugins_cli.py"
    framework = framework_path.read_text(encoding="utf-8")
    registry = registry_path.read_text(encoding="utf-8")
    cli = cli_path.read_text(encoding="utf-8")
    tree = ast.parse(framework, filename=str(framework_path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) in {
            "glob", "rglob", "spec_from_file_location", "exec_module", "module_from_spec"
        }:
            violations.append(f"dynamic_source_call:{_call_name(node)}:{node.lineno}")
    for token in ("GP_PLUGINS_DIR", "_LOADED_FILES", "source_text"):
        if token in framework:
            violations.append(f"retired_framework_surface:{token}")
    if "BUILTIN_PLUGIN_NAMES = (\"wave_hand\",)" not in registry:
        violations.append("missing_explicit_builtin_inventory")
    if "from gp_plugins.wave_hand import WaveHandPlugin" not in registry:
        violations.append("missing_static_wave_hand_import")
    if "import_module(" in registry or "GP_PLUGINS_DIR" in registry:
        violations.append("dynamic_registry_surface")
    if "pf.initialize_plugins()" not in cli or "pf.load_plugins()" in cli:
        violations.append("cli_not_builtin_initialized")
    return {
        "status": "plugin_source_boundary_ready" if not violations else "plugin_source_boundary_blocked",
        "violations": violations,
    }


def main() -> int:
    result = verify()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "plugin_source_boundary_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
