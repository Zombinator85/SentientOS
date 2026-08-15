"""Narrow static verification for the actuator file-write custody boundary."""

from __future__ import annotations

import ast
import json
from pathlib import Path


REQUIRED_CALLS = {"_open_sandbox_root", "fstat", "ftruncate", "write"}


def verify(path: Path = Path("api/actuator.py")) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "file_write"
    )
    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
    names = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in calls
        if isinstance(node.func, (ast.Name, ast.Attribute))
    }
    violations: list[str] = []
    for required in sorted(REQUIRED_CALLS - names):
        violations.append(f"missing_descriptor_operation:{required}")
    open_calls = [node for node in calls if isinstance(node.func, ast.Attribute) and node.func.attr == "open"]
    if not open_calls or not all(any(keyword.arg == "dir_fd" for keyword in node.keywords) for node in open_calls):
        violations.append("final_open_not_descriptor_relative")
    source = ast.get_source_segment(path.read_text(encoding="utf-8"), function) or ""
    for forbidden in ("Path.write_text", "target.parent.mkdir", "_safe_path("):
        if forbidden in source:
            violations.append(f"insecure_pathname_authority:{forbidden}")
    if "O_NOFOLLOW" not in source:
        violations.append("missing_final_no_follow")
    if "_descriptor_file_write_supported" not in source or "raise RuntimeError" not in source:
        violations.append("missing_unsupported_platform_fail_closed")
    return {
        "status": "actuator_file_descriptor_custody_ready" if not violations else "actuator_file_descriptor_custody_blocked",
        "path": str(path),
        "violations": violations,
    }


def main() -> int:
    result = verify()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "actuator_file_descriptor_custody_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
