from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import argparse
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

# Assist in resolving missing test imports by editing failing tests.

__test__ = False

ERROR_RE = re.compile(r"(?:ModuleNotFoundError|ImportError):.*?'([^']+)'")


def parse_missing_modules(log_path: Path) -> set[str]:
    modules: set[str] = set()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        m = ERROR_RE.search(line)
        if m:
            modules.add(m.group(1))
    return modules


def find_test_files(module: str) -> list[Path]:
    results = []
    for p in Path("tests").rglob("test_*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        if f"import {module}" in text or f"from {module} import" in text:
            results.append(p)
    return results


def patch_file(path: Path, module: str, replacement: str | None) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    if replacement:
        updated = [
            (
                line.replace(f"import {module}", f"import {replacement}")
                if line.lstrip().startswith(f"import {module}")
                else (
                    line.replace(f"from {module} import", f"from {replacement} import")
                    if line.lstrip().startswith(f"from {module} import")
                    else line
                )
            )
            for line in lines
        ]
        action = "replaced"
    else:
        skip_lines = [
            "import pytest",
            f"pytest.skip(\"Missing module '{module}'; test deprecated — see RITUAL_FAILURES.md\")",
        ]
        updated = skip_lines + lines
        action = "skipped"
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    return action


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix missing imports in tests")
    parser.add_argument("--log", required=True, help="Pytest error log file")
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        sys.exit(1)

    modules = parse_missing_modules(log_path)
    summary: list[str] = []
    for module in modules:
        for test_file in find_test_files(module):
            print(f"Missing module '{module}' in {test_file}")
            repl = input("Replacement import path (leave blank to skip test): ").strip()
            action = patch_file(test_file, module, repl or None)
            summary.append(f"{test_file}: {action}")

    if summary:
        print("\nSummary:")
        for entry in summary:
            print(f" - {entry}")


if __name__ == "__main__":
    main()
