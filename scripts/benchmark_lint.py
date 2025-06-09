from __future__ import annotations

import time
from pathlib import Path

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()

from privilege_lint import PrivilegeLinter, iter_py_files
from privilege_lint.runner import parallel_validate


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
    print(f"Cold: {cold:.2f}s, Warm: {warm:.2f}s, cache hit ratio {hit_ratio:.2f}")


if __name__ == "__main__":
    main()

