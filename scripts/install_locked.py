import argparse
import os
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Install from lock files")
    parser.add_argument("mode", choices=["bin", "src"], help="which lock file to install")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    lock = root / f"lock-{args.mode}.txt"
    if not lock.exists():
        print(f"lock file not found: {lock}", file=sys.stderr)
        sys.exit(1)

    if not os.environ.get("CI"):
        print(f"Installing from {lock.name}; this helper is mostly for CI.")

    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(lock)])
    subprocess.check_call([sys.executable, "-m", "pip", "install", str(root)])


if __name__ == "__main__":  # pragma: no cover
    main()
