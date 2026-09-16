from __future__ import annotations

import argparse
from pathlib import Path
import sys

from sentientos.historical_surface_disposition import build_inventory_report, dumps_report, load_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and report descriptive repository-surface dispositions.")
    parser.add_argument("--registry", default="architecture/historical_surface_dispositions.json")
    parser.add_argument("--workspace-root", default=".")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    registry, errors = load_registry(Path(args.registry))
    report = build_inventory_report(registry, Path(args.workspace_root), errors)
    rendered = dumps_report(report)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if report.valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
