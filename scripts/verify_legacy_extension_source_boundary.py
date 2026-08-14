"""Narrow static verifier for the retired legacy extension authority boundary."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOADERS = (ROOT / "plugin_bus.py", ROOT / "sentientos" / "plugin_loader.py")


def verify() -> list[str]:
    failures: list[str] = []
    forbidden_attributes = {"spec_from_file_location", "exec_module", "reload", "entry_points"}
    for path in LOADERS:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        used = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        used.update(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
        for name in sorted(forbidden_attributes & used):
            failures.append(f"{path.relative_to(ROOT)} uses retired activation primitive {name}")
        if 'glob("*.py")' in source or "glob('*.py')" in source:
            failures.append(f"{path.relative_to(ROOT)} discovers Python directory contents")
        if "watchdog" in source:
            failures.append(f"{path.relative_to(ROOT)} retains executable watcher machinery")

    metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if '[project.entry-points."sentientos.plugins"]' in metadata:
        failures.append("pyproject.toml retains the retired sentientos.plugins entry-point group")
    return failures


def main() -> int:
    failures = verify()
    if failures:
        print("\n".join(failures))
        return 1
    print("legacy_extension_source_boundary_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
