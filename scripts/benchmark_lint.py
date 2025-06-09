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
    dur = time.time() - start
    print(f"Linted {len(files)} files in {dur:.2f}s")


if __name__ == "__main__":
    main()
