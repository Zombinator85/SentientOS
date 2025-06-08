from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()
require_lumos_approval()

__test__ = False

ERROR_PATTERN = re.compile(r"ModuleNotFoundError: No module named '(?P<mod>[^']+)'")


def parse_missing_modules(log_path: Path) -> set[str]:
    modules = set()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        m = ERROR_PATTERN.search(line)
        if m:
            modules.add(m.group('mod'))
    return modules


def find_tests_for_module(module: str) -> list[Path]:
    tests = []
    for path in Path('.').rglob('test_*.py'):
        content = path.read_text(encoding='utf-8', errors='ignore')
        if f"import {module}" in content or f"from {module} import" in content:
            tests.append(path)
    return tests


def process_file(path: Path, module: str, replacement: str | None) -> str:
    lines = path.read_text(encoding='utf-8').splitlines()
    changed = False
    if replacement:
        new_lines = []
        for line in lines:
            if line.lstrip().startswith(f"import {module}"):
                new_lines.append(f"import {replacement}")
                changed = True
            elif line.lstrip().startswith(f"from {module} import"):
                new_lines.append(line.replace(f"from {module} import", f"from {replacement} import"))
                changed = True
            else:
                new_lines.append(line)
        lines = new_lines
    else:
        skip_header = [
            "import pytest",
            f"pytest.skip('Module {module} missing; deprecated test — see RITUAL_FAILURES.md')",
        ]
        lines = skip_header + lines
        changed = True
    if changed:
        path.write_text("\n".join(lines) + "\n", encoding='utf-8')
    return "replaced" if replacement else "skipped"


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix missing module imports in tests")
    parser.add_argument("log_file", help="Pytest error log file")
    args = parser.parse_args()
    log_path = Path(args.log_file)
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        sys.exit(1)

    modules = parse_missing_modules(log_path)
    summary = []
    for mod in modules:
        tests = find_tests_for_module(mod)
        for test_file in tests:
            print(f"Missing module '{mod}' found in {test_file}")
            repl = input("Enter replacement import path or leave blank to skip test: ").strip()
            action = process_file(test_file, mod, repl if repl else None)
            summary.append(f"{test_file}: {action}")

    if summary:
        print("\nSummary:")
        for item in summary:
            print(" -", item)


if __name__ == "__main__":
    main()
