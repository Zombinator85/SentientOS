from __future__ import annotations

import argparse
from pathlib import Path

from sentientos.remote_bundle import export_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export deterministic remote probe bundle")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--last-n", type=int, default=25)
    args = parser.parse_args(argv)

    bundle = export_bundle(Path.cwd().resolve(), Path(args.out), last_n=max(1, args.last_n))
    print(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
