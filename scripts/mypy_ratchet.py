from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys

BASELINE_PATH = Path("glow/contracts/mypy_baseline.json")
STATUS_PATH = Path("glow/forge/ratchets/mypy_ratchet_status.json")
RATCHET_LOG_PATH = Path("pulse/ratchets.jsonl")
DEFAULT_TARGETS = ["scripts", "sentientos"]
STRICT_SUBSET_PREFIXES = ("sentientos/forge", "sentientos/cathedral_forge.py", "sentientos/forge_")
ERROR_PATTERN = re.compile(
    r"^(?P<path>[^:\n]+):(?P<line>\d+):(?P<column>\d+):\s+(?P<severity>error|note):\s+(?P<message>.+?)(?:\s+\[(?P<code>[^\]]+)\])?$"
)


@dataclass(frozen=True)
class MypyError:
    path: str
    line: int
    column: int
    message: str
    code: str

    def signature(self) -> str:
        return f"{self.path}:{self.line}:{self.column}:{self.code}:{self.message}"

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "code": self.code,
            "signature": self.signature(),
        }


def parse_mypy_output(stdout: str) -> list[MypyError]:
    errors: list[MypyError] = []
    for raw in stdout.splitlines():
        match = ERROR_PATTERN.match(raw.strip())
        if match is None or match.group("severity") != "error":
            continue
        errors.append(
            MypyError(
                path=match.group("path"),
                line=int(match.group("line")),
                column=int(match.group("column")),
                message=match.group("message"),
                code=match.group("code") or "",
            )
        )
    return sorted(errors, key=lambda item: (item.path, item.line, item.column, item.code, item.message))


def build_baseline(errors: list[MypyError]) -> dict[str, object]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for error in errors:
        grouped.setdefault(error.path, []).append(error.to_dict())
    return {
        "schema_version": 1,
        "targets": DEFAULT_TARGETS,
        "error_count": len(errors),
        "errors_by_module": {path: grouped[path] for path in sorted(grouped)},
    }




def _write_status(payload: dict[str, object]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_ratchet_event(payload: dict[str, object]) -> None:
    RATCHET_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {"ratchet": "mypy", **payload}
    with RATCHET_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")

def _run_mypy(targets: list[str]) -> tuple[int, str]:
    command = [
        sys.executable,
        "-m",
        "mypy",
        "--hide-error-context",
        "--no-color-output",
        "--show-column-numbers",
        "--show-error-codes",
        *targets,
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    stdout = completed.stdout.strip()
    if completed.stderr.strip():
        stdout = f"{stdout}\n{completed.stderr.strip()}" if stdout else completed.stderr.strip()
    return completed.returncode, stdout


def _changed_python_files(repo_root: Path, diff_base: str | None) -> list[str]:
    if diff_base:
        cmd = ["git", "diff", "--name-only", "--diff-filter=AMR", f"{diff_base}...HEAD", "--", "*.py"]
    else:
        cmd = ["git", "diff", "--name-only", "--diff-filter=AMR", "--", "*.py"]
    completed = subprocess.run(cmd, cwd=repo_root, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return []
    files = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return sorted(path for path in files if Path(path).exists())


def _strict_touched_subset(paths: list[str]) -> list[str]:
    return [path for path in paths if path.startswith(STRICT_SUBSET_PREFIXES)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mypy debt ratchet: fail only on new type errors vs baseline.")
    parser.add_argument("--baseline", default=str(BASELINE_PATH))
    parser.add_argument("--refresh", action="store_true", help="Refresh and write baseline from current mypy output.")
    parser.add_argument("--touched-surface", action="store_true", help="Run mypy on changed Python files in this branch.")
    parser.add_argument("--diff-base", default=os.getenv("SENTIENTOS_MYPY_DIFF_BASE"))
    args = parser.parse_args(argv)

    repo_root = Path.cwd()
    baseline_path = Path(args.baseline)

    targets = list(DEFAULT_TARGETS)
    touched: list[str] = []
    strict_subset: list[str] = []
    if args.touched_surface:
        touched = _changed_python_files(repo_root, args.diff_base)
        if touched:
            targets = touched
            strict_subset = _strict_touched_subset(touched)

    _, output = _run_mypy(targets)
    errors = parse_mypy_output(output)

    if args.refresh:
        if os.getenv("SENTIENTOS_ALLOW_BASELINE_REFRESH") != "1":
            print(json.dumps({"status": "error", "reason": "SENTIENTOS_ALLOW_BASELINE_REFRESH=1 required for --refresh"}, sort_keys=True))
            return 2
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline = build_baseline(errors)
        baseline_path.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        status_payload = {"status": "baseline_refreshed", "baseline_path": str(baseline_path), "error_count": len(errors)}
        _write_status(status_payload)
        _append_ratchet_event(status_payload)
        print(json.dumps(status_payload, sort_keys=True))
        return 0

    if not baseline_path.exists():
        print(json.dumps({"status": "error", "reason": f"baseline not found: {baseline_path}"}, sort_keys=True))
        return 2

    baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_modules = baseline_payload.get("errors_by_module", {})
    baseline_signatures = {
        str(item.get("signature"))
        for rows in baseline_modules.values()
        if isinstance(rows, list)
        for item in rows
        if isinstance(item, dict)
    }
    current_signatures = {row.signature() for row in errors}
    new_signatures = sorted(current_signatures - baseline_signatures)

    result: dict[str, object] = {
        "status": "ok" if not new_signatures else "new_errors",
        "target_scope": "touched_surface" if args.touched_surface and touched else "repo_wide",
        "checked_targets": targets,
        "new_error_count": len(new_signatures),
        "new_errors": new_signatures[:200],
    }
    if strict_subset:
        strict_code, strict_out = _run_mypy(["--strict", "--follow-imports=skip", *strict_subset])
        result["strict_subset_checked"] = strict_subset
        result["strict_subset_status"] = "ok" if strict_code == 0 else "failed"
        if strict_code != 0:
            result["strict_subset_excerpt"] = strict_out.splitlines()[:10]
    _write_status(result)
    _append_ratchet_event(result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if new_signatures else 0


if __name__ == "__main__":
    raise SystemExit(main())
