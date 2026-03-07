from __future__ import annotations

import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    completed = subprocess.run([sys.executable, "-m", "sentientos.audit_tools", *args], check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
