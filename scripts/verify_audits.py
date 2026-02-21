from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, TypedDict, cast

CODE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path.cwd().resolve()
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from sentientos.audit_sink import AuditSinkConfig, resolve_audit_paths
from sentientos.audit_chain_gate import verify_audit_chain, write_audit_chain_report
from sentientos.privilege import require_admin_banner, require_lumos_approval

os.environ["SENTIENTOS_AUDIT_MODE"] = "baseline"

require_admin_banner()
require_lumos_approval()

import audit_immutability as ai
from scripts import tooling_status
from sentientos.recovery_tasks import enqueue_audit_chain_repair_task

RESULT_PATH = Path("glow/audits/verify_audits_result.json")
SCHEMA_VERSION = "1.0"
MAX_ISSUES = 20
MAX_ISSUE_LENGTH = 200

IssueCode = Literal[
    "missing_entry",
    "extra_entry",
    "hash_mismatch",
    "timestamp_order_violation",
    "schema_violation",
    "chain_prev_mismatch",
    "genesis_marker_mismatch",
    "unknown",
]


class AuditIssue(TypedDict):
    code: IssueCode
    path: str
    expected: str
    actual: str
    details: str


if os.getenv("LUMOS_AUTO_APPROVE") != "1" and (os.getenv("CI") or os.getenv("GIT_HOOKS")):
    os.environ["LUMOS_AUTO_APPROVE"] = "1"

ROOT = REPO_ROOT
CONFIG = Path("config/master_files.json")
VALID_EXTS = {".jsonl", ".json", ".log"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bounded_text(value: object) -> str:
    return str(value)[:MAX_ISSUE_LENGTH]


def _bounded_issues(issues: List[str]) -> List[str]:
    return [_bounded_text(issue) for issue in issues[:MAX_ISSUES]]


def _bounded_structured_issues(issues: List[AuditIssue]) -> List[AuditIssue]:
    return [
        {
            "code": issue["code"],
            "path": _bounded_text(issue["path"]),
            "expected": _bounded_text(issue["expected"]),
            "actual": _bounded_text(issue["actual"]),
            "details": _bounded_text(issue["details"]),
        }
        for issue in issues[:MAX_ISSUES]
    ]


def write_result(*, ok: bool, issues: List[str], structured_issues: List[AuditIssue], error: str | None) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": _iso_now(),
        "tool": "verify_audits",
        "ok": ok,
        "issues": _bounded_issues(issues),
        "structured_issues": _bounded_structured_issues(structured_issues),
        "error": error,
    }
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _load_config() -> dict[str, str]:
    if not CONFIG.exists():
        return {}
    try:
        raw = json.loads(CONFIG.read_text())
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}
    except Exception:
        return {}
    return {}


def _is_log_file(path: Path) -> bool:
    try:
        first = path.read_text(encoding="utf-8", errors="ignore").lstrip().splitlines()[0]
    except Exception:
        return False
    if path.suffix.lower() in VALID_EXTS:
        return first.startswith("{") and "timestamp" in first and "data" in first
    return bool(not path.suffix and first.startswith("{") and "timestamp" in first and "data" in first)


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_issue(path: Path, lineno: int, message: str) -> str:
    return f"{path.name}:{lineno}: {message}"


def _make_issue(*, code: IssueCode, path: Path, expected: object, actual: object, details: object) -> AuditIssue:
    return {
        "code": code,
        "path": str(path),
        "expected": _bounded_text(expected),
        "actual": _bounded_text(actual),
        "details": _bounded_text(details),
    }


