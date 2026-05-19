from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.mypy_baseline_common import (
    BASELINE_PATH,
    DEFAULT_MYPY_COMMAND,
    STATUS_INVALID,
    STATUS_MISSING,
    compare_records,
    load_manifest,
    manifest_records,
    parse_mypy_output,
)


def _run_command(command: list[str]) -> str:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    output = completed.stdout
    if completed.stderr:
        output = f"{output}\n{completed.stderr}" if output else completed.stderr
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare current repo-wide mypy output against the deterministic baseline.")
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH, help="Baseline manifest path to read.")
    parser.add_argument("--current-output-file", type=Path, help="Read current mypy output instead of invoking mypy.")
    parser.add_argument("--summary", type=Path, help="Optional path for reviewer summary JSON.")
    parser.add_argument("targets", nargs="*", help="Override mypy targets/flags after 'python -m mypy'.")
    args = parser.parse_args(argv)

    if not args.baseline.exists():
        summary = {"status": STATUS_MISSING, "baseline": str(args.baseline)}
        print(json.dumps(summary, sort_keys=True))
        return 2
    try:
        manifest = load_manifest(args.baseline)
    except ValueError as exc:
        summary = {"status": STATUS_INVALID, "baseline": str(args.baseline), "reason": str(exc)}
        print(json.dumps(summary, sort_keys=True))
        return 2

    command = list(DEFAULT_MYPY_COMMAND if not args.targets else (sys.executable, "-m", "mypy", *args.targets))
    output = args.current_output_file.read_text(encoding="utf-8") if args.current_output_file is not None else _run_command(command)
    result = compare_records(baseline_records=manifest_records(manifest), current_records=parse_mypy_output(output))
    summary = {
        "status": result["status"],
        "baseline": str(args.baseline),
        "baseline_digest": manifest["digest"],
        "mypy_command": manifest.get("mypy_command", list(DEFAULT_MYPY_COMMAND)),
        "matched_existing_errors": result["matched_existing_errors"],
        "new_errors": result["new_errors"],
        "retired_errors": result["retired_errors"],
        "matched_with_location_drift": result["matched_with_location_drift"],
        "drifted_files": result["drifted_files"],
        "affected_new_files": result["affected_new_files"],
    }
    if result["new_errors"]:
        summary["new_error_records"] = result["new_error_records"]
    if result["retired_errors"]:
        summary["retired_error_records"] = result["retired_error_records"]
    text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.summary is not None:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(text, encoding="utf-8")
    return 1 if result["new_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
