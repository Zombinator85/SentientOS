from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, TypedDict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import audit_immutability as ai
from scripts import tooling_status

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

# enable auto-approve when `CI` or `GIT_HOOKS` is set (see docs/ENVIRONMENT.md)
if os.getenv("LUMOS_AUTO_APPROVE") != "1" and (os.getenv("CI") or os.getenv("GIT_HOOKS")):
    os.environ["LUMOS_AUTO_APPROVE"] = "1"

ROOT = Path(__file__).resolve().parent.parent
CONFIG = Path("config/master_files.json")
VALID_EXTS = {".jsonl", ".json", ".log"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bounded_text(value: object) -> str:
    return str(value)[:MAX_ISSUE_LENGTH]


def _bounded_issues(issues: List[str]) -> List[str]:
    return [_bounded_text(issue) for issue in issues[:MAX_ISSUES]]


def _bounded_structured_issues(issues: List[AuditIssue]) -> List[AuditIssue]:
    bounded: List[AuditIssue] = []
    for issue in issues[:MAX_ISSUES]:
        bounded.append(
            {
                "code": issue["code"],
                "path": _bounded_text(issue["path"]),
                "expected": _bounded_text(issue["expected"]),
                "actual": _bounded_text(issue["actual"]),
                "details": _bounded_text(issue["details"]),
            }
        )
    return bounded


def write_result(
    *,
    ok: bool,
    issues: List[str],
    structured_issues: List[AuditIssue],
    error: str | None,
) -> dict[str, object]:
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
        pass
    return {}


def _is_log_file(path: Path) -> bool:
    """Return True if the file looks like a valid audit log."""
    try:
        first = path.read_text(encoding="utf-8", errors="ignore").lstrip().splitlines()[0]
    except Exception:
        return False

    if path.suffix.lower() in VALID_EXTS:
        return first.startswith("{") and "timestamp" in first and "data" in first

    if not path.suffix and first.startswith("{") and "timestamp" in first and "data" in first:
        return True
    return False


def _attempt_repair(line: str) -> Optional[str]:
    """Try simple fixes for malformed JSON lines."""
    s = line.strip()
    if s.endswith(","):
        s = s[:-1]
    if not s.endswith("}"):
        s = s + "}"
    try:
        json.loads(s)
    except Exception:
        return None
    return s


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _format_issue(path: Path, lineno: int, message: str) -> str:
    return f"{path.name}:{lineno}: {message}"


def _make_issue(
    *,
    code: IssueCode,
    path: Path,
    expected: object,
    actual: object,
    details: object,
) -> AuditIssue:
    return {
        "code": code,
        "path": str(path),
        "expected": _bounded_text(expected),
        "actual": _bounded_text(actual),
        "details": _bounded_text(details),
    }


def check_file(
    path: Path,
    prev_digest: str = "0" * 64,
    quarantine: bool = False,
    *,
    repair: bool = False,
    stats: Optional[Dict[str, int]] = None,
) -> Tuple[bool, List[str], str]:
    """Validate one audit log line by line."""
    if stats is not None:
        stats.setdefault("fixed", 0)
        stats.setdefault("quarantined", 0)
        stats.setdefault("unrecoverable", 0)

    errors: List[str] = []
    structured: List[AuditIssue] = []
    bad_lines: List[str] = []
    repair_lines: List[str] = []
    prev = prev_digest
    first = True
    prev_ts: datetime | None = None
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            if repair:
                fixed = _attempt_repair(line)
                if fixed is not None:
                    entry = json.loads(fixed)
                    repair_lines.append(fixed)
                    if stats is not None:
                        stats["fixed"] += 1
                else:
                    errors.append(_format_issue(path, lineno, exc.msg))
                    structured.append(
                        _make_issue(
                            code="schema_violation",
                            path=path,
                            expected="valid JSON object",
                            actual=line.strip() or "<empty>",
                            details=f"line {lineno}: {exc.msg}",
                        )
                    )
                    bad_lines.append(line)
                    if stats is not None:
                        stats["quarantined"] += 1
                        stats["unrecoverable"] += 1
                    continue
            else:
                errors.append(_format_issue(path, lineno, exc.msg))
                structured.append(
                    _make_issue(
                        code="schema_violation",
                        path=path,
                        expected="valid JSON object",
                        actual=line.strip() or "<empty>",
                        details=f"line {lineno}: {exc.msg}",
                    )
                )
                bad_lines.append(line)
                if stats is not None:
                    stats["quarantined"] += 1
                continue

        if not isinstance(entry, dict):
            errors.append(_format_issue(path, lineno, "not a JSON object"))
            structured.append(
                _make_issue(
                    code="schema_violation",
                    path=path,
                    expected="JSON object",
                    actual=type(entry).__name__,
                    details=f"line {lineno}: not a JSON object",
                )
            )
            bad_lines.append(line)
            if stats is not None:
                stats["quarantined"] += 1
                stats["unrecoverable"] += 1
            continue

        if entry.get("_void") is True:
            structured.append(
                _make_issue(
                    code="extra_entry",
                    path=path,
                    expected="non-void entry",
                    actual="_void=true",
                    details=f"line {lineno}: void marker encountered",
                )
            )
            continue

        if entry.get("prev_hash") != prev:
            if first:
                errors.append(_format_issue(path, lineno, "prev hash mismatch"))
                code: IssueCode = "genesis_marker_mismatch" if prev == "0" * 64 else "chain_prev_mismatch"
                structured.append(
                    _make_issue(
                        code=code,
                        path=path,
                        expected=prev,
                        actual=entry.get("prev_hash", "<missing>"),
                        details=f"line {lineno}: prev hash mismatch",
                    )
                )
            else:
                errors.append(_format_issue(path, lineno, "chain break"))
                structured.append(
                    _make_issue(
                        code="chain_prev_mismatch",
                        path=path,
                        expected=prev,
                        actual=entry.get("prev_hash", "<missing>"),
                        details=f"line {lineno}: chain break",
                    )
                )
        if "data" not in entry:
            errors.append(_format_issue(path, lineno, "missing data field"))
            structured.append(
                _make_issue(
                    code="missing_entry",
                    path=path,
                    expected="data field",
                    actual="missing",
                    details=f"line {lineno}: missing data field",
                )
            )
            bad_lines.append(line)
            if stats is not None:
                stats["quarantined"] += 1
                stats["unrecoverable"] += 1
            continue
        current_ts = _parse_timestamp(entry.get("timestamp"))
        if current_ts is None:
            structured.append(
                _make_issue(
                    code="schema_violation",
                    path=path,
                    expected="ISO-8601 timestamp",
                    actual=entry.get("timestamp", "<missing>"),
                    details=f"line {lineno}: invalid timestamp",
                )
            )
        elif prev_ts is not None and current_ts < prev_ts:
            errors.append(_format_issue(path, lineno, "timestamp order violation"))
            structured.append(
                _make_issue(
                    code="timestamp_order_violation",
                    path=path,
                    expected=prev_ts.isoformat(),
                    actual=current_ts.isoformat(),
                    details=f"line {lineno}: timestamp moved backwards",
                )
            )

        digest = ai._hash_entry(entry["timestamp"], entry["data"], entry.get("prev_hash", prev))
        current = entry.get("rolling_hash") or entry.get("hash")
        if current != digest:
            errors.append(_format_issue(path, lineno, "hash mismatch"))
            structured.append(
                _make_issue(
                    code="hash_mismatch",
                    path=path,
                    expected=digest,
                    actual=current or "<missing>",
                    details=f"line {lineno}: hash mismatch",
                )
            )
            bad_lines.append(line)
            if stats is not None:
                stats["quarantined"] += 1
                stats["unrecoverable"] += 1
            continue
        prev = current
        first = False
        prev_ts = current_ts or prev_ts

    if quarantine and bad_lines:
        bad_path = path.with_suffix(path.suffix + ".bad")
        bad_path.write_text("\n".join(bad_lines) + "\n", encoding="utf-8")

    if repair and repair_lines:
        repair_path = path.with_suffix(path.suffix + ".repairable")
        repair_path.write_text("\n".join(repair_lines) + "\n", encoding="utf-8")

    path_errors[str(path)] = structured
    return len(errors) == 0, errors, prev


path_errors: Dict[str, List[AuditIssue]] = {}


def verify_audits_detailed(
    quarantine: bool = False,
    directory: Path | None = None,
    *,
    repair: bool = False,
) -> tuple[dict[str, List[AuditIssue]], float, Dict[str, int]]:
    issues_by_path: dict[str, List[AuditIssue]] = {}
    results, percent, stats = verify_audits(quarantine=quarantine, directory=directory, repair=repair)
    for path in sorted(results.keys()):
        issues_by_path[path] = list(path_errors.get(path, []))
    return issues_by_path, percent, stats


def verify_audits(
    quarantine: bool = False,
    directory: Path | None = None,
    *,
    repair: bool = False,
) -> tuple[dict[str, List[str]], float, Dict[str, int]]:
    """Verify multiple audit logs."""
    results: dict[str, List[str]] = {}
    path_errors.clear()
    logs: List[Path] = []
    stats: Dict[str, int] = {"fixed": 0, "quarantined": 0, "unrecoverable": 0}

    if directory is not None:
        logs = sorted(p for p in Path(directory).iterdir() if _is_log_file(p))
    else:
        data = _load_config()
        for file in data.keys():
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


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Audit log verifier",
        epilog="Set LUMOS_AUTO_APPROVE=1 to bypass prompts.",
    )
    ap.add_argument("path", nargs="?", help="Log directory or single file")
    ap.add_argument("--repair", action="store_true", help="attempt to repair malformed lines and chain")
    ap.add_argument("--auto-repair", action="store_true", help="heal logs then verify")
    ap.add_argument("--check-only", action="store_true", help="verify without modifying logs")
    ap.add_argument("--auto-approve", action="store_true", help="skip prompts (deprecated, use --no-input)")
    ap.add_argument("--no-input", action="store_true", help="skip prompts")
    ap.add_argument("--strict", action="store_true", help="abort if repairs occur")
    args = ap.parse_args(argv)

    all_issues: List[str] = []
    structured_issues: List[AuditIssue] = []
    error: str | None = None
    try:
        auto_env = (
            args.auto_approve
            or args.no_input
            or args.strict
            or os.getenv("LUMOS_AUTO_APPROVE") == "1"
        )
        if auto_env:
            os.environ["LUMOS_AUTO_APPROVE"] = "1"

        strict_env = args.strict or os.getenv("STRICT") == "1"
        if args.strict:
            os.environ["STRICT"] = "1"

        directory = None
        if args.path:
            p = Path(args.path)
            directory = p if p.is_dir() else p.parent

        logs: list[Path] = []
        if directory is not None:
            logs = sorted(p for p in Path(directory).iterdir() if _is_log_file(p))
        else:
            data = _load_config()
            for file in data.keys():
                q = Path(file)
                if not q.is_absolute():
                    q = ROOT / q
                if _is_log_file(q):
                    logs.append(q)

        res, percent, stats = verify_audits(
            quarantine=True,
            directory=directory,
            repair=args.repair and not args.check_only,
        )

        chain_ok = all(not e for e in res.values())
        total_fixed = 0

        if args.auto_repair and not chain_ok:
            from scripts import audit_repair

            prev = "0" * 64
            for log in logs:
                prev, fixed = audit_repair.repair_log(log, prev, check_only=False)
                total_fixed += fixed
            res, percent, stats = verify_audits(quarantine=True, directory=directory, repair=False)
            chain_ok = all(not e for e in res.values())
        elif args.repair and not args.check_only:
            from scripts import audit_repair

            prev = "0" * 64
            for log in logs:
                prev, fixed = audit_repair.repair_log(log, prev, check_only=False)
                print(f"Repair {log.name}: {fixed} fixed")
                total_fixed += fixed
            res, percent, stats = verify_audits(quarantine=True, directory=directory, repair=False)
            chain_ok = all(not e for e in res.values())

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
        if args.repair or args.auto_repair:
            print(
                f"{stats['fixed']} lines fixed, {stats['quarantined']} lines quarantined, {stats['unrecoverable']} unrecoverable"
            )
        if (
            stats.get("fixed", 0) == 0
            and stats.get("quarantined", 0) == 0
            and stats.get("unrecoverable", 0) == 0
        ):
            print("✅ No mismatches.")

        status_label = "passed" if chain_ok else "failed"
        reason = None if chain_ok else "integrity_mismatch"
        if not logs:
            status_label = "skipped"
            reason = "no_audit_logs_found"
            chain_ok = True
        exit_code = 0
        if strict_env and total_fixed:
            print("Strict mode: repairs detected")
            status_label = "failed"
            reason = "strict_mode_repairs_detected"
            exit_code = 1
            all_issues.append("strict_mode_repairs_detected")
        elif not chain_ok:
            exit_code = 1

        summary = tooling_status.render_result("verify_audits", status=status_label, reason=reason)
        print(json.dumps(summary, sort_keys=True))
        write_result(ok=chain_ok, issues=all_issues, structured_issues=structured_issues, error=None)
        return exit_code
    except Exception as exc:  # pragma: no cover - defensive
        error = str(exc)
        write_result(ok=False, issues=all_issues, structured_issues=structured_issues, error=error)
        print(json.dumps({"tool": "verify_audits", "status": "error", "reason": error}, sort_keys=True))
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
