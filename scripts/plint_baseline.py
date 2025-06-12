#!/usr/bin/env python3
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()


import json
from pathlib import Path

from privilege_lint import (  # type: ignore[attr-defined]  # optional local module
    PrivilegeLinter,
    iter_py_files,
)
from privilege_lint.runner import parallel_validate


def main() -> None:
    linter = PrivilegeLinter()
    files = iter_py_files([str(Path.cwd())])
    issues = parallel_validate(linter, files)
    baseline = {msg: True for msg in sorted(issues)}
    Path(".plint_baseline.json").write_text(json.dumps(baseline, indent=2))
    print(f"Baseline written with {len(baseline)} entries")


if __name__ == "__main__":
    main()
