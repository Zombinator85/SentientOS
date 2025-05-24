import argparse
import os
import time
from pathlib import Path


def tail_file(path: Path, delay: float = 1.0) -> None:
    """Print new lines as they are written to the given file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    with path.open("r", encoding="utf-8") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(delay)
                continue
            print(line.rstrip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Tail a memory log file")
    parser.add_argument(
        "--file",
        default="logs/memory.jsonl",
        help="Path to the log file to tail",
    )
    args = parser.parse_args()
    tail_file(Path(args.file))


if __name__ == "__main__":
    main()
