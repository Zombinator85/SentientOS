from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.ci_baseline import CI_BASELINE_PATH, emit_ci_baseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit CI baseline contract artifact.")
    parser.add_argument("--output", type=Path, default=CI_BASELINE_PATH)
    args = parser.parse_args(argv)

    snapshot = emit_ci_baseline(output_path=args.output)
    print(
        json.dumps(
            {
                "tool": "emit_ci_baseline",
                "output": str(args.output),
                "passed": snapshot.passed,
                "failed_count": snapshot.failed_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