def check_file(path: Path, prev_digest: str = "0" * 64, quarantine: bool = False, *, repair: bool = False, stats: Optional[Dict[str, int]] = None) -> Tuple[bool, List[str], str]:
    _ = repair
    if stats is not None:
        stats.setdefault("fixed", 0)
        stats.setdefault("quarantined", 0)
        stats.setdefault("unrecoverable", 0)

    errors: List[str] = []
    structured: List[AuditIssue] = []
    prev = prev_digest
    first = True
    prev_ts: datetime | None = None
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(_format_issue(path, lineno, exc.msg))
            structured.append(_make_issue(code="schema_violation", path=path, expected="valid JSON object", actual=line.strip() or "<empty>", details=f"line {lineno}: {exc.msg}"))
            if stats is not None:
                stats["quarantined"] += 1
                stats["unrecoverable"] += 1
            continue
        if not isinstance(entry, dict):
            errors.append(_format_issue(path, lineno, "not a JSON object"))
            structured.append(_make_issue(code="schema_violation", path=path, expected="JSON object", actual=type(entry).__name__, details=f"line {lineno}: not a JSON object"))
            continue
        if entry.get("_void") is True:
            structured.append(_make_issue(code="extra_entry", path=path, expected="non-void entry", actual="_void=true", details=f"line {lineno}: void marker encountered"))
            continue
        if entry.get("prev_hash") != prev:
            errors.append(_format_issue(path, lineno, "chain break" if not first else "prev hash mismatch"))
            code: IssueCode = "genesis_marker_mismatch" if first and prev == "0" * 64 else "chain_prev_mismatch"
            structured.append(_make_issue(code=code, path=path, expected=prev, actual=entry.get("prev_hash", "<missing>"), details=f"line {lineno}: prev hash mismatch"))
        if "data" not in entry:
            errors.append(_format_issue(path, lineno, "missing data field"))
            structured.append(_make_issue(code="missing_entry", path=path, expected="data field", actual="missing", details=f"line {lineno}: missing data field"))
            continue
        current_ts = _parse_timestamp(entry.get("timestamp"))
        if current_ts is None:
            structured.append(_make_issue(code="schema_violation", path=path, expected="ISO-8601 timestamp", actual=entry.get("timestamp", "<missing>"), details=f"line {lineno}: invalid timestamp"))
        elif prev_ts is not None and current_ts < prev_ts:
            errors.append(_format_issue(path, lineno, "timestamp order violation"))
            structured.append(_make_issue(code="timestamp_order_violation", path=path, expected=prev_ts.isoformat(), actual=current_ts.isoformat(), details=f"line {lineno}: timestamp moved backwards"))

        digest = ai._hash_entry(entry["timestamp"], entry["data"], entry.get("prev_hash", prev))
        current = entry.get("rolling_hash") or entry.get("hash")
        if current != digest:
            errors.append(_format_issue(path, lineno, "hash mismatch"))
            structured.append(_make_issue(code="hash_mismatch", path=path, expected=digest, actual=current or "<missing>", details=f"line {lineno}: hash mismatch"))
            continue
        prev = str(current)
        first = False
        prev_ts = current_ts or prev_ts

    path_errors[str(path)] = structured
    if quarantine and errors:
        path.with_suffix(path.suffix + ".bad").write_text("\n".join(errors) + "\n", encoding="utf-8")
    return len(errors) == 0, errors, prev


path_errors: Dict[str, List[AuditIssue]] = {}


def verify_audits_detailed(quarantine: bool = False, directory: Path | None = None, *, repair: bool = False) -> tuple[dict[str, List[AuditIssue]], float, Dict[str, int]]:
    issues_by_path: dict[str, List[AuditIssue]] = {}
    results, percent, stats = verify_audits(quarantine=quarantine, directory=directory, repair=repair)
    for path in sorted(results.keys()):
        issues_by_path[path] = list(path_errors.get(path, []))
    return issues_by_path, percent, stats


def verify_audits(quarantine: bool = False, directory: Path | None = None, *, repair: bool = False) -> tuple[dict[str, List[str]], float, Dict[str, int]]:
    results: dict[str, List[str]] = {}
    path_errors.clear()
    logs: List[Path] = []
    stats: Dict[str, int] = {"fixed": 0, "quarantined": 0, "unrecoverable": 0}

    if directory is not None:
        logs = sorted(p for p in Path(directory).iterdir() if _is_log_file(p))
    else:
        for file in _load_config().keys():
            p = Path(file)
            if not p.is_absolute():
                p = ROOT / p
            if _is_log_file(p):
                logs.append(p)

    prev = "0" * 64
    valid = 0
    for path in logs:
        _, errs, prev = check_file(path, prev, quarantine=quarantine, repair=repair, stats=stats)
        results[str(path)] = errs
        if not errs:
            valid += 1
    percent = 0.0 if not logs else valid / len(logs) * 100
    return results, percent, stats


