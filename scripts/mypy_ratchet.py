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
from typing import Any

BASELINE_PATH = Path("glow/contracts/mypy_baseline.json")
POLICY_PATH = Path("glow/contracts/mypy_policy.json")
STATUS_PATH = Path("glow/forge/ratchets/mypy_ratchet_status.json")
RATCHET_LOG_PATH = Path("pulse/ratchets.jsonl")
CANONICAL_BASELINE_PATH = Path("glow/contracts/canonical_typing_baseline.json")
CLUSTER_SUMMARY_PATH = Path("glow/contracts/typing_cluster_summary.json")
RATCHET_STATUS_PATH = Path("glow/contracts/typing_ratchet_status.json")
DIGEST_PATH = Path("glow/contracts/final_typing_baseline_digest.json")
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


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch(path, pattern) for pattern in patterns)


def _stable_signature_from_row(row: dict[str, object]) -> str:
    stable = row.get("stable_signature")
    if isinstance(stable, str) and stable:
        return stable
    return f"{row.get('path', '')}:{row.get('code', '')}:{row.get('message', '')}"


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


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
    modules_obj = baseline_payload.get("errors_by_module", {})
    modules = modules_obj if isinstance(modules_obj, dict) else {}
    rows = _baseline_rows(baseline_payload)
    protected_patterns = _as_string_list(policy.get("protected_patterns", []))
    strict_patterns = _as_string_list(policy.get("strict_patterns", []))
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
        "baseline_error_count": _as_int(baseline_payload.get("error_count", 0)),
        "baseline_module_count": len(modules),
        "protected_patterns": protected_patterns,
        "protected_module_count": len(protected_modules),
        "protected_modules_sample": protected_modules[:25],
        "strict_patterns": strict_patterns,
        "strict_module_count": len(strict_modules),
        "strict_modules_sample": strict_modules[:25],
        "intentional_debt_modules": sorted({str(row.get("path", "")) for row in rows if str(row.get("path", "")).startswith(("scripts/", "sentientos/"))})[:25],
    }


def _write_status(payload: dict[str, object]) -> None:
    _write_json(STATUS_PATH, payload)


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


