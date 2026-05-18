from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.mypy_baseline_common import BASELINE_PATH, DEFAULT_MYPY_COMMAND, build_manifest, manifest_to_text, parse_mypy_output


def _run_command(command: list[str]) -> tuple[int, str]:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    output = completed.stdout
    if completed.stderr:
        output = f"{output}\n{completed.stderr}" if output else completed.stderr
    return completed.returncode, output


def _mypy_version() -> str:
    completed = subprocess.run([sys.executable, "-m", "mypy", "--version"], check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return "unknown"
    return completed.stdout.strip() or "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or refresh the deterministic repo-wide mypy baseline manifest.")
    parser.add_argument("--output", type=Path, default=BASELINE_PATH, help="Baseline manifest path to write.")
    parser.add_argument("--mypy-output-file", type=Path, help="Read existing mypy output instead of invoking mypy.")
    parser.add_argument("--print", action="store_true", help="Print the manifest instead of writing it.")
    parser.add_argument("targets", nargs="*", help="Override mypy targets/flags after 'python -m mypy'.")
    args = parser.parse_args(argv)

    if args.mypy_output_file is not None:
        output = args.mypy_output_file.read_text(encoding="utf-8")
        command = list(DEFAULT_MYPY_COMMAND if not args.targets else ("python", "-m", "mypy", *args.targets))
    else:
        command = list(DEFAULT_MYPY_COMMAND if not args.targets else (sys.executable, "-m", "mypy", *args.targets))
        _, output = _run_command(command)

    manifest = build_manifest(records=parse_mypy_output(output), mypy_command=command, mypy_version=_mypy_version())
    text = manifest_to_text(manifest)
    if args.print:
        print(text, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        summary = {
            "status": "mypy_baseline_refreshed",
            "baseline": str(args.output),
            "total_error_count": manifest["total_error_count"],
            "affected_file_count": manifest["affected_file_count"],
            "digest": manifest["digest"],
        }
        print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