def _tracked_content(path: Path) -> str | None:
    try:
        rel = path.relative_to(REPO_ROOT)
    except ValueError:
        return None
    completed = subprocess.run(["git", "show", f"HEAD:{rel.as_posix()}"], check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return None
    return completed.stdout


def _verify_single(path: Path) -> tuple[bool, list[str]]:
    if not path.exists():
        return (True, [])
    ok, errors, _ = check_file(path, "0" * 64, quarantine=False, repair=False, stats={})
    return (ok, errors)


def _runtime_error_details(path: Path, errors: list[str]) -> tuple[str, list[str]]:
    if not errors:
        return "unknown", []
    kind: str = "unknown"
    examples: list[str] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    has_final_newline = path.read_text(encoding="utf-8", errors="replace").endswith("\n")
    for issue in errors[:5]:
        examples.append(issue[:160])
        msg = issue.lower()
        if "chain break" in msg or "prev hash mismatch" in msg:
            kind = "chain_break"
        elif "hash mismatch" in msg:
            if kind == "unknown":
                kind = "chain_break"
        elif "missing data" in msg or "not a json object" in msg:
            if kind == "unknown":
                kind = "schema_violation"
        elif "expecting" in msg or "unterminated" in msg or "extra data" in msg:
            line_no = 0
            try:
                line_no = int(issue.split(":", 2)[1])
            except Exception:
                line_no = 0
            if line_no == len(lines) and not has_final_newline:
                kind = "truncated_line"
            elif kind == "unknown":
                kind = "malformed_json"
    return kind, examples


def _strict_privileged_status(config: AuditSinkConfig) -> dict[str, object]:
    baseline_ok, baseline_errors = _verify_single(config.baseline_path)
    runtime_ok, runtime_errors = _verify_single(config.runtime_path)

    baseline_status = "ok"
    tracked = _tracked_content(config.baseline_path)
    if tracked is not None and config.baseline_path.exists() and config.baseline_path.read_text(encoding="utf-8") != tracked:
        baseline_status = "drift"
    if not baseline_ok:
        baseline_status = "broken"

    runtime_status = "ok" if runtime_ok else "broken"
    runtime_error_kind, runtime_error_examples = _runtime_error_details(config.runtime_path, runtime_errors)
    suggested_fix = "run: make audit-repair"
    if runtime_error_kind in {"malformed_json", "truncated_line"}:
        suggested_fix = "run: make audit-repair (doctor will quarantine malformed/truncated runtime evidence)"
    return {
        "baseline_status": baseline_status,
        "runtime_status": runtime_status,
        "baseline_path": str(config.baseline_path),
        "runtime_path": str(config.runtime_path),
        "baseline_errors": baseline_errors,
        "runtime_errors": runtime_errors,
        "runtime_error_kind": runtime_error_kind,
        "runtime_error_examples": runtime_error_examples,
        "suggested_fix": suggested_fix,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Audit log verifier", epilog="Set LUMOS_AUTO_APPROVE=1 to bypass prompts.")
    ap.add_argument("path", nargs="?", help="Log directory or single file")
    ap.add_argument("--repair", action="store_true", help="attempt to repair malformed lines and chain")
    ap.add_argument("--auto-repair", action="store_true", help="heal logs then verify")
    ap.add_argument("--check-only", action="store_true", help="verify without modifying logs")
    ap.add_argument("--auto-approve", action="store_true", help="skip prompts")
    ap.add_argument("--no-input", action="store_true", help="skip prompts")
    ap.add_argument("--strict", action="store_true", help="abort if strict privileged audit checks fail")
    ap.add_argument("--show-paths", action="store_true", help="show resolved privileged baseline/runtime audit paths")
    ap.add_argument("--runtime-dir", type=str, help="override runtime audit directory")
    args = ap.parse_args(argv)

    global REPO_ROOT, ROOT
    REPO_ROOT = Path.cwd().resolve()
    ROOT = REPO_ROOT
    all_issues: List[str] = []
    structured_issues: List[AuditIssue] = []
    try:
        if args.auto_approve or args.no_input or args.strict or os.getenv("LUMOS_AUTO_APPROVE") == "1":
            os.environ["LUMOS_AUTO_APPROVE"] = "1"

        if args.runtime_dir:
            os.environ["SENTIENTOS_AUDIT_RUNTIME_DIR"] = args.runtime_dir
        sink_config = resolve_audit_paths(REPO_ROOT)

        if args.show_paths:
            print(json.dumps({"baseline_path": str(sink_config.baseline_path), "runtime_path": str(sink_config.runtime_path), "mode": sink_config.mode}, sort_keys=True))

        directory = None
        if args.path:
            p = Path(args.path)
            directory = p if p.is_dir() else p.parent

        res, percent, stats = verify_audits(quarantine=True, directory=directory, repair=args.repair and not args.check_only)
        chain_ok = all(not e for e in res.values())
        audit_chain = verify_audit_chain(REPO_ROOT)
        audit_chain_report = write_audit_chain_report(REPO_ROOT, audit_chain)

        for file, errors in res.items():
            structured_issues.extend(path_errors.get(file, []))
            if not errors:
                print(f"{file}: valid")
            else:
                print(f"{file}: {len(errors)} issue(s)")
                all_issues.extend(errors)
                for err in errors:
                    print(f"  {err}")
        print(f"{percent:.1f}% of logs valid")
        if (stats.get("fixed", 0), stats.get("quarantined", 0), stats.get("unrecoverable", 0)) == (0, 0, 0):
            print("✅ No mismatches.")
        print(json.dumps({"audit_chain_status": audit_chain.status, "audit_chain_report": str(audit_chain_report.relative_to(REPO_ROOT))}, sort_keys=True))

        strict_output = _strict_privileged_status(sink_config) if args.strict else None
        if strict_output is not None:
            baseline_errors = cast(List[str], strict_output["baseline_errors"])
            runtime_errors = cast(List[str], strict_output["runtime_errors"])
            print(json.dumps({
                "baseline_status": strict_output["baseline_status"],
                "runtime_status": strict_output["runtime_status"],
                "baseline_path": strict_output["baseline_path"],
                "runtime_path": strict_output["runtime_path"],
                "runtime_error_kind": strict_output["runtime_error_kind"],
                "runtime_error_examples": strict_output["runtime_error_examples"],
                "suggested_fix": strict_output["suggested_fix"],
            }, sort_keys=True))
            all_issues.extend([f"baseline:{issue}" for issue in baseline_errors])
            all_issues.extend([f"runtime:{issue}" for issue in runtime_errors])

        status_label = "passed"
        reason = None
        exit_code = 0
        if not chain_ok and not args.strict:
            status_label = "failed"
            reason = "integrity_mismatch"
            exit_code = 1
        if args.strict and strict_output is not None and (
            strict_output["baseline_status"] in {"drift", "broken"} or strict_output["runtime_status"] == "broken"
        ):
            status_label = "failed"
            reason = "strict_privileged_audit_failure"
            exit_code = 1
        if args.strict and not audit_chain.ok:
            status_label = "failed"
            reason = "audit_chain_broken"
            exit_code = 1
            if os.getenv("SENTIENTOS_AUDIT_CHAIN_ENFORCE", "0") == "1":
                enqueue_audit_chain_repair_task(
                    REPO_ROOT,
                    reason="verify_audits_strict_failed",
                    incident_id=None,
                )

        summary = tooling_status.render_result("verify_audits", status=status_label, reason=reason)
        print(json.dumps(summary, sort_keys=True))
        write_result(ok=exit_code == 0, issues=all_issues, structured_issues=structured_issues, error=None)
        return exit_code
    except Exception as exc:  # pragma: no cover
        write_result(ok=False, issues=all_issues, structured_issues=structured_issues, error=str(exc))
        print(json.dumps({"tool": "verify_audits", "status": "error", "reason": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
