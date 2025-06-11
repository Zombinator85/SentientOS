from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()

import time
import subprocess
from pathlib import Path

from sentientos.privilege import require_admin_banner, require_lumos_approval


from privilege_lint import PrivilegeLinter, iter_py_files
from privilege_lint.runner import parallel_validate, iter_data_files
from privilege_lint.typing_rules import run_incremental


def main(path: str = ".") -> None:
    files = iter_py_files([path])
    linter = PrivilegeLinter()
    start = time.time()
    parallel_validate(linter, files)
    cold = time.time() - start

    start = time.time()
    parallel_validate(linter, files)
    warm = time.time() - start
    hit_ratio = 1 - len([f for f in files if not linter.cache.is_valid(f)]) / len(files)

    _, checked = run_incremental(files, linter.cache, strict=linter.config.mypy_strict)
    data_files = iter_data_files(linter.config.data_paths)

    start = time.time()
    subprocess.run(['bash', 'scripts/precommit_privilege.sh'], check=True)
    hook_time = time.time() - start

    print(
        f"Cold: {cold:.2f}s, Warm: {warm:.2f}s, cache hit {hit_ratio:.2f}, mypy {len(checked)} files, data {len(data_files)}, pre-commit {hook_time:.2f}s"
    )


if __name__ == "__main__":
    main()