def _tracked_python_files(repo_root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return []
    return sorted(line.strip() for line in completed.stdout.splitlines() if line.strip())


def _canonical_roots(policy: dict[str, object]) -> list[str]:
    roots = policy.get("canonical_roots")
    if isinstance(roots, list) and roots:
        return [str(item).strip().rstrip("/") for item in roots if str(item).strip()]
    return ["."]


def _canonical_excludes(policy: dict[str, object]) -> list[str]:
    excludes = policy.get("canonical_exclude_globs")
    if isinstance(excludes, list):
        return [str(item) for item in excludes if isinstance(item, str)]
    return []


def _in_roots(path: str, roots: list[str]) -> bool:
    for root in roots:
        if root in {"", "."}:
            return True
        if path == root or path.startswith(f"{root}/"):
            return True
    return False


def _canonical_repo_targets(repo_root: Path, policy: dict[str, object]) -> list[str]:
    roots = _canonical_roots(policy)
    excludes = _canonical_excludes(policy)
    files = _tracked_python_files(repo_root)
    return sorted(path for path in files if _in_roots(path, roots) and not _matches_any(path, excludes))


def _path_cluster(path: str) -> str:
    if "/" not in path:
        return "_repo_root"
    return path.split("/", 1)[0]


def _cluster_summary(errors: list[MypyError], *, policy: dict[str, object]) -> dict[str, object]:
    by_cluster: dict[str, dict[str, int]] = {}
    for error in errors:
        cluster = _path_cluster(error.path)
        data = by_cluster.setdefault(cluster, {"error_count": 0, "module_count": 0})
        data["error_count"] += 1
    module_sets: dict[str, set[str]] = {}
    for error in errors:
        cluster = _path_cluster(error.path)
        module_sets.setdefault(cluster, set()).add(error.path)
    for cluster, modules in module_sets.items():
        by_cluster[cluster]["module_count"] = len(modules)
    ordered = sorted(by_cluster.items(), key=lambda item: (-item[1]["error_count"], item[0]))
    return {
        "schema_version": 1,
        "excluded_glob_count": len(_canonical_excludes(policy)),
        "cluster_count": len(ordered),
        "clusters": [
            {"cluster": cluster, "error_count": counts["error_count"], "module_count": counts["module_count"]}
            for cluster, counts in ordered
        ],
    }


def _code_family_summary(errors: list[MypyError]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for error in errors:
        counts[error.code] = counts.get(error.code, 0) + 1
    return {code: counts[code] for code in sorted(counts)}


def _promotable_modules(
    *,
    baseline_rows: list[dict[str, object]],
    current_errors: list[MypyError],
    protected_patterns: list[str],
) -> list[str]:
    baseline_modules = {
        str(row.get("path", ""))
        for row in baseline_rows
        if isinstance(row, dict) and _matches_any(str(row.get("path", "")), protected_patterns)
    }
    current_modules = {row.path for row in current_errors if _matches_any(row.path, protected_patterns)}
    return sorted(module for module in baseline_modules if module and module not in current_modules)


def _emit_typing_artifacts(
    *,
    baseline_payload: dict[str, object],
    current_errors: list[MypyError],
    result: dict[str, object],
    policy: dict[str, object],
    checked_targets: list[str],
) -> None:
    baseline_rows = _baseline_rows(baseline_payload)
    protected_patterns = _as_string_list(policy.get("protected_patterns", []))
    baseline_signatures = {_stable_signature_from_row(row) for row in baseline_rows}
    current_signatures = {row.stable_signature() for row in current_errors}
    deferred_signatures = sorted(baseline_signatures & current_signatures)
    ratcheted_signatures = sorted(current_signatures - baseline_signatures)
    promotable = _promotable_modules(
        baseline_rows=baseline_rows,
        current_errors=current_errors,
        protected_patterns=protected_patterns,
    )
    protected_scope = result.get("protected_scope", {})
    protected_new = 0
    if isinstance(protected_scope, dict):
        protected_new = _as_int(protected_scope.get("new_error_count", 0))

    canonical = {
        "schema_version": 1,
        "config_file": "mypy.ini",
        "checked_target_count": len(checked_targets),
        "checked_targets_sample": checked_targets[:200],
        "excluded_globs": _canonical_excludes(policy),
        "error_count": len(current_errors),
        "module_count": len({error.path for error in current_errors}),
        "error_count_by_code": _code_family_summary(current_errors),
    }
    cluster_summary = _cluster_summary(current_errors, policy=policy)
    strict_targets_obj = result.get("policy_strict_targets", [])
    strict_target_count = len(strict_targets_obj) if isinstance(strict_targets_obj, list) else 0
    ratchet_status = {
        "schema_version": 1,
        "status": str(result.get("status", "unknown")),
        "ratcheted_new_error_count": len(ratcheted_signatures),
        "protected_new_error_count": protected_new,
        "deferred_debt_error_count": len(deferred_signatures),
        "promotable_protected_modules": promotable[:100],
        "policy_strict_status": str(result.get("policy_strict_status", "not_run")),
        "policy_strict_target_count": strict_target_count,
        "excluded_glob_count": len(_canonical_excludes(policy)),
    }
    digest = {
        "schema_version": 1,
        "canonical_error_count": canonical["error_count"],
        "baseline_error_count": _as_int(baseline_payload.get("error_count", 0)),
        "delta_vs_baseline": _as_int(canonical["error_count"]) - _as_int(baseline_payload.get("error_count", 0)),
        "cluster_count": cluster_summary["cluster_count"],
        "ratchet_status": ratchet_status["status"],
        "policy_strict_status": ratchet_status["policy_strict_status"],
        "excluded_glob_count": ratchet_status["excluded_glob_count"],
    }
    _write_json(CANONICAL_BASELINE_PATH, canonical)
    _write_json(CLUSTER_SUMMARY_PATH, cluster_summary)
    _write_json(RATCHET_STATUS_PATH, ratchet_status)
    _write_json(DIGEST_PATH, digest)


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

    targets = _canonical_repo_targets(repo_root, policy)
    if not targets:
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
        baseline["targets"] = _canonical_roots(policy)
        baseline["target_file_count"] = len(targets)
        baseline["canonical_config_file"] = "mypy.ini"
        baseline["canonical_exclude_globs"] = _canonical_excludes(policy)
        baseline["canonical_roots"] = _canonical_roots(policy)
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
        "checked_target_count": len(targets),
        "checked_targets_sample": targets[:200],
        "new_error_count": len(new_signatures),
        "new_errors": new_signatures[:200],
    }
    if strict_subset:
        strict_code, strict_out = _run_mypy(["--strict", "--follow-imports=skip", *strict_subset])
        result["strict_subset_checked"] = strict_subset
        result["strict_subset_status"] = "ok" if strict_code == 0 else "failed"
        if strict_code != 0:
            result["strict_subset_excerpt"] = strict_out.splitlines()[:10]

    protected_patterns = _as_string_list(policy.get("protected_patterns", []))
    if protected_patterns:
        protected = _protected_scope_summary(
            baseline_rows=baseline_rows,
            current_errors=errors,
            patterns=protected_patterns,
        )
        result["protected_scope"] = protected

    strict_patterns = _as_string_list(policy.get("strict_patterns", []))
    strict_targets = sorted({error.path for error in errors if _matches_any(error.path, strict_patterns)})
    enforced_patterns = _as_string_list(policy.get("strict_enforced_patterns", []))
    enforced_targets = sorted({path for path in targets if _matches_any(path, enforced_patterns)})
    all_strict_targets = sorted(set(strict_targets + enforced_targets))
    if all_strict_targets:
        strict_code, strict_out = _run_mypy(["--strict", "--follow-imports=skip", *all_strict_targets])
        result["policy_strict_targets"] = all_strict_targets
        result["policy_strict_status"] = "ok" if strict_code == 0 else "failed"
        if strict_code != 0:
            result["policy_strict_excerpt"] = strict_out.splitlines()[:10]

    _write_status(result)
    _append_ratchet_event(result)
    _emit_typing_artifacts(
        baseline_payload=baseline_payload,
        current_errors=errors,
        result=result,
        policy=policy,
        checked_targets=targets,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    protected_scope = result.get("protected_scope", {})
    protected_regression = _as_int(protected_scope.get("new_error_count", 0)) if isinstance(protected_scope, dict) else 0
    strict_failed = result.get("policy_strict_status") == "failed"
    return 1 if new_signatures or protected_regression or strict_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
