from __future__ import annotations

import argparse
from dataclasses import dataclass
from fnmatch import fnmatch
import json
import os
from pathlib import Path
import re
import subprocess
import sys

BASELINE_PATH = Path("glow/contracts/mypy_baseline.json")
POLICY_PATH = Path("glow/contracts/mypy_policy.json")
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

    def stable_signature(self) -> str:
        return f"{self.path}:{self.code}:{self.message}"

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "code": self.code,
            "signature": self.signature(),
            "stable_signature": self.stable_signature(),
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
    by_code: dict[str, int] = {}
    for error in errors:
        grouped.setdefault(error.path, []).append(error.to_dict())
        by_code[error.code] = by_code.get(error.code, 0) + 1

    top_modules = sorted(((path, len(rows)) for path, rows in grouped.items()), key=lambda item: (-item[1], item[0]))[:25]
    return {
        "schema_version": 2,
        "targets": DEFAULT_TARGETS,
        "error_count": len(errors),
        "error_count_by_code": {code: by_code[code] for code in sorted(by_code)},
        "top_modules": [{"module": module, "error_count": count} for module, count in top_modules],
        "errors_by_module": {path: grouped[path] for path in sorted(grouped)},
    }


def _load_policy(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch(path, pattern) for pattern in patterns)


def _stable_signature_from_row(row: dict[str, object]) -> str:
    stable = row.get("stable_signature")
    if isinstance(stable, str) and stable:
        return stable
    return f"{row.get('path', '')}:{row.get('code', '')}:{row.get('message', '')}"


def _protected_scope_summary(
    *,
    baseline_rows: list[dict[str, object]],
    current_errors: list[MypyError],
    patterns: list[str],
) -> dict[str, object]:
    baseline_signatures = {_stable_signature_from_row(row) for row in baseline_rows if _matches_any(str(row.get("path", "")), patterns)}
    current_signatures = {row.stable_signature() for row in current_errors if _matches_any(row.path, patterns)}
    new_signatures = sorted(current_signatures - baseline_signatures)
    return {
        "patterns": patterns,
        "baseline_error_count": len(baseline_signatures),
        "current_error_count": len(current_signatures),
        "new_error_count": len(new_signatures),
        "new_errors": new_signatures[:200],
    }


def _baseline_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    modules = payload.get("errors_by_module", {})
    rows: list[dict[str, object]] = []
    if not isinstance(modules, dict):
        return rows
    for raw in modules.values():
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    rows.append(item)
    return rows


def _summary_report(*, baseline_payload: dict[str, object], policy: dict[str, object]) -> dict[str, object]:
    modules = baseline_payload.get("errors_by_module", {})
    rows = _baseline_rows(baseline_payload)
    protected_patterns = [str(item) for item in policy.get("protected_patterns", []) if isinstance(item, str)]
    strict_patterns = [str(item) for item in policy.get("strict_patterns", []) if isinstance(item, str)]
    protected_modules = sorted(
        module
        for module in modules.keys()
        if isinstance(module, str) and _matches_any(module, protected_patterns)
    )
    strict_modules = sorted(
        module for module in modules.keys() if isinstance(module, str) and _matches_any(module, strict_patterns)
    )
    return {
        "schema_version": 1,
        "baseline_error_count": int(baseline_payload.get("error_count", 0)),
        "baseline_module_count": len(modules) if isinstance(modules, dict) else 0,
        "protected_patterns": protected_patterns,
        "protected_module_count": len(protected_modules),
        "protected_modules_sample": protected_modules[:25],
        "strict_patterns": strict_patterns,
        "strict_module_count": len(strict_modules),
        "strict_modules_sample": strict_modules[:25],
        "intentional_debt_modules": sorted({str(row.get("path", "")) for row in rows if str(row.get("path", "")).startswith(("scripts/", "sentientos/"))})[:25],
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
    parser.add_argument("--policy", default=str(POLICY_PATH), help="Path to mypy ratchet policy JSON.")
    parser.add_argument("--report", action="store_true", help="Print baseline/policy summary without running mypy.")
    parser.add_argument("--touched-surface", action="store_true", help="Run mypy on changed Python files in this branch.")
    parser.add_argument("--diff-base", default=os.getenv("SENTIENTOS_MYPY_DIFF_BASE"))
    args = parser.parse_args(argv)

    repo_root = Path.cwd()
    baseline_path = Path(args.baseline)
    policy = _load_policy(Path(args.policy))

    if args.report:
        if not baseline_path.exists():
            print(json.dumps({"status": "error", "reason": f"baseline not found: {baseline_path}"}, sort_keys=True))
            return 2
        baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        print(json.dumps({"status": "ok", "report": _summary_report(baseline_payload=baseline_payload, policy=policy)}, indent=2, sort_keys=True))
        return 0

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
    baseline_rows = _baseline_rows(baseline_payload)
    baseline_signatures = {_stable_signature_from_row(row) for row in baseline_rows}
    current_signatures = {row.stable_signature() for row in errors}
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

    protected_patterns = [str(item) for item in policy.get("protected_patterns", []) if isinstance(item, str)]
    if protected_patterns:
        protected = _protected_scope_summary(
            baseline_rows=baseline_rows,
            current_errors=errors,
            patterns=protected_patterns,
        )
        result["protected_scope"] = protected

    strict_patterns = [str(item) for item in policy.get("strict_patterns", []) if isinstance(item, str)]
    strict_targets = sorted({error.path for error in errors if _matches_any(error.path, strict_patterns)})
    if strict_targets:
        strict_code, strict_out = _run_mypy(["--strict", "--follow-imports=skip", *strict_targets])
        result["policy_strict_targets"] = strict_targets
        result["policy_strict_status"] = "ok" if strict_code == 0 else "failed"
        if strict_code != 0:
            result["policy_strict_excerpt"] = strict_out.splitlines()[:10]

    _write_status(result)
    _append_ratchet_event(result)
    print(json.dumps(result, indent=2, sort_keys=True))
    protected_regression = int(result.get("protected_scope", {}).get("new_error_count", 0)) if isinstance(result.get("protected_scope"), dict) else 0
    strict_failed = result.get("policy_strict_status") == "failed"
    return 1 if new_signatures or protected_regression or strict_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
